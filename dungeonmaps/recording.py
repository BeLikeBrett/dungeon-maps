"""Bounded local evidence for tracking problems. Never uploads pictures."""

from collections import deque
import io
import json
import math
import os
from pathlib import Path
import queue
import tempfile
import threading
import time
import zipfile

import numpy as np
from PIL import Image

from . import __version__
from .data import user_dir
from .samples import SampleUploader

MAX_RAM = 128 * 1024 * 1024
MAX_DISK = 2 * 1024 * 1024 * 1024
MAX_FILES = 200
HISTORY_SECONDS = 180


class Recorder:
    def __init__(self, folder=None, log=lambda *a: None):
        self.folder = folder or os.path.join(user_dir("state"), "recordings")
        self.log = log
        self.enabled = os.environ.get("DUNGEONMAPS_RECORDING", "on") != "off"
        self.frames = deque()
        self.cases = deque(maxlen=12)
        self.bytes = 0
        self.last_frame = self.last_saved = -math.inf
        self.busy = False
        self.worker = None
        self.upload = SampleUploader(log=log)
        self.session = "session-%s-%d" % (time.strftime("%Y%m%d-%H%M%S"), time.time_ns())
        self.journal = queue.Queue(maxsize=128)
        self.journal_worker = None
        self.last_journal = -math.inf
        self.prune_lock = threading.Lock()

    def _directory(self, dungeon):
        return os.path.join(self.folder, dungeon, time.strftime("%Y-%m-%d"))

    def _prune(self):
        with self.prune_lock:
            paths = list(Path(self.folder).rglob("trace-*.zip"))
            paths += list(Path(self.folder).rglob("session-*.jsonl"))
            # Preserve manual correction clips and compact session timelines
            # ahead of automatic motion snapshots, within the same total cap.
            files = sorted((2 if p.suffix == ".jsonl" else 1 if "-marked.zip" in p.name else 0,
                            p.stat().st_mtime, p, p.stat().st_size) for p in paths)
            total = sum(s for _, _, _, s in files)
            count = sum(p.suffix == ".zip" for _, _, p, _ in files)
            for _, _, path, size in files:
                if total <= MAX_DISK and count <= MAX_FILES:
                    break
                if count > MAX_FILES and total <= MAX_DISK and path.suffix != ".zip":
                    continue
                path.unlink(missing_ok=True)
                total -= size
                count -= path.suffix == ".zip"

    def _journal(self, meta):
        if self.journal_worker is None:
            def write():
                count = 0
                while True:
                    directory, row = self.journal.get()
                    try:
                        os.makedirs(directory, exist_ok=True)
                        with open(os.path.join(directory, self.session + ".jsonl"), "a", encoding="utf-8") as fh:
                            fh.write(json.dumps(row, allow_nan=False) + "\n")
                        count += 1
                        if count % 60 == 0:
                            self._prune()
                    except (OSError, ValueError) as e:
                        self.log("session evidence unavailable:", repr(e))
                    finally:
                        self.journal.task_done()
            self.journal_worker = threading.Thread(target=write, daemon=True)
            self.journal_worker.start()
        try:
            self.journal.put_nowait((self._directory(meta["dungeon_key"]), meta))
        except queue.Full:
            pass  # disk trouble must never stall capture/gameplay

    def clear(self):
        self.frames.clear()
        self.cases.clear()
        self.bytes = 0
        self.last_frame = -math.inf

    def add_case(self, case, now, yards_per_pixel, elapsed):
        if self.enabled and case is not None:
            self.cases.append((now, dict(case, yards_per_pixel=float(yards_per_pixel), elapsed=float(elapsed))))

    def add(self, img, fields, pf, now, score, force=False, accepted=None):
        if not self.enabled or (not force and now - self.last_frame < .5):
            return
        self.last_frame = now
        # Only the minimap rectangle, at its native resolution; never the desktop.
        rgb = np.ascontiguousarray(img[..., :3], dtype=np.uint8).copy()
        meta = {"t": now, "fields": dict(fields), "floor": pf.floor,
                "position": [float(v) for v in pf.est] if pf.est is not None else None,
                "spread": float(pf.spread) if math.isfinite(pf.spread) else None,
                "uncertainty": float(pf.uncertainty) if math.isfinite(pf.uncertainty) else None,
                "trust": float(pf.trust) if math.isfinite(pf.trust) else None,
                "scale": pf.scale, "source": pf.source, "odometry_score": float(score),
                "route_checks": pf.route_checks, "route_used": pf.route_used}
        meta.update(walked=pf.walked, raw=[float(v) for v in pf.raw], motion_valid=int(pf.motion_valid))
        meta.update(dungeon_key=pf.data.dungeons[pf.dungeon - 1]["key"] if pf.dungeon else "outside",
                    calibration_key=pf.calib.key, utc=time.time(), version=__version__, session=self.session,
                    movement_accepted=accepted)
        if now - self.last_journal >= 1:
            self.last_journal = now
            self._journal(meta)
        if rgb.nbytes > MAX_RAM:
            return
        self.frames.append((rgb, meta))
        self.bytes += rgb.nbytes
        while self.frames and (now - self.frames[0][1]["t"] > HISTORY_SECONDS or self.bytes > MAX_RAM):
            self.bytes -= self.frames.popleft()[0].nbytes

    def trigger(self, reason, event, now=None):
        now = time.monotonic() if now is None else now
        if not self.enabled or not self.frames or self.busy or now - self.last_saved < 10:
            return False
        frames = list(self.frames)
        cases = [(t, c) for t, c in self.cases if frames[0][1]["t"] <= t <= frames[-1][1]["t"] + 1]
        self.busy, self.last_saved = True, now

        def save():
            temp = None
            try:
                directory = self._directory(frames[-1][1]["dungeon_key"])
                os.makedirs(directory, exist_ok=True)
                with tempfile.NamedTemporaryFile(dir=directory, suffix=".tmp", delete=False) as fh:
                    temp = fh.name
                manifest = {"format": 1, "version": __version__, "reason": reason, "event": event,
                            "frames": [m for _, m in frames], "motion_cases": len(cases),
                            "dungeon": frames[-1][1]["dungeon_key"], "session": self.session}
                with zipfile.ZipFile(temp, "w", compression=zipfile.ZIP_STORED) as z:
                    z.writestr("manifest.json", json.dumps(manifest, allow_nan=False))
                    for i, (rgb, _) in enumerate(frames):
                        buf = io.BytesIO()
                        Image.fromarray(rgb).save(buf, format="PNG", compress_level=1)
                        z.writestr("minimap/%04d.png" % i, buf.getvalue())
                    for i, (t, case) in enumerate(cases):
                        buf = io.BytesIO()
                        np.savez_compressed(buf, t=t, **case)
                        z.writestr("motion/%02d.npz" % i, buf.getvalue())
                name = "trace-%s-%d-%s.zip" % (time.strftime("%Y%m%d-%H%M%S"), time.time_ns(),
                                              "marked" if event.get("kind") == "marked" else "motion")
                path = os.path.join(directory, name)
                os.replace(temp, path)
                temp = None
                self._prune()
                self.log("tracking evidence saved:", path, "(%d minimap frames; %s)" % (len(frames), reason))
                if event.get("kind") == "marked":
                    self.upload.submit(frames, event)
            except Exception as e:
                self.log("tracking evidence unavailable:", repr(e))
            finally:
                if temp:
                    try:
                        os.unlink(temp)
                    except OSError:
                        pass
                self.busy = False

        self.worker = threading.Thread(target=save, daemon=True)
        self.worker.start()
        return True
