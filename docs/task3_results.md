# Task 3 replicated operational results

**Status:** frozen confirmatory capacity study executed — 600/600 AnyLogic
runs, 253,756 entity rows, strict result validation `PASS`, CRN alignment
`PASS`, and primary precision target met. The earlier 150-run pilot remains
valid exploratory and engineering evidence.

**Claim boundary:** a non-calibrated, fixed-service-time pooled-FCFS
assumption sandbox. Results are comparative Monte Carlo evidence conditional
on the registered inputs; they are not measured HTX performance, a calibrated
baseline, a site forecast, a staffing answer, or an economic recommendation.

## Executive finding

The most defensible result is a **mechanism finding**, not a winning policy:

> Under the frozen confirmatory assumptions, joint `Security +4 /
> Immigration +3` capacity reduced the base-rate mean replication-level total
> queue-wait P95 by `2.678732 s` relative to reference. The supporting
> low/base/high results show that the magnitude is rate-dependent; they do not
> establish a universally dominant option.

This is exactly why the pipeline retains stage timestamps, cutoff state, full
drain, replication-level KPIs, configuration lineage, and confidence
intervals. Animation alone would not show bottleneck migration or hidden
clearance risk.

## Confirmatory evidence health

| Gate | Recorded outcome |
|---|---:|
| Registered grid | 4 capacity alternatives × 3 arrival rates = 12 cells |
| Replications per cell | 50 |
| Exact run coverage | 600 / 600 |
| Entity rows | 253,756 |
| Strict result validator | `PASS`, 0 errors |
| CRN alignment | `PASS` |
| Within-rate CRN groups | 150 |
| Compared branch-invariant draws | 1,141,902 |
| Primary contrast method | paired Student-t |
| Primary paired sample | 50 replication pairs |
| Precision target | half-width `0.382159515 s <= 1.0 s` |

The statistical sample for the primary result is 50 paired replication-level
KPI differences, not the entity rows.

## Confirmatory primary result

The pre-specified primary direction was joint capacity minus reference at the
base arrival rate:

```text
-2.678732146 s, 95% CI [-3.060891661, -2.296572631]
paired n = 50; half-width = 0.382159515 s
```

The interval excludes zero and meets the registered `1.0 s` half-width
target. This confirms a reduction in the modelled metric under the frozen
assumptions; it does not establish a staffing or economic recommendation.

For interpretability, the supporting reference-minus-joint improvements are:

| Registered arrival rate | Improvement (s) | Paired 95% CI (s) |
|---|---:|---:|
| Exact 95% low | `0.066904` | `[0.006751, 0.127058]` |
| Point estimate / base | `2.678732` | `[2.296573, 3.060892]` |
| Exact 95% high | `33.158314` | `[31.410389, 34.906238]` |

The total-queue-wait-P95 point order was joint, Immigration +3, Security +4,
then reference at all three registered rates. That stable point order is
descriptive. Some other pairwise intervals remain unresolved, and pairwise
point-direction stability across rates is false, so the study does not show
general option dominance.

Tracked evidence:

- [compact analysis package](../results/analysis/confirmatory_capacity/README.md)
- [strict validation report](../results/analysis/confirmatory_capacity/validation.json)
- [CRN alignment report](../results/analysis/confirmatory_capacity/crn_alignment.json)
- [primary result](../results/analysis/confirmatory_capacity/primary_result.json)
- [rate rankings](../results/analysis/confirmatory_capacity/rate_rankings.csv)
- [pairwise contrasts](../results/analysis/confirmatory_capacity/within_rate_pairwise_contrasts.csv)
- [ranking stability](../results/analysis/confirmatory_capacity/ranking_stability.json)

## Pilot evidence retained

The earlier `15 × 10 = 150` run pilot remains useful for pipeline verification,
variance estimation, broad sensitivity screening, and engineering diagnosis.
Its contrasts remain exploratory independent-Welch results because pilot CRN
alignment was `NOT_TESTED`; the confirmatory `PASS` does not apply
retroactively.

