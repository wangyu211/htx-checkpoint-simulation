# YOLO26m tracker sensitivity experiment

Status: event-level audit in progress; counts are candidate counts, not ground
truth  
Run date: 2026-07-27

## Question

How much does the association method change the crossing ledger when the
detector evidence is held exactly constant?

There are more than three tracking algorithms in the literature. This
experiment deliberately compares three complementary choices:

1. a transparent constant-velocity Hungarian baseline;
2. Ultralytics ByteTrack as a conservative score-aware tracker;
3. Ultralytics BoT-SORT as the stronger association candidate.

The project owner froze the human full-video aggregate at `L→R = 12` and
`R→L = 34` on 2026-07-27. It is the accepted aggregate assessment input and a
useful cross-check, but it is not event-time ground truth.

## Controlled detector evidence

YOLO26m inference was run once. Every tracker then replayed the same
post-tile-translation, post-cross-tile-NMS float32 detections:

- source video SHA-256:
  `4e2adef6a7c11ff4bac604a034229a08dfd53747360862cc53d0098f53bc7a2c`;
- YOLO26m ONNX SHA-256:
  `b5113287e92138b3740e2ad5100c5db54990310fe882e3e55f2ad4bcf07dcc73`;
- detection-cache SHA-256:
  `913c35e32ee900a1863282d2b1664b03dfdc89174de7c1b8c4045238e2197f67`;
- 748 frames and 27,055 merged person detections;
- ROI `(0, 0, 1280, 310)`;
- inference tiles `(0, 0, 720, 310)` and `(560, 0, 1280, 310)`;
- cross-tile NMS IoU `0.50`;
- count line `x=640`, 12-pixel deadband, three side-confirmation frames,
  and 24-pixel minimum crossing displacement.

BoT-SORT used `gmc_method=none` because the camera is fixed and
`with_reid=false` because no appearance model was introduced. ByteTrack and
BoT-SORT came from `ultralytics==8.4.107`.

## Candidate-count results

The first comparison used the same externally configured `min_hits=4` value:

| Tracker | L→R | R→L | Total |
|---|---:|---:|---:|
| Hungarian | 12 | 34 | 46 |
| ByteTrack | 9 | 27 | 36 |
| BoT-SORT | 8 | 30 | 38 |

This knob is not semantically identical across implementations. Ultralytics
internally withholds a newly born track before the adapter observes it, so an
external four-output threshold can require one more detector match than the
Hungarian baseline. A sensitivity run removed that extra output threshold:

| Tracker | External `min_hits` | L→R | R→L | Total |
|---|---:|---:|---:|---:|
| Hungarian | 1 | 12 | 35 | 47 |
| ByteTrack | 1 | 9 | 29 | 38 |
| BoT-SORT | 1 | 9 | 30 | 39 |

The conclusion is unchanged: Hungarian is recall-oriented but unstable,
ByteTrack is the most conservative, and BoT-SORT lies between them. The
aggregate count alone cannot identify the most accurate tracker.

## Reproducibility

Each `min_hits=4` tracker run was repeated from the same detection cache. For
all three trackers, both `crossing_ledger.csv` and
`track_observations.csv` were byte-identical to the first replay.

The implementation was also checked against the installed Ultralytics API:
`Boxes` receives `[x1, y1, x2, y2, confidence, class_id]`, and tracker output
is read as `[x1, y1, x2, y2, track_id, score, class_id, detection_index]`.
All 39 offline project tests pass.

## Event-level disagreement audit

The decisive evidence is what happened at disagreements, not which aggregate
number happens to equal the manual total.

Among 11 Hungarian-only candidates:

| Classification | L→R | R→L | Examples |
|---|---:|---:|---|
| True physical crossing | 1 | 4 | E2, E17, E18, E35, E40 |
| False association/crossing | 3 | 2 | E10, E11, E14, E26, E32 |
| Ambiguous handover/duplicate | 0 | 1 | E24 |

The false candidates include stale side-state, direction reversal, and
identity reassignment across the count line. Separately, all four physical
events found by ByteTrack/BoT-SORT but missed by Hungarian were visually true:

- one `L→R` event at about 7.955 seconds;
- two `R→L` events at about 9.755 and 10.222 seconds;
- one BoT-SORT-only `R→L` event at about 20.856 seconds.

Therefore Hungarian's raw `12/34` match to the accepted aggregate is
partly compensating error: false positives and missed true events can cancel.
It must not be reported as validation of `34`.

