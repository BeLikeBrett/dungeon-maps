"""Reference atlases (atlas.py, tools/reference_atlas.py): loaded as fully known, never repainted.

Ragefire 2026-11-23: a learned atlas had smeared ghost corridors from drifted runs, and matching it
moved the arrow 10-20 yards into the wrong parallel hall. A reference made from the game's own
minimap textures must win over that learned atlas and stay exactly as made, whatever gets pasted.
"""
import os as _os, tempfile as _tempfile  # noqa: E401
if not _os.environ.get("DUNGEONMAPS_TEST_ISOLATED"):
    _tmp = _tempfile.mkdtemp(prefix="dungeonmaps-test-")
    _os.environ.update(XDG_DATA_HOME=_tmp, XDG_STATE_HOME=_tmp, LOCALAPPDATA=_tmp, DUNGEONMAPS_TEST_ISOLATED="1")

import os
import sys
import tempfile

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dungeonmaps.atlas import MAX_WEIGHT, RES, Atlases  # noqa: E402
from dungeonmaps.data import Data  # noqa: E402

FLOOR = 213


def make_reference(folder, atlases, floor):
    a = atlases.get(floor)
    rng = np.random.default_rng(1)
    gray = rng.integers(30, 200, a.sum.shape).astype(np.uint8)
    known = np.zeros(a.sum.shape, bool)
    known[100:-100, 100:-100] = True
    np.savez_compressed(os.path.join(folder, "%d.npz" % floor), gray=gray, known=known,
                        res=np.float32(RES), n_max=np.float64(a.n_max), w_max=np.float64(a.w_max))
    return gray, known


def main():
    data = Data()
    with tempfile.TemporaryDirectory() as learned, tempfile.TemporaryDirectory() as ref:
        gray, known = make_reference(ref, Atlases(data, folder=learned, reference_dirs=()), FLOOR)

        # A learned atlas on disk with garbage where the reference knows better.
        plain = Atlases(data, folder=learned, reference_dirs=())
        a = plain.get(FLOOR)
        a.sum[:] = 7 * MAX_WEIGHT
        a.wt[:] = MAX_WEIGHT
        a.changed = True
        plain.save(background=False)

        a = Atlases(data, folder=learned, reference_dirs=(ref,)).get(FLOOR)
        assert a.fixed is not None and np.array_equal(a.fixed, known)
        mean = a.sum / np.maximum(a.wt, 1e-6)
        assert np.allclose(mean[known], gray[known]), "the reference must replace learned pixels"
        assert (a.wt[~known] == 0).all(), "an atlas learned before the reference is dropped once"

        # Learned after the reference (saved with its flag): kept outside the reference.
        a.sum[~known] = 7 * MAX_WEIGHT
        a.wt[~known] = MAX_WEIGHT
        a.changed = True
        owner = Atlases(data, folder=learned, reference_dirs=(ref,))
        owner.atlases[FLOOR] = a
        owner.save(background=False)
        a = Atlases(data, folder=learned, reference_dirs=(ref,)).get(FLOOR)
        mean = a.sum / np.maximum(a.wt, 1e-6)
        assert np.allclose(mean[~known], 7), "outside the reference, newly learned pixels stay"
        assert (a.odo[known] < -1e8).all(), "reference pixels are old: always matchable"

        # Pastes (ordinary, hard and a Shift+click replace) never change reference pixels.
        before_sum, before_wt = a.sum.copy(), a.wt.copy()
        picture = np.full((64, 64), 250, np.float32)
        mask = np.ones((64, 64), np.float32)
        for n, w in [((a.n_max - 400), (a.w_max - 500)), ((a.n_max - 50), (a.w_max - 50))]:
            for kw in ({}, {"weight": 4.0}, {"weight": 4.0, "replace": True}):
                a.paste(picture, mask, n, w, 0.6, **kw)
        assert np.array_equal(a.sum[known], before_sum[known]) and np.array_equal(a.wt[known], before_wt[known])
        assert not np.array_equal(a.sum[~known], before_sum[~known]), "unknown margins still learn"

        # A reference made for another grid is ignored, not misplaced.
        z = dict(np.load(os.path.join(ref, "%d.npz" % FLOOR)))
        z["n_max"] = z["n_max"] + 5
        np.savez_compressed(os.path.join(ref, "%d.npz" % FLOOR), **z)
        assert Atlases(data, folder=learned, reference_dirs=(ref,)).get(FLOOR).fixed is None

        # The located position comes straight from the reference picture.
        np.savez_compressed(os.path.join(ref, "%d.npz" % FLOOR), gray=gray, known=known, res=np.float32(RES),
                            n_max=np.float64(a.n_max), w_max=np.float64(a.w_max))
        a = Atlases(data, folder=learned, reference_dirs=(ref,)).get(FLOOR)
        n, w = a.n_max - 400.0, a.w_max - 500.0
        view, vmask = a.render(n, w, 0.625, 128)
        r = a.locate(view, vmask, n + 9, w - 6, 0.625, 20)
        assert r is not None and abs(r[0] - n) < 0.5 and abs(r[1] - w) < 0.5, r
    print("reference atlas: loads over learned pixels, fixed against pastes, grid-checked, locates")


if __name__ == "__main__":
    main()
