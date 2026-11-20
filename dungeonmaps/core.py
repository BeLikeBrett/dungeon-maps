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

from .data import MAP_H, MAP_W, MINIMAP_DIAMETER, Data
from .facing import Facing
from .odometry import Odometry
from .position import ParticleFilter
from .walkmap import WalkMaps

STALE_AFTER = 3.0   # seconds without a good minimap frame: your arrow fades
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

    # -- per frame -----------------------------------------------------------------------------------

    def frame(self, b, crop, now, full_crop=None):
        """b: the decoded beacon; crop(rect) -> RGB array or None, for rectangles in beacon pixels.
        full_crop: the same for rectangles anywhere in the window (None when only crop exists)."""
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
        if me is None and not friends:
            return None
        return {"canvas": cv, "me": me, "friends": friends}

