# Dungeon Maps: plan and status

## v1.0.8 live repair (2026-11-21)
- Reject impossible minimap shifts before committing them; preserve a dim arrow for known uncertain
  poses, stop boss pins from teleporting ranged players, bound scale learning and ignore stale cached
  startup marks. Restored Brett's pre-glitch local calibration/atlas and preserved all faulty evidence.
- Exact rejected image-match snapshots are locally replayable; sampled recordings alone missed the
  transient failure. All movement/atlas and new regression tests pass locally.

## v1.0.6 (2026-11-21)
- Manual fixes replace conflicting learned pixels; entrances remain approximate. Castle staircase
  trace retained privately for further comparisons; height-related drift remains unconfirmed.
- Compact correction contributions from each installation: 20 recent samples per dungeon, six
  minimap thumbnails each, private server storage with a 2 GB global cap. Native opt-out/notice,
  retry outbox and acknowledgement; v6 beacon keeps backward decoding for v4/v5.
- Public relay deployment and real castle upload verified. Private report CLI installed on server.

## v1.0.5 (2026-11-21)
- Hidden route context from all 122 imported guide traces; cached floor connections, no route lines
  or forced boss order. Soft weights every 3 yards, permissive when most guesses leave the guide.
- Ongoing room context, named-floor transitions, and short-lived broad active-boss hints. Beacon v5
  sends active boss and kill mask; tracker remains compatible with the installed v4 addon.
- Atlas recent-write safeguards apply to local and global matching, including corrected pixels and
  interpolation boundaries. Relocations require three matches across five yards; stale async
  results are discarded. Independent uncertainty is distinct from particle agreement. Boss spawn
  pins do not train scale or repaint the learned atlas as ground truth.
- Audited 212 existing boss pins against imported client encounter IDs. Corrected five known
  creature names, retained encounter/localized aliases, and fixed shared-ID name matching. Single
  boss encounters learn native boss-unit names per locale; multi-boss pins keep individual labels.
- Regression coverage: tests/test_context.py plus real Lua addon/beacon harnesses and existing suite.
- Local diagnostic recorder and isolated sampled-minimap replay added at Brett's request; up to
  60 s / 30 MB RAM and 10 archives / 100 MB retained. Shift+click corrections capture evidence;
  pictures stay local. All Linux tests, full pipeline/atlas tests, context and recorder tests pass.

## Done in v1.0.4 (2026-11-20)
- **Shift+click** the map where you stand to place your arrow; the map says so.
- **Gear on the map** (top right): show teammates without Dungeon Maps (off by default), live
  tracker, and sizes for your arrow, teammate dots and boss icons. `/dmaps dots|bosses <size>`,
  `/dmaps others`. Beacon v4 carries the dot size to the overlay.
- **Minimap atlas:** the tracker learns each floor's minimap picture, matches the live minimap
  against it, and holds the arrow on the map. Fixes (entrance, boss, your click) correct the stretch
  before them, so the next run of a dungeon is better. A tracker started mid-dungeon finds you from
  the atlas. Tests: drift of 12 yards → ~2.5 yards.
- **Scale calibration** from fix to fix; logs say how far off the arrow was at every fix.

## Done (2026-11-20)
- **Add-on renamed** from Dungeon Map Key to Dungeon Maps; `/dmaps` (and `/dmk`).
- **Beacon v3:** 53 cells, carrying the group key, the character name, your arrow size and your
  class colour.
