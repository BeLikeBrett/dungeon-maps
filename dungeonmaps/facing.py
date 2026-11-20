"""Which way you face, read off the player arrow in the middle of the minimap, every frame.

The template is the game's own arrow (a silver cone with a blue eye), cut from a real minimap
(data/minimap_sample.png) and turned to point north (data/minimap_arrow.npz, made by
tools/make_arrow_template.py). Its axis was found from the cone's mirror symmetry.

Each frame the centre of the minimap is compared with the template turned to every 2 degrees, using
only the pixels the arrow covers at that angle (the map behind it never counts), as normalised
correlation: three matrix products, well under a millisecond. The best angle is refined to a fraction
of a step. Nothing is learned, so it is right from the first frame.

Angles: degrees, 0 = north (up on the minimap), clockwise.
"""

import os

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(HERE, "data", "minimap_arrow.npz")
P = 40                 # side (pixels) the comparison runs at
STEP = 2               # degrees between turned templates
MIN_SCORE = 0.5        # weaker matches are not trusted (something drawn on top of the arrow)
RECENTRE_BELOW = 0.85  # a weaker match makes it look for the arrow's exact centre again
RECENTRE_EVERY = 0.5   # ... at most this often (seconds)
RECHECK_EVERY = 2.0    # and the centre is checked this often anyway (a 1 px miss can still score well)
SHIFT = 2              # minimap pixels searched each way for that centre


def _gray(rgb):
    return rgb[..., 0] * 0.299 + rgb[..., 1] * 0.587 + rgb[..., 2] * 0.114


def _rotate(img, deg):
    """Turn a float image clockwise by deg about its centre."""
    return np.asarray(Image.fromarray(img.astype(np.float32), mode="F").rotate(-deg, resample=Image.BILINEAR),
                      np.float32)


def _resize(img, n):
    return np.asarray(Image.fromarray(img.astype(np.float32), mode="F").resize((n, n), Image.BILINEAR), np.float32)


def _soften(img):
    """A light blur, so the arrow drawn a pixel off still lines up."""
    k = np.array([0.25, 0.5, 0.25], np.float32)
    p = np.pad(img, 1, mode="edge")
    p = p[:, :-2] * k[0] + p[:, 1:-1] * k[1] + p[:, 2:] * k[2]
    return p[:-2] * k[0] + p[1:-1] * k[1] + p[2:] * k[2]


class Facing:
    def __init__(self, template=TEMPLATE):
        t = np.load(template)
        self.fraction = float(t["side"]) / float(t["minimap_w"])  # patch side / minimap width
        gray, mask = _resize(t["gray"], P), _resize(t["mask"], P)
        self.angles = np.arange(0, 360, STEP, dtype=np.float32)
        ms, ts = [], []
        for a in self.angles:
            m = (_rotate(mask, a) > 0.5).astype(np.float32).ravel()
            g = _soften(_rotate(gray, a)).ravel() * m
            g = (g - m * (g.sum() / m.sum())) * m        # zero mean inside the mask
            ts.append(g / np.linalg.norm(g))
            ms.append(m)
        self.M = np.stack(ms)                              # (angles, P*P) masks
        self.T = np.stack(ts)                              # (angles, P*P) normalised templates
        self.n = self.M.sum(1)
        self.reset()

    ready = True

    def reset(self):
        self.angle = None
        self.score = 0.0
        self.off = (0, 0)          # where the arrow's centre is, against the minimap's centre (pixels)
        self.last_recentre = -1e9
        self.centred = False

    def patch(self, minimap_rgb, off=None):
        """The centre of a minimap crop (moved by off pixels), as a P x P float patch."""
        h, w = minimap_rgb.shape[:2]
        dx, dy = self.off if off is None else off
        side = max(8, int(round(w * self.fraction)))
        x0, y0 = (w - side) // 2 + dx, (h - side) // 2 + dy
        if x0 < 0 or y0 < 0 or x0 + side > w or y0 + side > h:
            return None
        g = _gray(minimap_rgb[y0:y0 + side, x0:x0 + side].astype(np.float32))
        return _soften(_resize(g, P) if side != P else g)

    def read_minimap(self, minimap_rgb, now=None):
        """Facing from a minimap crop; finds the arrow's exact centre again when the match is weak."""
        import time
        now = time.monotonic() if now is None else now
        p = self.patch(minimap_rgb)
        best = self._scores(p) if p is not None else None
        since = now - self.last_recentre
        weak = best is None or best[0] < RECENTRE_BELOW
        if not self.centred or (weak and since > RECENTRE_EVERY) or since > RECHECK_EVERY:
            self.last_recentre = now
            self.centred = True
            for dy in range(-SHIFT, SHIFT + 1):
                for dx in range(-SHIFT, SHIFT + 1):
                    q = self.patch(minimap_rgb, (dx, dy))
                    r = self._scores(q) if q is not None else None
                    if r and (best is None or r[0] > best[0] + 0.02):
                        best, self.off = r, (dx, dy)
        if best is None:
            return None
        self.score = best[0]
        if self.score < MIN_SCORE:
            return None
        self.angle = best[1]
        return self.angle

    def read(self, patch):
        """Facing from a patch (patch()), or None when the arrow can't be seen."""
        r = self._scores(patch)
        self.score = r[0]
        if self.score < MIN_SCORE:
            return None
        self.angle = r[1]
        return self.angle

    def _scores(self, patch):
        """(best score, refined angle) for a patch."""
        p = patch.ravel().astype(np.float32)
        s1 = self.M @ p
        s2 = self.M @ (p * p)
        var = np.maximum(s2 - s1 * s1 / self.n, 1e-6)
        s = (self.T @ p) / np.sqrt(var)
        i = int(np.argmax(s))
        a, b, c = s[i - 1], s[i], s[(i + 1) % len(s)]
        den = a - 2 * b + c
        frac = 0.5 * (a - c) / den if den < -1e-9 else 0.0
        return float(b), float(self.angles[i] + frac * STEP) % 360
