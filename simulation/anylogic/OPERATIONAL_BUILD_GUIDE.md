# Task 3 AnyLogic operational build and run guide

**AnyLogic:** Personal Learning Edition 8.9.9

**Authoritative model source:** `simulation/anylogic/HTXCheckpointSimulation/HTXCheckpointSimulation.alpx`

**Generator:** `scripts/generate_operational_anylogic.py`

**Batch design:** 15 registered scenarios × 10 independent replications, run serially

**Claim boundary:** executable and traceable assumption sandbox; **not calibrated
to an HTX site and not an operational forecast**

This guide describes the current generated workflow. Earlier versions of this
document contained a long, manual copy-and-paste build procedure. That
procedure is obsolete and has been removed. Do not hand-enter the generated
parameters, Java actions, experiment mappings, or hashes in AnyLogic.

## 1. Generated model structure

The split AnyLogic project contains:

| Object | Purpose |
|---|---|
| `OperationalTraveller` | Per-traveller lineage, random draws, timestamps, routing flags, and resource IDs |
| `OperationalCheckpointModel` | Pooled FCFS Security and Immigration process model |
| `OperationalInteractive` | One canonical reference smoke run |
| `OperationalPilot` | Registry-driven Parameter Variation experiment |

The process is:

```text
HPP arrivals
    -> pooled FCFS Security [36 resources in the reference]
    -> pooled FCFS Immigration [21 resources in the reference]
    -> exit
```

The arrival window is `[0, 300)` seconds in the reference. At 300 seconds the
Source closes, but the model continues until the admitted cohort drains
completely. A replication is complete only when all conservation checks pass,
both queues and both in-service counters are zero, and no traveller was
rejected or dropped.

Primary service times are fixed in v1 because the evidence supports context
means but not an identified distributional shape. The additional-check
scenario is a deliberately pessimistic, counter-held risk proxy. It is not a
claim about ICA operating practice.

## 2. Sources of truth

Do not maintain a second parameter table in AnyLogic. These repository files
control the generated model:

| File | Contract |
|---|---|
| `config/operational_scenarios.csv` | Exact 15-scenario registry and pilot replication count |
| `config/provenance_registry.csv` | Evidence and transparent-assumption registry |
| `config/scenario_provenance.csv` | Scenario-field-to-provenance mappings |
| `config/result_schema_registry.csv` | Exact output schemas |
| `src/analysis/validate_operational_contract.py` | Canonicalization, hashes, and fail-closed input checks |
| `scripts/generate_operational_anylogic.py` | Generated AnyLogic objects and experiments |

`config_sha256` is **not** the hash of a visually copied raw CSV line. It is
the SHA-256 digest of the canonical UTF-8 representation produced by
`scenario_config_sha256()` over the exact registered columns. Always obtain
and verify hashes through the validator and generator. The current reference
hash is:

```text
166e6c918cff63041b08f31ff5c17fbea49008b8cdd3047b1082b326faae3460
```

The generated output selector is `output_collection_id`, not
`output_root_directory`:

| Experiment | `output_collection_id` | Raw output root |
|---|---|---|
| `OperationalInteractive` | `anylogic_operational` | `results/raw/anylogic_operational` |
| `OperationalPilot` | `anylogic_operational_batch` | `results/raw/anylogic_operational_batch` |

The Java export code locates the repository root by walking upward until it
finds `config/operational_scenarios.csv`, then writes beneath
`results/raw/<output_collection_id>`.

## 3. Regenerate safely

Run all commands from the repository root. Close AnyLogic before regeneration
so it does not retain or overwrite stale split-project fragments.

```powershell
.\.venv\Scripts\python.exe -m src.analysis.validate_operational_contract
.\.venv\Scripts\python.exe scripts\generate_operational_anylogic.py
.\.venv\Scripts\python.exe -m unittest tests.test_anylogic_operational
```

Expected generator summary:

```text
OperationalPilot: 15 scenarios x 10 replications (serial)
Generated operational AnyLogic split fragments
```

The generator fails closed unless:

- the operational contract passes;
- the CSV header is canonical;
- exactly 15 unique scenario IDs exist;
- every scenario declares exactly 10 pilot replications; and
- the GUI-owned operational class and experiment IDs still exist.

The script edits only the generated operational objects. The deterministic,
HPP, gate, and earlier model objects remain regression oracles.

For the full repository regression suite:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

## 4. Random-number policy

`routing_rng` and `tie_rng` are initialized to `null` in the model. They are
created lazily only after the experiment has injected and checked the seed
parameters. This prevents model construction from consuming stale default
seeds.

For Pilot scenario index `i` (zero based) and replication `r` (1 to 10):

```text
stream_base = master_seed + 100000 * i + 100 * r
arrival_seed = stream_base + 1
service_seed = stream_base + 2
routing_seed = stream_base + 3
tie_seed     = stream_base + 4
```

The AnyLogic default random generator is reseeded with `arrival_seed`.
`routing_rng` and `tie_rng` use their named streams. Fixed v1 service times do
not consume `service_seed`, but it remains in the lineage record.

`crn_alignment_status` is `NOT_TESTED`. A shared master-seed policy alone does
not establish common-random-number alignment, so downstream scenario
contrasts default to independent Welch intervals.

## 5. Run the reference smoke experiment

1. Open
   `simulation/anylogic/HTXCheckpointSimulation/HTXCheckpointSimulation.alpx`
   in AnyLogic PLE.
2. Run `OperationalInteractive`.
3. Use the visible experiment window and allow the model to drain fully.
4. Confirm that the window reaches `Finished`.
5. Close the experiment window before starting another experiment.

