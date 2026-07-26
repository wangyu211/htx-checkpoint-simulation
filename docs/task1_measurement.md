# Task 1 — Day-1 Working Measurement Report

**Status:** WORKING EVIDENCE — NOT FROZEN
**Last updated:** 2026-07-26
**Decision:** No arrival-rate input is approved for the simulation yet.

This report records the first reproducible measurement pass over the supplied
video. It deliberately separates automated crossing candidates, a first-pass
event review, and the still-pending final measurement ledger. It is not a claim
that a 24.9-second clip is sufficient to calibrate an operational checkpoint.

## 1. Assignment premises and scope

The analysis adopts the two premises stated in the assessment:

1. the crowd shown in the supplied video is characteristic of the baseline
   population; and
2. the built-up area shown is analogous to an immigration-checkpoint entrance.

These are **problem premises**, not findings established from the clip. In
particular, the short video cannot establish population representativeness,
day-to-day stationarity, peak-period behaviour, or transferability to a real
checkpoint. The model will therefore be presented as a transparent comparative
what-if simulation under the stated premises, not as a validated digital twin.

The current direction labels, `left_to_right` and `right_to_left`, are image
coordinates only. Neither direction is yet labelled as the operational
“arrival” stream; that semantic mapping must be confirmed before a
direction-specific arrival process is frozen.

## 2. Source-video audit

| Field | Audited value |
|---|---:|
| File | `TestVidTask.mov` |
| SHA-256 | `4e2adef6a7c11ff4bac604a034229a08dfd53747360862cc53d0098f53bc7a2c` |
| Container video | H.264, Main profile, Level 3.1 |
| Audio | None detected |
| Resolution | 1280 × 720 px |
| Decoded frames | 748 |
| Average frame rate | 30.012692534 fps |
| Presentation duration | 24.922788889 s |
| YOLOX-S ONNX SHA-256 | `c5c2d13e59ae883e6af3b45daea64af4833a4951c92d116ec270d9ddbe998063` |

Frame rate is not used as the event clock. The video contains presentation-time
variation and B-frames, so each observation and crossing is timestamped from
the decoded presentation timestamp (`CAP_PROP_POS_MSEC`). This avoids silently
replacing actual presentation time with `frame_index / average_fps`.

The source video, decoded frames, contact sheets, and annotated review video
remain local working material and are not committed to the public repository.
Only non-pixel derived evidence is eligible for publication.

## 3. Measurement geometry

Visual inspection showed that the lower portion of the image contains glass
and strong pedestrian reflections. Running detection over the full 1280 × 720
frame would therefore permit the same physical person to be represented again
as a reflected “person.”

The current analysis geometry is:

- pedestrian corridor ROI: `(x1, y1, x2, y2) = (0, 0, 1280, 310)`;
- excluded reflection region: all pixels at `y >= 310`;
- central vertical count line: `x = 640`;
- overlapping inference tiles:
  `(0, 0, 720, 310)` and `(560, 0, 1280, 310)`;
- overlapping-tile detections are merged before tracking.

The two tiles preserve more person pixels for small or partially occluded
travellers than a single whole-frame resize. The 160-pixel overlap also avoids
making the count line coincide with an inference-tile boundary.

A narrower entrance crop was tested and rejected as the main counting geometry:
local clustering and vertical motion near the entrance made it unsuitable for
estimating total bidirectional corridor flow. The central corridor line is the
current reproducible reference geometry.

## 4. Detection, tracking, and reconciliation pipeline

### 4.1 Person detection

The detector is YOLOX-S exported to ONNX and executed with ONNX Runtime on CPU.
The implementation follows the official YOLOX preprocessing, output decoding,
and non-maximum-suppression structure. The low candidate threshold (`0.05`) is
intentional: in this high-angle, crowded scene, small and partially occluded
people often receive low scores. At this stage a missed person is more difficult
to recover than a false candidate that can be reviewed.

