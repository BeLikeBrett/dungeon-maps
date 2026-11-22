"""Where you are: a particle filter over the dungeon floor.

Hundreds of guesses ("particles") of your position move with every minimap slide the odometry measures,
each with a little noise and its own small scale error. Guesses that end up off the walkable paths (the
light-yellow areas of the map art, walkmap.py) lose weight for every yard they walk there; the
survivors are copied. So drift that would carry you through a wall is pulled back onto the path, and
a corridor fixes you sideways all by itself. A jump down a ledge still works: weights never quite
reach zero, and if every guess is off the paths the art is assumed wrong there and ignored.

Exact fixes: the dungeon entrance and a fresh Shift+click on the map ("I am here"). Boss spawns
are never player fixes; stationary bosses provide at most one soft hint during a search. With no fix at all the guesses
start spread over every path of the floor (inside the named room when the game says which one), and
your position is shown once they agree.

Positions are world yards (north, west), as the game's map data uses.
"""

import json
import math
import os
import re

import numpy as np

from .data import MAP_H, MAP_W, box_extent, room_main_floor, user_dir
from .routes import Routes

CALIB_FILE = os.path.join(user_dir("state"), "calibration.json")
FIX_SIGMA = {"entrance": 3.0, "marked": 4.0, "boss": 15.0, "matched": 2.0}  # (you pull a boss from range)


class ScaleCalibration:
    """How far off the minimap scale is (true distance / measured), learned from pairs of fixes and
    kept between runs. One per minimap setting (indoors/outdoors, zoom)."""

    def __init__(self, path=CALIB_FILE, log=lambda *a: None):
        self.path, self.log = path, log
        self.key = "?"
        try:
            with open(path, encoding="utf-8") as fh:
                self.table = json.load(fh)
        except (OSError, ValueError):
            self.table = {}

    def get(self):
        """(log-scale mean, log-scale sd)."""
        row = self.table.get(self.key)
        if row is None:
            # Legacy/global calibration is a weak starting prior, never a sink
            # for measurements made in a different dungeon.
            row = self.table.get(self.key.rsplit("/", 1)[-1], (0.0, CALIB_PRIOR, 0))
            row = (row[0], max(row[1], CALIB_PRIOR), 0)
        m, sd, _ = row
        return m, sd

    def add(self, ratio, sd_meas):
        m, sd = self.get()
        n = self.table.get(self.key, (0, 0, 0))[2]
        z = math.log(ratio)
        k = sd * sd / (sd * sd + sd_meas * sd_meas)
        if abs(z - m) > 0.04:
            k = min(k, 0.04 / abs(z - m))  # one approximate click pair cannot rescale every future step
        m = m + k * (z - m)
        sd = max(SCALE_MIN_SPREAD, math.sqrt((1 - k) * sd * sd) + 0.003)  # (a little forgetting)
        self.table[self.key] = (m, sd, n + 1)
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            with open(self.path, "w", encoding="utf-8") as fh:
                json.dump(self.table, fh)
        except OSError:
            pass
        return math.exp(m), sd

