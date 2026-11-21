"""Friends' dots: glide between relay updates, jump (not slide) across the map, never sit under your
arrow, and put the name on the side away from you."""
import os as _os, tempfile as _tempfile  # noqa: E401
if not _os.environ.get("DUNGEONMAPS_TEST_ISOLATED"):  # never touch the real atlas, calibration or caches
    _tmp = _tempfile.mkdtemp(prefix="dungeonmaps-test-")
    _os.environ.update(XDG_DATA_HOME=_tmp, XDG_STATE_HOME=_tmp, LOCALAPPDATA=_tmp, DUNGEONMAPS_TEST_ISOLATED="1")

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dungeonmaps.core import Core  # noqa: E402
from dungeonmaps.data import MAP_H, MAP_W  # noqa: E402


def main():
    c = Core()
    w, h = 1002, 668
    me = {"u": 0.5, "v": 0.5, "size": 1.0}
    f = lambda u, v: [{"name": "Kev", "u": u, "v": v}]  # noqa: E731
    out = c._layout(me, f(0.2, 0.2), w, h, 0.0)
    assert (out[0]["u"], out[0]["v"]) == (0.2, 0.2) and out[0]["label"] == "above"
    # a small step glides: after one 1/15 s tick it's part of the way there
    out = c._layout(me, f(0.21, 0.2), w, h, 1 / 15)
    assert 0.2 < out[0]["u"] < 0.21, out
    # far away (a teleport, or the first fix after the entrance): no slide across the map
    out = c._layout(me, f(0.8, 0.8), w, h, 2 / 15)
    assert (out[0]["u"], out[0]["v"]) == (0.8, 0.8) and out[0]["label"] == "below"
    # standing exactly on you: pushed onto a ring around your arrow
    c2 = Core()
    out = c2._layout(me, [{"name": "A", "u": 0.5, "v": 0.5}, {"name": "B", "u": 0.5, "v": 0.5}], w, h, 0.0)
    ring = [math.hypot((p["u"] - 0.5) * w, (p["v"] - 0.5) * h) for p in out]
    assert all(r > 15 for r in ring), ring
    gap = math.hypot((out[0]["u"] - out[1]["u"]) * w, (out[0]["v"] - out[1]["v"]) * h)
    assert gap > 10, gap                     # and not on top of each other
    # friends who left are forgotten
    c2._layout(me, [], w, h, 1.0)
    assert c2.shown_friends == {}
    assert MAP_W and MAP_H
    print("PASS layout")


if __name__ == "__main__":
    main()
