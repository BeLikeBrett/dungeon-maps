r"""Windows: WoW's window through Windows Graphics Capture, a native layered overlay.

  * Capture: the windows-capture package (Windows Graphics Capture) on the "World of Warcraft" window:
    keeps working while the game is covered (not while minimized). No picker, nothing to set up.
  * Placement: Windows says where the window is (DWM frame bounds), so the overlay sits exactly over
    the dungeon map; checked every frame.
  * Overlay: a borderless, always-on-top, click-through native window over the map canvas with
    per-pixel transparency. WoW must run windowed or "windowed fullscreen" (exclusive fullscreen
    hides overlays).

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

from . import __version__, beacon
from . import telemetry as tele
from .core import Core
from .data import user_dir
from .share import Share

WOW_TITLE = "World of Warcraft"
MAX_FPS = 60
LOG_FILE = os.path.join(user_dir("state"), "tracker.log")


def info(*a):
    tele.telemetry.record(" ".join(str(x) for x in a))
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
    # ctypes otherwise assumes a 32-bit int, truncating HWNDs/handles on 64-bit Windows.
    user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
    user32.FindWindowW.restype = wintypes.HWND
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetParent.argtypes = [wintypes.HWND]
    user32.GetParent.restype = wintypes.HWND
    user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.LONG]
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int,
                                  ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]
    for name in ("IsWindowVisible", "IsIconic"):
        getattr(user32, name).argtypes = [wintypes.HWND]
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    dwmapi.DwmGetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD,
                                           ctypes.c_void_p, wintypes.DWORD]
    ctypes.windll.kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    ctypes.windll.kernel32.CreateMutexW.restype = wintypes.HANDLE
    gdi32 = ctypes.windll.gdi32

    class BitmapInfoHeader(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("width", wintypes.LONG), ("height", wintypes.LONG),
                    ("planes", wintypes.WORD), ("bits", wintypes.WORD), ("compression", wintypes.DWORD),
                    ("image_size", wintypes.DWORD), ("xppm", wintypes.LONG), ("yppm", wintypes.LONG),
                    ("used", wintypes.DWORD), ("important", wintypes.DWORD)]

    class BlendFunction(ctypes.Structure):
        _fields_ = [("op", ctypes.c_ubyte), ("flags", ctypes.c_ubyte),
                    ("alpha", ctypes.c_ubyte), ("format", ctypes.c_ubyte)]

    user32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR,
                                     wintypes.DWORD, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                     ctypes.c_int, wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE,
                                     ctypes.c_void_p]
    user32.CreateWindowExW.restype = wintypes.HWND
    user32.DestroyWindow.argtypes = [wintypes.HWND]
    user32.UpdateLayeredWindow.argtypes = [wintypes.HWND, wintypes.HDC, ctypes.POINTER(wintypes.POINT),
        ctypes.POINTER(wintypes.SIZE), wintypes.HDC, ctypes.POINTER(wintypes.POINT), wintypes.DWORD,
        ctypes.POINTER(BlendFunction), wintypes.DWORD]
    user32.PeekMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND,
                                   wintypes.UINT, wintypes.UINT, wintypes.UINT]
    user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
    user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
    user32.DispatchMessageW.restype = ctypes.c_ssize_t
    gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
    gdi32.CreateCompatibleDC.restype = wintypes.HDC
    gdi32.CreateDIBSection.argtypes = [wintypes.HDC, ctypes.POINTER(BitmapInfoHeader), wintypes.UINT,
                                     ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE, wintypes.DWORD]
    gdi32.CreateDIBSection.restype = wintypes.HBITMAP
    gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HANDLE]
    gdi32.SelectObject.restype = wintypes.HANDLE
    gdi32.DeleteObject.argtypes = [wintypes.HANDLE]
    gdi32.DeleteDC.argtypes = [wintypes.HDC]
    WindowProc = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT,
                                   wintypes.WPARAM, wintypes.LPARAM)

    class WindowClass(ctypes.Structure):
        _fields_ = [("style", wintypes.UINT), ("proc", WindowProc), ("class_extra", ctypes.c_int),
                    ("window_extra", ctypes.c_int), ("instance", wintypes.HINSTANCE),
                    ("icon", wintypes.HICON), ("cursor", wintypes.HANDLE), ("background", wintypes.HANDLE),
                    ("menu", wintypes.LPCWSTR), ("name", wintypes.LPCWSTR)]

    class Guid(ctypes.Structure):
        _fields_ = [("a", wintypes.DWORD), ("b", wintypes.WORD), ("c", wintypes.WORD),
                    ("d", ctypes.c_ubyte * 8)]

    class NotifyIconData(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("hwnd", wintypes.HWND), ("id", wintypes.UINT),
                    ("flags", wintypes.UINT), ("message", wintypes.UINT), ("icon", wintypes.HICON),
                    ("tip", wintypes.WCHAR * 128), ("state", wintypes.DWORD), ("mask", wintypes.DWORD),
                    ("info", wintypes.WCHAR * 256), ("version", wintypes.UINT),
                    ("title", wintypes.WCHAR * 64), ("info_flags", wintypes.DWORD),
                    ("guid", Guid), ("balloon_icon", wintypes.HICON)]

    ctypes.windll.kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
    ctypes.windll.kernel32.GetModuleHandleW.restype = wintypes.HMODULE
    user32.RegisterClassW.argtypes = [ctypes.POINTER(WindowClass)]
    user32.UnregisterClassW.argtypes = [wintypes.LPCWSTR, wintypes.HINSTANCE]
    user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.DefWindowProcW.restype = ctypes.c_ssize_t
    user32.LoadImageW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT,
                                  ctypes.c_int, ctypes.c_int, wintypes.UINT]
    user32.LoadImageW.restype = wintypes.HANDLE
    user32.LoadIconW.argtypes = [wintypes.HINSTANCE, ctypes.c_void_p]
    user32.LoadIconW.restype = wintypes.HICON
    user32.DestroyIcon.argtypes = [wintypes.HICON]
    user32.CreatePopupMenu.restype = wintypes.HMENU
    user32.AppendMenuW.argtypes = [wintypes.HMENU, wintypes.UINT, ctypes.c_size_t, wintypes.LPCWSTR]
    user32.TrackPopupMenu.argtypes = [wintypes.HMENU, wintypes.UINT, ctypes.c_int, ctypes.c_int,
                                     ctypes.c_int, wintypes.HWND, ctypes.c_void_p]
    user32.DestroyMenu.argtypes = [wintypes.HMENU]
    user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.RegisterWindowMessageW.argtypes = [wintypes.LPCWSTR]
    shell32 = ctypes.windll.shell32
    shell32.Shell_NotifyIconW.argtypes = [wintypes.DWORD, ctypes.POINTER(NotifyIconData)]
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
        build = sys.getwindowsversion().build
        # Passing an unsupported option makes windows-capture reject the entire session.
        # The callback below still limits processing to MAX_FPS on older Windows versions.
        cap = WindowsCapture(cursor_capture=False if build >= 19041 else None,
                             draw_border=False if build >= 20348 else None,
                             minimum_update_interval=1000 // MAX_FPS if build >= 26100 else None,
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


def window_rect(hwnd):
    """The window's DWM frame bounds on the screen (what window capture delivers), physical pixels."""
    r = wintypes.RECT()
    if dwmapi.DwmGetWindowAttribute(hwnd, 9, ctypes.byref(r), ctypes.sizeof(r)) != 0:
        user32.GetWindowRect(hwnd, ctypes.byref(r))
    return r.left, r.top, r.right, r.bottom


