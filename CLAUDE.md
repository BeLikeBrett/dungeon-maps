# Dungeon Maps: working notes

## Latest: v1.0.8 live glitch repair (2026-11-21)
- Live logs showed 100–300-yard image-matching jumps in seconds; poisoned i2z0 calibration grew to
  1.133 (per-particle ~1.15). Boss pulls also hard-seeded ranged players at spawn pins, and spread
  oscillating around 6 yd hid the arrow. User's 08:58:05 mark immediately contradicted a boss snap.
- Odometry rejects candidate steps larger than (2 + 30 * min(elapsed,.5)) world yards BEFORE changing
  offsets/static learning. Reset/rebase prevents an opposite phantom jump next frame. Core clears
  the invalid trail and excludes the broken segment from calibration and map learning. Real teleports
  or unusually fast knockbacks may require visual reacquisition or a fresh user mark.
- Known, uncertain poses stay visible/dim (displayable separate from found); whole-floor searches
  remain hidden. Boss pins seed only unknown/different-floor/searching poses, spread 25 yd; never
  teleport an already tracked ranged player. Cached manual markers at startup are ignored as stale.
- Scale pairs accepted only .8..1.25, no learning across rejected motion, and each accepted pair
  changes log scale by <=.04 with its Kalman uncertainty updated consistently.
- Live repair started v1.0.8 at 09:06, no capture prompt. Restored known calibration from backup
  dungeonmaps-before-route-context-20261121-075232 and Lordaeron atlas from dungeonmaps-v105-20261121-082523.
  Faulty state + all four available recordings preserved at user data research/glitch-20261121-090318/.
  Fresh user mark 09:08:20 arrived; later motion plausible, scale ~.96, no new impossible jumps observed
  through 09:13. User feedback, not particle spread, is required to confirm actual game accuracy.
- Sparse old PNGs did not reproduce the transient spike, despite recorded raw path inflation. New
  rejects retain exact NCC key/current/mask/offset/max-step arrays (<=3 cases) locally inside trace ZIPs.
  tools/replay_trace.py replays these cases exactly; normal sampled route remains approximate.
  Community sample policy/server unchanged; exact-case arrays are never uploaded.
- Regression tests: impossible high-score peak + rebase, no opposite jump, scale poisoning, stable
  dim arrow across 5.9/6.1/25 yd spreads, ranged pulls, unknown-boss recovery, stale startup mark.
  Full pipeline/atlas and other Linux checks passed; recorder case round-trip/replay passes.

## v1.0.7 Windows locale fix (2026-11-21)
- v1.0.6's Windows CI exposed that Data() used the platform's default encoding. The newly retained
  international encounter aliases require explicit UTF-8; fixed and covered under a simulated cp1252
  file default. v1.0.6 tag is retained as failed history; v1.0.7 delivers the corrected release.

## Latest: v1.0.6 correction learning and community dataset (2026-11-21)
- Explicit Shift+click fixes now REPLACE conflicting pixels in the visible minimap footprint
  instead of blending weight-4 corrections with old weight-12 texture. Entrance estimates retain
  the previous gentle behavior. Unknown/masked pixels remain intact. Latest age guards still apply.
- Brett's first private trace was a castle spiral staircase: circling while climbing indoors.
  Kept privately at ~/.local/share/dungeon-maps/research/castle-20261121/. Do not commit recordings.
  Its 14.4-yard correction is useful evidence, not proof that elevation caused the drift. Recreated
  wrong-atlas experiment using the real image: blended correction retained 14.4 yd offset; replacing
  the footprint learned the corrected reference (~0.03 yd numerical alignment, not live accuracy).
- Recorder now retains walked distance and raw net odometry in future samples, so stair loops can
  be distinguished from earlier translation bias. Local archives remain bounded and private.
- Community uploads: native settings checkbox + one-time local notice; beacon **v6, still 58 cells**
  adds contribute (1 bit). Decode v4/v5 too, default contribute=0 until the new addon loads.
  samples.py sends ONLY manual marks: <=6 128x128 minimap PNGs + selected non-identifying metadata,
  current data SHA, approximate correction, random installation ID. One installation != unique human.
  Opt-out via checkbox, DUNGEONMAPS_SAMPLES/LOGS/RECORDING/RELAY=off. Pending outbox <=40 MB,
  20 per dungeon, retries every 30 s / max one successful report per 10 s; require persisted ack.
