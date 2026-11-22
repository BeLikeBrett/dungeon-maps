# Ruins of Lordaeron

Dungeon key: `ruinsoflordaeron`. Floor: `1029991`.

## Current assessment

The player reported nearly perfect tracking on the latest run, with one manual
correction. The arrow sometimes showed a question mark while still appearing
accurate. A remaining concern involved travelling over a grey castle bridge and
jumping down as a shortcut.

Only the latest correction and its attached clip were selected for this review.
Earlier corrections from hours before are excluded at the player's request.
The clip itself records tracker **1.0.11** and beacon **6**; those recorded versions
take precedence over the latest release number.

| Measurement | Result |
| --- | --- |
| Recorded correction | 21.18 yards |
| Clip coverage | 106 minimap frames over 52.60 seconds |
| Mean / minimum minimap match score | 0.942 / 0.840 |
| Sampled replay endpoint error, v1.0.11 | 22.005 yards |
| Sampled replay endpoint error, v1.0.14 | 22.005 yards |
| Maximum position difference between those replays | 0 yards |

The replay used sampled crops, an approximate seeded starting distribution, and no
live atlas or calibration files. Its results describe this clip comparison only.
The recorded 21.18-yard correction and the replay's 22.005-yard error are different
measurements; neither establishes accuracy along the entire run.

## Decision

**Preserve the tracking algorithm and current learned maps.** No bridge-specific
rule was implemented. The pictures do not establish the character's height or
exact bridge-jump timing, so this case cannot define a reliable elevated region
or bridge-to-ground transition.

Future bridge work should use verified before/after examples on this dungeon and
check that ordinary ground travel, backtracking and shortcuts still work. These
observations do not justify a new positioning rule for other dungeons.

Machine-readable record: [2026-11-22 bridge/drop case](cases/2026-11-22-bridge-drop.json).
Raw evidence remains private.
