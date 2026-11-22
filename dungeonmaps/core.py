"""The tracker's brain, the same on every system: one call per game frame.

The platform code (linux.py, windows.py) gets WoW's window picture and finds the addon's beacon in it;
it hands the decoded beacon and a way to cut rectangles out of that picture to Core.frame(). Core
reads the minimap (odometry.py: how far you moved; facing.py: which way you face), keeps your position
(position.py, on the walkable paths of walkmap.py), shares it with your group (share.py), and
Core.view() says what the overlay should draw: you and your friends on the open dungeon map.

All coordinates here are window pixels (the beacon's top-left = the window's top-left).
"""

import math
import threading
import time

import numpy as np

from .atlas import Atlases
from .data import MAP_H, MAP_W, MINIMAP_DIAMETER, Data
from .facing import Facing
from .odometry import Odometry
from .position import N as N_PARTICLES, ParticleFilter
from .recording import Recorder
from .walkmap import WalkMaps

STALE_AFTER = 3.0   # seconds without a good minimap frame: your arrow fades
# Marker sizes in pixels of the 1002-pixel-wide map (both overlays scale them to the canvas)
ARROW_BASE, ARROW_MIN = 26, 20   # your arrow (times the add-on's "Your arrow size")
DOT_BASE, DOT_MIN = 13, 10       # a friend's dot
GLIDE = 0.08        # seconds: friends' dots glide between relay updates (about 15 a second)
SNAP = 30           # map pixels: a bigger jump (a new spot, a new floor) is drawn at once
SHARE_EVERY = 1 / 15  # seconds between position messages to the group
# The minimap atlas (atlas.py): match the minimap against it, paste the minimap into it
ATLAS_EVERY = 0.2
TRAIL_EVERY = 2.5      # yards walked between two minimap pictures kept for the stretch since the last fix
TRAIL_MAX = 320        # (about 800 yards; older ones are dropped)     # seconds between matches
LOCK_SCORE, LOCK_MARGIN, LOCK_SHARE = 0.62, 0.08, 0.35   # a match that nudges the estimate
LOCK_SIGMA = 3.0      # yards
JUMP_SCORE, JUMP_MARGIN = 0.75, 0.12   # a match far from every guess: moves you there
FIND_SCORE, FIND_MARGIN, FIND_SHARE = 0.75, 0.15, 0.5    # no position: found on the whole floor
WALK_FROM_ATLAS_EVERY = 30.0  # seconds: what the atlas knows as floor joins the walk map


def _travel_dir(track, now, span):
    """(speed yards/s, direction degrees) over the last span seconds of (t, east, north), or None."""
    old = [p for p in track if now - p[0] >= span]
    if not old or now - old[-1][0] > span * 1.6:
        return None
    t0, e0, n0 = old[-1]
    _, e1, n1 = track[-1]
    dt = now - t0
    if dt <= 0:
        return None
    return math.hypot(e1 - e0, n1 - n0) / dt, math.degrees(math.atan2(e1 - e0, n1 - n0)) % 360