## Pilot reference assumption sandbox

`REFERENCE_ASSUMPTION_SANDBOX_V1` uses the accepted Task 1 rate
`1.364213/s`, HPP arrivals for 300 seconds, 36 Security resources at fixed
21.818181818-second demand, 21 Immigration resources at fixed 13-second
demand, pooled FCFS, empty/idle start, and full drain.

| Metric | Mean | 95% CI |
|---|---:|---:|
| Replication-level total queue-wait P95 | 3.52 s | 2.92–4.12 s |
| Total queue wait mean | 0.67 s | 0.48–0.87 s |
| Security wait P95 | 2.07 s | 1.44–2.71 s |
| Immigration wait P95 | 2.32 s | 1.99–2.65 s |
| Security utilization | 74.0% | 71.3%–76.7% |
| Immigration utilization | 75.6% | 72.9%–78.3% |
| Not exited at the 300 s cutoff | 11.94% | 10.56%–13.32% |
| Cohort clear after cutoff | 35.31 s | 34.11–36.50 s |

The reference averages 409.4 arrivals and 360.5 exits by the cutoff. Its low
wait is unsurprising: the reference was deliberately capacity-derived with
headroom, uses fixed service times, and starts empty and idle. It must not be
described as observed baseline performance.

## Pilot capacity and bottleneck migration

| Scenario | Security P95 | Immigration P95 | Utilization S / I | Total P95 |
|---|---:|---:|---:|---:|
| Reference | 2.07 s | 2.32 s | 74.0% / 75.6% | 3.52 s |
| Security +4 | 0.02 s | 2.52 s | 65.1% / 73.8% | 2.68 s |
| Immigration +3 | 2.12 s | 0.17 s | 74.6% / 66.7% | 2.31 s |
| Both +4/+3 | 0.75 s | 0.75 s | 67.8% / 67.3% | 1.62 s |

Scenario-minus-reference total-P95 contrasts:

- Security +4: **−0.84 s** (95% CI −1.81 to +0.13), unresolved at `n=10`.
- Immigration +3: **−1.21 s** (−3.01 to +0.59), unresolved at `n=10`.
- Both: **−1.91 s** (−3.37 to −0.44), a clear but operationally small
  reduction under this sandbox.

Single-stage capacity largely removes its own stage wait while leaving the
other stage active. The joint case best expresses the balanced serial-system
mechanism; it is not an economic optimum because costs and roster constraints
are absent.

## Pilot dominant sensitivities

| Scenario | Total queue-wait P95 | Not exited at cutoff | Clear after cutoff |
|---|---:|---:|---:|
| Reference | 3.52 s | 11.9% | 35.3 s |
| Demand +20% | 17.06 s | 15.6% | 48.3 s |
| Immigration context 24 s | 164.87 s | 45.2% | 218.8 s |
| Immigration context 45 s | 513.87 s | 71.0% | 604.6 s |
| Counter-held proxy: 2% × 900 s | 47.29 s | 22.1% | 953.8 s |
| Counter-held proxy: 2% × 7,200 s | 30.36 s | 18.6% | 7,214.2 s |

- Demand `+20%` raises the primary P95 by **13.54 s** (95% CI
  +7.21 to +19.86), illustrating nonlinear queue growth as both stages
  approach capacity.
- The 24-second and 45-second Immigration contexts increase the primary P95
  by **161.35 s** and **510.35 s**, respectively. Immigration becomes the
  unambiguous downstream constraint.
- The risk rows are deliberately pessimistic foreign-boundary proxies. Their
  long clear times show why a queue-wait P95 alone is insufficient.

The 7,200-second risk row having a lower queue-wait P95 than the 900-second
row is **not** an improvement: the rare 2% branch can be missed by a P95,
queue wait excludes the additional service duration, different random
samples are used, and there are only 10 pilot replications. Full-drain clear
time correctly exposes the extreme operational consequence.

## Pilot automation scenarios

All automation variants reduce Immigration utilization and make Security the
residual tail. Primary-P95 contrasts are:

