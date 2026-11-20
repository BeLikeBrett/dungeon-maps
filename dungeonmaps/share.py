"""Sharing positions with your group through the Dungeon Maps relay.

Everyone in the same party/raid has the same group number in their beacon (a hash of the members'
GUIDs, made by the addon). Each tracker joins the relay room of that number and sends its position
about 15 times a second while it knows it; the relay passes it to the others in the room, nothing is
stored. A friend's arrow disappears 5 seconds after their last message. Solo (group 0): nothing is
sent.

The connection runs in its own thread, reconnects by itself (backing off up to 30 s), and never
holds up the tracker: send() only replaces the latest message waiting to go out.

Relay: wss://dungeonmaps.brettj.dev by default; DUNGEONMAPS_RELAY=<url> to use another one,
DUNGEONMAPS_RELAY=off to share nothing.
"""

import json
import os
import threading
import time

DEFAULT_RELAY = "wss://dungeonmaps.brettj.dev"
FRIEND_TIMEOUT = 5.0
PROTOCOL = "dungeonmaps/1"


def relay_url():
    url = os.environ.get("DUNGEONMAPS_RELAY", DEFAULT_RELAY).strip()
    return None if url.lower() in ("", "off", "none", "0") else url


class Share:
    def __init__(self, url=None, log=lambda *a: None, connect=None):
        self.url = url or relay_url()
        self.log = log
        self._connect = connect          # tests: a fake connection factory
        self.room = 0
        self.name = ""
        self._out = None                 # latest message waiting to be sent
        self._friends = {}               # name -> (time, state)
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._thread = None
        self.connected = False

    # -- tracker side --------------------------------------------------------------------------------

    def set_room(self, group, name):
        """The group (0 = not grouped: leave) and your name; joins/leaves as they change."""
        if group == self.room and name == self.name:
            return
        with self._lock:
            self.room, self.name = group, name
            self._friends.clear()
            self._out = None
        self._wake.set()
        if group and self.url and self._thread is None:
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()

    def send(self, state):
        with self._lock:
            self._out = state
        self._wake.set()

    def friends(self, now=None):
        """[(name, state)] of everyone else in the group heard from lately."""
        now = time.monotonic() if now is None else now
        with self._lock:
            return [(n, s) for n, (t, s) in self._friends.items() if now - t < FRIEND_TIMEOUT and n != self.name]

    # -- connection thread ---------------------------------------------------------------------------

    def _open(self):
        if self._connect:
            return self._connect(self.url)
        from websockets.sync.client import connect
        return connect(self.url, open_timeout=10, close_timeout=2, max_size=4096,
                       user_agent_header="DungeonMaps")

    def _run(self):
        backoff = 1.0
        while True:
            room, name = self.room, self.name
            if not room:
                self._wake.wait(5)
                self._wake.clear()
                continue
            try:
                ws = self._open()
            except Exception as e:
                self.log("relay: can't connect (%s), retrying in %d s" % (e, backoff))
                time.sleep(backoff)
                backoff = min(30.0, backoff * 2)
                continue
            backoff = 1.0
            try:
                ws.send(json.dumps({"t": "join", "room": "%08x" % room, "name": name, "app": PROTOCOL}))
                self.connected = True
                self.log("relay: joined the group's room")
                self._session(ws, room, name)
            except Exception as e:
                self.log("relay: connection lost (%s)" % e)
            finally:
                self.connected = False
                try:
                    ws.close()
                except Exception:
                    pass

    def _session(self, ws, room, name):
        while self.room == room and self.name == name:
            with self._lock:
                out, self._out = self._out, None
            if out is not None:
                ws.send(json.dumps(dict(out, t="pos"), separators=(",", ":")))
            # read whatever arrived, without blocking the sending for long
            try:
                while True:
                    msg = ws.recv(timeout=0 if out is not None else 0.05)
                    self._receive(msg)
            except TimeoutError:
                pass
            if self._out is None:
                self._wake.wait(0.05)
                self._wake.clear()

    def _receive(self, msg):
        try:
            m = json.loads(msg)
        except ValueError:
            return
        who = m.get("name")
        if not isinstance(who, str):
            return
        with self._lock:
            if m.get("t") == "pos" and all(isinstance(m.get(k), (int, float)) for k in ("u", "v")):
                self._friends[who] = (time.monotonic(), m)
            elif m.get("t") == "left":
                self._friends.pop(who, None)
