# Task 3 Part 2 — Capacity-Availability Stress Design

**Status:** execution and registered analysis complete

**Study ID:** `TASK3_CAPACITY_AVAILABILITY_STRESS_V1`

**Purpose:** explain how fewer concurrently open service positions change
queue length, waiting, backlog, and recovery under the same registered demand
and service assumptions.

## Why this is a separate analysis

The two capacity studies answer complementary questions and must not be
silently mixed:

| Analysis | Question | Runs |
|---|---|---:|
| Part 1 — capacity expansion | What improves when Security and/or Immigration capacity is added? | 600 immutable runs |
| Part 2 — capacity availability | What deteriorates when fewer Security and/or Immigration positions are available? | 600 new runs plus 150 read-only Reference runs |

Part 1 remains unchanged. Part 2 reuses only its 150 Reference runs, after
configuration, seed, key, and traveller-level alignment checks, and combines
them with 600 new reduction runs. The Part 2 analytical grid therefore has
750 runs.

This analysis directly addresses the assessment brief's example of
investigating staffing-level effects. It is a model-based capacity-resilience
analysis, not a staffing roster forecast.

## Meaning of 36 / 21

`36` Security and `21` Immigration resources are the reference capacities
that actually govern concurrency in the executable model. They were selected
by the transparent rule

```text
capacity = ceil(arrival_rate × mean_service_time / 0.85)
```

so the reference configuration is near 85% nominal offered load at the
accepted point-estimate arrival rate. These values are not counts observed in
the video, an HTX roster, installed checkpoint capacity, or recommended
headcount.

For Part 2, one capacity unit means one concurrently staffed and open service
position during the modelled window. It should not be converted one-for-one
into total FTE without shift, break, relief, absenteeism, and roster data.

## Frozen experimental grid

The four new execution arms are:

| Scenario | Security | Immigration | Interpretation |
|---|---:|---:|---|
| `CAPACITY_AVAIL_SECURITY_MINUS_4` | 32 | 21 | Security-only availability loss |
| `CAPACITY_AVAIL_IMMIGRATION_MINUS_3` | 36 | 18 | Immigration-only availability loss |
| `CAPACITY_AVAIL_JOINT_MINUS_4_MINUS_3` | 32 | 18 | joint reduction; primary alternative |
| `CAPACITY_AVAIL_SEVERE_JOINT_30_17` | 30 | 17 | critical stress boundary, not a proposed roster |

The read-only comparison arm is
`REFERENCE_ASSUMPTION_SANDBOX_V1 = 36 / 21`.

All five arms are analysed at the same three frozen arrival-rate levels used
in Part 1:

| Arrival level | Rate (/s) | Role |
|---|---:|---|
| Exact-count low | `0.944757366` | lower HPP count-interval endpoint |
| Point estimate / base | `1.364213297` | accepted count divided by exposure |
| Exact-count high | `1.906351344` | upper HPP count-interval endpoint |

The resulting nominal offered loads are:

| Capacity S / I | Low rho S / I | Base rho S / I | High rho S / I |
|---|---:|---:|---:|
| 36 / 21 | `0.573 / 0.585` | `0.827 / 0.845` | `1.155 / 1.180` |
| 32 / 21 | `0.644 / 0.585` | `0.930 / 0.845` | `1.300 / 1.180` |
| 36 / 18 | `0.573 / 0.682` | `0.827 / 0.985` | `1.155 / 1.377` |
| 32 / 18 | `0.644 / 0.682` | `0.930 / 0.985` | `1.300 / 1.377` |
| 30 / 17 | `0.687 / 0.722` | `0.992 / 1.043` | `1.386 / 1.458` |

This grid is intentional. It tests whether a modest capacity loss has little
effect in a light regime, produces nonlinear queue growth near saturation,
and compounds an already overloaded high-demand regime. The `30 / 17` arm
crosses the nominal `rho = 1` boundary at the base rate and is therefore a
mechanism stress test, not a staffing proposal.

## Primary analysis

The single primary estimand is:

> At the base arrival rate, the `32 / 18 minus 36 / 21` difference in the mean
> replication-level `peak_total_waiting_queue`, measured in travellers.

For each replication:

```text
Q_total(t) = Q_security(t) + Q_immigration(t)
peak_total_waiting_queue = max_t Q_total(t)
```

The peak is taken over the full-drain run so that a downstream Immigration
queue forming after the arrival cutoff is not hidden. Time-weighted mean
queues remain restricted to the fixed `[0, 300)` arrival window so their
denominator is comparable across scenarios.

Queue intervals are reconstructed from the immutable traveller ledger:

```text
Security waiting:    [security_queue_join, security_start)
Immigration waiting: [immigration_queue_join, immigration_start)
```

Zero-duration waits do not enter a queue. At equal timestamps, interval ends
are processed before interval starts. This prevents an artificial one-person
spike. The total peak is reconstructed simultaneously; it is not the sum of
two stage peaks that may occur at different times.

## Secondary analysis

Supporting metrics are:

- peak Security and Immigration waiting queues;
- time-weighted mean Security, Immigration, and total waiting queues over the
  300-second arrival window;
- stage queue counts and total backlog at arrival cutoff;
- Security, Immigration, and total queue-wait P95;
- completions at cutoff and cohort clear time after cutoff;
- arrival-window utilization and nominal offered load as explanatory
  diagnostics.

