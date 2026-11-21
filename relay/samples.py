"""Private, bounded correction dataset. Anonymous installation IDs, no public read API."""
import base64
import json
import math
import os
from pathlib import Path
import re
import struct
import tempfile
import threading
import time

MAX_MESSAGE = 512 * 1024
MAX_PER_DUNGEON = 20
MAX_TOTAL = 2 * 1024 ** 3
HEX32 = re.compile(r"^[0-9a-f]{32}$")
DUNGEON = re.compile(r"^[a-z0-9_]{1,48}$")
FIELD_NAMES = {"version", "dungeon", "room", "zoom", "indoors", "rotate", "radius4",
               "mm_w", "mm_h", "active_boss", "boss_mask", "lm_kind", "lm_count"}
META_NAMES = {"t", "floor", "position", "spread", "uncertainty", "trust", "scale", "source",
              "odometry_score", "route_checks", "route_used", "walked", "raw", "odo_yards"}


def numeric(v):
    if v is None:
        return None
    if isinstance(v, (float, int)) and not isinstance(v, bool) and math.isfinite(v) and abs(v) <= 1e12:
        return v
    if isinstance(v, list) and len(v) == 2:
        return [numeric(x) for x in v]
    raise ValueError("invalid number")


def validate(m):
    if not isinstance(m, dict) or m.get("t") != "sample" or m.get("app") != "dungeonmaps/1":
        raise ValueError("bad protocol")
    for key in ("id", "sample_id"):
        if not isinstance(m.get(key), str) or not HEX32.fullmatch(m[key]):
            raise ValueError("bad id")
    if not isinstance(m.get("dungeon"), str) or not DUNGEON.fullmatch(m["dungeon"]):
        raise ValueError("bad dungeon")
    event = m.get("event")
    if not isinstance(event, dict) or event.get("kind") != "marked":
        raise ValueError("manual corrections only")
    event = {k: numeric(event[k]) for k in ("floor", "before", "fix", "sigma", "error_yards") if k in event}
    if not isinstance(event.get("fix"), list) or not isinstance(event.get("floor"), int):
        raise ValueError("missing correction")
    if any(not isinstance(v, (float, int)) for v in event["fix"]) or not 0 < event["floor"] < 2 ** 31:
        raise ValueError("invalid correction")
    if not isinstance(event.get("sigma"), (float, int)) or not 0 < event["sigma"] <= 100:
        raise ValueError("invalid correction uncertainty")
    event["kind"] = "marked"
    frames = m.get("frames")
    if not isinstance(frames, list) or not 1 <= len(frames) <= 6:
        raise ValueError("bad frame count")
    clean_frames = []
    for frame in frames:
        if not isinstance(frame, dict) or not isinstance(frame.get("image"), str) or len(frame["image"]) > 100_000:
            raise ValueError("bad image")
        raw = base64.b64decode(frame["image"], validate=True)
        if raw[:8] != b"\x89PNG\r\n\x1a\n" or raw[12:16] != b"IHDR" or len(raw) < 33:
            raise ValueError("PNG required")
        if struct.unpack(">II", raw[16:24]) != (128, 128):
            raise ValueError("minimap thumbnail required")
        meta = frame.get("meta")
        if not isinstance(meta, dict) or not isinstance(meta.get("fields"), dict):
            raise ValueError("bad context")
        clean = {k: numeric(meta[k]) for k in META_NAMES - {"source"} if k in meta}
        clean["source"] = str(meta.get("source", ""))[:40]
        clean["fields"] = {k: numeric(v) for k, v in meta["fields"].items() if k in FIELD_NAMES}
        clean_frames.append({"image": frame["image"], "meta": clean})
    digest = m.get("data_sha256", "")
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ValueError("missing data version")
    return {"t": "sample", "app": "dungeonmaps/1", "format": 1, "id": m["id"],
            "sample_id": m["sample_id"], "dungeon": m["dungeon"], "version": str(m.get("version", ""))[:24],
            "data_sha256": digest, "event": event, "frames": clean_frames}


class SampleStore:
    def __init__(self, folder, max_total=MAX_TOTAL):
        self.folder = Path(folder)
        self.max_total = max_total
        self.lock = threading.Lock()
        self.window = 0
        self.count = 0
        self.clients = {}

    def save(self, message):
        sample = validate(message)
        body = json.dumps(sample, allow_nan=False, separators=(",", ":")).encode()
        if len(body) > MAX_MESSAGE:
            raise ValueError("sample too large")
        with self.lock:
            now = time.time()
            minute = int(now // 60)
            if minute != self.window:
                self.window, self.count, self.clients = minute, 0, {}
            client = sample["id"]
            if self.count >= 60 or self.clients.get(client, 0) >= 8:
                raise ValueError("rate limited")
            self.count += 1
            self.clients[client] = self.clients.get(client, 0) + 1
            folder = self.folder / sample["dungeon"] / client
            folder.mkdir(parents=True, exist_ok=True, mode=0o700)
            path = folder / (sample["sample_id"] + ".json")
            if path.exists():
                return sample["sample_id"]  # idempotent retry after an acknowledgement was lost
            temp = None
            try:
                with tempfile.NamedTemporaryFile(dir=folder, suffix=".tmp", delete=False) as f:
                    temp = f.name
                    f.write(body)
                os.replace(temp, path)
                temp = None
            finally:
                if temp:
                    os.unlink(temp)
            files = sorted(folder.glob("*.json"), key=lambda p: p.stat().st_mtime)
            for old in files[:-MAX_PER_DUNGEON]:
                old.unlink()
            all_files = sorted(self.folder.glob("*/*/*.json"), key=lambda p: p.stat().st_mtime)
            total = sum(p.stat().st_size for p in all_files)
            for old in all_files:
                if total <= self.max_total:
                    break
                total -= old.stat().st_size
                old.unlink()
            return sample["sample_id"]
