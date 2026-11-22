"""WC geometry must remain instance-only, survive atlas updates, and leave other maps alone."""
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace

import numpy as np
from PIL import Image

temp = tempfile.TemporaryDirectory()
os.environ.update(XDG_DATA_HOME=temp.name, XDG_STATE_HOME=temp.name, LOCALAPPDATA=temp.name,
                  DUNGEONMAPS_RECORDING='off', DUNGEONMAPS_SAMPLES='off')
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dungeonmaps import walkmap
from dungeonmaps.core import Core
from dungeonmaps.data import Data, MAP_H, MAP_W

data = Data()
maps = walkmap.WalkMaps(data)
assert maps.art_path(279).endswith('279-instance-v2.png')
assert maps.art_path(213).endswith('213.png')
assert maps.art_path(1029991).endswith('1029991.png')
# An old parchment cache exists but must never define WC's walls anymore.
Image.new('RGB', (MAP_W, MAP_H), 'white').save(Path(walkmap.CACHE)/'279.png')
wc = maps.get(279)
assert wc is not None and maps.has_art(279)
weights = wc.weight.copy()
# The removed approach chamber's centre is not instance floor.
assert weights[560, 350] < .2
# Latest new-map manual references remain on their actual instance passage.
for u,v in [(439/1002,339/668),(435/1002,343/668),(438/1002,361/668)]:
    assert wc.weights([u],[v])[0] > .8, (u,v)
maps.add_floor(279, np.ones((MAP_H,MAP_W), bool))
assert np.array_equal(wc.weight, weights), 'texture coverage turned walls into WC paths'
# Existing atlas expansion still operates for every other dungeon.
base = np.zeros((MAP_H,MAP_W), bool); base[100:140,100:140] = True
maps.add_floor(213, base)
rfc = maps.get(213)
extra = base.copy(); extra[200:240,200:240] = True
maps.add_floor(213, extra)
assert rfc.weight[220,220] == 1
core = Core(info=lambda *a:None)
core.atlases.floor_on_map = lambda *a: (_ for _ in ()).throw(AssertionError('WC spawned atlas-to-floor work'))
core._walk_from_atlas(279)
mask = np.array(Image.open(ROOT/'dungeonmaps/data/wailing_instance_walk.png'))
assert mask.shape == (MAP_H,MAP_W) and set(np.unique(mask)) <= {0,255}
assert 10000 < np.count_nonzero(mask) < MAP_H*MAP_W*.65
print('PASS WC instance geometry, no stale parchment, no atlas path expansion, latest manual points, other maps unchanged')

# A camera zoom transition is a rebase, not a player movement. This profile
# exists only on WC, so the change cannot delay another dungeon's minimap.
f = dict(dungeon=5,lm_count=0,lm_kind=0,lm_floor=0,room=0,indoors=1,zoom=3,
         radius4=240,mm_w=128,mm_h=128,map_open=0,shown_floor=1,rotate=0)
c = Core(info=lambda *a:None)
c.recording.enabled=False
c._atlas=lambda *a:None
c.facing.read_minimap=lambda *a:None
c.pf.dungeon=5;c.pf._init(279,(0.,0.),1.,500,'marked')
rgb=np.random.default_rng(9).integers(0,256,(128,128,3),dtype=np.uint8)
def beacon(fields):
    return SimpleNamespace(fields=fields,name='Fixture',colour='#ffffff',rect=lambda key:(0,0,128,128))
c._frame(beacon(f),lambda rect:rgb,0.,None)
step=c.odo.step
c.odo.step=lambda *a:(_ for _ in ()).throw(AssertionError('zoom animation entered odometry'))
f=dict(f,zoom=4,radius4=160)
c._frame(beacon(f),lambda rect:rgb,.1,None)
c._frame(beacon(f),lambda rect:rgb,.3,None)
assert abs(c.minimap_settle_until - .45) < 1e-9 and np.array_equal(c.pf.raw,[0,0])
c.odo.step=step
c._frame(beacon(f),lambda rect:rgb,.5,None)
assert c.odo.key is not None and np.array_equal(c.pf.raw,[0,0])
assert not c.pf.motion_valid,'missing zoom-transition movement must not calibrate scale'
# Entering another dungeon clears a WC-specific pending hold immediately.
c.minimap_settle_until=100.
c._frame(beacon(dict(f,dungeon=1)),lambda rect:rgb,.6,None)
assert c.minimap_settle_until < 0
print('PASS WC zoom animation is excluded and rebased; other dungeon capture is unaffected')