- **Friends are class-coloured dots** (like the add-on's group dots), with their name; only you get
  the direction arrow.
- **Settings panel** (Esc → Options → AddOns → Dungeon Maps): your arrow size (0.5–2.5×) and live
  mode. `/dmaps size 1.5` does the same.
- **Icon** for the add-on list and the exe (`tools/make_icon.py`).
- **Picture maps** load from Forever Dungeon Routes' folder.
- **Tracker split** into a shared core and Linux/Windows runners.
- **Sharing:** relay client plus relay server. Friends are drawn with name and colour, only on the
  floor being shown.
- **Linux overlay** draws you and your friends; the compositor helpers cover niri, Hyprland and Sway.
- **Windows runner:**
  - Windows Graphics Capture by HWND (windows-capture 2.0.1);
  - click-through, never-activating Tk overlay;
  - single instance;
  - exits 3 s after WoW closes (10 min if WoW never opens).
- **CI:** tests on Linux, a Windows overlay smoke test, and the exe built with PyInstaller. A tag
  makes a release.

## Waiting on
- **Brett adds the Cloudflare route** `dungeonmaps.brettj.dev` → `http://localhost:8105` on
  brettserver. The relay container (`~/dungeonmaps-relay`, `docker compose up -d --build`) is
  running and was tested through an SSH tunnel on 2026-11-20.
- **Real Windows test** by a friend: capture, overlay placement, DPI scaling, and the Win10 border.
- **First live test of sharing** with two people in one group.

## Ideas
- Linux: an option to skip the portal picker (screenshot mode only).
- Show friends on other floors as a count or an edge marker.

## Continuation (2026-11-20)
- CI 44770396045: Windows smoke failed before exercising the overlay because the test did not put
  the repository on `sys.path`. Fixed the import; strengthened checks to cover overlay construction
  and the startup notice, and made their first native show non-activating. Win32 handles now have
  explicit ctypes signatures for 64-bit Python.
- Public relay check: `dungeonmaps.brettj.dev` does not resolve yet; live sharing remains pending.
- Windows availability: libvirt system daemon unavailable, session has no guests. Historical
  `/satassd/winiso` images are gone; `/satassd/haloos-vm/haloos-win-disk.qcow2` exists and is being
  investigated using a disposable overlay. SanDisk native Windows remains a reboot option.
- Duplicate coarse/exact friend dots: asked Brett to choose hiding, dimming, or keeping coarse dots;
  no behavior change until he chooses.
- Correction after booting the disposable guest: the misleading `haloos-win-disk.qcow2` now boots
  HaloOS (confirmed on tty2), not Windows. Stopped the guest. No usable local Windows guest found;
  native Windows on sdb3 requires Brett to reboot. Added Windows-runner integration checks with a
  synthetic game window and the built exe; these report unsupported capture separately.
- Native Windows overlay passes the no-focus smoke test. Built-exe checks on Windows build 26100,
  96 DPI verified single instance and synthetic beacon placement (2/3-pixel cells). Initial WGC on
  the borderless fake window was unavailable; retrying with a normal decorated test window.
- Found and fixed a shutdown timing bug: capture retry sleeps could postpone exit to 7.39 seconds.
  Window lifetime is now checked independently every 0.1 seconds, including during capture retries.
- Brett has not restarted WoW yet and asked to continue release work. He confirmed the intended
  display: own arrow, everyone else dots. Explained the possible duplicate room-estimate/exact dot;
  no coarse-dot behavior change selected. Check duplication during the live test.
- Brett requested silent tray startup for the Windows exe, with right-click → Close; automatic
  exit after WoW closes stays. Implemented a native notification-area icon and Close menu, removed
  the startup notice, bundled the icon, and added source/exe tray lifecycle checks.
- Removed a leftover 25 ms Linux rotation animation: turning now applies instantly as required.
- Capture investigation: WGC delivered 152 real frames on CI. The 1100-pixel fake game exceeded
  the 1024-pixel CI desktop, so Tk cropped off the beacon header. Reduced the fixture to 900×650
  and require WGC capture/decode in CI (removed the permissive CI flag).
- Required WGC capture/decode now passes on real Windows CI (build 26100, 96 DPI); the packaged exe
  also passes silent tray startup, Close, single instance, and automatic exit (3.41 seconds).
  Added a final captured-canvas alignment check against Win32 ClientToScreen, including decorations.
- Public relay route is now live: two real Share clients exchanged positions both ways through
  `wss://dungeonmaps.brettj.dev` in an isolated test group. A two-person in-game test remains pending.
- Brett clarified launch-time permission: no OS autostart on either platform; when manually opening
  the exe, ask permission to read WoW and keep window capture working while covered. Kept WGC
  (discarded the uncommitted visible-screen experiment). Added per-launch capture consent, the real
  Windows borderless-access request, and an optional link to Screenshot borders settings if denied.
  Tests exercise consent rejection/acceptance and ensure a second instance doesn't ask again.
- Compatibility review found unconditional WGC options would reject capture on Windows 10 / older
  Windows 11. Gate cursor control at build 19041, border control at 20348, and minimum update interval
  at 26100; older builds keep the callback FPS limiter and use supported defaults.
- Tracking continues through covered-window WGC frames; the overlay itself now hides whenever WoW
  isn't foreground or is minimized, so it never paints arrows over another app. Added a real Windows
  covering-window test that checks capture continues while the overlay is hidden.

## Bundled-map release update (2026-11-20)
- v1.0.0 published successfully (CI 44778185183); all three assets downloaded, hashes and layouts
  verified. It was immediately superseded by Brett's explicit request below.
- **Brett superseded the earlier map-exclusion rule:** include Santiago's images in the public repo
  and release. Copied all 17 original BLPs, byte-identical to the installed FDR copies, with credits.
  The add-on loads its own `DungeonMaps/maps/` files directly; FDR and discovery APIs aren't required.
- Preparing v1.0.1: all 17 BLPs decode, crop correctly, and the Lua harness opens every corresponding
  floor and verifies the exact bundled texture path without Forever Dungeon Routes installed.

## v1.0.1 ready to share (2026-11-20)
- Published https://github.com/BeLikeBrett/dungeon-maps/releases/tag/v1.0.1 (release CI 44780176787
  green). All three downloaded assets match GitHub's SHA-256 digests and expected versions/layouts.
  The add-on zip contains all 17 original map images plus credits; standalone paths verified.
- Brett's installed `_forever_/Interface/AddOns/DungeonMaps` is v1.0.1: all 24 files match the release
  source byte-for-byte, including every map. DungeonMapKey is absent from the active AddOns folder.
  A full WoW restart is still required; current game/old tracker were left untouched.