class Core:
    def __init__(self, share=None, log=lambda *a: None, info=print):
        self.log, self.info = log, info
        self.data = Data()
        self.walkmaps = WalkMaps(self.data)
        self.pf = ParticleFilter(self.data, self.walkmaps, log=log, info=info)
        self.atlases = Atlases(self.data)
        self.odo_yards = 0.0       # yards walked this session (the atlas's clock)
        self.atlas_at = self.atlas_saved = self.atlas_search_at = self.atlas_walk_at = -math.inf
        self.atlas_busy = False
        self.track_at = -math.inf  # (a position line in the log every few seconds)
        self.atlas_found = None    # a whole-floor match from the background search, to apply
        self.context_key = None
        self.context_epoch = 0
        self.pending_match = None
        self.pending_since = None
        self.confidence_match = None
        self.trail = []            # [(odo yards, floor, north, west, yd/px, picture)] since the last fix
        self.trail_start = 0.0     # odo yards at the last fix
        self.pf.on_fix = self._on_fix
        self.recording = Recorder(log=info)
        self.odo = Odometry()
        self.facing = Facing()
        self.share = share
        self.fields = self.beacon = None
        self.mm_key = None
        self.minimap_settle_until = -math.inf
        self.last_good = -math.inf
        self.motion_at = None
        self.track = []            # (time, east, north) yards travelled, last second
        self.east = self.north = 0.0
        self.heading_mm = None     # facing on the minimap (0 = north, clockwise)
        self.art_busy = False
        self.want_full = False     # the platform should hand over a whole frame (map art)
        self.hinted = False
        self.last_share = -math.inf
        self.name = ""
        self.colour = "#cccccc"
        self.shown_friends = {}    # name -> [u, v, time drawn]: where each friend's dot is drawn
        self.counts = {"frames": 0, "minimap_read": 0, "facing_read": 0, "ms": 0.0, "ms_max": 0.0,
                       "atlas_tries": 0, "atlas_locks": 0, "atlas_jumps": 0, "pasted": 0, "repasted": 0}

    # -- per frame -----------------------------------------------------------------------------------

    def frame(self, b, crop, now, full_crop=None):
        """b: the decoded beacon; crop(rect) -> RGB array or None, for rectangles in beacon pixels.
        full_crop: the same for rectangles anywhere in the window (None when only crop exists)."""
        t0 = time.perf_counter()
        try:
            self._frame(b, crop, now, full_crop)
        finally:
            ms = (time.perf_counter() - t0) * 1000
            c = self.counts
            c["frames"] += 1
            c["ms"] += ms
            c["ms_max"] = max(c["ms_max"], ms)

    def _frame(self, b, crop, now, full_crop):
        f = b.fields
        context = (f["dungeon"], f["lm_count"], f["zoom"], f["radius4"], f["indoors"],
                   f["room"], f.get("active_boss", 0), f.get("boss_mask", 0))
        if context != self.context_key:
            if self.context_key and context[0] != self.context_key[0]:
                self.trail = []
                self.trail_start = self.odo_yards
                self.recording.clear()
            self.context_key = context
            self.context_epoch += 1
            self.atlas_found = self.pending_match = self.confidence_match = None
        self.fields, self.beacon = f, b
        self.recording.upload.set_allowed(f.get("contribute", 0) == 1)
        self.name = b.name
        self.colour = b.colour
        mm = b.rect("mm")
        key = (f["mm_w"], f["mm_h"], f["zoom"], f["radius4"], f["dungeon"], f["indoors"])
        if key != self.mm_key:
            previous_key = self.mm_key
            if previous_key is None or previous_key[4] != key[4]:
                self.minimap_settle_until = -math.inf
            elif previous_key[2:4] != key[2:4] and f["dungeon"]:
                floors = self.data.dungeons[f["dungeon"] - 1]["floors"]
                settle = max(self.data.floors[fl].get("zoom_settle_seconds", 0) for fl in floors)
                if settle:
                    # WC recordings show high-score false shifts while the
                    # minimap animates a zoom change. Rebase after it settles;
                    # never turn that scaling into player movement or learning.
                    self.minimap_settle_until = now + settle
                    self._lost_motion()
                    self.motion_at = None
            if self.mm_key is None or key[:2] != self.mm_key[:2]:
                self.odo.reset_static()
                self.facing.reset()
            self.mm_key = key
            self.odo.reset()
        dungeon_key = self.data.dungeons[f["dungeon"] - 1]["key"] if f["dungeon"] else "outside"
        profile = "%s/i%dz%d" % (dungeon_key, f["indoors"], f["zoom"])
        changed_profile = self.pf.calib.key != profile
        self.pf.calib.key = profile
        if changed_profile and self.pf.p is not None and self.pf.dungeon == f["dungeon"]:
            m, sd = self.pf.calib.get()
            self.pf.s = np.exp(self.pf.rng.normal(m, sd, len(self.pf.p)))
            # A pair spanning two settings cannot train either setting alone.
            self.pf.anchor = None
            self.pf.raw[:] = 0
            self.trail = []
            self.trail_start = self.odo_yards
        old_landmark = self.pf.lm_count
        self.pf.on_beacon(f)
        if old_landmark != self.pf.lm_count and f["lm_kind"] in (1, 3):
            self.odo.reset()  # the click anchors the current picture, not the previous step
            self.motion_at = None
        if mm and not f["rotate"] and self.pf.dungeon:
            img = crop(mm)
            if img is not None and img.shape[0] >= 16 and img.shape[1] >= 16:
                self._minimap(img, mm, f, now)
        if f["map_open"]:
            self._capture_art(f, b, full_crop or crop)
        self._share(f, now)
        if now - self.track_at >= 5 and self.pf.dungeon and self.pf.est is not None:
            self.track_at = now
            pf = self.pf
            u, v = self.data.to_map(pf.floor, *pf.est)
            self.info("at map %.0f,%.0f floor %s spread %.1f trust %s scale %.3f (%s)" % (
                u * MAP_W, v * MAP_H, pf.floor, pf.spread, "-" if pf.trust == math.inf else "%.0f" % pf.trust,
                pf.scale, pf.source))

    def _minimap(self, img, mm, f, now):
        if f.get("minimap_blocked", 0) or now < self.minimap_settle_until:
            # Keep diagnostic pictures but never use tooltip/map pixels as
            # terrain, facing, a keyframe, or learned atlas texture.
            self.recording.add(img, f, self.pf, now, self.odo.score, accepted=False)
            return
        radius = f["radius4"] / 4
        if not radius:
            table = MINIMAP_DIAMETER["indoor" if f["indoors"] == 1 else "outdoor"]
            radius = table[min(f["zoom"], 5)] / 2
        ypp = 2 * radius / mm[2]
        dt = max(0.0, now - self.motion_at) if self.motion_at is not None else 0.0
        # 30 yd/s covers ordinary dungeon movement/sprints with ample margin.
        # Missing time is not permission for an unlimited image-matching jump.
        self.odo.max_step = (2.0 + 30.0 * min(dt, 0.5)) / ypp
        rejected_before = self.odo.rejected
        delta = self.odo.step(img)
        if delta is None and dt > 1.0 and self.odo.rejected == rejected_before:
            # A tooltip/scene change can leave the key unable to match forever.
            # Rebase without inventing movement; let the atlas recover pose.
            self._lost_motion()
            self.odo.reset()
            self.motion_at = now
            self.info("minimap match stalled; rebasing and searching learned references")
        if self.odo.rejected != rejected_before:
            self.info("ignored impossible minimap step: %.1f yards in %.3f seconds" % (self.odo.rejected_step * ypp, dt))
            self._lost_motion()
            self.recording.add_case(self.odo.rejection, now, ypp, dt)
            self.recording.add(img, f, self.pf, now, self.odo.score, force=True, accepted=False)
            self.recording.trigger("impossible minimap step", {"kind": "motion", "floor": self.pf.floor,
                                   "yards": self.odo.rejected_step * ypp, "elapsed": dt})
        if delta is not None or self.odo.rejected != rejected_before:
            self.motion_at = now
        if delta is not None:
            self.counts["minimap_read"] += 1
            self.last_good = now
            d_east, d_north = delta[0] * ypp, -delta[1] * ypp
            self.pf.move(d_north, -d_east)
            self.east += d_east
            self.north += d_north
            self.odo_yards += math.hypot(d_east, d_north)
            self.track.append((now, self.east, self.north))
            while self.track and now - self.track[0][0] > 1.0:
                self.track.pop(0)
        # Recovery must not depend on odometry already succeeding. Recording
        # rejected/weak frames is essential to diagnose stalls and obstructions.
        self._atlas(now, ypp * img.shape[1] / self.odo.mask.shape[1])
        self.recording.add(img, f, self.pf, now, self.odo.score, accepted=delta is not None)
        h = self.facing.read_minimap(img, now)
        if h is not None:
            self.counts["facing_read"] += 1
            self.heading_mm = h
        else:
            a = _travel_dir(self.track, now, 0.5)
            if a and a[0] > 2.0:
                self.heading_mm = a[1]   # arrow covered: the way you are moving

    def _lost_motion(self):
        self.pf.motion_valid = False
        self.pf.pose_error = max(15.0, self.pf.pose_error)
        self.pf.trust = max(800.0, self.pf.trust)
        self.trail = []
        self.trail_start = self.odo_yards
        self.track = []
        self.atlas_found = self.pending_match = self.confidence_match = None
        self.context_epoch += 1

    # -- the minimap atlas ---------------------------------------------------------------------------

    def _atlas(self, now, ypp_s):
        """ypp_s: yards per pixel of the odometry's SIZE x SIZE minimap picture (before correction)."""
        pf = self.pf
        if self.atlas_found is not None:
            self._apply_found()
        if now - self.atlas_at < ATLAS_EVERY:
            return
        self.atlas_at = now
        gray = getattr(self.odo, "gray", None)
        floors = pf.floors
        floor = pf.floor if pf.floor is not None else (floors[0] if len(floors) == 1 else None)
        if gray is None or floor is None:
            return
        if gray[self.odo.mask > 0].std() < 2:
            return
        a = self.atlases.get(floor)
        if a is None:
            return
        mask = self.odo.mask
        ypp_s *= pf.scale
        c = self.counts
        if pf.p is None or pf.searching is not None:
            self._atlas_search(a, gray, mask, ypp_s, now)
        elif pf.walked >= 8 or pf.source not in ("entrance", "marked") or pf.guessed:
            # (just after the entrance or your click, those win: the atlas may be what's wrong there)
            n, w = pf.est
            c["atlas_tries"] += 1
            r = a.locate(gray, mask, n, w, ypp_s, min(40.0, 10.0 + 0.25 * pf.trust), self.odo_yards)
            if r is not None:
                N, W, score, second, share = r
                if score >= LOCK_SCORE and score - second >= LOCK_MARGIN and share >= LOCK_SHARE:
                    c["atlas_locks"] += 1
                    if math.hypot(N - n, W - w) <= 3 * max(LOCK_SIGMA, pf.spread):
                        strong = score >= 0.8 and score - second >= 0.12 and share >= 0.5
                        verified = strong and self._confidence_lock(floor, N, W, now)
                        was_guess = pf.guessed
                        pf.observe(N, W, LOCK_SIGMA, verified=verified)
                        if was_guess and not pf.guessed:
                            self.info("tracking confidence recovered from consistent minimap matches")
                    elif (score >= JUMP_SCORE and score - second >= JUMP_MARGIN
                          and self._confirm_match(floor, N, W)):
                        c["atlas_jumps"] += 1
                        self.recording.trigger("atlas relocation", {
                            "floor": floor, "before": [float(n), float(w)], "match": [float(N), float(W)],
                            "score": score, "second": second})
                        self.info("the minimap matches the atlas %.0f yards from the arrow: moved there (%.2f, next best %.2f)" % (
                            math.hypot(N - n, W - w), score, second))
                        pf._init(floor, (N, W), 2.0, N_PARTICLES, "matched")
            if pf.guessed:
                self._atlas_search(a, gray, mask, ypp_s, now)
        if (pf.found and pf.floor == floor and not pf.guessed and pf.spread < 8
                and (not self.trail or self.odo_yards - self.trail[-1][0] >= TRAIL_EVERY)):
            n, w = pf.est
            self.trail.append((self.odo_yards, floor, n, w, ypp_s, np.clip(gray, 0, 255).astype(np.uint8)))
            if len(self.trail) > TRAIL_MAX:
                self.trail.pop(0)
        if pf.found and pf.floor == floor and pf.spread < 5 and not pf.guessed:
            # Only the entrance or your own click may repaint what the atlas already knows (and outweighs
            # it, healing a wrong patch); anything else only fills in parts not seen yet, or the atlas
            # would follow the drift it is there to correct.
            hard = pf.walked < 8 and pf.source in ("entrance", "marked")
            weight = 4.0 if hard else math.exp(-pf.trust / 80.0)
            if weight > 0.1:
                n, w = pf.est
                a.paste(gray, mask, n, w, ypp_s, weight, self.odo_yards, fill_only=not hard,
                        replace=hard and pf.source == "marked")
                c["pasted"] += 1
        if now - self.atlas_saved > 60:
            self.atlas_saved = now
            self.atlases.save()
        if now - self.atlas_walk_at > WALK_FROM_ATLAS_EVERY:
            self.atlas_walk_at = now
            self._walk_from_atlas(floor)

    def _on_fix(self, floor, before, fix, why, sigma):
        """A fix (entrance, boss, your click) after a stretch of dead reckoning: the arrow was off by
        (fix - before). The drift grew along the way, so the pictures of the stretch are pasted again
        with their share of the correction (a loop closure) and outweigh what was pasted on the way.
        That's how the first run of a dungeon teaches a straight atlas for the next ones."""
        if why == "marked" or (before is not None and math.hypot(fix[0] - before[0], fix[1] - before[1]) >= 10):
            self.recording.trigger("position correction", {
                "floor": floor, "before": list(before) if before is not None else None,
                "fix": list(fix), "kind": why, "sigma": sigma,
                "error_yards": math.hypot(fix[0] - before[0], fix[1] - before[1]) if before is not None else None})
        trail, start = self.trail, self.trail_start
        self.trail, self.trail_start = [], self.odo_yards
        if not self.pf.stretch_valid:
            self.info("atlas: broken/inconsistent movement stretch not re-pasted; fresh correction still anchors current view")
            return
        if before is None or sigma > 15 or not trail:
            return
        dn, dw = fix[0] - before[0], fix[1] - before[1]
        span = max(self.odo_yards - start, 1e-6)
        if math.hypot(dn, dw) > 0.35 * span + 3 * sigma:
            self.info("fix (%s) is %.0f yards from the arrow after %.0f yards: the stretch isn't re-pasted" % (
                why, math.hypot(dn, dw), span))
            return
        a = self.atlases.get(floor)
        if a is None:
            return
        weight = 4.0 if sigma <= 5 else 1.0
        mask = self.odo.mask
        k = 0
        for odo, fl, n, w, ypp, gray in trail:
            if fl != floor:
                continue
            f = min(1.0, max(0.0, (odo - start) / span))
            a.paste(gray.astype(np.float32), mask, n + f * dn, w + f * dw, ypp, weight, odo)
            k += 1
        self.counts["repasted"] += k
        self.info("atlas: %d minimap pictures of the last %.0f yards re-pasted with the fix's correction "
                  "(%.1f yards at the end)" % (k, span, math.hypot(dn, dw)))

    def _atlas_search(self, a, gray, mask, ypp, now):
        """No position yet: look for the minimap on the whole floor (in the background: it takes a moment)."""
        if self.atlas_busy or now - self.atlas_search_at < 2.0 or a.coverage() < 3000:
            return
        # Snapshot only when starting a worker, not at every throttled attempt.
        gray, mask = gray.copy(), mask.copy()
        self.atlas_busy = True
        self.atlas_search_at = now
        moved_from = (self.north, self.east)
        epoch, odo = self.context_epoch, self.odo_yards
        pending = self.pending_match
        predicted = None
        if pending is not None and pending[0] == a.floor:
            _, pn, pw, north, east, _, _ = pending
            predicted = (pn + self.north - north, pw - self.east + east)

        def work():
            try:
                r = None
                # Once one picture uniquely identifies a place on the whole
                # floor, validate its predicted continuation locally. Requiring
                # every later picture to be globally unique rejects ordinary
                # corridors even when the movement history disambiguates them.
                if predicted is not None:
                    candidate = a.locate(gray, mask, *predicted, ypp, 12.0, odo)
                    if candidate is not None:
                        _, _, score, second, share = candidate
                        if score >= FIND_SCORE and score - second >= 0.02 and share >= FIND_SHARE:
                            r = candidate
                if r is None:
                    candidate = a.locate_anywhere(gray, mask, ypp, odo)
                    if candidate is not None:
                        _, _, score, second, share = candidate
                        if score >= FIND_SCORE and score - second >= FIND_MARGIN and share >= FIND_SHARE:
                            r = candidate
                if r is not None:
                    N, W, score, second, share = r
                    self.atlas_found = (a.floor, N, W, score, second, moved_from, epoch)
            except Exception as e:  # (a background helper must never stop tracking)
                self.info("atlas search failed:", repr(e))
            finally:
                self.atlas_busy = False
        threading.Thread(target=work, daemon=True).start()

    def _apply_found(self):
        floor, N, W, score, second, (n0, e0), epoch = self.atlas_found
        self.atlas_found = None
        pf = self.pf
        if epoch != self.context_epoch or floor not in pf.floors:
            return  # a room/fix/dungeon/zoom changed while the worker was searching
        if pf.found and not pf.guessed and pf.searching is None:
            return
        N, W = N + (self.north - n0), W - (self.east - e0)   # (you kept walking meanwhile)
        if not self._confirm_match(floor, N, W):
            return
        self.recording.trigger("atlas reacquisition", {
            "floor": floor, "match": [float(N), float(W)], "score": score, "second": second})
        self.info("found you with the minimap atlas (%.2f, next best %.2f)" % (score, second))
        pf._init(floor, (N, W), 3.0, N_PARTICLES, "matched")

    def _confidence_lock(self, floor, n, w, now):
        old = self.confidence_match
        if old is not None:
            fl, pn, pw, north, east, start, last, count = old
            expected = (pn + self.north - north, pw - self.east + east)
            if fl == floor and now - last <= 1.5 and math.hypot(n - expected[0], w - expected[1]) <= 6:
                self.confidence_match = (floor, n, w, self.north, self.east, start, now, count + 1)
                return count >= 2 and now - start >= .5
        self.confidence_match = (floor, n, w, self.north, self.east, now, now, 1)
        return False

    def _confirm_match(self, floor, n, w):
        """Confirm across a short walk, or repeated stable observations over real time."""
        old = self.pending_match
        if old is not None:
            fl, pn, pw, north, east, start, count = old
            expected = (pn + self.north - north, pw - self.east + east)
            if fl == floor and math.hypot(n - expected[0], w - expected[1]) <= 6.0:
                self.pending_match = (floor, n, w, self.north, self.east, start, count + 1)
                stable = self.pending_since is not None and time.monotonic() - self.pending_since >= 2.0
                return count >= 2 and (self.odo_yards - start >= 5.0 or stable)
        self.pending_match = (floor, n, w, self.north, self.east, self.odo_yards, 1)
        self.pending_since = time.monotonic()
        return False

    def _walk_from_atlas(self, floor):
        """Floor the atlas has seen joins the walk map (in the background)."""
        if self.data.floors.get(floor, {}).get("walk_mask"):
            return  # WC has client geometry; seeing a texture doesn't prove it is a floor.
        def work():
            try:
                fm = self.atlases.floor_on_map(floor)
                if fm is not None:
                    self.walkmaps.add_floor(floor, fm)
            except Exception as e:
                self.info("atlas walk map failed:", repr(e))
        threading.Thread(target=work, daemon=True).start()

    def _capture_art(self, f, b, crop):
        """Keep a copy of each floor's map art (once): the walkable paths come from it."""
        floors = self.pf.floors
        if self.art_busy or not (0 < f["shown_floor"] <= len(floors)):
            return
        floor = floors[f["shown_floor"] - 1]
        if self.walkmaps.has_art(floor):
            self.want_full = False
            return
        cv = b.rect("cv")
        art = crop(cv) if cv else None
        if art is None or art.shape[0] < 100:
            self.want_full = True
            return
        self.want_full = False
        self.art_busy = True

        def work():
            try:
                wm = self.walkmaps.save_art(floor, art)
                self.info("saved the map of floor %d: %s" % (floor, "paths found" if wm else "no paths found"))
            except (OSError, ValueError) as error:
                self.info("map cache unavailable:", repr(error))
            finally:
                self.art_busy = False
        threading.Thread(target=work, daemon=True).start()

    def _share(self, f, now):
        sh = self.share
        if sh is None or now - self.last_share < SHARE_EVERY:
            return
        self.last_share = now
        pf = self.pf
        group = f["group"] if f["dungeon"] else 0
        sh.set_room(group, self.name)
        if group and pf.displayable:
            key = self.data.dungeons[pf.dungeon - 1]["key"]
            u, v = self.data.to_map(pf.floor, *pf.est)
            sh.send({"d": key, "f": pf.floor, "u": round(float(u), 4), "v": round(float(v), 4),
                     "c": self.colour, "g": pf.guessed,
                     "ok": now - self.last_good < STALE_AFTER})

    def stats(self, extra=None):
        """A summary since the last call (sent with the logs, about once a minute)."""
        c, n = self.counts, max(1, self.counts["frames"])
        f, pf = self.fields or {}, self.pf
        cov = None
        if pf.floor is not None and pf.floor in self.atlases.atlases:
            cov = round(self.atlases.atlases[pf.floor].coverage())
        out = {"frames": c["frames"], "ms_avg": round(c["ms"] / n, 1), "ms_max": round(c["ms_max"], 1),
               "atlas_tries": c["atlas_tries"], "atlas_locks": c["atlas_locks"], "atlas_jumps": c["atlas_jumps"],
               "pasted": c["pasted"], "repasted": c["repasted"], "atlas_yd2": cov, "scale": round(pf.scale, 3),
               "trust": None if pf.trust == math.inf else round(pf.trust),
               "spread": None if pf.spread == math.inf else round(pf.spread, 1),
               "uncertainty": round(pf.uncertainty, 1) if pf.found else None,
               "active_boss": pf.active_boss, "boss_mask": pf.boss_mask,
               "route_checks": pf.route_checks, "route_used": pf.route_used,
               "motion_rejected": self.odo.rejected, "motion_valid": pf.motion_valid,
               "minimap_read": round(c["minimap_read"] / n, 2), "facing_read": round(c["facing_read"] / n, 2),
               "dungeon": self.data.dungeons[pf.dungeon - 1]["key"] if pf.dungeon else None,
               "floor": pf.floor if pf.dungeon else None, "found": bool(pf.found),
               "fix": pf.source if pf.found else None, "map_open": bool(f.get("map_open")),
               "beacon": f.get("version"), "grouped": bool(f.get("group")),
               "relay": None if self.share is None else bool(self.share.connected),
               "friends": len(self.shown_friends)}
        out.update(extra or {})
        self.counts = {k: 0 for k in self.counts}
        self.counts["ms"] = self.counts["ms_max"] = 0.0
        return out

    # -- what to draw --------------------------------------------------------------------------------

    def map_heading(self):
        """Facing turned into map degrees (the map art may be rotated against north)."""
        h = self.heading_mm
        if h is None or self.pf.est is None:
            return None
        n, w = self.pf.est
        r = math.radians(h)
        u0, v0 = self.data.to_map(self.pf.floor, n, w)
        u1, v1 = self.data.to_map(self.pf.floor, n + math.cos(r), w - math.sin(r))
        return math.degrees(math.atan2((u1 - u0) * MAP_W, -(v1 - v0) * MAP_H)) % 360

    def view(self, now):
        """What the overlay shows: None (nothing) or {"canvas": (x, y, w, h) window pixels,
        "me": {...} or None, "friends": [...]}, positions in map fractions (u, v) of the canvas.
        You: an arrow (with your facing); friends: class-coloured dots with their names."""
        f, pf = self.fields, self.pf
        if not f or not f["map_open"] or not pf.dungeon:
            return None
        cv = self.beacon.rect("cv")
        floors = pf.floors
        if not cv or not 0 < f["shown_floor"] <= len(floors):
            return None
        shown = floors[f["shown_floor"] - 1]
        if pf.p is None and not self.hinted:
            self.hinted = True
            self.info("no starting point yet (you reloaded or started the tracker inside the dungeon): "
                      "walk a little, or Shift+click the dungeon map where you stand")
        me = None
        if pf.displayable and pf.floor == shown:
            u, v = self.data.to_map(pf.floor, *pf.est)
            if -0.02 <= u <= 1.02 and -0.02 <= v <= 1.02:
                hd = self.map_heading()
                me = {"u": round(float(u), 4), "v": round(float(v), 4),
                      "heading": round(hd, 1) if hd is not None else None,
                      "fresh": now - self.last_good < STALE_AFTER,
                      "guess": pf.guessed, "size": self.beacon.arrow_size}
        friends = []
        if self.share is not None:
            key = self.data.dungeons[pf.dungeon - 1]["key"]
            for name, s in self.share.friends(now):
                if s.get("d") == key and s.get("f") == shown:
                    c = s.get("c")
                    if not (isinstance(c, str) and len(c) == 7 and c[0] == "#"):
                        c = "#cccccc"
                    friends.append({"name": name[:24], "u": s["u"], "v": s["v"], "color": c,
                                    "fresh": bool(s.get("ok", True)), "guess": bool(s.get("g"))})
        friends = self._layout(me, friends, cv[2], cv[3], now)
        if me is None and not friends:
            return None
        for f in friends:
            f["size"] = self.beacon.dot_size   # (the addon's "Teammate dots" setting)
        return {"canvas": cv, "me": me, "friends": friends}

    def _layout(self, me, friends, w, h, now):
        """Where friends' dots are drawn: gliding between relay updates, never under your arrow, and
        with the name on the side away from you ("label": "above" or "below")."""
        k = w / MAP_W
        seen = set()
        for f in friends:
            seen.add(f["name"])
            d = self.shown_friends.get(f["name"])
            if d is None or math.hypot((f["u"] - d[0]) * MAP_W, (f["v"] - d[1]) * MAP_H) > SNAP:
                d = self.shown_friends[f["name"]] = [f["u"], f["v"], now]
            else:
                a = 1 - math.exp(-max(0.0, now - d[2]) / GLIDE)
                d[0] += (f["u"] - d[0]) * a
                d[1] += (f["v"] - d[1]) * a
                d[2] = now
            f["u"], f["v"] = d[0], d[1]
        for name in list(self.shown_friends):
            if name not in seen:
                del self.shown_friends[name]
        if me is not None:
            # friends standing on you go on a ring around your arrow, so both stay visible
            arrow = max(ARROW_MIN, ARROW_BASE * k) * (me.get("size") or 1)
            dot = max(DOT_MIN, DOT_BASE * k) * self.beacon.dot_size if self.beacon else max(DOT_MIN, DOT_BASE * k)
            ring = arrow * 0.6 + dot / 2 + 2
            mx, my = me["u"] * w, me["v"] * h
            close = []
            for f in friends:
                dx, dy = f["u"] * w - mx, f["v"] * h - my
                if math.hypot(dx, dy) < ring:
                    a = math.atan2(dy, dx) if math.hypot(dx, dy) > 1 else math.pi / 4
                    close.append([a, f])
            close.sort(key=lambda c: c[0])
            gap = (dot + 4) / ring   # radians between neighbours on the ring
            for i in range(1, len(close)):
                close[i][0] = max(close[i][0], close[i - 1][0] + gap)
            for a, f in close:
                f["u"], f["v"] = (mx + ring * math.cos(a)) / w, (my + ring * math.sin(a)) / h
            for f in friends:
                f["label"] = "below" if f["v"] > me["v"] else "above"
        for f in friends:
            f["u"], f["v"] = round(f["u"], 4), round(f["v"], 4)
            f.setdefault("label", "above")
        return friends

