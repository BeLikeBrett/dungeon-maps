"""Draws the Dungeon Maps icon: addon/DungeonMaps/icon.tga (add-on list) and packaging/icon.ico (exe).
    python3 tools/make_icon.py"""
import math
import os
import random

from PIL import Image, ImageDraw, ImageFilter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
S = 256
WALL, FLOOR = (110, 78, 40, 255), (246, 226, 168, 255)


def draw():
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((6, 6, S - 6, S - 6), 34, fill=(46, 38, 30, 255), outline=(20, 16, 12, 255), width=6)
    d.rounded_rectangle((16, 16, S - 16, S - 16), 26, fill=(196, 160, 80, 255))
    par = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    pd = ImageDraw.Draw(par)
    pd.rounded_rectangle((26, 26, S - 26, S - 26), 18, fill=(224, 196, 140, 255))
    rnd = random.Random(4)
    for _ in range(900):
        x, y, c = rnd.randint(28, S - 28), rnd.randint(28, S - 28), rnd.randint(-22, 10)
        pd.point((x, y), fill=(214 + c, 182 + c, 120 + c, 255))
    im.alpha_composite(par.filter(ImageFilter.GaussianBlur(0.6)))
    d = ImageDraw.Draw(im)
    # rooms and corridors: the light walkable paths of a dungeon map
    rooms = [(48, 152, 112, 210), (150, 56, 210, 112), (150, 158, 210, 210)]
    paths = [[(80, 180), (80, 84), (180, 84)], [(80, 180), (180, 184)]]
    for colour, grow, width in ((WALL, 4, 26), (FLOOR, 0, 16)):
        for p in paths:
            d.line(p, fill=colour, width=width, joint="curve")
        for r in rooms:
            d.rounded_rectangle((r[0] - grow, r[1] - grow, r[2] + grow, r[3] + grow), 8 + grow, fill=colour)
    # boss skull
    cx, cy = 180, 84
    d.ellipse((cx - 17, cy - 19, cx + 17, cy + 13), fill=(30, 22, 18, 255))
    d.rectangle((cx - 9, cy + 6, cx + 9, cy + 19), fill=(30, 22, 18, 255))
    d.ellipse((cx - 10, cy - 8, cx - 2, cy + 1), fill=(220, 40, 30, 255))
    d.ellipse((cx + 2, cy - 8, cx + 10, cy + 1), fill=(220, 40, 30, 255))
    # a friend: class-coloured dot
    d.ellipse((167, 171, 193, 197), fill=(0, 0, 0, 255))
    d.ellipse((170, 174, 190, 194), fill=(255, 124, 10, 255))
    # you: the gold arrow, heading up the corridor
    ax, ay, ang = 80, 168, 0.0
    shape = [(0, -40), (24, 30), (0, 16), (-24, 30)]
    pts = [(ax + x * math.cos(ang) - y * math.sin(ang), ay + x * math.sin(ang) + y * math.cos(ang)) for x, y in shape]
    d.line(pts + [pts[0]], fill=(0, 0, 0, 255), width=12, joint="curve")
    d.polygon(pts, fill=(255, 210, 77, 255))
    d.line(pts + [pts[0]], fill=(0, 0, 0, 255), width=5, joint="curve")
    return im


if __name__ == "__main__":
    im = draw()
    im.save(os.path.join(ROOT, "packaging", "icon.ico"), sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    im.resize((64, 64), Image.LANCZOS).save(os.path.join(ROOT, "addon", "DungeonMaps", "icon.tga"))
    im.save(os.path.join(ROOT, "packaging", "icon.png"))
