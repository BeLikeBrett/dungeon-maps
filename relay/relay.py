"""Dungeon Maps relay: passes live positions; privately retains bounded diagnostic contributions.

A tracker connects, sends {"t": "join", "room": "<8 hex>", "name": "<character>", "app": "dungeonmaps/1"},
then {"t": "pos", ...} about 15 times a second. Every pos is sent on to the others in the room with
"name" set by the relay (a client can't speak for someone else); when a client leaves, the others get
{"t": "left", "name": ...}.

Limits: 1 KB messages, 30 messages a second per client (extra ones are dropped), 40 per room,
2000 connections in all, 6 h per connection.

Logs (for fixing problems): a tracker may instead open with one {"t": "log", "id": "<32 hex>", "name",
"v", "os", "lines": [...], "stats": {...}} (up to 128 KB) and close. It is appended to
<logs>/<YYYY-MM-DD>/<id>.log. Caps: 4 MB per install per day, 120 log messages a minute in all,
1 GB in all (the oldest days go first), 30 days kept. --logs '' turns this off.

Manual correction samples use t=sample and a persisted sample_ack. samples.py validates compact
minimap-only reports and retains 20 per installation/dungeon, 2 GB total. --samples '' disables.
There is no public dataset read endpoint. Upload writes run off the party relay's event loop.

    python3 relay.py [--port 8105]      (behind the Cloudflare tunnel: wss://dungeonmaps.brettj.dev)
"""

import argparse
import asyncio
import json
import logging
import os
import re
import shutil
import time

from websockets.asyncio.server import serve
from samples import MAX_MESSAGE as SAMPLE_MAX_MSG, SampleStore

ROOM_RE = re.compile(r"^[0-9a-f]{8}$")
ID_RE = re.compile(r"^[0-9a-f]{32}$")
LOG_MAX_MSG, LOG_PER_DAY, LOG_PER_MIN, LOG_TOTAL, LOG_DAYS = 128 * 1024, 4 << 20, 120, 1 << 30, 30
LOG_DIR = None
SAMPLES = None
log_window = [0.0, 0]  # (minute start, messages)
MAX_ROOM, MAX_CLIENTS, RATE, MAX_AGE = 40, 2000, 30, 6 * 3600
rooms = {}  # room -> {websocket: name}
log = logging.getLogger("relay")


async def handler(ws):
    total = sum(len(r) for r in rooms.values())
    if total >= MAX_CLIENTS:
        await ws.close(1013, "busy")
        return
    try:
        raw_hello = await asyncio.wait_for(ws.recv(), 10)
        hello = json.loads(raw_hello)
    except Exception:
        return
    if isinstance(hello, dict) and hello.get("t") == "log":
        if len(raw_hello) <= LOG_MAX_MSG:
            save_log(hello, ws)
        await ws.close()
        return
    if isinstance(hello, dict) and hello.get("t") == "sample":
        try:
            if SAMPLES is None:
                raise ValueError("samples disabled")
            sample_id = await asyncio.to_thread(SAMPLES.save, hello)
            await ws.send(json.dumps({"t": "sample_ack", "ok": True, "sample_id": sample_id}))
        except (ValueError, OSError):
            await ws.send(json.dumps({"t": "sample_ack", "ok": False}))
        await ws.close()
        return
    if not isinstance(hello, dict):
        return
    room, name = hello.get("room"), hello.get("name")
    if hello.get("t") != "join" or not isinstance(room, str) or not ROOM_RE.match(room) \
            or not isinstance(name, str) or not 0 < len(name) <= 24:
        await ws.close(1008, "bad join")
        return
    members = rooms.setdefault(room, {})
    if len(members) >= MAX_ROOM:
        await ws.close(1013, "room full")
        return
    members[ws] = name
    started, window, count = time.monotonic(), time.monotonic(), 0
    try:
        async for raw in ws:
            now = time.monotonic()
            if now - started > MAX_AGE:
                break
            if now - window >= 1:
                window, count = now, 0
            count += 1
            if count > RATE or not isinstance(raw, str) or len(raw) > 1024:  # (pos messages)
                continue
            try:
                m = json.loads(raw)
            except ValueError:
                continue
            if not isinstance(m, dict) or m.get("t") != "pos":
                continue
            m["name"] = name
            out = json.dumps(m, separators=(",", ":"))
            for other in list(members):
                if other is not ws:
                    try:
                        await other.send(out)
                    except Exception:
                        pass
    except Exception:
        pass
    finally:
        members.pop(ws, None)
        if members:
            out = json.dumps({"t": "left", "name": name})
            for other in list(members):
                try:
                    await other.send(out)
                except Exception:
                    pass
        else:
            rooms.pop(room, None)


