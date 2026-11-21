"""Regression: an interrupted map-cache write must not crash capture and reopen the picker."""
import os as _os, tempfile as _tempfile  # noqa: E401
if not _os.environ.get("DUNGEONMAPS_TEST_ISOLATED"):  # never touch the real atlas, calibration or caches
    _tmp = _tempfile.mkdtemp(prefix="dungeonmaps-test-")
    _os.environ.update(XDG_DATA_HOME=_tmp, XDG_STATE_HOME=_tmp, LOCALAPPDATA=_tmp, DUNGEONMAPS_TEST_ISOLATED="1")

from pathlib import Path
import os
import sys
import tempfile
from unittest.mock import patch

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dungeonmaps import linux, walkmap
from dungeonmaps.data import Data, MAP_H, MAP_W

with tempfile.TemporaryDirectory() as directory, patch.object(walkmap, 'CACHE', directory):
    wm = walkmap.WalkMaps(Data())
    path = Path(wm.art_path(213))
    # Reproduce a real PNG with an intact header but missing pixel data.
    from io import BytesIO
    encoded = BytesIO()
    Image.new('RGB', (MAP_W, MAP_H), 'tan').save(encoded, format='PNG')
    path.write_bytes(encoded.getvalue()[:60])
    assert wm.get(213) is None and not path.exists()
    assert not wm.has_art(213), 'damaged cache prevents recapture'
    art = np.full((MAP_H, MAP_W, 3), 80, dtype=np.uint8)
    wm.save_art(213, art)
    with Image.open(path) as image:
        image.load()
        assert image.size == (MAP_W, MAP_H)
    before = path.read_bytes()
    # Failed writes preserve the previously complete image, and clean up their temp files.
    with patch.object(Image.Image, 'save', side_effect=OSError('simulated interrupted write')):
        try:
            wm.save_art(213, art)
        except OSError:
            pass
        else:
            raise AssertionError('write failure not exercised')
    assert path.read_bytes() == before
    assert set(os.listdir(directory)) <= {'213.png', '213-walk.png'}

class Gst:
    class MessageType:
        ERROR, EOS = 1, 2

class Message:
    type = Gst.MessageType.EOS

class Bus:
    def pop_filtered(self, flags): return Message()

class Pipeline:
    def get_bus(self): return Bus()

portal = linux.PortalWindow()
portal.pipeline, portal.Gst, portal.state = Pipeline(), Gst, 'running'
portal.stop = lambda: setattr(portal, 'pipeline', None)
with patch.object(linux, 'info'):
    portal.check()
assert portal.state == 'failed', 'stream failure would reopen picker'
print('PASS cache corruption recovery, atomic writes, and no portal reprompt on stream failure')