N = 500                 # particles once you are found
N_GLOBAL = 4000         # particles while searching the whole floor
NOISE_PER_YARD = 0.08   # random walk added per yard moved (yards; real minimaps drift more than tests)
NOISE_FIXED = 0.01      # ... and per update
SCALE_SPREAD = 0.06     # each particle's minimap-scale error (fraction) before any calibration
SCALE_MIN_SPREAD = 0.015
CALIB_MIN_YARDS = 35.0  # fix-to-fix calibration needs at least this far between the two fixes
CALIB_PRIOR = 0.10      # how wrong the minimap scale may be before any calibration (log sd; seen ~20 %)
FIX_SPREAD = 1.0        # yards: spread after an exact fix
BOSS_SPREAD = 25.0      # a spawn/patrol is only a broad hint when no player position is known
FOUND_SPREAD = 6.0      # yards: trusted estimate; broader known estimates are labelled uncertain
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
    def __init__(self, data, walkmaps, rng=None, log=lambda *a: None, info=None, calib=None):
        self.data = data
        self.walkmaps = walkmaps
        self.rng = rng or np.random.default_rng()
        self.log = log
        self.info = info or log
        self.calib = calib if calib is not None else ScaleCalibration(log=self.info)
        self.dungeon = 0
        self.routes = Routes(data)
        self.reset()
        self.on_fix = None      # (floor, estimate before or None, fix, why, sigma) -> None (set by the core)

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
        self.trust = math.inf   # yards walked since the position was last known for sure
        self.walked = 0.0       # yards walked since the last fix
        self.raw = np.zeros(2)  # odometry since the last fix, before any scale correction
        self.anchor = None      # (floor, north, west, sigma) of the last fix
        self.route_previous = None
        self.route_travel = self.context_travel = 0.0
        self.current_room = None
        self.active_boss = 0
        self.boss_mask = 0
        self.boss_context_travel = 0.0
        self.boss_hint_used = False
        self.route_checks = self.route_used = 0
        self.motion_valid = True
        self.stretch_valid = True
        self.pose_error = math.inf  # current localization error; separate from calibration/training history

    # -- set up ------------------------------------------------------------------------------------

    @property
    def floors(self):
        return self.data.dungeons[self.dungeon - 1]["floors"] if self.dungeon else []

    @property
    def found(self):
        return self.est is not None and self.spread <= FOUND_SPREAD and self.searching is None

    @property
    def displayable(self):
        return self.est is not None and self.searching is None

    @property
    def uncertainty(self):
        """Include accumulated bias: identical particles can still all be wrong."""
        return max(self.spread, self.pose_error)

    @property
    def guessed(self):
        return not self.found or self.uncertainty > 12.0

    def scale_prior(self, n):
        m, sd = self.calib.get()
        if self.s is not None and self.searching is None:
            # keep what this run learned about the scale (weighted, in logs), within the calibration
            ls = np.log(np.maximum(self.s, 1e-3))
            mw = float((ls * self.w).sum())
            sw = math.sqrt(max(0.0, float(((ls - mw) ** 2 * self.w).sum())))
            sw = max(sw, 0.025)  # (resampling makes the particles look surer than they are)
            v1, v2 = sd * sd, sw * sw
            m, sd = (m / v1 + mw / v2) / (1 / v1 + 1 / v2), max(SCALE_MIN_SPREAD, math.sqrt(1 / (1 / v1 + 1 / v2)))
        return np.exp(m + self.rng.normal(0, sd, n))

    @property
    def scale(self):
        """The particles' (weighted) minimap scale correction."""
        if self.s is None:
            return math.exp(self.calib.get()[0])
        return float((self.s * self.w).sum())

    def _init(self, floor, centre, spread, n, why):
        self._check_fix(floor, centre, why)
        s = self.scale_prior(n)
        self.floor = floor
        self.p = np.asarray(centre, float) + self.rng.normal(0, spread, (n, 2))
        self.s = s
        self.w = np.full(n, 1 / n)
        self.source = why
        self.pose_error = 6.0 if why == "matched" else FIX_SIGMA.get(why, 6.0)
        if why == "boss":
            self.pose_error = 25.0
        self.off_path = 0.0
        self.searching = None
        if why in ("entrance", "marked"):
            self.trust = 0.0
        elif why == "matched":
            # An atlas relocation is not a new independent ground-truth anchor.
            self.trust = max(80.0, self.trust) if math.isfinite(self.trust) else 80.0
        elif why == "boss":
            self.trust = max(800.0, self.trust)  # a spawn pin is only a broad recovery hint
        self.route_previous = None
        self.route_travel = self.context_travel = 0.0
        self._estimate()
        self.log("position ->", why, "floor", floor)

    def _check_fix(self, floor, centre, why):
        """At every fix: how far off the estimate was (the log tells how tracking went), and the
        minimap scale learned from the distance between this fix and the previous one."""
        n, w = float(centre[0]), float(centre[1])
        sigma = FIX_SIGMA.get(why, 6.0)
        if self.est is not None and self.floor == floor and self.searching is None and why != "matched":
            err = math.hypot(self.est[0] - n, self.est[1] - w)
            self.info("fix (%s): the arrow was %.1f yards off after %.0f yards walked (scale %.3f)" % (
                why, err, self.walked, self.scale))
        a = self.anchor
        self.stretch_valid = self.motion_valid
        if a is not None and a[0] == floor and why not in ("matched", "boss") and self.motion_valid:
            true = np.array([n - a[1], w - a[2]])
            dt, dr = float(np.hypot(*true)), float(np.hypot(*self.raw))
            if dt >= CALIB_MIN_YARDS and dr >= CALIB_MIN_YARDS:
                ang = math.degrees(math.atan2(true[1], true[0]) - math.atan2(self.raw[1], self.raw[0]))
                ang = (ang + 180) % 360 - 180
                ratio = dt / dr
                if abs(ang) < 25 and 0.8 < ratio < 1.25:
                    k, sd = self.calib.add(ratio, (sigma + a[3]) / dt + 0.02)
                    self.info("minimap scale: this stretch says x%.3f (turn %.0f deg); calibrated x%.3f +- %.3f" % (
                        ratio, ang, k, sd))
                else:
                    self.stretch_valid = False
                    self.info("minimap scale: stretch ignored (x%.2f, turn %.0f deg)" % (ratio, ang))
        if why == "boss":
            # A spawn pin is not the player's location: ranged pulls and patrols
            # must not calibrate scale or repaint the atlas as ground truth.
            if self.on_fix:
                self.on_fix(floor, None, (n, w), why, sigma)  # discard a discontinuous trail
            return
        if why != "matched":
            if self.on_fix:  # (the atlas re-pastes the stretch since the last fix, corrected)
                same = self.est is not None and self.floor == floor and self.searching is None
                self.on_fix(floor, tuple(self.est) if same else None, (n, w), why, sigma)
            self.anchor = (floor, n, w, sigma)
            self.raw = np.zeros(2)
            self.walked = 0.0
            self.motion_valid = True

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
        self.s = None
        self.s = self.scale_prior(len(p))
        self.w = np.full(len(p), 1 / len(p))
        self.source = "searching"
        self.route_previous = None
        self.route_travel = self.context_travel = 0.0
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
                self.info("landmark from the addon: %s at map %.0f,%.0f floor %d (#%d%s)" % (
                    {1: "entrance", 2: "boss", 3: "marked"}.get(kind, kind), u * MAP_W, v * MAP_H, floor,
                    f["lm_count"], ", already known at start" if first else ""))
                # The beacon keeps the last mark indefinitely. A mark already
                # present at startup may be minutes behind the moving player.
                if kind in (1, 3) and not (first and (self.p is not None or kind == 3)):
                    self.fix(floor, u, v, "entrance" if kind == 1 else "marked")
                # Boss pins are guide annotations, not player measurements.
                # Never seed a player pose from one, even while lost.
        rooms = self.data.rooms.get(key, [])
        room = rooms[f["room"] - 1] if 0 < f["room"] <= len(rooms) else None
        self.current_room = room
        active = f.get("active_boss", 0)
        mask = f.get("boss_mask", 0)
        if mask != self.boss_mask:
            self.info("boss progress:", bin(mask))
        self.boss_mask = mask
        if active != self.active_boss:
            self.active_boss = active
            self.boss_context_travel = 0.0
            self.boss_hint_used = False
        if f["room"] != self.room:
            self.room = f["room"]
            if room is not None and self.floor is not None and not any(b[0] == self.floor for b in room["boxes"]):
                # The game names a room exclusive to another floor. Discard the
                # old-floor estimate; search the new room rather than guessing its centre.
                self.floor, self.p, self.est = room_main_floor(room), None, None
                self.searching = None
                self.route_previous = None
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

    def _room_hint(self, room, outside=0.1):
        """The game says which named room you are in: guesses outside it lose most of their weight."""
        if not any(b[0] == self.floor for b in room["boxes"]):
            return
        u, v = self.data.to_map(self.floor, self.p[:, 0], self.p[:, 1])
        px = ROOM_MARGIN * self.data.px_per_yard(self.floor)
        inside = _box_contains(self.data, self.floor, room["boxes"], u, v, px)
        if inside.any():
            self.w = self.w * np.where(inside, 1.0, outside)
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
        self.raw += step
        self.walked += dist
        self.trust += dist
        self.pose_error += 0.015 * dist
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
            self.route_travel += dist
            self.context_travel += dist
            if self.route_travel >= 3.0:
                graph = self.routes.get(self.floor)
                if graph is not None:
                    self.route_checks += 1
                    like, near = graph.weights(self.p, self.route_previous, self.route_travel)
                    if (near * self.w).sum() >= 0.65:
                        self.route_used += 1
                        self.w *= like ** min(1.0, self.route_travel / 3.0)
                        self.w /= self.w.sum()
                self.route_previous = self.p.copy()
                self.route_travel = 0.0
            if self.context_travel >= 5.0:
                # Recheck while walking, rather than applying a frame-rate-dependent
                # stream of repeated observations. Named rooms are approximate too.
                if self.current_room is not None:
                    self._room_hint(self.current_room, outside=0.8)
                self._boss_hint(self.context_travel)
                self.context_travel = 0.0
        self._resample_if_needed()
        self._estimate()
        if self.searching is not None:
            self.held = self.held + dist if self.spread <= FOUND_SPREAD else 0.0
            if self.held >= CONFIRM_YARDS:
                self.searching = None
                self.source = "found by walking"
                self.log("found you by walking")

    def _boss_hint(self, distance):
        # A fight says "near this boss", never "at its spawn point". Only use
        # the opening 40 yards: bosses can be kited or patrol away from the pin.
        if (not self.active_boss or self.searching is None or self.boss_hint_used
                or self.boss_context_travel >= 40 or not self.dungeon):
            return
        if self.boss_mask & (1 << (self.active_boss - 1)):
            return  # a defeated boss cannot keep pulling the estimate toward its pin
        self.boss_context_travel += distance
        key = self.data.dungeons[self.dungeon - 1]["key"]
        bosses = self.data.bosses.get(key, [])
        if not 0 < self.active_boss <= len(bosses):
            return
        boss = bosses[self.active_boss - 1]
        if re.search(r"\b(patrol\w*|roam\w*|wander\w*)\b", boss.get("note", ""), re.I):
            return
        if boss["floor"] != self.floor:
            return
        centre = np.asarray(self.data.to_world(self.floor, boss["x"], boss["y"]))
        d = np.linalg.norm(self.p - centre, axis=1)
        if not (d < 60).any():
            return  # patrols/guide positions may be wrong; don't crush every guess
        self.w *= 0.5 + 0.5 * np.exp(-0.5 * (d / 40.0) ** 2)
        self.w /= self.w.sum()
        self.boss_hint_used = True  # one soft observation, not repeated attraction

    def observe(self, n, w, sigma, why="matched", verified=False):
        """An outside measurement of where you are (the atlas matched the minimap there).
        Returns True when it was used."""
        if self.p is None:
            return False
        d2 = ((self.p - np.array([n, w])) ** 2).sum(1)
        like = np.exp(-0.5 * d2 / (sigma * sigma))
        if (like * self.w).sum() < 1e-4:
            return False  # nothing near it: the caller decides whether it's a new fix
        self.w = self.w * (like + 1e-6)
        self.w /= self.w.sum()
        self._resample_if_needed()
        self._estimate()
        if verified:
            # Repeated strong visual observations recover current localization.
            # They do not repair missing raw motion or authorize scale learning.
            self.pose_error = min(self.pose_error, max(6.0, 2 * sigma))
        if self.searching is not None and self.spread <= FOUND_SPREAD:
            self.searching = None
            self.source = "found by the minimap"
            self.trust = max(80.0, self.trust) if math.isfinite(self.trust) else 80.0
        # (a match while tracking holds the arrow on the atlas but doesn't make it a sure fix: the
        # atlas is only as good as the runs that taught it)
        return True

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
            if self.route_previous is not None:
                self.route_previous = self.route_previous[idx].copy()
            self.w = np.full(m, 1 / m)
            if self.searching is not None:
                # fresh guesses keep a wrong early answer from locking in
                k = int(INJECT * m)
                fresh = self._random_guesses(self.searching[0], self.searching[1], k)
                if fresh is not None and len(fresh) == k:
                    j = self.rng.choice(m, k, replace=False)
                    self.p[j] = fresh
                    if self.route_previous is not None:
                        self.route_previous[j] = fresh
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
