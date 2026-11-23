"""Walkable paths of a dungeon floor, read from its map art.

The art (captured once per floor from the Dungeon Maps addon's map, then cached) draws the paths as pale,
light areas; the parchment around them is a stronger tan, rock and lava deeply coloured. A pixel is
path when it is pale (low saturation) and not darker than its surroundings, or clearly brighter than
them (the bright yellow crossings). Only the areas connected to the entrance, the boss spots and the
named rooms are kept, which drops specks in the parchment, the title banner and the drawings.

Skull icons, the legend and the note line are drawn over the art by the addon: "unknown" there.
The result is a weight per map pixel for the particle filter: 1 on a path, falling off over a few
yards outside it (a jump down a ledge stays possible, a walk through a wall doesn't).
"""

import os
import tempfile
import threading
from collections import deque

import numpy as np
from PIL import Image, ImageFilter

from .data import HERE, MAP_H, MAP_W, user_dir

CACHE = os.path.join(user_dir("data"), "floors")
WALL_SIGMA = 5.0     # yards: how fast the weight falls off outside a path (hand-drawn art misses lanes)
FLOOR_WEIGHT = 0.08  # never near zero: the art can miss a lane (Ragefire's ramps) or a ledge
UNKNOWN_WEIGHT = 0.6
MAX_DIST = 40        # map pixels the distance field looks out to


def _save_png(image, path):
    """Publish only complete images: readers must never see an in-progress PNG."""
    temp = None
    try:
        with tempfile.NamedTemporaryFile(dir=os.path.dirname(path), suffix=".tmp", delete=False) as fh:
            temp = fh.name
            image.save(fh, format="PNG")
        os.replace(temp, path)
    finally:
        if temp and os.path.exists(temp):
            os.unlink(temp)


def _blur(img, r):
    return np.array(Image.fromarray(img).filter(ImageFilter.GaussianBlur(r)))


def _dilate(m, n=1):
    for _ in range(n):
        d = m.copy()
        d[1:] |= m[:-1]; d[:-1] |= m[1:]; d[:, 1:] |= m[:, :-1]; d[:, :-1] |= m[:, 1:]
        m = d
    return m


def _erode(m, n=1):
    return ~_dilate(~m, n)


def _connected(mask, seeds):
    """Pixels of mask 4-connected to any seed (y, x)."""
    out = np.zeros_like(mask)
    q = deque()
    for y, x in seeds:
        if mask[y, x] and not out[y, x]:
            out[y, x] = True
            q.append((y, x))
    h, w = mask.shape
    while q:
        y, x = q.popleft()
        for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
            if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not out[ny, nx]:
                out[ny, nx] = True
                q.append((ny, nx))
    return out


def _snap(mask, x, y, r=25):
    """Nearest mask pixel to (x, y) within r, as (y, x), or None."""
    x, y = int(round(x)), int(round(y))
    y0, y1, x0, x1 = max(0, y - r), min(MAP_H, y + r + 1), max(0, x - r), min(MAP_W, x + r + 1)
    ys, xs = np.nonzero(mask[y0:y1, x0:x1])
    if not len(xs):
        return None
    i = np.argmin((ys + y0 - y) ** 2 + (xs + x0 - x) ** 2)
    return ys[i] + y0, xs[i] + x0


