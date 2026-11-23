"""Build reference atlases (dungeonmaps/atlas.py) from the game's own minimap textures.

The in-game minimap draws the minimap textures of the dungeon's building parts. Forever Dungeon Routes
(Data/Minimaps.lua) lists, per map floor, which texture file goes where on the 1002x668 map. This tool
reads those textures from the installed client's CASC storage (CascLib), pastes them onto the floor's
map, and resamples that onto the floor's atlas grid (1 yard per pixel, luminance). The tracker then
matches the live minimap against it instead of an atlas learned from (drifting) runs.

Usage:
  python tools/reference_atlas.py --wow "~/Faugus/.../World of Warcraft" --casclib /path/libcasc.so \
      [--floor 213 ...] [--out ~/.local/share/dungeon-maps/reference] [--preview DIR]

Without --floor: every floor of every dungeon in dungeons.json that FDR has textures for.
The output is derived from Blizzard's textures: it is written to the user's own data folder by default
and is not part of the repository.
"""
import argparse
import ctypes as C
import io
import os
import re
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dungeonmaps.atlas import RES, Atlases, FloorAtlas  # noqa: E402
from dungeonmaps.data import MAP_H, MAP_W, Data, user_dir  # noqa: E402

# Building parts FDR lists on a floor that are not inside the instance (the WC approach cave, outside
# the portal: build_wailing_map.py leaves them out too).
EXCLUDE = {279: {8111382, 8111387, 8111391, 8111396}}
K = 2  # paste the textures at twice the map frame (their native detail is ~2.5 px per yard)


class Casc:
    def __init__(self, lib, wow):
        self.lib = lib = C.CDLL(lib)
        lib.CascOpenStorage.argtypes = [C.c_char_p, C.c_uint32, C.POINTER(C.c_void_p)]
        lib.CascOpenStorage.restype = C.c_bool
        lib.CascOpenFile.argtypes = [C.c_void_p, C.c_void_p, C.c_uint32, C.c_uint32, C.POINTER(C.c_void_p)]
        lib.CascOpenFile.restype = C.c_bool
        lib.CascGetFileSize.argtypes = [C.c_void_p, C.POINTER(C.c_uint32)]
        lib.CascGetFileSize.restype = C.c_uint32
        lib.CascReadFile.argtypes = [C.c_void_p, C.c_void_p, C.c_uint32, C.POINTER(C.c_uint32)]
        lib.CascReadFile.restype = C.c_bool
        lib.CascCloseFile.argtypes = [C.c_void_p]
        self.h = C.c_void_p()
        if not lib.CascOpenStorage(str(wow).encode(), 2, C.byref(self.h)):
            raise SystemExit("CascLib could not open the game's storage at %s" % wow)

    def read(self, file_id):
        f = C.c_void_p()
        if not self.lib.CascOpenFile(self.h, C.c_void_p(file_id), 2, 3, C.byref(f)):  # by file ID
            return None
        size = self.lib.CascGetFileSize(f, None)
        buf, got = C.create_string_buffer(size), C.c_uint32()
        ok = self.lib.CascReadFile(f, buf, size, C.byref(got))
        self.lib.CascCloseFile(f)
        return buf.raw[:got.value] if ok else None


def fdr_parts(minimaps_lua):
    """{floor: [[file, x, y, w, h, ULx, ULy, LLx, LLy, URx, URy, LRx, LRy, level], ...]} from FDR."""
    floors, cur = {}, None
    for line in Path(minimaps_lua).read_text(encoding="utf-8").splitlines():
        m = re.match(r"\s*\[(\d+)\]\s*=\s*\{", line)
        if m:
            cur = floors.setdefault(int(m.group(1)), [])
            continue
        m = re.match(r"\s*\{\s*([-\d.,\s]+)\}", line)
        if m and cur is not None:
            cur.append([float(v) for v in m.group(1).split(",") if v.strip()])
    return floors


