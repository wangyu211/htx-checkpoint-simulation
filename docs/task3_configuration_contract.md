# Task 3 configuration contract

**Status:** operational assumption contract and 15 × 10 pilot verified; not
calibrated

**Version:** 2.0, 2026-07-28

## Outcome

Task 3 deliberately keeps verification fixtures, measured demand evidence,
and operational assumptions in separate contracts:

| Contract | Purpose | Current status |
|---|---|---|
| `config/model_run_configs.csv` / `VERIFY_TWO_STAGE_A` | Exact six-person, 2 s/3 s, one-server-per-stage regression oracle | `READY` and verified |
| `config/model_run_configs.csv` / `BASELINE_LOCAL_WINDOW_HPP` | Demand-only row carrying the accepted Task 1 rate | `BLOCKED_INPUTS` by design |
| `config/operational_scenarios.csv` | Registered comparative assumption sandbox with explicit service, capacity, technology, and risk sensitivities | `READY_ASSUMPTION_SANDBOX`; 15 × 10 pilot complete |

The last row does not “unblock” or calibrate the demand-only row. It creates a
different, transparent what-if study whose non-video inputs are supported by
named context, derivation, or explicit sensitivity assumptions in
`config/scenario_provenance.csv` and `config/provenance_registry.csv`.

## Accepted demand boundary

The operational contract references `task1_final_aggregate` and uses:

- image-space arrival direction: right to left;
- accepted count: 34;
- exposure: 24.922788889 seconds; and
- observed-window intensity: 1.364213 travellers/second.

Because no signed 34-event timestamp ledger exists, the model uses an HPP
(homogeneous Poisson process) assumption. Stationary independent arrivals are
therefore an explicit modelling choice, not a video finding. The operational
pilot uses a 300-second arrival window and then fully drains every admitted
traveller. It does not impose 34 as a fixed cohort and does not claim that the
short clip establishes long-run demand.

## Registered operational v1

`OperationalCheckpointModel` implements:

```text
HPP arrivals
  -> pooled FCFS Security with finite resources
  -> pooled FCFS Immigration with finite resources
  -> exit
```

The reference assumption sandbox declares:

- Security: 36 resources, fixed 21.818181818-second demand;
- Immigration: 21 resources, fixed 13-second demand;
- finite 5,000-traveller queue guards at both stages;
- pooled FCFS at both stages;
- no automation or additional checks in the reference;
- 300 seconds of arrivals followed by full drain; and
- 10 pilot replications with master-seed lineage.

The 15 registered scenarios vary capacity, demand, named service-time context,
effective automation uptake/multiplier, and an external counter-held risk
proxy. They do not implement genuinely separate per-counter queues. The
2%/900-second and 2%/7,200-second risk rows are deliberately pessimistic
external boundary tests and must not be described as ICA practice.

All operational rows are labelled `NOT_CALIBRATED` and
`COMPARATIVE_WHAT_IF_ONLY`.

## Fail-closed validation

Run both configuration validators from the repository root:

```powershell
.\.venv\Scripts\python.exe -m src.analysis.validate_model_run_configs
.\.venv\Scripts\python.exe -m src.analysis.validate_operational_contract
```

The legacy validator checks the oracle/demand-only configuration states. The
operational validator checks the exact 15-row schema, scenario/provenance
joins, numeric and enum domains, reference consistency, evidence boundaries,
and a canonical configuration hash. It writes:

```text
results/intermediate/model_configuration/validation.json
results/intermediate/operational_contract/validation.json
```

The operational AnyLogic generator fails closed if the registered rows,
ordering, IDs, or canonical hash differ from the embedded experiment
contract.

## Verification slices retained

`TwoStageDeterministic` remains the exact service/queue/cutoff/full-drain
regression oracle. Its values are not eligible for operational performance
claims.

`HppArrivalVerification` remains the demand-only mechanism check with
lambda `1.364213`/second, cutoff `24.922788889` seconds, seed `2026072710`, and
a half-open `[0,T)` boundary. Its verified fixed-seed run realised 32 arrivals
and reproduced three output files byte for byte. This result does not identify
service, staffing, queue, technology, or exception parameters.

## Operational pilot evidence

Run `OperationalPilot: OperationalCheckpointModel` in the split AnyLogic PLE
project and wait for `Finished`. The visible Parameter Variation experiment
executes 15 scenarios × 10 replications serially and writes run folders under:

```text
results/raw/anylogic_operational_batch/
```

Then consolidate, validate exact coverage, analyse, and build the dashboard:

```powershell
.\.venv\Scripts\python.exe -m src.analysis.consolidate_operational_results
.\.venv\Scripts\python.exe -m src.analysis.validate_operational_results `
  --require-pilot-coverage
.\.venv\Scripts\python.exe -m src.analysis.analyse_operational_replications
.\.venv\Scripts\python.exe -m src.analysis.build_operational_dashboard
```

Recorded outcome:

- 150/150 scenario-replication runs;
- 61,218 traveller rows;
- exact registered coverage with no duplicate or missing keys;
- schema, lineage, seed, event order, conservation, resource/queue, and
  full-drain validation: `PASS`; and
- replication-level estimates and independent scenario contrasts produced.

Evidence links:

- [`strict validation report`](../results/intermediate/operational_results/validation.json)
- [`analysis manifest`](../results/analysis/operational/analysis_manifest.json)
- [`scenario estimates`](../results/analysis/operational/scenario_estimates.csv)
- [`scenario contrasts`](../results/analysis/operational/scenario_contrasts.csv)
- [`dashboard and interpretation`](../results/analysis/operational/README.md)

Scenario-specific seeds are valid and distinct, but traveller-level
common-random-number alignment is `NOT_TESTED`. Analysis therefore uses
independent Welch intervals rather than paired contrasts.

## Claim and delivery boundary

This evidence supports an executable, reproducible comparative pilot under
registered assumptions. It does not establish operational validity,
calibration, an HTX service level, a site forecast, an economic optimum, or a
final staffing recommendation.

The current GUI is minimal and the supported workflow remains a visible
AnyLogic PLE run. No headless or standalone execution is claimed. Genuinely
separate queue banks, a polished interactive layout, field calibration,
confirmatory replication sizing, and CRN alignment remain future extensions.

The configuration boundary is engine-independent even though AnyLogic is the
selected primary engine.
