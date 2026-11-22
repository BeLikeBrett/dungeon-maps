# Dungeon validation

Reviewed tracking evidence, organized by dungeon. These files document observations
and decisions; the tracker does not load them as positioning rules.

| Dungeon | Latest reviewed case | Decision |
| --- | --- | --- |
| [Ruins of Lordaeron](dungeons/ruinsoflordaeron/README.md) | 2026-11-22: bridge/drop report, one correction | Preserve tracking; bridge adjustment needs more evidence |

## Layout

```text
validation/
  dungeons/<dungeon-key>/
    README.md                 current assessment and unresolved cases
    cases/<date>-<case>.json   reviewed metrics, versions, scope and decision
```

Use the stable keys from `dungeonmaps/data/dungeons.json`. Add a dungeon directory
when its evidence has been reviewed. An absent directory means no published
assessment, rather than a claim that tracking works or fails there.

## Reviewing a case

1. Select the exact correction or run being assessed. Record its tracker build,
   beacon version, floor, minimap settings and data hash when available. Leave
   unavailable values null. Exclude superseded or incompatible recordings explicitly.
2. Distinguish player feedback, measured correction distance and replay results.
   A manual click is approximate; one corrected endpoint does not validate an entire run.
3. Compare changes with the recorded build using the same selected inputs in isolated
   caches. State the replay's sampling, initialization and coverage limits.
4. Keep dungeon-specific observations and any proposed region/layer rules under that
   dungeon. Do not infer a bridge outline or elevation from one point. A shared algorithm
   change needs evidence and regression checks from other affected dungeons.
5. Publish the decision: preserve behavior, investigate, or apply a validated change.
   Name implemented changes separately from proposals and observations.

## Private evidence

Raw recordings, minimap pictures, community payloads, installation IDs and local
paths stay outside the public dataset. Case JSON contains only reviewed summary
metrics. Private source clips are retained separately so their original data can
be replayed without putting screenshots in the repository.

The live recorder already writes new clips and timelines under
`recordings/<dungeon-key>/<date>/` in the tracker state directory. Older flat archives
remain readable. This documentation does not migrate or alter live learned maps.

## Community sample reports

Run against a **private** copy of the server's sample directory:

```sh
python tools/samples_report.py /private/samples
python tools/samples_report.py /private/samples --dungeon ruinsoflordaeron --version 1.0.11
python tools/samples_report.py /private/samples --sample-id SELECTED_SAMPLE_ID
```

Reports always separate dungeon, tracker version and map-data SHA-256. Use
`--data-sha` to select a specific data revision. Unknown versions/hashes get their
own groups. A report is an inventory of submitted corrections, not a measured
whole-run accuracy score or automatic approval to train from every submission.
