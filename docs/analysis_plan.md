# Result-Blind Analysis Plan

Status: **DRAFT — do not treat as frozen**

Working version: `0.1`, 2026-07-26

This plan will be frozen after the selected simulation engine passes the
baseline, export, seed, and verification gates, and before formal scenario
results are inspected.

## Decision question

Under documented baseline assumptions, which interventions—Security capacity,
Immigration capacity, Immigration queue pooling, or a technology-enabled
service mixture—form the operationally non-dominated set for controlling tail
waiting risk as local demand and measurement uncertainty change?

The decision is deliberately framed as a feasible/Pareto-set problem. Without
cost, implementation-risk, or staffing-value data, the analysis will not name
an economic optimum.

## Result-blind hypotheses

- **H1 — Bottleneck migration.** If Immigration is the constraining stage,
  adding Security capacity alone will not materially improve total tail wait
  and may increase the transient downstream queue.
- **H2 — Queue pooling.** With homogeneous Immigration servers, a pooled queue
  will reduce lane imbalance and may reduce tail waiting without adding
  capacity. The effect is conditional and may shrink under service or traveller
  heterogeneity.
- **H3 — Effective-uptake threshold.** Technology-enabled service will
  outperform marginal Immigration capacity only beyond a joint threshold in
  effective uptake and service-time reduction.
- **H4 — Recommendation stability.** A policy is described as stable only if
  it remains feasible across the predeclared local-demand and video-input
  sensitivity cases actually tested.

These are testable expectations, not conclusions. H2 remains in the final
claim set only if separate and pooled queues are implemented as genuinely
different mechanisms.

## Model boundary

- Local entrance area represented by the supplied video.
- Sequential Security and Immigration processing.
- Finite operational-period experiment.
- Comparative what-if model, not a calibrated digital twin or on-site diagnosis.

## Planned primary estimand

For each replication, calculate the arrival-cohort P95 total waiting time
(`Q95_r`). The scenario-level primary estimate is the mean of `Q95_r` across
replications with a 95% confidence interval.

The working primary feasibility rule is that the upper endpoint of that
scenario-level confidence interval is no more than **900 seconds (15 minutes)**.
This is an explicitly **illustrative decision threshold**, not an ICA service
standard. Decision stability will also be reported at predeclared 600-, 900-,
and 1,200-second thresholds so that the recommendation is not an artefact of
one unsupported cutoff.

Working guardrails:

- cutoff backlog is no more than 5% of the arrival cohort;
- the last member of the arrival cohort clears within 900 seconds after the
  arrival window closes; and
- no scenario may improve waiting by dropping, balking, or silently truncating
  travellers.

Cutoff throughput is reported but is not counted as independent evidence from
cutoff backlog when all admitted travellers are conserved. The confirmatory
replication count, seed manifest, exact planned contrasts, and final arrival
horizon remain `TBD` until the video audit and simulation pilot are complete.

## Minimum P1 comparisons

- Baseline.
- Security-capacity change.
- Immigration-capacity change.
- Immigration separate-versus-pooled queue policy.
- Technology-enabled Immigration-service mixture.
- Illustrative `+20%` local-demand sensitivity.

## Statistical gates

- Use paired CRN analysis only after traveller-level random-input alignment is
  verified; otherwise use independent replications and an independent
  difference interval.
- Baseline and retained policies use identical outer input sample IDs.
- Use a fixed confirmatory replication count selected from pilot variance
  before formal runs.
- Minimum input treatment is low/base/high sensitivity; nested input
  uncertainty is an enhancement after the P1 gate.
- The threshold sensitivity is fixed at 600/900/1,200 seconds before formal
  results. Any amendment must be logged rather than silently replacing it.

## Decision output

Report the feasible and operationally non-dominated set. Without cost,
implementation-risk, or staffing-value data, do not claim an overall economic
optimum. A single option may be described only as a conditional pilot
candidate under explicitly stated assumptions.
