# Confirmatory capacity analysis package

**Study:** `TASK3_CAPACITY_MECHANISM_CONFIRMATORY_V1`

**Status:** executed and complete. Strict result validation and
traveller-level common-random-number (CRN) alignment both returned `PASS`.

**Claim boundary:** conditional capacity-mechanism evidence under the
registered fixed-service-time, pooled-FCFS, empty-start, 300-second arrival,
and full-drain assumptions. This package does not establish a calibrated HTX
baseline, staffing answer, economic optimum, site forecast, or costed
deployment recommendation.

## Execution audit

| Item | Recorded result |
|---|---:|
| Design cells | 12 |
| Replications per cell | 50 |
| Exact run coverage | 600 / 600 |
| Entity rows | 253,756 |
| Strict result validation | `PASS` |
| CRN alignment | `PASS` |
| Within-rate pairing groups | 150 |
| Compared branch-invariant draw values | 1,141,902 |
| Confirmatory comparison method | paired Student-t |

The compact tracked package retains run- and replication-level outputs,
validation reports, analysis tables, artifact hashes, and the consolidated
entity-log hash and row count. The large source entity log itself is not part
of this compact package.

## Primary confirmatory result

The pre-specified primary estimand is joint `Security +4 / Immigration +3`
minus reference at the base arrival rate for the mean replication-level total
queue-wait P95:

```text
difference = -2.678732146 s
paired 95% CI = [-3.060891661, -2.296572631]
paired n = 50
achieved half-width = 0.382159515 s <= 1.0 s target
```

The precision target was met. In the equivalent reference-minus-joint
direction, the base-rate improvement is `2.678732 s` with paired 95% CI
`[2.296573, 3.060892]`.

## Supporting rate sensitivity

| Registered arrival rate | Reference minus joint (s) | Paired 95% CI (s) |
|---|---:|---:|
| Exact 95% low | `0.066904` | `[0.006751, 0.127058]` |
| Point estimate / base | `2.678732` | `[2.296573, 3.060892]` |
| Exact 95% high | `33.158314` | `[31.410389, 34.906238]` |

For total queue-wait P95, joint is lowest at the base and high rates. At the
low endpoint, joint and Immigration +3 are tied at `0.000 s`; Security +4 and
reference follow. This is supporting descriptive evidence, not proof that one
option dominates all others. The low-endpoint tie and other unresolved
pairwise intervals mean strict point-order stability across rates is false.

## Post-hoc load-regime supplement

The load-regime supplement was calculated after the confirmatory analysis from
the same frozen 253,756-row entity ledger. It did **not** rerun AnyLogic or
change any study cell, input, parameter, seed, or confirmatory result. Its
outputs are therefore post-hoc supporting diagnostics, not additional
confirmatory endpoints.

Three utilization-related quantities have deliberately different meanings:

- **Nominal offered load**, \(\rho = \lambda \bar{s}/c\), is the configured
  arrival rate multiplied by mean stage service demand and divided by stage
  capacity. Immigration demand includes additional-check demand. This is a
  dimensionless design-load quantity and may exceed one.
- **Arrival-window utilization** is the sum of each service interval's overlap
  with the fixed `[0, 300)`-second arrival window, divided by
  `capacity x 300 seconds`. It measures realised server occupancy while
  arrivals remain open.
- **Full-drain utilization**, reported in the original replication KPIs as
  `security_utilization` and `immigration_utilization`, is total stage busy
  time divided by `capacity x max(300 seconds, last exit)`. Its denominator
  includes the post-cutoff drain period, so it is not interchangeable with
  either nominal offered load or arrival-window utilization and can obscure
  short-window overload.

The nominal-load estimates show why the high endpoint is a distinct operating
regime:

| Arrival level | Reference Security / Immigration | Joint Security / Immigration |
|---|---:|---:|
| Exact 95% low | `0.573 / 0.585` | `0.515 / 0.512` |
| Point estimate / base | `0.827 / 0.845` | `0.744 / 0.739` |
| Exact 95% high | `1.155 / 1.180` | `1.040 / 1.033` |

