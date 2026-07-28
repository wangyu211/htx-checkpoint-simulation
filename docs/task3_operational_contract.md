# Task 3 operational assumption-sandbox contract

**Contract:** `TASK3_OPERATIONAL_ASSUMPTION_SANDBOX_V1`

**Model:** `TASK3_OPERATIONAL_POOLED_V1`

**Recorded execution:** 15 scenarios × 10 pilot replications; 12 capacity/rate
cells × 50 confirmatory replications

**Claim ceiling:** comparative what-if evidence only; not a calibrated HTX
baseline, site forecast, digital twin, or staffing recommendation

## Purpose

The assessment video identifies a short-window directional arrival aggregate.
It does not identify local service-time distributions, open-resource rosters,
queue capacities, automation eligibility, or exception workload. Task 3
therefore uses a named, executable **reference assumption sandbox** plus
controlled sensitivity scenarios. Every executable input has field-level
provenance in:

- [`operational_scenarios.csv`](../config/operational_scenarios.csv);
- [`provenance_registry.csv`](../config/provenance_registry.csv); and
- [`scenario_provenance.csv`](../config/scenario_provenance.csv).

The contract validator rejects incomplete provenance, non-canonical hashes,
unnamed blends of official contexts, changes outside each declared scenario
family, and any executable v1 row that claims an unimplemented separate-queue
mechanism.

## Executable v1 boundary

```text
HPP arrivals
  -> pooled FCFS Security
  -> pooled FCFS Immigration
  -> optional counter-held additional work
  -> Exit
```

Both processing stages use finite homogeneous resources. Arrivals are admitted
on `[0, 300)` seconds, then the Source closes and the complete admitted cohort
drains. A run cannot pass if a traveller is dropped, rejected, silently
truncated, or left in the system.

Pooled FCFS is the only implemented queue policy. V1 does **not** implement
counter-specific Immigration queues. A genuine
separate-queue comparison requires replicated queue objects, an explicit lane
assignment/tie rule, and counter-specific event logging. It remains a future
mechanism rather than a scenario-label change, and the interactive experiment
does not offer a misleading queue-policy selector.

Additional checks use a `COUNTER_HELD_RISK_REFERRAL_PROXY`: selected
travellers retain an Immigration resource for the declared extra work. This
deliberately pessimistic boundary does not assert ICA practice or invent
unobserved secondary capacity.

## Interactive execution surface

`OperationalInteractive` is a visible 2D exploratory/ad-hoc run. Its four
zones make the implemented process legible:

```text
Arrival -> Security -> Immigration -> Exit
```

The live presentation shows admitted and completed counts, Security and
Immigration queue and in-service counts, queue maxima, branch counts, and
`run_status`. Its complete editable pre-run parameter surface is exactly:

1. `demand_multiplier`;
2. `security_capacity`;
3. `immigration_capacity`;
4. `automation_uptake`; and
5. `automation_multiplier`.

All other process, queue, cutoff, service, and seed fields remain fixed.
Inputs are set before Run, and AnyLogic's built-in Pause/Resume/Stop controls
govern execution. The generated interactive scenario is labelled
`INTERACTIVE_EXPLORATORY`, uses replication `0`, and exports to a separate
ad-hoc collection. It is for mechanism exploration and demonstration.
Reportable claims come only from validated replicated experiments.

## Reference assumptions

| Input | Reference value | Evidence/use class |
|---|---:|---|
| Arrival rate | `1.364213/s` | accepted local 34/24.922788889 short-window aggregate |
| Arrival family | HPP | stationary-independent modelling assumption |
| Arrival window | `300 s`, then full drain | transparent pilot horizon |
| Security service | fixed `21.818181818 s` | reciprocal of external 165 pax/hour/lane bound |
| Immigration service | fixed `13 s` | named Singapore land bus-hall passport context |
| Security capacity | `36` | `ceil(lambda × service / 0.85)` assumption |
| Immigration capacity | `21` | `ceil(lambda × service / 0.85)` assumption |
| Queue guards | `5000` at each stage | explicit non-loss implementation guard |
| Automation | disabled | enabled only in named sensitivity rows |
| Additional check | disabled | enabled only in external risk-bound rows |
| Pilot replications | `10` | pipeline/variance pilot, not confirmatory precision |

Fixed service values are deliberate: a published mean does not identify a
Normal, Lognormal, Gamma, or other distribution. Service variability must be
introduced as a named sensitivity rather than inferred.

## Registered scenario families

- **Capacity:** Security `+4`, Immigration `+3`, and the joint change.
- **Demand:** illustrative `0.8×` and `1.2×` multipliers.
- **Service context:** named `10 s`, `13 s`, `24 s`, and `45 s` Singapore
  contexts, kept separate rather than averaged.
- **Automation:** effective uptake `0.5` and `1.0`, tested with declared
  remaining-time multipliers `0.6` and `0.4`.
