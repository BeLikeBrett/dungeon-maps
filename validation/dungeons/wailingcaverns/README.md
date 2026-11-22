# Wailing Caverns

Dungeon key: `wailingcaverns`. Instance floor: `279`.

## Separate approach and instance maps (v1.0.16)

The old later-version parchment omits the Winding Chasm, leaving Pythas and Skum
on blank space. The [source project's notes](https://www.curseforge.com/wow/addons/forever-dungeon-routes/files/9143658)
confirm that mismatch. The v1.0.15 terrain replacement restored that wing, but its
raw mesh edges and extra approach chamber made the map hard to follow.

The current map separates the two contexts:

- **Approach cave:** unchanged Classic Atlas entrance map by Arith, from the
  [GPL-2.0 Atlas source](https://github.com/nanderson11/Atlas). A marks the cave
  entrance; B marks the instance portal. This is a native static map with optional
  manual pins. It never emits dungeon tracking data or trains floor 279.
- **Instance:** a clean navigation chart rebuilt from 43 client textures, excluding
  approach-chamber parts 8111382, 8111387, 8111391 and 8111396. It retains the exact
  world frame, boss coordinates, rooms, entrance and guide route. Optional baked
  teal arrows follow the boss circuit; gold follows the Naralex escort. Crossing
  passages may be on different levels, rather than a junction.

The [Turtle Atlas maps](https://github.com/Otari98/Atlas) were reviewed, but their
custom rooms/bosses are incompatible with Forever. No Turtle-only instance art was
imported. HiddenMaps was inspected as a reference; its restricted assets/code were
not copied. Atlas credits and its full asset license ship with the addon.

Native context selection requires an uninstanced `Cavern of Mists` / `Wailing
Caverns` zone. Entering the actual instance selects its own map regardless of room
text. The approach is not added to the 41-dungeon tracker/beacon list. New texture
filenames require a full WoW restart; the updater now tells users this. The old
instance terrain remains a safe fallback until the new pictures load.

## Tracking evidence and changes

Selected clips belong to the current Wailing Caverns run, recorded with tracker
**1.0.11**, beacon **6**. Older Ruins corrections are excluded. Old-parchment
corrections and the last three new-map manual references are distinguished; the
manual clicks are approximate observations, not universal ground truth.

At the three new-map references, the old cached parchment assigned a floor weight
of **0.08**. The new instance passage mask assigns **1.0**. The learned atlas could
previously turn texture coverage, including non-floor space, into a permitted
path. WC's bundled geometry mask now remains authoritative: atlas coverage cannot
widen it. The removed approach chamber remains at **0.08**, even if the atlas
covers it. Other dungeons keep their existing atlas/path behavior.

Recorded rejected peaks also include minimap zoom transitions. Only WC now holds
movement/learning for 0.35 seconds after a zoom/radius change, then rebases the
picture. This avoids interpreting a scaling animation as player translation and
invalidates calibration across the missing interval.

These are measured path-model checks and a zoom-transition regression, **not a
full-frequency live accuracy result**. Two-dimensional texture geometry does not
identify the player's height. The latest selected Ruins replay is unchanged
between recorded v1.0.11 and candidate v1.0.16 (maximum difference: 0 yards).

Checks exercise actual Lua portal/context switching, missing-picture fallback,
all eight unchanged boss pins, texture reuse, protocol compatibility, atlas-mask
isolation, zoom rebasing, updater transactions and Windows packaging. The clean
chart is one prebuilt texture, with no per-frame route drawing or extra capture.

Machine-readable assessment: [2026-11-22 map separation and path mask](cases/2026-11-22-map-separation.json).
Raw clips, screenshots, installation identifiers and local paths remain private.

## Boss labels

All eight labels match the installed Forever client encounter export:

1. Lady Anacondra
2. Lord Cobrahn
3. Kresh
4. Lord Pythas
5. Skum
6. Lord Serpentis
7. Verdan the Everliving
8. Mutanus the Devourer

Anacondra's position varies; Kresh patrols the river. Pins are guide locations,
not exact live creature positions. The full [212-pin name audit](../../boss-names.json)
records encounter IDs/titles and explains retained creature-name differences.
