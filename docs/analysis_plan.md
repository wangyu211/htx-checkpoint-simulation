# Task 3 Analysis Plan and Execution Record

**Status:** exploratory pilot and Part 1 capacity-expansion study executed;
Part 1 validation and CRN gates `PASS`; Part 2 capacity-availability study
frozen pre-run

**Version:** 0.5, 2026-07-28

The original result-blind draft established the primary estimand, claim
boundary, and rule that paired common-random-number (CRN) analysis could be
used only after alignment verification. The 15-scenario × 10-replication
`OperationalPilot` has now been run and inspected. This document therefore
records the executed pilot analysis; it is not retrospective
preregistration and must not be presented as confirmatory. The pilot is
retained as exploratory and engineering evidence.

The engine/orchestration gate, deterministic two-stage oracle, operational
contract, 150-run batch, strict result validation, replication analysis, and
post-run dashboard all pass their declared software/evidence gates.

The separate
[`TASK3_CAPACITY_MECHANISM_CONFIRMATORY_V1`](task3_confirmatory_design.md)
design froze a narrow base-rate joint-capacity contrast, a 12-cell
low/base/high rate grid, 50 replications per cell, a `1.0 s` precision target,
and a fail-closed CRN rule before its outcomes were inspected. That 600-run
study has now been executed and is the confirmatory evidence in this record.

The independent
[`TASK3_CAPACITY_AVAILABILITY_STRESS_V1`](task3_capacity_availability_design.md)
design is Part 2. It asks what happens to queue length when fewer service
positions are concurrently available. It freezes four reduction arms across
the same low/base/high arrival levels, 50 replications per cell, and a
simultaneous peak-total-queue primary metric before inspecting outcomes.

## Decision question

Under the registered reference assumptions, how sensitive is tail waiting and
clearance behaviour to:

- Security and Immigration capacity;
- local demand;
- named Immigration service-time contexts;
- effective technology uptake and service-time multipliers; and
- external additional-work boundary stresses?

The pilot identifies conditional sensitivities and candidates for further
study. Without calibrated site inputs, cost, implementation-risk, or
staffing-value data, it does not identify an economic optimum or a final
operational recommendation.

The confirmatory question is narrower: at the registered point-estimate
arrival rate, what is the joint `Security +4 / Immigration +3` minus
reference difference in the mean replication-level total queue-wait P95?
Low/high exact count-interval rates and the two single-stage arms are
supporting mechanism analyses.

The Part 2 question is complementary: at the same point-estimate arrival
rate, what is the joint `Security 32 / Immigration 18` minus Reference
`36 / 21` difference in the mean replication-level simultaneous peak total
waiting queue? Single-stage reductions identify where the queue forms; the
`30 / 17` arm and low/high rates describe the near-saturation and overload
boundaries. Until the new runs pass all gates, this is a frozen question, not
a result.

## Hypotheses and implementation boundary

- **H1 — Bottleneck migration.** Capacity at one stage may have limited value
  if the other stage constrains the flow. The pilot includes Security-only,
  Immigration-only, and joint-capacity scenarios.
- **H2 — Queue pooling.** A pooled queue may reduce lane imbalance relative to
  genuinely separate queues. This hypothesis is **not tested in v1**:
  `OperationalCheckpointModel` implements pooled FCFS only, so no
  separate-versus-pooled effect is claimed.
- **H3 — Effective-uptake threshold.** Technology effects depend jointly on
  effective uptake and service-time reduction. The pilot includes named
  multiplier/uptake combinations as comparative scenarios, not adoption
  forecasts.
- **H4 — Stress sensitivity.** Conclusions may change under demand,
  service-time, or additional-work stresses. The pilot includes explicit
  low/high demand, named service contexts, and external risk-bound rows.
- **H5 — Capacity availability.** A reduction may have modest consequences
  at light load but nonlinear queue consequences near saturation. Part 2
  tests stage-specific, joint, and critical-boundary capacity reductions;
  it does not represent an observed roster or propose staffing levels.

These remain modelling expectations and scope statements rather than claims
about an HTX site.

## Model boundary

