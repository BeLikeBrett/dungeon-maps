"""Reads the Dungeon Maps addon's beacon: a strip of 54 coloured cells (2 x 2 pixels each) the addon
draws in the game's top-left corner.

Cells 1-2 are magenta and green (to find the strip), cells 3-5 hold the 8 colour levels (0..7 per
channel, measured here so gamma or colour settings can't confuse the decoder), cells 6-54 carry
9 bits each (3 per channel), the last one a checksum. Field layout: DungeonMaps.lua, beaconCells().
"""

from dataclasses import dataclass

import numpy as np

HEADER = 5
CELLS = 54
PX = 2  # cell side in pixels (BEACON_PX in the addon)
FORMAT_VERSION = 4

# (name, bits) in the order the addon pushes them
FIELDS = [
    ("version", 3), ("map_open", 1), ("indoors", 2), ("rotate", 1), ("zoom", 3), ("radius4", 11),
    ("dungeon", 6), ("shown_floor", 4), ("lm_count", 6), ("lm_kind", 2), ("lm_floor", 4),
    ("lm_u", 12), ("lm_v", 12), ("room", 7),
    ("mm_x", 13), ("mm_y", 13), ("mm_w", 12), ("mm_h", 12),
    ("cv_x", 13), ("cv_y", 13), ("cv_w", 12), ("cv_h", 12),
    # v2: the group (same number for every member; 0 = not grouped) and your character's name
    ("group", 32), ("name_len", 5),
] + [("n%d" % i, 8) for i in range(24)] + [
    # v3: your arrow's size (tenths, from the addon's settings) and your class colour (5 bits a channel)
    ("arrow_size", 5), ("cr", 5), ("cg", 5), ("cb", 5),
    # v4: how big your teammates' dots are drawn (tenths, the addon's "Teammate dots" setting)
    ("dot_size", 5),
]


@dataclass
class Beacon:
    x: float  # centre of the first cell, in the image searched
    y: float
    pitch: float  # pixels from one cell centre to the next
    fields: dict

    @property
    def name(self):
        f = self.fields
        raw = bytes(f["n%d" % i] for i in range(min(24, f["name_len"])))
        return raw.decode("utf-8", "replace")

    @property
    def colour(self):
        """Class colour as #rrggbb."""
        f = self.fields
        return "#%02x%02x%02x" % tuple(round(f[k] * 255 / 31) for k in ("cr", "cg", "cb"))

    @property
    def arrow_size(self):
        return min(2.5, max(0.5, self.fields["arrow_size"] / 10)) if self.fields["arrow_size"] else 1.0

    @property
    def dot_size(self):
        return min(2.5, max(0.5, self.fields["dot_size"] / 10)) if self.fields.get("dot_size") else 1.0

    def rect(self, prefix):
        """A rectangle the addon sent (relative to the strip's top-left), in image pixels."""
        f = self.fields
        if f[prefix + "_w"] == 0:
            return None
        left = self.x - self.pitch / 2
        top = self.y - self.pitch / 2
        return (left + f[prefix + "_x"] - 4096, top + f[prefix + "_y"] - 4096, f[prefix + "_w"], f[prefix + "_h"])


def _magenta(img):
    r, g, b = img[..., 0].astype(np.int16), img[..., 1].astype(np.int16), img[..., 2].astype(np.int16)
    return (r > 190) & (b > 190) & (g < 70)


def _green(img):
    r, g, b = img[..., 0].astype(np.int16), img[..., 1].astype(np.int16), img[..., 2].astype(np.int16)
    return (g > 190) & (r < 70) & (b < 70)


def _runs(row):
    """(start, end) of runs of True in a 1-D bool array (end exclusive)."""
    d = np.diff(np.concatenate(([0], row.view(np.int8), [0])))
    return list(zip(np.flatnonzero(d == 1), np.flatnonzero(d == -1)))


def decode_at(img, x, y, pitch):
    """Decode a strip whose first cell is centred at (x, y). None unless every check passes."""
    h, w = img.shape[:2]
    pts = []
    for i in range(CELLS):
        cx, cy = int(round(x + i * pitch)), int(round(y))
        if not (0 <= cx < w and 0 <= cy < h):
            return None
        pts.append(img[cy, cx].astype(np.float32))
    if not (_magenta(pts[0][None, :]).all() and _green(pts[1][None, :]).all()):
        return None
    # measured value of each level 0..7 (cells 3-5 = levels (0,1,2) (3,4,5) (6,7,0); 7 also from cell 1/2)
    lv = {0: [pts[0][1], pts[1][0], pts[1][2], pts[2][0], pts[4][2]], 7: [pts[0][0], pts[0][2], pts[1][1], pts[4][1]],
          1: [pts[2][1]], 2: [pts[2][2]], 3: [pts[3][0]], 4: [pts[3][1]], 5: [pts[3][2]], 6: [pts[4][0]]}
    levels = np.array([np.mean(lv[i]) for i in range(8)])
    if np.any(np.diff(levels) <= 4):  # must climb steadily
        return None

    def level(v):
        return int(np.argmin(np.abs(levels - v)))

    values = []
    for p in pts[HEADER:]:
        values.append(level(p[0]) * 64 + level(p[1]) * 8 + level(p[2]))
    data, check = values[:-1], values[-1]
    if sum(data) % 512 != check:
        return None
    bits = []
    for v in data:
        bits.extend((v >> (8 - k)) & 1 for k in range(9))
    fields, pos = {}, 0
    for name, n in FIELDS:
        v = 0
        for b in bits[pos:pos + n]:
            v = v * 2 + b
        fields[name] = v
        pos += n
    if fields["version"] != FORMAT_VERSION:
        return None
    return Beacon(x, y, pitch, fields)


def find(img):
    """Search a whole image for the strip. Returns a Beacon or None."""
    mag, grn = _magenta(img), _green(img)
    ys = np.flatnonzero(mag.any(axis=1))
    tried = set()
    for y in ys:
        for x0, x1 in _runs(mag[y]):
            if not 1 <= x1 - x0 <= 16:
                continue
            # the green cell must follow right after
            g = grn[y, x1:x1 + 20]
            gruns = _runs(g)
            if not gruns or gruns[0][0] > 2:
                continue
            g0, g1 = x1 + gruns[0][0], x1 + gruns[0][1]
            cm, cg = (x0 + x1 - 1) / 2, (g0 + g1 - 1) / 2
            # blended cell edges make any one estimate of the cell pitch a pixel off: try several
            pitches = sorted({p for p in (cg - cm, x1 - x0, g1 - g0, g1 - x1, g0 - x0, round(cg - cm))
                              if 1.5 <= p <= 16}, key=lambda p: abs(p - (cg - cm)))
            # the rows of the magenta cell at this column; the centre of the rows that decode
            col = mag[:, int(round(cm))]
            top = bottom = y
            while top > 0 and col[top - 1] and y - top < 16:
                top -= 1
            while bottom + 1 < len(col) and col[bottom + 1] and bottom - y < 16:
                bottom += 1
            key = (round(cm), top, bottom)
            if key in tried:
                continue
            tried.add(key)
            for pitch in pitches:
                for x in (cm, x1 - pitch / 2, x0 + pitch / 2):
                    good = [r for r in range(top, bottom + 1) if decode_at(img, x, r, pitch)]
                    if good:
                        return decode_at(img, x, sum(good) / len(good), pitch)
    return None