- **Risk boundary:** external `2% / 900 s` and `2% / 7200 s` counter-held
  stresses; neither is an ICA parameter estimate.

## Result and statistical contracts

[`result_schema_registry.csv`](../config/result_schema_registry.csv) freezes:

1. `run_manifest.csv` — configuration/hash, scenario/replication lineage,
   random streams, cutoff/drain, and claim status;
2. `entity_log.csv` — exogenous draws, service demand, full event timestamps,
   branch flags, and resource IDs;
3. `replication_kpis.csv` — one statistical observation per replication;
4. `scenario_estimates.csv` — scenario means and 95% Student-t intervals; and
5. `scenario_contrasts.csv` — scenario-minus-reference intervals.

The primary estimand is the mean of the 10 replication-level
`total_queue_wait_p95_seconds` values. The 61,218 traveller rows are not
treated as independent statistical replications.

Paired analysis is prohibited unless a separate alignment report verifies
traveller IDs and branch-invariant draws. Pilot `crn_alignment_status` is
`NOT_TESTED`, so its recorded contrasts use independent Welch intervals. The
frozen confirmatory study passed the full alignment gate and therefore uses
paired Student-t inference for its within-rate contrasts.

## Generate, run, and verify

Generate the operational objects from the registered contract:

```powershell
.\.venv\Scripts\python.exe -m src.analysis.validate_operational_contract
.\.venv\Scripts\python.exe scripts\generate_operational_anylogic.py
.\.venv\Scripts\python.exe -m unittest tests.test_anylogic_operational
```

Open the split AnyLogic project, run
`OperationalPilot: OperationalCheckpointModel`, and wait for the visible
window to show `Finished`. A blank Parameter Variation presentation is
expected; the experiment auto-starts and exports the evidence tables.

Then run:

```powershell
.\.venv\Scripts\python.exe -m src.analysis.consolidate_operational_results
.\.venv\Scripts\python.exe -m src.analysis.validate_operational_results `
  --require-pilot-coverage
.\.venv\Scripts\python.exe -m src.analysis.analyse_operational_replications
.\.venv\Scripts\python.exe -m src.analysis.build_operational_dashboard
```

For the frozen capacity study, run
`CapacityRobustnessConfirmatory: OperationalCheckpointModel`. Its Parameter
Variation window can be blank; a private one-shot timer starts it
automatically, so do not press Play. Parallel evaluation is disabled. The
experiment runs `12 × 50 = 600` replications serially and must reach
`Finished`.

## Recorded evidence

The completed run contains:

- 150/150 registered scenario-replication keys;
- 61,218 traveller records;
- zero dropped or rejected travellers;
- exact schema, hash, lineage, seed, event-order, conservation, and full-drain
  validation with no errors;
- finite-resource operation enforced by AnyLogic's Process Modeling Library;
  an independent per-resource interval-overlap audit has not been performed;
- 165 scenario-estimate rows; and
- 154 exploratory contrast rows.

Evidence:

- [strict validation report](../results/analysis/operational/validation.json)
- [analysis manifest](../results/analysis/operational/analysis_manifest.json)
- [scenario estimates](../results/analysis/operational/scenario_estimates.csv)
- [scenario contrasts](../results/analysis/operational/scenario_contrasts.csv)
- [dashboard and concise interpretation](../results/analysis/operational/README.md)
- [reviewer-facing results report](task3_results.md)

Passing these gates establishes implementation integrity, registered coverage,
and Monte Carlo analysis conditional on the fixed assumptions. It does not
establish input calibration, operational validity, or forecast accuracy.

## Recorded confirmatory evidence

The completed `CapacityRobustnessConfirmatory` study contains:

- `600/600` expected runs with strict validation `PASS`;
- `253,756` entity records;
- exact coverage of four capacity alternatives at three registered arrival
  rates, with 50 replications per cell;
- CRN alignment `PASS` for all 150 within-rate replication groups; and
- conditional paired analysis after the CRN gate passed.

The retained compact package is entirely under
`results/analysis/confirmatory_capacity/`:

- [compact audit manifest](../results/analysis/confirmatory_capacity/audit_manifest.json)
- [strict validation report](../results/analysis/confirmatory_capacity/validation.json)
- [CRN alignment report](../results/analysis/confirmatory_capacity/crn_alignment.json)
- [analysis manifest](../results/analysis/confirmatory_capacity/analysis_manifest.json)
- [primary result](../results/analysis/confirmatory_capacity/primary_result.json)
- [scenario estimates](../results/analysis/confirmatory_capacity/scenario_estimates.csv)
- [scenario contrasts](../results/analysis/confirmatory_capacity/scenario_contrasts.csv)

The confirmatory result remains conditional capacity-mechanism evidence under
pooled FCFS, fixed service times, empty/idle start, the 300-second arrival
window, and full drain. Neither the execution count nor CRN `PASS` supplies
missing field calibration, cost evidence, or roster feasibility.
