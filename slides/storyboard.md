# Task 4 — five-slide operational-insights storyboard

**Status:** implemented in
[`HTX_Task4_Operational_Insights.pptx`](HTX_Task4_Operational_Insights.pptx).

The deck uses five content slides, matching the assessment limit. The visible
copy is written for HTX reviewers; speaker notes retain the talk track and
`[Sources]` blocks.

## Slide 1 — Problem overview

> From 25 seconds of video to a decision-ready checkpoint model

The decision problem is framed as evidence-to-policy inference under sparse
local data. The clip can seed a scenario, but it cannot validate a checkpoint
or justify a staffing forecast.

## Slide 2 — Simulation design and assumptions

> The pipeline prevents a short clip from becoming a false baseline

One three-step visual connects:

1. candidate generation, fallback cross-check, and human-owned measurement;
2. an event-driven `Arrival → Security → Immigration → full drain` model; and
3. replicated output analysis with P95, cutoff WIP, clear time, intervals, and
   explicit claim boundaries.

## Slide 3 — Reference performance

> The reference is stable because its assumptions provide headroom

The slide labels the reference as a non-calibrated, pooled-FCFS assumption
sandbox. It reports:

- total queue-wait P95 `3.52 s` (`95% CI 2.92–4.12`);
- Security / Immigration utilization `74.0% / 75.6%`; and
- cohort clear time after the 300-second cutoff `35.3 s`
  (`95% CI 34.1–36.5`).

The evidence gate is also visible: `150/150` runs, `61,218` traveller rows,
zero drops, and strict validation `PASS`.

## Slide 4 — Scenario comparison

> Single-stage capacity moves the bottleneck; service evidence dominates

A stage-level clustered chart compares Reference, Security `+4`, Immigration
`+3`, and joint `+4/+3`. It shows that expanding one stage largely leaves the
other stage active. The joint contrast is `−1.91 s` versus reference
(`95% CI −3.37 to −0.44`).

Two sensitivity callouts prevent a narrow staffing interpretation:

- `+20%` demand raises the total queue-wait P95 to `17.06 s`; and
- the registered `24 s` Immigration context raises it to `164.87 s`.

The slide states the pilot boundary: `n=10` per scenario, pooled FCFS, fixed
service times, and CRN not verified.

## Slide 5 — Recommendations and operational insight

> Pilot balanced capacity—but buy evidence before buying certainty

The recommendation is a staged site-evidence and mechanism-pilot programme,
not a cost-free winner. The rare-work boundary demonstrates why a queue-wait
P95 alone is insufficient:

- queue-wait P95 `30.4 s`; but
- full-drain clear time `7,214 s ≈ 2.0 h`.

The next evidence priorities are time-of-day arrivals, service and exception
distributions, queue/resource/roster observations, confirmatory precision with
verified CRN, and cost/licensing constraints.

## Claim boundary

> Non-calibrated pooled-FCFS assumption sandbox; comparative Monte Carlo
> evidence conditional on registered inputs—not measured HTX performance, a
> site forecast, staffing recommendation, or economic optimum.
