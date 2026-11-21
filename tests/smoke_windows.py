"""Windows only (CI): the overlay window really is click-through, never-activating and topmost, and
draws you and a friend. No WoW needed."""
import os as _os, tempfile as _tempfile  # noqa: E401
if not _os.environ.get("DUNGEONMAPS_TEST_ISOLATED"):  # never touch the real atlas, calibration or caches
    _tmp = _tempfile.mkdtemp(prefix="dungeonmaps-test-")
    _os.environ.update(XDG_DATA_HOME=_tmp, XDG_STATE_HOME=_tmp, LOCALAPPDATA=_tmp, DUNGEONMAPS_TEST_ISOLATED="1")

import ctypes
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dungeonmaps import windows

assert sys.platform == "win32"
user32 = ctypes.windll.user32
def foreground():
    hwnd = user32.GetForegroundWindow()
    title = ctypes.create_unicode_buffer(256)
    user32.GetWindowTextW(ctypes.c_void_p(hwnd), title, len(title))
    return hwnd, title.value

fg_before = user32.GetForegroundWindow()
print("foreground before overlay:", foreground(), flush=True)
ov = windows.Overlay()
print("foreground after overlay:", foreground(), "overlay:", ov.hwnd,
      "native layered window", flush=True)
assert user32.GetForegroundWindow() == fg_before, "overlay initialization took the foreground"
me = {"u": 0.5, "v": 0.5, "heading": 45.0, "fresh": True, "guess": False, "size": 1.5}
friend = {"name": "Byai", "u": 0.3, "v": 0.6, "color": "#ff7c0a", "fresh": True, "guess": False}
ov.update((100, 100, 800, 533, me, [friend]))
for _ in range(20):
    ov.pump()
    time.sleep(0.02)
style = user32.GetWindowLongW(ov.hwnd, -20)
assert style & 0x20 and style & 0x80000 and style & 0x8000000 and style & 0x8, hex(style)  # transparent, layered, noactivate, topmost
assert user32.IsWindowVisible(ov.hwnd)
assert user32.GetForegroundWindow() == fg_before, "overlay took the foreground"
assert ov.image.getpixel((240, 320)) == (255, 124, 10, 255), "friend dot missing"
assert ov.image.getbbox(), "empty overlay"
ov.notice("Dungeon Maps smoke test", seconds=0.1)
ov.pump()
assert user32.GetForegroundWindow() == fg_before, "notice took the foreground"
closed = []
tray = windows.Tray(lambda: closed.append(True))
assert not user32.IsWindowVisible(tray.hwnd), "tray opened a window"
assert user32.GetForegroundWindow() == fg_before, "tray took the foreground"
user32.PostMessageW(tray.hwnd, 0x111, windows.Tray.CLOSE, 0)
ov.pump()
assert closed == [True], "tray Close command was not handled"
tray.close()
ov.update(None)
ov.pump()
assert not user32.IsWindowVisible(ov.hwnd)
ov.close()
print("PASS windows overlay smoke")
