"""Route ambiguity, atlas self-confirmation, run context, and name regressions."""
import os
import tempfile
import sys
import time
import threading
import json
import subprocess

os.environ.update(XDG_DATA_HOME=tempfile.mkdtemp(), XDG_STATE_HOME=tempfile.mkdtemp())
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
from dungeonmaps.routes import RouteGraph
from dungeonmaps.data import Data
from dungeonmaps.atlas import FloorAtlas
from dungeonmaps.core import Core
from dungeonmaps.position import ParticleFilter
from dungeonmaps import beacon
from test_pipeline import encode


class Coordinates:
    def to_world(self, floor, u, v):
        return u, v


def route_tests():
    # Parallel lanes connect at the far end of a U. Nearby is not connected here.
    graph = RouteGraph(Coordinates(), 1, [{"pts": [0, 0, 0, 100, 20, 100, 20, 0]}])
    p = np.array([[0., 10.], [20., 10.]])
    previous = np.array([[0., 7.], [0., 7.]])
    w, _ = graph.weights(p, previous, 3.)
    assert w[0] > w[1] * 1.4, w
    # The actual connection and walking backwards carry no crossing penalty.
    w, _ = graph.weights(np.array([[20., 100.], [0., 7.]]),
                         np.array([[0., 100.], [0., 10.]]), 20.)
    assert np.all(w > .98), w
    # Unknown shortcuts stay possible; disconnected route scraps never assert walls.
    graph = RouteGraph(Coordinates(), 1, [{"pts": [0, 0, 0, 100]}, {"pts": [20, 0, 20, 100]}])
    w, _ = graph.weights(p, previous, 3.)
    assert np.all(w > .98), w
    w, near = graph.weights(np.array([[200., 200.]]), None, 3.)
    assert not near.any() and w[0] >= .85
    # Repeated soft evidence can resolve a drifting lane without snapping positions.
    graph = RouteGraph(Coordinates(), 1, [{"pts": [0, 0, 0, 100]}])
    w, _ = graph.weights(np.array([[0., 30.], [25., 30.]]), None, 3.)
    odds = (w[0] / w[1]) ** 20
    assert odds > 10, odds
    print("PASS route connections, reverse travel, missing paths, and gentle drift correction")


def atlas_tests():
    rng = np.random.default_rng(1)
    gray = rng.uniform(40, 220, (32, 32)).astype(np.float32)
    mask = np.ones((32, 32))
    a = FloorAtlas(213, 100., 100., 200, 200)
    a.paste(gray, mask, 0., 0., 1., odo=0.)
    assert a.render(0., 0., 1., 32, odo=100.)[1].sum() > 500
    a.paste(gray, mask, 0., 0., 1., odo=100.)
    assert a.render(0., 0., 1., 32, odo=101.)[1].sum() == 0
    # An explicit correction overrides old texture, while unobserved pixels survive.
    corrected = 255 - gray
    a.paste(corrected, mask, 0., 0., 1., weight=4., odo=200., replace=True)
    rendered, valid = a.render(0., 0., 1., 32)
    clean = FloorAtlas(213, 100., 100., 200, 200)
    clean.paste(corrected, mask, 0., 0., 1., weight=4.)
    expected, _ = clean.render(0., 0., 1., 32)
    assert np.max(np.abs(rendered[valid > 0] - expected[valid > 0])) < 1e-4
    c = Core(info=lambda *a: None)
    c.pf.dungeon = 1
    c.odo_yards = 55.
    done, args = threading.Event(), []

    class Atlas:
        floor = 213
        def coverage(self): return 4000
        def locate_anywhere(self, *values):
            args.append(values[-1]); done.set()

    c._atlas_search(Atlas(), gray, mask, 1., 0.)
    assert done.wait(2) and args == [55.], args
    # One impressive peak, or repeated stationary frames, cannot relocate you.
    assert not c._confirm_match(213, 0., 0.)
    assert not c._confirm_match(213, 0., 0.)
    assert not c._confirm_match(213, 0., 0.)
    c.north = c.odo_yards = 61.
    assert c._confirm_match(213, 61., 0.)
    # A worker result from before a fix/dungeon/zoom change is discarded.
    c.atlas_found = (213, 10., 10., .99, .1, (0., 0.), c.context_epoch - 1)
    c._apply_found()
    assert c.pf.p is None
    # Once a global seed is unique, movement history can disambiguate a later
    # corridor picture even though that individual picture isn't globally unique.
    c2 = Core(info=lambda *a: None)
    c2.pending_match = (213, 0., 0., 0., 0., 0., 1)
    class Continuation(Atlas):
        def locate(self, *values):
            assert values[-1] == 0.0
            return 0., 0., .8, .77, 1.
        def locate_anywhere(self, *values):
            raise AssertionError("credible local continuation should retain the global seed")
    c2._atlas_search(Continuation(), gray, mask, 1., 0.)
    deadline = time.monotonic() + 2
    while c2.atlas_busy and time.monotonic() < deadline:
        time.sleep(.001)
    assert c2.atlas_found is not None
    print("PASS atlas freshness, relocation corroboration, and stale worker rejection")


