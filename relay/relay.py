"""Dungeon Maps relay: passes live positions between trackers in the same group. Stores nothing.

A tracker connects, sends {"t": "join", "room": "<8 hex>", "name": "<character>", "app": "dungeonmaps/1"},
then {"t": "pos", ...} about 15 times a second. Every pos is sent on to the others in the room with
"name" set by the relay (a client can't speak for someone else); when a client leaves, the others get
{"t": "left", "name": ...}.

Limits: 1 KB messages, 30 messages a second per client (extra ones are dropped), 40 per room,
2000 connections in all, 6 h per connection.

    python3 relay.py [--port 8105]      (behind the Cloudflare tunnel: wss://dungeonmaps.brettj.dev)
"""

import argparse
import asyncio
import json
import logging
import re
import time

from websockets.asyncio.server import serve

ROOM_RE = re.compile(r"^[0-9a-f]{8}$")
MAX_ROOM, MAX_CLIENTS, RATE, MAX_AGE = 40, 2000, 30, 6 * 3600
rooms = {}  # room -> {websocket: name}
log = logging.getLogger("relay")


async def handler(ws):
    total = sum(len(r) for r in rooms.values())
    if total >= MAX_CLIENTS:
        await ws.close(1013, "busy")
        return
    try:
        hello = json.loads(await asyncio.wait_for(ws.recv(), 10))
    except Exception:
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
            if count > RATE or not isinstance(raw, str) or len(raw) > 1024:
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


async def main(port):
    async with serve(handler, "0.0.0.0", port, max_size=1024, ping_interval=20, ping_timeout=20,
                     server_header="DungeonMapsRelay"):
        log.info("relay on port %d", port)
        await asyncio.get_running_loop().create_future()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8105)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    asyncio.run(main(ap.parse_args().port))
