# YOLOX-S + Supervision ByteTrack recount

Status: local candidate audit; not event-level ground truth  
Run date: 2026-07-27

## Purpose

This run checks whether the licence-friendlier YOLOX-S detector plus the
MIT-licensed Supervision ByteTrack implementation can reproduce the manually
reviewed corridor count. It is a controlled cross-check, not a replacement for
manual reconciliation.

No Ultralytics detector or tracker implementation is used in this experiment.

## Frozen evidence and geometry

- video SHA-256:
  `4e2adef6a7c11ff4bac604a034229a08dfd53747360862cc53d0098f53bc7a2c`;
- YOLOX-S ONNX SHA-256:
  `c5c2d13e59ae883e6af3b45daea64af4833a4951c92d116ec270d9ddbe998063`;
- YOLOX post-tile-NMS detection-cache SHA-256:
  `9a036bd64f348e52b9f40bd1b2a2c1379f04add6a07c0fcc7c45b23fe78a7d4c`;
- 748 decoded frames over 24.922788889 seconds;
- analysis ROI `(0, 0, 1280, 310)`;
- inference tiles `(0, 0, 720, 310)` and `(560, 0, 1280, 310)`;
- detector confidence threshold `0.05`;
- count line `x=640`, 12-pixel deadband, three new-side confirmation
  frames, and 24-pixel minimum crossing displacement;
- Supervision `0.25.1`, OpenCV `4.13.0`, ONNX Runtime `1.28.0`, CPU execution.

The current crossing-state implementation resets side maturity after a missing
observation. This removes two candidates retained by an earlier run whose
maturity incorrectly accumulated across a track gap.

## ByteTrack parameter sensitivity

Every row replays the exact same hashed YOLOX detection cache.

| Activation threshold | Matching threshold | L→R raw | R→L raw | Total raw |
|---:|---:|---:|---:|---:|
| 0.05 | 0.80 | 4 | 19 | 23 |
| 0.10 | 0.80 | 4 | 18 | 22 |
| 0.05 | 0.90 | 7 | 25 | 32 |
| 0.10 | 0.90 | 7 | 25 | 32 |
| 0.15 | 0.90 | 7 | 25 | 32 |
| 0.20 | 0.80 | 6 | 19 | 25 |
| 0.20 | 0.90 | 7 | 24 | 31 |

Supervision ByteTrack uses detections between `0.10` and the activation
threshold in its second association stage. Activation `0.15` therefore
exercises the intended two-stage mechanism while retaining the same raw
candidate set as the `0.05/0.90` and `0.10/0.90` runs.

The material change between matching thresholds `0.80` and `0.90` shows that
the crowded overhead scene is association-sensitive. The raw total should not
be presented as an automatically measured truth.

## Event-level audit

The high-recall `0.15/0.90` configuration proposes:

- 7 left-to-right candidates;
- 25 right-to-left candidates.

The four-page temporal-strip review found one clear right-to-left duplicate:
the candidates at approximately `6.555 s` and `6.855 s` are the same physical
person under a track-ID handover. A separate close pair at approximately
`16.989 s` and `17.189 s` shows two different pedestrians and must not be
deduplicated.

After removing the clear duplicate, the current YOLOX-S + ByteTrack review
count is:

| Direction | Raw candidates | Clear duplicates removed | Distinct reviewed candidates |
|---|---:|---:|---:|
| Left-to-right | 7 | 0 | 7 |
| Right-to-left | 25 | 1 | 24 |
| Total | 32 | 1 | 31 |

The reviewed right-to-left candidate rate is `24 / 24.922788889 =
0.962974/s`, or approximately `57.78/min`. This is descriptive arithmetic for
the observed clip, not a long-run arrival-rate estimate.

## Cross-model alignment

Against the primary YOLO26m BoT-SORT ledger, using same-direction one-to-one
matching with `|Δtime| <= 0.50 s` and `|Δcentroid_y| <= 40 px`:

| Direction | YOLOX-S ByteTrack | YOLO26m BoT-SORT | Matched | YOLOX-only | BoT-only |
|---|---:|---:|---:|---:|---:|
| Right-to-left | 25 | 30 | 23 | 2 | 7 |
| Left-to-right | 7 | 8 | 7 | 0 | 1 |

For the 23 matched right-to-left events, mean absolute time difference is
`0.041 s` and mean vertical difference is `2.52 px`. This near frame-level
agreement supports the shared events, while the unmatched events show why the
aggregate counts differ. YOLOX-S + ByteTrack misses much of the dense
right-to-left burst around `19.2–21.2 s`.

## Decision

Use YOLOX-S + Supervision ByteTrack as the reproducible, licence-friendlier
baseline and conservative cross-check. Its reviewed `7/24` candidate set is
not a statistical lower bound and does not overturn the accepted human
aggregate of `12/34`. The gap is evidence of detector/association sensitivity on
small, occluded pedestrians and should be shown explicitly in the assessment.

The formal assessment input remains the frozen human aggregate in
`data/derived/task1_final_aggregate.csv`. If event-level detector/tracker
performance must later be established, a new signed ledger should reconcile
manual review, YOLO26m/BoT-SORT, the classical-CV audit channel, and this
YOLOX-S/ByteTrack baseline. No such ledger is claimed here.

## Reproduction

From the repository root, after installing `requirements-bytetrack.txt` in the
isolated `.venv-bytetrack` environment:

```powershell
.\.venv-bytetrack\Scripts\python.exe -m src.cv.audit_crossings `
  --video data\raw\TestVidTask.mov `
  --model models\yolox_s.onnx `
  --output-dir _work\cv_yoloxs_bytetrack_sensitivity_20260727\a015_m090 `
  --tracker bytetrack `
  --track-activation-threshold 0.15 `
  --minimum-matching-threshold 0.90 `
  --min-hits 1 `
  --detection-cache-in _work\cv_yoloxs_detections_conf005_20260727.npz
```

The candidate ledger SHA-256 for this run is
`016b61897ff9800147cfe4c30b5c738dd225fbfa14b07e1173b425346496c26d`.
