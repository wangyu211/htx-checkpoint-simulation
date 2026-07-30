# AnyLogic HPP arrival-only verification

**Status:** `PASS` for the arrival-demand mechanism only  
**Readiness scope:** `ARRIVAL_ONLY`  
**Experiment role:** `DEMAND_MECHANISM_VERIFICATION`  
**Engine:** AnyLogic PLE 8.9.9, build `8.9.9.202607020720`  
**Verified:** 2026-07-27

## Claim boundary

`HppArrivalVerification` verifies that the accepted Task 1 aggregate can drive
an executable homogeneous Poisson process (HPP) arrival mechanism with explicit
lineage, a live cutoff, a fixed seed, count conservation, and reproducible CSV
output. It does not verify an operational checkpoint baseline.

The source configuration remains:

```text
BASELINE_LOCAL_WINDOW_HPP = BLOCKED_INPUTS
```

Security and Immigration service-time distributions, resource capacities,
queue capacities, and additional-check inputs are still missing. No service,
queueing, staffing, routing, utilisation, waiting-time, or policy-performance
claim follows from this arrival-only run.

## Model and assumption

The split ALPX source contains the deliberately narrow flow:

```text
travellerSource (Source, RATE) -> checkpointSink (Sink)
```

The demand parameters are:

| Parameter | Value |
|---|---:|
| Arrival intensity, lambda | 1.364213 travellers/second |
| Exposure and cutoff, T | 24.922788889 seconds |
| Expected count, lambda x T | 33.999992599 |
| AnyLogic arrival seed | 2026072710 |
| Accepted time interval | `[0, T)` |
| PLE generated-arrival guard | 49000 |

`LOCAL_WINDOW_HPP_STATIONARY_INDEPENDENT` is a modelling assumption: arrivals
are treated as stationary and independent within the short observed window.
The video did not establish those stochastic properties and did not provide an
adjudicated 34-event timestamp ledger. Consequently, 34 is the HPP expected
count over this exposure, not a fixed cohort or a target that a single run must
match.

The half-open interval `[0, T)` makes the boundary explicit: an arrival exactly
at the cutoff is excluded. The 49000-arrival guard protects the AnyLogic PLE
execution limit; it was not reached.

## Observed verification run

With seed `2026072710`, the verified split-model run realised 32 arrivals.
Every independent count surface agreed:

| Evidence surface | Count |
|---|---:|
| `arrival_ledger.csv` rows | 32 |
| `run_manifest.csv` realised count | 32 |
| Source count | 32 |
| Sink count | 32 |
| `run_summary.csv` realised count | 32 |

All 32 ledger timestamps are finite, strictly increasing, and inside
`[0, 24.922788889)`. The run closed arrivals at the cutoff, conserved flow
through the Source/Sink demand-only model, and reported `guard_hit=false`.

The experiment was run twice from the split ALPX project. The synchronized
single-file CLI ALP was then run from its final delivery path. Both subsequent
runs produced three CSV files byte-for-byte identical to the preserved split
reference:

| File | SHA-256 |
|---|---|
| `arrival_ledger.csv` | `0abc5e8e46bb7bab06b37fc2bd785b7822ee864987144c83e115b4bb46319418` |
| `run_manifest.csv` | `d3215ccd4e989051457996ba3367dbfe09e7d877e7fe1d61a797ef33b8e01dae` |
| `run_summary.csv` | `086ec4be69587686dd48a3fdc3d92658ccca823d430b48edb405996a4da61cdc` |

These hashes record byte-identical output across the documented local runs
under the same engine build, model, configuration, and seed. They do not
establish cross-version or cross-platform byte stability, show that 32 is the
true or expected traveller count, or imply that a Python generator with the
same integer seed will produce the same ledger.

## Run and validate

Open either the split source or synchronized single-file delivery copy in
AnyLogic PLE 8.9.9:

```text
simulation/anylogic/HTXCheckpointSimulation/HTXCheckpointSimulation.alpx
simulation/anylogic/HTXCheckpointSimulationCLI/HTXCheckpointSimulationCLI.alp
```

Run `HppArrivalVerification`. It writes:

```text
results/raw/anylogic_hpp_arrival_verification/run_manifest.csv
results/raw/anylogic_hpp_arrival_verification/arrival_ledger.csv
results/raw/anylogic_hpp_arrival_verification/run_summary.csv
```

Validate schemas, lineage, parameter values, the half-open time boundary,
count conservation, the PLE guard, and the preserved reference:

```powershell
.\.venv\Scripts\python.exe -m src.analysis.validate_anylogic_hpp_arrival `
  --reference-dir results\intermediate\anylogic_hpp_arrival_verification\reference_split_run
```

The recorded result is `status: PASS`,
`reproducibility.byte_identical: true`, and no validation errors.

## Use in later policy experiments

Once transparent service/resource assumptions are approved, scenario
comparisons should replay the same accepted arrival ledger across policy
alternatives. Holding demand fixed separates policy effects from arrival
noise. Independent HPP replications may additionally quantify demand
uncertainty, but they answer a different question and must retain explicit
seed and configuration lineage.