- Windows: verified real CI capture/decode/physical placement, tracking while covered with overlay
  hidden over other apps, consent rejection/acceptance, tray Close during capture, single instance,
  and ~3.4-second automatic exit. No usable local Windows VM; actual WoW, other Windows DPI settings,
  Win10 border behavior, and granted borderless permission still need a live check.
- Relay public two-client exchange verified; two-person in-game sharing and Linux live checks after
  restart remain pending. No hide/dim change to coarse group dots was selected.

## Live Linux repair (2026-11-20)
- Brett restarted WoW and confirmed the live arrow now displays after repair.
- Root cause: an interrupted/non-atomic PNG cache write left `floors/213.png` truncated. Loading it
  crashed the tracker; QML restarted it every 3 s, reopening the portal picker each time. An old
  pre-rename tracker was also still running. Stopped the old/new looping copies by verified exact
  PIDs, preserved the bad PNG, and started one screenshot-mode tracker; cache rebuilt successfully.
- Permanent fix: atomic PNG writes, serialized cache readers/writers, damaged-cache discard/recapture,
  and nonfatal cache/preview errors. Linux stream failure falls back without reopening the picker;
  QML crash recovery uses screenshot mode. Retain portal connection/session and close resources.
- Launches serialized and PID-validated; a capture-owner lock prevents duplicate workers. Repeated
  `start` calls preserved the live PID; a duplicate worker exited 73 before asking permission.
- Current live repair runs with screenshot capture, stable and user-confirmed. Next manual launch
  may ask once for portal capture; failures won't ask again. No OS startup entries added.
- Preparing v1.0.2 with the shared cache fix for Windows too; Windows uses no Linux portal/picker.

## v1.0.2 verified (2026-11-20)
- Release CI 44783249166 passed Linux tests, the new cache/portal regression, and the rebuilt Windows
  executable integration test. Published v1.0.2 with all three assets and all 17 bundled maps.
- Local full tracking pipeline passes. Duplicate `start` calls kept the same live overlay/worker;
  duplicate direct capture exited 73 without a picker. Live worker stayed stable beyond eight minutes,
  and Brett confirmed the arrow is showing. Current run is deliberately in screenshot fallback mode.
- Existing Faugus pre/post hooks remain the launch mechanism. Normal next launch can request portal
  selection once; failure/recovery never requests it again automatically. No OS autostart was added.
- Windows capture, permission, overlay, tray Close, single instance and shutdown tests pass again.
  The Linux portal UI loop has no Windows equivalent; the shared map-cache fix protects both.

## v1.0.3: Brett's fix list (2026-11-20, Claude)
- **Duplicate friend dots:** the add-on drew a coarse dot (room, landmark or "~28 yards") as well as
  the overlay's exact one, so a friend could show twice (one at the entrance). Group messages now
  carry an `L` flag when live mode is on; the add-on draws no coarse dot for live teammates
  (legend: "live on the tracker").
- **Overlap with your arrow:** `core._layout` glides friends between relay updates (snapping on
  jumps over 30 map px), pushes friends standing on you onto a ring around your arrow, and puts
  their name tag on the side away from you. Both overlays draw a white-rimmed dot plus a dark
  name pill.
- **Yellow border (Windows):** WGC is used only when Windows grants borderless capture. Otherwise
  `ScreenCapture` (DXGI desktop duplication) crops WoW out of its monitor while WoW is foreground.
  The overlay is excluded from capture in that mode only (WDA_EXCLUDEFROMCAPTURE). After 3 failed
  starts it falls back to WGC. The "open Screenshot borders settings" dialog was removed.
- **Auto-update (Windows exe):** `dungeonmaps/update.py` checks the latest GitHub release on every
  start.
  - A newer exe is downloaded, SHA-256-checked against GitHub's digest, swapped in via a
    rename to `.old`, and relaunched with `--updated-from=<pid>`.
  - The add-on in `_forever_/Interface/AddOns` (found from the remembered Wow.exe path, Program
    Files, or the registry) is replaced all-or-nothing. A tray balloon says /reload.
  - `DUNGEONMAPS_UPDATE=off` turns it off.
- **Taint ("Interface actions failed because of this AddOn: 34"):**
  - Add-on code no longer calls `WorldMapFrame:SetMapID`.
  - It never toggles the world map in combat.
  - The map key is only overridden in dungeons that have a map.
  - Waiting on Brett: if the count still climbs, `/console taintLog 1`, reproduce, then read
    `_forever_/Logs/taint.log`.
- **Memory (44 MB):** the beacon redraws ~33×/s and made ~11 KB of garbage each time. It now
  reuses its tables (~2 KB, most of that from the test harness's stubs).
- **Logs on the server:** `dungeonmaps/telemetry.py` sends log lines, crashes and a per-minute
  stats line (`Core.stats()`) to the relay. They are stored in brettserver
  `~/dungeonmaps-relay/logs/<UTC day>/<install id>.log`.
  - Caps: 4 MB per install per day, 1 GB in total, 30 days.
  - `DUNGEONMAPS_LOGS=off` turns it off.
  - The relay was redeployed and tested through the public route; position sharing was re-verified.
