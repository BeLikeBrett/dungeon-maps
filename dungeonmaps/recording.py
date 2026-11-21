"""Bounded local evidence for tracking problems. Never uploads pictures."""

from collections import deque
import io
import json
import math
import os
import tempfile
import threading
import time
import zipfile

import numpy as np
from PIL import Image

from . import __version__
from .data import user_dir
from .samples import SampleUploader

MAX_RAM = 30 * 1024 * 1024
MAX_DISK = 100 * 1024 * 1024
MAX_FILES = 10


class Recorder:
    def __init__(self, folder=None, log=lambda *a: None):
        self.folder = folder or os.path.join(user_dir("state"), "recordings")
        self.log = log
        self.enabled = os.environ.get("DUNGEONMAPS_RECORDING", "on") != "off"
        self.frames = deque()
        self.cases = deque(maxlen=3)
        self.bytes = 0
        self.last_frame = self.last_saved = -math.inf
        self.busy = False
        self.worker = None
        self.upload = SampleUploader(log=log)

    def clear(self):
        self.frames.clear()
        self.cases.clear()
        self.bytes = 0
        self.last_frame = -math.inf

    def add_case(self, case, now, yards_per_pixel, elapsed):
        if self.enabled and case is not None:
            self.cases.append((now, dict(case, yards_per_pixel=float(yards_per_pixel), elapsed=float(elapsed))))

    def add(self, img, fields, pf, now, score, force=False):
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
        if rgb.nbytes > MAX_RAM:
            return
        self.frames.append((rgb, meta))
        self.bytes += rgb.nbytes
        while self.frames and (now - self.frames[0][1]["t"] > 60 or self.bytes > MAX_RAM):
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
                os.makedirs(self.folder, exist_ok=True)
                with tempfile.NamedTemporaryFile(dir=self.folder, suffix=".tmp", delete=False) as fh:
                    temp = fh.name
                manifest = {"format": 1, "version": __version__, "reason": reason, "event": event,
                            "frames": [m for _, m in frames], "motion_cases": len(cases)}
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
                name = "trace-%s-%d.zip" % (time.strftime("%Y%m%d-%H%M%S"), time.time_ns())
                path = os.path.join(self.folder, name)
                os.replace(temp, path)
                temp = None
                files = sorted((os.path.getmtime(os.path.join(self.folder, n)), os.path.join(self.folder, n))
                               for n in os.listdir(self.folder) if n.startswith("trace-") and n.endswith(".zip"))
                total = sum(os.path.getsize(p) for _, p in files)
                while files and (len(files) > MAX_FILES or total > MAX_DISK):
                    _, old = files.pop(0)
                    total -= os.path.getsize(old)
                    os.unlink(old)
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
