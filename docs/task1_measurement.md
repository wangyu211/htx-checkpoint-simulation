# Task 1 — Final aggregate measurement report

**Status:** FROZEN AGGREGATE — EVENT-TIME LEDGER UNAVAILABLE

**Decision date:** 2026-07-27

**Decision owner:** Wang Yu, assessment candidate and project owner

**Accepted full-video aggregate:** 12 left-to-right and 34 right-to-left
crossings over 24.922788889 seconds

**Assessment entrance mapping:** `right_to_left` is the simulated arrival
direction, giving `34 / 24.922788889 = 1.364213` travellers/second

This report preserves the reproducible computer-vision candidate work and the
subsequent full-video human aggregate adjudication. The accepted deliverable is
an **aggregate freeze**, not a signed person-by-person event-time ledger. No
event IDs or timestamps have been reconstructed after the fact.

The frozen rate is a short-window input anchor for comparative simulation under
the assignment premises. It is not evidence that a 24.9-second clip is
sufficient to estimate long-run checkpoint demand.

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

The direction labels, `left_to_right` and `right_to_left`, are image
coordinates. For this assessment, the project owner mapped `right_to_left` to
the operational entrance/arrival stream on 2026-07-27. This is an explicit
assessment decision, not a direction inferred by the detector.

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
| Local YOLO26m ONNX SHA-256 | `b5113287e92138b3740e2ad5100c5db54990310fe882e3e55f2ad4bcf07dcc73` |

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

Sections 4.1–4.6 preserve the original YOLOX-S/Hungarian/ByteTrack candidate
and recall-review history. A later controlled comparison selected
YOLO26m + BoT-SORT as the primary local candidate path and
YOLOX-S + Supervision ByteTrack as the licence-friendlier public fallback.
Neither path owns the accepted count: both inform the human adjudication, and
their disagreement is evidence of method sensitivity. The final aggregate
decision is recorded in Section 4.7.

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

At that historical stage, accepting all three recovered events would have
produced **38**: 9 left-to-right and 29 right-to-left, or 1.524709 total
crossings per video second. The resulting **35–38** range was a review bracket,
not a confidence interval. It has been superseded by the later full-video human
aggregate adjudication described below.

### 4.7 Final full-video human aggregate adjudication

After reviewing the full clip in both directions, the project owner froze the
following aggregate on 2026-07-27:

| Image direction | Accepted crossings | Observed-window rate |
|---|---:|---:|
| Left-to-right | 12 | 0.481487/s |
| Right-to-left | 34 | 1.364213/s |
| Total bidirectional | 46 | 1.845700/s |

The assessment entrance analogy maps `right_to_left` to arrivals. The
simulation therefore uses the observed-window anchor `1.364213/s`, with
separate low/base/high sensitivity rather than treating the clip as a
population demand study.

This adjudication was performed as a full-video **aggregate count**. It did not
produce a signed row for every physical crossing, so the candidate event IDs
and timestamps in the earlier ledgers must not be relabelled as the final 46
people. The authoritative non-pixel freeze product is
[`task1_final_aggregate.csv`](../data/derived/task1_final_aggregate.csv).

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

## 6. What can and cannot parameterise the model

| Candidate parameter | Evidence | Current disposition |
|---|---|---|
| Bidirectional crossing count | Full-video human aggregate adjudication | Frozen for this assessment at 12 L→R and 34 R→L; aggregate-only |
| Direction-specific arrival rate | Owner maps R→L to the entrance direction | Frozen short-window anchor at `1.364213/s` |
| Inter-arrival distribution | At most a 24.9-second local sample; no final event-time ledger | Use a transparent HPP assumption and low/base/high rate sensitivity; do not claim a fitted empirical distribution |
| Walking speed | Pixel displacement observable | No metres/second without a documented scale or homography |
| Personal space / density | Pixel separation observable with perspective distortion | No metric calibration; use only as qualitative scene evidence |
| Group size | Co-motion may suggest groups but is confounded by crowd flow | Do not infer groups automatically without a stated rule and review |

Accordingly, the simulation may use `1.364213/s` as the **accepted local-window
input anchor**. The earlier 27/29 R→L reviews and the 35–38 total review bracket
are retained as historical evidence of detector/tracker and review sensitivity;
they are not alternative statistical samples, confidence limits, or current
model inputs.

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
- The R→L entrance mapping is an assessment decision and has not been validated
  against an operational checkpoint camera specification.
- The video contains no direct evidence about Security or Immigration service
  times, staffing, additional-check probabilities, or queue discipline; those
  must be explicit assumptions or scenario variables.

## 8. Freeze decision and remaining assurance work

Completed for the assessment submission:

1. Reproducible detector/tracker candidate generation and sensitivity checks.
2. Sequential full-video visual review, including direction-specific manual
   counting.
3. Project-owner aggregate decision: 12 L→R and 34 R→L on 2026-07-27.
4. Explicit mapping of R→L to the assessment entrance stream.
5. Versioned aggregate freeze in `task1_final_aggregate.csv`.
6. Documented low/base/high demand-rate sensitivity for the simulation.

Not completed, and therefore not claimed:

1. A signed event-time ledger linking all 46 accepted people to timestamps,
   reviewer decisions, and reason codes.
2. Frame-level ground truth or measured detector/tracker accuracy.
3. Evidence that the 24.9-second observed rate is stationary or representative
   of long-run checkpoint demand.
4. Metric speed, spacing, or density calibration from a homography or known
   distance.

If a later operational study needs trace replay, empirical inter-arrival
modelling, or detector performance measurement, it must create a new signed
event ledger from raw pixels under
[`task1_review_protocol.md`](task1_review_protocol.md). That future work must
remain separate from the accepted aggregate; historical candidate ledgers must
not be overwritten or retrofitted into ground truth.
