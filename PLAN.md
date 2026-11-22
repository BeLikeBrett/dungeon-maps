# Dungeon Maps: plan and status

## v1.0.17 green-map regression and native entrance arrow (2026-11-22)
- User photos show v16 instance texture green. Our old Pillow/stub tests were insufficient: palette
  BLP2 encoding1 decoded offline but failed in this client. Rebuild both existing WC filenames as
  DXT1 BLP2 encoding2, hasMips1, complete11-level chain, matching working Ruins header/layout.
  tools/blp.py + builder now generate this; test_maps checks actual compression/mip sizes/bounds.
- Atlas entrance1/2/3 = Mad Magglish (varies), Trigore the Lasher (rare), Boahn (rare), verified in
  primary Atlas ClassicEra data. Added visible left-margin map key and shortened portal label.
- Approach now has native outdoor API arrow, with UnitPosition and C_Map1413->continent-world
  fallback; only outside, Kalimdor1, finite/nonsecret. Affine fit of Atlas to client WMO109550/ADT36,33
  geometry:421 inliers, .900584px RMS; six derived coefficients in Approaches.lua. Rotation follows
  same transform. Reference: public HiddenMaps v1.2.2 static WMO facts, no code/art redistributed.
  Private ORB/RANSAC reference + player screenshots retained under research/wailing-render-20261122.
- Native arrow updates only while visible approach, per game frame; reuse texture/unchanged props.
  No tracker protocol/data/index/party/sample/instance-algorithm changes. Live external reader16 is
  compatible with native17 (same7/58). No tracker restart just for version string is needed.
- Native17 installed directly and every file byte-verified, backup under wow-addon-backups/. Existing
  filenames/Approaches.lua already known to client, so /reload retries this repair. User instructed.
  Do NOT claim live visual confirmation from tests or movement logs. Fresh game rendering pending.

## v1.0.16 Wailing Caverns approach / instance separation (2026-11-22)
- Supersedes v1.0.15 WC artwork notes below. User asked to research Turtle/free maps and fix both
  the portal approach and actual instance, autonomously. Turtle Atlas has incompatible custom
  rooms/bosses; do not import those. Unchanged Classic Atlas entrance BLP (Arith, GPL-2.0) included
  with license/credits, as native-only virtual floor -43. Not in tracker JSON/dungeon order/beacon.
- Approach selected ONLY when IsInInstance() is false and plain subzone/minimap text is Cavern of
  Mists or Wailing Caverns. Static A->B portal guide + manual marks, not automatic live tracking.
  Real instance43 always uses actual floor279. Zone transitions update binding/open map context.
- Rebuilt clean instance chart from43 installed client textures. Exclude approach chamber IDs
  8111382,8111387,8111391,8111396. Keep exact world/entry/rooms/boss positions/route data. New BLP
  plain + optional baked route guide, exact1002x668 crop; one texture, no per-frame route drawing.
  tools/build_wailing_map.py reproduces from private extracted client BLPs; inputs not committed.
- Bundled binary WC passage mask + art_revision instance-v2 supersedes stale279.png. WC-only
  atlas-to-walk expansion disabled (coverage sees walls/void). Latest three manual references old
  parchment weight .08 -> instance1.0; excluded chamber stays .08 even with atlas coverage. This is
  a path-model check, not live whole-run accuracy. Other dungeons unchanged. WC zoom/radius changes
  hold images .35s then rebase, with invalid motion learning; other maps have no hold profile.
- Public sanitized case: validation/dungeons/wailingcaverns/. Private current WC clips/run-only
  log/old art/path-mask-review under ~/.local/share/dungeon-maps/research/wailing-20261122/.
  All captured tracker1.0.11/beacon6; exclude older Ruins. Latest Ruins isolated v11/v16 sampled
  replay stays identical (maxdiff0); no Ruins heuristic or live learned-cache edit.
- Both platform packages include the new mask. Windows updater distinguishes new media and tells
  users to fully restart WoW; code-only updates still /reload. Beacon stays v7/58, decoder4..7.
- v1.0.16 release CI45034905144 passed; Windows executable/capture/overlay/updater checks passed.
  Downloaded all three assets, verified GitHub SHA-256, native/source bytes, Linux mask, EXE mask
  entry and real downloaded ZIP install in isolation. Public release notes updated.
