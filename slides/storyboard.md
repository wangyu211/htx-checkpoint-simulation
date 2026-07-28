# Task 4 — final five-slide operational-insights storyboard

**Status:** implemented and visually verified in
[`HTX_Task4_Operational_Insights.pptx`](HTX_Task4_Operational_Insights.pptx).

The deck is limited to five slides. Visible copy is reviewer-facing; every
slide has a talk track and a `[Sources]` block in speaker notes. The
presentation separates measurement, model assumptions, confirmatory
inference, and the evidence needed before deployment.

## Slide 1 — Problem and evidence boundary

> From 24.9 seconds of video to an auditable checkpoint what-if model

- Accepted local aggregate: 12 left-to-right and 34 right-to-left.
- The clip seeds a conditional model; it does not calibrate long-run demand.
- The evidence chain is human-adjudicated aggregate → executable DES →
  predeclared 600-run study.

## Slide 2 — Measurement, model and inference

> Measurement, model and inference are kept separate

- **Measure:** `34 / 24.922788889 = 1.364213/s`; exact conditional HPP
  interval `0.944757–1.906351/s`; no signed final event-time ledger.
- **Model:** pooled FCFS Security → Immigration, fixed service, 36 / 21
  reference resources, empty start, 300-second arrival window, full drain.
- **Infer:** four capacity alternatives × three registered arrival rates × 50
  replications; pairing only after traveller-level CRN `PASS`.

## Slide 3 — Confirmatory evidence gate

> The 600-run claim is predeclared, paired and auditable

- One frozen primary contrast: base-rate joint `+4/+3` minus reference.
- `600/600` valid runs and `253,756` traveller rows.
- CRN `PASS`: 150 within-rate groups and 1,141,902 draw comparisons.
- Achieved primary 95% half-width `0.382 s`, within the frozen `1.0 s`
  target; no post-hoc extension.

## Slide 4 — Confirmatory result and rate sensitivity

> Joint +4/+3 cuts base-rate P95; the modelled gain is rate-dependent

- Primary joint-minus-reference effect: `−2.678732 s`, paired 95% CI
  `[−3.060892, −2.296573]`, `n=50`.
- Reference-minus-joint supporting improvements: `0.066904 s` low,
  `2.678732 s` base, and `33.158314 s` high; all three intervals exclude zero.
- Joint is lowest at base/high. At the low endpoint, joint and Immigration +3
  tie at `0.000 s`.
- Other pairwise intervals remain unresolved, so no universal option-dominance
  claim is made.

## Slide 5 — Bounded decision and next evidence

> Advance joint +4/+3 to field calibration—not staffing rollout

The study supports carrying the joint mechanism into field calibration. It
does not support immediate staffing, forecasting, cost, or rollout decisions.
The next gates are:

1. time-of-day arrivals and a signed event ledger;
2. stage service-time and exception distributions;
3. observed queues, open resources, rosters, and downtime;
4. calibrated validation and costing of a controlled joint pilot; and
5. production computer-vision licensing and security controls.

## Claim boundary

> Conditional capacity-mechanism evidence under a non-calibrated,
> fixed-service-time pooled-FCFS sandbox—not measured HTX performance, a site
> forecast, staffing answer, economic optimum, or deployment approval.
