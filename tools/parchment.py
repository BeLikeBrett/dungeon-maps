"""Paint top-down client geometry as a parchment dungeon map.

Input is an RGBA composite of the game's own minimap textures (opaque where
the cave floor is). The output keeps that exact pixel frame, so boss pins,
route points and the live arrow still line up. Everything here is drawn
procedurally: no third-party artwork is copied into the result.

Development-only tool (numpy + Pillow); the add-on just loads the BLP.
"""
import heapq
import math

import numpy as np
from PIL import Image, ImageDraw, ImageFont

INK = (40, 24, 11)
FONT_FILES = ('/usr/share/fonts/gsfonts/C059-Bold.otf',
              '/usr/share/fonts/TTF/DejaVuSerif-Bold.ttf')


def blur(a, sigma):
    """Gaussian-like blur (three separable box passes, edge-clamped, float32)."""
    a = a.astype(np.float32)
    width = max(1, int(round(math.sqrt(4*sigma*sigma + 1))))
    half = width // 2
    for axis in (0, 1):
        n = a.shape[axis]
        for _ in range(3):
            pad = [(0, 0), (0, 0)]
            pad[axis] = (half+1, width-half-1)
            c = np.cumsum(np.pad(a, pad, mode='edge'), axis=axis, dtype=np.float64)
            a = ((np.take(c, np.arange(width, width+n), axis=axis)
                  - np.take(c, np.arange(0, n), axis=axis))/width).astype(np.float32)
    return a


def _noise(h, w, cell, seed):
    rng = np.random.default_rng(seed)
    gh, gw = int(h/cell)+3, int(w/cell)+3
    grid = Image.fromarray(rng.random((gh, gw)).astype(np.float32), 'F')
    return np.asarray(grid.resize((int(gw*cell), int(gh*cell)), Image.Resampling.BICUBIC),
                      np.float32)[:h, :w]


def fbm(h, w, cell, octaves, seed):
    total, amp, norm = np.zeros((h, w), np.float32), 1.0, 0.0
    for octave in range(octaves):
        total += amp*_noise(h, w, max(1.0, cell/2**octave), seed+octave)
        norm += amp
        amp *= 0.5
    return total/norm


def _mix(a, b, t):
    return a + (b-a)*np.asarray(t, np.float32)[..., None]


def _c(*rgb):
    return np.array(rgb, np.float32)/255


def paint(raw, scale=2, seed=7, pools=False, water=True, edge=1.0, detail=0.6, density=1):
    """Return the painted map as an RGB image at raw.size*scale.

    raw: RGBA client-texture composite. pools: also paint green slime pools
    (the approach cave's Cavern of Mists) distinct from ordinary water.
    water: detect blue water; off where blue-tinted rock would be misread.
    edge: outline anti-aliasing (map px; keep small so the shape stays 1:1).
    detail: how much client texture relief shows. density: raw pixels per map pixel.
    """
    W, H = round(raw.size[0]*scale/density), round(raw.size[1]*scale/density)
    K = scale
    src = raw.convert('RGBA')
    if src.size != (W, H):
        src = src.resize((W, H), Image.Resampling.BICUBIC)
    src = np.asarray(src, np.float32)/255
    rgb, alpha = src[..., :3], src[..., 3]
    lum = rgb @ np.array([0.3, 0.55, 0.15], np.float32)

    solid = ((alpha > 0.4) & (lum > 0.11)).astype(np.float32)
    m = blur(solid, edge*K)
    floor = np.clip((m-0.5)*8+0.5, 0, 1)

    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    blue = ((b > r*1.13) & (g > r*1.08) & (b > 0.3)).astype(np.float32) if water else np.zeros_like(lum)
    water = np.clip((blur(blue*floor, 1.2*K)-0.4)*5, 0, 1)
    slime = np.zeros_like(water)
    if pools:
        slime = ((g > r*1.25) & (g > b*1.25) & (g > 0.28)).astype(np.float32)
        slime = np.clip((blur(slime*floor, 1.5*K)-0.4)*5, 0, 1)

    # Parchment.
    n1 = fbm(H, W, 220*K, 5, seed)
    n2 = fbm(H, W, 40*K, 3, seed+20)
    paper = _mix(_c(158, 122, 74), _c(202, 170, 118), np.clip((n1-0.3)*1.9, 0, 1))
    paper *= (0.96 + 0.06*n2)[..., None]
    stain = fbm(H, W, 140*K, 3, seed+40)
    paper = _mix(paper, paper*_c(170, 130, 90)*1.3, np.clip((stain-0.62)*5, 0, 1)*0.55)
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    d = np.sqrt(((xx/W-0.5)*1.25)**2 + ((yy/H-0.5)*1.35)**2)
    paper *= (1 - 0.55*np.clip(d-0.32, 0, 1)**1.4)[..., None]

    # Rock shadow around the passages.
    outside = 1-floor
    far = np.clip(blur(floor, 30*K)*1.5, 0, 1)
    mid = np.clip(blur(floor, 10*K)*2.0, 0, 1)
    near = np.clip(blur(floor, 3.5*K)*2.2, 0, 1)
    rim = fbm(H, W, 14*K, 2, seed+60)
    img = _mix(paper, paper*_c(150, 120, 90), far*outside*0.55)
    img = _mix(img, _c(96, 64, 34)*(0.94+0.12*rim)[..., None], mid*outside*0.75)
    img = _mix(img, _c(58, 36, 18), near*outside*0.85)

    # Floor: parchment tones carrying the client texture's own rocks and roots.
    soft = blur(lum, 0.5*K)
    relief = (soft - blur(soft, 5*K))*detail/1.1
    broad = blur(lum, 16*K)
    ground = _mix(_c(178, 146, 96), _c(226, 202, 152), np.clip((broad-0.22)*2.6, 0, 1))
    hue = np.stack([blur(rgb[..., i], 12*K) for i in range(3)], -1)
    hue = np.clip(hue/(hue.mean(-1, keepdims=True)+1e-4), 0.6, 1.5)
    ground = ground*0.72 + ground*hue*0.28
    ground += (np.clip(relief, -0.18, 0.18)*1.1)[..., None]
    inner = blur(floor, 6*K)
    ground *= (0.62 + 0.38*np.clip((inner-0.5)*2.0, 0, 1)**0.8)[..., None]
    ground *= (0.975 + 0.05*n2)[..., None]

    depth = np.clip(blur(water, 4*K), 0, 1)
    wet = _mix(_c(120, 150, 138), _c(70, 104, 104), np.clip((depth-0.5)*2, 0, 1))
    wet += (np.clip(relief, -0.1, 0.1)*0.4)[..., None]
    ground = _mix(ground, wet, water*0.95)
    shore = np.clip(blur(water, 1.0*K)*(1-water)*2.5, 0, 1)
    ground = _mix(ground, _c(205, 196, 160), shore*0.6)
    if pools:
        deep = np.clip(blur(slime, 5*K), 0, 1)
        goo = _mix(_c(128, 150, 84), _c(74, 104, 52), np.clip((deep-0.5)*2, 0, 1))
        goo += (np.clip(relief, -0.1, 0.1)*0.5)[..., None]
        ground = _mix(ground, goo, slime*0.92)
        edge = np.clip(blur(slime, 1.0*K)*(1-slime)*2.5, 0, 1)
        ground = _mix(ground, _c(188, 196, 140), edge*0.5)
    img = _mix(img, ground, floor)

    outline = np.clip(1 - np.abs(m-0.5)*5, 0, 1)
    img = _mix(img, _c(38, 22, 10), outline*0.9)
    img *= (0.99 + 0.02*_noise(H, W, 1.5*K, seed+90))[..., None]
    return Image.fromarray((np.clip(img, 0, 1)*255).astype(np.uint8))


