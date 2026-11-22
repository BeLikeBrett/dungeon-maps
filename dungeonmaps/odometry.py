"""Minimap odometry: how far you moved, from how far the minimap picture slid since the last frame.

The minimap keeps you in the middle and slides the dungeon under you (north up, the "rotate minimap"
option off). Two frames are aligned with masked normalised cross-correlation (Padfield, "Masked object
registration in the Fourier domain", 2012): only the inside of the round minimap counts, without its
border and without the player arrow in the middle, so those still parts can't pull the answer to
"no movement". Frames are compared against a key frame, not the frame before, so small errors don't
pile up; a new key frame is taken once the picture has slid far or matches poorly.
"""

import numpy as np

SIZE = 128              # the minimap is resampled to this many pixels across
OUTER = 0.90            # use the disc out to this fraction of the radius (skips the border art)
INNER = 0.16            # and from this fraction (skips the player arrow)
MIN_OVERLAP = 0.35      # a shift counts only where at least this share of the masks overlap
REKEY_SHIFT = 0.28      # new key frame once the picture slid this share of the minimap width
REKEY_SCORE = 0.75      # ... or matches the key frame worse than this
MIN_SCORE = 0.45        # below this a frame is ignored (loading screen, something on top)
STATIC_VOTES = 2.0      # a pixel that stayed put this many times while the map slid is UI, not map
STATIC_WINDOW = 30      # frames looked back over
STATIC_STEP = 2.0       # SIZE px moved between the pictures kept for that
STATIC_SPAN = 10        # ... during which the map must have slid this far (SIZE px) both ways
STATIC_REBUILD = 24     # rebuild the mask once this many pixels changed status


def _mask(n):
    yy, xx = np.mgrid[0:n, 0:n]
    c = (n - 1) / 2
    r = np.hypot(xx - c, yy - c) / (n / 2)
    return ((r <= OUTER) & (r >= INNER)).astype(np.float64)


def to_gray(rgb):
    """Minimap crop (H x W x 3, uint8) -> SIZE x SIZE float luminance (area resampling)."""
    img = rgb[..., :3].astype(np.float64) @ np.array([0.299, 0.587, 0.114])
    h, w = img.shape
    ys = (np.arange(SIZE + 1) * h / SIZE).astype(int)
    xs = (np.arange(SIZE + 1) * w / SIZE).astype(int)
    # area average via cumulative sums
    cs = np.zeros((h + 1, w + 1))
    cs[1:, 1:] = img.cumsum(0).cumsum(1)
    tot = cs[ys[1:]][:, xs[1:]] - cs[ys[:-1]][:, xs[1:]] - cs[ys[1:]][:, xs[:-1]] + cs[ys[:-1]][:, xs[:-1]]
    area = np.outer(np.maximum(ys[1:] - ys[:-1], 1), np.maximum(xs[1:] - xs[:-1], 1))
    return tot / area


def edges(img):
    gy, gx = np.gradient(img)
    return np.hypot(gx, gy)


class MaskedNCC:
    """Masked normalised cross-correlation of two SIZE x SIZE images with the same mask."""

    def __init__(self, n=SIZE, mask=None):
        self.n = n
        self.m = _mask(n) if mask is None else mask
        self.shape = (2 * n - 1, 2 * n - 1)
        self.fs = tuple(int(2 ** np.ceil(np.log2(s))) for s in self.shape)
        self.Fm = np.fft.rfft2(self.m, self.fs)
        # overlap counts don't depend on the images
        self.N = self._corr(self.Fm, self.Fm)

    def _corr(self, A, B):
        """sum_x a(x) b(x + s) for all shifts s (index [n-1+sy, n-1+sx])."""
        c = np.fft.irfft2(np.conj(A) * B, self.fs)
        c = np.roll(c, (self.n - 1, self.n - 1), axis=(0, 1))
        return c[:self.shape[0], :self.shape[1]]

    def prepare(self, img):
        a = img * self.m
        return np.fft.rfft2(a, self.fs), np.fft.rfft2(a * img, self.fs)

    def surface(self, key, cur):
        """NCC for every shift s where cur(x + s) lines up with key(x)."""
        Fk, Fk2 = key
        Fc, Fc2 = cur
        N = self.N
        Sk = self._corr(Fk, self.Fm)
        Sc = self._corr(self.Fm, Fc)
        Skk = self._corr(Fk2, self.Fm)
        Scc = self._corr(self.Fm, Fc2)
        Skc = self._corr(Fk, Fc)
        eps = 1e-9
        Nc = np.maximum(N, eps)
        num = Skc - Sk * Sc / Nc
        den = (Skk - Sk ** 2 / Nc) * (Scc - Sc ** 2 / Nc)
        ncc = num / np.sqrt(np.maximum(den, eps))
        ncc[N < MIN_OVERLAP * N.max()] = -1
        ncc[den < 1e-3 * max(den.max(), eps)] = -1  # flat overlap (nothing to match on)
        return ncc


def _subpixel(surf, iy, ix):
    def fit(a, b, c):
        d = a - 2 * b + c
        return 0.0 if d >= 0 else 0.5 * (a - c) / d
    dy = fit(surf[iy - 1, ix], surf[iy, ix], surf[iy + 1, ix]) if 0 < iy < surf.shape[0] - 1 else 0.0
    dx = fit(surf[iy, ix - 1], surf[iy, ix], surf[iy, ix + 1]) if 0 < ix < surf.shape[1] - 1 else 0.0
    return max(-0.5, min(0.5, dy)), max(-0.5, min(0.5, dx))