def context_tests():
    data = Data()
    class NoMaps:
        def get(self, floor): return None
    pf = ParticleFilter(data, NoMaps(), rng=np.random.default_rng(1))
    pf.dungeon = 1
    pf._init(213, (0., 0.), 1., 500, "marked")
    pf.trust = 1000.
    assert pf.spread < 3 and pf.uncertainty >= 19 and pf.guessed
    pf.observe(0., 0., 3.)
    assert pf.trust == 1000.
    pf._init(213, (0., 0.), 1., 500, "matched")
    assert pf.trust == 1000. and pf.guessed
    # A real manual fix does restore confidence.
    pf._init(213, (0., 0.), 1., 500, "marked")
    assert not pf.guessed
    f = dict(dungeon=1, lm_count=0, lm_kind=0, lm_floor=0, room=0,
             active_boss=2, boss_mask=1)
    pf.on_beacon(f)
    assert pf.active_boss == 2 and pf.boss_mask == 1
    f.update(active_boss=0, boss_mask=0)
    pf.on_beacon(f)
    assert pf.active_boss == 0 and pf.boss_mask == 0
    # Fight context distinguishes two position hypotheses without snapping any
    # particles, and ends when the boss dies or the whole group is far from its pin.
    boss = data.bosses[data.dungeons[0]["key"]][0]
    centre = np.asarray(data.to_world(boss["floor"], boss["x"], boss["y"]))
    fight = ParticleFilter(data, NoMaps(), rng=np.random.default_rng(1))
    fight.dungeon = 1
    fight._init(boss["floor"], centre, 1., 500, "marked")
    fight.p[250:] += 100.
    positions = fight.p.copy()
    fight.active_boss = 1
    fight._boss_hint(5.)
    assert fight.w[:250].sum() > fight.w[250:].sum() and np.array_equal(fight.p, positions)
    fight.boss_mask = 1
    weights = fight.w.copy()
    fight._boss_hint(5.)
    assert np.array_equal(fight.w, weights)
    fight.boss_mask = 0
    fight.p += 500.
    fight._boss_hint(5.)
    assert np.array_equal(fight.w, weights)
    # A weak spawn-pin recovery cannot teach the atlas or reset a real anchor.
    anchor = pf.anchor
    pf._init(213, (80., 0.), 8., 500, "boss")
    assert pf.anchor is anchor and pf.trust >= 800 and pf.guessed
    # Resampling must carry each particle's own preceding route position.
    pf.route_previous = pf.p.copy()
    pf.w[:] = 0
    pf.w[0] = 1
    old = pf.p[0].copy()
    pf._resample_if_needed()
    assert np.all(pf.route_previous == old) and len(pf.route_previous) == len(pf.p)
    # A uniquely named room on a new floor must not leave a confident old-floor arrow.
    for i, dungeon in enumerate(data.dungeons, 1):
        candidates = data.rooms.get(dungeon["key"], [])
        if len(dungeon["floors"]) > 1:
            found = next(((j, r) for j, r in enumerate(candidates, 1)
                          if len({b[0] for b in r["boxes"]}) == 1
                          and r["boxes"][0][0] != dungeon["floors"][0]), None)
            if found:
                j, room = found
                pf.dungeon = i
                pf._init(dungeon["floors"][0], (0., 0.), 1., 500, "marked")
                pf.room = 0
                pf.on_beacon(dict(dungeon=i, lm_count=0, lm_kind=0, lm_floor=0, room=j))
                assert pf.floor == room["boxes"][0][0] and pf.est is None
                break
    else:
        raise AssertionError("missing multi-floor room fixture")
    # v4 remains usable until /reload; v5 fields survive both encoders.
    for version in (4, 5, 6):
        fields = dict(version=version, active_boss=27, boss_mask=(1 << 31) + 13, contribute=1)
        cols = encode(fields)
        img = np.zeros((2, len(cols) * 2, 3), np.uint8)
        for i, col in enumerate(cols): img[:, 2*i:2*i+2] = col
        b = beacon.decode_at(img, .5, .5, 2)
        assert b and b.fields["active_boss"] == (27 if version >= 5 else 0)
        assert b.fields["boss_mask"] == (fields["boss_mask"] if version >= 5 else 0)
        assert b.fields["contribute"] == (1 if version == 6 else 0)
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    result = subprocess.run(["lua5.1", os.path.join(root, "tests/beacon_harness.lua"),
                             os.path.join(root, "addon"), "context"],
                            check=True, text=True, capture_output=True)
    cols = json.loads([l for l in result.stdout.splitlines() if l.startswith("{")][-1])["cells"]
    img = np.repeat(np.asarray(cols, np.uint8)[None, :, :], 2, axis=1)
    b = beacon.decode_at(img, .5, 0, 2)
    assert b and b.fields["active_boss"] == 2 and b.fields["boss_mask"] == 1, b
    print("PASS independent uncertainty, run state, and v4/v5 compatibility")


