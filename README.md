# Dungeon Maps

Dungeon maps for **WoW: Forever**. Inside a dungeon, your map key opens a big map of
the floor you're on, with the bosses and your group marked. Outside a dungeon the key works as normal.

With the **tracker** running as well, the map shows a live arrow for where you are and which way
you're facing. **Everyone in your group who runs it shows up too**, as a dot in their class colour
with their name, at their exact spot.

The tracker only looks at the game window (the minimap and a small coloured strip the add-on draws
in the top-left corner). It never reads or touches the game's memory or files.

## Install

### 1. The add-on (everyone)

1. Download `DungeonMaps-addon.zip` from the [latest release](../../releases/latest).
2. Unzip it into `World of Warcraft\_forever_\Interface\AddOns\`. You should end up with
   `AddOns\DungeonMaps\DungeonMaps.toc`.
3. Fully restart WoW. Santiago Reyes's hand-drawn maps for all 17 Forever floors are included;
   **Forever Dungeon Routes is not required**.

That's enough for the maps. Bosses, group dots and Shift+click "I'm here" all work without the tracker.

### 2. The tracker (for the live arrows)

**Windows:** download `DungeonMaps.exe` from the release and run it, before or after starting WoW.
- When you open it, it asks permission to read the WoW window. After you allow it, it runs in the
  system tray. Right-click its icon and choose **Close** whenever you want.
  It also closes automatically three seconds after WoW closes.
- Its log is at `%LOCALAPPDATA%\DungeonMaps\state\tracker.log`.
- WoW must be in **Windowed** or **Windowed (Fullscreen)** mode, because exclusive fullscreen hides
  overlays.
- Windows SmartScreen may warn about an unknown app the first time: click "More info", then "Run anyway".
- No yellow border: where Windows allows borderless window capture, it uses that (tracking keeps
  going while another window covers WoW). Otherwise (Windows 10, or the permission off) it reads the
  screen instead, which only sees WoW while it's the active window. Either way the arrows only show
  over WoW.
- **Updates itself:** each time it opens it checks GitHub for a newer release, swaps in the new exe
  and updates the add-on in your `_forever_` folder. A tray message tells you to `/reload` if WoW
  is open. `DUNGEONMAPS_UPDATE=off` turns this off.

**Linux (Wayland):** needs Python 3 with `numpy`, `Pillow` and `websockets`, GStreamer with the
PipeWire plug-in plus `python-gobject` (for window capture), `grim`, and
[Quickshell](https://quickshell.org) for the overlay.

```sh
tar xzf DungeonMaps-linux.tar.gz
dungeon-maps/linux/dungeon-maps          # or: dungeon-maps start / stop, e.g. as launcher hooks
```

When WoW is open a "share a window" dialog appears: pick World of Warcraft.
If that stream fails, it falls back to screenshots of the visible game without asking again.
Automatic crash recovery also uses screenshots, so it won't repeatedly reopen the picker.

## Using it

- Open the dungeon map in a dungeon. Your arrow appears once the tracker knows where you are:
  - Walking in through the entrance sets it straight away.
  - So does Shift+clicking the map where you stand.
  - Pulling a boss sets it too.
  - If you start the tracker partway through a dungeon, it works out where you are by walking. Until
    it's sure, the arrow is dimmed and labelled "You?".
- **Friends:** anyone in your party or raid who also runs the tracker shows up on your map, and you
  on theirs. Nothing to set up. Solo, nothing is sent.
- The tracker uses guide routes and their connections in the background to help tell nearby
  passages apart. It draws no route lines, allows backtracking and shortcuts, and checks room
  changes and active boss encounters too. The arrow is labelled "You?" when its accuracy is uncertain.
- Boss labels use the creature's name where the encounter title differs; hover to see that title.
  For an unambiguous single-boss encounter, the addon also remembers the game's actual boss-unit
  name in your language.
- Uncertain positions stay visible as "You?" instead of blinking out at a confidence threshold.
  Boss pulls preserve a tracked player position; a boss spawn is only a broad hint when you're lost.
  Impossible minimap jumps are discarded and do not train scale calibration or the learned map.
- **Settings:** Esc → Options → AddOns → Dungeon Maps (or `/dmaps settings`) has your arrow's size
  and the live-tracker switch. `/dmaps` lists the other commands.

## What is shared

While you're grouped, inside a dungeon, the tracker sends the following about 15 times a second to
the relay at `dungeonmaps.brettj.dev`:
- your character name;
- the dungeon and floor;
- your spot on the map and your class colour.

The relay passes these straight on to the trackers of people in the same group and keeps nothing.

**Logs:** to help fix problems, the tracker also sends its log to the relay about once a minute:
the same lines as `tracker.log`, crash reports, and a stats line (frames, time per frame, how your
position was found, capture mode). With them go a random install id, your character name, the
tracker version and your OS. No pictures. They are kept for 30 days. `DUNGEONMAPS_LOGS=off` turns
this off.

**Local tracking evidence:** the tracker keeps up to one minute of minimap crops and tracking
context in a bounded memory buffer (30 MB). Shift+click corrections, large position corrections,
and atlas relocations save that buffer to `state/recordings/trace-*.zip` beside the local log.
It retains at most 10 recordings and 100 MB. Full recordings stay on your computer. If the arrow
is wrong, Shift+click your known position while you're there:
the saved lead-up includes the old estimate and your correction for comparison. Set
`DUNGEONMAPS_RECORDING=off` to disable this. `python tools/replay_trace.py <trace.zip>` reprocesses
sampled minimaps with isolated caches; it starts from the recorded estimate, so this is an
approximate comparison, not an exact replay or independent proof of every position.
Rejected movement also saves the exact grayscale reference/current pictures, matching mask and
offsets inside the local archive. The replay tool can reproduce these individual matching decisions
exactly; they are separate from the approximate sampled walk and stay local.

**Community corrections:** with the current addon and tracker, Shift+click also contributes a
compact correction sample to Brett's server. Each sample has your map correction, the old estimate,
movement/confidence context, the data version, and up to six 128×128 minimap pictures from the preceding
minute. Metadata excludes character names, GUIDs, group hashes, and local paths; pictures contain
only the minimap rectangle, resized to 128×128, never the full screen.
Samples use the existing random installation ID (one installation is not a verified unique person).
The server keeps up to **20 recent samples per installation per dungeon**, subject to a 2 GB total
storage cap; samples are private to the server owner. Manual clicks are approximate observations,
not automatically trusted universal map fixes. Upload failures retry from a bounded 40 MB local outbox.
The addon displays a one-time notice. Disable **Share Shift+click corrections and minimap pictures**
in `/dmaps settings`, or set `DUNGEONMAPS_SAMPLES=off`. `DUNGEONMAPS_LOGS=off`,
`DUNGEONMAPS_RECORDING=off`, and `DUNGEONMAPS_RELAY=off` also prevent new sample uploads.
Older addons do not contribute pictures until updated/reloaded.

To turn all relay communication off, set `DUNGEONMAPS_RELAY=off`. The `--no-share` switch disables
live party positions. To use your own relay, set `DUNGEONMAPS_RELAY=wss://your.host` (the server is in
`relay/`).

## Credits

- Dungeon layouts, boss and room positions: Forever Dungeon Routes
  data (MIT, Checkov23).
- Hand-drawn Forever maps: Santiago Reyes, Atlas de Azeroth: Forever. Included with the original
  watermarks and credits; these images retain the artist's copyright (see `maps/CREDITS.txt` in the add-on).
- Everything else: MIT, see `LICENSE`.