def monitors():
    """[(HMONITOR, (left, top, right, bottom))] in EnumDisplayMonitors order (windows-capture's
    monitor numbering, from 1)."""
    out = []
    proc_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC,
                                   ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)

    def found(handle, _dc, rect, _data):
        r = rect.contents
        out.append((handle, (r.left, r.top, r.right, r.bottom)))
        return True
    user32.EnumDisplayMonitors(None, None, proc_type(found), 0)
    return out


class ScreenCapture:
    """WoW's window cut out of its monitor's picture (DXGI desktop duplication, what screen
    recorders use): Windows draws no yellow border and asks no permission, but only sees the game
    while it is actually on screen, so frames are taken only while WoW is the foreground window.
    Used when Windows won't capture the window without its border (Windows 10 and older 11 builds,
    or the Screenshot borders permission off). Same interface as WindowCapture."""

    def __init__(self):
        self.frame = None
        self.full = None
        self.serial = 0
        self.top = 400
        self.want_full = False
        self.new = threading.Event()
        self.closed = False
        self.thread = None
        self.running = False

    def start(self, hwnd):
        # (a DXGI session belongs to the thread that made it: it is opened, used and dropped there)
        self.closed, self.running = False, True
        ready, result = threading.Event(), []
        self.thread = threading.Thread(target=self._run, args=(hwnd, ready, result), daemon=True)
        self.thread.start()
        if not ready.wait(10) or result[0] is not None:
            self.running = False
            raise RuntimeError(result[0] if result else "desktop duplication didn't start")

    @staticmethod
    def _open(hwnd):
        from windows_capture import DxgiDuplicationSession  # windows-capture 2.0.x
        user32.MonitorFromWindow.restype = wintypes.HMONITOR
        mon = user32.MonitorFromWindow(hwnd, 2)  # MONITOR_DEFAULTTONEAREST
        mons = monitors()
        order = [i for i, (h, _) in enumerate(mons) if h == mon] + list(range(len(mons)))
        for i in dict.fromkeys(order):   # the window's monitor first; check the numbering by size
            try:
                candidate = DxgiDuplicationSession(i + 1)
                fr = None
                until = time.monotonic() + 0.5
                while fr is None and time.monotonic() < until:
                    fr = candidate.acquire_frame(50)
            except BaseException as e:   # (the native side can raise PanicException, a BaseException)
                if isinstance(e, (KeyboardInterrupt, SystemExit)):
                    raise
                info("desktop duplication on monitor %d unavailable: %r" % (i + 1, e))
                continue
            l, t, r, b = mons[i][1]
            if fr is None or (fr.width, fr.height) == (r - l, b - t):
                return candidate, mons[i][1]
        return None, None

    def _run(self, hwnd, ready, result):
        try:
            session, mon = self._open(hwnd)
        except BaseException as e:
            session, mon = None, repr(e)
        result.append(None if session else (mon or "desktop duplication unavailable"))
        ready.set()
        if session is None:
            self.closed = True
            return
        errors, last = 0, 0.0
        while self.running:
            if user32.GetForegroundWindow() != hwnd or user32.IsIconic(hwnd):
                time.sleep(0.05)   # covered or minimized: the screen doesn't show the game
                continue
            try:
                fr = session.acquire_frame(20)
            except BaseException as e:  # mode change, UAC prompt, display sleep: start over
                if isinstance(e, (KeyboardInterrupt, SystemExit)):
                    raise
                errors += 1
                info("desktop duplication lost (%r)" % e)
                if errors > 20:
                    break
                time.sleep(0.5)
                try:
                    session.recreate()
                except BaseException as e:
                    if isinstance(e, (KeyboardInterrupt, SystemExit)):
                        raise
                continue
            errors = 0
            if fr is None:
                continue          # nothing on screen changed
            now = time.monotonic()
            if now - last < 1 / MAX_FPS and not self.want_full:
                continue
            last = now
            l, t, r, b = window_rect(hwnd)
            ox, oy, w, h = l - mon[0], t - mon[1], r - l, b - t
            x0, y0 = max(0, ox), max(0, oy)
            x1, y1 = min(fr.width, ox + w), min(fr.height, oy + h)
            if x1 - x0 < 64 or y1 - y0 < 64 or (x0, y0) != (ox, oy):
                continue          # the window's top-left is off this monitor
            full = self.want_full
            self.want_full = False
            n = (y1 - y0) if full else min(y1 - y0, self.top)
            bpp = fr.bytes_per_pixel
            raw = fr._raw_buffer()[y0:y0 + n, x0 * bpp:x1 * bpp]
            if fr.color_format == "rgba16f":
                px = raw.copy().view(np.float16).reshape(n, x1 - x0, 4)
                px = (np.clip(px.astype(np.float32), 0, 1) * 255).astype(np.uint8)[..., [2, 1, 0, 3]]
            else:
                px = np.array(raw).reshape(n, x1 - x0, 4)
                if fr.color_format == "rgba8":
                    px = px[..., [2, 1, 0, 3]]
            self.serial += 1
            self.frame = Frame(px, x1 - x0, y1 - y0, self.serial)
            if full:
                self.full = self.frame
            self.new.set()
        self.closed = True
        self.new.set()

    def finished(self):
        return self.thread is None or self.closed or not self.thread.is_alive()

    def stop(self):
        self.running = False
        if self.thread is not None and self.thread is not threading.current_thread():
            self.thread.join(timeout=1)
        self.thread = None
        self.frame = None