def data_and_performance():
    # International encounter aliases must load even on a Windows cp1252 locale.
    import builtins
    from unittest.mock import patch
    real_open = builtins.open
    def windows_open(*args, **kwargs):
        kwargs.setdefault("encoding", "cp1252")
        return real_open(*args, **kwargs)
    with patch("builtins.open", windows_open):
        localized = Data()
    assert any(any(ord(c) > 127 for c in alias) for bs in localized.bosses.values()
               for b in bs for alias in b["aliases"])
    data = Data()
    expected = {"The Baron", "Magmatus", "Arcanic Enigma", "Overlord Mugg", "Deathless Marrow"}
    bosses = [b for bs in data.bosses.values() for b in bs]
    assert len(bosses) == 212 and expected <= {b["name"] for b in bosses}
    assert all(b["encounters"] and b["floor"] in data.floors for b in bosses)
    assert sum(len(r["paths"]) for r in data.routes.values()) == 122
    paths = data.routes["ruinsoflordaeron"]["paths"]
    t0 = time.perf_counter()
    graph = RouteGraph(data, 1029991, paths)
    build = time.perf_counter() - t0
    rng = np.random.default_rng(1)
    for n in (500, 4000):
        p = graph.points[rng.integers(len(graph.points), size=n)] + rng.normal(0, 3, (n, 2))
        previous = p + np.array([0, 3])
        graph.weights(p, previous, 3.)
        t0 = time.perf_counter()
        for _ in range(10): graph.weights(p, previous, 3.)
        ms = (time.perf_counter() - t0) * 100
        print("route context: %d particles %.2f ms/check (every 3 yards); build %.1f ms" % (n, ms, build * 1000))
    print("PASS all 212 boss records and 122 route traces")


if __name__ == "__main__":
    route_tests()
    atlas_tests()
    context_tests()
    data_and_performance()
