"""Verify every referenced bundled BLP decodes and crops to the addon's canvas aspect ratio."""
import subprocess
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
manifest = subprocess.check_output(['lua5.1', '-e', r"""
local ns = {}
assert(loadfile("addon/DungeonMaps/Data.lua"))("DungeonMaps", ns)
for floor, info in pairs(ns.Floors) do
  if info.image then
    io.write(floor, "\t", info.image.file, "\t", info.image.right or 1, "\t", info.image.bottom or 1, "\n")
  end
end
"""], cwd=ROOT, text=True)
expected = set()
for line in manifest.splitlines():
    floor, file, right, bottom = line.split('\t')
    relative = file.replace('\\', '/') + '.blp'
    expected.add(relative)
    path = ROOT / 'addon/DungeonMaps' / relative
    with Image.open(path) as art:
        art.load()  # includes decoding every compressed image block, not just its header
        assert art.format == 'BLP' and art.size == (1024, 1024), (relative, art.format, art.size)
        width, height = art.size
        right, bottom = float(right), float(bottom)
        assert 0 < right <= 1 and 0 < bottom <= 1, relative
        crop = art.crop((0, 0, round(width * right), round(height * bottom))).convert('RGB')
        assert abs(crop.width / crop.height - 1002 / 668) < 0.01, relative
        assert any(hi - lo > 30 for lo, hi in crop.getextrema()), ('blank map', relative)
    print('OK', floor, relative)
actual = {p.relative_to(ROOT / 'addon/DungeonMaps').as_posix()
          for p in (ROOT / 'addon/DungeonMaps/maps').glob('*.blp')}
extra = {'maps/wailing_caverns_route.blp', 'maps/wailing_caverns_approach.blp'}
assert len(expected) == 18 and expected | extra == actual, ((expected | extra) - actual, actual - expected - extra)
for name in extra:
    with Image.open(ROOT / 'addon/DungeonMaps' / name) as image:
        image.load()
        assert image.format == 'BLP' and image.size == ((512, 512) if 'approach' in name else (1024, 1024))
assert 'Santiago Reyes' in (ROOT / 'addon/DungeonMaps/maps/CREDITS.txt').read_text()
print('PASS 17 Santiago maps plus WC instance/plain/approach artwork: decoded, correct crop and credits')

# Wailing Caverns' later-version parchment omits the Winding Chasm. Its
# replacement uses all client building parts in the existing coordinate frame.
subprocess.run(['lua5.1', '-e', r"""
local ns = {}
assert(loadfile("addon/DungeonMaps/Data.lua"))("DungeonMaps", ns)
assert(ns.Floors[279].terrain and #ns.MinimapArt[279] == 43)
for floor, info in pairs(ns.Floors) do
  if floor ~= 279 then assert(not info.terrain, "another floor's renderer changed") end
end
for floor in pairs(ns.MinimapArt) do assert(floor == 279) end
local excluded = {[8111382]=true,[8111387]=true,[8111391]=true,[8111396]=true}
for _, part in ipairs(ns.MinimapArt[279]) do
  assert(not excluded[part[1]], "approach chamber leaked into instance")
  assert(#part == 14 and part[1] > 0 and part[4] > 0 and part[5] > 0)
  assert(part[2] >= 0 and part[3] >= 0 and part[2]+part[4] <= 1002.02 and part[3]+part[5] <= 668.02)
end
for _, boss in ipairs(ns.Bosses.wailingcaverns) do
  local x,y,covered = boss.x*1002, boss.y*668, false
  for _, part in ipairs(ns.MinimapArt[279]) do
    if x >= part[2] and x <= part[2]+part[4] and y >= part[3] and y <= part[3]+part[5] then covered=true end
  end
  assert(covered, "no terrain coverage at "..boss.name)
end
print("PASS Wailing Caverns terrain bounds cover all eight pins, including the east wing; other floors unchanged")
"""], cwd=ROOT, check=True)
