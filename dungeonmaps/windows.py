"""Windows: WoW's window through Windows Graphics Capture, the overlay drawn with Tk.

  * Capture: the windows-capture package (Windows Graphics Capture) on the "World of Warcraft" window:
    keeps working while the game is covered (not while minimized). No picker, nothing to set up.
  * Placement: Windows says where the window is (DWM frame bounds), so the overlay sits exactly over
    the dungeon map; checked every frame.
  * Overlay: a borderless, always-on-top, click-through Tk window over the map canvas (Tk comes with
    Python). WoW must run windowed or "windowed fullscreen" (exclusive fullscreen hides overlays).

    DungeonMaps.exe            (or: python -m dungeonmaps)

Start it before or after WoW; it waits for the game and closes itself 3 s after WoW closes (or after
10 minutes if WoW never opens).
Only one copy runs at a time. Log: %LOCALAPPDATA%\DungeonMaps\state\tracker.log
"""

import ctypes
import math
import os
import sys
import threading
import time

import numpy as np

from . import beacon
from .core import Core
from .data import user_dir
from .share import Share

WOW_TITLE = "World of Warcraft"
MAX_FPS = 60
LOG_FILE = os.path.join(user_dir("state"), "tracker.log")
KEY = "#ff00fe"  # the overlay's transparent colour


def info(*a):
    try:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as fh:
            fh.write(time.strftime("%H:%M:%S ") + " ".join(str(x) for x in a) + "\n")
    except OSError:
        pass
    if sys.stderr:
        print(*a, file=sys.stderr, flush=True)


# ------------------------------------------------------------------------------------------------
# Win32
# ------------------------------------------------------------------------------------------------

if sys.platform == "win32":
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    dwmapi = ctypes.windll.dwmapi
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # physical pixels everywhere
    except Exception:
        user32.SetProcessDPIAware()


def find_wow():
    """HWND of WoW's main window, or None."""
    hwnd = user32.FindWindowW(None, WOW_TITLE)
    return hwnd if hwnd and user32.IsWindowVisible(hwnd) else None


def frame_origin(hwnd):
    """Screen position (physical pixels) of the window's captured picture: its DWM frame bounds."""
    r = wintypes.RECT()
    if dwmapi.DwmGetWindowAttribute(hwnd, 9, ctypes.byref(r), ctypes.sizeof(r)) != 0:  # EXTENDED_FRAME_BOUNDS
        user32.GetWindowRect(hwnd, ctypes.byref(r))
    return r.left, r.top, user32.IsIconic(hwnd) != 0


# ------------------------------------------------------------------------------------------------
# Capture
# ------------------------------------------------------------------------------------------------

class Frame:
    def __init__(self, rows, w, h, serial):
        self.rows, self.w, self.h, self.serial = rows, w, h, serial

    def crop(self, x, y, w, h):
        x0, y0 = max(0, int(round(x))), max(0, int(round(y)))
        x1, y1 = min(self.w, int(round(x + w))), min(self.rows.shape[0], int(round(y + h)))
        if x1 <= x0 or y1 <= y0:
            return None
        return np.ascontiguousarray(self.rows[y0:y1, x0:x1, 2::-1])  # BGRA -> RGB


class WindowCapture:
    def __init__(self):
        self.frame = None
        self.full = None
        self.serial = 0
        self.top = 400
        self.want_full = False
        self.new = threading.Event()
        self.control = None
        self.closed = False
        self.last = 0.0

    def start(self, hwnd):
        from windows_capture import WindowsCapture  # windows-capture 2.0.x
        cap = WindowsCapture(cursor_capture=False, draw_border=False, minimum_update_interval=1000 // MAX_FPS,
                             window_hwnd=hwnd)

        @cap.event
        def on_frame_arrived(frame, control):
            now = time.monotonic()
            if now - self.last < 1 / MAX_FPS and not self.want_full:
                return
            self.last = now
            buf = frame.frame_buffer  # (h, w, 4) BGRA, only valid during this call
            h, w = buf.shape[:2]
            full = self.want_full
            self.want_full = False
            rows = np.array(buf[:h if full else min(h, self.top)])
            self.serial += 1
            self.frame = Frame(rows, w, h, self.serial)
            if full:
                self.full = self.frame
            self.new.set()

        @cap.event
        def on_closed():
            self.closed = True
            self.new.set()

        self.closed = False
        self.control = cap.start_free_threaded()

    def finished(self):
        try:
            return self.control is None or self.closed or self.control.is_finished()
        except Exception:
            return True

    def stop(self):
        try:
            if self.control:
                self.control.stop()
        except Exception:
            pass
        self.control = None
        self.frame = None


# ------------------------------------------------------------------------------------------------
# Overlay
# ------------------------------------------------------------------------------------------------

def _dim(hex_colour, k):
    """Blend towards black (Tk has no per-item alpha)."""
    r, g, b = (int(hex_colour[i:i + 2], 16) for i in (1, 3, 5))
    return "#%02x%02x%02x" % (int(r * k), int(g * k), int(b * k))


