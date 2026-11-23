"""The minimap atlas: what the minimap has shown on each floor, pasted into one picture in world yards.

The minimap is a picture of the dungeon around you. Whenever the tracker is sure where you are (just
after the entrance, a boss pull, a click on the map, or because the atlas itself just matched), the
minimap's picture is pasted into the floor's atlas at that spot. From then on every minimap picture is
matched against the atlas around where the tracker thinks you are (masked normalised cross-correlation,
the same maths as odometry.py): a clear match says exactly where you are, and odometry drift is gone.
Walking back through any part already seen locks you on again, and new areas join the atlas as you go
(each new picture overlaps what's known, so the atlas is stitched like a panorama).

The atlas is kept on disk per floor, so a second run starts with the whole dungeon known: with no
starting point at all (the tracker started inside a dungeon) the minimap is matched against the whole
floor at once.

The atlas also says where the floor is: dark void on the minimap is outside the dungeon, so walkmap.py
treats anything the atlas has seen as floor as walkable, which fixes paths the map art draws unclearly.

Atlas pixels: RES yards each; row 0 = the floor's north edge (+ margin), column 0 = its west edge.

A floor can also have a REFERENCE atlas (reference/<floor>.npz, made by tools/reference_atlas.py from the
game's own minimap textures, which are exactly what the minimap draws). Its pixels are loaded as fully
known and are FIXED: no paste ever changes them, so drifted runs can't smear ghost corridors into the
atlas (Ragefire 2026-11-23: a learned atlas with doubled corridors made 10-20 yard jumps).
"""

import math
import os
import tempfile
import threading

import numpy as np

from .data import MAP_H, MAP_W, user_dir

RES = 1.0             # yards per atlas pixel
MARGIN = 150.0        # yards around the map's own extent
MIN_WEIGHT = 0.5      # an atlas pixel counts once this much picture went into it
MAX_WEIGHT = 12.0     # (old pictures fade, so a changed spot or a bad paste heals)
MIN_AGE = 30.0        # yards: only pictures pasted at least this long a walk ago are matched against
                      # (matching what was pasted a moment ago would only confirm the drift)
FILL_TRUST = 15.0     # yards since the last sure position: after that, pictures only fill unknown parts
VOID = 22             # minimap luminance below this is outside the dungeon
PEAK_APART = 8.0      # yards: a match's runner-up is looked for at least this far from it
CACHE = os.path.join(user_dir("data"), "atlas")
# Reference atlases: made locally from this player's client, or shipped with the program.
REFERENCE_DIRS = (os.path.join(user_dir("data"), "reference"),
                  os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "reference"))


def _fft_size(n):
    return int(2 ** math.ceil(math.log2(max(n, 2))))


def masked_match(big, bmask, small, smask, min_overlap=0.3):
    """Masked normalised cross-correlation (Padfield 2012) of `small` at every top-left position
    inside `big` (both float images with 0/1 masks). Returns (ncc surface over the positions where
    small fits wholly inside big, overlap share of small's mask)."""
    H, W = big.shape
    n, m = small.shape
    fs = (_fft_size(H + n), _fft_size(W + m))
    rf, irf = np.fft.rfft2, np.fft.irfft2
    Bm = rf(bmask, fs)
    B1 = rf(big * bmask, fs)
    B2 = rf(big * big * bmask, fs)
    Tm = np.conj(rf(smask, fs))
    T1 = np.conj(rf(small * smask, fs))
    T2 = np.conj(rf(small * small * smask, fs))

    def corr(A, B):  # sum_x a(x + s) b(x) for top-left positions s
        return irf(A * B, fs)[:H - n + 1, :W - m + 1]

    N = corr(Bm, Tm)
    Sb, St = corr(B1, Tm), corr(Bm, T1)
    Sbb, Stt = corr(B2, Tm), corr(Bm, T2)
    Sbt = corr(B1, T1)
    eps = 1e-9
    Nc = np.maximum(N, eps)
    num = Sbt - Sb * St / Nc
    vb = Sbb - Sb * Sb / Nc
    vt = Stt - St * St / Nc
    den = vb * vt
    ncc = num / np.sqrt(np.maximum(den, eps))
    share = N / max(float(smask.sum()), eps)
    bad = (share < min_overlap) | (vb < 4.0 * Nc) | (vt < 4.0 * Nc)  # too little shared, or flat
    ncc[bad] = -1
    return ncc, share


def _peak(surf, exclude=4):
    """Best value and position, and the best value farther than `exclude` pixels from it."""
    iy, ix = np.unravel_index(int(np.argmax(surf)), surf.shape)
    best = float(surf[iy, ix])
    s = surf.copy()
    s[max(0, iy - exclude):iy + exclude + 1, max(0, ix - exclude):ix + exclude + 1] = -1
    return best, iy, ix, float(s.max())


