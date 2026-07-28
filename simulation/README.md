# Simulation implementation

## Selected primary engine

AnyLogic PLE 8.9.9 for Windows x64 is the selected primary engine. The
installed build is `8.9.9.202607020720` with its bundled Eclipse Adoptium Java
17.0.9. The synthetic GUI execution/export/seed/reproducibility gate and the
single-file ALP `-r` launch path passed on 2026-07-27.

The official installer is available from:

<https://www.anylogic.com/files/anylogic-ple-8.9.9.x86_64.exe>

AnyLogic PLE is used solely as a personal, non-production skills
demonstration. It remains governed by AnyLogic's software license agreement;
this repository does not grant operational, commercial, or research reuse
rights for the engine or model.

## Model artifacts

- The editable source is
  `anylogic/HTXCheckpointSimulation/HTXCheckpointSimulation.alpx`.
- The adjacent `anylogic/HTXCheckpointSimulation/_alp/` directory contains the
  split model definition and is required. The `.alpx` file is not
  self-contained.
- `anylogic/HTXCheckpointSimulationCLI/HTXCheckpointSimulationCLI.alp` is a
  synchronized single-file copy used to test the documented `-r` launch path.
  It is not a standalone application.
- The split source also contains `CheckpointModel`, `CheckpointTraveller`, and
  the `TwoStageDeterministic` experiment. They isolate the verified
  Security-to-Immigration mechanism from the original technical gate.
- The split source contains a separate `HppArrivalModel` and
  `HppArrivalVerification` experiment. Its Source-to-Sink scope verifies only
  the local-window arrival-demand mechanism; it is not an operational
  checkpoint baseline.
- `OperationalCheckpointModel` and `OperationalTraveller` implement the Task 3
  pooled-FCFS assumption sandbox.
- `OperationalInteractive` provides the exploratory four-zone 2D view and five
  bounded pre-run inputs. `OperationalPilot` and
  `CapacityRobustnessConfirmatory` provide the reportable replicated evidence.

The ALPX project is the source of truth. Regenerate the ALP copy through
`File -> Save As`, clear `Use multi-part ALP format`, and repeat the launch and
hash checks whenever the source model changes.

## Technical gate — PASS

The synthetic gate uses a native Process Modeling Library flow:

```text
Source -> Queue -> Delay -> Sink
```

| Gate condition | Evidence | Status |
|---|---|---|
| Two input samples × three stochastic replications | 6 manifest and summary rows | PASS |
| Explicit scenario/input/replication/seed lineage | validator checks every exported row | PASS |
| Fixed-schema entity and replication CSV output | 72 entity rows plus two run tables | PASS |
| Same manifest reproduces identical output | second GUI run is byte-identical | PASS |
| Different replication IDs change stochastic draws | three distinct fingerprints per input sample | PASS |
| Serial export is race-free | parallel evaluations disabled; no duplicate rows or headers | PASS |
| GUI source-model path | `.alpx` `GatePV2x3` auto-start; 6 runs / 72 entities | PASS |
| Single-file command-line GUI launch path | Gate and two-stage reach `Finished` without Play | PASS |

