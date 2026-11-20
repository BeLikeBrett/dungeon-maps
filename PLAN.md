# Dungeon Maps: plan and status

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
