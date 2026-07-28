# YOLO26 detector A/B experiment

Status: experimental sensitivity analysis, not a frozen Task 1 result  
Run date: 2026-07-27

## Question

Does replacing the original YOLOX-S detector with a current YOLO26 detector
improve candidate generation for the overhead checkpoint video?

This experiment isolates the detector. It keeps the following components fixed:

- source video and source SHA-256;
- upper real-floor ROI `(0, 0, 1280, 310)`;
- overlapping inference tiles `(0, 0, 720, 310)` and
  `(560, 0, 1280, 310)`;
- 640-pixel model input;
- central count line `x=640`;
- confidence threshold `0.05`;
- constant-velocity Hungarian tracker;
- 12-pixel line deadband, three confirmation frames, and 24-pixel minimum
  displacement.

The project owner froze the human full-video aggregate at L→R 12 and R→L 34 on
2026-07-27. This accepted assessment input remains aggregate-only; it is not
event-time ground truth for evaluating a detector or tracker.

## Reproducibility checks

- Official Ultralytics `v8.4.0` weights were loaded with
  `ultralytics==8.4.107` and exported as fixed-shape, end-to-end ONNX.
- The export input is `(1, 3, 640, 640)` and its output is `(1, 300, 6)`.
- The custom ONNX adapter uses centred letterboxing, BGR→RGB conversion,
  `[0, 1]` normalization, and inverse letterbox geometry.
- On the first inference tile, custom ONNX output matched official PyTorch
  output at the same `rect=False` geometry: 27 person detections and matching
  leading scores to approximately `1e-6`.
- All 39 offline project tests passed after the adapter and detector-cache
  tests were added.

## Controlled results

| Detector | ONNX SHA-256 | Size | L→R candidates | R→L candidates | Total | Approx. CPU wall time |
|---|---|---:|---:|---:|---:|---:|
| YOLOX-S | `c5c2d13e59ae883e6af3b45daea64af4833a4951c92d116ec270d9ddbe998063` | 34.20 MiB | 8 | 28 | 36 | 75 s |
| YOLO26s | `95f558d013de150e6a69416c21d9d20efa4aac8f41cc831e6d71e6eacaa0f213` | 36.47 MiB | 14 | 38 | 52 | 74 s |
| YOLO26m | `b5113287e92138b3740e2ad5100c5db54990310fe882e3e55f2ad4bcf07dcc73` | 78.12 MiB | 12 | 34 | 46 | 149 s |

Wall time includes two tiled inferences per frame, tracking, CSV output, and
annotated MP4 encoding on the same CPU-only ONNX Runtime setup. It is an
engineering measurement for this pipeline, not a general model benchmark.

Aggregate counts alone are not precision or recall. Visual review of the
YOLO26m candidate ledger found:

- stale-ID or discontinuous track jumps in E10, E11, and E26;
- likely handover duplicates in E23/E22, E25/E24, E32/E31, and E36/E35;
- plausible missed crossings that can numerically compensate for false
  candidates.

The apparent equality of `12/34` to the accepted aggregate cannot establish
event-level accuracy.

## Interpretation

YOLO26 exposes more small or occluded person evidence than the YOLOX-S
baseline, but the extra detections exceed what the current lightweight tracker
can associate reliably. The experiment has shifted the dominant failure mode
from detector recall toward track identity and event deduplication.

YOLO26m is the stronger research candidate: it produces fewer raw crossing
candidates than YOLO26s and is closer to the working directional totals.
However, it takes roughly twice as long as YOLO26s/YOLOX-S on this CPU setup.
YOLO26s has no demonstrated advantage in the current end-to-end pipeline:
similar runtime to YOLOX-S but more duplicate or fragmented crossing
candidates.

## Decision

1. Keep YOLOX-S as the reproducible, Apache-2.0 baseline.
2. Retain YOLO26m as an experimental candidate generator.
3. Keep the frozen human aggregate independent of detector/tracker selection;
   aggregate equality is not model validation.
4. If model performance must later be measured, use the completed
   Hungarian/ByteTrack/BoT-SORT sensitivity experiment in
   `docs/yolo26m_tracker_sensitivity.md` to build and reconcile a new signed
   event-time ledger.
5. Select the final detector/tracker pair using event-level precision, recall,
   ID switches, duplicate events, missed crossings, and wall time—not aggregate
   count alone.

## External evidence and licence boundary

YOLO26 is Ultralytics' current generation and uses an end-to-end NMS-free
design; the official specifications report higher COCO accuracy for YOLO26s
than the YOLOX-S reference result. This is evidence for testing, not evidence
of superiority on this overhead video:

- [YOLO26 model documentation](https://docs.ultralytics.com/models/yolo26/)
- [YOLO26 technical paper](https://arxiv.org/abs/2606.03748)
- [YOLOX reference repository](https://github.com/Megvii-BaseDetection/YOLOX)

The YOLOX source repository is Apache-2.0; the exact release-weight terms
remain a production review item. Ultralytics software and exported-model
metadata declare AGPL-3.0, with separate paid R&D and Enterprise/commercial
options. The YOLO26 files remain local and Git-ignored. Excluding them prevents
accidental redistribution but does not decide the licence scope of an
integration. Any proprietary, internal, or production incorporation needs an
explicit licence determination. This experiment is not a deployment
recommendation:

- [Ultralytics licensing](https://www.ultralytics.com/license)
- repository-level boundary: `LICENSING.md`

## Local evidence

- YOLO26s summary:
  `_work/cv_yolo26s_hungarian_x640_20260727/run_summary.json`
- YOLO26m summary:
  `_work/cv_yolo26m_hungarian_x640_20260727/run_summary.json`
- YOLO26m review pages:
  `_work/cv_yolo26m_hungarian_x640_20260727/owner_review/pages/`
- YOLO26m enlarged suspicious events:
  `_work/cv_yolo26m_hungarian_x640_20260727/owner_review_zoom/`
