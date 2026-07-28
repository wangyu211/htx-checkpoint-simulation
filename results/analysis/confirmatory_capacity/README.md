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
