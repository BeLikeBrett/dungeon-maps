"""Odometry on a synthetic dungeon: a textured world seen through a fake minimap (round, border ring
that never moves, the player arrow turning in the middle, two party blips wandering, pixel noise).
Walks a winding 600-yard path at running speed and reports how far the estimate drifts."""
import math
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dungeonmaps.odometry import Odometry  # noqa: E402

MM = 189                  # minimap pixels across (UI scale 0.9 here)
RADIUS = 60.0             # yards, centre to edge (C_Minimap.GetViewRadius)
YPP = 2 * RADIUS / MM     # yards per minimap pixel


def world(n=2600, seed=3, void=False):
    rng = np.random.default_rng(seed)
    img = np.zeros((n, n))
    for scale, amp in ((6, 30), (18, 50), (60, 70)):  # texture at a few sizes
        noise = rng.standard_normal((n, n))
        f = np.fft.rfft2(noise)
        ky = np.fft.fftfreq(n)[:, None]
        kx = np.fft.rfftfreq(n)[None, :]
        f *= np.exp(-(kx ** 2 + ky ** 2) * (scale ** 2) * 4)
        layer = np.fft.irfft2(f, (n, n))
        img += amp * layer / layer.std()
    walls = (np.abs(img) < 18)  # corridors: brighter floors with darker walls
    out = 90 + 0.5 * img + 60 * walls
    if void:  # a real dungeon minimap: halls ~25 yards wide in flat black
        noise = rng.standard_normal((n, n))
        f = np.fft.rfft2(noise)
        ky = np.fft.fftfreq(n)[:, None]
        kx = np.fft.rfftfreq(n)[None, :]
        f *= np.exp(-(kx ** 2 + ky ** 2) * (90 ** 2) * 4)
        halls = np.fft.irfft2(f, (n, n))
        halls /= halls.std()
        out = np.where(np.abs(halls) < 0.35, out, 8.0)
    return np.clip(out, 0, 255)


def crop(w, cx, cy):
    """MM x MM view centred on (cx, cy) world pixels, bilinear."""
    x0, y0 = cx - MM / 2, cy - MM / 2
    ix, iy = int(math.floor(x0)), int(math.floor(y0))
    fx, fy = x0 - ix, y0 - iy
    a = w[iy:iy + MM + 1, ix:ix + MM + 1]
    top = a[:-1, :-1] * (1 - fx) + a[:-1, 1:] * fx
    bot = a[1:, :-1] * (1 - fx) + a[1:, 1:] * fx
    return top * (1 - fy) + bot * fy


_ARROW = np.load(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dungeonmaps", "data", "minimap_arrow.npz"))


def _arrow(heading):
    from PIL import Image
    side = int(round(MM * float(_ARROW["side"]) / float(_ARROW["minimap_w"])))
    out = []
    for k in ("gray", "mask"):
        im = Image.fromarray(_ARROW[k].astype(np.float32), mode="F").rotate(-heading, resample=Image.BILINEAR)
        out.append(np.asarray(im.resize((side, side), Image.BILINEAR), np.float32))
    return side, out[0], out[1]


OVERLAYS = True  # addon text / icons printed on the minimap (they never move)


def dress(view, heading, t, rng):
    yy, xx = np.mgrid[0:MM, 0:MM]
    c = (MM - 1) / 2
    r = np.hypot(xx - c, yy - c)
    out = view.copy()
    out[r > MM / 2 * 0.97] = 20                                    # outside the disc
    out[(r > MM / 2 * 0.93) & (r <= MM / 2 * 0.97)] = 200          # gold border ring
    for k in range(2):                                             # party blips wandering
        bx = c + 40 * math.cos(t * 0.7 + k * 2)
        by = c + 40 * math.sin(t * 0.5 + k * 3)
        out[np.hypot(xx - bx, yy - by) < 4] = 230
    if OVERLAYS:
        # "Questie Tracker"-like text bottom right, a moon icon top right
        txt = (xx > c + 20) & (xx < c + 85) & (yy > c + 62) & (yy < c + 74)
        out[txt & (((xx // 3) + (yy // 2)) % 3 == 0)] = 235
        out[txt & (((xx // 3) + (yy // 2)) % 3 == 1)] = 40
        out[np.hypot(xx - (c + 55), yy - (c - 60)) < 11] = 60
        out[np.hypot(xx - (c + 58), yy - (c - 62)) < 7] = 220
    # the game's player arrow (cut from a real minimap), turned to the heading, on top of
    # everything else as in the game
    side, g, m = _arrow(heading)
    a0 = int(round(c - (side - 1) / 2))
    sl = out[a0:a0 + side, a0:a0 + side]
    sl[:] = np.where(m > 0.5, g, sl)
    out = out + rng.normal(0, 3, out.shape)
    g = np.clip(out, 0, 255).astype(np.uint8)
    return np.stack([g, g, g], axis=-1)


def run(rate_hz=8, speed=7.0, length=600.0, seed=0, void=False):
    rng = np.random.default_rng(seed)
    w = world(void=void)
    odo = Odometry()
    dt = 1 / rate_hz
    x = y = 1300.0            # world pixels; truth
    x0, y0 = x, y
    est = np.zeros(2)         # estimate (yards east, yards south) from the start
    heading, walked, t = 0.0, 0.0, 0.0
    times = []
    if void:  # start inside a hall
        while w[int(y), int(x)] < 20:
            x += 7
    x0, y0 = x, y
    while walked < length:
        heading += rng.normal(0, 12) * dt * 3
        step = speed * dt / YPP
        if void:  # stay in the halls: turn away from walls (void) a few yards ahead
            for _ in range(36):
                ax = x + 4 / YPP * math.sin(math.radians(heading))
                ay = y - 4 / YPP * math.cos(math.radians(heading))
                if w[int(ay), int(ax)] > 20 and 200 < ax < 2400 and 200 < ay < 2400:
                    break
                heading += 10
        x += step * math.sin(math.radians(heading))
        y -= step * math.cos(math.radians(heading))
        walked += speed * dt
        t += dt
        frame = dress(crop(w, x, y), heading, t, rng)
        t0 = time.perf_counter()
        d = odo.step(frame)
        times.append(time.perf_counter() - t0)
        if d is not None:
            est += d * YPP
    truth = np.array([(x - x0) * YPP, (y - y0) * YPP])
    err = np.hypot(*(est - truth))
    return err, walked, 1000 * np.mean(times)


if __name__ == "__main__":
    from dungeonmaps import odometry
    if "--no-learning" in sys.argv:
        odometry.STATIC_VOTES = 1e9
    ok = True
    for void, rate, seed in ((False, 8, 0), (False, 8, 1), (False, 3, 0), (True, 8, 0), (True, 8, 1), (True, 3, 0)):
        if True:
            err, walked, ms = run(rate_hz=rate, seed=seed, void=void)
            print("%s %d Hz, walk %d: %.0f yards walked, ended %.1f yards off (%.1f%%), %.1f ms per frame" % (
                "halls in void," if void else "textured world,", rate, seed, walked, err, 100 * err / walked, ms))
            ok &= err < 0.03 * walked
    print("PASS odometry" if ok else "FAIL odometry")
    sys.exit(0 if ok else 1)
