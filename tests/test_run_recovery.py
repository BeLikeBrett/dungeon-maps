"""Regressions from the Nov 22 run: blocked minimaps, stalls, scoped learning, large zoomed floors."""
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

root = tempfile.TemporaryDirectory()
os.environ.update(XDG_DATA_HOME=root.name, XDG_STATE_HOME=root.name, LOCALAPPDATA=root.name)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
from PIL import Image, ImageFilter
from dungeonmaps.core import Core
from dungeonmaps.position import ScaleCalibration
from dungeonmaps.atlas import FloorAtlas
from dungeonmaps.odometry import _mask

c = Core(info=lambda *a: None)
c.recording.enabled = False
c.atlases.get = lambda f: None
c.walkmaps.get = lambda f: None
c.pf.dungeon = 1
c.pf._init(213, (0., 0.), 1., 500, 'marked')
f = dict(dungeon=1, lm_count=0, lm_kind=0, lm_floor=0, room=0, indoors=1,
         zoom=3, radius4=240, mm_w=128, mm_h=128, map_open=0, shown_floor=1, rotate=0)
rgb = np.random.default_rng(1).integers(0, 256, (128, 128, 3), np.uint8)
original = c.odo.step
c.odo.step = lambda image: (_ for _ in ()).throw(AssertionError('UI popup entered odometry'))
c._minimap(rgb, (0, 0, 128, 128), dict(f, minimap_blocked=1), 0.)
assert np.array_equal(c.pf.raw, [0, 0]) and c.odo.key is None
c.odo.step = original
c._minimap(rgb, (0, 0, 128, 128), f, 0.)
recoveries = []
c._atlas = lambda now, ypp: recoveries.append(now)
c.odo.ncc.surface = lambda *a: np.full((255, 255), -1.)
c._minimap(rgb, (0, 0, 128, 128), f, .2)
assert .2 in recoveries, 'atlas recovery must work while odometry is failing'
c._minimap(rgb, (0, 0, 128, 128), f, 1.2)
assert c.odo.key is None and not c.pf.motion_valid and c.pf.guessed
assert np.array_equal(c.pf.raw, [0, 0]), 'rebasing must not invent displacement'
c._minimap(rgb, (0, 0, 128, 128), f, 1.3)
assert c.odo.key is not None and np.array_equal(c.pf.raw, [0, 0])
c._minimap(np.zeros_like(rgb), (0, 0, 128, 128), f, 1.4)
assert not c.odo.gray.any(), 'recovery must not reuse a stale picture on blank frames'

cal = ScaleCalibration(path=str(Path(root.name)/'calibration.json'))
cal.table['i1z3'] = (.02, .02, 5)
cal.key = 'ruinsoflordaeron/i1z3'
assert cal.get() == (.02, .1)
cal.add(1.1, .03)
assert cal.table['i1z3'] == (.02, .02, 5)
cal.key = 'ragefire/i1z3'
assert cal.get() == (.02, .1), 'another dungeon must not inherit Lordaeron measurements'
c.pf.calib.key = 'ragefire/i1z3'
c.pf.raw[:] = 100
c._frame(SimpleNamespace(fields=dict(f, zoom=4), name='Test', colour='#ffffff', rect=lambda p: None),
         lambda rect: None, 2., None)
assert c.pf.calib.key == 'ragefire/i1z4' and c.pf.anchor is None
assert np.array_equal(c.pf.raw, [0, 0]), 'a mixed-zoom stretch cannot train a single profile'

class Atlas:
    def paste(self, *args, **kwargs): raise AssertionError('inconsistent path taught the atlas')
c.atlases.get = lambda floor: Atlas()
c.pf.anchor = (213, 0., 0., 4.)
c.pf.motion_valid = True
c.pf.raw[:] = [100., 0.]
c.trail = [(0., 213, 0., 0., 1., np.ones((128, 128), np.uint8))]
c.odo_yards = 200.
c.pf._init(213, (250., 0.), 1., 500, 'marked')
assert not c.pf.stretch_valid and c.pf.motion_valid and c.pf.source == 'marked'

# Previously span > 1100 silently returned None at close zoom, regardless of match quality.
rng = np.random.default_rng(8)
a = FloorAtlas(213, 0, 0, 900, 900)
a.sum[:] = np.asarray(Image.fromarray(rng.integers(20, 230, (900, 900), np.uint8))
                      .filter(ImageFilter.GaussianBlur(2))) * 3.
a.wt[:] = 1
truth = (-580., -420.)
gray, mask = a.render(*truth, .7, 128)
mask *= _mask(128)
r = a.locate_anywhere(gray, mask, .7)
assert r and np.linalg.norm(np.asarray(r[:2])-truth) < 3 and r[2] > .8 and r[2]-r[3] > .15, r
print('PASS popup exclusion, stalled matching recovery, dungeon calibration isolation, bad-path learning guard and coarse-to-fine search')