def _subpixel(surf, iy, ix):
    def fit(a, b, c):
        d = a - 2 * b + c
        return 0.0 if d >= 0 else max(-0.5, min(0.5, 0.5 * (a - c) / d))
    h, w = surf.shape
    dy = fit(surf[iy - 1, ix], surf[iy, ix], surf[iy + 1, ix]) if 0 < iy < h - 1 else 0.0
    dx = fit(surf[iy, ix - 1], surf[iy, ix], surf[iy, ix + 1]) if 0 < ix < w - 1 else 0.0
    return dy, dx


def _save_npz(path, **arrays):
    temp = None
    try:
        with tempfile.NamedTemporaryFile(dir=os.path.dirname(path), suffix=".tmp", delete=False) as fh:
            temp = fh.name
            np.savez_compressed(fh, **arrays)
        os.replace(temp, path)
    finally:
        if temp and os.path.exists(temp):
            os.unlink(temp)


class FloorAtlas:
    def __init__(self, floor, n_max, w_max, rows, cols):
        self.floor = floor
        self.n_max, self.w_max = n_max, w_max
        self.sum = np.zeros((rows, cols), np.float32)
        self.wt = np.zeros((rows, cols), np.float32)
        self.odo = np.full((rows, cols), -1e9, np.float32)  # session yards walked when first pasted
        self.changed = False
        self.pasted = 0
        self.fixed = None  # bool (rows, cols): reference pixels no paste may change

    def set_reference(self, gray, known):
        """Load a reference atlas (same grid): known pixels become fixed, fully weighted truth."""
        if gray.shape != self.sum.shape or known.shape != self.sum.shape:
            return False
        known = known.astype(bool)
        self.sum[known] = gray[known].astype(np.float32) * MAX_WEIGHT
        self.wt[known] = MAX_WEIGHT
        self.odo[known] = -1e9
        self.fixed = known
        return True

    # -- coordinates ---------------------------------------------------------------------------------

    def rc(self, n, w):
        """World (north, west) yards -> atlas (row, column), floats."""
        return (self.n_max - n) / RES, (self.w_max - w) / RES

    def _sample(self, arr, r, c, newer_than=None):
        """Bilinear samples of arr at float rows/columns (0 outside)."""
        h, w = arr.shape
        r0, c0 = np.floor(r).astype(int), np.floor(c).astype(int)
        fr, fc = r - r0, c - c0
        out = np.zeros(r.shape, np.float32)
        for dr, dc, k in ((0, 0, (1 - fr) * (1 - fc)), (0, 1, (1 - fr) * fc), (1, 0, fr * (1 - fc)), (1, 1, fr * fc)):
            rr, cc = r0 + dr, c0 + dc
            ok = (rr >= 0) & (rr < h) & (cc >= 0) & (cc < w)
            values = arr[rr[ok], cc[ok]]
            if newer_than is not None:
                values = values > newer_than
            out[ok] += values * k[ok]
        return out

    # -- paste and match -----------------------------------------------------------------------------

    def paste(self, gray, mask, n, w, ypp, weight=1.0, odo=0.0, fill_only=False, replace=False):
        """gray: SIZE x SIZE minimap luminance centred on you at (n, w); ypp yards per pixel of it.
        odo: the session's yards walked (marks new pixels); fill_only: only parts not known yet."""
        size = gray.shape[0]
        c = (size - 1) / 2
        reach = c * ypp
        r0, c0 = self.rc(n, w)
        rows = np.arange(int(math.floor(r0 - reach / RES)), int(math.ceil(r0 + reach / RES)) + 1)
        cols = np.arange(int(math.floor(c0 - reach / RES)), int(math.ceil(c0 + reach / RES)) + 1)
        rows = rows[(rows >= 0) & (rows < self.sum.shape[0])]
        cols = cols[(cols >= 0) & (cols < self.sum.shape[1])]
        if not len(rows) or not len(cols):
            return
        rr, cc = np.meshgrid(rows, cols, indexing="ij")
        # atlas pixel -> world -> minimap pixel (y down = south, x right = east)
        y = c + (rr * RES - r0 * RES) / ypp
        x = c + (cc * RES - c0 * RES) / ypp
        yi, xi = np.round(y).astype(int), np.round(x).astype(int)
        ok = (yi >= 0) & (yi < size) & (xi >= 0) & (xi < size)
        m = np.zeros(rr.shape, np.float32)
        g = np.zeros(rr.shape, np.float32)
        m[ok] = mask[yi[ok], xi[ok]]
        g[ok] = gray[yi[ok], xi[ok]]
        k = m * float(weight)
        block = (slice(rows[0], rows[-1] + 1), slice(cols[0], cols[-1] + 1))
        if self.fixed is not None:
            k = k * ~self.fixed[block]  # the reference is the truth: never repaint it
        s, t, o = self.sum[block], self.wt[block], self.odo[block]
        unknown = t < MIN_WEIGHT
        if fill_only:
            k = k * unknown
        if replace:
            # Explicit user corrections override stale, misregistered texture.
            # Blending a new weight-4 fix with old weight-12 data mostly keeps
            # the old error. Only replace pixels actually seen through the mask.
            seen = k > 0
            s[seen] = 0
            t[seen] = 0
        o[k > 0] = odo  # the last write, including corrections: never match a fresh repaint
        s += g * k
        t += k
        over = t > MAX_WEIGHT
        if over.any():
            f = MAX_WEIGHT / t[over]
            s[over] *= f
            t[over] *= f
        self.changed = True
        self.pasted += 1

    def render(self, n, w, ypp, size, odo=None):
        """The atlas seen like the minimap: size x size pixels of ypp yards, centred on (n, w).
        Returns (picture, mask); with odo, the mask leaves out pictures pasted under MIN_AGE ago."""
        c = (size - 1) / 2
        r0, c0 = self.rc(n, w)
        yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
        r = r0 + (yy - c) * ypp / RES
        cl = c0 + (xx - c) * ypp / RES
        wt = self._sample(self.wt, r, cl)
        s = self._sample(self.sum, r, cl)
        mask = wt >= MIN_WEIGHT
        if odo is not None:
            # A bilinear timestamp blends unknown (-1e9) with fresh pixels and
            # makes their edges appear ancient. Exclude any fresh contributor.
            mask &= self._sample(self.odo, r, cl, newer_than=odo - MIN_AGE) < 1e-6
        mask = mask.astype(np.float32)
        return np.where(mask > 0, s / np.maximum(wt, 1e-6), 0).astype(np.float32), mask

    def locate(self, gray, mask, n, w, ypp, search_yards, odo=None):
        """Match the minimap against the atlas around (n, w), up to search_yards away.
        Returns (north, west, score, runner-up score, overlap share) or None."""
        size = gray.shape[0]
        margin = int(math.ceil(search_yards / ypp))
        big, bmask = self.render(n, w, ypp, size + 2 * margin, odo)
        if bmask.sum() < 0.15 * mask.sum():
            return None
        surf, share = masked_match(big, bmask, gray, mask)
        # (the runner-up must be somewhere else, not the shoulder of the same broad peak)
        best, iy, ix, second = _peak(surf, exclude=max(4, int(round(PEAK_APART / ypp))))
        if best <= -1:
            return None
        dy, dx = _subpixel(surf, iy, ix)
        # top-left (margin, margin) = exactly where we thought; further down/right = south/east
        sy, sx = iy + dy - margin, ix + dx - margin
        return n - sy * ypp, w - sx * ypp, best, second, float(share[iy, ix])

    def locate_anywhere(self, gray, mask, ypp, odo=None, max_px=600):
        """Match the minimap against everything the atlas knows (no estimate needed).
        Returns (north, west, score, runner-up score, overlap share) or None."""
        known = self.wt >= MIN_WEIGHT
        if known.sum() * RES * RES < 3000:
            return None
        rows, cols = np.nonzero(known)
        size = gray.shape[0]
        span = max(rows.max() - rows.min(), cols.max() - cols.min()) * RES / ypp + size
        if span > max_px:
            # Zooming in must not silently disable whole-floor recovery. Search
            # a bounded coarse image, then verify the result at full resolution.
            from PIL import Image
            factor = span / max_px * 1.1
            side = int(size / factor)
            if side < 24:
                return None  # too little visual detail for an honest global lock
            small = np.asarray(Image.fromarray(gray.astype(np.float32)).resize(
                (side, side), Image.Resampling.BOX))
            smask = np.asarray(Image.fromarray(mask.astype(np.float32)).resize(
                (side, side), Image.Resampling.BOX))
            smask = (smask >= .99).astype(np.float32)
            coarse = self.locate_anywhere(small, smask, ypp * size / side, odo, max_px)
            if coarse is None or coarse[2] < .65 or coarse[2] - coarse[3] < .08:
                return None
            refined = self.locate(gray, mask, coarse[0], coarse[1], ypp,
                                  max(12., 4 * ypp * size / side), odo)
            if refined is None:
                return None
            n, w, score, second, share = refined
            # A unique local peak cannot erase global ambiguity.
            return n, w, min(score, coarse[2]), max(second, coarse[3]), share
        rc, cc = (rows.min() + rows.max()) / 2, (cols.min() + cols.max()) / 2
        n, w = self.n_max - rc * RES, self.w_max - cc * RES
        return self.locate(gray, mask, n, w, ypp, (span - size) / 2 * ypp + size / 2 * ypp, odo)

    def coverage(self):
        """Square yards the atlas knows."""
        return float((self.wt >= MIN_WEIGHT).sum()) * RES * RES

    def floor_mask(self):
        """Where the atlas has seen dungeon floor (not void): bool, atlas pixels."""
        known = self.wt >= MIN_WEIGHT
        mean = np.where(known, self.sum / np.maximum(self.wt, 1e-6), 0)
        return known & (mean >= VOID)


