# Task 3 AnyLogic operational build and run guide

**AnyLogic:** Personal Learning Edition 8.9.9

**Authoritative model source:** `simulation/anylogic/HTXCheckpointSimulation/HTXCheckpointSimulation.alpx`

**Generator:** `scripts/generate_operational_anylogic.py`

**Batch designs:** 15 registered scenarios × 10 pilot replications and 12
capacity/rate cells × 50 confirmatory replications, both run serially

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
| `OperationalInteractive` | Exploratory/ad-hoc four-zone 2D Simulation experiment with five pre-run inputs and live state |
| `OperationalPilot` | Registry-driven Parameter Variation experiment |
| `CapacityRobustnessConfirmatory` | Frozen capacity/rate Parameter Variation experiment with 600 serial runs and one-shot auto-start |

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
| `config/confirmatory_capacity_study.json` | Frozen 12-cell capacity/rate design and 600-run cap |
| `config/confirmatory_seed_manifest.csv` | Exact 150 within-rate replication seed groups |
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
| `CapacityRobustnessConfirmatory` | `confirmatory_capacity` | `results/raw/confirmatory_capacity` |

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
CapacityRobustnessConfirmatory: 12 cells x 50 replications (600 capped runs, serial)
Generated operational AnyLogic split fragments and single-file launcher
```

The generator fails closed unless:

- the operational contract passes;
- the CSV header is canonical;
- exactly 15 unique scenario IDs exist;
- every scenario declares exactly 10 pilot replications; and
- the frozen confirmatory design has exactly 12 cells, 50 replications per
  cell, and 150 valid seed groups; and
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

Pilot `crn_alignment_status` is `NOT_TESTED`. A shared master-seed policy alone
does not establish common-random-number alignment, so pilot scenario contrasts
default to independent Welch intervals.

The confirmatory experiment uses its separate frozen seed manifest. Within an
arrival-rate level and replication, all four capacity alternatives receive the
same arrival, service, routing, and tie seeds. Paired analysis is still
forbidden until the traveller-level validator confirms identical traveller
sets and branch-invariant draws. The completed confirmatory gate returned
`PASS` across all 150 within-rate groups.

## 5. Run the exploratory interactive experiment

1. Open
   `simulation/anylogic/HTXCheckpointSimulation/HTXCheckpointSimulation.alpx`
   in AnyLogic PLE.
2. Run `OperationalInteractive`.
3. On the initial experiment screen, edit only the five exposed parameters:
   `demand_multiplier`, `security_capacity`, `immigration_capacity`,
   `automation_uptake`, and `automation_multiplier`.
4. Press Run. During execution, use AnyLogic's built-in Pause/Resume/Stop
   controls as needed.
5. Use the live four-zone 2D view:
   Arrival → Security → Immigration → Exit.
6. Observe admitted/completed progress, both queue counts, both in-service
   counts, queue maxima, technology/additional-check counts, and `run_status`.
7. Allow the cohort to drain, confirm `Finished`, and close the experiment
   window before starting another experiment. Stop and reopen the experiment
   to reset structural inputs.

Interactive domains are enforced before simulation:

| Parameter | Allowed value |
|---|---:|
| `demand_multiplier` | `0.5` through `2.0` |
| `security_capacity` | integer `1` through `200` |
| `immigration_capacity` | integer `1` through `200` |
| `automation_uptake` | `0.0` through `1.0` |
| `automation_multiplier` | strictly between `0.0` and `1.0` when uptake is positive; forced to `1.0` when uptake is zero |

Pooled FCFS is the only implemented queue policy. It is fixed rather than
offered as a fake selector. The interactive experiment generates an
`INTERACTIVE_EXPLORATORY` ad-hoc scenario, uses replication ID `0`, and writes
outside the reportable replicated collections. Use it to inspect behaviour,
not to make reportable claims.

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

## 7. Run `CapacityRobustnessConfirmatory`

`CapacityRobustnessConfirmatory` is also a visible AnyLogic PLE Parameter
Variation experiment:

1. Close any running experiment window.
2. In the Projects tree, run `CapacityRobustnessConfirmatory`.
3. The Parameter Variation window may be blank. Do not press Play.
4. A private one-shot Swing timer starts the experiment automatically after
   approximately 300 ms.
5. Wait until the bottom-right status reads `Finished`, then close the window.

The frozen experiment crosses four capacity alternatives with three registered
arrival-rate levels, uses 50 replications per cell, and therefore executes:

```text
12 cells × 50 replications = 600 runs
```

Evaluation is serial (`AllowParallelEvaluations=false`), no adaptive extension
is permitted, and the same full-drain termination and fail-closed export
checks apply to every run. Raw run folders are written under:

```text
results/raw/confirmatory_capacity/
  <scenario_id>/
    <input_sample_id>/
      replication_<NNN>/
        run_manifest.csv
        entity_log.csv
        replication_kpis.csv
