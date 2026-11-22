"""Build WC's instance-only navigation artwork from the installed client's BLP tiles.

Usage: python tools/build_wailing_map.py --tiles /private/extracted-client-tiles
The tile IDs/placement come from the generated addon data. Output retains that
1002x668 coordinate frame; it does not infer new player or boss coordinates.
"""
import argparse
import json
import math
from pathlib import Path
import subprocess

import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from blp import write_blp

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tiles', type=Path, required=True)
    args = parser.parse_args()
    script = "local n={};assert(loadfile('addon/DungeonMaps/Data.lua'))('DungeonMaps',n);for _,p in ipairs(n.MinimapArt[279]) do print(table.concat(p,',')) end"
    parts = [list(map(float, line.split(','))) for line in subprocess.check_output(
        ['lua5.1', '-e', script], cwd=ROOT, text=True).splitlines()]
    excluded = {8111382, 8111387, 8111391, 8111396}
    assert len(parts) == 43 and not excluded.intersection(int(p[0]) for p in parts)
    canvas = Image.new('RGBA', (1002, 668), (0, 0, 0, 0))
    for part in sorted(parts, key=lambda p: p[13]):
        with Image.open(args.tiles / (str(int(part[0])) + '.blp')) as source:
            image = source.convert('RGBA')
        width, height = max(1, round(part[3])), max(1, round(part[4]))
        sw, sh = image.size
        ulx, uly, llx, lly, urx, ury, _, _ = part[5:13]
        coefficients = ((urx-ulx)*sw/width, (llx-ulx)*sw/height, ulx*sw,
                        (ury-uly)*sh/width, (lly-uly)*sh/height, uly*sh)
        tile = image.transform((width, height), Image.Transform.AFFINE, coefficients,
                               resample=Image.Resampling.BILINEAR)
        canvas.alpha_composite(tile, (round(part[1]), round(part[2])))
    pixels = np.asarray(canvas)
    rgb = pixels[:, :, :3].astype(float)
    floor = (pixels[:, :, 3] > 100) & (rgb.max(2) > 38)
    mask = Image.fromarray((floor*255).astype('uint8')).filter(ImageFilter.MaxFilter(3))
    mask = mask.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.MedianFilter(3))
    # Ship the geometry mask separately. UI route lines and the texture atlas
    # (which also sees walls/void) must not redefine walkable WC passages.
    mask.save(ROOT/'dungeonmaps/data/wailing_instance_walk.png')
    water = ((rgb[:, :, 2] > rgb[:, :, 0]*1.13) & (rgb[:, :, 1] > rgb[:, :, 0]*1.08)
             & (rgb[:, :, 2] > 75) & floor)
    water = Image.fromarray((water*255).astype('uint8')).filter(ImageFilter.MaxFilter(3))
    water = water.filter(ImageFilter.MedianFilter(5))
    rng = np.random.default_rng(4)
    paper = np.clip(np.full((668, 1002, 3), [114, 76, 36]) + rng.normal(0, 1.2, (668, 1002, 1)), 0, 255).astype('uint8')
    chart = Image.fromarray(paper)
    chart.paste((51, 37, 24), mask=mask.filter(ImageFilter.MaxFilter(7)))
    chart.paste((211, 192, 149), mask=mask)
    chart.paste((84, 139, 149), mask=Image.fromarray(np.minimum(np.asarray(water), np.asarray(mask))))
    inner = np.asarray(mask, dtype=int) - np.asarray(mask.filter(ImageFilter.MinFilter(3)), dtype=int)
    chart.paste((155, 128, 83), mask=Image.fromarray(inner.clip(0, 255).astype('uint8')))
    output = ROOT / 'addon/DungeonMaps/maps'

    def save(image, name):
        padded = Image.new('RGB', (1024, 1024), (114, 76, 36))
        padded.paste(image, (0, 0))
        write_blp(padded, output / (name+'.blp'))

    save(chart, 'wailing_caverns_instance')
    guided = chart.copy()
    draw = ImageDraw.Draw(guided)
    data = json.loads((ROOT/'dungeonmaps/data/dungeons.json').read_text(encoding='utf-8'))
    paths = data['routes']['wailingcaverns']['paths']
    for index, path in enumerate(paths):
        points = [(u*1002, v*668) for u,v in zip(path['pts'][::2], path['pts'][1::2])]
        # The first trace continues with the walk back after Verdan. Keep the
        # outbound circuit clear; the second trace is Naralex's escort path.
        if index == 0:
            points = points[:254]
        colour = (31, 99, 113) if index == 0 else (168, 109, 34)
        draw.line(points, fill=(238, 224, 185), width=7, joint='curve')
        draw.line(points, fill=colour, width=3, joint='curve')
        since = 0.0
        for a,b in zip(points[:-1], points[1:]):
            dx,dy=b[0]-a[0],b[1]-a[1]
            length=math.hypot(dx,dy);since += length
            if length < 1 or since < 45:
                continue
            ux,uy=dx/length,dy/length
            x,y=b
            triangle=[(x+5*ux,y+5*uy),(x-5*ux+4*uy,y-5*uy-4*ux),(x-5*ux-4*uy,y-5*uy+4*ux)]
            draw.polygon(triangle, fill=colour)
            since=0
    save(guided, 'wailing_caverns_route')
    print('Built two instance-only WC maps, same world frame, 43 client parts; approach excluded')


if __name__ == '__main__':
    main()
