"""Particle scale stays anchored to the fix-to-fix calibration (WC 2026-11-22 run).

Live, wall/route weighting selected short-stepping particles: the particle scale fell to 0.897
while every fix-to-fix stretch measured ~1.0, and each new stretch re-seeded that bias.
"""
import math
import os
import sys
import tempfile
from pathlib import Path

temp = tempfile.TemporaryDirectory()
os.environ.update(XDG_DATA_HOME=temp.name, XDG_STATE_HOME=temp.name, LOCALAPPDATA=temp.name)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import dungeonmaps.position as position
from dungeonmaps.data import Data
from dungeonmaps.position import ParticleFilter, ScaleCalibration


class NoMaps:
    def get(self, floor):
        return None


def make(seed=3):
    calib = ScaleCalibration(path=os.path.join(temp.name, "calibration-%d.json" % seed))
    calib.key = "wailingcaverns/i1z2"
    calib.table[calib.key] = (math.log(0.994), 0.044, 4)
    pf = ParticleFilter(Data(), NoMaps(), rng=np.random.default_rng(seed), calib=calib)
    pf.routes.get = lambda floor: None
    pf.dungeon = 5
    pf._init(279, (0.0, 0.0), 1.0, position.N, "marked")
    return pf


def walk_with_short_step_bias(pf, yards=800.0, step=0.1):
    """Every yard, favour particles that step short (what dead ends and corners did live)."""
    travelled = 0.0
    while travelled < yards:
        pf.move(step, 0.0)
        travelled += step
        if int(travelled / step) % 10 == 0:
            pf.w = pf.w * np.exp(-0.6 * pf.s)
            pf.w /= pf.w.sum()
            pf._resample_if_needed()
    return pf.scale


# 1. A new stretch starts from the calibration alone, never from the last run's surviving scales.
pf = make()
pf.s = np.full(len(pf.p), 0.897)
s = pf.scale_prior(20000)
assert abs(float(np.exp(np.log(s).mean())) - 0.994) < 0.003, s.mean()
assert abs(float(np.log(s).std()) - 0.044) < 0.003

# 2. Under sustained selection, the scale must stay within the calibrated uncertainty...
anchored = walk_with_short_step_bias(make())
assert anchored >= 0.994 * math.exp(-2.0 * 0.044) - 1e-3, anchored  # bounded at 2 sd (+ last yard)
# ... while the old behaviour (no reversion) collapses the way the live run did.
saved = position.SCALE_REVERT_YARDS
position.SCALE_REVERT_YARDS = 0.0
try:
    collapsed = walk_with_short_step_bias(make())
finally:
    position.SCALE_REVERT_YARDS = saved
assert collapsed < anchored - 0.03, (collapsed, anchored)

# 3. Reversion is batched per yard walked (move() runs every frame) and is idle while searching.
pf = make(5)
before = pf.s.copy()
for _ in range(9):
    pf.move(0.1, 0.0)
assert np.array_equal(pf.s, before) and abs(pf.scale_travel - 0.9) < 1e-9
pf.move(0.2, 0.0)
assert not np.array_equal(pf.s, before) and pf.scale_travel == 0.0
pf.searching = (279, None)
before = pf.s.copy()
pf.move(5.0, 0.0)
assert np.array_equal(pf.s, before)

print("PASS scale anchored to calibration: prior %.3f, biased walk %.3f (unanchored %.3f), batched per yard"
      % (0.994, anchored, collapsed))
