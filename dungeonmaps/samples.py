"""Compact manual-correction contributions, retried from a bounded local outbox."""
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import threading
import time

from PIL import Image

from . import __version__
from .data import Data, HERE, user_dir
from .share import PROTOCOL, relay_url
from .telemetry import install_id

MAX_MESSAGE = 512 * 1024
SAFE_FIELDS = {"version", "dungeon", "room", "zoom", "indoors", "rotate", "radius4",
               "mm_w", "mm_h", "active_boss", "boss_mask", "lm_kind", "lm_count"}
SAFE_META = {"t", "floor", "position", "spread", "uncertainty", "trust", "scale", "source",
             "odometry_score", "route_checks", "route_used", "walked", "raw", "odo_yards", "fields"}


def prepare_sample(frames, event, identity):
    """No character names, GUIDs, group hashes, full screens, or local file paths."""
    # Longer local diagnostics do not expand the community contribution window.
    frames = [f for f in frames if f[1]["t"] >= frames[-1][1]["t"] - 60]
    dungeon_index = frames[-1][1]["fields"]["dungeon"]
    data = Data()
    if not 0 < dungeon_index <= len(data.dungeons) or event.get("kind") != "marked":
        raise ValueError("a manual dungeon correction is required")
    dungeon = data.dungeons[dungeon_index - 1]["key"]
    selected = sorted({round(i * (len(frames) - 1) / 5) for i in range(6)})
    out = []
    for i in selected:
        rgb, meta = frames[i]
        if meta["floor"] != event["floor"]:
            continue
        meta = {k: v for k, v in meta.items() if k in SAFE_META}
        meta["fields"] = {k: v for k, v in meta["fields"].items() if k in SAFE_FIELDS}
        meta["t"] -= frames[0][1]["t"]
        buf = io.BytesIO()
        Image.fromarray(rgb).resize((128, 128), Image.Resampling.BOX).save(buf, format="PNG")
        out.append({"meta": meta, "image": base64.b64encode(buf.getvalue()).decode("ascii")})
    if not out:
        raise ValueError("no frames of the corrected floor")
    stamp = json.dumps([identity, event, frames[-1][1]["t"]], sort_keys=True)
    message = {"t": "sample", "app": PROTOCOL, "format": 1, "id": identity,
               "sample_id": hashlib.sha256(stamp.encode()).hexdigest()[:32], "dungeon": dungeon,
               "version": __version__, "event": event, "frames": out,
               "data_sha256": hashlib.sha256(Path(HERE, "data", "dungeons.json").read_bytes()).hexdigest()}
    if len(json.dumps(message).encode()) > MAX_MESSAGE:
        raise ValueError("sample too large")
    return message


class SampleUploader:
    def __init__(self, folder=None, url=None, connect=None, log=lambda *a: None):
        self.folder = Path(folder or os.path.join(user_dir("state"), "samples-pending"))
        off = any(os.environ.get(k, "").lower() in ("off", "0", "no")
                  for k in ("DUNGEONMAPS_SAMPLES", "DUNGEONMAPS_LOGS", "DUNGEONMAPS_RECORDING"))
        self.url = None if off else (url or relay_url())
        self.id, self.connect, self.log = install_id(), connect, log
        self.allowed = False
        self.worker = None
        self.wake = threading.Event()
        self.lock = threading.Lock()

    def set_allowed(self, allowed):
        value = bool(allowed) and bool(self.url)
        changed = value != self.allowed
        self.allowed = value
        if self.allowed and self.worker is None:
            self.worker = threading.Thread(target=self._run, daemon=True, name="correction-samples")
            self.worker.start()
        if changed:
            self.wake.set()

    def submit(self, frames, event):
        if not self.allowed or event.get("kind") != "marked":
            return False
        message = prepare_sample(frames, event, self.id)
        with self.lock:
            return self._save(message)

    def _save(self, message):
        if not self.allowed:
            return False
        self.folder.mkdir(parents=True, exist_ok=True)
        target = self.folder / (message["dungeon"] + "-" + message["sample_id"] + ".json")
        with tempfile.NamedTemporaryFile(dir=self.folder, suffix=".tmp", mode="w", delete=False) as f:
            temp = f.name
            json.dump(message, f, allow_nan=False, separators=(",", ":"))
        os.replace(temp, target)
        files = sorted(self.folder.glob(message["dungeon"] + "-*.json"), key=lambda p: p.stat().st_mtime)
        for old in files[:-20]:
            old.unlink(missing_ok=True)
        files = sorted(self.folder.glob("*.json"), key=lambda p: p.stat().st_mtime)
        total = sum(p.stat().st_size for p in files)
        for old in files:
            if total <= 40 * 1024 * 1024:
                break
            total -= old.stat().st_size
            old.unlink(missing_ok=True)
        self.wake.set()
        return True

    def flush_one(self):
        if not self.allowed or not self.url:
            return False
        try:
            with self.lock:
                files = sorted(self.folder.glob("*.json"))
                if not files:
                    return False
                path = files[0]
                message = json.loads(path.read_text())
            if self.connect:
                ws = self.connect(self.url)
            else:
                from websockets.sync.client import connect
                ws = connect(self.url, open_timeout=10, close_timeout=2, max_size=4096,
                             user_agent_header="DungeonMaps")
            try:
                if not self.allowed:
                    return False
                ws.send(json.dumps(message, separators=(",", ":")))
                ack = json.loads(ws.recv(timeout=10))
                if ack.get("t") != "sample_ack" or not ack.get("ok") or ack.get("sample_id") != message["sample_id"]:
                    return False
                with self.lock:
                    path.unlink(missing_ok=True)
                self.log("correction sample uploaded:", message["dungeon"], message["sample_id"])
                return True
            finally:
                ws.close()
        except Exception as e:
            self.log("correction upload pending:", type(e).__name__)
            return False

    def _run(self):
        while True:
            self.wake.wait(30)
            self.wake.clear()
            # One per 10 seconds; server also rate-limits and retains only 20 per bucket.
            if self.flush_one():
                time.sleep(10)
                self.wake.set()
