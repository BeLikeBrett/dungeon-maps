"""Tracker logs -> relay -> logs/<day>/<id>.log, through a real relay on a local port."""
import os as _os, tempfile as _tempfile  # noqa: E401
if not _os.environ.get("DUNGEONMAPS_TEST_ISOLATED"):  # never touch the real atlas, calibration or caches
    _tmp = _tempfile.mkdtemp(prefix="dungeonmaps-test-")
    _os.environ.update(XDG_DATA_HOME=_tmp, XDG_STATE_HOME=_tmp, LOCALAPPDATA=_tmp, DUNGEONMAPS_TEST_ISOLATED="1")

import asyncio
import json
import os
import socket
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "relay"))


def main():
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["XDG_STATE_HOME"] = os.environ["LOCALAPPDATA"] = tmp
        import relay
        from dungeonmaps import telemetry
        relay.LOG_DIR = os.path.join(tmp, "logs")
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()
        threading.Thread(target=lambda: asyncio.run(relay.main(port)), daemon=True).start()
        time.sleep(0.5)

        t = telemetry.Telemetry(url="ws://127.0.0.1:%d" % port)
        t.name = lambda: "Brettz"
        t.stats = lambda: {"frames": 900, "ms_avg": 4.2}
        t.record("capturing World of Warcraft")
        t.record("bad\x00line\nwith newline")
        for i in range(500):
            t.record("x" * 900)                     # more than one batch's worth
        assert t.flush(), "flush failed"
        assert len(t.lines) > 0, "a batch must be capped"
        while t.lines:
            assert t.flush()
        time.sleep(0.3)
        day = os.listdir(relay.LOG_DIR)[0]
        text = open(os.path.join(relay.LOG_DIR, day, t.id + ".log"), encoding="utf-8").read()
        assert "Brettz" in text and "capturing World of Warcraft" in text, text[:300]
        assert '"ms_avg":4.2' in text
        assert "bad line with newline" in text      # no control characters reach the file
        assert text.count("===") >= 2
        # bad ids are ignored; a dead relay keeps the lines for later
        from websockets.sync.client import connect
        with connect("ws://127.0.0.1:%d" % port) as ws:
            ws.send(json.dumps({"t": "log", "id": "../../etc", "lines": ["no"]}))
        dead = telemetry.Telemetry(url="ws://127.0.0.1:1")
        dead.record("kept")
        assert not dead.flush(timeout=1) and list(dead.lines)[-1].endswith("kept")
        # pruning: old days go, today stays
        os.makedirs(os.path.join(relay.LOG_DIR, "2000-01-01"))
        relay.prune_logs()
        assert sorted(os.listdir(relay.LOG_DIR)) == [day], os.listdir(relay.LOG_DIR)
        # the same install id every time
        assert telemetry.install_id() == t.id
    print("PASS telemetry")


if __name__ == "__main__":
    main()
