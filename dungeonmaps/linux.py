"""Linux: WoW's window through the screencast portal, the overlay (Quickshell) fed JSON lines.

  * Capture: xdg-desktop-portal ScreenCast of WoW's window (PipeWire -> GStreamer), so tracking goes
    on while the game is covered or on another workspace. A picker asks for the window when WoW is
    open (pick "World of Warcraft"). Without the portal: grim screenshots (wlroots compositors).
  * Placement: where the window is on the screen comes from finding the beacon in a small grim
    screenshot (compositors don't tell clients where windows are), checked every 0.4 s in a thread,
    only while the dungeon map is open.
  * Window and monitor lookups: niri, Hyprland or Sway IPC (any other compositor: all screens searched).

    python3 -m dungeonmaps            # normally started by the overlay: qs -p overlay
    python3 -m dungeonmaps --debug    # also log what it sees
"""

import json
import os
import shutil
import subprocess
import sys
import threading
import time

import numpy as np

from . import beacon
from .core import Core
from .data import user_dir
from .share import Share

SCREEN_FRAME = 1 / 30         # screenshot mode: seconds between frames
SEARCH_EVERY = 1.0            # seconds between screen searches for the beacon (to place the overlay)
PLACE_CHECK_EVERY = 0.4       # seconds between checks that the game didn't move on the screen
MAX_FPS = 60                  # frames a second taken from the window stream
TOKEN_FILE = os.path.join(user_dir("state"), "portal.json")
LOG_FILE = os.path.join(user_dir("state"), "tracker.log")
DEBUG = "--debug" in sys.argv


def info(*a):
    print(*a, file=sys.stderr, flush=True)
    try:  # also kept in a file (the overlay swallows stderr into its own log)
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        with open(LOG_FILE, "a") as fh:
            fh.write(time.strftime("%H:%M:%S ") + " ".join(str(x) for x in a) + "\n")
    except OSError:
        pass


def log(*a):
    if DEBUG:
        info(*a)


# ------------------------------------------------------------------------------------------------
# Compositor: monitors and the WoW window (niri, Hyprland, Sway)
# ------------------------------------------------------------------------------------------------

def _run_json(cmd):
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=3)
        return json.loads(r.stdout) if r.returncode == 0 else None
    except Exception:
        return None


def _compositor():
    if os.environ.get("NIRI_SOCKET") and shutil.which("niri"):
        return "niri"
    if os.environ.get("HYPRLAND_INSTANCE_SIGNATURE") and shutil.which("hyprctl"):
        return "hyprland"
    if os.environ.get("SWAYSOCK") and shutil.which("swaymsg"):
        return "sway"
    return None


COMPOSITOR = _compositor()


def _is_wow(title, app):
    title, app = (title or "").lower(), (app or "").lower()
    return "world of warcraft" in title or app.startswith("wow")


def outputs():
    """[{name, x, y, w, h, scale}] in global logical coordinates."""
    res = []
    if COMPOSITOR == "niri":
        for name, o in (_run_json(["niri", "msg", "-j", "outputs"]) or {}).items():
            lg = o.get("logical")
            if lg:
                res.append({"name": name, "x": lg["x"], "y": lg["y"], "w": lg["width"], "h": lg["height"],
                            "scale": lg["scale"]})
    elif COMPOSITOR == "hyprland":
        for m in _run_json(["hyprctl", "-j", "monitors"]) or []:
            s = m.get("scale", 1) or 1
            res.append({"name": m["name"], "x": m["x"], "y": m["y"], "w": m["width"] / s, "h": m["height"] / s,
                        "scale": s})
    elif COMPOSITOR == "sway":
        for o in _run_json(["swaymsg", "-t", "get_outputs", "-r"]) or []:
            if o.get("active"):
                r = o["rect"]
                res.append({"name": o["name"], "x": r["x"], "y": r["y"], "w": r["width"], "h": r["height"],
                            "scale": o.get("scale", 1)})
    return res


