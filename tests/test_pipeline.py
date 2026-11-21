"""End to end without the game: WoW's window frames (as the screencast portal delivers them) with the
addon's 2 px beacon in the corner, a minimap showing a synthetic dungeon, and the dungeon map open,
fed through the real Tracker at 60 frames a second. The window sits on a fake screen (grim and niri
replaced) so the overlay placement is checked too.

  1. walk from Ragefire Chasm's entrance with a deliberately wrong minimap scale (4 %), with and
     without the walkable-path map: the paths must hold the arrow on course;
  2. the arrow's facing against the truth while turning;
  3. boss pins must not teleport an already tracked player (including ranged pulls);
  4. no starting point at all: the guesses spread over the paths must find you by walking;
  5. friends: positions arriving from the relay are drawn when they are on the shown floor.
"""
import os as _os, tempfile as _tempfile  # noqa: E401
if not _os.environ.get("DUNGEONMAPS_TEST_ISOLATED"):  # never touch the real atlas, calibration or caches
    _tmp = _tempfile.mkdtemp(prefix="dungeonmaps-test-")
    _os.environ.update(XDG_DATA_HOME=_tmp, XDG_STATE_HOME=_tmp, LOCALAPPDATA=_tmp, DUNGEONMAPS_TEST_ISOLATED="1")

import json
import math
import os
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
from dungeonmaps import beacon, linux, walkmap  # noqa: E402
from dungeonmaps.data import Data  # noqa: E402
import test_odometry as sim  # noqa: E402
from test_beacon import ADDONS  # noqa: E402

OUT_W, OUT_H = 2560, 1440
WIN_W, WIN_H = 2544, 1349
WIN = (8, 83)                       # the window's top-left on the output (bar above it)
MM_AT = (2290.4, 64.2, 189, 189)    # window pixels
CANVAS_AT = (760.3, 300.7, 1002 * 0.8 * 1349 / 768, 668 * 0.8 * 1349 / 768)
RFC = 213
DT = 1 / 60


def encode(fields):
    """Python twin of the addon's beaconCells(): fields -> the cell colours."""
    bits = []
    legacy = fields.get("version") == 4
    layout = beacon.FIELDS[:-3] if legacy else beacon.FIELDS[:-1] if fields.get("version") == 5 else beacon.FIELDS
    for name, n in layout:
        v = max(0, min(2 ** n - 1, int(math.floor(fields.get(name, 0) + 0.5))))
        bits += [(v >> (n - 1 - i)) & 1 for i in range(n)]
    cells = []
    for c in range((54 if legacy else beacon.CELLS) - beacon.HEADER - 1):
        v = 0
        for b in (bits[c * 9:(c + 1) * 9] + [0] * 9)[:9]:
            v = v * 2 + b
        cells.append(v)
    cells.append(sum(cells) % 512)
    header = [(7, 0, 7), (0, 7, 0), (0, 1, 2), (3, 4, 5), (6, 7, 0)]
    cols = [tuple(round(l * 255 / 7) for l in h) for h in header]
    cols += [(round((v >> 6) * 255 / 7), round(((v >> 3) & 7) * 255 / 7), round((v & 7) * 255 / 7)) for v in cells]
    return cols


def check_encoder_matches_lua():
    out = subprocess.run(["lua5.1", os.path.join(HERE, "beacon_harness.lua"), ADDONS], capture_output=True, text=True, check=True).stdout
    info = json.loads([l for l in out.splitlines() if l.startswith("{")][-1])
    img = np.zeros((20, 200, 3), np.uint8)
    for i, c in enumerate(info["cells"]):
        img[0:2, 2 * i:2 * i + 2] = c
    b = beacon.find(img)
    mine = encode(b.fields)
    lua = [tuple(c) for c in info["cells"]]
    assert all(max(abs(a - c) for a, c in zip(x, y)) <= 1 for x, y in zip(mine, lua)), (mine, lua)
    print("Python encoder == addon Lua encoder")


class FakeFrame:
    def __init__(self, img, serial):
        self.img, self.w, self.h, self.serial = img, WIN_W, WIN_H, serial

    def crop(self, x, y, w, h):
        x0, y0 = max(0, int(round(x))), max(0, int(round(y)))
        x1, y1 = min(self.w, int(round(x + w))), min(self.h, int(round(y + h)))
        return self.img[y0:y1, x0:x1].copy() if x1 > x0 and y1 > y0 else None


