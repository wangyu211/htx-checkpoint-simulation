# Task 4 — final five-slide operational-insights storyboard

**Status:** implemented and visually verified in the canonical submission deck,
[`HTX_Task4_Operational_Insights.pptx`](HTX_Task4_Operational_Insights.pptx).
A byte-identical local v4 copy is retained as the versioned review artifact;
the canonical deck is the repository deliverable.

The deck is limited to five slides. Visible copy is reviewer-facing; every
slide has a talk track and a repository-relative `[Sources]` block in speaker
notes. The presentation keeps measurement, model assumptions, confirmatory
inference, exploratory sensitivity, and deployment evidence visibly separate.

## Slide 1 — Problem and evidence boundary

> From 24.9 seconds of video to an auditable checkpoint what-if model

- Accepted local aggregate: 12 left-to-right and 34 right-to-left.
- The 34 accepted right-to-left crossings anchor a conditional model; they do
  not calibrate long-run site demand.
- Two studies test different questions:
  - 600 confirmatory runs test a frozen capacity mechanism.
  - 2,700 exploratory runs map its conditional operating boundary.

## Slide 2 — Measurement, model and inference

> Measurement, model and inference stay separate—and visible

- **Measure:** human-adjudicated count and a bounded HPP arrival-rate interval.
- **Model:** executable two-stage traveller-level DES; pooled FCFS, finite
  resources, fixed service-time assumptions, a 300-second arrival window, and
  full drain.
- **Confirm:** four alternatives × three registered arrival rates × 50
  replications = 600 frozen runs.
- **Explore:** nine Security capacities × six Immigration capacities × 50
  replications = 2,700 Base-demand runs.
- CRN alignment and validation pass in both studies. The five repeated cells
  validate cross-batch reproducibility only and do not enter the response
  surface twice.

## Slide 3 — Stochastic response versus deterministic ideal

> Variability creates delay before deterministic saturation

- At the derived 36/21 reference, deterministic-ideal P95 queue wait is
  `0 s`, while stochastic HPP mean replication-level P95 total wait is
  `3.93 s`.
- With Immigration fixed at 21, Security capacity 36→28 increases P95 total
  wait from `3.93 s` to `24.43 s`.
- With Security fixed at 36, Immigration capacity 21→16 increases it from
  `3.93 s` to `35.61 s`.
- The one-position penalty accelerates near `ρ ≈ 1`:
  - Security: `0.29 s` initially versus `6.98 s` near the boundary.
  - Immigration: `1.31 s` initially versus `14.68 s` near the boundary.
- The deterministic comparator uses regular arrivals and fixed service. It is
  an explanatory control, not a site forecast. Only integer capacities were
  simulated; connecting lines are visual guides.

## Slide 4 — Capacity surface and bottleneck migration

> The active bottleneck—not two shortages added—sets total delay

- The full 9 × 6 heatmap contains all 54 simulated capacity cells at fixed
  Base demand, with 50 replications per cell.
- **Immigration-dominant region:** at Immigration 16, Security 36→31 leaves
  total-wait P95 at approximately `35.61 s`; upstream relief is masked.
- **Security-dominant region:** at Security 28, Immigration 21→17 moves
  total-wait P95 only from `24.43 s` to `25.38 s`; downstream relief is
  masked.
- **Upstream metering:** for Security 30→29 with Immigration 18→17, the local
  difference-in-differences is `−4.02 s` (`95% CI [−4.72, −3.32]`).
  The negative interaction means serial-flow sub-additivity; it does not mean
  that removing capacity is beneficial.
- The response surface is conditional exploratory evidence, not a staffing
  recommendation.

## Slide 5 — Bounded decision and next evidence

> Calibrate the site, locate the bottleneck, then pilot relief

1. **Calibrate:** measure time-of-day arrivals, stage service, exceptions, and
   downtime.
2. **Locate:** place the observed site on the capacity response surface.
3. **Pilot:** relieve Security, Immigration, or both according to the active
   bottleneck.
4. **Validate:** test queue impact, cost, layout, and operating constraints.

The immediate decision is to advance the validated mechanism to site
calibration—not to approve a roster. A field pilot additionally needs:

- a signed time-of-day event ledger;
- stage service, exception, and downtime distributions;
- observed queues, open resources, and rosters;
- a costed bottleneck-aware intervention; and
- production computer-vision licensing and security controls.

## Audit and claim boundary

- `54 × 50 = 2,700` response-surface runs are complete.
- `1,113,588` traveller rows were audited.
- Configuration lineage, conservation, full drain, CRN alignment, and
  cross-batch reproducibility pass.
- `36/21` is a derived reference capacity—not observed staffing.
- Results are conditional mechanism and sensitivity evidence under a
  non-calibrated, fixed-service-time pooled-FCFS sandbox—not measured HTX
  performance, a site forecast, a staffing answer, an economic optimum, or
  deployment approval.