# ------------------------------------------------------------------------------------------------
# Overlay
# ------------------------------------------------------------------------------------------------

def _dim(hex_colour, k):
    """Blend towards black for stale or uncertain markers."""
    r, g, b = (int(hex_colour[i:i + 2], 16) for i in (1, 3, 5))
    return "#%02x%02x%02x" % (int(r * k), int(g * k), int(b * k))


class LayeredWindow:
    """Native display-only surface. No toolkit ever gets an opportunity to activate it."""

    def __init__(self, exclude_from_capture=False):
        # WS_EX_LAYERED | TRANSPARENT | TOOLWINDOW | NOACTIVATE; WS_POPUP, initially hidden.
        self.hwnd = user32.CreateWindowExW(0x80800a0, "STATIC", "Dungeon Maps", 0x80000000,
                                           0, 0, 1, 1, None, None, None, None)
        if not self.hwnd:
            raise ctypes.WinError()
        if exclude_from_capture:
            # WDA_EXCLUDEFROMCAPTURE (Windows 10 2004+): when the tracker reads the screen it must
            # never read back its own drawings (only then: streams and recordings still show them)
            user32.SetWindowDisplayAffinity(self.hwnd, 0x11)

    def present(self, image, x, y):
        # UpdateLayeredWindow expects a top-down BGRA DIB with premultiplied alpha.
        w, h = image.size
        pixels = np.array(image, dtype=np.uint8)
        alpha = pixels[:, :, 3:4].astype(np.uint16)
        pixels[:, :, :3] = (pixels[:, :, :3].astype(np.uint16) * alpha // 255).astype(np.uint8)
        raw = pixels[:, :, [2, 1, 0, 3]].tobytes()
        header = BitmapInfoHeader(40, w, -h, 1, 32, 0, len(raw), 0, 0, 0, 0)
        dc = gdi32.CreateCompatibleDC(None)
        bits = ctypes.c_void_p()
        bitmap = gdi32.CreateDIBSection(dc, ctypes.byref(header), 0, ctypes.byref(bits), None, 0)
        if not dc or not bitmap:
            if dc:
                gdi32.DeleteDC(dc)
            raise ctypes.WinError()
        old = gdi32.SelectObject(dc, bitmap)
        try:
            ctypes.memmove(bits, raw, len(raw))
            point, size, source = wintypes.POINT(round(x), round(y)), wintypes.SIZE(w, h), wintypes.POINT(0, 0)
            blend = BlendFunction(0, 0, 255, 1)  # AC_SRC_OVER, AC_SRC_ALPHA
            if not user32.UpdateLayeredWindow(self.hwnd, None, ctypes.byref(point), ctypes.byref(size),
                                            dc, ctypes.byref(source), 0, ctypes.byref(blend), 2):
                raise ctypes.WinError()
            user32.SetWindowPos(self.hwnd, -1, 0, 0, 0, 0, 0x1 | 0x2 | 0x10 | 0x40)
        finally:
            gdi32.SelectObject(dc, old)
            gdi32.DeleteObject(bitmap)
            gdi32.DeleteDC(dc)

    def close(self):
        if self.hwnd:
            user32.DestroyWindow(self.hwnd)
            self.hwnd = None

    def move(self, x, y):
        # Reuse the layered bitmap during map drags; no DIB allocation or full
        # RGBA conversion/upload when only the map's origin changed.
        if not user32.SetWindowPos(self.hwnd, -1, round(x), round(y), 0, 0, 0x1 | 0x10 | 0x40):
            raise ctypes.WinError()


class Tray:
    """A silent tray icon; the menu is opened only by the user's right-click."""

    CLASS = "DungeonMapsTray"
    MESSAGE = 0x8001
    CLOSE = 1

    def __init__(self, on_close):
        self.on_close = on_close
        self.taskbar_created = user32.RegisterWindowMessageW("TaskbarCreated")
        self.callback = WindowProc(self._message)
        self.instance = ctypes.windll.kernel32.GetModuleHandleW(None)
        self.window_class = WindowClass(name=self.CLASS, proc=self.callback, instance=self.instance)
        if not user32.RegisterClassW(ctypes.byref(self.window_class)):
            raise ctypes.WinError()
        self.hwnd = user32.CreateWindowExW(0x8000080, self.CLASS, "Dungeon Maps tracker", 0,
                                          0, 0, 0, 0, None, None, self.instance, None)
        if not self.hwnd:
            user32.UnregisterClassW(self.CLASS, self.instance)
            raise ctypes.WinError()
        here = os.path.dirname(__file__)
        path = os.path.join(here, "icon.ico")
        if not os.path.exists(path):
            path = os.path.join(here, "..", "packaging", "icon.ico")
        self.icon = user32.LoadImageW(None, path, 1, 32, 32, 0x10)
        self.owns_icon = bool(self.icon)
        self.icon = self.icon or user32.LoadIconW(None, 32512)
        self.data = NotifyIconData(size=ctypes.sizeof(NotifyIconData), hwnd=self.hwnd, id=1,
                                   flags=7, message=self.MESSAGE, icon=self.icon, tip="Dungeon Maps")
        if not shell32.Shell_NotifyIconW(0, ctypes.byref(self.data)):
            self.close()
            raise ctypes.WinError()
        info("tray icon ready")

    def _message(self, hwnd, message, wparam, lparam):
        # Our own window procedure, never attached to the game or another process.
        if message == self.MESSAGE and lparam in (0x205, 0x7b):  # right button up / context menu
            menu = user32.CreatePopupMenu()
            user32.AppendMenuW(menu, 0, self.CLOSE, "Close")
            point = wintypes.POINT()
            user32.GetCursorPos(ctypes.byref(point))
            # Windows requires foreground ownership to dismiss a tray menu correctly. This is
            # exclusively in direct response to the user's right-click, never during startup.
            user32.SetForegroundWindow(hwnd)
            command = user32.TrackPopupMenu(menu, 0x100 | 0x2, point.x, point.y, 0, hwnd, None)
            user32.PostMessageW(hwnd, 0, 0, 0)
            user32.DestroyMenu(menu)
            if command == self.CLOSE:
                self.on_close()
            return 0
        if message == 0x111 and wparam & 0xffff == self.CLOSE:  # WM_COMMAND
            self.on_close()
            return 0
        if message == self.taskbar_created and hasattr(self, "data"):
            shell32.Shell_NotifyIconW(0, ctypes.byref(self.data))
            return 0
        return user32.DefWindowProcW(hwnd, message, wparam, lparam)

    def notify(self, title, text):
        """A quiet tray notification (never takes focus)."""
        self.data.flags = 0x10  # NIF_INFO
        self.data.title = title[:63]
        self.data.info = text[:255]
        self.data.info_flags = 0x1 | 0x10  # NIIF_INFO | NIIF_NOSOUND
        shell32.Shell_NotifyIconW(1, ctypes.byref(self.data))  # NIM_MODIFY
        self.data.flags = 7

    def close(self):
        if self.hwnd:
            shell32.Shell_NotifyIconW(2, ctypes.byref(self.data))
            user32.DestroyWindow(self.hwnd)
            self.hwnd = None
            user32.UnregisterClassW(self.CLASS, self.instance)
        if self.owns_icon:
            user32.DestroyIcon(self.icon)
            self.owns_icon = False


class Overlay:
    """A click-through, never-activating Windows overlay. Runs on the main thread."""

    def __init__(self, exclude_from_capture=False):
        self.surface = LayeredWindow(exclude_from_capture)
        self.hwnd = self.surface.hwnd
        self.shown = False
        self.geometry = None
        self.drawn = None
        self.image = None
        self.notices = []
        self.fonts = {}

    def font(self, size):
        from PIL import ImageFont
        if size not in self.fonts:
            path = os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts", "segoeuib.ttf")
            try:
                self.fonts[size] = ImageFont.truetype(path, size)
            except OSError:
                self.fonts[size] = ImageFont.load_default(size=size)
        return self.fonts[size]

    def update(self, state):
        """state: None (hide) or (x, y, w, h physical screen pixels, me, friends)."""
        if state is None:
            if self.shown:
                user32.ShowWindow(self.hwnd, 0)
                self.shown = False
            return
        from PIL import Image, ImageDraw
        x, y, w, h, me, friends = state
        geo = (round(x), round(y), max(1, round(w)), max(1, round(h)))
        key = (geo[2:], repr(me), repr(friends))
        if key != self.drawn:
            self.image = Image.new("RGBA", geo[2:], (0, 0, 0, 0))
            self.draw = ImageDraw.Draw(self.image)
            for friend in friends:
                self._dot(friend, w, h)
            if me:
                self._marker(me, w, h, "#ffd24d", "You")
        if key != self.drawn or not self.shown:
            self.surface.present(self.image, geo[0], geo[1])
            self.geometry, self.drawn, self.shown = geo, key, True
        elif geo != self.geometry:
            self.surface.move(geo[0], geo[1])
            self.geometry = geo

    def _label(self, x, y, text, colour, w):
        size = int(max(11, 13 * w / 1002))
        self.draw.text((x, y), text, anchor="lm", fill=colour, font=self.font(size),
                       stroke_width=1, stroke_fill="#000000")

    def _dot(self, who, w, h):
        """A friend: class-coloured dot (black ring, light rim) and a name tag on the side away from
        your arrow, as laid out by core.py (the Linux overlay draws the same)."""
        k = who.get("size") or 1.0   # (the addon's "Teammate dots" setting)
        d = max(10, 13 * w / 1002) * k
        cx, cy = who["u"] * w, who["v"] * h
        colour = who.get("color") or "#cccccc"
        if who.get("fresh") is False or who.get("guess"):
            colour = _dim(colour, 0.6)
        for r, fill in ((d / 2 + 3, (255, 255, 255, 232)), (d / 2 + 1.5, "#000000"), (d / 2, colour)):
            self.draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=fill)
        text = who["name"] + ("?" if who.get("guess") else "")
        font = self.font(int(max(11, 12 * w / 1002) * max(0.85, min(1.6, k))))
        l, t, r, b = self.draw.textbbox((0, 0), text, font=font)
        tw, th = r - l + 10, b - t + 4
        ty = cy + d / 2 + 5 if who.get("label") == "below" else cy - d / 2 - 5 - th
        self.draw.rounded_rectangle((cx - tw / 2, ty, cx + tw / 2, ty + th), radius=th / 2,
                                    fill=(16, 16, 16, 179))
        self.draw.text((cx, ty + th / 2), text, anchor="mm", fill=colour, font=font)

    def _marker(self, who, w, h, colour, label):
        s = max(20, 26 * w / 1002) * (who.get("size") or 1)
        cx, cy = who["u"] * w, who["v"] * h
        if who.get("fresh") is False:
            colour = _dim(colour, 0.6)
        hd = who.get("heading")
        if hd is None:
            r = s * 0.35
            self.draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=colour, outline="#000000", width=2)
        else:
            a = math.radians(hd)
            ca, sa = math.cos(a), math.sin(a)
            pts = []
            for px, py in ((0.0, -0.46), (0.38, 0.44), (0.0, 0.22), (-0.38, 0.44)):
                px, py = px * s, py * s
                pts.append((cx + px * ca - py * sa, cy + px * sa + py * ca))
            self.draw.polygon(pts, fill=colour)
            self.draw.line(pts + pts[:1], fill="#000000", width=max(2, round(s * 0.1)), joint="curve")
        if who.get("guess"):  # (no "You" label: the gold arrow is you)
            self._label(cx + s / 2 + 2, cy, "?", colour, w)

    def notice(self, text, seconds=6):
        from PIL import Image, ImageDraw
        font = self.font(14)
        box = ImageDraw.Draw(Image.new("RGBA", (1, 1))).multiline_textbbox((0, 0), text, font=font)
        image = Image.new("RGBA", (box[2] - box[0] + 32, box[3] - box[1] + 24), "#1d1f24")
        ImageDraw.Draw(image).multiline_text((16 - box[0], 12 - box[1]), text, font=font, fill="#f0e6c8")
        surface = LayeredWindow()
        surface.present(image, user32.GetSystemMetrics(0) - image.width - 24,
                        user32.GetSystemMetrics(1) - image.height - 72)
        self.notices.append((time.monotonic() + seconds, surface))

    def pump(self):
        msg = wintypes.MSG()
        while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        for deadline, surface in self.notices[:]:
            if time.monotonic() >= deadline:
                surface.close()
                self.notices.remove((deadline, surface))

    def close(self):
        for _, surface in self.notices:
            surface.close()
        self.notices.clear()
        self.surface.close()

    def run(self, get_state, should_quit=lambda: False):
        try:
            while not should_quit():
                self.update(get_state())
                self.pump()
                time.sleep(0.004)
        finally:
            self.close()


