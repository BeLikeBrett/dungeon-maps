"""Private sample inventory, separated by dungeon, tracker build and map data."""
import argparse
from collections import defaultdict
import json
import math
from pathlib import Path
import statistics


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path, help="Private server samples directory")
    parser.add_argument("--dungeon", help="Exact dungeon key")
    parser.add_argument("--version", help="Exact recorded tracker version")
    parser.add_argument("--data-sha", help="Exact map-data SHA-256")
    parser.add_argument("--sample-id", help="Select one correction; never pool it with older samples")
    args = parser.parse_args(argv)
    if not args.folder.is_dir():
        parser.error("samples directory does not exist")
    groups = defaultdict(list)
    for path in args.folder.glob("*/*/*.json"):
        try:
            sample = json.loads(path.read_text(encoding="utf-8"))
            dungeon, event, identity = sample["dungeon"], sample["event"], sample["id"]
            if not isinstance(dungeon, str) or not isinstance(identity, str) or not isinstance(event, dict):
                continue
            if not isinstance(event.get("floor"), int):
                continue
            version = sample.get("version") or "unknown"
            data_sha = sample.get("data_sha256") or "unknown"
            if not isinstance(version, str) or not isinstance(data_sha, str):
                continue
            if ((args.dungeon is not None and dungeon != args.dungeon)
                    or (args.version is not None and version != args.version)
                    or (args.data_sha is not None and data_sha != args.data_sha)
                    or (args.sample_id is not None and sample.get("sample_id") != args.sample_id)):
                continue
            groups[dungeon, version, data_sha].append(sample)
        except (OSError, ValueError, KeyError, TypeError):
            continue
    print("Dungeon\tTracker version\tData SHA256\tInstallations\tSamples\tFloors\tMedian correction (yards)")
    for (dungeon, version, data_sha), values in sorted(groups.items()):
        errors = [v["event"].get("error_yards") for v in values]
        errors = [v for v in errors if type(v) in (int, float) and math.isfinite(v) and v >= 0]
        print("%s\t%s\t%s\t%d\t%d\t%s\t%s" % (
            dungeon, version, data_sha, len({v["id"] for v in values}), len(values),
            ",".join(str(f) for f in sorted({v["event"]["floor"] for v in values})),
            "%.1f" % statistics.median(errors) if errors else "unknown"))


if __name__ == "__main__":
    main()