YOLOX is described in [Ge et al., *YOLOX: Exceeding YOLO Series in
2021*](https://arxiv.org/abs/2107.08430); the reference implementation is the
[official Megvii YOLOX repository](https://github.com/Megvii-BaseDetection/YOLOX).

### 4.2 High-recall candidate tracking

The main candidate generator uses a simple constant-velocity track state with
Hungarian assignment. A track must mature for at least four matched
observations, and may survive up to 20 missed frames. A strict crossing requires:

- confirmed observations on both sides of the count-line deadband;
- deadband half-width of 12 px;
- three confirming frames on the new side; and
- at least 24 px of net crossing displacement.

This tracker is being used as a **high-recall proposal mechanism**, not as an
unreviewed source of truth. Its permissive detection threshold retains weak
observations for event-level reconciliation, at the cost of occasional identity
switches.

### 4.3 Conservative tracker cross-check

ByteTrack was run on the same ROI, tiles, timestamps, detector threshold, and
line geometry, with track activation threshold `0.10`. ByteTrack produced 24
crossing candidates: 5 left-to-right and 19 right-to-left. The count was
unchanged at activation threshold `0.05`, while `0.10` produced fewer short
tracks, so `0.10` is retained for this cross-check.

The ByteTrack result is an empirically more conservative sensitivity result in
this clip; it is **not** asserted to be a formal lower bound or ground truth.
ByteTrack is described in [Zhang et al., *ByteTrack: Multi-Object Tracking by
Associating Every Detection Box*](https://arxiv.org/abs/2110.06864); its
reference implementation is the
[official ByteTrack repository](https://github.com/ifzhang/ByteTrack).

Using both trackers is deliberate:

- the Hungarian run exposes weak and fragmented tracks for recall-oriented
  candidate generation;
- ByteTrack provides a more selective association check;
- tracker disagreement becomes an explicit review trigger instead of an
  undocumented modelling choice; and
- final inclusion depends on event evidence, not on agreement with either
  algorithm.

### 4.4 Event reconciliation

The strict Hungarian run at `x = 640` proposed **36 candidates**:
8 left-to-right and 28 right-to-left.

An offline regression test found that candidate-side maturity could previously
accumulate across a frame gap. The state machine was changed to reset that
maturity after a gap and the complete baseline was rerun. The candidate count
and track observations were unchanged; three event confirmation timestamps
shifted by one to four frames. The public candidate ledger records the corrected
timestamps. This is why the ledger is versioned evidence rather than a number
copied out of an early run.

An **AI-assisted first-pass review** inspected highlighted, time-local event
strips for all 36 candidates. It rejected one candidate (`event_id = 7`,
`track_id = 57`) because an implausible one-frame location jump indicated an
identity-association switch. The other 35 candidates were provisionally
accepted: 8 left-to-right and 27 right-to-left.

This first pass is **not a human audit**, not owner sign-off, and not a recall
assessment. Reviewing only proposed events can detect false positives but
cannot establish that no unproposed crossing was missed. The public working
ledger is
[`candidate_crossing_event_audit_x640.csv`](../data/derived/candidate_crossing_event_audit_x640.csv).

For orientation only, the 35 provisionally accepted events correspond to:

| Direction | Provisional events | Events / video second |
|---|---:|---:|
| Left-to-right | 8 | 0.320991 |
| Right-to-left | 27 | 1.083346 |
| Total bidirectional crossings | 35 | 1.404337 |

These rates are descriptive arithmetic (`event count / 24.922788889 s`), not
approved simulation inputs or estimates of long-run checkpoint demand.

### 4.5 Low-confidence recall stress test

The detector threshold was reduced from `0.05` to `0.02`, with the same
geometry and strict crossing rule. That run proposed 48 events (14
left-to-right and 34 right-to-left), but **48 is not a defensible high-recall
count**. Lowering the detector threshold also changed trajectory construction.

A predeclared one-to-one match required the same direction,
`|Δtime| <= 0.50 s`, and `|Δcentroid_y| <= 40 px`. It matched 28 event pairs,
leaving eight main-run-only and 20 low-threshold-only events. AI-assisted
screening of the 20 low-threshold-only events classified:

- 9 as visible passages;
- 6 as ID jumps, reuse, or box-merging artefacts; and
- 5 as uncertain under crowding/occlusion.

Even a visible low-threshold passage is not automatically a unique person
missing from the main ledger: it may be a different track representation of an
already-counted crossing. This run is therefore a **recall stress and review
queue**, not a maximum-count estimator.

### 4.6 Independent sequential visual sweep

An independent AI-assisted sweep sampled 250 sequential raw-pixel views at
10.004231 fps from frame 0 through frame 747, followed by 15.006346 fps enlarged
review of suspicious intervals. All 25 sweep pages were inspected in sequence,
not only around algorithm-proposed events.

It found three high-confidence physical crossings absent from the strict
central-line ledger:

| Sweep ID | Evidence time | Direction | Fragmentation mechanism |
|---|---:|---|---|
| `FN01` | 1.854211 s | Left-to-right | Top-boundary track 18 crosses but does not satisfy full maturity |
| `FN02` | 5.1–5.3 s | Right-to-left | One physical person fragments from track 41 to 81 at the line |
| `FN03` | 22.389233–22.522578 s | Right-to-left | Trolley pusher fragments from track 128 to 200 at the line |

The non-pixel review queue is
[`candidate_false_negative_sweep_x640.csv`](../data/derived/candidate_false_negative_sweep_x640.csv).
The sweep also identified apparent candidates that should not be added:
track 177 overlaps already-counted track 170 on the same physical person;
tracks 155/162 are duplicate/nested boxes for already-represented people;
tracks 90/103 contain ID jumps; and track 2 is left-censored at the video
start.

If an owner accepts all three recovered events, the current working physical
count becomes **38**: 9 left-to-right and 29 right-to-left, or 1.524709 total
crossings per video second. Until that sign-off, **35–38 is a review bracket,
not a confidence interval and not a frozen arrival input**. The owner must
decide from raw-pixel evidence under the
[`task1_review_protocol.md`](task1_review_protocol.md).

## 5. Counting-rule sensitivity

The following are automated candidate counts before final reconciliation.
“Strict” means a 12-pixel line deadband, three confirmation frames, and
24-pixel minimum displacement.

| Count line | Rule | Left-to-right | Right-to-left | Total |
|---:|---|---:|---:|---:|
| `x = 620` | Strict | 9 | 29 | 38 |
| `x = 640` | Strict | 8 | 28 | 36 |
| `x = 660` | Strict | 8 | 27 | 35 |
| `x = 640` | Permissive: 4 px, 2 frames, 16 px | 9 | 29 | 38 |

The strict ±20-pixel line shift changes the automated total from 35 to 38.
Relaxing the confirmation rule at the central line adds two automated
candidates, but one is a likely duplicate detection of an already-counted
physical person. These differences are material relative to the short
observation window, and they show why a single detector/tracker/count-line
setting should not be presented as measurement certainty.

Counts at adjacent lines are not expected to be perfectly invariant: partial
tracks can enter at an image boundary, occlusions can fragment identities, and
some trajectories can leave the ROI before reaching every test line.
Sensitivity events therefore need event-level reconciliation rather than
mechanical averaging.

## 6. What can and cannot yet parameterise the model

| Candidate parameter | Day-1 evidence | Current disposition |
|---|---|---|
| Bidirectional crossing count | Strict candidates, low-threshold stress, and complete AI-assisted sequential sweep | Working owner-review bracket 35–38; not frozen |
| Direction-specific arrival rate | Pixel directions measured, operational “arrival” direction not yet assigned | Not frozen |
| Inter-arrival distribution | At most a 24.9-second local sample | Insufficient for a defensible long-run distribution; retain low/base/high sensitivity |
| Walking speed | Pixel displacement observable | No metres/second without a documented scale or homography |
| Personal space / density | Pixel separation observable with perspective distortion | No metric calibration; use only as qualitative scene evidence |
| Group size | Co-motion may suggest groups but is confounded by crowd flow | Do not infer groups automatically without a stated rule and review |

Accordingly, **the simulation arrival input remains `TBD`**. Freezing
either `35 / 24.92 s` or `38 / 24.92 s` as the baseline before owner review
would conflate provisional event decisions, an unresolved direction mapping,
and a very short observation window with population demand.

## 7. Limitations

- The clip is short and covers one local time window; it cannot reveal peaks,
  seasonality, shift changes, or day-to-day variability.
- The assignment premises provide analogical validity but do not establish
  statistical representativeness.
- Occlusion, top and bottom ROI truncation, small person size, and visual
  similarity create both missed-detection and identity-switch risk.
- Tracker and crossing-rule sensitivity is non-negligible.
- The sequential 10 fps sweep improves recall review but is not a formal
  frame-level ground truth or a measured recall estimate.
- No camera calibration, ground-plane homography, or known-distance reference
  is available for physical walking speed or spacing.
- Direction in image space is not yet mapped to entrance-versus-exit semantics.
- The video contains no direct evidence about Security or Immigration service
  times, staffing, additional-check probabilities, or queue discipline; those
  must be explicit assumptions or scenario variables.

## 8. Actions required before measurement freeze

1. **Completed as AI-assisted evidence:** sequential full-video sweep plus
   targeted raw-pixel review of boundaries, occlusions, and tracker
   disagreement.
2. **Completed provisionally:** recovered-event, duplicate, boundary, and
   identity-switch cases are documented; three high-confidence events remain
   in the owner review queue.
3. Obtain project-owner human sign-off on all strict candidates, the three
   recovered events, and direction.
4. Confirm which image-space direction represents immigration-checkpoint
   arrivals under the assignment’s entrance analogy.
5. Promote a versioned final event ledger only after the preceding checks;
   preserve candidate and final counts separately.
6. Derive a documented baseline and low/high measurement sensitivity for the
   simulation. Do not fit a complex arrival distribution to this clip alone.
7. If physical walking speed is required, obtain a defensible distance
   reference or state clearly that the value is literature-/assumption-based
   and use the video only for qualitative calibration.

Until those actions are complete, every numerical count in this document is
working evidence and must remain outside the frozen simulation parameter set.