# ------------------------------------------------------------------------------------------------
# The loop
# ------------------------------------------------------------------------------------------------

EXIT_AFTER_WOW = 3.0       # seconds after WoW closes before the tracker closes too
GIVE_UP_WAITING = 600.0    # seconds to wait for WoW to open at all


class WindowsTracker:
    def __init__(self, share=True, borderless=True, release=None, note=None):
        self.core = Core(share=Share(log=info) if share else None, info=info)
        # Window capture keeps tracking while WoW is covered, but Windows draws a yellow border
        # around the game unless it allows borderless capture; then the screen is read instead.
        mode = os.environ.get("DUNGEONMAPS_CAPTURE") or ("window" if borderless else "screen")
        self.cap = ScreenCapture() if mode == "screen" else WindowCapture()
        self.capture_failures = 0
        info("capture mode:", "screen (no border)" if mode == "screen" else "window")
        self.release, self.note = release, note   # (update.py: the latest release; a note to show)
        self.wow_exe = None
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
        gone_at = None
        retry_at = 0.0
        while not self.quit:
            now = time.monotonic()
            hwnd = find_wow()
            if not hwnd:
                self.state = None
                if self.hwnd:
                    self.cap.stop()
                    self.hwnd = None
                if not self.seen_wow and now - started >= GIVE_UP_WAITING:
                    info("WoW didn't open: tracker closing")
                    self.quit = True
                    return
                if self.seen_wow:
                    if gone_at is None:
                        gone_at = now
                    if now - gone_at >= EXIT_AFTER_WOW:
                        info("WoW closed: tracker closing")
                        self.quit = True
                        return
                time.sleep(0.1)
                continue
            gone_at = None
            self.seen_wow = True
            if self.wow_exe is None:
                self.found_wow_exe(hwnd)
            if hwnd != self.hwnd:
                self.cap.stop()
                self.state = None
                self.hwnd = hwnd
                retry_at = 0.0
            if self.cap.finished():
                self.state = None
                if now < retry_at:
                    time.sleep(0.1)
                    continue
                self.cap.stop()
                try:
                    self.cap.start(self.hwnd)
                    self.capture_failures = 0
                    info("capturing World of Warcraft")
                except Exception as e:
                    info("can't capture the WoW window (%s); retrying" % e)
                    self.capture_failures += 1
                    if isinstance(self.cap, ScreenCapture) and self.capture_failures >= 3:
                        info("screen capture keeps failing: using window capture (Windows may show a border)")
                        self.cap = WindowCapture()
                    retry_at = time.monotonic() + 5
                    continue
            if not self.cap.new.wait(0.1):
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

    def found_wow_exe(self, hwnd):
        """Where WoW: Forever is installed (from its process): remembered for the add-on updates, and
        the add-on there is brought up to date now if the start-up check didn't know this folder."""
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        h = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid.value)  # QUERY_LIMITED_INFORMATION
        self.wow_exe = ""
        if not h:
            return
        try:
            buf, n = ctypes.create_unicode_buffer(1024), wintypes.DWORD(1024)
            if ctypes.windll.kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n)):
                self.wow_exe = buf.value
        finally:
            ctypes.windll.kernel32.CloseHandle(h)
        if not self.wow_exe:
            return
        from . import update
        d = update.remember_addons_dir(self.wow_exe)
        have = update.addon_version(d)
        if self.release and (have is None or have < self.release["version"]):
            def work():
                note = update.update_addon(self.release, info, [d])
                if note:
                    self.note = note
            threading.Thread(target=work, daemon=True).start()

    def overlay_state(self):
        # Keep reading WGC frames while covered, but never draw the map arrow over another app.
        if not self.hwnd or user32.GetForegroundWindow() != self.hwnd or user32.IsIconic(self.hwnd):
            return None
        return self.state

    def run(self):
        ov = Overlay(exclude_from_capture=isinstance(self.cap, ScreenCapture))
        tray = Tray(lambda: setattr(self, "quit", True))
        self.tray = tray
        worker = threading.Thread(target=self.worker, daemon=True)
        worker.start()
        try:
            def tick():
                if self.note:
                    note, self.note = self.note, None
                    tray.notify("Dungeon Maps", note)
                return self.quit
            ov.run(self.overlay_state, tick)
        finally:
            self.quit = True
            worker.join(timeout=1)
            self.cap.stop()
            tray.close()


