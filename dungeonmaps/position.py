"""Where you are: a particle filter over the dungeon floor.

Hundreds of guesses ("particles") of your position move with every minimap slide the odometry measures,
each with a little noise and its own small scale error. Guesses that end up off the walkable paths (the
light-yellow areas of the map art, walkmap.py) lose weight for every yard they walk there; the
survivors are copied. So drift that would carry you through a wall is pulled back onto the path, and
a corridor fixes you sideways all by itself. A jump down a ledge still works: weights never quite
reach zero, and if every guess is off the paths the art is assumed wrong there and ignored.

Exact fixes: the dungeon entrance and a right-click on the map ("I am here"). A boss pull moves you
only if you are far from that boss. With no fix at all (tracker started inside a dungeon) the guesses
start spread over every path of the floor (inside the named room when the game says which one), and
your position is shown once they agree.

Positions are world yards (north, west), as the game's map data uses.
"""

import math

import numpy as np

from .data import MAP_H, MAP_W, box_extent, room_main_floor

N = 500                 # particles once you are found
N_GLOBAL = 4000         # particles while searching the whole floor
NOISE_PER_YARD = 0.04   # random walk added per yard moved (yards)
NOISE_FIXED = 0.01      # ... and per update
SCALE_SPREAD = 0.03     # each particle's minimap-scale error (fraction)
FIX_SPREAD = 1.0        # yards: spread after an exact fix
BOSS_SPREAD = 8.0
BOSS_TRUST = 45.0       # a boss pull moves you only when you are farther than this from it
FOUND_SPREAD = 6.0      # yards: the estimate is shown when the particles agree this well
ROOM_MARGIN = 8.0       # yards outside a named room's boxes that are still "in the room"
CONFIRM_YARDS = 60.0    # searching: the answer must hold this far before it is shown
INJECT = 0.03           # searching: share of guesses replaced by fresh random ones at each resample


def _box_contains(data, floor, boxes, u, v, margin_px):
    x, y = u * MAP_W, v * MAP_H
    inside = np.zeros(np.shape(u), bool)
    for b in boxes:
        if b[0] != floor:
            continue
        l, t, r, btm = box_extent(b)
        inside |= (x >= l - margin_px) & (x <= r + margin_px) & (y >= t - margin_px) & (y <= btm + margin_px)
    return inside


