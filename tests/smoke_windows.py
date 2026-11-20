"""Windows only (CI): the overlay window really is click-through, never-activating and topmost, and
draws you and a friend. No WoW needed."""
import ctypes
import sys
import time

from dungeonmaps import windows

assert sys.platform == "win32"
user32 = ctypes.windll.user32
ov = windows.Overlay()
me = {"u": 0.5, "v": 0.5, "heading": 45.0, "fresh": True, "guess": False, "size": 1.5}
friend = {"name": "Byai", "u": 0.3, "v": 0.6, "color": "#ff7c0a", "fresh": True, "guess": False}
fg_before = user32.GetForegroundWindow()
ov.update((100, 100, 800, 533, me, [friend]))
for _ in range(20):
    ov.root.update()
    time.sleep(0.02)
style = user32.GetWindowLongW(ov.hwnd, -20)
assert style & 0x20 and style & 0x80000 and style & 0x8000000 and style & 0x8, hex(style)  # transparent, layered, noactivate, topmost
assert user32.IsWindowVisible(ov.hwnd)
assert user32.GetForegroundWindow() == fg_before, "overlay took the foreground"
assert len(ov.canvas.find_all()) >= 4, ov.canvas.find_all()
ov.update(None)
ov.root.update()
assert not user32.IsWindowVisible(ov.hwnd)
ov.root.destroy()
print("PASS windows overlay smoke")