Absolute total queue-wait P95 estimates (means of 50 replication-level P95s)
make the non-linear rate sensitivity visible:

| Arrival level | Reference mean (95% CI), s | Joint mean (95% CI), s |
|---|---:|---:|
| Exact 95% low | `0.066904 [0.006751, 0.127058]` | `0.000000 [0.000000, 0.000000]` |
| Point estimate / base | `3.928792 [3.156818, 4.700766]` | `1.250060 [0.826249, 1.673872]` |
| Exact 95% high | `51.671359 [48.002214, 55.340503]` | `18.513045 [16.251919, 20.774171]` |

At the exact 95% high arrival endpoint, the following model-scale waiting
diagnostics provide an interpretable view of the tail:

| Total queue wait strictly exceeds | Reference mean (95% CI) | Joint mean (95% CI) | Reference minus joint (paired 95% CI), percentage points |
|---|---:|---:|---:|
| `15 s` | `68.720% [65.354%, 72.087%]` | `20.235% [14.213%, 26.257%]` | `48.485 [42.780, 54.191]` |
| `30 s` | `40.997% [36.224%, 45.770%]` | `1.365% [0.091%, 2.639%]` | `39.632 [35.032, 44.232]` |
| `60 s` | `4.459% [2.309%, 6.609%]` | `0.000% [0.000%, 0.000%]` | `4.459 [2.309, 6.609]` |

For each traveller, total queue wait is
`(security start - security queue join) + (immigration start - immigration queue join)`.
Each threshold rate is first computed within a replication as the number of
travellers whose total wait is strictly above the threshold divided by all
arrivals in that fully drained run. Scenario estimates and their Student-t
intervals are then calculated across the 50 replication-level rates; entity
rows are not pooled as independent observations. Reference-minus-joint
contrasts pair equal replication IDs and use paired Student-t intervals because
the traveller-level CRN audit passed.

The `15/30/60 s` thresholds were selected post hoc as model-scale explanatory
diagnostics. They are **not ICA service-level agreements or published service
standards**, were not prospectively registered, and have no multiplicity-
adjusted confirmatory interpretation. Their intervals quantify replication
uncertainty conditional on this frozen assumption sandbox; they do not turn
the supplement into a calibrated site forecast, staffing rule, or operational
commitment.

## Package contents

- [audit manifest](audit_manifest.json): compact-package status, counts,
  hashes, and claim boundary
- [analysis manifest](analysis_manifest.json): analysis method, gate status,
  and output inventory
- [strict validation report](validation.json): exact 600-run/253,756-row
  coverage result
- [CRN alignment report](crn_alignment.json): 150-group traveller/draw
  alignment result
- [primary result](primary_result.json): pre-specified effect, interval, and
  achieved precision
- [ranking stability](ranking_stability.json): point-order and pairwise
  stability limits
- [rate rankings](rate_rankings.csv): scenario point estimates by arrival rate
- [within-rate pairwise contrasts](within_rate_pairwise_contrasts.csv):
  supporting paired comparisons and unresolved directions
- [scenario estimates](scenario_estimates.csv): replication-level KPI
  summaries by cell
- [scenario contrasts](scenario_contrasts.csv): each scenario versus reference
- [replication KPIs](replication_kpis.csv): analysis inputs at the replication
  level
- [run manifest](run_manifest.csv): exact executed run lineage
- [regime diagnostics manifest](regime_diagnostics_manifest.json): post-hoc
  role, source-ledger identity, thresholds, status, and output hashes
- [regime diagnostics by replication](regime_diagnostics_by_replication.csv):
  nominal load, arrival-window utilization, and threshold rates for all 600
  frozen runs
- [regime estimates](regime_estimates.csv): 50-replication summaries and
  Student-t intervals by scenario and arrival level
- [regime reference-joint contrasts](regime_reference_joint_contrasts.csv):
  paired reference-minus-joint threshold contrasts after the CRN pass
