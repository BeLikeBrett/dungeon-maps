"""Real Windows checks using a synthetic game window; never connects to or controls WoW.

Run after building: python tests/windows_integration.py dist/DungeonMaps.exe
CI may pass --allow-no-capture: unsupported WGC is reported explicitly, never as verified.
"""
import ctypes
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np
from PIL import Image, ImageTk, ImageGrab
from dungeonmaps import beacon, windows
from test_pipeline import encode


def main():
    import tkinter as tk
    from ctypes import wintypes

    exe = str(Path(sys.argv[1]).resolve())
    result = {"platform": sys.getwindowsversion().build}
    root = tk.Tk()
    root.title("World of Warcraft")
    root.geometry("1100x700+40+30")
    label = tk.Label(root, bd=0, highlightthickness=0)
    label.pack()
    shown = []
    serial = 0

    def paint(pitch=2):
        nonlocal serial
        serial += 1
        fields = dict(version=beacon.FORMAT_VERSION, map_open=1, indoors=1, zoom=3, radius4=240,
                      dungeon=1, shown_floor=1, lm_count=1, lm_kind=1, lm_floor=1,
                      lm_u=0.55 * 4095, lm_v=0.4 * 4095,
                      mm_x=900 + 4096, mm_y=40 + 4096, mm_w=140, mm_h=140,
                      cv_x=100 + 4096, cv_y=200 + 4096, cv_w=700, cv_h=460,
                      arrow_size=15, name_len=4, n0=84, n1=101, n2=115, n3=116,
                      cr=31, cg=31, cb=31)
        img = np.full((700, 1100, 3), 40, np.uint8)
        img[200:660, 100:800] = (70, 80, 90)
        # Moving counter outside the beacon forces new WGC frames.
        img[680:690, 0:serial % 100 + 1] = (90, 100, 110)
        for i, colour in enumerate(encode(fields)):
            img[:pitch, pitch * i:pitch * (i + 1)] = colour
        photo = ImageTk.PhotoImage(Image.fromarray(img))
        label.configure(image=photo)
        label.image = photo
        shown.append(photo)
        if len(shown) > 2:
            shown.pop(0)
        root.update()
        return img

    def pump(seconds, pitch=2):
        until = time.monotonic() + seconds
        while time.monotonic() < until:
            paint(pitch)
            time.sleep(0.03)

    paint()
    hwnd = windows.find_wow()
    assert hwnd, "synthetic game window not found"
    result["dpi"] = windows.user32.GetDpiForWindow(hwnd)
    tracker = windows.WindowsTracker(share=False)
    tracker.hwnd = hwnd
    tracker.core.walkmaps.has_art = lambda floor: True
    # Verify physical placement and beacon decoding at two UI scales, even if WGC is unavailable.
    ov = windows.Overlay()
    foreground = windows.user32.GetForegroundWindow()
    for pitch, position in ((2, "+40+30"), (3, "+140+80")):
        root.geometry("1100x700" + position)
        rgb = paint(pitch)
        bgra = np.zeros((700, 1100, 4), np.uint8)
        bgra[:, :, :3] = rgb[:, :, ::-1]
        tracker.process(windows.Frame(bgra, 1100, 700, pitch), time.monotonic())
        assert tracker.state and tracker.state[4], "beacon did not produce a player marker"
        ox, oy, _ = windows.frame_origin(hwnd)
        # Beacon coordinates use sampled cell centres (up to half a physical pixel).
        expected = (ox + 100, oy + 200, 700, 460)
        assert all(abs(a - b) <= 1 for a, b in zip(tracker.state[:4], expected)), tracker.state
        ov.update(tracker.state)
        ov.pump()
        rect = wintypes.RECT()
        windows.user32.GetWindowRect(ov.hwnd, ctypes.byref(rect))
        assert (rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top) == tuple(round(v) for v in tracker.state[:4])
        assert windows.user32.GetForegroundWindow() == foreground, "overlay took focus"
    ImageGrab.grab().save("windows-integration.png")
    result["physical_placement_and_beacon_pitches"] = [2, 3]
    ov.close()

    # WGC is unavailable on some virtual display adapters; record the limitation distinctly.
    cap = windows.WindowCapture()
    try:
        cap.start(hwnd)
        until = time.monotonic() + 10
        decoded = None
        while time.monotonic() < until:
            paint(3)
            fr = cap.frame
            if fr:
                decoded = beacon.find(fr.crop(0, 0, fr.w, 160))
                if decoded:
                    tracker.process(fr, time.monotonic())
                    break
            time.sleep(0.05)
        assert decoded and tracker.state, "WGC produced no decodable synthetic frame"
        result["wgc_capture_decode"] = True
    except Exception as error:
        result["wgc_capture_decode"] = str(error)
        if "--allow-no-capture" not in sys.argv:
            raise
        print("UNVERIFIED WGC:", error, flush=True)
    finally:
        cap.stop()

    # Exercise the actual one-file executable, including its bootloader and named mutex.
    processes = []
    with tempfile.TemporaryDirectory(prefix="dungeonmaps-test-") as state:
        env = dict(os.environ, LOCALAPPDATA=state, DUNGEONMAPS_RELAY="off")
        log = Path(state) / "DungeonMaps" / "state" / "tracker.log"
        try:
            first = subprocess.Popen([exe, "--no-share"], env=env)
            processes.append(first)
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                pump(0.1, 3)
                if log.exists() and "tracker started" in log.read_text():
                    break
                assert first.poll() is None, "packaged executable failed at startup"
            else:
                raise AssertionError("packaged executable did not start")
            foreground = windows.user32.GetForegroundWindow()
            pump(2, 3)
            assert first.poll() is None
            second = subprocess.Popen([exe, "--no-share"], env=env)
            processes.append(second)
            deadline = time.monotonic() + 15
            while second.poll() is None and time.monotonic() < deadline:
                pump(0.1, 3)
            assert second.poll() == 0, "second instance did not exit cleanly"
            assert first.poll() is None, "second instance ended the first"
            assert log.read_text().count("tracker started") == 1, log.read_text()
            assert windows.user32.GetForegroundWindow() == foreground, "executable took focus"
            result["exe_single_instance"] = True
            # Allow capture to finish starting before closing the fake game.
            pump(2, 3)
            root.destroy()
            closed = time.monotonic()
            first.wait(timeout=12)
            elapsed = time.monotonic() - closed
            assert first.returncode == 0 and "WoW closed: tracker closing" in log.read_text(), log.read_text()
            result["exe_exit_seconds_after_window_closed"] = round(elapsed, 2)
            assert 2.5 <= elapsed < 4.5, elapsed
            result["exe_log"] = log.read_text()
        finally:
            for process in processes:
                if process.poll() is None:
                    process.terminate()  # exact handles for our test children only
                    process.wait(timeout=10)
    Path("windows-test-results.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2), flush=True)
    print("PASS Windows executable integration", flush=True)


if __name__ == "__main__":
    main()
