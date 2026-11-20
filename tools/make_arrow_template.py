"""Cut the minimap player arrow out of a real minimap screenshot and save it pointing north.

    python3 tools/make_arrow_template.py [data/minimap_sample.png]   -> data/minimap_arrow.npz

The sample is a crop of exactly the minimap (the beacon's minimap rectangle). The arrow is a silver
cone with a blue eye; its axis is found from the cone's mirror symmetry, the mask is the cone (mirrored
to fill its shaded half) and the eye, grown by a pixel.
"""
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dungeonmaps")


def rot(a, deg):
    return np.asarray(Image.fromarray(a.astype(np.float32), mode="F").rotate(-deg, resample=Image.BILINEAR), np.float32)


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "data", "minimap_sample.png")
    m = np.array(Image.open(src).convert("RGB")).astype(np.float32)
    h, w = m.shape[:2]
    R = int(round(w * 0.11))
    c = m[h // 2 - R:h // 2 + R, w // 2 - R:w // 2 + R]
    mx, mn = c.max(2), c.min(2)
    sat = (mx - mn) / np.maximum(mx, 1)
    r, g, b = c[..., 0], c[..., 1], c[..., 2]
    core = (((b > r + 50) & (b > g + 30) & (b > 90)) | ((mx > 140) & (sat < 0.18))).astype(np.float32)
    best = max((((k := rot(core, -a)) * k[:, ::-1]).sum() / k.sum(), a) for a in np.arange(0, 360, 0.25))
    axis = best[1]
    k = rot(core, -axis) > 0.3
    k |= k[:, ::-1]
    d = k.copy()
    d[1:] |= k[:-1]; d[:-1] |= k[1:]; d[:, 1:] |= k[:, :-1]; d[:, :-1] |= k[:, 1:]
    gray = rot(c @ np.array([0.299, 0.587, 0.114], np.float32), -axis)
    np.savez_compressed(os.path.join(HERE, "data", "minimap_arrow.npz"), gray=gray, mask=d.astype(np.float32),
                        minimap_w=w, side=2 * R)
    print("arrow axis in the sample: %.2f deg; template %d px, %d px of arrow" % (axis, 2 * R, d.sum()))


if __name__ == "__main__":
    main()
