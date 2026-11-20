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
assert len(expected) == 17 and expected == actual, (expected - actual, actual - expected)
assert 'Santiago Reyes' in (ROOT / 'addon/DungeonMaps/maps/CREDITS.txt').read_text()
print('PASS 17 bundled maps: decoded, correct crop, complete references, artist credits')