class FakeGame:
    def __init__(self, seed=2, radius_bias=1.0):
        self.world = sim.world(void=True, seed=5)
        self.rng = np.random.default_rng(seed)
        self.data = Data()
        self.ppy = MM_AT[2] / 120.0       # minimap pixels per yard (view radius 60)
        self.radius_bias = radius_bias    # what the beacon claims vs the truth
        self.heading = 0.0
        self.t = 0.0
        self.lm_u, self.lm_v = 612 / 1002, 47 / 668
        self.N, self.W = self.data.to_world(RFC, self.lm_u, self.lm_v)
        self.cx0, self.cy0 = 1300.0, 1300.0
        while self.world[int(self.cy0), int(self.cx0)] < 20:
            self.cx0 += 7
        self.N0, self.W0 = self.N, self.W
        self.lm_count, self.lm_kind = 1, 1
        self.map_open = 1
        self.group, self.name, self.arrow_size = 0, "Breziath", 1.0
        self.win = np.full((WIN_H, WIN_W, 3), 40, np.uint8)
        self.serial = 0

    def img_xy(self, N=None, W=None):
        N = self.N if N is None else N
        W = self.W if W is None else W
        return self.cx0 + (self.W0 - W) * self.ppy, self.cy0 + (self.N0 - N) * self.ppy

    def walk(self, dt, speed=7.0, turn_sd=0.6):
        for _ in range(36):  # stay in the halls
            ex, ey = self.img_xy()
            h = math.radians(self.heading)
            ax, ay = ex + 4 * self.ppy * math.sin(h), ey - 4 * self.ppy * math.cos(h)
            if self.world[int(ay), int(ax)] > 20 and 200 < ax < 2400 and 200 < ay < 2400:
                break
            self.heading += 10
        h = math.radians(self.heading)
        self.N += speed * dt * math.cos(h)
        self.W -= speed * dt * math.sin(h)
        self.heading = (self.heading + self.rng.normal(0, turn_sd)) % 360
        self.t += dt

    def walk_map(self):
        """The synthetic dungeon's halls drawn onto Ragefire's map: a walk map that matches the world."""
        vv, uu = np.mgrid[0:walkmap.MAP_H, 0:walkmap.MAP_W]
        N, W = self.data.to_world(RFC, (uu + 0.5) / walkmap.MAP_W, (vv + 0.5) / walkmap.MAP_H)
        x, y = self.img_xy(N, W)
        ok = (x >= 0) & (x < self.world.shape[1] - 1) & (y >= 0) & (y < self.world.shape[0] - 1)
        walk = np.zeros(N.shape, bool)
        walk[ok] = self.world[y[ok].astype(int), x[ok].astype(int)] > 20
        return walkmap.WalkMap(walk, np.zeros_like(walk), self.data.px_per_yard(RFC))

    def frame(self):
        img = self.win
        f = dict(version=beacon.FORMAT_VERSION, map_open=self.map_open, indoors=1, rotate=0, zoom=3, radius4=240 * self.radius_bias,
                 dungeon=1, shown_floor=1, lm_count=self.lm_count, lm_kind=self.lm_kind, lm_floor=1,
                 lm_u=self.lm_u * 4095, lm_v=self.lm_v * 4095, room=0,
                 mm_x=MM_AT[0] + 4096, mm_y=MM_AT[1] + 4096, mm_w=MM_AT[2], mm_h=MM_AT[3],
                 cv_x=CANVAS_AT[0] + 4096, cv_y=CANVAS_AT[1] + 4096, cv_w=CANVAS_AT[2], cv_h=CANVAS_AT[3],
                 group=self.group, name_len=len(self.name), arrow_size=self.arrow_size * 10, cr=1.0 * 31,
                 cg=0.96 * 31, cb=0.41 * 31, **{"n%d" % i: c for i, c in enumerate(self.name.encode())})
        for i, c in enumerate(encode(f)):
            img[0:2, 2 * i:2 * i + 2] = c
        ex, ey = self.img_xy()
        view = sim.dress(sim.crop(self.world, ex, ey), self.heading, self.t, self.rng)
        mx, my = int(round(MM_AT[0])), int(round(MM_AT[1]))
        img[my:my + 189, mx:mx + 189] = view
        self.serial += 1
        return FakeFrame(img, self.serial)

    def screen_grab(self, output=None, region=None):
        scr = np.full((OUT_H, OUT_W, 3), 30, np.uint8)
        scr[WIN[1]:WIN[1] + WIN_H, WIN[0]:WIN[0] + WIN_W] = self.win[:OUT_H - WIN[1], :OUT_W - WIN[0]]
        if region:
            x, y, w, h = (int(round(v)) for v in region)
            return scr[y:y + h, x:x + w].copy()
        return scr

    def truth(self):
        return self.data.to_map(RFC, self.N, self.W)