def segment(art, seeds_uv, markers_uv):
    """art: MAP_H x MAP_W x 3 uint8. Returns (walkable, unknown) bool masks."""
    a = _blur(art, 1.5).astype(np.float32)
    lum = a @ np.array([0.299, 0.587, 0.114], np.float32)
    mx, mn = a.max(2), a.min(2)
    sat = (mx - mn) / np.maximum(mx, 1)
    bg = _blur(np.clip(lum, 0, 255).astype(np.uint8), 30).astype(np.float32)
    walk = ((sat < 0.58) & (lum > 0.9 * bg) & (lum > 60)) | ((lum > 1.2 * bg) & (lum > 150))
    unknown = np.zeros_like(walk)
    yy, xx = np.mgrid[0:MAP_H, 0:MAP_W]
    for u, v in markers_uv:  # the addon's skulls
        unknown |= np.hypot(xx - u * MAP_W, yy - v * MAP_H) < 17
    strip = np.zeros_like(walk)
    strip[MAP_H - 40:, :] = True         # the addon's legend and note line along the bottom
    walk &= ~strip
    walk = _erode(_dilate(walk | unknown, 2), 2)  # close hairline gaps
    seeds = [s for s in (_snap(walk, u * MAP_W, v * MAP_H) for u, v in seeds_uv) if s]
    walk = _connected(walk, seeds)
    unknown |= strip & _dilate(walk, 15)  # paths running under the legend: unknown, not walls
    # fill small holes (dots, specks inside paths)
    holes = _connected(~walk, [(0, 0), (MAP_H - 1, 0), (0, MAP_W - 1), (MAP_H - 1, MAP_W - 1)])
    small = ~walk & ~holes
    walk |= small & ~strip
    unknown &= walk | strip
    return walk & ~unknown, unknown


def distance(walk):
    """Distance (map pixels, 4-neighbour steps, capped) from each pixel to the nearest path pixel."""
    d = np.full(walk.shape, MAX_DIST, np.float32)
    d[walk] = 0
    m = walk.copy()
    for i in range(1, MAX_DIST):
        n = _dilate(m)
        d[n & ~m] = i
        m = n
        if m.all():
            break
    return d


class WalkMap:
    def __init__(self, walk, unknown, px_per_yard):
        self.walk = walk
        self.unknown = unknown
        dist_yd = distance(walk | unknown) / px_per_yard
        w = np.exp(-0.5 * (dist_yd / WALL_SIGMA) ** 2)
        w = np.maximum(w, FLOOR_WEIGHT)
        w[unknown] = UNKNOWN_WEIGHT
        self.weight = w.astype(np.float32)

    def add_floor(self, floor_mask):
        """Where the minimap atlas has seen floor is walkable too (the art may not show it as a path)."""
        if not hasattr(self, "base"):
            self.base = self.weight.copy()
        self.weight = np.where(floor_mask, np.float32(1.0), self.base).astype(np.float32)

    def weights(self, u, v):
        """Weight at map points (arrays of u, v in 0..1); outside the map: the floor weight."""
        x = np.round(np.asarray(u) * MAP_W).astype(int)
        y = np.round(np.asarray(v) * MAP_H).astype(int)
        ok = (x >= 0) & (x < MAP_W) & (y >= 0) & (y < MAP_H)
        out = np.full(x.shape, FLOOR_WEIGHT, np.float32)
        out[ok] = self.weight[y[ok], x[ok]]
        return out

    def sample(self, n, rng):
        """n random path points (u, v), for "where could I be" with no starting point."""
        ys, xs = np.nonzero(self.walk)
        i = rng.integers(0, len(xs), n)
        return (xs[i] + rng.random(n)) / MAP_W, (ys[i] + rng.random(n)) / MAP_H


