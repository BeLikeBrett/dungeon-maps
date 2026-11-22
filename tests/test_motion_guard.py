"""Impossible image peaks, poisoned scale pairs, ranged bosses, and arrow flicker."""
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

temp = tempfile.TemporaryDirectory()
os.environ.update(XDG_DATA_HOME=temp.name, XDG_STATE_HOME=temp.name, LOCALAPPDATA=temp.name)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
from dungeonmaps.odometry import Odometry, SIZE
from dungeonmaps.core import Core
from dungeonmaps.position import ParticleFilter

rgb = np.random.default_rng(1).integers(0, 256, (128, 128, 3), dtype=np.uint8)
odo = Odometry()
odo.max_step = 4.
assert np.array_equal(odo.step(rgb), np.zeros(2))
before = odo.offset.copy()
surface = np.full((2*SIZE-1, 2*SIZE-1), -1.)
surface[SIZE-1, SIZE-1+50] = .99
odo.ncc.surface = lambda *a: surface
assert odo.step(rgb) is None and odo.rejected == 1
assert np.array_equal(odo.offset, before)
assert np.array_equal(odo.step(rgb), np.zeros(2)), "rejected peak must not generate an opposite jump"
assert np.linalg.norm(odo.step(np.roll(rgb, 1, axis=1))) < 3

c = Core(info=lambda *a: None)
c.recording.enabled = False
c.walkmaps.get = lambda f: None
c.atlases.get = lambda f: None
c.pf.dungeon = 1
centre = c.data.to_world(213, .5, .5)
c.pf._init(213, centre, 1., 500, "marked")
f = dict(dungeon=1, map_open=1, shown_floor=1, radius4=240, indoors=1, zoom=3,
         lm_count=0, lm_kind=0, lm_floor=0, room=0)
c.fields = f
c.beacon = SimpleNamespace(rect=lambda p: (0, 0, 1002, 668), arrow_size=1., dot_size=1.)
c._minimap(rgb, (0, 0, 128, 128), f, 0.)
before = c.pf.est.copy()
c.odo.ncc.surface = lambda *a: surface
c._minimap(rgb, (0, 0, 128, 128), f, .05)
assert np.array_equal(c.pf.est, before) and np.array_equal(c.pf.raw, np.zeros(2))
assert not c.pf.motion_valid
for spread in (5.9, 6.1, 25.):
    c.pf.spread = spread
    assert c.view(.05)["me"]["guess"], "uncertain arrow must remain visible"
c.pf.spread = 1.
assert not c._confidence_lock(213, *centre, 0.)
assert not c._confidence_lock(213, *centre, .3)
assert c._confidence_lock(213, *centre, .6)
assert c.pf.observe(*c.pf.est, 3., verified=True)
assert not c.pf.guessed and not c.pf.motion_valid, "localization recovers without allowing unsafe scale training"

# Bad motion must not teach scale; a new real fix permits later valid pairs.
pf = c.pf
pf.calib.key = "test"
pf.raw = np.array([100., 0.])
pf.anchor = (213, 0., 0., 4.)
pf._init(213, (110., 0.), 1., 500, "marked")
assert pf.calib.get()[0] == 0 and pf.motion_valid
pf.raw = np.array([100., 0.])
pf._init(213, (220., 0.), 1., 500, "marked")
assert pf.calib.get()[0] > 0
prior = pf.calib.get()
pf.raw = np.array([100., 0.])
pf._init(213, (364.8, 0.), 1., 500, "marked")
assert pf.calib.get() == prior, "44.8% stretch must not poison global calibration"

# Boss start preserves a known player position, even for a distant spawn/patrol.
before = pf.est.copy()
pf.on_beacon(dict(f, lm_count=1, lm_kind=2, lm_floor=1, lm_u=3000, lm_v=3000))
assert np.array_equal(pf.est, before) and pf.source == "marked"
class NoMaps:
    def get(self, floor): return None
unknown = ParticleFilter(c.data, NoMaps())
unknown.on_beacon(dict(f, lm_count=1, lm_kind=2, lm_floor=1, lm_u=3000, lm_v=3000, active_boss=1))
assert not unknown.displayable and unknown.source != "boss", "a boss pin must not invent a player pose"
stale = ParticleFilter(c.data, NoMaps())
stale.on_beacon(dict(f, lm_count=9, lm_kind=3, lm_floor=1, lm_u=3000, lm_v=3000))
assert stale.est is None, "a cached mark from before startup is not a current player location"
stale.on_beacon(dict(f, lm_count=10, lm_kind=3, lm_floor=1, lm_u=3000, lm_v=3000))
assert stale.displayable and stale.source == "marked"
old_boss = ParticleFilter(c.data, NoMaps())
old_boss.on_beacon(dict(f, lm_count=19, lm_kind=2, lm_floor=1, lm_u=3000, lm_v=3000, active_boss=0))
assert old_boss.est is None, "a finished boss is not a startup position"
# Recovery also works while standing still; no repeated correction or walking ritual.
c.pending_match = None
assert not c._confirm_match(213, *centre)
assert not c._confirm_match(213, *centre)
c.pending_since -= 2.1
assert c._confirm_match(213, *centre)
print("PASS impossible peak rejection/rebase, no phantom reverse jump, calibration guards, ranged bosses, and visible uncertain arrows")