class Overlay:
    """A click-through, always-on-top window over the dungeon map. Runs on the main thread."""

    def __init__(self):
        import tkinter as tk
        self.tk = tk
        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.geometry("1x1+-32000+-32000")  # mapped once, off screen, at start (before the game matters)
        self.root.attributes("-topmost", True)
        self.root.configure(bg=KEY)
        self.root.attributes("-transparentcolor", KEY)
        self.canvas = tk.Canvas(self.root, bg=KEY, highlightthickness=0, bd=0)
        self.canvas.pack(fill="both", expand=True)
        self.root.update_idletasks()
        self.hwnd = self._click_through(self.root)
        user32.ShowWindow(self.hwnd, 0)  # SW_HIDE
        self.shown = False
        self.geometry = None
        self.drawn = None

    @staticmethod
    def _click_through(win):
        win.update_idletasks()
        hwnd = user32.GetParent(win.winfo_id()) or win.winfo_id()
        GWL_EXSTYLE = -20
        style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        # layered + transparent (clicks pass through) + tool window (no taskbar) + never takes focus
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | 0x80000 | 0x20 | 0x80 | 0x8000000)
        return hwnd

    def update(self, state):
        """state: None (hide) or (x, y, w, h screen pixels, me, friends)."""
        # Shown, hidden and moved with Win32 calls that never activate it: WoW keeps the keyboard.
        if state is None:
            if self.shown:
                user32.ShowWindow(self.hwnd, 0)  # SW_HIDE
                self.shown = False
            return
        x, y, w, h, me, friends = state
        geo = (round(x), round(y), max(1, round(w)), max(1, round(h)))
        if geo != self.geometry or not self.shown:
            self.geometry = geo
            # HWND_TOPMOST; SWP_NOACTIVATE | SWP_SHOWWINDOW
            user32.SetWindowPos(self.hwnd, -1, geo[0], geo[1], geo[2], geo[3], 0x10 | 0x40)
            self.shown = True
        key = (round(w), round(h), repr(me), repr(friends))
        if key == self.drawn:
            return
        self.drawn = key
        c = self.canvas
        c.delete("all")
        for f in friends:
            self._dot(f, w, h)
        if me:
            self._marker(me, w, h, "#ffd24d", "You")

    def _label(self, x, y, text, colour, w):
        c = self.canvas
        size = -int(max(11, 13 * w / 1002))
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (1, 1), (-1, 1), (1, -1)):
            c.create_text(x + dx, y + dy, text=text, anchor="w", fill="#000001", font=("Segoe UI", size, "bold"))
        c.create_text(x, y, text=text, anchor="w", fill=colour, font=("Segoe UI", size, "bold"))

    def _dot(self, who, w, h):
        """A friend: their class colour, black ring, name, as the addon draws group members."""
        c = self.canvas
        d = max(9, 14 * w / 1002)
        cx, cy = who["u"] * w, who["v"] * h
        colour = who.get("color") or "#cccccc"
        if who.get("fresh") is False or who.get("guess"):
            colour = _dim(colour, 0.6)
        r = d / 2 + 2
        c.create_oval(cx - r, cy - r, cx + r, cy + r, fill="#000001", outline="")
        r = d / 2
        c.create_oval(cx - r, cy - r, cx + r, cy + r, fill=colour, outline="")
        self._label(cx + d / 2 + 5, cy, who["name"] + ("?" if who.get("guess") else ""), colour, w)

    def _marker(self, who, w, h, colour, label):
        """You: the arrow, pointing where you face."""
        c = self.canvas
        s = max(20, 26 * w / 1002) * (who.get("size") or 1)
        cx, cy = who["u"] * w, who["v"] * h
        if who.get("fresh") is False or who.get("guess"):
            colour = _dim(colour, 0.6)
        hd = who.get("heading")
        if hd is None:
            r = s * 0.35
            c.create_oval(cx - r, cy - r, cx + r, cy + r, fill=colour, outline="#000000", width=2)
        else:
            a = math.radians(hd)
            ca, sa = math.cos(a), math.sin(a)
            pts = []
            for px, py in ((0.0, -0.46), (0.38, 0.44), (0.0, 0.22), (-0.38, 0.44)):  # arrow, pointing up
                px, py = px * s, py * s
                pts += [cx + px * ca - py * sa, cy + px * sa + py * ca]
            c.create_polygon(pts, fill=colour, outline="#000000", width=max(2, s * 0.1), joinstyle="round")
        self._label(cx + s / 2 + 3, cy, label + ("?" if who.get("guess") else ""), colour, w)

    def notice(self, text, seconds=6):
        """A small note in the screen's corner for a few seconds (the tracker has no window of its own)."""
        tk = self.tk
        w = tk.Toplevel(self.root)
        w.overrideredirect(True)
        w.attributes("-topmost", True)
        w.configure(bg="#1d1f24")
        self._click_through(w)
        tk.Label(w, text=text, justify="left", bg="#1d1f24", fg="#f0e6c8", font=("Segoe UI", 11),
                 padx=16, pady=12).pack()
        w.update_idletasks()
        w.geometry("+%d+%d" % (w.winfo_screenwidth() - w.winfo_width() - 24,
                               w.winfo_screenheight() - w.winfo_height() - 72))
        w.after(int(seconds * 1000), w.destroy)

    def run(self, get_state, should_quit=lambda: False):
        def tick():
            if should_quit():
                self.root.destroy()
                return
            try:
                self.update(get_state())
            finally:
                self.root.after(4, tick)  # ~250 checks a second: hides the moment the map closes
        tick()
        self.root.mainloop()


