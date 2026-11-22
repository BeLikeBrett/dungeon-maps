"""The self-updater's parts that don't need Windows: versions, the add-on swap, digest checks."""
import os as _os, tempfile as _tempfile  # noqa: E401
if not _os.environ.get("DUNGEONMAPS_TEST_ISOLATED"):  # never touch the real atlas, calibration or caches
    _tmp = _tempfile.mkdtemp(prefix="dungeonmaps-test-")
    _os.environ.update(XDG_DATA_HOME=_tmp, XDG_STATE_HOME=_tmp, LOCALAPPDATA=_tmp, DUNGEONMAPS_TEST_ISOLATED="1")

import hashlib
import io
import os
import sys
import tempfile
import zipfile
from unittest.mock import patch

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
from dungeonmaps import update  # noqa: E402


def addon_zip(version):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        src = os.path.join(ROOT, "addon", "DungeonMaps")
        for dirpath, _, files in os.walk(src):
            for f in files:
                path = os.path.join(dirpath, f)
                name = os.path.relpath(path, os.path.join(ROOT, "addon")).replace(os.sep, "/")
                data = open(path, "rb").read()
                if f == "DungeonMaps.toc":
                    data = b"\n".join(b"## Version: " + version.encode() if l.startswith(b"## Version:") else l
                                      for l in data.split(b"\n"))
                z.writestr(name, data)
        z.writestr("../evil.txt", b"no")          # never written outside the add-on folder
    return buf.getvalue()


def main():
    assert update.version_tuple("v1.0.3") == (1, 0, 3) and update.version_tuple("## Version: 1.0.10") == (1, 0, 10)
    assert update.version_tuple("v1.0.10") > update.version_tuple("v1.0.9")
    with tempfile.TemporaryDirectory() as tmp:
        addons = os.path.join(tmp, "_forever_", "Interface", "AddOns")
        os.makedirs(os.path.join(addons, "DungeonMaps"))
        with open(os.path.join(addons, "DungeonMaps", "DungeonMaps.toc"), "w") as fh:
            fh.write("## Title: Dungeon Maps\n## Version: 1.0.1\n")
        open(os.path.join(addons, "DungeonMaps", "stale.lua"), "w").close()
        z = addon_zip("9.9.9")
        rel = {"version": (9, 9, 9), "tag": "v9.9.9",
               "assets": {update.ADDON_ASSET: {"url": "x", "sha256": hashlib.sha256(z).hexdigest()}}}
        update._get = lambda url, timeout: z
        logs = []
        note = update.update_addon(rel, logs.append, [addons])
        assert note and "/reload" in note, (note, logs)
        assert update.addon_version(addons) == (9, 9, 9)
        files = set(os.listdir(os.path.join(addons, "DungeonMaps")))
        assert "stale.lua" not in files and "DungeonMaps.lua" in files and "maps" in files, files
        assert not os.path.exists(os.path.join(tmp, "_forever_", "Interface", "evil.txt"))
        assert not any(n.startswith("DungeonMaps.") for n in os.listdir(addons)), os.listdir(addons)
        # up to date: nothing happens
        assert update.update_addon(rel, logs.append, [addons]) is None
        # a download that doesn't match GitHub's digest is refused and the add-on is left alone
        bad = dict(rel, version=(10, 0, 0), tag="v10.0.0",
                   assets={update.ADDON_ASSET: {"url": "x", "sha256": "0" * 64}})
        assert update.update_addon(bad, logs.append, [addons]) is None
        assert update.addon_version(addons) == (9, 9, 9) and any("SHA-256" in line for line in logs), logs
        # the exe never updates itself when not frozen (running from source)
        assert update.update_exe(dict(rel, version=(99,)), logs.append) is False
        # Failure at the final directory swap restores the installed addon.
        replace = os.replace
        def fail_addon_swap(src, dest):
            if src.endswith("DungeonMaps.update"):
                raise OSError("simulated install failure")
            return replace(src, dest)
        with patch.object(update.os, "replace", side_effect=fail_addon_swap):
            assert update.update_addon(dict(rel, version=(10,)), logs.append, [addons]) is None
        assert update.addon_version(addons) == (9, 9, 9)
        # Exercise the frozen EXE path: digest check, replacement, preserved
        # options, parent handoff, rollback on failed launch and failed swap.
        exe = os.path.join(tmp, "DungeonMaps.exe")
        payload = b"new executable fixture"
        exe_rel = dict(rel, version=(99,), assets={update.EXE_ASSET:
                       {"url": "exe", "sha256": hashlib.sha256(payload).hexdigest()}})
        with patch.object(sys, "frozen", True, create=True), patch.object(sys, "executable", exe), \
             patch.object(sys, "argv", [exe, "--no-share", "--updated-from=123"]), \
             patch.object(update, "_get", return_value=payload):
            with open(exe, "wb") as f: f.write(b"old executable")
            with patch("subprocess.Popen") as launch:
                assert update.update_exe(exe_rel, logs.append)
                args = launch.call_args.args[0]
                assert args == [exe, "--no-share", "--updated-from=%d" % os.getpid()], args
            assert open(exe, "rb").read() == payload
            assert open(exe + ".old", "rb").read() == b"old executable"
            for mode in ("launch", "swap"):
                with open(exe, "wb") as f: f.write(b"old executable")
                def fail_exe_swap(src, dest):
                    if src == exe + ".new": raise OSError("simulated swap failure")
                    return replace(src, dest)
                with patch("subprocess.Popen", side_effect=OSError("launch failed")), \
                     patch.object(update.os, "replace", side_effect=fail_exe_swap if mode == "swap" else replace):
                    assert not update.update_exe(exe_rel, logs.append)
                assert open(exe, "rb").read() == b"old executable"
                assert not os.path.exists(exe + ".new")
    with patch.object(sys, "frozen", True, create=True), \
         patch.object(update, "wait_for_previous"), patch.object(update, "cleanup_old_exe"), \
         patch.object(update, "latest_release", return_value=exe_rel), \
         patch.object(update, "update_addon") as addon:
        for result in (True, False):
            with patch.object(update, "update_exe", return_value=result):
                assert update.run(logs.append) == (result, None)
                addon.assert_not_called()
    print("PASS update")


if __name__ == "__main__":
    main()