def composite(parts, casc):
    """The floor's minimap textures on its map, K x the 1002x668 frame, RGBA (alpha 0 = no texture)."""
    canvas = Image.new("RGBA", (MAP_W * K, MAP_H * K), (0, 0, 0, 0))
    missing = 0
    for p in sorted(parts, key=lambda p: p[13]):
        raw = casc.read(int(p[0]))
        if raw is None:
            missing += 1
            continue
        image = Image.open(io.BytesIO(raw)).convert("RGBA")
        w, h = max(1, round(p[3] * K)), max(1, round(p[4] * K))
        sw, sh = image.size
        ulx, uly, llx, lly, urx, ury = p[5:11]
        coefficients = ((urx - ulx) * sw / w, (llx - ulx) * sw / h, ulx * sw,
                        (ury - uly) * sh / w, (lly - uly) * sh / h, uly * sh)
        tile = image.transform((w, h), Image.Transform.AFFINE, coefficients, resample=Image.Resampling.BICUBIC)
        canvas.alpha_composite(tile, (round(p[1] * K), round(p[2] * K)))
    return canvas, missing


def to_atlas(data, floor, canvas):
    """Resample the composite onto the floor's atlas grid. Pixels a texture covers are known (the
    textures include their own black void); the rest stays unknown and learnable, so a building part
    FDR's list lacks is learned from runs instead of being fixed as void."""
    a = FloorAtlas(floor, *Atlases(data, folder=os.devnull, reference_dirs=())._extent(floor))
    # (area-average the 2x composite down towards the 1-yard grid before point sampling)
    yards_per_px = 1.0 / (data.px_per_yard(floor) * K)
    blur = max(0.0, 0.5 * RES / yards_per_px - 0.5)
    rgba = np.asarray(canvas.filter(ImageFilter.BoxBlur(blur)) if blur >= 0.5 else canvas).astype(np.float32)
    lum = rgba[..., :3] @ np.array([0.299, 0.587, 0.114], np.float32) * (rgba[..., 3] / 255)
    rows, cols = a.sum.shape
    rr, cc = np.mgrid[0:rows, 0:cols].astype(np.float64)
    u, v = data.to_map(floor, a.n_max - rr * RES, a.w_max - cc * RES)
    x, y = np.floor(u * MAP_W * K).astype(int), np.floor(v * MAP_H * K).astype(int)
    inside = (x >= 0) & (x < MAP_W * K) & (y >= 0) & (y < MAP_H * K)
    known = np.zeros((rows, cols), bool)
    known[inside] = rgba[..., 3][y[inside], x[inside]] >= 250  # (blurred edges are neither)
    gray = np.zeros((rows, cols), np.uint8)
    gray[known] = np.clip(np.round(lum[y[known], x[known]]), 0, 255).astype(np.uint8)
    return a, gray, known


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--wow", required=True, help="the World of Warcraft folder (holds .build.info)")
    ap.add_argument("--casclib", default=os.environ.get("DUNGEONMAPS_CASCLIB", "libcasc.so"))
    ap.add_argument("--fdr", help="ForeverDungeonRoutes/Data/Minimaps.lua (default: in the game's AddOns)")
    ap.add_argument("--floor", type=int, action="append", help="only these floors")
    ap.add_argument("--out", default=os.path.join(user_dir("data"), "reference"))
    ap.add_argument("--preview", help="also write <floor>.png composites here")
    args = ap.parse_args()
    wow = Path(os.path.expanduser(args.wow))
    fdr = Path(args.fdr) if args.fdr else wow / "_forever_/Interface/AddOns/ForeverDungeonRoutes/Data/Minimaps.lua"
    data, parts, casc = Data(), fdr_parts(fdr), Casc(args.casclib, wow)
    ours = {f for d in data.dungeons for f in d["floors"]}
    floors = args.floor or sorted(ours & set(parts))
    os.makedirs(args.out, exist_ok=True)
    for floor in floors:
        if floor not in parts or floor not in data.floors:
            print("floor %d: no FDR minimap textures or not a known floor; skipped" % floor)
            continue
        floor_parts = [p for p in parts[floor] if int(p[0]) not in EXCLUDE.get(floor, ())]
        canvas, missing = composite(floor_parts, casc)
        if missing == len(floor_parts):
            print("floor %d: none of its %d textures are in this client; skipped" % (floor, missing))
            continue
        a, gray, known = to_atlas(data, floor, canvas)
        np.savez_compressed(os.path.join(args.out, "%d.npz" % floor), gray=gray, known=known,
                            res=np.float32(RES), n_max=np.float64(a.n_max), w_max=np.float64(a.w_max))
        if args.preview:
            os.makedirs(args.preview, exist_ok=True)
            canvas.save(os.path.join(args.preview, "%d.png" % floor))
        print("floor %d: %d textures%s -> %s" % (floor, len(floor_parts) - missing,
                                                ", %d missing" % missing if missing else "", args.out))


if __name__ == "__main__":
    main()
