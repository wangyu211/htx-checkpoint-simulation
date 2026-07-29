# Task 4 final presentation storyboard

**Status:** implemented and visually verified.

- Canonical five-slide submission:
  [`HTX_Task4_Operational_Insights.pptx`](HTX_Task4_Operational_Insights.pptx)
- Separate local three-slide interview backup:
  `HTX_Task4_Technical_Backup.pptx`

The canonical deck complies with the brief's maximum of five content slides.
The backup is not part of the canonical Task 4 submission and is intentionally
not tracked because the release contract permits exactly one Task 4 PPTX.
Every slide contains speaker notes and a repository-relative `[Sources]` block.

## Canonical slide 1 — evidence boundary

> Evidence-Driven Checkpoint Simulation

- A 24.9-second observation supplies a human-adjudicated directional corridor
  anchor, not a long-run site-demand estimate.
- `34` accepted right-to-left crossings and `1.364/s` are presented with that
  boundary visible.
- A synthetic AnyLogic screenshot replaces all source-video-derived pixels.
- The executed evidence chain now comprises `4,750` validated AnyLogic runs:
  `600` confirmatory, `2,700` capacity-surface, `450` service-variability, and
  `1,000` peak-duration runs.
- The queue-layout result is described separately as an exact-gated conditional
  replay.

## Canonical slide 2 — auditable evidence architecture

> Measurement, mechanism and inference stay separate—and auditable

- **Measure:** `34` accepted right-to-left crossings and `12` opposite-direction
  crossings; computer vision assists, while a human accepts the aggregate.
- **Deployable reference:** YOLOX-S + ByteTrack. YOLO26m + BoT-SORT remains a
  technical-assessment demonstration with an explicit licence boundary.
- **Model:** executable two-stage DES, pooled FCFS, finite resources, full
  drain, and a derived `36/21` model reference.
- **Inference:** four executed AnyLogic studies, CRN and strict validation
  gates, plus a separate exact-gated queue replay.
- The visible claim boundary rules out staffing, SLA, site-forecast, and
  deployment-approval claims.

## Canonical slide 3 — capacity surface and bottleneck migration

> Queueing starts early—and the active bottleneck shifts

- At the derived `36/21` reference, deterministic-ideal P95 queue wait is
  `0 s`, while stochastic HPP mean replication-level P95 total wait is
  `3.93 s`.
- The full `9 × 6` capacity heatmap contains all 54 Base-demand cells with 50
  replications per cell.
- At Immigration capacity 16, Security changes are masked; at Security
  capacity 28, Immigration changes are masked.
- Near `ρ ≈ 1`, one lost modelled service position creates a much larger delay
  penalty.
- All `2,700` runs passed coverage, lineage, conservation, full-drain, CRN, and
  cross-batch checks. The surface is conditional mechanism evidence, not a
  roster or site forecast.

## Canonical slide 4 — duration exposes the operating regime

> Duration exposes the operating regime around ρ ≈ 1

At 120 minutes of stationary-HPP exposure:

- `36/21`, `ρ=.845`: mean P95 queue wait `4.47 s`;
- `30/18`, `ρ=.992`: `55.91 s`;
- `29/17`, `ρ=1.043`: `307 s`; and
- `28/16`, `ρ=1.108`: `748 s`.

The slide distinguishes stable, near-critical, and accumulating finite-horizon
regimes. It also points to two separately accepted robustness findings:

- joint service CV `0→1` adds `95.99 s` to post-cutoff clearance; and
- separate queues add `7.58 s` to P95 total queue wait relative to pooled FCFS.

Only 5, 15, 30, 60, and 120 minutes were simulated. The input is a
stationary-HPP extension of a short clip, not an observed time-of-day profile,
steady-state SLA, staffing rule, or site forecast.

## Canonical slide 5 — bounded decision sequence

> Calibrate the site, locate the regime, then pilot the right lever

1. **Calibrate:** measure time-of-day arrivals, corridor-to-processing-unit
   allocation, stage-service distributions, open-resource schedules,
   exceptions, and downtime.
2. **Locate:** identify `ρ`, duration regime, and the active bottleneck.
3. **Pilot:** test the evidence-supported lever—capacity margin, queue pooling,
   or service-variability relief.
4. **Validate:** assess queue tail, recovery, cost, physical layout, security,
   and operating constraints.

The immediate recommendation is to advance the validated mechanism to site
calibration, not to approve `36/21` or any other roster.

## Technical backup B1 — deterministic oracle

> Random arrivals create delay before deterministic saturation

The deterministic comparator uses regular arrivals and fixed service to isolate
the queueing effect of random arrivals and congestion. It is an explanatory
control, not the forecast.

## Technical backup B2 — service variability

> Service variability is a recovery risk before it is a queue risk

For joint CV `0→1`:

- queue-wait P95 increases by `1.668 s` (`95% CI [0.677, 2.660]`);
- system-time P95 increases by `43.471 s`
  (`[41.565, 45.376]`); and
- post-cutoff clearance increases by `95.993 s`
  (`[81.162, 110.823]`).

These are uncalibrated mean-preserving lognormal sensitivities.

## Technical backup B3 — queue pooling

> Pooling absorbs randomness; separate queues fragment idle capacity

At the `36/21` model reference:

- pooled P95 total wait is `3.929 s`;
- separate JSQ/no-jockeying P95 is `11.509 s`;
- the paired penalty is `+7.580 s` (`95% CI [6.969, 8.192]`); and
- separate queues exhibit a `28.9%` idle-capacity-fragmentation fraction.

This is an offline deterministic replay of the synthetic AnyLogic event ledger.
The executable AnyLogic model and UI remain pooled FCFS, and the observed site
queue policy is unknown.

## Final claim boundary

- `36/21` is a derived pooled model reference, not observed staffing.
- `1.364213/s` is a short-window directional corridor aggregate, not long-run
  site demand.
- Peak duration is a stationary-HPP sensitivity, not observed time of day.
- Service CV and queue policy are conditional sensitivities.
- The queue-layout result is an offline exact-gated replay, not an AnyLogic UI
  policy or field observation.
- No slide claims a staffing recommendation, SLA, site forecast, economic
  optimum, production licence, or deployment approval.