def make_tracker(game, walk=True, share=None):
    linux.outputs = lambda: [{"name": "DP-1", "x": 0, "y": 0, "w": OUT_W, "h": OUT_H, "scale": 1.0}]
    linux.wow_windows = lambda: (True, ["DP-1"])
    linux.grab = game.screen_grab
    t = linux.LinuxTracker(use_portal=False, share=False)
    c = t.core
    c.share = share
    c.walkmaps.has_art = lambda floor: True
    wm = game.walk_map() if walk else None
    c.walkmaps.get = lambda floor: wm
    c.pf.rng = np.random.default_rng(7)
    c.pf.routes.enabled = False  # synthetic geography has no relation to the real RFC guide
    c.recording.enabled = False  # tested separately; synthetic runs aren't local player evidence
    t.sync_place = True
    t.emitted = []
    t.emit = lambda msg: t.emitted.append(msg)
    return t


def run(t, game, seconds, now, track=None, **walk):
    """Walk; returns (now, last error yards, worst error yards)."""
    ppy_map = game.data.px_per_yard(RFC)
    worst = last = 0.0
    for _ in range(int(round(seconds / DT))):
        game.walk(DT, **walk)
        now += DT
        t.window_frame(game.frame(), now)
        m = t.emitted[-1]
        if not m["show"] or not m["me"]:
            last = math.inf
            continue
        me = m["me"]
        tu, tv = game.truth()
        # where the overlay draws vs where the truth would be drawn, back in yards
        sx, sy = m["cx"] + me["u"] * m["cw"], m["cy"] + me["v"] * m["ch"]
        tx = WIN[0] + CANVAS_AT[0] + tu * CANVAS_AT[2]
        ty = WIN[1] + CANVAS_AT[1] + tv * CANVAS_AT[3]
        last = math.hypot(sx - tx, sy - ty) / (CANVAS_AT[2] / 1002 * ppy_map)
        worst = max(worst, last)
        if track is not None and me.get("heading") is not None:
            track.append(abs((me["heading"] - game.heading + 180) % 360 - 180))
    return now, last, worst


