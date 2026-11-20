"""Logs for fixing problems: each tracker sends its log lines, crash tracebacks and a stats summary to
the relay about once a minute (and when it closes), where they're kept per person per day.

Sent: an install id (random, made once), your character name, the tracker version, the system (OS
and build, compositor), the log lines (the same as the local tracker.log) and a stats line a minute:
frames, time per frame, how often the minimap was read, how your position was fixed, capture mode,
relay status. Never pictures. DUNGEONMAPS_LOGS=off (or DUNGEONMAPS_RELAY=off) sends nothing.
"""

import collections
import json
import os
import platform
import sys
import threading
import time
import traceback
import uuid

from . import __version__
from .data import user_dir
from .share import PROTOCOL, relay_url

EVERY = 60.0          # seconds between batches
MAX_LINES = 400       # per batch (the relay refuses more)
MAX_BYTES = 120_000   # (the relay takes up to 128 KB a message)
FIRST_AFTER = 20.0    # the first batch: soon after starting (start-up problems matter most)


def install_id():
    path = os.path.join(user_dir("state"), "install-id")
    try:
        with open(path, encoding="utf-8") as fh:
            v = fh.read().strip()
            if len(v) == 32:
                return v
    except OSError:
        pass
    v = uuid.uuid4().hex
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(v)
    except OSError:
        pass
    return v


def system():
    s = "%s %s" % (platform.system(), platform.release())
    if sys.platform == "win32":
        try:
            s += " build %d" % sys.getwindowsversion().build
        except Exception:
            pass
    else:
        for k, name in (("NIRI_SOCKET", "niri"), ("HYPRLAND_INSTANCE_SIGNATURE", "Hyprland"),
                        ("SWAYSOCK", "sway")):
            if os.environ.get(k):
                s += " " + name
                break
        else:
            s += " " + (os.environ.get("XDG_CURRENT_DESKTOP") or "?")
    return s


class Telemetry:
    def __init__(self, url=None, connect=None):
        url = url or relay_url()
        off = os.environ.get("DUNGEONMAPS_LOGS", "").lower() in ("off", "0", "no")
        self.url = None if off else url
        self.id = install_id()
        self.lines = collections.deque(maxlen=2000)
        self.lock = threading.Lock()
        self.stats = None            # () -> dict, set by the tracker
        self.name = lambda: ""
        self._connect = connect      # tests
        self.thread = None
        self.sent = 0

    def record(self, text):
        with self.lock:
            self.lines.append("%s %s" % (time.strftime("%H:%M:%S"), text[:1000]))

    def install_hooks(self):
        """Crashes (any thread) go into the log too."""
        old = sys.excepthook

        def hook(kind, value, tb):
            self.record("CRASH " + "".join(traceback.format_exception(kind, value, tb)))
            self.flush(timeout=3)
            old(kind, value, tb)
        sys.excepthook = hook

        def thread_hook(args):
            self.record("CRASH in thread %s: %s" % (args.thread.name if args.thread else "?", "".join(
                traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback))))
        threading.excepthook = thread_hook

    def start(self):
        if not self.url or self.thread:
            return
        self.install_hooks()
        self.thread = threading.Thread(target=self._run, name="telemetry", daemon=True)
        self.thread.start()

    def _run(self):
        time.sleep(FIRST_AFTER)
        while True:
            self.flush()
            time.sleep(EVERY)

    def batch(self):
        lines, size = [], 0
        with self.lock:
            while self.lines and len(lines) < MAX_LINES and size + len(self.lines[0]) < MAX_BYTES:
                size += len(self.lines[0]) + 4
                lines.append(self.lines.popleft())
        stats = None
        if self.stats:
            try:
                stats = self.stats()
            except Exception as e:
                stats = {"error": repr(e)}
        return {"t": "log", "app": PROTOCOL, "id": self.id, "name": (self.name() or "")[:24],
                "v": __version__, "os": system(), "lines": lines, "stats": stats}

    def flush(self, timeout=10):
        if not self.url:
            return False
        msg = self.batch()
        try:
            if self._connect:
                ws = self._connect(self.url)
            else:
                from websockets.sync.client import connect
                ws = connect(self.url, open_timeout=timeout, close_timeout=2, max_size=4096,
                             user_agent_header="DungeonMaps")
            try:
                ws.send(json.dumps(msg, separators=(",", ":")))
            finally:
                ws.close()
            self.sent += 1
            return True
        except Exception:
            with self.lock:  # keep them for the next try (the newest win if it overflows)
                self.lines.extendleft(reversed(msg["lines"]))
            return False


telemetry = Telemetry.__new__(Telemetry)   # replaced by setup(); record() before that is a no-op
telemetry.record = lambda text: None


def setup():
    global telemetry
    telemetry = Telemetry()
    return telemetry
