# Task 3 configuration contract

**Status:** operational assumption contract, 15 × 10 pilot, and 12 × 50
confirmatory capacity study verified; not calibrated

**Version:** 2.1, 2026-07-28

## Outcome

Task 3 deliberately keeps verification fixtures, measured demand evidence,
and operational assumptions in separate contracts:

| Contract | Purpose | Current status |
|---|---|---|
| `config/model_run_configs.csv` / `VERIFY_TWO_STAGE_A` | Exact six-person, 2 s/3 s, one-server-per-stage regression oracle | `READY` and verified |
| `config/model_run_configs.csv` / `BASELINE_LOCAL_WINDOW_HPP` | Demand-only row carrying the accepted Task 1 rate | `BLOCKED_INPUTS` by design |
| `config/operational_scenarios.csv` | Registered comparative assumption sandbox with explicit service, capacity, technology, and risk sensitivities | `READY_ASSUMPTION_SANDBOX`; 15 × 10 pilot complete |
| `config/confirmatory_capacity_study.json` / `config/confirmatory_seed_manifest.csv` | Frozen 12-cell capacity/rate grid, precision cap, and 150 within-rate seed groups | `EXECUTED`; 12 × 50 runs complete |

The operational and confirmatory rows do not “unblock” or calibrate the
demand-only row. They create transparent conditional studies whose non-video
inputs are supported by named context, derivation, or explicit sensitivity
assumptions in `config/scenario_provenance.csv` and
`config/provenance_registry.csv`.

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

## Interactive execution contract

`OperationalInteractive` is an exploratory/ad-hoc Simulation experiment, not
a report-producing scenario batch. Its 2D presentation follows four visible
zones:

```text
Arrival -> Security -> Immigration -> Exit
```

The live panel exposes admitted/completed progress, the queue and in-service
count at Security and Immigration, queue maxima, technology/additional-check
counts, and run status. Exactly five model parameters are genuine pre-run
controls:

| Parameter | Interactive domain |
|---|---:|
| `demand_multiplier` | `0.5` to `2.0` |
| `security_capacity` | integer `1` to `200` |
| `immigration_capacity` | integer `1` to `200` |
| `automation_uptake` | `0.0` to `1.0` |
| `automation_multiplier` | strictly between `0.0` and `1.0` when uptake is positive; reset to `1.0` when uptake is zero |

All other mechanism and lineage fields are fixed by the experiment. Pooled
FCFS is the only queue policy implemented in this AnyLogic experiment, so the
UI deliberately has no queue-policy selector. The distinct separate-lane
counterfactual is an offline exact-gated replay, not an interactive control.
Inputs are set before Run; structural changes are reset
by stopping and reopening the experiment. Replication `0` output is labelled
`INTERACTIVE_EXPLORATORY` and kept outside reportable replicated collections.
Reportable claims must come from validated replication outputs, not an
interactive trace.

## Fail-closed validation

Run both configuration validators from the repository root:

```powershell
.\.venv\Scripts\python.exe -m src.analysis.validate_model_run_configs
.\.venv\Scripts\python.exe -m src.analysis.validate_operational_contract
```

The legacy validator checks the oracle/demand-only configuration states. The
operational validator checks the exact 15-row schema, scenario/provenance
joins, numeric and enum domains, reference consistency, evidence boundaries,
and a canonical configuration hash. Their local working reports are
reproducibility artifacts rather than retained reviewer evidence.

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

- [`strict validation report`](../results/analysis/operational/validation.json)
- [`analysis manifest`](../results/analysis/operational/analysis_manifest.json)
- [`scenario estimates`](../results/analysis/operational/scenario_estimates.csv)
- [`scenario contrasts`](../results/analysis/operational/scenario_contrasts.csv)
- [`dashboard and interpretation`](../results/analysis/operational/README.md)

Scenario-specific seeds are valid and distinct, but traveller-level
common-random-number alignment is `NOT_TESTED`. Analysis therefore uses
independent Welch intervals rather than paired contrasts.

## Confirmatory capacity evidence

`CapacityRobustnessConfirmatory` crosses four capacity alternatives
(reference, Security `+4`, Immigration `+3`, and joint `+4/+3`) with three
registered HPP arrival-rate levels (exact-count 95% low, point estimate, and
exact-count 95% high). It is fixed at:

```text
12 cells × 50 replications = 600 runs
```

The visible Parameter Variation experiment uses a private one-shot timer to
start automatically after the window initializes. Parallel evaluations are
disabled, so all 600 runs execute serially. The completed compact evidence
package records:

- `600/600` exact run coverage and strict result validation `PASS`;
- `253,756` entity rows;
- CRN alignment `PASS` across all 150 within-rate replication groups; and
- paired Student-t analysis only after that traveller-level alignment gate
  passed.

Retained evidence is under
`results/analysis/confirmatory_capacity/`:

- [`audit_manifest.json`](../results/analysis/confirmatory_capacity/audit_manifest.json)
- [`validation.json`](../results/analysis/confirmatory_capacity/validation.json)
- [`crn_alignment.json`](../results/analysis/confirmatory_capacity/crn_alignment.json)
- [`analysis_manifest.json`](../results/analysis/confirmatory_capacity/analysis_manifest.json)
- [`primary_result.json`](../results/analysis/confirmatory_capacity/primary_result.json)
- [`run_manifest.csv`](../results/analysis/confirmatory_capacity/run_manifest.csv)
- [`replication_kpis.csv`](../results/analysis/confirmatory_capacity/replication_kpis.csv)

The confirmatory `PASS` is conditional capacity-mechanism evidence under the
registered pooled-FCFS, fixed-service, empty-start, and full-drain assumptions.
It does not calibrate an HTX baseline or justify an operational staffing
decision.

## Claim and delivery boundary

This evidence supports an executable, reproducible comparative pilot under
registered assumptions. It does not establish operational validity,
calibration, an HTX service level, a site forecast, an economic optimum, or a
final staffing recommendation.

The supported workflow remains a visible AnyLogic PLE run; no headless or
standalone execution is claimed. The four-zone interactive presentation and
five bounded pre-run controls are implemented, as is the frozen confirmatory
replication design and its CRN gate. Genuinely separate queue banks, field
calibration, and a production control interface remain outside v1.

The configuration boundary is engine-independent even though AnyLogic is the
selected primary engine.