- Local entrance demand evidence comes from the supplied short video.
- Arrivals are represented by a stationary-independent HPP assumption.
- The executable is a sequential Security-to-Immigration pooled-FCFS DES with
  finite resources.
- Arrivals occur for 300 seconds; the admitted cohort then fully drains.
- Queue guards are finite and non-binding under the recorded runs; no
  traveller may be silently dropped to improve a result.
- Automation is represented by an effective service-time multiplier.
- Additional work uses a counter-held risk proxy in the two external boundary
  scenarios.
- The model is a comparative what-if sandbox, not a calibrated digital twin,
  site diagnosis, or operational forecast.

## Reference scenario

The formal reference is `REFERENCE_ASSUMPTION_SANDBOX_V1`, never “calibrated
HTX baseline.” Its declared inputs include:

- Task 1 rate: 1.364213 travellers/second;
- HPP demand multiplier: 1.0;
- 300-second arrival cutoff and full drain;
- Security: 36 resources and fixed 21.818181818-second service;
- Immigration: 21 resources and fixed 13-second service;
- pooled FCFS and 5,000-traveller queue guards;
- automation disabled and zero additional checks; and
- 10 pilot replications with registered scenario-specific seed lineage.

Each value is linked to direct evidence, named context, derivation, structural
choice, or transparent assumption in the provenance registries. The
2-second/3-second `TwoStageDeterministic` oracle remains ineligible for
operational performance reporting.

## Analysis roles and primary estimands

For replication `r`, calculate the admitted arrival-cohort P95 total queue
waiting time, `Q95_r`.

For the exploratory pilot, each scenario mean uses 10 replication-level
values. Each contrast is scenario minus
`REFERENCE_ASSUMPTION_SANDBOX_V1`; traveller/draw alignment was not verified,
so those executed contrasts use independent Welch intervals. No paired-CRN
precision claim is made for the pilot.

For the confirmatory study, the single primary contrast is
`CAPACITY_BOTH_PLUS` minus `REFERENCE_ASSUMPTION_SANDBOX_V1` at
`LOCAL_WINDOW_HPP_BASE`. Its registered comparison method is paired
Student-t only after a current full CRN `PASS`, otherwise independent Welch.
The full gate passed, so the executed primary analysis used 50 paired
replication differences:

```text
-2.678732146 s, 95% CI [-3.060891661, -2.296572631]
half-width = 0.382159515 s <= 1.0 s target
```

Secondary outputs include:

- mean and P95 Security, Immigration, total queue, and system time;
- Security and Immigration utilisation;
- maximum queues;
- cutoff backlog and stage WIP;
- clear time after cutoff;
- admitted, completed, rejected/dropped, technology, and additional-check
  counts; and
- conservation and full-drain indicators.

The working 600/900/1,200-second wait thresholds are illustrative sensitivity
levels only. They are not ICA service standards.

## Executed pilot scenario set

The registered 15-row set contains:

1. reference assumption sandbox;
2. Security +4;
3. Immigration +3;
4. both capacity changes;
5. demand ×0.8;
6. demand ×1.2;
7. Singapore bus-hall QR context at 10 seconds;
8. Singapore train-kiosk context at 24 seconds;
9. Singapore train manual-counter context at 45 seconds;
10. HTX trial multiplier 0.6 at 50% effective uptake;
11. HTX trial multiplier 0.6 at 100% effective uptake;
12. ICA rollout multiplier 0.4 at 50% effective uptake;
13. ICA rollout multiplier 0.4 at 100% effective uptake;
14. external 2% / 900-second counter-held risk bound; and
15. external 2% / 7,200-second counter-held risk bound.

The external risk rows are deliberately pessimistic boundary tests. They are
not estimates of ICA referral frequency, handling, or staffing.

## Replication and statistical gates

- The exploratory batch uses 10 replications per scenario. Ten is a pilot count
  for variance and pipeline evidence, not a confirmatory precision claim.
- Its exact registered scenario × replication coverage is 150 runs,
  with no duplicate or missing keys.
- Pilot seeds are scenario-specific and reproducible.
- Pilot `crn_alignment_status` is `NOT_TESTED`; independent Welch contrasts are
  therefore required.