```

## 8. Consolidate, validate, and analyse

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

For the confirmatory study, consolidate the exact frozen key set and run its
fail-closed analysis:

```powershell
.\.venv\Scripts\python.exe -m src.analysis.consolidate_operational_results `
  --confirmatory
.\.venv\Scripts\python.exe -m src.analysis.analyse_confirmatory_capacity
```

The confirmatory analysis revalidates exact 600-run coverage and
traveller-level CRN alignment before choosing the pre-specified paired method
or Welch fallback. The repository-retained compact outputs are kept under
`results/analysis/confirmatory_capacity/`.

Expected consolidated files:

```text
results/raw/operational/
  run_manifest.csv
  entity_log.csv
  replication_kpis.csv
```

Expected validation report:

```text
results/analysis/operational/validation.json
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

Expected retained confirmatory outputs:

```text
results/analysis/confirmatory_capacity/
  audit_manifest.json
  validation.json
  crn_alignment.json
  analysis_manifest.json
  primary_result.json
  ranking_stability.json
  rate_rankings.csv
  scenario_estimates.csv
  scenario_contrasts.csv
  within_rate_pairwise_contrasts.csv
  run_manifest.csv
  replication_kpis.csv
```

For the Pilot, the strict result gate checks, among other invariants:

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

The confirmatory gate applies the same schema, lineage, event-order,
conservation, zero-loss, and full-drain checks to the exact 12 × 50 key set,
then applies its separate traveller-level CRN alignment gate. Passing either
execution gate establishes software, lineage, and conservation integrity. It
does not establish input calibration or operational validity.

## 9. Current verified evidence

The completed Pilot repository run has passed the strict gate:

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
results/analysis/operational/validation.json
results/analysis/operational/analysis_manifest.json
```

These counts prove complete registered coverage and software invariants for
this generated run. They do not convert the sandbox assumptions into
calibrated field inputs.

The completed confirmatory study records:

| Check | Verified value |
|---|---:|
| Capacity/rate cells × replications | `12 × 50 = 600`, serial |
| Exact run coverage | `600 / 600` |
| Entity records | `253,756` |
| Strict result validation | `PASS` |
| CRN alignment | `PASS`, 150 within-rate replication groups |
| Comparison method after the gate | `PAIRED_STUDENT_T` |

Reviewer-facing machine-readable evidence is retained at:

- [`audit_manifest.json`](../../results/analysis/confirmatory_capacity/audit_manifest.json)
- [`validation.json`](../../results/analysis/confirmatory_capacity/validation.json)
- [`crn_alignment.json`](../../results/analysis/confirmatory_capacity/crn_alignment.json)
- [`analysis_manifest.json`](../../results/analysis/confirmatory_capacity/analysis_manifest.json)
- [`primary_result.json`](../../results/analysis/confirmatory_capacity/primary_result.json)

These checks establish exact execution, lineage, conservation, and CRN
alignment for the frozen study. They remain conditional on the registered
pooled-FCFS, fixed-service, empty-start, and full-drain assumptions.
The compact audit manifest retains the 253,756-row entity-log hash and row
count; the 125 MB consolidated entity log itself is deliberately not tracked.

## 10. Statistical interpretation

The statistical sample is the 10 replication-level KPI values per scenario,
not the tens of thousands of traveller rows. The primary estimand is:

```text
mean of replication-level total_queue_wait_p95_seconds
```

The pilot analysis produces 95% Student-t intervals for scenario estimates.
Because pilot CRN alignment has not been tested, its scenario-minus-reference
contrasts use independent Welch intervals. With only 10 pilot replications,
treat fine pilot rankings as provisional.

The confirmatory design fixes 50 replications in each of 12 cells. Its current
full CRN alignment gate passed, so within-rate contrasts use paired Student-t
intervals. That statistical upgrade strengthens the frozen conditional
capacity-mechanism comparison; it does not establish calibrated demand,
service, resource, roster, or cost inputs.

## 11. Troubleshooting

### The Pilot window is blank

This is normal for the Parameter Variation experiment. Wait for the
auto-start timer and then for `Finished`.

### The window remains `Idle`

Close the experiment window, confirm the current generated split project was
saved and reopened, and rerun `OperationalPilot` or
`CapacityRobustnessConfirmatory`. Do not add a second timer or duplicate
variable manually.

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

## 12. Explicit non-claims

The current model does not claim a measured time-of-day arrival profile,
empirically fitted service-time distributions, calibrated HTX resource
counts, a physical terminal layout, or a site forecast. Confirmatory CRN
pairing is verified only for the frozen within-rate capacity study; pilot CRN
remains untested. The model also does not represent separate per-counter queues
or a separate Secondary inspection resource pool.

The implemented comparison levers are demand, pooled capacity, named
Immigration service contexts, automation uptake and service multipliers, and
the counter-held risk sensitivity. Present all of them as controlled what-if
scenarios under declared assumptions.
