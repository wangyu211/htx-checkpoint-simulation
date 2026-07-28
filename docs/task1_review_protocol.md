# Task 1 crossing-ledger review protocol

**Current assessment status:** the 2026-07-27 Task 1 decision is a frozen
human-adjudicated **aggregate** of 12 left-to-right and 34 right-to-left
crossings. No signed event-time ledger exists.

**Purpose:** define the additional, non-target-fit review required before this
project may claim a project-owner-signed event ledger or use observed event
times for trace replay. A tracker output that happens to contain 46 rows is
still a proposal set, not ground truth.

The machine-readable preregistration is
[`task1_event_review_protocol.json`](../config/task1_event_review_protocol.json).
It freezes the source hash, full-frame coverage, geometry, event definition,
decision rules, reconciliation gates, privacy boundary, and the explicit rule
that no expected total is used for validation.

## Stage A — freeze before review

Before entering a new event-level decision, freeze:

- source SHA-256, 748 decoded frames, and video timing;
- upper-corridor ROI `(0, 0, 1280, 310)` and count line `x=640`;
- image-direction definitions and the assessment-only mapping of
  `right_to_left` to arrivals;
- crossing-time, duplicate, occlusion, start-censor, and end-censor rules;
- candidate-source hashes and reconciliation gates; and
- reviewer/pass identifiers.

The project owner already knows the historical aggregate. This prevents
perfect cognitive blinding. The operational mitigation is to hide candidates,
tracker names, running totals, and the historical total; require complete
frame `0–747` coverage; and finish two full-video passes before revealing any
new total.

## Stage B — count-blind, all-frame enumeration

Generate local review assets from the restricted source video:

```powershell
.\.venv\Scripts\python.exe src\cv\make_visual_sweep.py `
  --video ..\TechnicalTestVideo-main\TestVidTask.mov `
  --output-dir _work\task1_signed_review_v1\pass1_blind `
  --roi 0,0,1280,310 --line-x 640 --all-frames --scale 0.75 `
  --no-pages `
  --review-video _work\task1_signed_review_v1\pass1_blind\blind_forward_0p25x.mp4 `
  --review-video-fps 7.503173133379491 `
  --write-enumeration-template
```

The generated manifest must report:

```text
requested_frame_range=0:747
sample_stride_frames=1
sample_count=748
complete_requested_frame_coverage=true
candidate_ids_visible=false
running_totals_visible=false
```

Review the complete slow video from start to finish. Record only approximate
PTS, image direction, approximate crossing height, a visual anchor, and any
boundary flag. Do not stop at a remembered number.

Perform a second isolated full-video pass. One project owner may conduct both
passes, but the final report must disclose `SINGLE_REVIEWER_DOUBLE_PASS`; it
must not describe an AI assistant as a second human reviewer.

The second representation may be all-frame sequential sheets:

```powershell
.\.venv\Scripts\python.exe src\cv\make_visual_sweep.py `
  --video ..\TechnicalTestVideo-main\TestVidTask.mov `
  --output-dir _work\task1_signed_review_v1\pass2_all_frame_sheets `
  --roi 0,0,1280,310 --line-x 640 --all-frames `
  --columns 4 --rows 2 --scale 0.5 `
  --write-enumeration-template
```

The current local package contains 94 sequential pages and covers every
decoded frame. The earlier 10 fps sweep remains useful as a recall screen but
is not accepted as an all-frame pass.

## Stage C — precise event and physical-identity review

Freeze both manual enumerations before opening candidate overlays. For every
proposed physical event, create a raw-pixel evidence packet with:

- full upper-corridor context;
- a local zoom;
- at least 0.5–1.0 seconds before and after the approximate event;
- decoded-frame PTS; and
- a raw-first view, with any algorithm overlay shown only afterward.

The event time is the first decoded-frame PTS on the destination side after a
stable movement across the line. If occlusion prevents exact-frame precision,
record `time_lower_seconds` and `time_upper_seconds` and mark the time as
interval-censored. Do not manufacture millisecond precision.

Decisions are:

- `ACCEPT`: one defensible physical crossing;
- `REJECT`: no crossing, approach only, duplicate fragment, tracker jump,
  reflection/excluded region, or a boundary-incomplete item; and
- `UNCERTAIN`: continuity remains unresolved after evidence review.

A traveller already beyond the line at frame 0 is
`LEFT_CENSORED_AT_START`, not an observed crossing. A traveller that has not
completed the crossing at frame 747 is not forced into the point estimate.

## Stage D — candidate ensemble as a recall challenge

Only after manual enumeration is frozen, reconcile it against the existing
candidate sources:

- YOLO26m + BoT-SORT;
- YOLO26m + ByteTrack;
- YOLO26m + Hungarian;
- the lower-hit/threshold sensitivity runs;
- YOLOX-S + ByteTrack;
- the classical-CV alert file; and
- the sequential false-negative challenge queue.

Candidate matching may propose a cluster only when direction agrees,
`|delta time| <= 0.50 s`, and `|delta y| <= 40 px`, using one-to-one matching
where possible. These gates do **not** decide physical identity. Track IDs are
local to one run and must never become person IDs.

Generate and review:

- manual-event by candidate-source coverage;
- manual-only events;
- algorithm-only clusters; and
- all ambiguous one-to-many or many-to-one clusters.

Every unmatched or ambiguous cluster receives an explicit human decision.
Rejected and uncertain proposals remain in the review-item history.

## Stage E — sign-off and release boundary

The public, non-pixel signed ledger is created only after all review items are
resolved. It must contain unique accepted physical crossings, source/video
identity, exact or interval-censored timing, direction, geometry, continuity
class, boundary flags, reviewer, timestamp, evidence-packet reference, and
reason code.

A detached sign-off binds the hashes of:

- this protocol/preregistration;
- review-item history;
- signed event ledger; and
- local evidence manifest.

Only after those hashes are fixed may the software reveal counts by direction.
There is no `expected_total=46` acceptance test.

- If review naturally yields `12/34/46`, publish a signed 46-person ledger.
- If it yields another value, preserve the historical aggregate and publish a
  versioned discrepancy report.
- `UNCERTAIN` events define lower/upper measurement sensitivity rather than
  being silently forced into the point estimate.

Raw video, crops, pages, and evidence packets remain under ignored `_work/`.
The public repository may contain the protocol, hashes, non-pixel ledger,
sign-off, validation report, and reproducible scripts. It must not publish
appearance descriptions, embeddings, cross-camera identities, or permanent
person IDs.

## Trace-replay interpretation

Once a signed ledger exists, accepted `right_to_left` crossings may be exported
as an observed-window arrival trace. Preserve source PTS and the
`24.922788889 s` cutoff; do not shift the first arrival to zero.

Permitted diagnostics include the empirical cumulative-arrival curve,
33 internal gaps if 34 arrival events are accepted, per-second counts,
descriptive gap/burstiness summaries, interval-timing sensitivity, and
signed-trace versus same-mean HPP mechanism comparison.

The short clip does not establish stationarity or time-of-day demand. Do not
loop it to simulate hours, treat service-seed replications as new arrival
samples, or describe HPP as empirically validated by this clip.
