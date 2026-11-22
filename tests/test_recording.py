"""Local evidence is bounded, lossless, replayable, and never a full screen."""
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

temp = tempfile.TemporaryDirectory()
os.environ.update(XDG_DATA_HOME=temp.name, XDG_STATE_HOME=temp.name, LOCALAPPDATA=temp.name)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
from PIL import Image
from dungeonmaps.core import Core
from dungeonmaps.recording import Recorder
from dungeonmaps import recording
from dungeonmaps.odometry import Odometry

c = Core(info=lambda *a: None)
c.pf.dungeon = 1
c.pf._init(213, (0., 0.), 1., 500, "marked")
fields = dict(dungeon=1, lm_count=1, lm_kind=3, lm_floor=1, room=0, indoors=1,
              zoom=3, radius4=240, mm_w=64, mm_h=64, lm_u=0, lm_v=0)
rgb = np.random.default_rng(1).integers(0, 256, (64, 64, 3), dtype=np.uint8)
for i in range(5):
    c.recording.add(rgb, fields, c.pf, float(i), .99)
motion = Odometry(); motion.max_step = 2.
motion.step(rgb)
assert motion.step(np.roll(rgb, 15, axis=1)) is None
c.recording.add_case(motion.rejection, 4., 1., .05)
c._on_fix(213, (0., 0.), (20., 0.), "marked", 4.)
c.recording.worker.join(5)
files = list(Path(c.recording.folder).rglob("trace-*.zip"))
assert len(files) == 1 and not list(Path(c.recording.folder).rglob("*.tmp"))
assert files[0].parent.parent.name == "ragefire"
c.recording.journal.join()
journals = list(Path(c.recording.folder).rglob("session-*.jsonl"))
assert len(journals) == 1
rows = [json.loads(line) for line in journals[0].read_text().splitlines()]
assert len(rows) == 5 and all(row["dungeon_key"] == "ragefire" for row in rows)
with zipfile.ZipFile(files[0]) as z:
    m = json.loads(z.read("manifest.json"))
    assert m["event"]["error_yards"] == 20 and len(m["frames"]) == 5
    assert m["motion_cases"] == 1 and "motion/00.npz" in z.namelist()
    got = np.array(Image.open(io.BytesIO(z.read("minimap/0000.png"))))
    assert np.array_equal(got, rgb)
result = subprocess.run([sys.executable, "tools/replay_trace.py", str(files[0])],
                        text=True, capture_output=True, check=True)
assert "Reprocessed distance" in result.stdout, result.stdout
assert "rejected True" in result.stdout, result.stdout
assert not c.recording.trigger("spam", {}, now=c.recording.last_saved + 1)
recording.MAX_RAM = 2 * rgb.nbytes
r = Recorder(folder=str(Path(temp.name) / "bounded"))
for i in range(10): r.add(rgb, fields, c.pf, float(i), .9)
assert len(r.frames) == 2 and r.bytes <= recording.MAX_RAM
recording.MAX_FILES = 2
for i in range(3):
    assert r.trigger("test", {}, now=100 + 11*i)
    r.worker.join(5)
assert len(list(Path(r.folder).rglob("trace-*.zip"))) == 2
r.clear()
assert not r.frames and r.bytes == 0
print("PASS local lossless minimap evidence, correction trigger, replay, throttling, RAM and disk limits")