# ------------------------------------------------------------------------------------------------
# The loop
# ------------------------------------------------------------------------------------------------

EXIT_AFTER_WOW = 3.0       # seconds after WoW closes before the tracker closes too
GIVE_UP_WAITING = 600.0    # seconds to wait for WoW to open at all


class WindowsTracker:
    def __init__(self, share=True):
        self.core = Core(share=Share(log=info) if share else None, info=info)
        self.cap = WindowCapture()
        self.state = None        # what the overlay shows (set by the worker, read by the overlay)
        self.win = None          # beacon in frames: (x, y, pitch)
        self.hwnd = None
        self.seen_wow = False
        self.quit = False

    def process(self, fr, now):
        b = None
        if self.win:
            x, y, pitch = self.win
            strip = fr.crop(0, 0, min(fr.w, int(x + beacon.CELLS * pitch + 8)), min(fr.h, int(y + pitch + 6)))
            if strip is not None:
                b = beacon.decode_at(strip, x, y, pitch)
        if b is None:
            top = fr.crop(0, 0, fr.w, min(fr.h, 160))
            b = beacon.find(top) if top is not None else None
            if b is None:
                self.win = None
                self.state = None
                return
            self.win = (b.x, b.y, b.pitch)
        if not b.fields["map_open"]:
            self.state = None  # first thing: the arrows go the instant the map does
        mm = b.rect("mm")
        if mm:
            self.cap.top = int(max(mm[1] + mm[3], b.y + 4)) + 8

        def full_crop(r):
            full, self.cap.full = self.cap.full, None
            return (full or fr).crop(*r)
        core = self.core
        core.frame(b, lambda r: fr.crop(*r), now, full_crop)
        if core.want_full:
            self.cap.want_full = True
        view = core.view(now)
        if view is None or not self.hwnd:
            self.state = None
            return
        ox, oy, minimized = frame_origin(self.hwnd)
        if minimized:
            self.state = None
            return
        x, y, w, h = view["canvas"]
        self.state = (ox + x, oy + y, w, h, view["me"], view["friends"])

    def worker(self):
        last = None
        started = time.monotonic()
        while True:
            if self.cap.finished():
                self.cap.stop()
                self.state = None
                self.hwnd = find_wow()
                if not self.hwnd:
                    if not self.seen_wow and time.monotonic() - started > GIVE_UP_WAITING:
                        info("WoW didn't open: tracker closing")
                        self.quit = True
                        return
                    if self.seen_wow:
                        gone = time.monotonic()
                        while not find_wow() and time.monotonic() - gone < EXIT_AFTER_WOW:
                            time.sleep(0.5)
                        if not find_wow():
                            info("WoW closed: tracker closing")
                            self.quit = True
                            return
                    time.sleep(2)
                    continue
                self.seen_wow = True
                try:
                    self.cap.start(self.hwnd)
                    info("capturing World of Warcraft")
                except Exception as e:
                    info("can't capture the WoW window (%s); retrying" % e)
                    time.sleep(5)
                    continue
            if not self.cap.new.wait(0.5):
                continue
            self.cap.new.clear()
            fr = self.cap.frame
            if fr is None or fr.serial == last:
                continue
            last = fr.serial
            try:
                self.process(fr, time.monotonic())
            except Exception as e:  # keep going: one bad frame must not end the tracker
                info("frame skipped: %r" % e)

    def run(self):
        threading.Thread(target=self.worker, daemon=True).start()
        ov = Overlay()
        ov.notice("Dungeon Maps tracker is running.\nOpen the dungeon map in WoW (your map key) to see the arrows.\n"
                  "It closes by itself when WoW closes.")
        ov.run(lambda: self.state, lambda: self.quit)


def single_instance():
    """True if no other copy is running (a named mutex, held until this process ends)."""
    single_instance.handle = ctypes.windll.kernel32.CreateMutexW(None, False, "Local\\DungeonMapsTracker")
    return ctypes.windll.kernel32.GetLastError() != 183  # ERROR_ALREADY_EXISTS


def main():
    if not single_instance():
        return
    info("Dungeon Maps tracker started")
    WindowsTracker(share="--no-share" not in sys.argv).run()
