# Task 3 selected-cell peak-duration sensitivity design

**Design status:** frozen before execution.

**Accepted-evidence status:** `EVIDENCE_ACCEPTED`; the
`PeakDurationSensitivity` AnyLogic experiment completed `1000/1000`
registered runs, and the fail-closed analyser accepted all validation, CRN,
cross-batch, conservation, full-drain, zero-loss, and computational-guard
gates.

The immutable machine-readable design deliberately remains a pre-run intent
record with `execution_status=NOT_EXECUTED` and `completed_run_count=0`.
Those fields are not retroactively rewritten. Execution status is recorded in
the hash-bound analysis package and in this post-run evidence record.

**Frozen on:** 29 July 2026

**Claim ceiling:** conditional finite-horizon sensitivity under an explicitly
extended stationary Base HPP assumption. This is not a time-of-day model, a
steady-state result, a site forecast, or a staffing recommendation.

## 1. Why this is a separate study

The completed 300-second confirmatory, capacity-availability, and exploratory
response-surface evidence remains immutable. Those studies answer useful
short-window mechanism questions from empty and then fully drain the admitted
cohort.

This independent design asks a different question:

> If the same stationary Base-rate HPP assumption is sustained for longer,
> how do queueing burden and post-cutoff recovery accumulate at four selected
> capacity regimes?

The longer windows therefore do **not** repair or replace the 300-second work.
The design was created after viewing those outcomes and is explicitly
exploratory.

## 2. Frozen inputs and selected cells

The arrival assumption remains `HPP` at
`1.3642132969720073 travellers/second`. Every newly executed cell, including
the new 300-second batch, uses the distinct input identity
`LOCAL_WINDOW_HPP_BASE_STATIONARY_EXTENSION`. The source
`LOCAL_WINDOW_HPP_BASE` supplies the measured short-window rate and registered
seed lineage only; it is not reused as the identity of a 5–120 minute
extrapolation. Security and Immigration retain the fixed mean service
assumptions, pooled FCFS queues, disabled automation/additional checks,
empty-and-idle start, and full drain after the arrival cutoff.

The selected capacity cells are:

| Security | Immigration | Design role |
|---:|---:|---|
| 36 | 21 | reference headroom |
| 30 | 18 | near-critical regime |
| 29 | 17 | joint finite-horizon accumulation regime |
| 28 | 16 | severe finite-horizon stress boundary |

Capacity means concurrently open service positions in the model. None of these
rows is evidence of an observed HTX roster, installed estate, or recommended
headcount.

## 3. Duration grid and run cap

Each capacity cell is independently run at arrival cutoffs of `300`, `900`,
`1800`, `3600`, and `7200` seconds: 5, 15, 30, 60, and 120 minutes.
Every run starts empty, closes arrivals at its own cutoff, and drains the
admitted cohort completely.

The frozen plan is:

- `4 capacity cells x 5 durations = 20 study cells`;
- `50 replications per cell`;
- `1000 proposed AnyLogic runs`;
- no adaptive extension after outcome inspection; and
- parallel evaluations disabled for deterministic artifact ordering.

All `1000/1000` planned runs were subsequently accepted. The pre-run
machine-readable design remains immutable; the accepted run count, raw-tree
digest, validation results, and estimates are recorded separately under
`results/analysis/peak_duration_sensitivity/`.

## 4. Dynamic non-binding guards

A two-hour HPP window can generate more than the former fixed 5,000-traveller
source guard. The source guard and **both** finite queue capacities are
synchronized to

```text
ceil(max(5000, lambda*T + 10*sqrt(lambda*T) + 100))
```

where `lambda` is the frozen Base rate and `T` is the arrival cutoff.

| Cutoff (s) | Arrival guard | Security queue cap | Immigration queue cap |
|---:|---:|---:|---:|
| 300 | 5000 | 5000 | 5000 |
| 900 | 5000 | 5000 | 5000 |
| 1800 | 5000 | 5000 | 5000 |
| 3600 | 5712 | 5712 | 5712 |
| 7200 | 10914 | 10914 | 10914 |

These are computational safety guards, not measured physical queue capacities.
Execution must still fail loudly if any guard binds.

## 5. Seed and configuration lineage

The seed manifest maps the exact 50 `MLE_BASE` tuples from
`confirmatory_seed_manifest.csv` into the distinct
`LOCAL_WINDOW_HPP_BASE_STATIONARY_EXTENSION` input identity. For replication
`r`, every duration/capacity cell receives the same registered
`pairing_group_id`, `master_seed`, `arrival_seed`, `service_seed`,
`routing_seed`, and `tie_seed`. The mapping preserves random-stream lineage
without mislabelling the longer stationary input as an observed local window.

The scenario file retains the existing canonical `SCENARIO_COLUMNS` schema.
Each exact row therefore remains compatible with the established
`scenario_config_sha256` lineage function; the design validator verifies 20
unique canonical hashes.