- Relay deployed at ~/dungeonmaps-relay on brettserver, existing public WSS unchanged. New private
  samples volume: samples/<dungeon>/<install-id>/<sample-id>.json, <=20 per bucket, <=2 GB total,
  8 uploads/install/min and 60/min total, <=512 KB payload. No public read API. Keep .dockerignore
  so data/logs/backups never enter image builds. samples_report.py reports per-dungeon coverage.
- Actual castle sample e90e0335ae328271d84a64129e8a835c acknowledged over PUBLIC WSS and verified
  on the server; uploaded capture version 1.0.5, one manual reference, six thumbnails (~266 KB).
  Owner annotation records spiral-staircase context. No other users' data was accessed/published.
- Server tests exercise malformed uploads, ID/path isolation, quotas, retry/ack, opt-out and party
  relay coexistence. New samples test added to CI; existing Linux + Windows jobs remain required.
- All 13 Linux test scripts + Lua harness passed for v1.0.6. Installed addon byte-verified and
  restarted exactly once in screenshot mode. Re-taught only the castle's stationary final minimap
  footprint at its manual reference; preserved the rest of the learned atlas. Backup:
  ~/.local/share/wow-addon-backups/dungeonmaps-v105-20261121-082523/. /reload needed for beacon v6.

## v1.0.5 tracking context (2026-11-21; supersedes older beacon/trust notes)
- Hidden guide context: `routes.py` samples the 122 imported route traces into small floor graphs.
  Run every 3 yards, soft weights only when >=65% of particle mass is near a known trace; no route
  drawing, forced boss order, hard walls, or penalty for disconnected guide scraps.
- Repeated room hints every 5 yards; a room exclusive to a different floor triggers a new search.
  Active boss hints have a wide radius and expire after 40 yards of movement. Kills alone never
  locate the player. Beacon **v5, 58 cells** adds active_boss (6 bits) and boss_mask (32 bits).
  Tracker still reads v4 until the addon reloads. Encoder twins and Lua harnesses cover both.
- Independent uncertainty grows with distance since a real fix; atlas agreement cannot reset that
  trust. Boss spawn pins cannot calibrate scale or repaint an atlas as an exact player position.
- All atlas searches exclude recent writes (including repaints and their interpolated edges).
  Whole-floor and large-jump relocations require 3 consistent matches across >=5 yards. Background
  results are invalidated by dungeon, landmark, room, minimap settings, or encounter changes.
- Audited all 212 existing boss pins against FDR's client DungeonEncounter IDs (70862). Five known
  creature/encounter differences corrected: The Baron/3355, Magmatus/3495, Arcanic Enigma/3301,
  Overlord Mugg/3451, Deathless Marrow/3478. Basis: FDR guide notes explicitly naming the creatures.
  Retain known creature labels (Sneed's Shredder, Gelihast, Ras Frostwhisper) and client encounter
  titles as aliases. Shared encounters resolve exact names before IDs (Mograine/Whitemane).
  `bossLabel` learns native boss-unit names per locale/encounter only for one pin + one boss unit;
  no target/add-based renaming. New/missing boss positions are not invented.
- Test with `python tests/test_context.py` plus the existing CI suite. Its microbenchmark measures
  both tracking (500 particles) and global search (4000); synthetic pipeline geography disables real
  guide routes deliberately. Both generated data files still come from one extractor invocation.
- Added bounded, local-only diagnostic evidence at Brett's request: `recording.py` retains native
  minimap crops at 2 Hz for <=60 s / 30 MB RAM; manual/large corrections and atlas relocations
  save PNGs plus beacon/position/confidence/odometry-score/route context. Background ZIP writes,
  10 s throttle, <=10 archives / 100 MB retained in state/recordings. No screenshots are uploaded.
  DUNGEONMAPS_RECORDING=off disables. `tools/replay_trace.py` uses isolated caches, the recorded
  starting estimate, and sampled minimaps: approximate comparison, not exact full-frequency replay.
  `tests/test_recording.py` checks lossless crops, real correction callback, replay, and limits.
- Validation: all existing Linux CI tests passed, plus context/recorder regressions and Lua harnesses.
  The stricter global search initially broke reacquisition; corrected by using a unique global seed
  followed by motion-consistent local matches. Final full atlas test passed: mid-run reacquisition
  <8 s / <5 yd; learned-atlas drift <4 yd. Route checks ~2 ms / 500 particles every 3 yards.
- Installed v1.0.5 byte-verified into Brett's active Faugus addon. Restarted the Linux tracker once
  in screenshot mode (no permission picker); startup log confirms v1.0.5, exactly one overlay/worker.
  Brett must /reload for new addon labels and beacon v5 context; tracker reads the current v4 meanwhile.
  Backup of previous addon, atlas, calibration: ~/.local/share/wow-addon-backups/
  dungeonmaps-before-route-context-20261121-075232/. No public release/push in this task.

Add-on (Lua, WoW: Forever, Interface 16001) + live tracker (Python) + relay (Python, brettserver).
Public repo: github.com/BeLikeBrett/dungeon-maps. Plan and status: PLAN.md.

## Layout
- `addon/DungeonMaps/`: the add-on. `Data.lua` is generated by `tools/extract.lua` from Forever
  Dungeon Routes' data (same run writes `dungeonmaps/data/dungeons.json`; the beacon sends indexes,
  so the two must come from one run).
