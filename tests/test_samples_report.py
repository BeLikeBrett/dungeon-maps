"""Offline reports must not pool different builds or data, or broaden a selected correction."""
import csv
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile

REPORT = Path(__file__).resolve().parents[1] / "tools/samples_report.py"

with tempfile.TemporaryDirectory() as folder:
    root = Path(folder)

    def save(dungeon, version, data, identity, name, error):
        path = root / dungeon / identity / (name + ".json")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(dict(dungeon=dungeon, version=version, data_sha256=data,
                                       id=identity, sample_id=name,
                                       event=dict(floor=1, error_yards=error))), encoding="utf-8")

    save("ruinsoflordaeron", "1.0.10", "a" * 64, "one", "old", 200)
    save("ruinsoflordaeron", "1.0.11", "a" * 64, "one", "selected", 20)
    save("ruinsoflordaeron", "1.0.11", "a" * 64, "two", "other", 10)
    save("ruinsoflordaeron", "1.0.11", "b" * 64, "one", "different-data", 80)
    save("ragefire", "1.0.11", "a" * 64, "one", "different-dungeon", 30)
    save("ragefire", None, None, "one", "legacy", None)
    (root / "ragefire/one/broken.json").write_text("{", encoding="utf-8")
    (root / "ragefire/one/not-an-object.json").write_text("[]", encoding="utf-8")

    def report(*args):
        out = subprocess.run([sys.executable, str(REPORT), str(root), *args],
                             capture_output=True, text=True, check=True).stdout
        return list(csv.DictReader(io.StringIO(out), delimiter="\t"))

    all_rows = report()
    assert len(all_rows) == 5, all_rows
    rows = report("--dungeon", "ruinsoflordaeron", "--version", "1.0.11")
    assert len(rows) == 2 and {r["Data SHA256"] for r in rows} == {"a" * 64, "b" * 64}
    rows = report("--dungeon", "ruinsoflordaeron", "--version", "1.0.11", "--data-sha", "a" * 64)
    assert len(rows) == 1 and rows[0]["Median correction (yards)"] == "15.0", rows
    assert rows[0]["Installations"] == "2" and rows[0]["Samples"] == "2", rows
    rows = report("--sample-id", "selected")
    assert len(rows) == 1 and rows[0]["Samples"] == "1" and rows[0]["Median correction (yards)"] == "20.0", rows
    assert report("--sample-id", "absent") == []
    assert report("--version", "unknown")[0]["Median correction (yards)"] == "unknown"

print("PASS sample report keeps dungeon/build/data groups separate and supports one-correction scope")