- HTX context, 50% uptake at `0.6×`: **−1.41 s**
  (95% CI −2.77 to −0.04);
- HTX context, 100% uptake at `0.6×`: **−0.67 s**
  (−2.32 to +0.99);
- ICA context, 50% uptake at `0.4×`: **−1.47 s**
  (−2.67 to −0.26); and
- ICA context, 100% uptake at `0.4×`: **−1.58 s**
  (−3.05 to −0.11).

The apparent non-monotonic HTX 50%/100% point estimates are sampling noise,
not evidence that more uptake is worse. Fine rankings are provisional because
CRN alignment is not verified and `n=10`.

## Why the pilot guardrails cannot be used as a traffic light

Every scenario is below the illustrative 900-second upper-CI rule for the
primary queue-wait P95, so that rule does not discriminate this pilot.
Conversely, every scenario exceeds the draft `≤5%` cutoff-backlog rule.

The backlog rule is structurally misaligned with a 300-second, empty-start
arrival window: in the reference, the mean 48.9 travellers not yet exited at
the cutoff comprise only 1.8 queued and 47.1 normally in service. “Not exited
at cutoff” is therefore mostly expected process WIP, not abandonment or
congestion. It should be reported descriptively until a calibrated horizon
and service-level definition exist.

The two risk-bound rows also exceed the 900-second cohort-clear guardrail.
Those are boundary failures under the counter-held proxy, not forecasts of
ICA operations.

## Interpretation limits

- The confirmatory claim is limited to the pre-specified base-rate
  joint-minus-reference contrast; the low/high contrasts and rankings are
  supporting.
- The confirmatory point order is stable, but unresolved pairwise intervals
  and false pairwise point-direction stability preclude a general dominance
  claim.
- Ten replications are a pilot count; pilot contrasts remain exploratory and
  must not inherit the confirmatory study's paired status.
- Confidence intervals quantify Monte Carlo error conditional on fixed
  assumptions; they omit input uncertainty and model-form error.
- The 154 contrasts are exploratory and have no multiplicity adjustment.
- Only pooled FCFS is implemented, so no separate-versus-pooled effect is
  claimed.
- Fixed service times, homogeneous resources, HPP arrivals, and empty/idle
  starts suppress important real-world variability.
- Utilization is normalized over each scenario's full-drain horizon; very
  long risk drains lower the utilization denominator and must not be read as
  within-window spare capacity.
- Negative Student-t bounds for non-negative KPIs are mathematical interval
  artifacts, not physically negative waiting.
- Automation multipliers, service contexts, and referral rows are registered
  scenario anchors/proxies, not adoption forecasts or local measurements.
- Costs, implementation risk, and roster constraints are absent; no economic
  optimum can be selected.

## Reproduce

The frozen confirmatory replay procedure is recorded in the
[confirmatory design and execution record](task3_confirmatory_design.md).
Its checked-in outputs are documented in the
[tracked compact analysis package](../results/analysis/confirmatory_capacity/README.md).

To reproduce the retained pilot, run
`OperationalPilot: OperationalCheckpointModel` in AnyLogic PLE and wait for
`Finished`, then:

```powershell
.\.venv\Scripts\python.exe -m src.analysis.validate_operational_contract
.\.venv\Scripts\python.exe -m src.analysis.consolidate_operational_results
.\.venv\Scripts\python.exe -m src.analysis.validate_operational_results `
  --require-pilot-coverage
.\.venv\Scripts\python.exe -m src.analysis.analyse_operational_replications
.\.venv\Scripts\python.exe -m src.analysis.build_operational_dashboard
```

Tracked pilot evidence:

- [strict validation report](../results/analysis/operational/validation.json)
- [analysis manifest](../results/analysis/operational/analysis_manifest.json)
- [scenario estimates](../results/analysis/operational/scenario_estimates.csv)
- [scenario contrasts](../results/analysis/operational/scenario_contrasts.csv)
- [dashboard PNG](../results/analysis/operational/operational_dashboard.png)
- [concise generated summary](../results/analysis/operational/README.md)