def clean(v, n):
    """One line of plain text, at most n characters."""
    return re.sub(r"[\x00-\x1f\x7f]", " ", str(v))[:n]


def save_log(m, ws):
    if not LOG_DIR or not isinstance(m.get("id"), str) or not ID_RE.match(m["id"]):
        return
    now = time.time()
    if now - log_window[0] >= 60:
        log_window[0], log_window[1] = now, 0
    log_window[1] += 1
    if log_window[1] > LOG_PER_MIN:
        return
    lines = m.get("lines")
    if not isinstance(lines, list):
        return
    day = time.strftime("%Y-%m-%d", time.gmtime(now))
    folder = os.path.join(LOG_DIR, day)
    path = os.path.join(folder, m["id"] + ".log")
    try:
        os.makedirs(folder, exist_ok=True)
        if os.path.exists(path) and os.path.getsize(path) > LOG_PER_DAY:
            return
        stats = m.get("stats")
        head = "=== %s UTC  %s  v%s  %s  from %s\n" % (
            time.strftime("%H:%M:%S", time.gmtime(now)), clean(m.get("name", ""), 24) or "?",
            clean(m.get("v", "?"), 16), clean(m.get("os", "?"), 80),
            clean((ws.request.headers.get("CF-IPCountry") if ws.request else None) or "?", 4))
        body = "".join("  " + clean(line, 2000) + "\n" for line in lines[:500] if isinstance(line, str))
        if isinstance(stats, dict):
            body += "  stats " + clean(json.dumps(stats, separators=(",", ":"))[:2000], 2000) + "\n"
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(head + body)
    except OSError as e:
        log.warning("log write failed: %r", e)


def prune_logs():
    """Drop days past LOG_DAYS, then the oldest days while over LOG_TOTAL."""
    if not LOG_DIR or not os.path.isdir(LOG_DIR):
        return
    days = sorted(d for d in os.listdir(LOG_DIR) if re.match(r"^\d{4}-\d{2}-\d{2}$", d))
    cutoff = time.strftime("%Y-%m-%d", time.gmtime(time.time() - LOG_DAYS * 86400))
    sizes = {}
    for d in days:
        p = os.path.join(LOG_DIR, d)
        sizes[d] = sum(e.stat().st_size for e in os.scandir(p) if e.is_file())
    total = sum(sizes.values())
    for d in days[:-1]:  # (never today's)
        if d < cutoff or total > LOG_TOTAL:
            shutil.rmtree(os.path.join(LOG_DIR, d), ignore_errors=True)
            total -= sizes[d]


async def pruner():
    while True:
        try:
            prune_logs()
        except Exception as e:
            log.warning("prune failed: %r", e)
        await asyncio.sleep(3600)


async def main(port):
    asyncio.get_running_loop().create_task(pruner())
    async with serve(handler, "0.0.0.0", port, max_size=SAMPLE_MAX_MSG, ping_interval=20, ping_timeout=20,
                     server_header="DungeonMapsRelay"):
        log.info("relay on port %d", port)
        await asyncio.get_running_loop().create_future()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8105)
    ap.add_argument("--logs", default="/logs", help="folder for the trackers' logs ('' = don't keep them)")
    ap.add_argument("--samples", default="/samples", help="private correction dataset ('' = disabled)")
    args = ap.parse_args()
    LOG_DIR = args.logs or None
    SAMPLES = SampleStore(args.samples) if args.samples else None
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    asyncio.run(main(args.port))