class Atlases:
    """Per-floor atlases, loaded from and saved to disk."""

    def __init__(self, data, folder=CACHE, reference_dirs=None):
        self.data = data
        self.folder = folder
        self.reference_dirs = REFERENCE_DIRS if reference_dirs is None else reference_dirs
        self.atlases = {}
        self.lock = threading.RLock()
        self.saving = False

    def path(self, floor):
        return os.path.join(self.folder, "%d.npz" % floor)

    def _extent(self, floor):
        corners = [self.data.to_world(floor, u, v) for u in (0.0, 1.0) for v in (0.0, 1.0)]
        ns, ws = [c[0] for c in corners], [c[1] for c in corners]
        n_max, w_max = max(ns) + MARGIN, max(ws) + MARGIN
        rows = int(math.ceil((n_max - (min(ns) - MARGIN)) / RES))
        cols = int(math.ceil((w_max - (min(ws) - MARGIN)) / RES))
        return n_max, w_max, min(rows, 4000), min(cols, 4000)

    def get(self, floor):
        with self.lock:
            a = self.atlases.get(floor)
            if a is None and floor in self.data.floors:
                a = FloorAtlas(floor, *self._extent(floor))
                learned_with_reference = False
                try:
                    z = np.load(self.path(floor))
                    if z["sum"].shape == a.sum.shape and float(z["res"]) == RES:
                        a.sum[:] = z["sum"]
                        a.wt[:] = z["wt"]   # (odo stays "long ago": all of it can be matched)
                        learned_with_reference = "reference" in z.files
                except (OSError, ValueError, KeyError):
                    pass  # no atlas yet (or a damaged one: start again)
                if self._load_reference(a) and not learned_with_reference:
                    # An atlas learned before the reference existed is drift-smeared (ghost corridors,
                    # texture outside the walls): drop all of it once; only what the reference lacks
                    # is learned again, and saved with the "reference" flag from then on.
                    keep = a.fixed
                    a.sum[~keep] = 0
                    a.wt[~keep] = 0
                    a.changed = True
                self.atlases[floor] = a
            return a

    def _load_reference(self, a):
        for folder in self.reference_dirs:
            try:
                with np.load(os.path.join(folder, "%d.npz" % a.floor)) as z:
                    if (float(z["res"]) == RES and abs(float(z["n_max"]) - a.n_max) < 1e-3
                            and abs(float(z["w_max"]) - a.w_max) < 1e-3 and a.set_reference(z["gray"], z["known"])):
                        return True
            except (OSError, ValueError, KeyError):
                continue  # none here (or made for another grid): try the next place
        return False

    def save(self, background=True):
        """Write changed atlases (in the background: compressing takes a moment)."""
        with self.lock:
            if self.saving:
                return  # (the next save writes what changed meanwhile)
            todo = [(a.floor, a.sum.copy(), a.wt.copy(), a.fixed is not None)
                    for a in self.atlases.values() if a.changed]
            for a in self.atlases.values():
                a.changed = False
        if not todo:
            return

        def work():
            self.saving = True
            try:
                os.makedirs(self.folder, exist_ok=True)
                for floor, s, w, ref in todo:
                    extra = {"reference": np.uint8(1)} if ref else {}
                    _save_npz(self.path(floor), sum=s, wt=w, res=np.float32(RES), **extra)
            except OSError:
                pass
            finally:
                self.saving = False
        if background:
            threading.Thread(target=work, daemon=True).start()
        else:
            work()

    def floor_on_map(self, floor):
        """The atlas's floor mask drawn on the map (MAP_H x MAP_W bool), or None when unknown."""
        a = self.atlases.get(floor) or self.get(floor)
        if a is None or a.coverage() < 2000:
            return None
        fm = a.floor_mask()
        vv, uu = np.mgrid[0:MAP_H, 0:MAP_W]
        n, w = self.data.to_world(floor, (uu + 0.5) / MAP_W, (vv + 0.5) / MAP_H)
        r, c = a.rc(n, w)
        r, c = np.round(r).astype(int), np.round(c).astype(int)
        ok = (r >= 0) & (r < fm.shape[0]) & (c >= 0) & (c < fm.shape[1])
        out = np.zeros((MAP_H, MAP_W), bool)
        out[ok] = fm[r[ok], c[ok]]
        return out
