# Task 3 Pilot Analysis Plan and Execution Record

**Status:** pilot design executed; not a frozen confirmatory analysis plan

**Version:** 0.3, 2026-07-28

The original result-blind draft established the primary estimand, claim
boundary, and rule that paired common-random-number (CRN) analysis could be
used only after alignment verification. The 15-scenario × 10-replication
`OperationalPilot` has now been run and inspected. This document therefore
records the executed pilot analysis; it is not retrospective
preregistration and must not be presented as confirmatory.

The engine/orchestration gate, deterministic two-stage oracle, operational
contract, 150-run batch, strict result validation, replication analysis, and
post-run dashboard all pass their declared software/evidence gates.

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

## Primary estimand

For replication `r`, calculate the admitted arrival-cohort P95 total queue
waiting time, `Q95_r`. For each scenario, report the mean of its 10
replication-level `Q95_r` values with a 95% confidence interval.

Each scenario contrast is scenario minus
`REFERENCE_ASSUMPTION_SANDBOX_V1`. Because traveller/draw alignment was not
verified, the executed default is an independent Welch interval. No paired-CRN
precision claim is made.

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

- The executed batch uses 10 replications per scenario. Ten is a pilot count
  for variance and pipeline evidence, not a confirmatory precision claim.
- Exact registered scenario × replication coverage is required: 150 runs,
  with no duplicate or missing keys.
- Seeds are scenario-specific and reproducible.
- `crn_alignment_status` is `NOT_TESTED`; independent Welch contrasts are
  therefore required.
- Monte Carlo confidence intervals are conditional on the registered input
  assumptions. They do not quantify input uncertainty or model-form error.
- A future confirmatory design must select its replication count and exact
  contrasts before inspecting new confirmatory outcomes.

## Run, validate, analyse, and visualise

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

Primary evidence:

- [`strict validation report`](../results/intermediate/operational_results/validation.json)
- [`analysis manifest`](../results/analysis/operational/analysis_manifest.json)
- [`scenario estimates`](../results/analysis/operational/scenario_estimates.csv)
- [`scenario contrasts`](../results/analysis/operational/scenario_contrasts.csv)
- [`dashboard and result interpretation`](../results/analysis/operational/README.md)

## Decision output and claim rule

The pilot may report direction, magnitude, uncertainty, and which assumptions
dominate the observed scenario response. Fine rankings with overlapping
intervals remain unresolved at `n=10`.

No option is labelled an operational optimum or final recommendation. At most,
an option may be described as a conditional candidate for a better-calibrated
pilot under explicit assumptions. Separate-queue evaluation, field
calibration, richer input distributions, confirmed CRN alignment, and
confirmatory replication sizing remain future work.