`OperationalInteractive` is locked to the canonical reference row. Its
replication ID is `0`, and its output is deliberately separated from the
reportable Pilot batch.

## 6. Run `OperationalPilot`

`OperationalPilot` must be run in the visible AnyLogic PLE GUI. This workflow
does not claim a headless PLE command-line runner.

1. Close any running experiment window.
2. In the Projects tree, run `OperationalPilot`.
3. The Parameter Variation window may appear blank. This is expected.
4. Do not press Play. A one-shot Swing timer starts the experiment
   automatically after approximately 300 ms.
5. Wait until the bottom-right status reads `Finished`.
6. Close the experiment window.

The experiment uses:

- free-form, registry-derived parameter expressions;
- 15 scenario iterations;
- 10 replications per iteration;
- serial evaluation (`AllowParallelEvaluations=false`);
- no fixed model-time stop (`StopOption=Never`); and
- a model-controlled full-drain termination.

Each replication writes:

```text
results/raw/anylogic_operational_batch/
  <scenario_id>/
    <input_sample_id>/
      replication_<NNN>/
        run_manifest.csv
        entity_log.csv
        replication_kpis.csv
```

A successful full Pilot produces exactly 150 manifest files, 150 KPI files,
and 150 entity-log files. The three files in every leaf directory must match
`config/result_schema_registry.csv`.

## 7. Consolidate, validate, and analyse

Do not analyse the nested raw batch directly. First consolidate it and require
the exact registered scenario-by-replication key set.

```powershell
.\.venv\Scripts\python.exe -m src.analysis.consolidate_operational_results
.\.venv\Scripts\python.exe -m src.analysis.validate_operational_results --require-pilot-coverage
.\.venv\Scripts\python.exe -m src.analysis.analyse_operational_replications
.\.venv\Scripts\python.exe -m src.analysis.build_operational_dashboard
```

For reportable Pilot output, do not use the consolidation script's
`--allow-partial` escape hatch.

Expected consolidated files:

```text
results/raw/operational/
  run_manifest.csv
  entity_log.csv
  replication_kpis.csv
```

Expected validation report:

```text
results/intermediate/operational_results/validation.json
```

Expected analysis outputs:

```text
results/analysis/operational/
  analysis_manifest.json
  scenario_estimates.csv
  scenario_contrasts.csv
  operational_dashboard.png
  operational_dashboard.svg
  README.md
```

The strict result gate checks, among other invariants:

- the exact 15 × 10 key set, with no missing or extra run;
- exact canonical scenario hash and configuration lineage;
- the scenario-specific seed formula;
- schema and type conformance;
- entity-to-manifest and KPI consistency;
- ordered timestamps;
- full-drain and cutoff conservation;
- zero rejection or drop count;
- utilization bounds; and
- `run_status=COMPLETE`.

Passing this gate establishes software, lineage, and conservation integrity.
It does not establish input calibration or operational validity.

## 8. Current verified Pilot evidence

The completed repository run has passed the strict gate:

| Check | Verified value |
|---|---:|
| Scenario-replication runs | 150 / 150 |
| Entity records | 61,218 |
| Validation errors | 0 |
| Contract status | `PASS` |
| Analysis estimate rows | 165 |
| Analysis contrast rows | 154 |

The machine-readable evidence is in:

```text
results/intermediate/operational_results/validation.json
results/analysis/operational/analysis_manifest.json
```

These counts prove complete registered coverage and software invariants for
this generated run. They do not convert the sandbox assumptions into
calibrated field inputs.

## 9. Statistical interpretation

The statistical sample is the 10 replication-level KPI values per scenario,
not the tens of thousands of traveller rows. The primary estimand is:

```text
mean of replication-level total_queue_wait_p95_seconds
```

The analysis produces 95% Student-t intervals for scenario estimates. Because
CRN alignment has not passed, scenario-minus-reference contrasts use
independent Welch intervals. With only 10 pilot replications, treat fine
rankings as provisional and use the results to identify dominant mechanisms,
failure boundaries, and the next evidence to collect.

## 10. Troubleshooting

### The Pilot window is blank

This is normal for the Parameter Variation experiment. Wait for the
auto-start timer and then for `Finished`.

### The window remains `Idle`

Close the experiment window, confirm the current generated split project was
saved and reopened, and rerun `OperationalPilot`. Do not add a second timer or
duplicate variable manually.

### The export cannot locate the repository

Open the `.alpx` from inside this repository and run it from AnyLogic. The
export code must be able to find `config/operational_scenarios.csv` in an
ancestor directory.

### Consolidation reports missing or extra runs

Treat that as a failed Pilot. Do not hand-edit the CSVs or weaken strict
coverage. Confirm the GUI reached `Finished`, inspect
`results/raw/anylogic_operational_batch`, and rerun the batch if necessary.

### A scenario hash fails

Do not paste or recompute a raw-line hash. Run the contract validator, then
regenerate the split project so the exact canonical hashes are embedded in
the experiment.

## 11. Explicit non-claims

The current model does not claim a measured time-of-day arrival profile,
empirically fitted service-time distributions, calibrated HTX resource
counts, a physical terminal layout, verified CRN pairing, or a site forecast.
It also does not represent a separate Secondary inspection resource pool.

The implemented comparison levers are demand, pooled capacity, named
Immigration service contexts, automation uptake and service multipliers, and
the counter-held risk sensitivity. Present all of them as controlled what-if
scenarios under declared assumptions.