Seed reuse expresses an alignment intent. Paired contrasts require a later
PASS from seed-tuple, arrival-ledger/prefix, and traveller-level exogenous-draw
checks. Until that gate passes, common random numbers are not claimed as
achieved.

## 6. Registered finite-horizon analysis

The primary evidence views are duration-by-capacity curves
for:

1. total queue wait P95;
2. peak total waiting queue;
3. cutoff backlog; and
4. cohort clear time after cutoff.

Supporting views include mean wait, time-weighted mean queue, stage P95 waits,
and the nearest-rank total-wait P95 among travellers arriving in
`[0.8T,T)`. Queue-growth evidence is reconstructed separately within every
replication: calculate the time-weighted mean total waiting queue over
`[0.5T,0.6T)`, `[0.6T,0.7T)`, `[0.7T,0.8T)`, `[0.8T,0.9T)`, and `[0.9T,T)`,
then fit OLS against the five window midpoint times. Replication-level slopes,
not pooled event rows, receive the 95% Student-t interval.

Where the offered-work utilization proxy is at or above one, a steady-state
service-level interpretation is invalid. Those cells are instead described
through finite-horizon backlog accumulation, late-arrival delay, and recovery
burden. Every estimate must retain a replication-level 95% interval, and
connected plot lines are only visual guides between the five simulated
durations. The reported P95 estimand is the mean of 50 replication-level P95
queue waits, not a P95 pooled across all travellers.

## 7. Accepted execution and result

The analyser accepted:

- `20` study cells x `50` replications = `1000/1000` runs;
- `3,768,780` traveller entity rows and `3,000` raw result files;
- exact same-duration, cross-capacity and nested-duration-prefix CRN gates;
- exact T=300 cross-batch reproduction over `200` runs and `82,488`
  traveller rows;
- zero rejection/drop, exact conservation, full cohort drain, and non-binding
  computational guards.

The main finite-horizon result is a regime change that the 300-second
empty-start surface could not show:

| Capacity S / I | Maximum offered-work `rho` proxy | 5-minute mean P95 wait | 120-minute mean P95 wait | Interpretation inside this sandbox |
|---:|---:|---:|---:|---|
| `36 / 21` | `0.845` | `3.929 s` | `4.472 s` | low, stable finite-horizon queue burden |
| `30 / 18` | `0.992` | `13.556 s` | `55.910 s` | near-critical long transient |
| `29 / 17` | `1.043` | `21.394 s` | `307.148 s` | sustained finite-horizon accumulation |
| `28 / 16` | `1.108` | `35.920 s` | `748.204 s` | stronger sustained accumulation |

The 120-minute mean cutoff waiting queue is `1.40`, `52.58`, `425.92`, and
`973.46` travellers respectively. At `29/17` and `28/16`, no steady-state
SLA is estimated because `rho >= 1`; only terminating-cohort accumulation
and recovery evidence is reported. The `30/18` result shows why `rho < 1`
does not imply a short warm-up: near-critical stochastic systems can retain a
long transient even though the terminating cohort eventually drains.

Accepted visual summaries:

- [`peak_duration_queue_sensitivity.png`](../results/analysis/peak_duration_sensitivity/figures/peak_duration_queue_sensitivity.png)
- [`peak_duration_recovery_diagnostics.png`](../results/analysis/peak_duration_sensitivity/figures/peak_duration_recovery_diagnostics.png)

## 8. Critical boundary: this is not an observed peak

The 24.9-second video supports a directional local-window crossing rate. It
does not establish that the same rate persists for 15, 30, 60, or 120 minutes.
Extending it as a stationary HPP is a transparent stress assumption chosen to
isolate duration effects.

A defensible time-of-day study would require longer timestamped arrival data
covering relevant days and periods, plus a registered piecewise/non-stationary
arrival model. This design must never be described as reconstructing such a
profile.

## 9. Reproduce and validate the frozen design and evidence

```powershell
.\.venv\Scripts\python.exe -m src.analysis.peak_duration_sensitivity_design
.\.venv\Scripts\python.exe -m unittest tests.test_peak_duration_sensitivity_design
.\.venv\Scripts\python.exe -m src.analysis.analyse_peak_duration_sensitivity
.\.venv\Scripts\python.exe -m src.analysis.plot_peak_duration_sensitivity
```

The validator fails closed on the four capacity cells, five cutoffs, guard
formula and computed values, synchronized queue caps, canonical scenario
schema, exact Base seed reuse, run cap, ordering, and `NOT_EXECUTED` status.

The design validator checks the immutable pre-run contract. The analysis
command separately fails closed unless all 1,000 raw runs, event-ledger
reconstruction, CRN gates, T=300 cross-batch reproduction, conservation,
full drain, zero-loss, and computational-guard checks pass. Confidence
intervals quantify Monte Carlo error conditional on the registered model
inputs; they do not include input uncertainty or model-form error.
