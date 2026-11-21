"""Replay recorded minimap frames (PNG crops of the minimap, in order) through the tracker's odometry.

  python3 tools/replay.py <folder of minimap PNGs> <yards per minimap pixel> [floor] [map art PNG]

Writes, next to the frames:
  mosaic.png   the frames stitched by dead reckoning (what the atlas would learn), with the path
  scale.txt    with a floor and its map art: the scale and place where the mosaic's floor best
               covers the dungeon on the art (how wrong the minimap scale is)
"""
import glob
import math
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dungeonmaps.atlas import VOID, FloorAtlas  # noqa: E402
from dungeonmaps.odometry import Odometry  # noqa: E402


def main():
    folder, ypp = sys.argv[1], float(sys.argv[2])
    frames = sorted(glob.glob(os.path.join(folder, "*.png")))
    frames = [f for f in frames if os.path.basename(f)[0].isdigit()]
    odo = Odometry()
    atlas = FloorAtlas(0, 1500.0, 1500.0, 3000, 3000)
    n = w = 0.0
    path = [(n, w)]
    good = 0
    for i, f in enumerate(frames):
        img = np.array(Image.open(f).convert("RGB"))
        d = odo.step(img)
        if d is None:
            continue
        good += 1
        n -= d[1] * ypp
        w -= d[0] * ypp
        path.append((n, w))
        if i % 3 == 0:
            atlas.paste(odo.gray, odo.mask, n, w, ypp * img.shape[1] / odo.mask.shape[1], 1.0)
    print("%d frames, %d read; walked %.0f yards (at %.3f yd/px)" % (
        len(frames), good, sum(math.hypot(a[0] - b[0], a[1] - b[1]) for a, b in zip(path, path[1:])), ypp))
    known = atlas.wt >= 0.5
    rows, cols = np.nonzero(known)
    r0, r1, c0, c1 = rows.min(), rows.max() + 1, cols.min(), cols.max() + 1
    mean = np.where(known, atlas.sum / np.maximum(atlas.wt, 1e-6), 0)[r0:r1, c0:c1]
    img = Image.fromarray(np.clip(mean, 0, 255).astype(np.uint8)).convert("RGB")
    dr = ImageDraw.Draw(img)
    pts = [(atlas.rc(a, b)[1] - c0, atlas.rc(a, b)[0] - r0) for a, b in path]
    dr.line(pts, fill=(255, 40, 40), width=2)
    dr.ellipse((pts[0][0] - 4, pts[0][1] - 4, pts[0][0] + 4, pts[0][1] + 4), outline=(0, 255, 0), width=2)
    img.save(os.path.join(folder, "mosaic.png"))
    print("mosaic.png: %dx%d yards" % (c1 - c0, r1 - r0))
    if len(sys.argv) > 4:
        scale_search(folder, atlas, known & (np.where(known, atlas.sum / np.maximum(atlas.wt, 1e-6), 0) >= VOID),
                     known, int(sys.argv[3]), sys.argv[4], path)


def scale_search(folder, atlas, floor_mask, known, floor, art_path, path):
    """Slide the mosaic's floor over the art's dungeon (everything that isn't plain parchment) at
    several scales; the best overlap gives the true scale."""
    from dungeonmaps.data import MAP_H, MAP_W, Data
    from dungeonmaps.walkmap import _blur, _dilate
    data = Data()
    art = np.array(Image.open(art_path).convert("RGB")).astype(np.float32)
    a = _blur(art.astype(np.uint8), 2).astype(np.float32)
    # the dungeon on the art: the paths, plus whatever differs from the plain parchment around it
    par = np.median(a[MAP_H // 2:, MAP_W * 3 // 4:].reshape(-1, 3), 0)
    diff = np.abs(a - par).sum(2)
    inside = _dilate(diff > 45, 2)
    inside[:90, :] = False   # (title banner)
    inside[MAP_H - 50:, :] = False
    ppy = data.px_per_yard(floor)
    rows, cols = np.nonzero(known)
    r0, r1, c0, c1 = rows.min(), rows.max() + 1, cols.min(), cols.max() + 1
    fm = floor_mask[r0:r1, c0:c1].astype(np.float32)
    km = known[r0:r1, c0:c1].astype(np.float32)
    best = None
    for s in np.arange(0.70, 1.50, 0.02):
        k = ppy * s  # art pixels per mosaic yard (at this scale correction)
        size = (max(8, int(round((c1 - c0) * k))), max(8, int(round((r1 - r0) * k))))
        f = np.array(Image.fromarray((fm * 255).astype(np.uint8)).resize(size, Image.BILINEAR)) / 255.0
        m = np.array(Image.fromarray((km * 255).astype(np.uint8)).resize(size, Image.BILINEAR)) / 255.0
        if f.shape[0] >= MAP_H or f.shape[1] >= MAP_W:
            continue
        t = (2 * f - 1) * m  # +1 floor, -1 void, 0 unknown
        A = inside.astype(np.float32) * 2 - 1
        H, W = A.shape
        fs = (H + t.shape[0], W + t.shape[1])
        c = np.fft.irfft2(np.fft.rfft2(A, fs) * np.conj(np.fft.rfft2(t, fs)), fs)[:H - t.shape[0] + 1, :W - t.shape[1] + 1]
        score = c / max(m.sum(), 1)
        iy, ix = np.unravel_index(int(np.argmax(score)), score.shape)
        if best is None or score[iy, ix] > best[0]:
            best = (float(score[iy, ix]), s, ix, iy, size)
    sc, s, ix, iy, size = best
    lines = ["best scale correction x%.2f (overlap score %.3f) at art (%d, %d) size %s" % (s, sc, ix, iy, size)]
    vis = art.astype(np.uint8).copy()
    k = ppy * s
    for (pn, pw) in path[::5]:
        rr, cc = atlas.rc(pn, pw)
        x, y = int(ix + (cc - c0) * k), int(iy + (rr - r0) * k)
        if 0 <= x < MAP_W and 0 <= y < MAP_H:
            vis[max(0, y - 1):y + 2, max(0, x - 1):x + 2] = (255, 0, 0)
    Image.fromarray(vis).save(os.path.join(folder, "path_on_art.png"))
    open(os.path.join(folder, "scale.txt"), "w").write("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