def wow_windows():
    """(open at all, [names of outputs where it is visible]) — None for 'can't tell' on other compositors."""
    if COMPOSITOR == "niri":
        wins = _run_json(["niri", "msg", "-j", "windows"]) or []
        spaces = _run_json(["niri", "msg", "-j", "workspaces"]) or []
        active = {w["id"]: w.get("output") for w in spaces if w.get("is_active")}
        mine = [w for w in wins if _is_wow(w.get("title"), w.get("app_id"))]
        return bool(mine), [active[w["workspace_id"]] for w in mine if w.get("workspace_id") in active]
    if COMPOSITOR == "hyprland":
        mons = _run_json(["hyprctl", "-j", "monitors"]) or []
        shown = {m["activeWorkspace"]["id"]: m["name"] for m in mons}
        mine = [c for c in _run_json(["hyprctl", "-j", "clients"]) or [] if _is_wow(c.get("title"), c.get("class"))]
        return bool(mine), [shown[c["workspace"]["id"]] for c in mine if c["workspace"]["id"] in shown]
    if COMPOSITOR == "sway":
        found = []

        def walk(node, output, visible):
            if node.get("type") == "output":
                output = node.get("name")
            if node.get("type") == "workspace":
                visible = node.get("visible", False)
            if _is_wow(node.get("name"), node.get("app_id")):
                found.append(output if visible else None)
            for k in ("nodes", "floating_nodes"):
                for c in node.get(k, []):
                    walk(c, output, visible)
        walk(_run_json(["swaymsg", "-t", "get_tree", "-r"]) or {}, None, False)
        return bool(found), [o for o in found if o]
    return None


def wow_running():
    w = wow_windows()
    return True if w is None else w[0]


# ------------------------------------------------------------------------------------------------
# Screenshots (grim)
# ------------------------------------------------------------------------------------------------

def parse_ppm(buf):
    parts, pos = [], 0
    while len(parts) < 4:
        while buf[pos:pos + 1].isspace():
            pos += 1
        if buf[pos:pos + 1] == b"#":
            pos = buf.index(b"\n", pos) + 1
            continue
        end = pos
        while not buf[end:end + 1].isspace():
            end += 1
        parts.append(buf[pos:end])
        pos = end
    w, h = int(parts[1]), int(parts[2])
    return np.frombuffer(buf, np.uint8, w * h * 3, pos + 1).reshape(h, w, 3)


def grab(output=None, region=None):
    """Screenshot of an output, or of a region in global logical coordinates. RGB uint8 or None."""
    cmd = ["grim", "-t", "ppm"]
    if output:
        cmd += ["-o", output]
    if region:
        x, y, w, h = region
        cmd += ["-g", "%d,%d %dx%d" % (round(x), round(y), max(1, round(w)), max(1, round(h)))]
    cmd.append("-")
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=3)
    except Exception:
        return None
    return parse_ppm(r.stdout) if r.returncode == 0 and r.stdout else None


def find_on_screen():
    """Screenshot the outputs WoW is on and look for the beacon: (output, Beacon) or (None, None)."""
    w = wow_windows()
    outs = outputs()
    names = [o["name"] for o in outs] if w is None else w[1]
    for out in outs:
        if out["name"] in names:
            img = grab(output=out["name"])
            b = beacon.find(img) if img is not None else None
            if b:
                return out, b
    return None, None


# ------------------------------------------------------------------------------------------------
# The screencast portal
# ------------------------------------------------------------------------------------------------

class Frame:
    """A frame of the window: the rows copied out of it (the top band, or all of it when asked)."""

    def __init__(self, rows, w, h, order, serial):
        self.rows, self.w, self.h, self.order, self.serial = rows, w, h, order, serial

    def crop(self, x, y, w, h):
        """RGB copy of a rectangle in window pixels, or None outside the rows that were copied."""
        x0, y0 = max(0, int(round(x))), max(0, int(round(y)))
        x1, y1 = min(self.w, int(round(x + w))), min(self.rows.shape[0], int(round(y + h)))
        if x1 <= x0 or y1 <= y0:
            return None
        return np.ascontiguousarray(self.rows[y0:y1, x0:x1][..., self.order])