class Odometry:
    """Feed minimap crops; get how far YOU moved since the last good frame, in crop pixels
    (x right = east, y down = south: the picture itself slides the other way)."""

    def __init__(self):
        self.ncc = MaskedNCC()
        self.disc = self.ncc.m.copy()
        # pixels printed on top of the minimap (addon text, icons) stay put while the map slides:
        # they are learned here and left out, or they would pull every match towards "no movement"
        self.votes = np.zeros((SIZE, SIZE), np.float32)
        self.static = np.zeros((SIZE, SIZE), bool)
        self.prev = None
        self.hist = []
        self.since_check = 0
        self.key_gray = None
        self.key = None
        self.key_offset = np.zeros(2)  # position of the key frame, SIZE-pixel units
        self.offset = np.zeros(2)      # last position, SIZE-pixel units
        self.score = 0.0
        self.max_step = None     # crop pixels; caller derives it from elapsed time and minimap scale
        self.rejected = 0
        self.rejected_step = 0.0
        self.rejection = None

    def reset(self):
        self.key = None
        self.prev = None

    def reset_static(self):
        """The minimap changed size or place: what is printed on it may have moved too."""
        self.hist = []
        self.votes[:] = 0
        self.static[:] = False
        self.ncc = MaskedNCC(mask=self.disc.copy())
        self.reset()

    @property
    def mask(self):
        """Where the minimap shows the map (SIZE x SIZE floats 0/1)."""
        return self.ncc.m

    def _learn_static(self, gray, moved_px):
        """A pixel is printed on top of the minimap when it kept its value while the map slid
        both ways (north-south AND east-west) under it. One-way slides don't count: walls running
        the way you walk look unchanged then."""
        if self.hist and np.hypot(*(self.offset - self.hist[-1][1])) < STATIC_STEP:
            return  # only keep pictures some way apart (frames can come 100+ a second)
        self.hist.append((gray, self.offset.copy()))
        if len(self.hist) > STATIC_WINDOW:
            self.hist.pop(0)
        self.since_check += 1
        if self.since_check < 4 or len(self.hist) < STATIC_WINDOW // 2:
            return
        offs = np.array([o for _, o in self.hist])
        span = offs.max(0) - offs.min(0)
        if span.min() < STATIC_SPAN:
            return
        self.since_check = 0
        stack = np.stack([g for g, _ in self.hist])
        still = (stack.max(0) - stack.min(0)) < 8
        textured = edges(stack.mean(0)) > 5
        self.votes += np.where(still & textured, 1.0, -1.0)
        np.clip(self.votes, 0, 6, out=self.votes)
        static = self.votes >= STATIC_VOTES
        grown = static.copy()  # text and icons have soft edges
        grown[1:] |= static[:-1]; grown[:-1] |= static[1:]
        grown[:, 1:] |= static[:, :-1]; grown[:, :-1] |= static[:, 1:]
        if np.count_nonzero(grown != self.static) >= STATIC_REBUILD:
            self.static = grown
            self.ncc = MaskedNCC(mask=self.disc * ~grown)
            if self.key_gray is not None:
                self.key = self.ncc.prepare(self.key_gray)

    def step(self, rgb):
        """Returns (dx, dy) you moved since the previous good frame, in crop pixels, or None."""
        gray = to_gray(rgb)
        self.gray = gray  # recovery must never reuse a previous picture after a blank/failed frame
        scale = rgb.shape[1] / SIZE
        if gray[self.ncc.m > 0].std() < 2:  # blank minimap
            return None
        cur = self.ncc.prepare(gray)
        if self.key is None:
            self.key = cur
            self.key_gray = gray
            self.key_offset = self.offset.copy()
            self.prev = gray
            return np.zeros(2)
        surf = self.ncc.surface(self.key, cur)
        n = SIZE
        iy, ix = np.unravel_index(np.argmax(surf), surf.shape)
        self.score = float(surf[iy, ix])
        if self.score < MIN_SCORE:
            self.prev = gray
            return None
        sy, sx = _subpixel(surf, iy, ix)
        # with this indexing -s is how far the view (you) moved (checked by tests/test_odometry.py)
        shift = -np.array([ix - (n - 1) + sx, iy - (n - 1) + sy])
        pos = self.key_offset + shift
        delta = (pos - self.offset) * scale
        if self.max_step is not None and np.hypot(*delta) > self.max_step:
            # Repetitive rooms / changing minimap layers can produce a strong
            # but impossible peak. Do not commit it, learn UI from it, or emit
            # the opposite jump next frame. Rebase on a fresh picture instead.
            self.rejected += 1
            self.rejected_step = float(np.hypot(*delta))
            self.rejection = {"key": self.key_gray.copy(), "current": gray.copy(),
                              "mask": self.mask.copy(), "offset": self.offset.copy(),
                              "key_offset": self.key_offset.copy(), "candidate": delta.copy(),
                              "crop_scale": float(scale), "max_step": float(self.max_step)}
            self.reset_static()
            return None
        self.offset = pos
        self._learn_static(gray, 0)
        self.prev = gray
        if np.hypot(*shift) > REKEY_SHIFT * n or self.score < REKEY_SCORE:
            self.key = self.ncc.prepare(gray)
            self.key_gray = gray
            self.key_offset = pos.copy()
        return delta
