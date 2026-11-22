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
Use a Quickshell package built for your installed Qt version. `DUNGEONMAPS_QUICKSHELL=/path/to/quickshell`
selects an optional per-app runtime.

## Using it

- Defeated bosses reset automatically on a fresh living entry into a dungeon. Reloading the UI,
  logging back in inside, and corpse returns preserve progress. `/dmaps reset` clears it manually.
- Open the dungeon map in a dungeon. Your arrow appears once the tracker knows where you are:
  - Walking in through the entrance sets it straight away.
  - So does Shift+clicking the map where you stand.
  - Fixed boss encounters can weakly guide a search. Patrol pins never set your position.
  - If you start the tracker partway through a dungeon, it works out where you are by walking. Until
    it's sure, a localized estimate is labelled "You?".
- **Friends:** anyone in your party or raid who also runs the tracker shows up on your map, and you
  on theirs. Nothing to set up. Solo, nothing is sent.
- The tracker uses guide routes and their connections in the background to help tell nearby
  passages apart. It draws no route lines, allows backtracking and shortcuts, and checks room
  changes and active boss encounters too. The arrow is labelled "You?" when its accuracy is uncertain.
- Boss labels use the creature's name where the encounter title differs; hover to see that title.
  For an unambiguous single-boss encounter, the addon also remembers the game's actual boss-unit
  name in your language.
- Fresh positions stay fully visible, with "You?" for uncertainty. Fading means minimap frames
  have stopped arriving. Repeated strong minimap matches restore confidence automatically;
  a rejected motion reading still prevents unsafe calibration learning.
  Boss pulls never set your position. Fixed bosses can provide one soft hint during a search;
  roaming bosses do not pull the estimate toward their map icons.
  Impossible minimap jumps are discarded and do not train scale calibration or the learned map.
- On Linux, the arrow uses a cached vector shape and short, bounded display prediction between
  captures. Corrections and heading changes remain immediate. Dragging the map moves markers
  within a fixed transparent surface. The beacon sits above the minimap to reduce screenshot
  capture size; neither the capture rate nor tracking rate increases.
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

**Local tracking evidence:** the tracker keeps up to three minutes of minimap crops and tracking
context in a bounded memory buffer (128 MB). Corrections and recovery events save clips under
`state/recordings/<dungeon>/<date>/trace-*.zip`. A compact, once-per-second
`session-*.jsonl` timeline records accepted and failed readings, zoom, confidence, movement and
calibration profile. Disk writes and image compression run in background threads.
It retains up to 200 clips within a 2 GB total budget, preserving manual correction clips and
session timelines ahead of automatic snapshots. Older flat recordings remain readable and count
against that budget. Full recordings stay on your computer; the community upload size is unchanged.
Set `DUNGEONMAPS_RECORDING=off` to disable both local pictures and timelines.
`python tools/replay_trace.py <trace.zip>` reprocesses sampled minimaps with isolated caches;
it starts from the recorded estimate, so this is an approximate comparison, not an exact replay
or independent proof of every position. Exact rejected image-match snapshots are included too.

Calibration profiles are separate for each dungeon and minimap zoom/indoor setting. Learned
minimap atlases are stored per floor. The tracker handles close-zoom global recovery with a coarse
search followed by detailed verification, and excludes known tooltip/map overlap reported by the
addon. A boss pin alone never sets your position; known patrols provide no spatial weighting.

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