- The queued hook did not run when Brett restarted (old Battle.net processes remained). Installed
  full native v16 directly with complete backup under ~/.local/share/wow-addon-backups/ and every
  file byte-verified. Pending ZIP renamed applied-addon-1.0.16.zip. User then restarted WoW again:
  new WoW process after install, and v16 tracker logs fresh WC movement from09:03:24 with no runtime
  errors. Native16 and tracker16 are now paired; no further restart required for this update.
- Refreshed the tracker once for this repair: log confirms v1.0.16, screenshots mode/private Qt6.12,
  no picker. Reader supports old protocol6 until native7 loads after restart. No game inputs or
  graphics changes. Do not repeat tracker restart merely for verification.

## v1.0.15 Wailing Caverns full terrain and boss names (2026-11-22)
- The original WC parchment omits the Winding Chasm. Show all47 client building-part textures on
  floor279, keeping pins/world/rooms/entry/routes and tracking math unchanged. Other floors retain art.
- All212 imported boss labels audited against client encounter export; documented creature-title
  differences preserved. Actual Lua matching covers all1634 names/aliases, including shared encounters.
- [WC assessment](validation/dungeons/wailingcaverns/README.md), complete name inventory and tests
  published together. Compatible native-only visual hotfix installed; /reload loads it. Full source
  update remains staged for Battle.net launch; no live tracker restart.

## Validation data organization (2026-11-22)
- Reviewed cases now live [under each dungeon](validation/README.md), with human-readable decisions
  and JSON metrics/provenance. Root README links to the index. Raw clips remain private.
- Latest Ruins case uses only the selected correction, excludes older builds' corrections, and
  preserves tracking. No bridge-specific positioning rule was implemented.
- Offline sample reports separate tracker builds and data revisions, with exact selection filters.
  Report regression coverage is in CI. No game/runtime/release version change for this organization.

## v1.0.14 manual defeated-boss reset (2026-11-22)
- Add "Clear defeated bosses" to map gear/Options. Clears displayed/current dungeon respectively,
  redraws immediately and preserves other dungeons/position/learning; same action as /dmaps reset.
- Native UI handlers and real beacon tests cover reset, correct wing, outside no-op, and landmark.
- Brett's active native was still v1.0.10. Backported button only, protocol6 unchanged, tested in
  isolation; /reload activates it safely with running tracker. Full source/native update stays paired
  in the Battle.net launch hook. No unsolicited tracker restart or capture picker.

## v1.0.13 automatic defeated-boss reset (2026-11-22)
- Fresh living dungeon visits clear old defeated flags across shared-instance wings. Preserve
  login/reload, duplicate notifications and corpse returns (including automatic door resurrection).
- A defeated boss being pulled again catches a missed reset; server reset messages refresh skulls.
- Existing beacon boss progress fields reset for both Linux and Windows. Learning data is retained.
- Covered all 41 maps in the Lua harness and the actual beacon round trip; updater checks pass.

## v1.0.12 run-based recovery and dungeon profiles (2026-11-22)
- Latest Lordaeron run: eight manual corrections, largest 169.2 and 93.1 yd; clean pictures at both
  large corrections. Native captures also show Questie hover popups at some impossible-match events.
  These are separate failure classes; popup blocking is not a complete explanation of the run.
- Beacon v7, still 58 cells: spare bit reports GameTooltip/shopping/map overlap over minimap.
  Decoder accepts v4/v5/v6/v7. Ignore obstructed images for odometry/facing/learning but record them.
- Boss pins never seed player poses. Spatial hints apply at most once during search for fixed
  bosses only; patrol/roam/wander guide notes exclude mobile bosses (including Witherfang/Bjork).
- Recovery runs even if odometry fails; rebase an unmatched key after >1s without inventing motion.
  Blank frames cannot reuse an old image. Whole-floor search uses coarse matching + full-detail
  verification when zoom/coverage would exceed the budget; 600px coarse span, bounded background work.
- Dungeon/indoor/zoom-specific scale profiles; legacy global values are weak priors. Profile changes
  discard mixed-setting calibration pairs. Stretches rejected for missing/inconsistent movement no
  longer re-paint atlas paths. Fresh manual current-view corrections remain valid learning anchors.
- Local evidence: 180s/128MB buffer, <=200 ZIP clips / 2GB including 1Hz background-written JSONL
  timelines. New paths <recordings>/<dungeon>/<local-date>/; per-process session IDs link clips.
  Include weak/rejected/blocked readings, UTC, profile key and acceptance flag. Prioritize manual
  clips/timelines over auto snapshots in pruning. Community remains 6 thumbnails of last 60s,
  20/install/dungeon; longer local recordings do not expand remote contributions.
