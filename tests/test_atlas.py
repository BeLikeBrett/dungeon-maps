"""The minimap atlas, end to end through the real tracker (the synthetic dungeon of test_pipeline):

  1. odometry drift (a slowly wandering error added to every minimap step, like real minimaps give)
     and no walkable-path map. A first run with a Shift+click fix every 20 s teaches the atlas (each fix
     re-pastes the stretch before it, corrected); on the next run, with no fixes at all, the drifting
     walk is held on the map by it (the same walk without the atlas drifts away). Within a single run
     without fixes the atlas must at least not make things worse;
  2. a second session: with the atlas saved, a tracker started in the middle of the dungeon with no
     starting point at all finds you from the minimap alone;
  3. fix-to-fix scale calibration: two fixes far apart teach the scale error.
"""
import os as _os, tempfile as _tempfile  # noqa: E401
if not _os.environ.get("DUNGEONMAPS_TEST_ISOLATED"):
    _tmp = _tempfile.mkdtemp(prefix="dungeonmaps-test-")
    _os.environ.update(XDG_DATA_HOME=_tmp, XDG_STATE_HOME=_tmp, LOCALAPPDATA=_tmp, DUNGEONMAPS_TEST_ISOLATED="1")

import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
import test_pipeline as tp  # noqa: E402
from dungeonmaps import atlas as atlas_mod  # noqa: E402
from dungeonmaps import position  # noqa: E402


def long_walk(use_atlas, seconds=150, seed=4, drift=True, mark_every=None):
    game = tp.FakeGame(seed=seed)
    t = tp.make_tracker(game, walk=False)
    if not use_atlas:
        t.core.atlases.get = lambda floor: None
    # drift: a bias that wanders (crop pixels per step) added to every odometry step
    rng = np.random.default_rng(9)
    bias = np.zeros(2)
    step = t.core.odo.step

    def drifting(img):
        nonlocal bias
        d = step(img)
        if d is not None:
            bias = np.clip(bias + rng.normal(0, 0.002, 2), -0.02, 0.02)
            d = d + bias
        return d
    if drift:
        t.core.odo.step = drifting
    errs = []
    now = 0.0
    for k in range(int(seconds)):
        if mark_every and k and k % mark_every == 0:   # you Shift+click where you stand
            game.lm_u, game.lm_v = game.data.to_map(tp.RFC, game.N, game.W)
            game.lm_count, game.lm_kind = game.lm_count + 1, 3
        now, last, _ = tp.run(t, game, 1.0, now)
        errs.append(last)
    return t, game, np.array(errs), now


def main():
    # 1. drift with and without the atlas
    def report(label, t, errs):
        late = errs[len(errs) // 2:]
        st = t.core.stats()
        print("%s: 2nd half median %.1f yards off, worst %.1f (locks %d, jumps %d, atlas %s yd2, scale %.3f)" % (
            label, np.median(late), late.max(), st["atlas_locks"], st["atlas_jumps"], st["atlas_yd2"],
            st["scale"]))
        return float(np.median(late))
    off = report("drifting, no atlas", *long_walk(False)[:3:2])
    t, _, errs, _ = long_walk(True)
    first = report("drifting, first run (atlas learned as it goes)", t, errs)
    assert first < 1.15 * off, (first, off)
    for d in os.listdir(atlas_mod.CACHE):
        os.remove(os.path.join(atlas_mod.CACHE, d))
    t, _, errs, _ = long_walk(True, mark_every=20)
    report("first run, drifting, Shift+click every 20 s", t, errs)
    t.core.atlases.save(background=False)
    t, _, errs, _ = long_walk(True)
    again = report("drifting, next run with that atlas", t, errs)
    assert again < 4 and again < 0.5 * off, (again, off)

    # 2. save the atlas; a new tracker started mid-dungeon (no entrance, no fix) finds you by the minimap
    t.core.atlases.save(background=False)
    assert os.path.exists(t.core.atlases.path(tp.RFC))
    game2 = tp.FakeGame(seed=21, radius_bias=1.10)
    game2.lm_count, game2.lm_kind = 0, 0
    for _ in range(int(20 / tp.DT)):   # start somewhere else than the entrance
        game2.walk(tp.DT)
    t2 = tp.make_tracker(game2, walk=False)
    found = None
    now2 = 0.0
    for k in range(40):
        now2, last, _ = tp.run(t2, game2, 0.5, now2)
        if t2.core.pf.found and found is None:
            found = (k + 1) * 0.5
        if found is not None and (k + 1) * 0.5 >= found + 3:
            break
    print("second session, no starting point: found by the atlas after %s s, then %.1f yards off (source %s)" % (
        found, last, t2.core.pf.source))
    assert found is not None and found <= 8 and last < 5, (found, last)

    # 3. fix-to-fix calibration: the scale error is learned from two fixes 60+ yards apart
    cal = position.ScaleCalibration(path=os.path.join(_os.environ["XDG_STATE_HOME"], "calib-test.json"))
    pf = position.ParticleFilter(t.core.data, t.core.walkmaps, rng=np.random.default_rng(1), calib=cal)
    pf.dungeon = 1
    floor = tp.RFC
    pf._init(floor, (0.0, 0.0), 1.0, position.N, "marked")
    for k in range(1, 4):            # 80 measured yards north, truly 88 (the minimap scale is 10 % low)
        for _ in range(80):
            pf.move(1.0, 0.0)
        pf._init(floor, (88.0 * k, 0.0), 1.0, position.N, "marked")
        print("calibration after %d 88-yard stretches: x%.3f (truth x1.100)" % (k, math.exp(cal.get()[0])))
    assert abs(math.exp(cal.get()[0]) - 1.10) < 0.04   # (each fix is only good to a few yards)
    assert atlas_mod.RES == 1.0
    print("PASS atlas")


if __name__ == "__main__":
    main()