The implementation differs by experiment type. AnyLogic PLE 8.9.9 does not
offer the native `Skip experiment screen and run model` option for a Parameter
Variation experiment. `GatePV2x3` therefore uses a pinned GUI-only adapter: a
one-shot `javax.swing.Timer` waits 300 ms for the window to initialize, stops
itself, and calls the documented
[`GatePV2x3.this.run()` API](https://anylogic.help/anylogic/experiments/parameter-variation.html)
once. `TwoStageDeterministic` is a Simulation experiment and uses its native
initial-screen bypass. Both auto-execute to `Finished`, but these remain
visible command-line GUI launch paths—not headless, standalone, or native
Parameter Variation skip-screen support. The adapter did not alter simulation
outputs: the gate validator returned `PASS` for all 6 runs and 72 entities, and
all three CSV files remained byte-identical to the reference run.

This gate proves experiment orchestration, CSV export, seed lineage, distinct
replications, and deterministic reruns. The separate deterministic experiment
verifies the basic Security-to-Immigration flow. The operational model adds
registered capacity, demand, service-context, technology-multiplier, and
counter-held risk-proxy scenarios, a four-zone interactive view, a post-run
dashboard, and a frozen confirmatory capacity study. Genuinely separate lane
queues and site calibration remain outside v1. Pilot CRN alignment remains
untested; the later confirmatory study has its own verified CRN gate.

## Deterministic two-stage mechanism — PASS

`TwoStageDeterministic` uses a genuine finite-resource DES:

```text
travellerSource
  -> securityService
  -> immigrationService
  -> checkpointSink
```

Both stages have one finite resource. The deliberately small exact oracle uses
arrivals `0, 0.5, 1.0, 1.5, 2.5, 3.5`, Security demand `2` seconds,
Immigration demand `3` seconds, and a live cutoff event at `6.5` seconds.

Those values are now explicit `CheckpointModel` parameters in both the split
ALPX source and single-file ALP copy. The Source, cutoff Event, ResourcePools,
Service queue capacities, and traveller service-demand assignment reference
the parameters; traveller demand fields have no numeric fallback. Static
contract/structure tests pass. The post-refactor split ALPX and single-file
ALP GUI runs both reached `Finished`; all three outputs were byte-identical to
the reference in both runs.

Observed and independently validated:

| Check | Expected and observed |
|---|---:|
| Completed at cutoff | 1 |
| Security queue / in service | 2 / 1 |
| Immigration queue / in service | 1 / 1 |
| WIP at cutoff | 5 |
| Exit times | 5, 8, 11, 14, 17, 20 |
| Drain end / clear after cutoff | 20 / 13.5 seconds |

Run the experiment from the split project, then validate:

```powershell
.\.venv\Scripts\python.exe -m src.analysis.validate_anylogic_two_stage
```

The three outputs are written only to
`results/raw/anylogic_two_stage_verification/`. See
`../docs/anylogic_two_stage_verification.md` for recorded evidence and claim
limits.

## HPP arrival-only demand mechanism - PASS

`HppArrivalVerification` deliberately excludes service, resources, and queues:

```text
travellerSource (Source, RATE) -> checkpointSink (Sink)
```

It implements the `LOCAL_WINDOW_HPP_STATIONARY_INDEPENDENT` assumption with
lambda `1.364213` travellers/second, cutoff `T=24.922788889` seconds, and
expected count `lambda*T=33.999992599`. Arrivals are admitted on the half-open
interval `[0, T)`. The model does not force the accepted Task 1 aggregate of
34 as a fixed arrival count.

The verified AnyLogic seed `2026072710` realised 32 arrivals. The Source, Sink,
manifest, summary, and 32-row ledger all agree. The `49000` PLE
generated-arrival guard was not reached. A second split-project run and a run
from the synchronized single-file ALP both reproduced all three output files
byte for byte:

| Output | SHA-256 |
|---|---|
| `arrival_ledger.csv` | `0abc5e8e46bb7bab06b37fc2bd785b7822ee864987144c83e115b4bb46319418` |
| `run_manifest.csv` | `d3215ccd4e989051457996ba3367dbfe09e7d877e7fe1d61a797ef33b8e01dae` |
| `run_summary.csv` | `086ec4be69587686dd48a3fdc3d92658ccca823d430b48edb405996a4da61cdc` |

Run `HppArrivalVerification` from the split ALPX project, then validate:

```powershell
.\.venv\Scripts\python.exe -m src.analysis.validate_anylogic_hpp_arrival
```

The result is `PASS` for `DEMAND_MECHANISM_VERIFICATION` with readiness scope
`ARRIVAL_ONLY`. `BASELINE_LOCAL_WINDOW_HPP` remains `BLOCKED_INPUTS`: Security
and Immigration service distributions, resource capacities, queue capacities,
and additional-check inputs are not identified by the video. This legacy
demand-only contract row is not the operational pilot contract. The pilot
instead uses separately registered, transparent assumption scenarios in
`../config/operational_scenarios.csv`; their `NOT_CALIBRATED` status must not
be read as filling those evidence gaps. See
`../docs/anylogic_hpp_arrival_verification.md` for full evidence and claim
limits.

## Operational assumption sandbox — PASS

`OperationalCheckpointModel` is a genuine two-stage, finite-resource DES:

```text
HPP travellerSource
  -> pooled FCFS securityService
  -> pooled FCFS immigrationService
  -> checkpointSink
```

Each replication admits arrivals for 300 seconds and then fully drains the
arrival cohort. The v1 queue mechanism is pooled FCFS at both stages. It is the
only implemented queue policy, and no UI offers a queue-policy selector.
`OperationalPilot` executes 15 registered capacity, demand, service-context,
automation-multiplier, and external risk-bound scenarios × 10 independent
replications. The completed batch contains 150/150 validated runs and 61,218
traveller rows.

The strict validator checks exact scenario × replication coverage, canonical
configuration lineage, seed formulas, schemas, event order, counts,
conservation, queue/resource bounds, and full drain. Analysis uses independent
Welch intervals because `crn_alignment_status` is `NOT_TESTED`. The run does
not support paired-CRN precision claims.

### Explore with `OperationalInteractive`

1. Open
   `anylogic/HTXCheckpointSimulation/HTXCheckpointSimulation.alpx`.
2. Run `OperationalInteractive: OperationalCheckpointModel`.
3. Before pressing Run, edit only the five displayed model parameters:
   `demand_multiplier`, `security_capacity`, `immigration_capacity`,
   `automation_uptake`, and `automation_multiplier`.
4. During execution, use AnyLogic's built-in Pause/Resume/Stop controls. Stop
   and reopen the experiment to reset structural inputs.

The 2D presentation follows Arrival → Security → Immigration → Exit. Its live
panel shows admitted/completed progress, Security and Immigration queue and
in-service counts, queue maxima, branch counts, and `run_status`. This run is
labelled exploratory/ad-hoc, uses replication `0`, and writes to a separate
collection. Do not use a single interactive trace for reportable claims;
those come from validated replication outputs.

### Run the reportable pilot

Run the pilot from the split ALPX source:

1. Open
   `anylogic/HTXCheckpointSimulation/HTXCheckpointSimulation.alpx`.
2. Run `OperationalPilot: OperationalCheckpointModel`.
3. Wait for the visible experiment window to show `Finished`.
4. From the repository root, run:

```powershell
.\.venv\Scripts\python.exe -m src.analysis.validate_operational_contract
.\.venv\Scripts\python.exe -m src.analysis.consolidate_operational_results
.\.venv\Scripts\python.exe -m src.analysis.validate_operational_results `
  --require-pilot-coverage
.\.venv\Scripts\python.exe -m src.analysis.analyse_operational_replications
.\.venv\Scripts\python.exe -m src.analysis.build_operational_dashboard
```

The consolidated data are in `../results/raw/operational/`; the validation
report is
[`../results/analysis/operational/validation.json`](../results/analysis/operational/validation.json).
Reviewer-facing outputs are the
[`results summary`](../results/analysis/operational/README.md),
[`scenario estimates`](../results/analysis/operational/scenario_estimates.csv),
[`scenario contrasts`](../results/analysis/operational/scenario_contrasts.csv),
and
[`dashboard`](../results/analysis/operational/operational_dashboard.png).

This is a comparative, not-calibrated pilot. It is not an HTX performance
estimate, production staffing model, or final recommendation. The risk rows
use a deliberately pessimistic counter-held workload proxy and must not be
presented as ICA practice.

### Run the confirmatory capacity study

Open the same split project and run
`CapacityRobustnessConfirmatory: OperationalCheckpointModel`. Its Parameter
Variation window may be blank. A private one-shot timer starts the experiment
automatically after approximately 300 ms, so do not press Play. Parallel
evaluation is disabled: the experiment runs 12 capacity/rate cells × 50
replications = 600 runs serially and must reach `Finished`.

The completed run has exact `600/600` coverage, 253,756 entity records, strict
validation `PASS`, and traveller-level CRN alignment `PASS`. Retained compact
evidence is under `../results/analysis/confirmatory_capacity/`:

- [`audit_manifest.json`](../results/analysis/confirmatory_capacity/audit_manifest.json)
- [`validation.json`](../results/analysis/confirmatory_capacity/validation.json)
- [`crn_alignment.json`](../results/analysis/confirmatory_capacity/crn_alignment.json)
- [`analysis_manifest.json`](../results/analysis/confirmatory_capacity/analysis_manifest.json)
- [`primary_result.json`](../results/analysis/confirmatory_capacity/primary_result.json)
- [`run_manifest.csv`](../results/analysis/confirmatory_capacity/run_manifest.csv)
- [`replication_kpis.csv`](../results/analysis/confirmatory_capacity/replication_kpis.csv)

The CRN gate permits the pre-specified paired analysis within each registered
arrival-rate level. It does not calibrate service times, capacities, arrival
shape, rosters, or costs. The confirmatory finding remains conditional
capacity-mechanism evidence, not a site forecast or staffing recommendation.

## Run and verify

### Split ALPX source

1. Open
   `anylogic/HTXCheckpointSimulation/HTXCheckpointSimulation.alpx`
   in AnyLogic PLE 8.9.9.
2. Run `GatePV2x3`.
3. Its visible experiment window starts automatically; wait for `Finished`.

### Single-file ALP launch

From the repository root:

```powershell
& "C:\Program Files\AnyLogic 8.9 Personal Learning Edition\AnyLogic.exe" `
  -r "$PWD\simulation\anylogic\HTXCheckpointSimulationCLI\HTXCheckpointSimulationCLI.alp" `
  "GatePV2x3"
```

The visible `GatePV2x3` experiment starts automatically through the one-shot
GUI adapter; wait for `Finished`.

Both paths write:

```text
results/raw/anylogic_gate/run_manifest.csv
results/raw/anylogic_gate/entity_log.csv
results/raw/anylogic_gate/run_summary.csv
```

Validate structure, lineage, event order, counts, and stochastic fingerprints:

```powershell
.\.venv\Scripts\python.exe -m src.analysis.validate_anylogic_gate
```

For a deterministic rerun, preserve the first output:

```powershell
$gateReference = Join-Path `
  ([System.IO.Path]::GetTempPath()) "htx-anylogic-gate-reference"
New-Item -ItemType Directory -Path $gateReference -Force | Out-Null
Copy-Item "results\raw\anylogic_gate\*.csv" $gateReference
```

Run the experiment again, then compare every output byte:

```powershell
.\.venv\Scripts\python.exe -m src.analysis.validate_anylogic_gate `
  --reference-dir $gateReference
```

The expected result is `status: PASS`, no errors, and
`reproducibility.byte_identical: true`. The tracked evidence and recorded
hashes are in `../docs/anylogic_gate_verification.md`.

## Open-source fallback

The successful gate did not trigger the fallback. A Python event-driven engine
with a lightweight browser UI remains the contingency if the full model or
delivery path later fails. It must still provide:

- the two-stage Security -> Immigration DES;
- pooled FCFS, with separate queues claimed only if genuinely implemented;
- finite resources, technology mixture, and additional checks;
- reset/re-run controls, a primitive 2D state view, and dashboard;
- identical parameter/scenario keys and output schemas; and
- replicated experiments, verification tests, and result figures.

Fallback is an implementation decision, not a reduction in the research
design.
