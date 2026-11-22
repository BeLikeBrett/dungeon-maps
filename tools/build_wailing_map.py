"""Build Wailing Caverns' map artwork from the installed client's minimap textures.

Usage:
  python tools/build_wailing_map.py --tiles /private/extracted-client-tiles \
      [--approach-ref approach-north.png --approach-registration registration.json]

The instance tile IDs/placement come from the generated addon data. Output keeps
that 1002x668 coordinate frame at 2x (bosses and the live arrow are unchanged).
The approach cave is painted in the Atlas 512x512 frame that Approaches.lua's
world-to-pixel coefficients target, at 2x resolution.
"""
import argparse
import json
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

import parchment
from blp import write_blp

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'addon/DungeonMaps/maps'
K = 2  # paint at twice the map frame, downsample at the end


def composite(tiles, scale=1):
    script = ("local n={};assert(loadfile('addon/DungeonMaps/Data.lua'))('DungeonMaps',n);"
              "for _,p in ipairs(n.MinimapArt[279]) do print(table.concat(p,',')) end")
    parts = [list(map(float, line.split(','))) for line in subprocess.check_output(
        ['lua5.1', '-e', script], cwd=ROOT, text=True).splitlines()]
    excluded = {8111382, 8111387, 8111391, 8111396}
    assert len(parts) == 43 and not excluded.intersection(int(p[0]) for p in parts)
    canvas = Image.new('RGBA', (1002*scale, 668*scale), (0, 0, 0, 0))
    for part in sorted(parts, key=lambda p: p[13]):
        with Image.open(tiles / (str(int(part[0])) + '.blp')) as source:
            image = source.convert('RGBA')
        width, height = max(1, round(part[3]*scale)), max(1, round(part[4]*scale))
        sw, sh = image.size
        ulx, uly, llx, lly, urx, ury, _, _ = part[5:13]
        coefficients = ((urx-ulx)*sw/width, (llx-ulx)*sw/height, ulx*sw,
                        (ury-uly)*sh/width, (lly-uly)*sh/height, uly*sh)
        tile = image.transform((width, height), Image.Transform.AFFINE, coefficients,
                               resample=Image.Resampling.BICUBIC if scale > 1 else Image.Resampling.BILINEAR)
        canvas.alpha_composite(tile, (round(part[1]*scale), round(part[2]*scale)))
    return canvas


def walk_mask(canvas):
    # The tracker's passage mask: unchanged geometry rule, independent of the artwork.
    pixels = np.asarray(canvas)
    rgb = pixels[:, :, :3].astype(float)
    floor = (pixels[:, :, 3] > 100) & (rgb.max(2) > 38)
    mask = Image.fromarray((floor*255).astype('uint8')).filter(ImageFilter.MaxFilter(3))
    mask = mask.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.MedianFilter(3))
    mask.save(ROOT/'dungeonmaps/data/wailing_instance_walk.png')


def save(image, name, size):
    """Pad to a power-of-two BLP (the addon crops with texcoords)."""
    padded = Image.new('RGB', (size, size), image.getpixel((2, 2)))
    padded.paste(image, (0, 0))
    write_blp(padded, OUT / (name+'.blp'))
    return padded


def instance(tiles, preview):
    walk_mask(composite(tiles))  # tracker mask: always from the 1x composite
    canvas = composite(tiles, K)  # art: client textures at native ~2x detail
    # Painted at 2x the 1002x668 frame into a 2048 texture: same texcoord crop
    # ratios as the old 1024 one, twice the detail on screen.
    art = parchment.paint(canvas, scale=K, seed=7, density=K)
    parchment.compass(art, 118*K, 590*K, 38*K)
    save(art, 'wailing_caverns_instance', 2048)
    if preview:
        art.save(preview/'wailing_caverns_instance.png')


# Atlas-frame (512 px) marker spots, measured from the original Atlas entrance
# map that Approaches.lua's coefficients were registered against.
ENTRANCE, PORTAL = (58, 416), (270, 350)
CREATURES = [('1', (40, 224)), ('1', (171, 297)), ('1', (125, 371)),
             ('2', (309.5, 244)), ('3', (293, 320))]


def approach(reference, registration, preview):
    S = 2*K  # approach texture is 1024 for the 512 Atlas frame; paint at 2x that
    matrix = np.array(json.loads(registration.read_text())['matrix'])  # reference px -> Atlas px
    A = np.vstack([matrix, [0, 0, 1]])
    inv = np.linalg.inv(A)
    # Output pixel (Atlas*S) -> reference pixel.
    scale = np.diag([1/S, 1/S, 1])
    m = inv @ scale
    with Image.open(reference) as source:
        ref = source.convert('RGBA')
    size = 512*S
    raw = ref.transform((size//K, size//K), Image.Transform.AFFINE,
                        tuple((m @ np.diag([K, K, 1]))[:2].ravel()), resample=Image.Resampling.BICUBIC)
    art = parchment.paint(raw, scale=K, seed=11, pools=True, water=False)

    mask = parchment.floor_mask(raw, scale=1)  # at 512*2 = Atlas*2
    half = mask[::2, ::2]
    path = parchment.walk_path(half, ENTRANCE, PORTAL)
    pts = [(x*S, y*S) for x, y in path]
    parchment.route(art, pts, (150, 34, 22), width=2.6*K*2, arrow_every=60*S, dashed=True)

    parchment.compass(art, 452*S, 60*S, 30*S)
    for text, (x, y) in CREATURES:
        parchment.badge(art, x*S, y*S, text, 9*S)
    parchment.badge(art, ENTRANCE[0]*S, ENTRANCE[1]*S, 'A', 11*S, fill=(36, 82, 40))
    parchment.badge(art, PORTAL[0]*S, PORTAL[1]*S, 'B', 11*S, fill=(84, 42, 120), glow=(170, 110, 230))
    parchment.label(art, (ENTRANCE[0]+16)*S, (ENTRANCE[1]+2)*S, 'Cave mouth', 13*S)
    final = art.resize((1024, 1024), Image.Resampling.LANCZOS)
    save(final, 'wailing_caverns_approach', 1024)
    if preview:
        final.save(preview/'wailing_caverns_approach.png')


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--tiles', type=Path, required=True)
    parser.add_argument('--approach-ref', type=Path)
    parser.add_argument('--approach-registration', type=Path)
    parser.add_argument('--preview', type=Path, help='also write PNG previews to this folder')
    args = parser.parse_args()
    instance(args.tiles, args.preview)
    print('Built WC instance map (2048) from 43 client parts; approach chamber excluded')
    if args.approach_ref:
        approach(args.approach_ref, args.approach_registration, args.preview)
        print('Built WC approach map in the Atlas frame (1024x1024)')


if __name__ == '__main__':
    main()
