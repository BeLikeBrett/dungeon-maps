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
    print("PASS update")


if __name__ == "__main__":
    main()