- Frozen updater now attempts EXE upgrade before installing a potentially newer addon protocol;
  failed tracker upgrades defer the addon. Future launches retry. Windows/Linux share these fixes.
- Validation: all 15 local Python scripts + Lua harness passed; updated sample-window/updater
  regressions rerun. Large synthetic close-zoom test recovered within .004yd in ~131ms; NOT live
  accuracy. Matching other manual thumbnails directly failed held-out accuracy and was not shipped.
- Private evidence and review: ~/.local/share/dungeon-maps/research/run-20261122/ (six retained full
  ZIPs, old atlas/calibration/log, 17 own-install server samples, run-review.json). Never publish it.
- WoW still running while changes prepared. Native addon/tracker activation must be paired on next
  full Battle.net launch, no unsolicited live restart. Current runtime remains v1.0.11 until then.

## v1.0.11 Windows dragging and updater verification (2026-11-21)
- Windows reuses its layered bitmap when only the map origin changes, moving with SetWindowPos
  and no-activate flags. Avoids RGBA premultiplication, DIB allocation and upload on pure drags.
- Addon swap restores the installed directory if the final rename fails. EXE replacement restores
  the prior executable if launching the replacement fails. Parent-process handoff declares 64-bit
  HANDLE signatures explicitly. Update asset names and automatic startup checks remain compatible.
- Expanded updater transaction tests cover frozen replacement, SHA check, preserved CLI flags,
  parent handoff, install/swap/launch rollback. Run on Linux and Windows CI. Windows native smoke
  checks drag reuses the bitmap, reaches its target rectangle and preserves foreground focus.
- Shared tracking/context, names and compact beacon improvements already ship to Windows in the
  same EXE/addon release. Linux-specific Qt runtime changes are local only.

## v1.0.10 arrow rendering and capture cost (2026-11-21)
- Linux fixed transparent layer surface, internal map translation, cached vector gold arrow.
  No rotation easing, raster Canvas uploads or blur effects. Presentation-only prediction <=one
  capture interval / 50 ms / six map pixels; stops on stale data, corrections, floors and long gaps.
- Align the beacon horizontally above the minimap, same v6 format/58 cells. Screenshot fixture
  reduced 2489x263 -> 199x263 (12.5x fewer pixels), with map/minimap coordinates unchanged.
- Optional DUNGEONMAPS_QUICKSHELL override for a Qt-matched local runtime. No desktop-wide runtime
  replacement. Brett's old binary warns of Qt 6.11.2 vs 6.12.0; Qt-matched private rebuild installed and
  isolated launch/duplicate/stop checks passed. Local prehook selects it on next launch.
- Qt 6.12 headless renderer: 6/6 tests pass, glyph PNG inspected. Node prediction regressions,
  beacon round trip, Lua harness, pipeline, context, layout, motion guards and capture recovery pass.
  End-to-end game FPS and perceived smoothness still need real play feedback.

## v1.0.9 confidence recovery and route cost (2026-11-21)
- Separate current pose uncertainty from calibration integrity: repeated strong, movement-consistent
  atlas matches restore pose confidence without authorizing learning across missing motion.
- Fresh own arrows stay solid with a question mark for uncertainty; only stale capture fades.
  Local and global visual recovery work for uncertain poses; three matches can also confirm over
  two seconds stationary. Ignore finished boss landmarks on startup.
- Resolve shared route cells once per check. Reference comparison produced identical weights and
  near-route decisions for 5,000 hypotheses on every route floor. Same-process benchmark: 500
  particles 1.63 -> 0.83 ms; 4,000 particles 13.38 -> 5.12 ms. These are route-check costs, not game FPS.
- Delay background image copies until a search actually starts. No per-frame route drawing or searches.
- All 14 Linux test scripts passed; final pipeline/context/atlas/guard reruns and Lua harness also
  passed. Exact live rejection replay reproduced the invalid peak and guard decision. Live accuracy
  still requires gameplay feedback.

## v1.0.8 live repair (2026-11-21)
- Reject impossible minimap shifts before committing them; preserve an arrow for known uncertain
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

## v1.0.18 parchment Wailing Caverns maps (2026-11-22, Claude)
- Brett: the v16/v17 WC maps (flat two-colour mask + Atlas entrance art) looked "horrendous" and
  inaccurate; asked for professional maps. New tools/parchment.py paints client minimap-texture
  composites as Blizzard-style parchment: rock-shadow halo, inked edge, floor keeps the textures'
  own rocks/roots, muted water, slime pools, compass. numpy + Pillow only (no scipy/cv2).