The Security-only, Immigration-only, Reference, and joint `32 / 18` arms also
form a two-by-two factorial mechanism check. Main effects and their interaction
may be reported as supporting analyses. Low/high arrival levels and the severe
arm are descriptive robustness evidence, not additional confirmatory claims.

## Replications, CRN, and validation

The new experiment runs `4 arms × 3 rates × 50 replications = 600` serial
runs. It does not add runs after seeing the outcome.

For every arrival-level and replication pair, Part 2 copies the exact Part 1
arrival, service, routing, and tie seed tuple. A common seed is only an
alignment intention. Paired Student-t intervals are permitted only after a
fresh validation confirms:

- exact analytical coverage and no duplicate run keys;
- identical Reference and reduction seed tuples within each pairing group;
- identical traveller identifiers and arrival times;
- identical service demands and branch-invariant random draws; and
- conservation, zero rejection/drop, and full drain.

If that gate does not pass, contrasts fall back to independent Welch
intervals. Reference artifacts remain read-only and their recorded hashes
must match before reuse.

## Executed results

The registered experiment completed all `600 / 600` new runs. The
consolidator then added the `150` immutable Reference runs, giving exactly
`750` analytical replications and `317,195` traveller records. Coverage,
configuration lineage, conservation, zero rejection/drop, full drain, seed
alignment, traveller alignment, and all branch-invariant draw checks passed.
The CRN audit compared `253,756` matched traveller pairs and `1,522,536`
draw values, so the pre-specified paired Student-t contrasts were authorised.

Mean replication-level simultaneous peak total waiting queues were:

| Capacity S / I | Low `0.945/s` | Base `1.364/s` | High `1.906/s` |
|---|---:|---:|---:|
| Reference `36 / 21` | `1.20` | `9.34` | `89.74` |
| Security reduction `32 / 21` | `1.40` | `14.68` | `131.46` |
| Immigration reduction `36 / 18` | `3.80` | `19.60` | `150.74` |
| Joint reduction `32 / 18` | `3.64` | `19.44` | `154.74` |
| Severe stress `30 / 17` | `4.56` | `30.76` | `177.58` |

The registered primary result is:

> At the base arrival-rate input, `32 / 18 minus 36 / 21` increased the mean
> replication-level simultaneous peak total waiting queue by `10.10`
> travellers (paired 95% CI `8.23` to `11.97`, `n = 50`).

Supporting base-rate results show the operational shape of that change:

| Capacity S / I | Mean total waiting queue | Total queue-wait P95 | Cutoff backlog | Clear time after cutoff |
|---|---:|---:|---:|---:|
| `36 / 21` | `1.11` | `3.93 s` | `50.66` | `35.36 s` |
| `32 / 21` | `2.98` | `7.09 s` | `53.40` | `37.85 s` |
| `36 / 18` | `6.00` | `12.25 s` | `58.96` | `43.54 s` |
| `32 / 18` | `6.38` | `12.32 s` | `59.12` | `43.59 s` |
| `30 / 17` | `12.23` | `21.08 s` | `70.94` | `53.92 s` |

At the base rate, the Immigration-only reduction increased the peak total
waiting queue by `10.26` travellers (`8.37` to `12.15`), compared with `5.34`
(`4.40` to `6.28`) for the Security-only reduction. This identifies
Immigration as the stronger near-saturation constraint under the registered
service assumptions. The joint peak is not the arithmetic sum of the two
stage effects: reducing upstream Security capacity also meters flow into
Immigration, while the simultaneous peak depends on when the two stage queues
overlap. Mean queue, P95 wait, backlog, and clear time are therefore reported
alongside the peak rather than treating one maximum as the whole result.

The arrival-rate boundary analysis confirms the nonlinear regime change. At
the low input, the joint-reduction peak increase was `2.44` travellers
(`2.20` to `2.68`). At the high input, the Reference was already overloaded
under the registered assumptions and the same reduction increased the peak by
`65.00` travellers (`64.27` to `65.73`). The severe `30 / 17` arm increased
the base-rate peak by `21.42` (`18.28` to `24.56`); it remains a stress
boundary, not a proposed staffing level.

Auditable outputs are in
[`results/analysis/capacity_availability`](../results/analysis/capacity_availability/README.md).
The primary machine-readable result is
[`primary_result.json`](../results/analysis/capacity_availability/primary_result.json),
and the explicit pairing gate is
[`crn_alignment.json`](../results/analysis/capacity_availability/crn_alignment.json).

## Claim boundary

Permitted statement:

> Under the registered fixed-service-time, pooled-FCFS, empty-start,
> 300-second arrival-window, and full-drain assumptions, reducing concurrently
> available service positions changed the simulated queue, waiting, backlog,
> and recovery measures by the reported amounts.

Not permitted:

- `36 / 21` is the observed or optimal HTX roster;
- one model resource equals one total employee;
- the reduction arms estimate real absenteeism, shift, or break patterns;
- low/base/high are calibrated time-of-day profiles;
- `30 / 17` is a recommended or observed operating condition; or
- the model provides a site forecast or minimum safe staffing level.

The relevant frozen sources are:

- [`capacity_availability_study.json`](../config/capacity_availability_study.json)
- [`capacity_availability_scenarios.csv`](../config/capacity_availability_scenarios.csv)
- [`capacity_availability_seed_manifest.csv`](../config/capacity_availability_seed_manifest.csv)
- [`capacity_availability_scenario_provenance.csv`](../config/capacity_availability_scenario_provenance.csv)
