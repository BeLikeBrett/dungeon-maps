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

from .data import MAP_H, MAP_W, MINIMAP_DIAMETER, Data
from .facing import Facing
from .odometry import Odometry
from .position import ParticleFilter
from .walkmap import WalkMaps

STALE_AFTER = 3.0   # seconds without a good minimap frame: your arrow fades
# Marker sizes in pixels of the 1002-pixel-wide map (both overlays scale them to the canvas)
ARROW_BASE, ARROW_MIN = 26, 20   # your arrow (times the add-on's "Your arrow size")
DOT_BASE, DOT_MIN = 13, 10       # a friend's dot
GLIDE = 0.08        # seconds: friends' dots glide between relay updates (about 15 a second)
SNAP = 30           # map pixels: a bigger jump (a new spot, a new floor) is drawn at once
SHARE_EVERY = 1 / 15  # seconds between position messages to the group


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
        self.pf = ParticleFilter(self.data, self.walkmaps, log=log)
        self.odo = Odometry()
        self.facing = Facing()
        self.share = share
        self.fields = None
        self.mm_key = None
        self.last_good = -math.inf
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
        self.counts = {"frames": 0, "minimap_read": 0, "facing_read": 0, "ms": 0.0, "ms_max": 0.0}

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
        self.fields, self.beacon = f, b
        self.name = b.name
        self.colour = b.colour
        mm = b.rect("mm")
        key = (f["mm_w"], f["mm_h"], f["zoom"], f["radius4"], f["dungeon"])
        if key != self.mm_key:
            if self.mm_key is None or key[:2] != self.mm_key[:2]:
                self.odo.reset_static()
                self.facing.reset()
            self.mm_key = key
            self.odo.reset()
        self.pf.on_beacon(f)
        if mm and not f["rotate"] and self.pf.dungeon:
            img = crop(mm)
            if img is not None and img.shape[0] >= 16 and img.shape[1] >= 16:
                self._minimap(img, mm, f, now)
        if f["map_open"]:
            self._capture_art(f, b, full_crop or crop)
        self._share(f, now)

    def _minimap(self, img, mm, f, now):
        delta = self.odo.step(img)
        if delta is not None:
            self.counts["minimap_read"] += 1
            self.last_good = now
            radius = f["radius4"] / 4
            if not radius:
                table = MINIMAP_DIAMETER["indoor" if f["indoors"] == 1 else "outdoor"]
                radius = table[min(f["zoom"], 5)] / 2
            ypp = 2 * radius / mm[2]
            d_east, d_north = delta[0] * ypp, -delta[1] * ypp
            self.pf.move(d_north, -d_east)
            self.east += d_east
            self.north += d_north
            self.track.append((now, self.east, self.north))
            while self.track and now - self.track[0][0] > 1.0:
                self.track.pop(0)
        h = self.facing.read_minimap(img, now)
        if h is not None:
            self.counts["facing_read"] += 1
            self.heading_mm = h
        else:
            a = _travel_dir(self.track, now, 0.5)
            if a and a[0] > 2.0:
                self.heading_mm = a[1]   # arrow covered: the way you are moving

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
        if group and pf.found:
            key = self.data.dungeons[pf.dungeon - 1]["key"]
            u, v = self.data.to_map(pf.floor, *pf.est)
            sh.send({"d": key, "f": pf.floor, "u": round(float(u), 4), "v": round(float(v), 4),
                     "c": self.colour, "g": pf.source == "found by walking",
                     "ok": now - self.last_good < STALE_AFTER})

    def stats(self, extra=None):
        """A summary since the last call (sent with the logs, about once a minute)."""
        c, n = self.counts, max(1, self.counts["frames"])
        f, pf = self.fields or {}, self.pf
        out = {"frames": c["frames"], "ms_avg": round(c["ms"] / n, 1), "ms_max": round(c["ms_max"], 1),
               "minimap_read": round(c["minimap_read"] / n, 2), "facing_read": round(c["facing_read"] / n, 2),
               "dungeon": self.data.dungeons[pf.dungeon - 1]["key"] if pf.dungeon else None,
               "floor": pf.floor if pf.dungeon else None, "found": bool(pf.found),
               "fix": pf.source if pf.found else None, "map_open": bool(f.get("map_open")),
               "beacon": f.get("version"), "grouped": bool(f.get("group")),
               "relay": None if self.share is None else bool(self.share.connected),
               "friends": len(self.shown_friends)}
        out.update(extra or {})
        self.counts = {"frames": 0, "minimap_read": 0, "facing_read": 0, "ms": 0.0, "ms_max": 0.0}
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
                      "walk a little, or right-click the dungeon map where you stand")
        me = None
        if pf.found and pf.floor == shown:
            u, v = self.data.to_map(pf.floor, *pf.est)
            if -0.02 <= u <= 1.02 and -0.02 <= v <= 1.02:
                hd = self.map_heading()
                me = {"u": round(float(u), 4), "v": round(float(v), 4),
                      "heading": round(hd, 1) if hd is not None else None,
                      "fresh": now - self.last_good < STALE_AFTER,
                      "guess": pf.source == "found by walking", "size": self.beacon.arrow_size}
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
            dot = max(DOT_MIN, DOT_BASE * k)
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

