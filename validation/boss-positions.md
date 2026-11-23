# Boss pin positions: independent check (2026-11-23)

Every pin comes from Forever Dungeon Routes 1.3.6. This compares each pin with the spawn
point of the same creature in an independent server dataset, the CMaNGOS classic world
database (`Full_DB/ClassicDB_1_12_1_z2815.sql.gz`, original 1.12 spawns in world yards).
Each pin was converted to world yards with its floor's `world` bounds. The orientation was
checked: the correct one gives a 19-yard median, and every other orientation gives about 200.

**This is a flag list, not ground truth.** WoW: Forever is not 1.12. Brett's runs report
Ragefire as correct, yet Oggleflint's pin is 166 yards from the CMaNGOS spawn; the
Ragefire map art even draws a skull near the CMaNGOS spot. Where the two sources disagree,
the pin was left alone. Pins are display plus one soft search hint only (boss pins never set
the player position, and the hint ignores anything more than 60 yards from every guess), so a
wrong pin cannot pull the arrow far.

Not compared: the new Forever dungeons (not in a 1.12 database), creatures CMaNGOS spawns by
script (Gahz'rilla, Avatar of Hakkar, Ring of Law, The Seven, ...), and combined labels.

## Per dungeon (yards from the nearest CMaNGOS spawn)

| Dungeon | Matched | Median | Worst |
| --- | --- | --- | --- |
| Ragefire Chasm | 4/4 | 10 | 166 |
| Deadmines | 8/8 | 7 | 24 |
| Wailing Caverns | 7/9 | 10 | 72 |
| Shadowfang Keep | 9/9 | 11 | 19 |
| Blackfathom Deeps | 7/8 | 22 | 56 |
| Stormwind Stockade | 6/6 | 6 | 26 |
| Razorfen Kraul | 9/9 | 15 | 36 |
| Gnomeregan | 5/6 | 10 | 69 |
| Scarlet Monastery: Graveyard | 2/5 | 14 | 23 |
| Scarlet Monastery: Library | 2/2 | 5 | 9 |
| Scarlet Monastery: Armory | 1/1 | 0 | 0 |
| Razorfen Downs | 4/6 | 9 | 107 |
| Scarlet Monastery: Cathedral | 3/3 | 4 | 7 |
| Uldaman | 6/8 | 11 | 25 |
| Zul'Farrak | 9/12 | 30 | 65 |
| Maraudon | 9/9 | 11 | 158 |
| Sunken Temple | 4/8 | 29 | 40 |
| Blackrock Depths | 18/22 | 21 | 131 |
| Dire Maul: East | 6/6 | 12 | 534 |
| Lower Blackrock Spire | 13/15 | 26 | 93 |
| Upper Blackrock Spire | 5/8 | 34 | 61 |
| Dire Maul: West | 6/7 | 13 | 24 |
| Dire Maul: North | 8/8 | 18 | 44 |
| Scholomance | 11/14 | 27 | 35 |
| Stratholme | 12/19 | 12 | 412 |
| Molten Core | 8/10 | 31 | 213 |
| Onyxia's Lair | 1/1 | 5 | 5 |
| Blackwing Lair | 7/8 | 41 | 124 |
| Zul'Gurub | 7/10 | 95 | 171 |
| Ruins of Ahn'Qiraj | 6/6 | 56 | 119 |
| Ahn'Qiraj Temple | 6/9 | 22 | 61 |
| Naxxramas | 13/15 | 19 | 43 |

Medians of 5 to 30 yards are normal: a pin marks the boss's room, not its exact spawn.
Zul'Gurub and Ruins of Ahn'Qiraj are off by a similar amount for every boss, which looks like
a different map frame rather than wrong pins; they were not investigated further.

## Over 40 yards

"Patrols" and "wanders" are CMaNGOS movement types: for those, the spawn is only where the
walk starts, so a large distance is expected (Kresh swims the river; Pusillin runs ahead of
the group; Rotgrip swims under the bridge).

| Dungeon | Pin | Kind | Yards | CMaNGOS movement |
| --- | --- | --- | --- | --- |
| Ragefire Chasm | Oggleflint | boss | 166 | wanders |
| Wailing Caverns | Kresh | boss | 72 | patrols (waypoints) |
| Blackfathom Deeps | Lorgus Jett | boss | 56 | stationary |
| Gnomeregan | Viscous Fallout | boss | 69 | patrols (waypoints) |
| Gnomeregan | Dark Iron Ambassador | rare | 52 | patrols (waypoints) |
| Razorfen Downs | Glutton | boss | 107 | patrols (waypoints) |
| Zul'Farrak | Zerillis | rare | 51 | patrols (waypoints) |
| Zul'Farrak | Antu'sul | boss | 65 | stationary |
| Maraudon | Meshlok the Harvester | rare | 158 | patrols (waypoints) |
| Maraudon | Tinkerer Gizlock | boss | 92 | stationary |
| Maraudon | Rotgrip | boss | 139 | patrols (waypoints) |
| Sunken Temple | Jammal'an the Prophet | boss | 40 | stationary |
| Blackrock Depths | Fineous Darkvire | boss | 43 | patrols (waypoints) |
| Blackrock Depths | Houndmaster Grebmar | boss | 57 | stationary |
| Blackrock Depths | Lord Roccor | boss | 131 | patrols (waypoints) |
| Blackrock Depths | Plugger Spazzring | boss | 58 | patrols (waypoints) |
| Blackrock Depths | Panzor the Invincible | rare | 47 | patrols (waypoints) |
| Dire Maul: East | Pusillin | boss | 534 | patrols (waypoints) |
| Lower Blackrock Spire | Spirestone Butcher | rare | 43 | patrols (waypoints) |
| Lower Blackrock Spire | Bijou | optional | 63 | stationary |
| Lower Blackrock Spire | Crystal Fang | rare | 93 | wanders |
| Lower Blackrock Spire | Ghok Bashguud | rare | 48 | wanders |
| Upper Blackrock Spire | Jed Runewatcher | rare | 61 | patrols (waypoints) |
| Dire Maul: North | Cho'Rush the Observer | boss | 44 | stationary |
| Stratholme | Magistrate Barthilas | boss | 412 | stationary |
| Molten Core | Magmadar | boss | 43 | stationary |
| Molten Core | Garr | boss | 52 | wanders |
| Molten Core | Baron Geddon | boss | 213 | patrols (waypoints) |
| Blackwing Lair | Razorgore the Untamed | boss | 41 | stationary |
| Blackwing Lair | Firemaw | boss | 124 | patrols (waypoints) |
| Blackwing Lair | Ebonroc | boss | 74 | patrols (waypoints) |
| Blackwing Lair | Flamegor | boss | 53 | wanders |
| Zul'Gurub | High Priestess Jeklik | boss | 117 | stationary |
| Zul'Gurub | High Priest Venoxis | boss | 75 | patrols (waypoints) |
| Zul'Gurub | High Priestess Mar'li | boss | 85 | stationary |
| Zul'Gurub | Bloodlord Mandokir | optional | 171 | stationary |
| Zul'Gurub | High Priest Thekal | boss | 95 | stationary |
| Zul'Gurub | Jin'do the Hexxer | optional | 99 | stationary |
| Ruins of Ahn'Qiraj | General Rajaxx | boss | 81 | stationary |
| Ruins of Ahn'Qiraj | Moam | optional | 51 | stationary |
| Ruins of Ahn'Qiraj | Buru the Gorger | optional | 60 | wanders |
| Ruins of Ahn'Qiraj | Ayamiss the Hunter | optional | 42 | stationary |
| Ruins of Ahn'Qiraj | Ossirian the Unscarred | boss | 119 | stationary |
| Ahn'Qiraj Temple | The Prophet Skeram | boss | 48 | stationary |
| Ahn'Qiraj Temple | Princess Huhuran | boss | 61 | patrols (waypoints) |
| Naxxramas | Anub'Rekhan | boss | 43 | stationary |

## To confirm in game

Stationary five-player bosses with the largest disagreement. If a pin is visibly in the
wrong room, a Shift+click correction and a note are enough to fix it:

- Blackfathom Deeps: Lorgus Jett (56 yd)
- Zul'Farrak: Antu'sul (65 yd)
- Maraudon: Tinkerer Gizlock (92 yd)
- Sunken Temple: Jammal'an the Prophet (40 yd)
- Blackrock Depths: Houndmaster Grebmar (57 yd)
- Dire Maul North: Cho'Rush the Observer (44 yd)
- Stratholme: Magistrate Barthilas (412 yd)
- Lower Blackrock Spire: Bijou (63 yd; the source already notes "Position varies")