class PortalWindow:
    """WoW's window as a stream. start() asks (in a thread: the picker can take a while)."""

    ORDERS = {"BGRx": [2, 1, 0], "BGRA": [2, 1, 0], "RGBx": [0, 1, 2], "RGBA": [0, 1, 2],
              "xRGB": [1, 2, 3], "ARGB": [1, 2, 3], "xBGR": [3, 2, 1], "ABGR": [3, 2, 1]}

    def __init__(self):
        self.state = "idle"        # idle -> starting -> asking -> running | failed
        self.frame = None
        self.full = None           # the whole frame asked for with want_full
        self.serial = 0
        self.pipeline = None
        self.bus = None
        self.session = None
        self.remote_fd = None
        self.top = 400             # rows copied from each frame (set to the minimap's bottom)
        self.want_full = False
        self.failures = 0
        self.new = threading.Event()

    def _request(self, bus, method, sig, args, token, timeout):
        from gi.repository import Gio, GLib
        sender = bus.get_unique_name()[1:].replace(".", "_")
        path = "/org/freedesktop/portal/desktop/request/%s/%s" % (sender, token)
        result = {}

        def on_response(_c, _s, _p, _i, _sig, params, *_):
            result["code"], result["res"] = params.unpack()

        sid = bus.signal_subscribe("org.freedesktop.portal.Desktop", "org.freedesktop.portal.Request",
                                   "Response", path, None, Gio.DBusSignalFlags.NONE, on_response)
        try:
            bus.call_sync("org.freedesktop.portal.Desktop", "/org/freedesktop/portal/desktop",
                          "org.freedesktop.portal.ScreenCast", method, GLib.Variant(sig, args),
                          None, Gio.DBusCallFlags.NONE, -1, None)
            ctx, end = GLib.MainContext.default(), time.monotonic() + timeout
            while "code" not in result and time.monotonic() < end:
                ctx.iteration(False)
                time.sleep(0.02)
        finally:
            bus.signal_unsubscribe(sid)
        if result.get("code") != 0:
            raise RuntimeError("%s: %s" % (method, "cancelled" if "code" in result else "no answer"))
        return result["res"]

    def _setup(self):
        # GStreamer's default GL (Wayland EGL on radeonsi) crashes with a bus error when downloaded
        # frames are read (mesa 26.3 / gst 1.28, 2026-11); surfaceless EGL on zink works and is fastest
        for k, v in (("GST_GL_WINDOW", "surfaceless"), ("GST_GL_PLATFORM", "egl"),
                     ("MESA_LOADER_DRIVER_OVERRIDE", "zink")):
            os.environ.setdefault(k, v)
        import gi
        gi.require_version("Gst", "1.0")
        gi.require_version("GstVideo", "1.0")
        from gi.repository import Gio, GLib, Gst
        Gst.init(None)
        self.Gst = Gst
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        self.bus = bus  # keep the session's owning connection alive after the setup thread returns
        n = [0]

        def tok():
            n[0] += 1
            return "dm%d_%d" % (os.getpid(), n[0])

        V = GLib.Variant
        t = tok()
        session = self._request(bus, "CreateSession", "(a{sv})",
                                ({"handle_token": V("s", t), "session_handle_token": V("s", tok())},), t, 10)["session_handle"]
        self.session = session
        modes = bus.call_sync("org.freedesktop.portal.Desktop", "/org/freedesktop/portal/desktop",
                              "org.freedesktop.DBus.Properties", "Get",
                              V("(ss)", ("org.freedesktop.portal.ScreenCast", "AvailableCursorModes")),
                              None, Gio.DBusCallFlags.NONE, -1, None).unpack()[0]
        t = tok()
        opts = {"types": V("u", 2), "multiple": V("b", False), "persist_mode": V("u", 2), "handle_token": V("s", t)}
        if modes & 1:
            opts["cursor_mode"] = V("u", 1)  # no cursor in the picture
        saved = self._token()
        if saved:
            opts["restore_token"] = V("s", saved)
        self._request(bus, "SelectSources", "(oa{sv})", (session, opts), t, 10)
        t = tok()
        self.state = "asking"
        res = self._request(bus, "Start", "(osa{sv})", (session, "", {"handle_token": V("s", t)}), t, 300)
        if res.get("restore_token"):
            self._token(res["restore_token"])
        node = res["streams"][0][0]
        ret, fds = bus.call_with_unix_fd_list_sync(
            "org.freedesktop.portal.Desktop", "/org/freedesktop/portal/desktop",
            "org.freedesktop.portal.ScreenCast", "OpenPipeWireRemote", V("(oa{sv})", (session, {})),
            GLib.VariantType("(h)"), Gio.DBusCallFlags.NONE, -1, None, None)
        fd = fds.get(ret.unpack()[0])
        self.remote_fd = fd
        stream_fd = os.dup(fd)  # PipeWire owns the descriptor handed to its stream
        # GPU buffers (DMA-BUF) onto the GPU, to RGBA and down into memory, at most MAX_FPS a second
        # (extra frames are dropped before any of that); only the newest frame is kept
        pipeline = Gst.parse_launch(
            ("pipewiresrc fd=%d path=%d do-timestamp=true keepalive-time=1000 "
             "! videorate max-rate=%d drop-only=true "
             "! glupload ! glcolorconvert ! video/x-raw(memory:GLMemory),format=RGBA ! gldownload "
             "! video/x-raw,format=RGBA "
             "! appsink name=sink max-buffers=1 drop=true sync=false emit-signals=true") % (stream_fd, node, MAX_FPS))
        pipeline.get_by_name("sink").connect("new-sample", self._on_sample)
        pipeline.set_state(Gst.State.PLAYING)
        self.pipeline = pipeline
        self.state = "running"
        info("window capture running")

    def _on_sample(self, sink):
        Gst = self.Gst
        sample = sink.emit("pull-sample")
        if sample is None:
            return Gst.FlowReturn.OK
        caps = sample.get_caps().get_structure(0)
        w, h = caps.get_value("width"), caps.get_value("height")
        order = self.ORDERS.get(caps.get_value("format"))
        if order is None:
            return Gst.FlowReturn.OK
        buf = sample.get_buffer()
        stride, offset = w * 4, 0
        try:
            from gi.repository import GstVideo
            meta = GstVideo.buffer_get_video_meta(buf)
            if meta:
                stride, offset = meta.stride[0], meta.offset[0]
        except Exception:
            pass
        full = self.want_full
        self.want_full = False
        n = h if full else min(h, self.top)
        try:  # copy now: the buffer goes back to the stream after this returns
            data = buf.extract_dup(offset, n * stride)
        except Exception:
            return Gst.FlowReturn.OK
        n = len(data) // stride
        rows = np.frombuffer(data, np.uint8)[:n * stride].reshape(n, stride)[:, :w * 4].reshape(n, w, 4)
        self.serial += 1
        self.frame = Frame(rows, w, h, order, self.serial)
        if full:
            self.full = self.frame
        self.new.set()
        return Gst.FlowReturn.OK

    def start(self):
        if self.state != "idle":
            return

        def run():
            try:
                self.state = "starting"
                self._setup()
            except Exception as e:  # cancelled, no portal, no pipewire...
                self.stop()
                self.state = "failed"
                info("window capture unavailable (%s); using screenshots" % e)
        threading.Thread(target=run, daemon=True).start()

    def stop(self):
        if self.pipeline is not None:
            self.pipeline.set_state(self.Gst.State.NULL)
            self.pipeline = None
        self.frame = None
        self.full = None
        if self.bus is not None and self.session is not None:
            try:
                from gi.repository import Gio
                self.bus.call_sync("org.freedesktop.portal.Desktop", self.session,
                                   "org.freedesktop.portal.Session", "Close", None, None,
                                   Gio.DBusCallFlags.NONE, 1000, None)
            except Exception:
                pass
        self.session = self.bus = None
        if self.remote_fd is not None:
            try:
                os.close(self.remote_fd)
            except OSError:
                pass
            self.remote_fd = None

    def check(self):
        """A broken stream falls back to screenshots, never another unsolicited picker."""
        if self.pipeline is None or self.state != "running":
            return
        Gst = self.Gst
        msg = self.pipeline.get_bus().pop_filtered(Gst.MessageType.ERROR | Gst.MessageType.EOS)
        if msg is None:
            return
        why = msg.parse_error()[0].message if msg.type == Gst.MessageType.ERROR else "stream ended"
        self.stop()
        self.failures += 1
        self.state = "failed"
        info("window capture stopped (%s); using screenshots without asking again" % why)

    def wait(self, timeout):
        got = self.new.wait(timeout)
        self.new.clear()
        return got

    def _token(self, value=None):
        try:
            if value is None:
                with open(TOKEN_FILE) as fh:
                    return json.load(fh).get("restore_token")
            os.makedirs(os.path.dirname(TOKEN_FILE), exist_ok=True)
            with open(TOKEN_FILE, "w") as fh:
                json.dump({"restore_token": value}, fh)
        except Exception:
            return None


