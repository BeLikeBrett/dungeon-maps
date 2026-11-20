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