- `dungeonmaps/`: the tracker package.
  - `core.py`: shared per-frame logic.
  - `linux.py`: portal capture, grim, Quickshell output.
  - `windows.py`: Windows Graphics Capture and the Tk overlay.
  - `share.py`: relay client.
  - `beacon` / `odometry` / `facing` / `position` / `walkmap` / `data`.
- `overlay/shell.qml`: Linux overlay (runs `python3 -m dungeonmaps`).
- `relay/`: WebSocket relay (Docker), deployed on brettserver in `~/dungeonmaps-relay` as container
  `dungeonmaps-relay`, port 8105 (localhost only),
  reached through the Cloudflare tunnel as dungeonmaps.brettj.dev.
- `tests/`: `python tests/test_*.py`; the Lua harnesses run the real add-on under a stubbed WoW API.
  `smoke_windows.py` runs only on CI (windows-latest).

## Rules
- **Screen only.** Never read or write the WoW process (memory, injection, hooks, input).
- **Santiago Reyes's maps are never committed or shipped.** The add-on loads them from Forever
  Dungeon Routes' folder (`FDR_PATH`). `.gitignore` blocks `addon/DungeonMaps/maps/` and `*.blp`.
- **The beacon format has three twins that must change together:**
  - `beaconCells()` in DungeonMaps.lua;
  - `FIELDS` / `CELLS` / `FORMAT_VERSION` in dungeonmaps/beacon.py;
  - `encode()` in tests/test_pipeline.py (checked against the Lua by `check_encoder_matches_lua`).

  Bump FORMAT_VERSION on any change. v4 is 54 cells (v3's full 53 + the teammate dot size): adding a field means more
  cells (BEACON_CELLS in Lua, CELLS in Python).
- **The group key** is djb2 over the sorted member GUIDs joined with ",", mod 2^32. It is computed in
  `groupKey()` in Lua and `group_key()` in tests/test_beacon.py.
- **No startup services or autostart:** Brett rejected both a systemd unit and Windows start-up
  entries. Linux runs from the launcher's pre/post hooks (`linux/dungeon-maps start|stop`). The
  Windows .exe is started by hand and exits 3 s after WoW closes (10 min if WoW never opens).
- **Drawing:** you are the gold arrow (size from the add-on setting); friends are dots in their class
  colour with a black ring and their name, never arrows. Both overlays (`overlay/shell.qml`,
  `windows.py`) must match.
- **The Windows overlay must never take focus:** it is shown, hidden and moved with
  `SetWindowPos` / `ShowWindow` and no-activate flags, never Tk's deiconify.
- **Linux capture needs zink surfaceless GL:** `GST_GL_WINDOW=surfaceless`, `GST_GL_PLATFORM=egl`,
  `MESA_LOADER_DRIVER_OVERRIDE=zink`. Default EGL on radeonsi gives a bus error in gldownload.
  niri shows the picker on every start (restore tokens aren't honoured).

## Release
- Push a `vX.Y.Z` tag. CI tests, builds DungeonMaps.exe (PyInstaller), and attaches the exe, the
  add-on zip and the Linux tarball.
- Bump the version in `DungeonMaps.toc` and `dungeonmaps/__init__.py` first.

## Continuation notes (2026-11-20)
- Run Windows smoke directly as `python tests/smoke_windows.py`; it now inserts the repo root.
  Foreground assertions must start BEFORE constructing the overlay and cover notices too.
- Tk windows start withdrawn; apply no-activate styles before showing via Win32.
- Declare ctypes HWND/HANDLE signatures explicitly; default c_int can truncate 64-bit handles.
- Old Linux tracker was still running while WoW was open during continuation; left it untouched.
- Tk 8.6.14 unconditionally calls SetActiveWindow on its first wrapper, even withdrawn; overlay
  windows also use Tk's `-disabled` attribute to make native activation impossible.
- Supersedes the Tk notes above: Tk 8.6.15 still activated its withdrawn/disabled wrapper on CI.
  Windows now uses a native `WS_EX_NOACTIVATE` layered window from creation, with Pillow rendering
  and `UpdateLayeredWindow` (premultiplied BGRA). There is no Tk dependency in the shipped tracker.
- Windows lifetime checks run independently of capture retry scheduling; do not block the worker
  for 5-second retries or the required 3-second exit is delayed. The executable integration check
  enforces the exit deadline even on systems where WGC cannot capture.
- Brett's Windows UI choice (2026-11-20): start silently in the system tray, right-click → Close,
  automatic exit 3 seconds after the game closes. No startup notice or main window. Tray menu
  foreground ownership is allowed only in direct response to the user's right-click.
- Do not reintroduce QML `Behavior on rotation` / RotationAnimation: movement and turning are instant.
- Public relay route verified 2026-11-20: real Share clients exchanged positions both ways through
  `wss://dungeonmaps.brettj.dev`. Do not treat the earlier DNS-pending notes as current state.
- Windows test fixture must fit the CI desktop (1024×768): a wider Tk image crops off the beacon
  header. WGC is required in CI; artifacts include captured frames and on-screen overlay evidence.
- Latest permission preference supersedes fully silent launch: the Windows exe asks capture consent
  when manually opened, then lives in the tray. Requests actual Windows borderless permission;
  offers Screenshot borders settings if Windows denies it. No autostart and no automatic policy
  changes. This launch-time permission UI is authorized; ongoing overlay/tray must not steal focus.
- Retain WGC capture while covered. Do not replace it with visible-screen-only capture: Brett chose
  launch-time permission instead. Border removal still depends on Windows support/permission.
- WGC optional properties require OS feature gates: cursor control >=19041, border control >=20348,
  MinUpdateInterval >=26100. `None` selects library defaults; requesting unsupported properties
  rejects the entire session. Windows 10 may require a border but capture must still work.

## Latest map decision — supersedes earlier exclusion rule (2026-11-20)
- Brett explicitly requested Santiago's map images in the PUBLIC repo and release. The earlier
  "never committed/shipped" rule is superseded. All 17 originals now belong in `addon/DungeonMaps/maps/`.
- Keep `maps/CREDITS.txt` and the original images/watermarks. Art retains Santiago's copyright;
  code/data licensing is unchanged. Do not require FDR just to load these bundled pictures.
- `tests/test_maps.py` decodes every bundled BLP and checks the crop; `addon_harness.lua` opens every
  picture floor through the real add-on and checks its texture path with FDR/discovery APIs absent.
- Current release is **v1.0.1**, commit 7604d48; CI 44780176787 passed and all three release downloads
  were verified. Bundled maps are included in the public add-on zip and require no FDR installation.
- Brett's installed add-on was verified byte-for-byte against all 24 source files (17 maps), version
  1.0.1; old DungeonMapKey is absent from active AddOns. Full WoW restart and live dungeon check remain.

## Picker-loop regression and repair (2026-11-20)
- Cache PNGs must be written atomically and fully decoded under a lock. A truncated `213.png` caused
  the live tracker to crash on every move and QML to reopen the picker every 3 s. Never let damaged
  cache files terminate tracking; discard them and recapture. Diagnostic previews are optional.
- Capture permission is once per manual app launch: stream failure falls back without re-prompting,
  and QML recovery passes --screenshots. Exit 73 means another capture owner; retry with screenshots
  after 3 seconds so a departing owner cannot permanently disable a newly launched overlay.
- `linux/dungeon-maps start` serializes launches and validates the PID's executable/overlay path.
  Linux Python capture also holds an advisory owner lock. Keep those guards in both launch paths.
- `stop` takes the same launch lock and terminates the launcher's private process group, including
  the Python capture worker. Killing only qs can orphan that worker with the capture lock held.
  Verified with two real start/duplicate-start/stop cycles in Faugus's environment, plus a held
  capture lock that was released to verify automatic recovery without a permission picker.
- Current live tracker was started with DUNGEONMAPS_CAPTURE=screenshots to end the popup loop without
  another picker. Brett confirmed the arrow displays. Old pre-rename tracker was stopped by exact PID.
- Current fix release is **v1.0.2**, commit 05e1381; release CI 44783249166 green, including Windows
  executable checks and corrupt-cache/atomic-write/no-reprompt regressions. Keep bundled maps.
- Do not restart the currently working Linux capture into portal mode while Brett is playing.
  It uses screenshot fallback and was user-confirmed live. Normal game-launch hooks remain enabled;
  next normal app launch may ask once. No repeated permission dialogs on automatic recovery.

## v1.0.3 notes (2026-11-20, Claude); these supersede the WGC-only notes above
- **Capture choice (Windows):**
  - WGC only when `request_borderless()` returns True.
  - Otherwise `ScreenCapture` (DXGI duplication, windows-capture 2.0.1: 1-based EnumDisplayMonitors
    index, checked against the monitor size) reads the screen only while WoW is foreground. In that
    mode only, the overlay gets WDA_EXCLUDEFROMCAPTURE.
  - Brett wanted the yellow border gone, so "never visible-screen capture" no longer holds.
  - `DUNGEONMAPS_CAPTURE=window|screen` forces a mode.
- **Taint:** add-on code must not call `WorldMapFrame:SetMapID` or toggle the world map in combat.
  Use `toggleWorldMap()`.
- **Beacon garbage:** `beaconCells()` reuses `beaconBits` / `beaconOut`. Don't allocate tables per update.
- **Friends:**
  - The add-on skips its coarse dot for teammates whose group message has the `L` (live) flag.
  - The overlay's `_layout` handles gliding, the ring around your arrow, and label side.
- **Server logs:** `ssh -p 2222 brett@192.168.0.108 'ls ~/dungeonmaps-relay/logs/'`. One file per install
  per UTC day; each batch starts with a `===` header (time, name, version, OS, country), and a
  `stats {...}` line shows frames, ms, minimap_read, facing_read, fix, capture and relay. Read them
  when Brett reports a problem.
- **Updates:** a release's exe and add-on reach Windows users on their next exe start
  (`update.py`). Bump both version strings, or the add-on won't update.

## v1.0.4 notes (2026-11-20, Claude): tracking + map settings
- **Beacon v4** = 54 cells: v3 + `dot_size` (5 bits, tenths) after cb. Friends' dots in both overlays
  scale by it (`friend["size"]`).
- **Add-on:**
  - Shift+left-click marks "I am here". Right-click no longer does, and Shift never starts a drag.
  - The gear left of the close button opens map settings, built by `addSettingsControls`, the same
    code as the Options panel: `showOthers` (default off, which hides teammates whose group message
    never arrived, i.e. `rooms[name] == nil`), live, and `arrowSize` / `dotSize` / `bossSize`
    (0.5–2.5).
- **Atlas (`atlas.py`):** a per-floor minimap mosaic in world yards, saved in user data `atlas/<floor>.npz`.
  - **Loop closure:** the core keeps a trail of minimap pictures since the last fix. On each fix
    (entrance, marked, boss) `_on_fix` re-pastes them with the error spread linearly along the
    stretch (weight 4, or 1 for boss).
  - **Pinned by tests_atlas:** an atlas lock must NEVER reset `pf.trust` (only one that ends a search
    may). Hard pastes are keyed on `pf.walked` (yards since a real fix). Getting either wrong makes
    the atlas repaint itself with drift and then lock onto it.
  - `_peak` excludes 8 yards (PEAK_APART) around the best match; 4 px only measured the shoulder of
    the same peak.
- **Scale:** fix-to-fix calibration per `i{indoors}z{zoom}` in state `calibration.json`, prior
  CALIB_PRIOR 0.10. A real minimap recording of Ragefire (tools/replay.py) fit the art at ×1.06,
  not the ~20 % first suspected.
- `tools/replay.py <frames dir> <yd/px> [floor art.png]` stitches recorded minimap PNGs into a mosaic
  and fits it to the art's scale.
- **Logs** now carry "fix (...): the arrow was N yards off after M yards walked", landmark lines, an
  "at map x,y" line every 5 s, and atlas re-paste lines. Read them for tracking reports.
