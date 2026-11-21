"""Private dataset overview: python tools/samples_report.py /path/to/samples."""
from collections import defaultdict
import json
from pathlib import Path
import statistics
import sys

groups = defaultdict(list)
for path in Path(sys.argv[1]).glob("*/*/*.json"):
    try:
        sample = json.loads(path.read_text())
        groups[sample["dungeon"]].append(sample)
    except (OSError, ValueError, KeyError):
        continue
print("Dungeon\tInstallations\tSamples\tFloors\tMedian correction (yards)")
for key, values in sorted(groups.items()):
    errors = [v["event"]["error_yards"] for v in values if isinstance(v["event"].get("error_yards"), (int, float))]
    print("%s\t%d\t%d\t%s\t%s" % (key, len({v["id"] for v in values}), len(values),
          ",".join(str(f) for f in sorted({v["event"]["floor"] for v in values})),
          "%.1f" % statistics.median(errors) if errors else "unknown"))