def floor_mask(raw, scale=1, edge=1.0):
    """The binary passage mask paint() uses (at raw.size*scale)."""
    W, H = raw.size[0]*scale, raw.size[1]*scale
    src = np.asarray(raw.convert('RGBA').resize((W, H), Image.Resampling.BICUBIC), np.float32)/255
    lum = src[..., :3] @ np.array([0.3, 0.55, 0.15], np.float32)
    solid = ((src[..., 3] > 0.4) & (lum > 0.11)).astype(np.float32)
    return blur(solid, edge*scale) > 0.5


def font(size):
    for path in FONT_FILES:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default(size)


def compass(img, cx, cy, r):
    """Inked eight-point compass rose (north up), drawn onto an RGB/RGBA image."""
    layer = Image.new('RGBA', img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    ink, pale = INK + (225,), (228, 208, 162, 225)
    for ring, w in ((0.62, 0.045), (0.70, 0.02)):
        d.ellipse([cx-r*ring, cy-r*ring, cx+r*ring, cy+r*ring], outline=ink, width=max(1, int(r*w)))
    for i in range(8):
        a = i*math.pi/4
        length, half = (r, r*0.13) if i % 2 == 0 else (r*0.55, r*0.11)
        tip = (cx+math.sin(a)*length, cy-math.cos(a)*length)
        left = (cx+math.sin(a-math.pi/2)*half, cy-math.cos(a-math.pi/2)*half)
        right = (cx+math.sin(a+math.pi/2)*half, cy-math.cos(a+math.pi/2)*half)
        d.polygon([tip, left, (cx, cy)], fill=ink)
        d.polygon([tip, right, (cx, cy)], fill=pale, outline=ink)
    f = font(int(r*0.42))
    d.text((cx, cy-r*1.22), 'N', font=f, fill=ink, anchor='mm')
    _paste(img, layer)


def _paste(img, layer):
    if img.mode == 'RGBA':
        img.alpha_composite(layer)
    else:
        img.paste(layer, (0, 0), layer)


def smooth(points, rounds=2):
    """Chaikin corner cutting; keeps the end points."""
    pts = list(points)
    for _ in range(rounds):
        if len(pts) < 3:
            break
        out = [pts[0]]
        for (ax, ay), (bx, by) in zip(pts[:-1], pts[1:]):
            out.append((ax*0.75+bx*0.25, ay*0.75+by*0.25))
            out.append((ax*0.25+bx*0.75, ay*0.25+by*0.75))
        out.append(pts[-1])
        pts = out
    return pts


def route(img, points, colour, width, arrow_every, dashed=False):
    """Draw a haloed route line with direction chevrons (points in img pixels)."""
    pts = smooth(points)
    layer = Image.new('RGBA', img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    halo = (238, 224, 186, 200)
    d.line(pts, fill=halo, width=int(width*2.6), joint='curve')
    for x, y in (pts[0], pts[-1]):
        rr = width*1.3
        d.ellipse([x-rr, y-rr, x+rr, y+rr], fill=halo)
    if dashed:
        run, on = 0.0, True
        dash = width*3.2
        segment = [pts[0]]
        for a, b in zip(pts[:-1], pts[1:]):
            run += math.dist(a, b)
            segment.append(b)
            if run >= dash:
                if on:
                    d.line(segment, fill=colour+(255,), width=int(width), joint='curve')
                segment, run, on = [b], 0.0, not on
        if on and len(segment) > 1:
            d.line(segment, fill=colour+(255,), width=int(width), joint='curve')
    else:
        d.line(pts, fill=colour+(255,), width=int(width), joint='curve')
    since = arrow_every*0.5
    for a, b in zip(pts[:-1], pts[1:]):
        length = math.dist(a, b)
        since += length
        if length < 1e-6 or since < arrow_every:
            continue
        since = 0.0
        ux, uy = (b[0]-a[0])/length, (b[1]-a[1])/length
        x, y = b
        s = width*1.9
        tri = [(x+s*ux, y+s*uy), (x-s*ux+s*0.85*uy, y-s*uy-s*0.85*ux), (x-s*0.4*ux, y-s*0.4*uy),
               (x-s*ux-s*0.85*uy, y-s*uy+s*0.85*ux)]
        d.polygon(tri, fill=colour+(255,), outline=halo)
    _paste(img, layer)


def badge(img, x, y, text, radius, fill=(52, 32, 16), ring=(214, 172, 86), glow=None):
    """Round map marker with a gold ring and a cream glyph."""
    layer = Image.new('RGBA', img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    if glow:
        for k in range(6, 0, -1):
            rr = radius*(1+0.12*k)
            d.ellipse([x-rr, y-rr, x+rr, y+rr], fill=glow+(int(22*(7-k)),))
    rr = radius*1.12
    d.ellipse([x-rr+radius*0.12, y-rr+radius*0.18, x+rr+radius*0.12, y+rr+radius*0.18], fill=(0, 0, 0, 90))
    d.ellipse([x-rr, y-rr, x+rr, y+rr], fill=ring+(255,))
    d.ellipse([x-radius*0.88, y-radius*0.88, x+radius*0.88, y+radius*0.88], fill=fill+(255,))
    d.text((x, y+radius*0.04), text, font=font(int(radius*1.15)), fill=(246, 230, 190, 255), anchor='mm')
    _paste(img, layer)


def label(img, x, y, text, size, anchor='lm'):
    """Small-caps style map caption with a parchment halo."""
    layer = Image.new('RGBA', img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.text((x, y), text, font=font(size), fill=INK+(255,), anchor=anchor,
           stroke_width=max(2, size//6), stroke_fill=(236, 220, 178, 230))
    _paste(img, layer)


def walk_path(mask, start, goal):
    """Shortest centre-favouring path through a boolean mask (Dijkstra, 8-way)."""
    h, w = mask.shape
    inner = blur(mask.astype(np.float32), 4)
    cost = np.where(mask, 1.0 + 10.0*(1.0-np.clip((inner-0.5)*2, 0, 1))**2, np.inf)

    def snap(p):
        x, y = int(round(p[0])), int(round(p[1]))
        ys, xs = np.nonzero(mask)
        i = np.argmin((xs-x)**2 + (ys-y)**2)
        return int(ys[i]), int(xs[i])

    s, g = snap(start), snap(goal)
    dist = np.full((h, w), np.inf)
    prev = {}
    dist[s] = 0
    heap = [(0.0, s)]
    steps = [(-1, 0, 1), (1, 0, 1), (0, -1, 1), (0, 1, 1),
             (-1, -1, 1.4142), (-1, 1, 1.4142), (1, -1, 1.4142), (1, 1, 1.4142)]
    while heap:
        du, u = heapq.heappop(heap)
        if u == g:
            break
        if du > dist[u]:
            continue
        for dy, dx, k in steps:
            v = (u[0]+dy, u[1]+dx)
            if 0 <= v[0] < h and 0 <= v[1] < w and cost[v] < np.inf:
                nd = du + k*cost[v]
                if nd < dist[v]:
                    dist[v] = nd
                    prev[v] = u
                    heapq.heappush(heap, (nd, v))
    if g not in prev and g != s:
        raise ValueError('goal not reachable through the mask')
    path, node = [], g
    while node != s:
        path.append((node[1], node[0]))
        node = prev[node]
    path.append((s[1], s[0]))
    path.reverse()
    return path[::4] + [path[-1]]