# ------------------------------------------------------------------------------------------------
# The loop
# ------------------------------------------------------------------------------------------------

class LinuxTracker:
    def __init__(self, use_portal=True, share=True):
        self.core = Core(share=Share(log=info) if share else None, log=log, info=info)
        self.portal = PortalWindow() if use_portal else None
        self.win = None          # beacon in window frames: (x, y, pitch)
        self.place = None        # window pixels -> output pixels: {"out", "dx", "dy", "bx", "by", "pitch"}
        self.screen = None       # screenshot mode: {"out", "region", "bx", "by", "pitch", "misses"}
        self.last_search = -1e9
        self.last_place_check = -1e9
        self.placing = False
        self.sync_place = False  # tests: place on the spot
        self.last_emit = None

    # -- output to the overlay -----------------------------------------------------------------------

    def emit(self, msg):
        line = json.dumps(msg, separators=(",", ":"))
        if line != self.last_emit:
            self.last_emit = line
            print(line, flush=True)

    def hide(self):
        self.emit({"show": False})

    def show(self, view, out, dx, dy):
        """view: Core.view(); dx, dy: window pixels -> output pixels."""
        x, y, w, h = view["canvas"]
        s = out["scale"]
        self.emit({"show": True, "screen": out["name"],
                   "cx": round((x + dx) / s, 1), "cy": round((y + dy) / s, 1),
                   "cw": round(w / s, 1), "ch": round(h / s, 1),
                   "me": view["me"], "friends": view["friends"]})

    # -- window capture mode -------------------------------------------------------------------------

    def window_frame(self, fr, now):
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
                self.hide()
                return
            self.win = (b.x, b.y, b.pitch)
        if not b.fields["map_open"]:
            self.hide()  # first thing: the arrows go the instant the map does
        mm = b.rect("mm")
        if self.portal and mm:
            self.portal.top = int(max(mm[1] + mm[3], b.y + 4)) + 8  # rows to copy: down to the minimap

        def crop(r):
            return fr.crop(*r)

        def full_crop(r):
            full = self.portal.full if self.portal else None
            if full is not None:
                self.portal.full = None
                return full.crop(*r)
            return fr.crop(*r)
        core = self.core
        core.frame(b, crop, now, full_crop)
        if self.portal and core.want_full:
            self.portal.want_full = True
        view = core.view(now)
        if view is None:
            self.hide()
            return
        self.check_place_soon(now, b)
        pl = self.place
        if pl:
            self.show(view, pl["out"], pl["dx"], pl["dy"])
        else:
            self.hide()

    def check_place_soon(self, now, b):
        """Where the game's window is on the screen, in the background (screenshots take ~15 ms)."""
        if self.sync_place:
            self.check_place(now, b.x, b.y)
            return
        if self.placing or (self.place and now - self.last_place_check < PLACE_CHECK_EVERY):
            return
        if not self.place and now - self.last_search < SEARCH_EVERY:
            return
        self.placing = True
        bx, by = b.x, b.y

        def work():
            try:
                self.check_place(now, bx, by)
            finally:
                self.placing = False
        threading.Thread(target=work, daemon=True).start()

    def check_place(self, now, bx, by):
        if self.place and now - self.last_place_check < PLACE_CHECK_EVERY:
            return
        self.last_place_check = now
        pl = self.place
        if pl:
            out, s = pl["out"], pl["out"]["scale"]
            x0, y0 = pl["bx"] - pl["pitch"] * 2, pl["by"] - pl["pitch"] * 2
            w, h = (beacon.CELLS + 4) * pl["pitch"], pl["pitch"] * 4
            img = grab(region=(out["x"] + x0 / s, out["y"] + y0 / s, w / s, h / s))
            sb = None
            if img is not None:
                sb = beacon.decode_at(img, pl["bx"] - x0, pl["by"] - y0, pl["pitch"]) or beacon.find(img)
            if sb:
                pl["bx"], pl["by"] = sb.x + x0, sb.y + y0   # region pixels -> output pixels
                pl["dx"], pl["dy"] = pl["bx"] - bx, pl["by"] - by
                return
            self.place = None
        if now - self.last_search < SEARCH_EVERY:
            return
        self.last_search = now
        out, sb = find_on_screen()
        if sb:
            self.place = {"out": out, "bx": sb.x, "by": sb.y, "pitch": sb.pitch, "dx": sb.x - bx, "dy": sb.y - by}
            log("game found on", out["name"])

    # -- screenshot mode -----------------------------------------------------------------------------

    def screen_frame(self, now):
        sc = self.screen
        if sc is None:
            if now - self.last_search < SEARCH_EVERY:
                return
            self.last_search = now
            out, b = find_on_screen()
            if not b:
                return
            sc = self.screen = {"out": out, "bx": b.x, "by": b.y, "pitch": b.pitch, "misses": 0}
            self._screen_region(b, (0, 0))
        out, s = sc["out"], sc["out"]["scale"]
        rx, ry, rw, rh = sc["region"]
        img = grab(region=(out["x"] + rx / s, out["y"] + ry / s, rw / s, rh / s))
        b = None
        if img is not None:
            b = beacon.decode_at(img, sc["bx"] - rx, sc["by"] - ry, sc["pitch"]) or beacon.find(img)
        if b is None:
            sc["misses"] += 1
            if sc["misses"] >= 3:
                self.screen = None
                self.core.odo.reset()
                self.hide()
            return
        sc["misses"] = 0
        if not b.fields["map_open"]:
            self.hide()
        sc["bx"], sc["by"], sc["pitch"] = b.x + rx, b.y + ry, b.pitch
        mm = b.rect("mm")
        if mm and (mm[0] < 0 or mm[1] < 0 or mm[0] + mm[2] > rw or mm[1] + mm[3] > rh):
            self._screen_region(b, (rx, ry))  # the minimap moved: capture its new place next frame
            self.core.odo.reset()
            return

        def crop(r):
            x, y, w, h = (int(round(c)) for c in r)
            c = img[max(0, y):y + h, max(0, x):x + w]
            return c if c.size else None

        def full_crop(r):
            return grab(region=(out["x"] + (r[0] + rx) / s, out["y"] + (r[1] + ry) / s, r[2] / s, r[3] / s))
        self.core.frame(b, crop, now, full_crop)
        view = self.core.view(now)
        if view is None:
            self.hide()
        else:
            self.show(view, out, rx, ry)

    def _screen_region(self, b, offset):
        """Capture rectangle (output pixels): the beacon strip plus the minimap, padded."""
        ox, oy = offset
        x0, y0 = b.x + ox - b.pitch, b.y + oy - b.pitch
        x1, y1 = b.x + ox + beacon.CELLS * b.pitch, b.y + oy + b.pitch
        mm = b.rect("mm")
        if mm:
            x0, y0 = min(x0, mm[0] + ox), min(y0, mm[1] + oy)
            x1, y1 = max(x1, mm[0] + ox + mm[2]), max(y1, mm[1] + oy + mm[3])
        self.screen["region"] = (int(x0) - 4, int(y0) - 4, int(x1 - x0) + 9, int(y1 - y0) + 9)

    # -- loop ----------------------------------------------------------------------------------------

    def run(self):
        self.hide()
        portal, last_serial, retry = self.portal, None, -1e9
        while True:
            now = time.monotonic()
            if portal:
                portal.check()
                if portal.state == "idle" and now - retry > 5:
                    retry = now
                    if wow_running():  # ask for WoW's window only once it is open
                        portal.start()
            if portal and portal.state == "running":
                if not portal.wait(0.25):
                    continue
                fr = portal.frame
                if fr is None or fr.serial == last_serial:
                    continue
                last_serial = fr.serial
                self.window_frame(fr, time.monotonic())
            elif self.screen is None and not wow_running():
                time.sleep(3.0)  # WoW closed: just wait for it
            else:
                self.screen_frame(now)
                time.sleep(max(0.0, SCREEN_FRAME - (time.monotonic() - now)) if self.screen else 0.25)


def main():
    import fcntl
    # One capture owner even when started manually or while a launcher hook is also firing.
    runtime = os.environ.get("XDG_RUNTIME_DIR") or user_dir("state")
    os.makedirs(runtime, exist_ok=True)
    owner = open(os.path.join(runtime, "dungeon-maps-capture.lock"), "a")
    try:
        fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        owner.close()
        raise SystemExit(73)
    try:
        LinuxTracker(use_portal="--screenshots" not in sys.argv and os.environ.get("DUNGEONMAPS_CAPTURE") != "screenshots",
                     share="--no-share" not in sys.argv).run()
    except KeyboardInterrupt:
        pass
    finally:
        owner.close()
