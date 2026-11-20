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
from dungeonmaps.windows_permissions import BORDER_TITLE, CAPTURE_TITLE
from test_pipeline import encode


def main():
    import tkinter as tk
    from ctypes import wintypes

    exe = str(Path(sys.argv[1]).resolve())
    result = {"platform": sys.getwindowsversion().build}
    root = tk.Tk()
    root.title("World of Warcraft")
    root.geometry("900x650+40+30")
    label = tk.Label(root, bd=0, highlightthickness=0, anchor="nw")
    label.pack()
    shown = []
    serial = 0
    consent_answer = 6
    consent_count = 0
    windows.user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    windows.user32.SendMessageW.restype = ctypes.c_ssize_t

    def answer_prompts():
        nonlocal consent_count
        dialog = windows.user32.FindWindowW("#32770", CAPTURE_TITLE)
        if dialog:
            consent_count += 1
            windows.user32.SendMessageW(dialog, 0x111, consent_answer, 0)
        dialog = windows.user32.FindWindowW("#32770", BORDER_TITLE)
        if dialog:
            # CI must not modify system policy. Continue with a border if the OS denies it.
            windows.user32.SendMessageW(dialog, 0x111, 7, 0)

    def paint(pitch=2):
        nonlocal serial
        serial += 1
        fields = dict(version=beacon.FORMAT_VERSION, map_open=1, indoors=1, zoom=3, radius4=240,
                      dungeon=1, shown_floor=1, lm_count=1, lm_kind=1, lm_floor=1,
                      lm_u=0.55 * 4095, lm_v=0.4 * 4095,
                      mm_x=720 + 4096, mm_y=40 + 4096, mm_w=140, mm_h=140,
                      cv_x=100 + 4096, cv_y=200 + 4096, cv_w=700, cv_h=420,
                      arrow_size=15, name_len=4, n0=84, n1=101, n2=115, n3=116,
                      cr=31, cg=31, cb=31)
        img = np.full((650, 900, 3), 40, np.uint8)
        img[200:620, 100:800] = (70, 80, 90)
        # Moving counter outside the beacon forces new WGC frames.
        img[630:640, 0:serial % 100 + 1] = (90, 100, 110)
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
            answer_prompts()
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
    for pitch, position in ((2, "+40+30"), (3, "+80+50")):
        root.geometry("900x650" + position)
        rgb = paint(pitch)
        bgra = np.zeros((650, 900, 4), np.uint8)
        bgra[:, :, :3] = rgb[:, :, ::-1]
        tracker.process(windows.Frame(bgra, 900, 650, pitch), time.monotonic())
        assert tracker.state and tracker.state[4], "beacon did not produce a player marker"
        ox, oy, _ = windows.frame_origin(hwnd)
        # Beacon coordinates use sampled cell centres (up to half a physical pixel).
        expected = (ox + 100, oy + 200, 700, 420)
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
        # Compare the real captured canvas to its client-area position on the desktop, including
        # the title bar and frame. This catches capture-origin errors that raw-frame tests cannot.
        windows.user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
        client = wintypes.POINT(0, 0)
        assert windows.user32.ClientToScreen(hwnd, ctypes.byref(client))
        expected = (client.x + 100, client.y + 200, 700, 420)
        assert all(abs(a - b) <= 1 for a, b in zip(tracker.state[:4], expected)), (tracker.state, expected)
        captured_overlay = windows.Overlay()
        try:
            captured_overlay.update(tracker.state)
            captured_overlay.pump()
            rect = wintypes.RECT()
            windows.user32.GetWindowRect(captured_overlay.hwnd, ctypes.byref(rect))
            assert all(abs(a - b) <= 1 for a, b in zip(
                (rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top), expected))
            ImageGrab.grab().save("windows-captured-overlay.png")
        finally:
            captured_overlay.close()
        result["wgc_physical_canvas_alignment"] = True
        result["wgc_capture_decode"] = True
        # WGC must keep delivering the game when another ordinary window covers it. Only the
        # overlay is hidden; tracking continues, without drawing over the covering application.
        cover = tk.Toplevel(root)
        cover.title("Synthetic covering window")
        cover.geometry("950x700+40+20")
        cover.update()
        cover_hwnd = windows.user32.GetParent(cover.winfo_id()) or cover.winfo_id()
        windows.user32.SetForegroundWindow(cover_hwnd)
        serial_before = cap.serial
        pump(0.4, 3)
        assert cap.serial > serial_before, "covered game stopped producing frames"
        tracker.process(cap.frame, time.monotonic())
        assert tracker.state and tracker.overlay_state() is None, "covered overlay remained visible"
        cover.destroy()
        windows.user32.SetForegroundWindow(hwnd)
        assert tracker.overlay_state() is not None
        result["wgc_tracks_while_covered"] = True
        result["overlay_hidden_while_covered"] = True
    except Exception as error:
        result["wgc_capture_decode"] = str(error)
        if "--allow-no-capture" not in sys.argv:
            raise
        print("UNVERIFIED WGC:", error, flush=True)
    finally:
        result["wgc_frame_count"] = cap.serial
        result["wgc_closed"] = cap.closed
        if cap.frame:
            fr = cap.frame
            result["wgc_frame_size"] = [fr.w, fr.h, fr.rows.shape[0]]
            Image.fromarray(fr.crop(0, 0, fr.w, fr.rows.shape[0])).save("windows-capture.png")
        cap.stop()

    # Exercise the actual one-file executable, including its bootloader and named mutex.
    processes = []
    with tempfile.TemporaryDirectory(prefix="dungeonmaps-test-") as state:
        env = dict(os.environ, LOCALAPPDATA=state, DUNGEONMAPS_RELAY="off")
        log = Path(state) / "DungeonMaps" / "state" / "tracker.log"
        try:
            consent_answer = 7
            declined = subprocess.Popen([exe, "--no-share"], env=env)
            processes.append(declined)
            deadline = time.monotonic() + 30
            while declined.poll() is None and time.monotonic() < deadline:
                pump(0.1, 3)
            assert declined.returncode == 0 and "capture permission declined" in log.read_text()
            assert "tracker started" not in log.read_text(), "captured without consent"
            result["exe_capture_consent_declined"] = True
            consent_answer = 6
            first = subprocess.Popen([exe, "--no-share"], env=env)
            processes.append(first)
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                pump(0.1, 3)
                if log.exists() and "tracker started" in log.read_text():
                    break
                assert first.poll() is None, "packaged executable failed at startup"
            else:
                ImageGrab.grab().save("windows-startup.png")
                raise AssertionError("packaged executable did not start")
            assert "capture permission granted for this run" in log.read_text()
            assert "borderless capture access" in log.read_text()
            assert "ModuleNotFoundError" not in log.read_text() and "ImportError" not in log.read_text(), log.read_text()
            result["exe_capture_consent_accepted"] = True
            # The launch-time permission UI is authorized; the running tracker must then preserve
            # the fake game's foreground, including when a second copy is started.
            windows.user32.SetForegroundWindow(hwnd)
            foreground = windows.user32.GetForegroundWindow()
            deadline = time.monotonic() + 10
            tray = None
            while time.monotonic() < deadline:
                pump(0.1, 3)
                tray = windows.user32.FindWindowW(windows.Tray.CLASS, "Dungeon Maps tracker")
                if tray and "tray icon ready" in log.read_text():
                    break
            assert tray and not windows.user32.IsWindowVisible(tray), "silent tray startup failed"
            result["exe_silent_tray_startup"] = True
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
            assert not windows.user32.FindWindowW(windows.Tray.CLASS, "Dungeon Maps tracker"), "tray window leaked"
            # Relaunch with an active capture, then select the tray's Close command while the
            # fake game keeps rendering. This also checks shutdown of the native capture thread.
            root = tk.Tk()
            root.title("World of Warcraft")
            root.geometry("900x650+40+30")
            label = tk.Label(root, bd=0, highlightthickness=0, anchor="nw")
            label.pack()
            paint(3)
            manual = subprocess.Popen([exe, "--no-share"], env=env)
            processes.append(manual)
            deadline = time.monotonic() + 30
            tray = None
            while time.monotonic() < deadline:
                tray = windows.user32.FindWindowW(windows.Tray.CLASS, "Dungeon Maps tracker")
                if tray and log.read_text().count("capturing World of Warcraft") == 2:
                    break
                assert manual.poll() is None, "manual-close instance failed at startup"
                pump(0.1, 3)
            assert tray and log.read_text().count("capturing World of Warcraft") >= 2, "manual-close capture never started"
            windows.user32.PostMessageW(tray, 0x111, windows.Tray.CLOSE, 0)
            deadline = time.monotonic() + 5
            while manual.poll() is None and time.monotonic() < deadline:
                pump(0.1, 3)
            assert manual.returncode == 0, "tray Close did not exit cleanly"
            root.destroy()
            result["exe_tray_close"] = True
            assert consent_count == 3, ("unexpected permission prompt count", consent_count)
            result["exe_permission_once_per_launch"] = True
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
