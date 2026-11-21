"""Reprocess a local evidence ZIP with the current tracker, without touching live caches.

Usage: python tools/replay_trace.py /path/to/trace-....zip
The recorded initial estimate and sampled minimaps are an approximation, not a
full-frequency deterministic replay or independent ground truth for the whole run.
"""
import io
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import zipfile


def main():
    archive = Path(sys.argv[1]).resolve()
    with tempfile.TemporaryDirectory(prefix="dungeonmaps-replay-") as temp:
        os.environ.update(XDG_DATA_HOME=temp, XDG_STATE_HOME=temp, LOCALAPPDATA=temp,
                          DUNGEONMAPS_RECORDING="off")
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        import numpy as np
        from PIL import Image
        from dungeonmaps.core import Core
        from dungeonmaps.position import N

        c = Core(info=lambda *a: None)
        c.atlases.get = lambda floor: None  # old learned caches are intentionally not assumed
        c.walkmaps.get = lambda floor: None
        c.pf.rng = np.random.default_rng(7)
        with zipfile.ZipFile(archive) as z:
            manifest = json.loads(z.read("manifest.json"))
            for name in z.namelist():
                if name.startswith("motion/") and name.endswith(".npz"):
                    from dungeonmaps.odometry import MaskedNCC, _subpixel
                    with np.load(io.BytesIO(z.read(name)), allow_pickle=False) as case:
                        match = MaskedNCC(mask=case["mask"])
                        surf = match.surface(match.prepare(case["key"]), match.prepare(case["current"]))
                        iy, ix = np.unravel_index(np.argmax(surf), surf.shape)
                        dy, dx = _subpixel(surf, iy, ix)
                        shift = -np.array([ix - (match.n - 1) + dx, iy - (match.n - 1) + dy])
                        candidate = (case["key_offset"] + shift - case["offset"]) * float(case["crop_scale"])
                        print("Exact motion case %s: candidate %.2f px; allowed %.2f px; rejected %s" % (
                            name, np.linalg.norm(candidate), float(case["max_step"]),
                            np.linalg.norm(candidate) > float(case["max_step"])))
            frames = manifest["frames"]
            first = next((i for i, f in enumerate(frames) if f["position"] is not None and f["floor"] is not None), None)
            if first is None:
                raise SystemExit("No starting estimate; this archive still contains crops and search context to inspect.")
            seed = frames[first]
            c.pf.dungeon = seed["fields"]["dungeon"]
            c.pf.calib.key = "i%dz%d" % (seed["fields"]["indoors"], seed["fields"]["zoom"])
            c.pf.calib.table[c.pf.calib.key] = (math.log(seed["scale"]), .015, 0)
            c.pf._init(seed["floor"], seed["position"], 1., N, "marked")
            c.pf.lm_count = seed["fields"]["lm_count"]
            for i in range(first, len(frames)):
                m = frames[i]
                f = m["fields"]
                c.pf.on_beacon(f)
                rgb = np.array(Image.open(io.BytesIO(z.read("minimap/%04d.png" % i))).convert("RGB"))
                c._minimap(rgb, (0, 0, f["mm_w"], f["mm_h"]), f, m["t"])
            event = manifest["event"]
            print("Reason:", manifest["reason"], "| version:", manifest["version"], "| crops:", len(frames))
            print("Recorded correction (yards):", event.get("error_yards", "not a manual reference"))
            if event.get("fix") and c.pf.est is not None and c.pf.floor == event.get("floor"):
                print("Reprocessed distance from correction (yards): %.2f" % math.dist(c.pf.est, event["fix"]))
            print("Replay starts from the recorded estimate, uses sampled minimaps, and excludes old learned caches.")
            print("Compare on the same archive; manual map corrections are approximate references.")


if __name__ == "__main__":
    main()