- The confirmatory design fixed 12 cells × 50 replications = 600 runs before
  outcome inspection. All 600 runs and 253,756 entity rows passed strict
  validation.
- Confirmatory CRN alignment is `PASS` across 150 within-rate replication
  groups and 1,141,902 compared branch-invariant draw values. Paired analysis
  is therefore permitted for within-rate contrasts.
- The primary confirmatory half-width is `0.382159515 s`, satisfying the
  registered `<= 1.0 s` target without adding runs post hoc.
- Part 2 fixes 12 new cells × 50 replications = 600 new runs and reuses only
  the 150 immutable Reference runs after exact hash, key, seed, and
  traveller-level alignment checks. Its analytical grid is 750 runs.
- Part 2 uses paired intervals only after a fresh CRN gate returns explicit
  `PASS`; otherwise it falls back to independent Welch intervals. Adaptive
  post-outcome extension is prohibited.
- Monte Carlo confidence intervals are conditional on the registered input
  assumptions. They do not quantify input uncertainty or model-form error.

## Executed evidence and reproduction

Run `OperationalPilot: OperationalCheckpointModel` in AnyLogic PLE and wait
for `Finished`, then execute:

```powershell
.\.venv\Scripts\python.exe -m src.analysis.validate_operational_contract
.\.venv\Scripts\python.exe -m src.analysis.consolidate_operational_results
.\.venv\Scripts\python.exe -m src.analysis.validate_operational_results `
  --require-pilot-coverage
.\.venv\Scripts\python.exe -m src.analysis.analyse_operational_replications
.\.venv\Scripts\python.exe -m src.analysis.build_operational_dashboard
```

Recorded execution:

- 150/150 runs;
- 61,218 traveller rows;
- strict validation `PASS`; and
- 165 scenario-estimate rows and 154 contrast rows.

Tracked pilot evidence:

- [`strict validation report`](../results/analysis/operational/validation.json)
- [`analysis manifest`](../results/analysis/operational/analysis_manifest.json)
- [`scenario estimates`](../results/analysis/operational/scenario_estimates.csv)
- [`scenario contrasts`](../results/analysis/operational/scenario_contrasts.csv)
- [`dashboard and result interpretation`](../results/analysis/operational/README.md)

Confirmatory execution:

- 12 cells × 50 replications = 600/600 runs;
- 253,756 entity rows;
- strict result validation `PASS`;
- CRN alignment `PASS` across 150 groups and 1,141,902 compared draw values;
  and
- paired primary precision target met at `n = 50`.

Tracked confirmatory evidence:

- [`compact package guide`](../results/analysis/confirmatory_capacity/README.md)
- [`audit manifest`](../results/analysis/confirmatory_capacity/audit_manifest.json)
- [`strict validation report`](../results/analysis/confirmatory_capacity/validation.json)
- [`CRN alignment report`](../results/analysis/confirmatory_capacity/crn_alignment.json)
- [`primary result`](../results/analysis/confirmatory_capacity/primary_result.json)
- [`ranking stability`](../results/analysis/confirmatory_capacity/ranking_stability.json)

## Decision output and claim rule

The pilot may report direction, magnitude, uncertainty, and which assumptions
dominate the observed scenario response. Fine rankings with overlapping
intervals remain unresolved at `n=10`.

The confirmatory result supports the narrow statement that, under the
registered fixed-service-time pooled-FCFS assumptions, joint capacity reduced
the base-rate mean replication-level total queue-wait P95 relative to the
reference by `2.678732 s` (reference minus joint, paired 95% CI
`[2.296573, 3.060892]`). In the supporting rate analysis, joint is lowest at
the base and high endpoints and tied with Immigration +3 at `0.000 s` at the
low endpoint. It must not be reported as option dominance: the low-endpoint
tie and other unresolved pairwise intervals mean that a strict point order is
not stable across rates.

No option is labelled an operational optimum or final recommendation. All
results are conditional on a non-calibrated, fixed-service-time pooled-FCFS
sandbox. Separate-queue evaluation, field calibration, richer input
distributions, costs, implementation risk, and roster constraints remain
outside scope; the study does not provide a calibrated baseline, staffing
answer, or economic claim.
