"""Facing from the minimap arrow (the game's own arrow, drawn on the synthetic dungeon's minimap at the
test's smaller UI scale): spin on the spot over varied ground, both ways, and check the angle read
against the truth on every frame. Nothing is learned first."""
import os as _os, tempfile as _tempfile  # noqa: E401
if not _os.environ.get("DUNGEONMAPS_TEST_ISOLATED"):  # never touch the real atlas, calibration or caches
    _tmp = _tempfile.mkdtemp(prefix="dungeonmaps-test-")
    _os.environ.update(XDG_DATA_HOME=_tmp, XDG_STATE_HOME=_tmp, LOCALAPPDATA=_tmp, DUNGEONMAPS_TEST_ISOLATED="1")

import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
import test_odometry as sim  # noqa: E402
from dungeonmaps.facing import Facing  # noqa: E402


def main():
    rng = np.random.default_rng(4)
    fc = Facing()
    errs, times, misses = [], [], 0
    for void in (True, False):
        w = sim.world(void=void)
        x = y = 1300.0
        for k in range(360):
            true = (k * 7.3) % 360 if k < 180 else (-k * 11.1) % 360
            if k % 30 == 0:  # somewhere else
                x, y = rng.uniform(400, 2200, 2)
                while void and w[int(y), int(x)] < 20:
                    x += 3
            img = sim.dress(sim.crop(w, x, y), true, k * 0.02, rng)
            t0 = time.perf_counter()
            got = fc.read_minimap(img, now=k * 0.02 + (0 if void else 100))
            times.append(time.perf_counter() - t0)
            if got is None:
                misses += 1
                continue
            errs.append(abs((got - true + 180) % 360 - 180))
    errs = np.array(errs)
    print("facing: median error %.1f deg, 95%% %.1f deg, worst %.1f deg, %d/720 unsure, %.2f ms per read" % (
        np.median(errs), np.percentile(errs, 95), errs.max(), misses, 1000 * np.mean(times)))
    assert np.median(errs) < 2 and np.percentile(errs, 95) < 5 and errs.max() < 15 and misses < 10
    print("PASS facing")


if __name__ == "__main__":
    main()