- Instance: same 43 client parts, same 1002x668 frame; tracker walk mask generation untouched and
  byte-identical. Route BLP: anti-aliased, Chaikin-smoothed haloed lines, teal circuit on top of a
  dashed gold Naralex escort, chevrons every 70 px.
- Approach: painted from the private north-up WMO 109550 minimap reference warped by the existing
  registration matrix into the Atlas 512 frame at 1024x1024 (`square` display is resolution-free;
  Approaches.lua coefficients unchanged; alignment overlay vs old Atlas edges matched). A/B and
  creature 1/2/3 badges at Atlas glyph positions; red dashed A->B = Dijkstra shortest path through
  the painted floor mask (centre-favouring). It is geometry-derived, not verified in game.
- Rebuild: python tools/build_wailing_map.py --tiles /tmp/dungeonmaps-wailing-client
  --approach-ref /tmp/wc-approach-reference-private.png --approach-registration
  ~/.local/share/dungeon-maps/research/wailing-render-20261122/wc-approach-registration.json
  (inputs private, not committed; --preview DIR writes PNGs).
- All three WC BLPs are DXT1 from tools/blp.py; test_maps expects 1024 for all and a clean mip chain.
  Lua note/key text mention the red A->B dashes. Credits updated (no Atlas/HiddenMaps art remains).
- Installed live (byte-verified) while WoW ran; backup ~/.local/share/wow-addon-backups/
  dungeonmaps-before-v18-parchment-*. /reload needed. NOT yet seen in game; not committed/released.
- Brett saw it in game (no green; DXT1 confirmed working) and asked: remove the path lines, higher
  quality, less rough. Route guide removed entirely (routeFile, wailing_caverns_route.blp, gear
  option, legend note). Instance texture now 2048x2048 painted at 2x frame (same crop ratios).
  Painter smoothed: edge blur 2.4 (3.2 erased Cobrahn-room inner walls), pre-blurred relief at
  ~40%, faint grain/rim noise. Approach keeps its red A->B line (not asked to remove). Installed
  live again; backup dungeonmaps-before-v18b-smooth-*.
- Brett: smoothing taken too literally; wants 1:1 shapes ("some of it looked obviously cropped"
  = smoothing erased inlets/pillars/thin walls), but clean. Now: instance tiles composited at
  native 2x (composite(tiles, K); the 1x walk mask path untouched), paint(density=K), outline AA
  edge=1.0 map px (keeps geometry 1:1), crisp ink, relief 0.6 from 0.5K-pre-blurred luminance,
  low grain. Do not raise edge again without his ask. Backup dungeonmaps-before-v18c-native-*.
- Tracking (same v1.0.18, Claude): Brett's run corrections (20.3/13.6/14.8/46.8/17.6/4.7 yd)
  all had particle scale 0.897-0.947 vs stretch 0.949-1.019; calibration matched the stretches.
  Cause: particle scale is only selected (walls/route favour short steps) and scale_prior re-seeded
  each stretch from it (~3:1 over calibration). Now: scale_prior = calibration only;
  SCALE_REVERT_YARDS=250 per-particle log-scale reversion + matching noise, batched per walked
  yard (scale_travel); SCALE_MAX_SIGMAS=2 bound on the weighted mean. tests/test_scale_reversion.py
  (in CI). Shared change: 22 clips replayed (WC + Ruins), mean 21.4->20.1, full-stretch clip
  9.3->2.3; three clips 1.4-2.2 worse (documented). Case: validation/dungeons/wailingcaverns/cases/
  2026-11-22-scale-drift.json. Replays exclude the atlas; atlas-at-calibration-scale is a proposal.
  Replay harness + grids + clips: ~/.local/share/dungeon-maps/research/wailing-scale-20261122/
  (replay_ab.py; AB_SUBSTEP=0.1 dense updates matter: 2 Hz replays hide the selection effect).
- Optimizations (bit-identical, verified): MaskedNCC caches key-only sums per key (surface
  4.46->2.92 ms/frame); _estimate cluster distances per axis (3.46->0.22 ms @500, 9.35->1.24 @4000).
- Live tracker runs from this repo; the Python changes load at the next game launch (hook). Not
  restarted mid-play. No pending-addon.zip exists. Nothing committed/released yet.

