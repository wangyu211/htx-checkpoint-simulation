# Task 3 confirmatory capacity-mechanism design

**Design:** `TASK3_CAPACITY_MECHANISM_CONFIRMATORY_V1`

**Status:** frozen design executed; 600/600 AnyLogic runs, strict result
validation `PASS`, CRN alignment `PASS`, and confirmatory analysis complete

**Claim ceiling:** conditional capacity-mechanism evidence only. This design
does not create a calibrated HTX baseline, site forecast, economic optimum, or
staffing recommendation.

## Why this upgrade exists

The 15-scenario x 10-replication run was deliberately a pilot. It established
the executable pipeline, exposed bottleneck migration, and supplied variance
estimates. It did not pre-register a narrow primary question, quantify
short-window Poisson counting uncertainty, or verify common-random-number
(CRN) alignment.

This upgrade converted those lessons into a frozen confirmatory design that
was registered before the 600-run outcomes were inspected:

1. one primary capacity contrast;
2. an exact count-based arrival-rate sensitivity;
3. a replication cap selected from pilot variance without borrowing
   unverified CRN precision; and
4. a machine-enforced traveller-level CRN gate.

The machine-readable design is
[`confirmatory_capacity_study.json`](../config/confirmatory_capacity_study.json).
The 150 explicit stream groups are frozen in
[`confirmatory_seed_manifest.csv`](../config/confirmatory_seed_manifest.csv).

## Arrival-rate uncertainty: what it does and does not mean

Conditional on the accepted right-to-left count `n = 34`, the observed exposure
`T = 24.922788889 s`, and a homogeneous Poisson process:

```text
N | lambda, T ~ Poisson(lambda T)
lambda_hat = N / T
```

The exact two-sided 95% Garwood interval is:

```text
lower = 0.5 * chi2_quantile(0.025, 2N) / T
upper = 0.5 * chi2_quantile(0.975, 2(N + 1)) / T
```

This gives the three registered arrival levels:

| Role | Rate (travellers/s) | Relative to point estimate |
|---|---:|---:|
| Exact 95% lower endpoint | `0.944757366` | `0.6925x` |
| Count/exposure point estimate | `1.364213297` | `1.0000x` |
| Exact 95% upper endpoint | `1.906351344` | `1.3974x` |

These endpoints quantify **Poisson counting-process sampling error only,
conditional on 34 being the accepted count**. They do not quantify:

- human adjudication error;
- detector/tracker model-selection error;
- ambiguity between earlier candidate counts such as 27, 29, and 34;
- time-of-day or day-to-day demand variation;
- non-stationarity; or
- arrival-model misspecification.

The 27/29/34 values are not interchangeable repeated observations. They came
from different technical/review stages, so treating them as a statistical
sample would invent a distribution. Human-count uncertainty must instead be
handled by the frozen audit trail and, if necessary, independent re-review of
the video.

The interval is wide because 24.9 seconds is short. That is an honest result
and a reason to request longer site data before making operational forecasts.

## Narrowed study question and cells

The primary question is:

> At the count/exposure point-estimate arrival rate, what is the
> `CAPACITY_BOTH_PLUS` minus reference difference in the mean of
> replication-level total queue-wait P95?

Only this contrast is confirmatory. The two single-stage arms diagnose
bottleneck migration at the base rate. Low/high arrival endpoints test whether
the joint mechanism is robust to exact count-based rate uncertainty; those
boundary contrasts are supporting and descriptive.

| Arrival level | Reference | Security +4 | Immigration +3 | Joint +4/+3 |
|---|:---:|:---:|:---:|:---:|
| Exact 95% low | run | run | run | run |
| Point estimate | run | run | run | run |
| Exact 95% high | run | run | run | run |

This is a complete `4 capacity alternatives x 3 rate levels = 12 cells`
capacity-mechanism grid rather than a repeat of the heterogeneous exploratory
15-scenario portfolio. Keeping all four capacity alternatives at all three
rates makes bottleneck migration and option-ranking stability directly
auditable instead of assuming that the base-rate ordering persists at the
count-interval boundaries. Only the pre-specified base-rate joint-versus-
reference contrast is confirmatory; cross-rate rankings remain supporting.
Service times, pooled FCFS, empty/idle start, 300-second arrival window, and
full-drain rule remain fixed registered assumptions. Therefore the design
tests a capacity mechanism under those assumptions; it does not solve input
calibration.

