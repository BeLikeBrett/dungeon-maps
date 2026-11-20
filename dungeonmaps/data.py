"""Dungeon data (data/dungeons.json, made by tools/extract.lua from Forever Dungeon Routes' data, the
same run that makes the addon's Data.lua: the beacon sends indexes) and the map maths."""

import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MAP_W, MAP_H = 1002, 668
MINIMAP_DIAMETER = {          # yards across the minimap when the game doesn't say (HereBeDragons)
    "indoor": [300, 240, 180, 120, 80, 50],
    "outdoor": [466 + 2 / 3, 400, 333 + 1 / 3, 266 + 2 / 3, 200, 133 + 1 / 3],
}


def user_dir(kind):
    """Where this program keeps things: kind "data" (map art, walk maps) or "state" (settings, log)."""
    if sys.platform == "win32":
        base = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "DungeonMaps")
        return os.path.join(base, kind)
    env = {"data": "XDG_DATA_HOME", "state": "XDG_STATE_HOME"}[kind]
    default = {"data": "~/.local/share", "state": "~/.local/state"}[kind]
    return os.path.join(os.environ.get(env) or os.path.expanduser(default), "dungeon-maps")


class Data:
    def __init__(self, path=os.path.join(HERE, "data", "dungeons.json")):
        with open(path) as fh:
            d = json.load(fh)
        self.dungeons = d["dungeons"]
        self.floors = {int(k): v for k, v in d["floors"].items()}
        self.rooms = d["rooms"]
        self.bosses = d.get("bosses", {})
        self.entry = d.get("entry", {})

    def to_map(self, floor, n, w):
        """World (north, west yards) -> map (u, v) on a floor (FDR's DR:WorldToFloor)."""
        info = self.floors[floor]
        f = info.get("frame")
        if f:
            return f[0] * n + f[1] * w + f[2], f[3] * n + f[4] * w + f[5]
        minx, miny, maxx, maxy = info["world"]
        return (maxy - w) / (maxy - miny), (maxx - n) / (maxx - minx)

    def to_world(self, floor, u, v):
        info = self.floors[floor]
        f = info.get("frame")
        if f:
            a, b, c, d, e, g = f
            det = a * e - b * d
            uu, vv = u - c, v - g
            return (e * uu - b * vv) / det, (a * vv - d * uu) / det
        minx, miny, maxx, maxy = info["world"]
        return maxx - v * (maxx - minx), maxy - u * (maxy - miny)

    def px_per_yard(self, floor):
        info = self.floors[floor]
        f = info.get("frame")
        if f:
            return math.hypot(f[0] * MAP_W, f[1] * MAP_W)
        minx, miny, maxx, maxy = info["world"]
        return MAP_W / (maxy - miny)


def box_extent(box):
    """Upright bounding box of a room box, in map pixels: (left, top, right, bottom)."""
    _, u, v, w, h, ang = box
    c, s = abs(math.cos(ang)), abs(math.sin(ang))
    bw, bh = w * c + h * s, w * s + h * c
    x, y = u * MAP_W, v * MAP_H
    return x - bw / 2, y - bh / 2, x + bw / 2, y + bh / 2


def room_main_floor(room):
    area = {}
    for b in room["boxes"]:
        area[b[0]] = area.get(b[0], 0) + b[3] * b[4]
    return min(area, key=lambda f: (-area[f], f)) if area else None


def room_center(room, floor):
    su = sv = tot = 0.0
    for b in room["boxes"]:
        if b[0] == floor:
            a = b[3] * b[4]
            su, sv, tot = su + b[1] * a, sv + b[2] * a, tot + a
    return (su / tot, sv / tot) if tot else None
