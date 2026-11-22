# Wailing Caverns

Dungeon key: `wailingcaverns`. Floor: `279`.

## Missing eastern wing

The player reported boss pins 4 and 5 appearing on blank parchment outside the
drawn passages. They represent **Lord Pythas** and **Skum** in the Winding Chasm.
The later-version parchment used by the addon omits that wing. The source map
project documents this mismatch in its [0.5.19 notes](https://www.curseforge.com/wow/addons/forever-dungeon-routes/files/9143658).

The fix uses the client's complete minimap terrain for **this floor only**:
47 building-part textures with the source's exact placement, orientation and
layer order. Boss positions, world frame, entrance, rooms, route data and tracking
math stay unchanged. The tracker JSON is byte-identical to the previous release.
Textures are configured when opening/changing floors and reused on reopening.

Checks cover all eight pin locations within the exported terrain bounds, actual
Lua texture setup, unchanged marker positions, texture reuse and hiding the terrain
when another floor opens. Bounds coverage is not a claim of independently verified
live creature spawn coordinates. A new in-game screenshot is still needed to
confirm that this client loads every terrain texture as expected.

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