## Precision target and run cap

The target is a two-sided 95% interval half-width of at most `1.0 s` for the
primary base-rate difference.

Pilot standard deviations for the replication-level primary metric were:

| Pilot arm | Standard deviation (s) |
|---|---:|
| Reference | `0.835371324` |
| Security +4 | `1.185190025` |
| Immigration +3 | `2.447822001` |
| Joint +4/+3 | `1.955665006` |

The design uses `2.447822001 s`, the largest of the four values, as the
standard-deviation envelope for **each** independent arm. For equal arm size
`r`, the conservative planning half-width is:

```text
h(r) = t(0.975, 2r - 2) * sqrt(2 * s_max^2 / r)
```

This calculation requires 48 runs per arm (`h = 0.9921 s`). The plan rounds
up to 50 runs per cell (`h = 0.9715 s`). With 12 cells, the fixed run cap is:

```text
12 cells * 50 replications = 600 runs
```

This is an independent two-sample precision calculation. It does not use a
paired pilot variance, does not claim statistical power for a chosen minimum
effect, and does not promise that low/high boundary cells will attain the same
precision. If the realised primary interval misses the target, the miss is
reported; runs are not added post hoc.

## CRN seed intent and mandatory validation gate

The seed manifest uses common stream seeds across scenario variants within the
same arrival level and replication. Different arrival levels are separate
input samples and are not paired with each other.

A shared seed is not proof of CRN alignment. Before any paired interval is
allowed, [`validate_crn_alignment.py`](../src/analysis/validate_crn_alignment.py)
requires all of the following:

1. exact expected run coverage, with no missing, duplicate, or unexpected run;
2. `COMPLETE` status and exact master/arrival/service/routing/tie seeds;
3. identical traveller-ID sets for every within-level scenario group; and
4. equality, traveller by traveller, of all recorded branch-invariant draws:
   arrival time, Security demand, conventional Immigration demand,
   automation uniform, additional-check uniform, and lane-tie uniform.

Queue joins, resource assignments, service starts, and exits may differ: those
are endogenous scenario responses, not CRN alignment fields.

Run the gate on the consolidated confirmatory result directory:

```powershell
.\.venv\Scripts\python.exe -m src.analysis.validate_crn_alignment `
  --results-dir results\raw\confirmatory_capacity_consolidated
```

Paired analysis is permitted only when the report contains all of:

```json
{
  "status": "PASS",
  "seed_alignment_pass": true,
  "traveller_level_alignment_pass": true,
  "branch_invariant_draws_pass": true
}
```

If any condition fails, the pre-specified fallback is an independent Welch
interval. In the executed confirmatory study, the current full gate passed:
all 600 runs and 253,756 entity rows were covered, all 150 within-rate
replication groups aligned, and 1,141,902 branch-invariant draw values were
compared. The confirmatory analysis therefore used the permitted paired
Student-t interval. The earlier 150-run pilot remains `NOT_TESTED` and cannot
be retroactively described as paired.

## Executed confirmatory result

The 12 cells were each run for the fixed 50 replications (`12 x 50 = 600`).
Strict result validation and CRN alignment both returned `PASS`.

For the pre-specified base-rate primary estimand, joint capacity
(`Security +4 / Immigration +3`) minus reference was:

```text
-2.678732146 s, 95% CI [-3.060891661, -2.296572631]
paired n = 50; achieved half-width = 0.382159515 s <= 1.0 s target
```

Equivalently, in the more intuitive reference-minus-joint direction, the
supporting rate-specific improvements were:

| Registered arrival rate | Reference minus joint (s) | Paired 95% CI (s) |
|---|---:|---:|
| Exact 95% low | `0.066904` | `[0.006751, 0.127058]` |
| Point estimate / base | `2.678732` | `[2.296573, 3.060892]` |
| Exact 95% high | `33.158314` | `[31.410389, 34.906238]` |

For total queue-wait P95, joint was lowest at the base and high rates and
tied with Immigration +3 at `0.000 s` at the low endpoint. This is
supporting, rate-specific evidence—not proof of option dominance. The
low-endpoint tie and other unresolved pairwise intervals mean strict
point-order stability across rates is false.

The tracked compact analysis package contains the auditable result:

- [package guide](../results/analysis/confirmatory_capacity/README.md)
- [strict validation report](../results/analysis/confirmatory_capacity/validation.json)
- [CRN alignment report](../results/analysis/confirmatory_capacity/crn_alignment.json)
- [primary result](../results/analysis/confirmatory_capacity/primary_result.json)
- [ranking stability](../results/analysis/confirmatory_capacity/ranking_stability.json)

These results are conditional capacity-mechanism evidence under the
registered fixed-service-time, pooled-FCFS, empty-start, and full-drain
assumptions. They do not create a calibrated baseline, staffing answer,
economic optimum, or costed deployment recommendation.

## Validate the frozen design

```powershell
.\.venv\Scripts\python.exe -m src.analysis.confirmatory_design
.\.venv\Scripts\python.exe -m unittest `
  tests.test_confirmatory_design tests.test_confirmatory_pipeline `
  tests.test_crn_alignment