def single_instance():
    """True if no other copy is running (a named mutex, held until this process ends)."""
    single_instance.handle = ctypes.windll.kernel32.CreateMutexW(None, False, "Local\\DungeonMapsTracker")
    return ctypes.windll.kernel32.GetLastError() != 183  # ERROR_ALREADY_EXISTS


def start_telemetry(tracker):
    """Logs and a stats line a minute to the relay (see telemetry.py); off with DUNGEONMAPS_LOGS=off."""
    t = tele.setup()
    t.name = lambda: tracker.core.name
    t.stats = lambda: tracker.core.stats({"capture": "screen" if isinstance(tracker.cap, ScreenCapture) else "window"})
    t.start()
    return t


def main():
    from . import update
    update.wait_for_previous()   # (just updated: the old copy still holds the single-instance lock)
    if not single_instance():
        return
    exit_now, note = update.run(info)
    if exit_now:
        return                   # the new version is starting
    release = update.last_release
    from .windows_permissions import ask_capture, request_borderless
    if not ask_capture(info):
        return
    borderless = request_borderless(info)
    tracker = WindowsTracker(share="--no-share" not in sys.argv, borderless=borderless, release=release, note=note)
    t = start_telemetry(tracker)
    info("Dungeon Maps tracker started (v%s, %s)" % (__version__, tele.system()))
    try:
        tracker.run()
    finally:
        info("tracker stopped")
        t.flush(timeout=3)