class ParticleFilter:
    def __init__(self, data, walkmaps, rng=None, log=lambda *a: None):
        self.data = data
        self.walkmaps = walkmaps
        self.rng = rng or np.random.default_rng()
        self.log = log
        self.dungeon = 0
        self.reset()

    def reset(self):
        self.floor = None
        self.p = None           # (n, 2) north, west
        self.s = None           # (n,) scale
        self.w = None           # (n,) weights
        self.lm_count = None
        self.room = 0
        self.est = None
        self.spread = math.inf
        self.source = "none"
        self.off_path = 0.0     # yards walked with every particle off the paths
        self.searching = None   # (floor, room) while looking for you with no fix
        self.held = 0.0         # searching: yards walked with the guesses agreeing

    # -- set up ------------------------------------------------------------------------------------

    @property
    def floors(self):
        return self.data.dungeons[self.dungeon - 1]["floors"] if self.dungeon else []

    @property
    def found(self):
        return self.est is not None and self.spread <= FOUND_SPREAD and self.searching is None

    def _init(self, floor, centre, spread, n, why):
        self.floor = floor
        self.p = np.asarray(centre, float) + self.rng.normal(0, spread, (n, 2))
        self.s = 1 + self.rng.normal(0, SCALE_SPREAD, n)
        self.w = np.full(n, 1 / n)
        self.source = why
        self.off_path = 0.0
        self.searching = None
        self._estimate()
        self.log("position ->", why, "floor", floor)

    def fix(self, floor, u, v, why, spread=FIX_SPREAD):
        self._init(floor, self.data.to_world(floor, u, v), spread, N, why)

    def _random_guesses(self, floor, room, n):
        wm = self.walkmaps.get(floor)
        if wm is None:
            return None
        u, v = wm.sample(n * 3, self.rng)
        if room is not None:
            px = ROOM_MARGIN * self.data.px_per_yard(floor)
            keep = _box_contains(self.data, floor, room["boxes"], u, v, px)
            if keep.sum() > 50:
                u, v = u[keep], v[keep]
        u, v = u[:n], v[:n]
        return np.stack(self.data.to_world(floor, u, v), 1)

    def search_floor(self, floor, room=None):
        """No fix: spread guesses over the floor's paths (inside the room when known)."""
        p = self._random_guesses(floor, room, N_GLOBAL)
        if p is None:
            return False
        self.floor = floor
        self.p = p
        self.s = 1 + self.rng.normal(0, SCALE_SPREAD, len(p))
        self.w = np.full(len(p), 1 / len(p))
        self.source = "searching"
        self.searching = (floor, room)
        self.held = 0.0
        self._estimate()
        self.log("searching floor", floor, "with", len(p), "guesses")
        return True

    # -- updates -----------------------------------------------------------------------------------

    def on_beacon(self, f):
        """Dungeon, landmarks and room from the addon's beacon."""
        if f["dungeon"] != self.dungeon:
            self.dungeon = f["dungeon"]
            self.reset()
        if not self.dungeon:
            return
        floors = self.floors
        key = self.data.dungeons[self.dungeon - 1]["key"]
        if f["lm_count"] != self.lm_count:
            first = self.lm_count is None
            self.lm_count = f["lm_count"]
            if f["lm_kind"] and 0 < f["lm_floor"] <= len(floors):
                floor = floors[f["lm_floor"] - 1]
                u, v = f["lm_u"] / 4095, f["lm_v"] / 4095
                kind = f["lm_kind"]
                if kind in (1, 3) and not (first and self.p is not None):
                    self.fix(floor, u, v, "entrance" if kind == 1 else "marked")
                elif kind == 2:
                    n, w = self.data.to_world(floor, u, v)
                    far = self.est is None or self.floor != floor or \
                        math.hypot(n - self.est[0], w - self.est[1]) > BOSS_TRUST or not self.found
                    if far:
                        self.fix(floor, u, v, "boss", BOSS_SPREAD)
        rooms = self.data.rooms.get(key, [])
        room = rooms[f["room"] - 1] if 0 < f["room"] <= len(rooms) else None
        if f["room"] != self.room:
            self.room = f["room"]
            if room is not None and self.p is not None:
                self._room_hint(room)
        if self.p is None:
            floor = None
            if room is not None:
                floor = room_main_floor(room)
            elif len(floors) == 1:
                floor = floors[0]
            if floor is not None:
                self.search_floor(floor, room)

    def _room_hint(self, room):
        """The game says which named room you are in: guesses outside it lose most of their weight."""
        if not any(b[0] == self.floor for b in room["boxes"]):
            return
        u, v = self.data.to_map(self.floor, self.p[:, 0], self.p[:, 1])
        px = ROOM_MARGIN * self.data.px_per_yard(self.floor)
        inside = _box_contains(self.data, self.floor, room["boxes"], u, v, px)
        if inside.any():
            self.w = self.w * np.where(inside, 1.0, 0.1)
            self.w /= self.w.sum()
            self._resample_if_needed()
            self._estimate()

    def move(self, d_north, d_west):
        """You moved this far (yards, from the minimap)."""
        if self.p is None:
            return
        dist = math.hypot(d_north, d_west)
        n = len(self.p)
        step = np.array([d_north, d_west])
        self.p += step[None, :] * self.s[:, None]
        self.p += self.rng.normal(0, NOISE_FIXED + NOISE_PER_YARD * dist, (n, 2))
        if dist > 0:
            wm = self.walkmaps.get(self.floor)
            if wm is not None:
                u, v = self.data.to_map(self.floor, self.p[:, 0], self.p[:, 1])
                like = wm.weights(u, v)
                if (like * self.w).sum() < 0.05:
                    # every guess is off the paths: the art is wrong here (or a jump): don't judge
                    self.off_path += dist
                else:
                    self.off_path = 0.0
                    # evidence per yard walked, not per frame (frames come 100+ a second)
                    self.w = self.w * like ** min(1.0, dist / 0.5)
                    self.w /= self.w.sum()
        self._resample_if_needed()
        self._estimate()
        if self.searching is not None:
            self.held = self.held + dist if self.spread <= FOUND_SPREAD else 0.0
            if self.held >= CONFIRM_YARDS:
                self.searching = None
                self.source = "found by walking"
                self.log("found you by walking")

    def _resample_if_needed(self):
        ess = 1 / np.sum(self.w ** 2)
        n = len(self.w)
        target = N if (self.spread <= 3 * FOUND_SPREAD and self.searching is None) else n
        if ess < n / 2 or (target < n and ess < n * 0.9):
            # systematic resampling (and shrink the set once you are found)
            m = target
            pos = (self.rng.random() + np.arange(m)) / m
            idx = np.minimum(np.searchsorted(np.cumsum(self.w), pos), n - 1)
            self.p, self.s = self.p[idx].copy(), self.s[idx].copy()
            self.w = np.full(m, 1 / m)
            if self.searching is not None:
                # fresh guesses keep a wrong early answer from locking in
                k = int(INJECT * m)
                fresh = self._random_guesses(self.searching[0], self.searching[1], k)
                if fresh is not None and len(fresh) == k:
                    j = self.rng.choice(m, k, replace=False)
                    self.p[j] = fresh
                    self.s[j] = 1 + self.rng.normal(0, SCALE_SPREAD, k)

    def _estimate(self):
        """Weighted mean of the main cluster (several clusters while searching: the heaviest one)."""
        w, p = self.w, self.p
        mean = (p * w[:, None]).sum(0)
        spread = math.sqrt(max(0.0, ((p - mean) ** 2 * w[:, None]).sum()))
        if spread > FOUND_SPREAD:
            # the heaviest neighbourhood: pick among a sample of particles the one with most weight nearby
            k = min(200, len(p))
            cand = self.rng.choice(len(p), k, replace=False, p=w)
            sub = self.rng.choice(len(p), min(1500, len(p)), replace=False)
            d2 = ((p[cand][:, None, :] - p[sub][None, :, :]) ** 2).sum(-1)
            mass = ((d2 < 10 ** 2) * w[sub][None, :]).sum(1)
            c = p[cand[int(np.argmax(mass))]]
            near = ((p - c) ** 2).sum(1) < 10 ** 2
            wn = w * near
            if wn.sum() > 0:
                mean = (p * wn[:, None]).sum(0) / wn.sum()
                # the spread that counts: how much of the weight is NOT in that cluster
                spread = max(spread * (1 - wn.sum()), math.sqrt(((p - mean) ** 2 * wn[:, None]).sum() / wn.sum()))
        self.est, self.spread = mean, spread