def main():
    check_encoder_matches_lua()

    # 1. wrong minimap scale, with and without the paths
    res = {}
    for walk in (False, True):
        game = FakeGame(radius_bias=1.04)
        t = make_tracker(game, walk)
        now, last, worst = run(t, game, 60, 0.0)
        res[walk] = (last, worst)
        print("4%% scale error, %s: after 60 s / 420 yards the arrow is %.1f yards off (worst %.1f)" % (
            "paths on " if walk else "paths off", last, worst))
    assert res[True][0] < 6 and res[True][0] < res[False][0], res

    # 2. facing, while running and turning a lot (correct scale from here on)
    game = FakeGame()
    t = make_tracker(game)
    errs = []
    now, last, worst = run(t, game, 40, 0.0, track=errs, turn_sd=2.0)
    late = np.array(errs[len(errs) // 2:])
    print("facing (2nd half, arrow learned: %s): median %.1f deg, 95%% %.1f deg; position %.1f yards off" % (
        t.core.facing.ready, np.median(late), np.percentile(late, 95), last))
    assert t.core.facing.ready and np.median(late) < 5, np.median(late)
    assert last < 4, last

    # the map closes: the very first frame without it hides the arrow, before anything else runs
    import time as _t
    shown = t.emitted[-1]["show"]
    game.map_open = 0
    calls = []
    orig = t.core.frame
    t.core.frame = lambda *a, **k: (calls.append(t.emitted[-1]["show"]), orig(*a, **k))  # on screen when work began
    fr = game.frame()
    t0 = _t.perf_counter()
    t.window_frame(fr, now + DT)
    ms = 1000 * (_t.perf_counter() - t0)
    del t.core.frame
    game.map_open = 1
    print("map closed: arrow hidden on that same frame (shown before: %s; hidden before other work: %s; %.2f ms)" % (
        shown, calls == [False], ms))
    assert shown and calls == [False] and t.emitted[-1] == {"show": False}

    # 3. A boss pin is the creature's spawn, not the ranged player's position.
    t.core.atlases.get = lambda floor: None
    # (toward the middle of the map, so the spots stay on it: the beacon clamps them to its edges)
    cn, cw = game.data.to_world(RFC, 0.5, 0.5)
    k = 80 / max(math.hypot(cn - game.N, cw - game.W), 1e-6)
    dn, dw = (cn - game.N) * k, (cw - game.W) * k            # "the boss spot" 80 yards inwards
    tu, tv = game.data.to_map(RFC, game.N + dn, game.W + dw)
    game.lm_u, game.lm_v, game.lm_count, game.lm_kind = tu, tv, 2, 2
    before = t.core.pf.est.copy()
    now, _, _ = run(t, game, DT, now)
    assert math.hypot(*(t.core.pf.est - before)) < 3, "a far boss pin must not teleport a tracked player"
    # a near boss pull while you are tracked (here: just after your Shift+click) doesn't move you
    game.lm_u, game.lm_v = game.data.to_map(RFC, game.N, game.W)
    game.lm_count, game.lm_kind = 3, 3
    now, _, _ = run(t, game, DT, now)
    assert t.core.pf.found, t.core.pf.spread
    before = t.core.pf.est.copy()
    game.lm_u, game.lm_v = game.data.to_map(RFC, game.N + 0.25 * dn, game.W + 0.25 * dw)  # 20 yards away
    game.lm_count, game.lm_kind = 4, 2
    now, _, _ = run(t, game, DT, now)
    moved = math.hypot(*(t.core.pf.est - before))
    print("far boss pin kept tracked position; near boss pull moved %.1f yards" % moved)
    assert moved < 3, moved

    # 4. no starting point: tracker started inside the dungeon
    game = FakeGame(seed=11)
    game.lm_count, game.lm_kind = 0, 0
    t = make_tracker(game)
    t.core.atlases.get = lambda floor: None   # (found by walking; the atlas search is test_atlas's)
    found_at = None
    for k in range(120):
        now, last, _ = run(t, game, 1.0, now)
        if t.core.pf.found and found_at is None:
            found_at = k + 1
        if found_at and k + 1 >= found_at + 10:
            break
    guess = t.emitted[-1]["me"].get("guess")
    print("no starting point: found after %s s of walking, then %.1f yards off (shown as \"You?\": %s)" % (
        found_at, last, guess))
    assert found_at is not None and last < 8 and guess is True, (found_at, last)

    # 5. friends: what the relay hands over is drawn (only on the shown floor), and we send ours
    class FakeShare:
        def __init__(self):
            self.room, self.sent = None, []
            self.others = [("Byai", {"d": "ragefirechasm", "f": RFC, "u": 0.4, "v": 0.5, "c": "#ff7c0a", "g": False, "ok": True}),
                           ("Thicc", {"d": "ragefirechasm", "f": 999, "u": 0.1, "v": 0.1, "h": None})]

        def set_room(self, group, name):
            self.room = (group, name)

        def send(self, state):
            self.sent.append(state)

        def friends(self, now=None):
            return self.others
    sh = FakeShare()
    game = FakeGame()
    game.group = 0x2EF870D1
    game.arrow_size = 1.6
    key = game.data.dungeons[0]["key"]
    for _, st in sh.others:
        st["d"] = key
    t = make_tracker(game, share=sh)
    now, last, _ = run(t, game, 3.0, now)
    m = t.emitted[-1]
    names = [f["name"] for f in m["friends"]]
    mine = sh.sent[-1]
    print("friends: drawn %s (Thicc is on another floor); joined room %08x as %s; sent %d positions in 3 s, "
          "last %.3f,%.3f" % (names, sh.room[0], sh.room[1], len(sh.sent), mine["u"], mine["v"]))
    assert names == ["Byai"] and sh.room == (0x2EF870D1, "Breziath") and 30 <= len(sh.sent) <= 50
    assert mine["d"] == key and mine["f"] == RFC and abs(mine["u"] - m["me"]["u"]) < 0.01
    fr = m["friends"][0]
    print("friend dot: colour %s, no facing (%s); our class colour sent %s; our arrow size %.1fx" % (
        fr["color"], "heading" not in fr, mine["c"], m["me"]["size"]))
    assert fr["color"] == "#ff7c0a" and "heading" not in fr and mine["c"] == "#fff76b" and m["me"]["size"] == 1.6
    print("PASS pipeline")


if __name__ == "__main__":
    main()