## Independent classical-CV cross-check

Claude's background-subtraction/blob ledger provides a genuinely different
measurement path. It uses the same `y=0..310` real-floor ROI and leftward
operational direction, but discards the first 90 frames for background-model
warm-up.

Window alignment matters:

- its centre-line configuration reports 32 rows over 21.924 seconds, or
  `1.460/s`;
- `1.39/s` is the mean across 20 parameter configurations, not `32/21.924`;
- BoT-SORT reports 29 `R→L` candidates in that same post-warm-up window, or
  `1.323/s`;
- the owner's provisional full-video result is `34/24.923 = 1.364/s`.

The blob CSV has 32 rows but only 27 unique track IDs. IDs 202, 637, 489, and
460 trigger repeatedly, creating five extra same-ID crossing alerts. In a
dense merged blob, those alerts may represent fragmentation, several people
inside one component, or both; they cannot simply be labelled 32 unique
travellers.

One-to-one timestamp/vertical-position alignment between the blob ledger and
BoT-SORT is nevertheless strong:

- 23 events match at both `0.50 s / 40 px` and `0.75 s / 60 px` gates;
- median absolute differences are `0.194 s` and `6.1 px`;
- BoT-SORT is on average `0.202 s` later, consistent with track-confirmation
  delay;
- after resolving obvious repeated alerts, there are four distinct
  blob-only and seven BoT-SORT-only candidates;
- the deduplicated candidate union is therefore `23 + 4 + 7 = 34`.

This is materially better evidence for the owner's `34` than agreement between
aggregate totals, but it is still triangulation rather than proof. The 11
single-method candidates would need visual adjudication before any event-level
accuracy claim.
The reported `0.20/s` standard deviation across blob configurations should be
described as a sensitivity spread, not a calibrated sampling standard error or
confidence interval.

## Decision

Use the three trackers as a sensitivity ensemble, not as three votes on a
single total:

1. within this local experiment, use BoT-SORT as the primary automatic
   association path;
2. use Hungarian as the high-recall candidate generator;
3. use ByteTrack as the conservative cross-check;
4. retain the classical-CV ledger as an independent audit channel;
5. cluster their events by direction, time, and vertical position;
6. manually label every disagreement and deduplicate handovers;
7. keep the accepted `12/34` aggregate separate from any future reconciled
   event-time ledger; use that ledger for event-level model validation, not to
   retrofit support for the aggregate decision.

BoT-SORT is the preferred primary path because it retains more verified events
than ByteTrack while avoiding several obvious Hungarian identity jumps. This
is a provisional engineering choice, not a claim of measured precision or
recall. Metrics such as HOTA, IDF1, precision, and recall require labelled
event/identity ground truth and will not be fabricated from aggregate totals.

## Licence and deployment boundary

The exact ByteTrack and BoT-SORT classes used above came from
`ultralytics==8.4.107`, and the YOLO26m model is an Ultralytics trained model.
Ultralytics identifies both its software and trained models as AGPL-3.0 by
default. Its current terms provide a paid R&D licence for strictly
non-operational research and an Enterprise/commercial path for operational
use.

Consequently, “BoT-SORT primary” is a measurement conclusion, not a claim that
this implementation can be privately deployed by HTX. A deployable design
must either obtain the applicable paid R&D licence for a strictly
non-operational proof of concept, obtain an Enterprise/commercial licence for
operational use, or replace the detector and tracker implementation with
licence-approved components and repeat the event-level validation. The
upstream BoT-SORT research repository is MIT, but substituting that
implementation is a new engineering configuration and must be tested rather
than assumed equivalent. See `LICENSING.md`.

## Local evidence

- exact detector cache:
  `_work/tracker_ab_yolo26m_20260727/detections_yolo26m.npz`;
- primary `min_hits=4` tracker outputs:
  `_work/tracker_ab_yolo26m_20260727/{hungarian,bytetrack,botsort}/`;
- byte-identical repeats:
  `_work/tracker_ab_yolo26m_20260727/repeat/`;
- threshold-sensitivity outputs:
  `_work/tracker_ab_yolo26m_20260727/min_hits_1/`;
- disagreement zooms:
  `_work/tracker_ab_yolo26m_20260727/disagreement_zoom/`;
- owner count history:
  `_work/owner_review_zoom/owner_manual_count_history.csv`.
