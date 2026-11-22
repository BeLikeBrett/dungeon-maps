"""Round trip: the addon's real Lua encodes a beacon (beacon_harness.lua, stubbed WoW API), this
paints it into a fake 2544x1349 screen (with a gamma shift and blurred cell edges) and decodes it."""
import os as _os, tempfile as _tempfile  # noqa: E401
if not _os.environ.get("DUNGEONMAPS_TEST_ISOLATED"):  # never touch the real atlas, calibration or caches
    _tmp = _tempfile.mkdtemp(prefix="dungeonmaps-test-")
    _os.environ.update(XDG_DATA_HOME=_tmp, XDG_STATE_HOME=_tmp, LOCALAPPDATA=_tmp, DUNGEONMAPS_TEST_ISOLATED="1")

import json
import os
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from dungeonmaps import beacon  # noqa: E402

ADDONS = os.path.join(os.path.dirname(HERE), "addon")  # the addon in this repo
GUIDS = ["Player-5826-0A1B2C3D", "Player-5826-00FF0011", "Player-5826-0B00B135", "Player-5826-01234567",
         "Player-5826-0C0FFEE0"]  # beacon_harness.lua's group


def group_key(guids):
    """Python twin of the addon's groupKey(): djb2 of the sorted GUIDs, mod 2^32."""
    h = 5381
    for ch in ",".join(sorted(guids)).encode():
        h = (h * 33 + ch) % 2 ** 32
    return h or 1


def lua_beacon():
    out = subprocess.run(["lua5.1", os.path.join(HERE, "beacon_harness.lua"), ADDONS], capture_output=True, text=True, check=True).stdout
    return json.loads([l for l in out.splitlines() if l.startswith("{")][-1])


def paint(info, gamma=1.0, blur=True):
    rng = np.random.default_rng(1)
    img = rng.integers(0, 256, (1349, 2544, 3), dtype=np.uint8)  # busy game picture
    bx, by = info["beacon"]
    P = beacon.PX
    for i, c in enumerate(info["cells"]):
        img[by:by + P, bx + P * i:bx + P * i + P] = c
    if blur:  # the right half of each cell's last column blends a little into the next
        sl = img[by:by + P, bx:bx + P * beacon.CELLS + 1].astype(np.float32)
        sl[:, P::P] = 0.8 * sl[:, P::P] + 0.2 * sl[:, P - 1:-1:P]
        img[by:by + P, bx:bx + P * beacon.CELLS + 1] = sl.astype(np.uint8)
    img = (255 * (img / 255.0) ** gamma).astype(np.uint8)
    return img


def main():
    info = lua_beacon()
    assert info["shown"], "beacon hidden"
    for gamma in (1.0, 0.8, 1.25):
        img = paint(info, gamma)
        b = beacon.find(img)
        assert b, "not found at gamma %s" % gamma
        f = b.fields
        assert f["dungeon"] == 1 and f["map_open"] == 1 and f["shown_floor"] == 1, f
        assert f["lm_kind"] == 1 and f["lm_count"] == 1 and f["lm_floor"] == 1, f
        assert abs(f["lm_u"] / 4095 - 612 / 1002) < 0.01 and abs(f["lm_v"] / 4095 - 47 / 668) < 0.01, f
        assert f["room"] == 1 and f["zoom"] == 3 and f["indoors"] == 1 and f["radius4"] == 240, f
        assert f["version"] == beacon.FORMAT_VERSION and b.name == "Breziath", (f["version"], b.name)
        assert f["group"] == group_key(GUIDS), (f["group"], group_key(GUIDS))
        # the harness's player has no class (grey 0.8) and set "Your arrow size" to 1.4
        assert b.colour == "#cecece" and b.arrow_size == 1.4, (b.colour, b.arrow_size)
        mm, cv = b.rect("mm"), b.rect("cv")
        em, ec = info["minimap"], info["canvas"]
        for got, want in ((mm, em), (cv, ec)):
            assert all(abs(g - w) <= 1.5 for g, w in zip(got, want)), (got, want)
        print("gamma %.2f ok (%s, group %08x): beacon at (%.1f, %.1f) pitch %.2f, minimap %s, map canvas %s" % (
            gamma, b.name, f["group"], b.x, b.y, b.pitch, tuple(round(v, 1) for v in mm), tuple(round(v, 1) for v in cv)))
    print("PASS beacon round trip")
    # Aligning the beacon above the minimap preserves decoded coordinates while
    # drastically reducing the screenshot rectangle read back from the desktop.
    from dungeonmaps.linux import LinuxTracker
    output = subprocess.run(["lua5.1", os.path.join(HERE, "beacon_harness.lua"), ADDONS, "near"],
                            capture_output=True, text=True, check=True).stdout
    near = json.loads([line for line in output.splitlines() if line.startswith("{")][-1])
    b = beacon.find(paint(near))
    assert b and abs(b.x - near["minimap"][0]) < 2
    assert all(abs(g - w) < 1.5 for g, w in zip(b.rect("cv"), near["canvas"]))
    tracker = LinuxTracker(share=False, use_portal=False)
    tracker.screen = {}
    tracker._screen_region(b, (0, 0))
    new = tracker.screen["region"]
    tracker._screen_region(beacon.find(paint(info)), (0, 0))
    old = tracker.screen["region"]
    assert new[2] * new[3] < old[2] * old[3] / 10, (old, new)
    print("PASS compact screenshot region: %s -> %s (%.1fx fewer pixels)" %
          (old[2:], new[2:], old[2] * old[3] / (new[2] * new[3])))
    blocked = subprocess.run(["lua5.1", os.path.join(HERE, "beacon_harness.lua"), ADDONS, "blocked"],
                             capture_output=True, text=True, check=True).stdout
    blocked = json.loads([line for line in blocked.splitlines() if line.startswith("{")][-1])
    assert beacon.find(paint(blocked)).fields["minimap_blocked"] == 1
    assert b.fields["minimap_blocked"] == 0


if __name__ == "__main__":
    main()
