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

That's enough for the maps. Bosses, group dots and right-click "I'm here" all work without the tracker.

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
  - So does right-clicking the map where you stand.
  - Pulling a boss sets it too.
  - If you start the tracker partway through a dungeon, it works out where you are by walking. Until
    it's sure, the arrow is dimmed and labelled "You?".
- **Friends:** anyone in your party or raid who also runs the tracker shows up on your map, and you
  on theirs. Nothing to set up. Solo, nothing is sent.
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

To turn sharing off, set the environment variable `DUNGEONMAPS_RELAY=off`, or run the tracker with
`--no-share`. To use your own relay, set `DUNGEONMAPS_RELAY=wss://your.host` (the server is in
`relay/`).

## Credits

- Dungeon layouts, boss and room positions: Forever Dungeon Routes
  data (MIT, Checkov23).
- Hand-drawn Forever maps: Santiago Reyes, Atlas de Azeroth: Forever. Included with the original
  watermarks and credits; these images retain the artist's copyright (see `maps/CREDITS.txt` in the add-on).
- Everything else: MIT, see `LICENSE`.
