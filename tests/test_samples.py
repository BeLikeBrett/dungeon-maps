"""Private correction contributions: opt-out, retries, quotas, validation, real relay coexistence."""
import base64
import copy
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time

temp = tempfile.TemporaryDirectory()
os.environ.update(XDG_DATA_HOME=temp.name, XDG_STATE_HOME=temp.name, LOCALAPPDATA=temp.name)
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np
from dungeonmaps.samples import SampleUploader, prepare_sample
from websockets.sync.client import connect

spec = importlib.util.spec_from_file_location("sample_store", ROOT / "relay/samples.py")
server_samples = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server_samples)

rgb = np.random.default_rng(1).integers(0, 256, (192, 192, 3), dtype=np.uint8)
meta = dict(t=10., floor=213, position=[0., 0.], source="marked", walked=10., raw=[1., 2.],
            fields=dict(dungeon=1, mm_w=192, mm_h=192, room=0, n0=66, name_len=4, group=123, contribute=1))
frames = [(rgb, dict(meta, t=float(i))) for i in range(12)]
event = dict(kind="marked", floor=213, before=[10., 0.], fix=[0., 0.], sigma=4., error_yards=10.)
message = prepare_sample(frames, event, "a" * 32)
assert len(message["frames"]) == 6 and len(json.dumps(message)) <= 512 * 1024
fields = message["frames"][0]["meta"]["fields"]
assert not {"n0", "name_len", "group", "contribute"} & fields.keys()
assert server_samples.validate(message)["event"]["fix"] == [0., 0.]
store = server_samples.SampleStore(Path(temp.name) / "store")
assert store.save(message) == message["sample_id"]
assert store.save(message) == message["sample_id"]
assert len(list(store.folder.glob("*/*/*.json"))) == 1
for i in range(25):
    m = copy.deepcopy(message); m["sample_id"] = "%032x" % i
    store.window = 0  # quota tests span independent minute windows
    store.save(m)
assert len(list(store.folder.glob("*/*/*.json"))) == 20
for change in [dict(id="../escape"), dict(dungeon="../escape"), dict(frames=[]),
               dict(event=dict(event, fix=[float("nan"), 0.])),
               dict(frames=[dict(image=base64.b64encode(b"not a PNG").decode(), meta=meta)])]:
    try: server_samples.validate(dict(message, **change))
    except (ValueError, TypeError): pass
    else: raise AssertionError(change)
store.max_total = 1
store.window = 0
m = dict(message, sample_id="b" * 32)
store.save(m)
assert not list(store.folder.glob("*/*/*.json"))
u = SampleUploader(folder=Path(temp.name) / "outbox", url="ws://127.0.0.1:1")
assert not u.submit(frames, event) and not u.folder.exists()
u.allowed = True
assert u.submit(frames, event)
assert not u.flush_one() and len(list(u.folder.glob("*.json"))) == 1
u.allowed = False
assert not u.flush_one()

with socket.socket() as s:
    s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]
proc = subprocess.Popen([sys.executable, str(ROOT / "relay/relay.py"), "--port", str(port),
                         "--logs", "", "--samples", str(Path(temp.name) / "live")],
                        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
try:
    url = "ws://127.0.0.1:%d" % port
    for _ in range(50):
        try:
            with connect(url, open_timeout=1): pass
            break
        except OSError: time.sleep(.05)
    else: raise AssertionError(proc.stderr.read().decode())
    with connect(url) as one, connect(url) as two:
        for ws, name in [(one, "A"), (two, "B")]:
            ws.send(json.dumps(dict(t="join", room="12345678", name=name, app="dungeonmaps/1")))
        time.sleep(.05)
        u.url, u.allowed = url, True
        assert u.flush_one() and not list(u.folder.glob("*.json"))
        one.send(json.dumps(dict(t="pos", u=.2, v=.3)))
        got = json.loads(two.recv(timeout=3))
        assert got["name"] == "A" and got["u"] == .2
    assert len(list((Path(temp.name) / "live").glob("*/*/*.json"))) == 1
finally:
    proc.terminate(); proc.wait(timeout=5)
os.environ["DUNGEONMAPS_SAMPLES"] = "off"
assert SampleUploader(url="ws://example.invalid").url is None
os.environ.pop("DUNGEONMAPS_SAMPLES")
os.environ["DUNGEONMAPS_RELAY"] = "off"
assert SampleUploader().url is None
print("PASS sample privacy, opt-outs, retry/ack, 20-per-install-per-dungeon retention, total cap, and live party relay coexistence")