class WalkMaps:
    """Per-floor walk maps: built from art captured off the dungeon map, cached on disk."""

    def __init__(self, data):
        self.data = data
        self.maps = {}
        self.lock = threading.RLock()
        os.makedirs(CACHE, exist_ok=True)

    def art_path(self, floor):
        revision = self.data.floors.get(floor, {}).get("art_revision")
        name = "%d-%s.png" % (floor, revision) if revision else "%d.png" % floor
        return os.path.join(CACHE, name)

    def has_art(self, floor):
        mask = self.data.floors.get(floor, {}).get("walk_mask")
        if mask and os.path.isfile(os.path.join(HERE, "data", mask)):
            return True
        return os.path.exists(self.art_path(floor))

    def _seeds(self, floor):
        seeds, markers = [], []
        for d in self.data.dungeons:
            if floor not in d["floors"]:
                continue
            key = d["key"]
            e = self.data.entry.get(key)
            if e and e["floor"] == floor:
                seeds.append((e["x"], e["y"]))
            for b in self.data.bosses.get(key, []):
                # Main bosses only: optional/rare pins were added later, and seeding/masking them
                # would change walk masks of already-cached (verified) floors. Their small skulls
                # inside rooms are enclosed specks that segment() fills as floor anyway.
                if b["floor"] == floor and not b.get("kind"):
                    seeds.append((b["x"], b["y"]))
                    markers.append((b["x"], b["y"]))
            for r in self.data.rooms.get(key, []):
                for box in r["boxes"]:
                    if box[0] == floor:
                        seeds.append((box[1], box[2]))
        return seeds, markers

    def add_floor(self, floor, floor_mask):
        """Atlas floor (MAP_H x MAP_W bool) joins the floor's walk map; with no art, it IS the walk map."""
        if self.data.floors.get(floor, {}).get("walk_mask"):
            return  # Texture coverage includes walls and air; retain verified WC geometry.
        with self.lock:
            wm = self._get(floor)
            if wm is None:
                if floor_mask.sum() < 500:
                    return
                wm = WalkMap(floor_mask, np.zeros_like(floor_mask), self.data.px_per_yard(floor))
                self.maps[floor] = wm
                self.atlas_only = getattr(self, "atlas_only", set()) | {floor}
            wm.add_floor(floor_mask)

    def save_art(self, floor, art):
        """art: the canvas as captured (any size): stored at MAP_W x MAP_H; rebuilds the walk map."""
        img = Image.fromarray(art)
        if img.size != (MAP_W, MAP_H):
            img = img.resize((MAP_W, MAP_H), Image.LANCZOS)
        with self.lock:
            _save_png(img, self.art_path(floor))
            self.maps.pop(floor, None)
            return self.get(floor)

    def get(self, floor):
        with self.lock:
            return self._get(floor)

    def _get(self, floor):
        if floor in self.maps:
            return self.maps[floor]
        mask = self.data.floors.get(floor, {}).get("walk_mask")
        if mask:
            try:
                with Image.open(os.path.join(HERE, "data", mask)) as image:
                    walk = np.asarray(image.convert("L")) > 127
                if walk.shape != (MAP_H, MAP_W) or walk.sum() < 500:
                    raise ValueError("invalid bundled walk mask")
                wm = WalkMap(walk, np.zeros_like(walk), self.data.px_per_yard(floor))
                self.maps[floor] = wm
                return wm
            except (OSError, ValueError, SyntaxError):
                pass  # Ordinary cache/capture recovery remains available if an install is incomplete.
        if not self.has_art(floor) or floor not in self.data.floors:
            return None
        try:
            with Image.open(self.art_path(floor)) as image:
                art = np.array(image.convert("RGB"))
            if art.shape != (MAP_H, MAP_W, 3):
                raise ValueError("invalid cached map dimensions")
        except (OSError, ValueError, SyntaxError):
            # A cache is disposable. Discard damage and let the next frame recapture the map,
            # instead of terminating the tracker (and reopening the Linux permission picker).
            try:
                os.unlink(self.art_path(floor))
            except OSError:
                pass
            return None
        seeds, markers = self._seeds(floor)
        walk, unknown = segment(art, seeds, markers)
        if walk.sum() < 500:  # nothing sensible found: don't constrain
            self.maps[floor] = None
            return None
        wm = WalkMap(walk, unknown, self.data.px_per_yard(floor))
        # preview for checking by eye: paths green, unknown blue
        vis = art.copy()
        vis[walk] = (0.5 * vis[walk] + [0, 110, 0]).astype(np.uint8)
        vis[unknown] = (0.5 * vis[unknown] + [0, 0, 110]).astype(np.uint8)
        try:
            _save_png(Image.fromarray(vis), os.path.join(CACHE, "%d-walk.png" % floor))
        except OSError:
            pass  # the diagnostic preview must never interrupt tracking
        self.maps[floor] = wm
        return wm