```

The design validator recomputes the exact Poisson endpoints, precision
requirement, 12-cell/600-run cap, all 150 seed groups, and every stream seed.

## Reproduce the frozen study

Close AnyLogic before regeneration, then run:

```powershell
.\.venv\Scripts\python.exe scripts\generate_operational_anylogic.py
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

To reproduce the executed study, open
`simulation/anylogic/HTXCheckpointSimulation/HTXCheckpointSimulation.alpx`
in AnyLogic PLE and run `CapacityRobustnessConfirmatory`. The blank Parameter
Variation window is expected. A private one-shot timer starts the study
automatically; do not press Play. The study runs 12 cells x 50 replications
serially and must reach `Finished`. Each run is written beneath
`results/raw/confirmatory_capacity/<scenario>/<input-sample>/replication_NNN`.

After the 600 replay runs finish:

```powershell
.\.venv\Scripts\python.exe -m src.analysis.consolidate_operational_results `
  --confirmatory
.\.venv\Scripts\python.exe -m src.analysis.validate_operational_results `
  --results-dir results\raw\confirmatory_capacity_consolidated `
  --require-confirmatory-coverage `
  --report results\intermediate\confirmatory_capacity\validation.json
.\.venv\Scripts\python.exe -m src.analysis.analyse_confirmatory_capacity
```

The final analysis writes only to
`results/analysis/confirmatory_capacity`. It records the achieved primary
half-width, all rate-specific rankings, ranking stability, and the exact CRN
decision. Paired intervals are used only after a current full CRN `PASS`;
otherwise the analysis automatically uses the pre-specified Welch fallback.

## Execution status and boundaries

Implemented and executed in this upgrade:

- exact count-based low/base/high rates;
- one primary and explicitly secondary analyses;
- conservative independent precision sizing and a fixed run cap;
- a complete machine-readable seed manifest;
- generated `CapacityRobustnessConfirmatory` AnyLogic Parameter Variation
  experiment with 12 registry-derived cells, 50 replications per cell, serial
  execution, exact frozen stream seeds, and one-shot auto-start;
- composite `(scenario_id, input_sample_id, replication_id)` lineage and exact
  600-run coverage validation;
- an executable, artifact-hashed traveller-level CRN alignment validator;
- fail-closed consolidation and confirmatory analysis with paired/Welch
  gating, achieved precision, pairwise directions, and ranking stability;
- unit tests covering arithmetic, generator parity, exact coverage,
  stale-report rejection, pairing fallback, and ranking reversal;
- 600/600 completed runs, 253,756 entity rows, strict validation `PASS`, and
  CRN alignment `PASS` across 150 groups and 1,141,902 compared draw values;
  and
- the paired base-rate primary result with the achieved `0.382159515 s`
  half-width, satisfying the registered `1.0 s` target.

Deliberately not changed:

- the accepted human aggregate or its audit document;
- the completed pilot results;
- the 15-scenario pilot registry or its already executed results;
- the operational process mechanism, service-time assumptions, queue policy,
  start state, arrival cutoff, or full-drain rule;
- service-time or site calibration assumptions.

After the registered run completed and passed its gates, the repository README
and Task 4 presentation were updated with the observed confirmatory result and
its claim boundary. No result was pre-filled before execution. These
boundaries are intentional: the upgrade answers the technical-review gap
without rewriting accepted upstream evidence or silently replacing pilot
results. The commands above are retained as the reproducibility path.
