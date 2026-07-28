# AnyLogic Technical Gate Verification

**Status:** PASS  
**Date:** 2026-07-27  
**Engine:** AnyLogic Personal Learning Edition 8.9.9
(`8.9.9.202607020720`)

## Purpose and scope

This gate verifies that the selected engine can execute native Process
Modeling Library blocks, orchestrate outer input samples and inner stochastic
replications, preserve explicit seed lineage, export fixed-schema CSV files,
and reproduce an identical run manifest.

It is a synthetic one-stage harness:

```text
Source -> Queue -> Delay -> Sink
```

It is not an operational result and does not yet verify the full
Security-to-Immigration process, separate-versus-pooled Immigration queues,
technology and additional-check mechanisms, the interactive dashboard, CRN
pairing across scenarios, or site validity.

## Tested artifacts

- Split source model:
  `simulation/anylogic/HTXCheckpointSimulation/HTXCheckpointSimulation.alpx`
  together with its adjacent `_alp/` directory.
- Single-file launch copy:
  `simulation/anylogic/HTXCheckpointSimulationCLI/HTXCheckpointSimulationCLI.alp`.
- Experiment: `GatePV2x3`.
- Test oracle: `config/anylogic_gate_manifest.csv`.
- Independent validator: `src/analysis/validate_anylogic_gate.py`.

The test oracle contains two synthetic input samples and three replications per
sample. Each run admits 12 travellers.

## Observed evidence

| Check | Evidence | Status |
|---|---:|---|
| Input samples | 2 | PASS |
| Replications per sample | 3 | PASS |
| Total run rows | 6 | PASS |
| Total traveller rows | 72 | PASS |
| Fixed output schemas | manifest, entity, summary | PASS |
| Explicit run lineage | scenario, input sample, replication, seed | PASS |
| Distinct stochastic fingerprints | 3 per input sample | PASS |
| Legal event order and positive demand | all 72 rows | PASS |
| Second GUI execution | byte-identical to first GUI execution | PASS |
| Automatic visible-GUI start | no Play click; 6 runs and 72 entities | PASS |
| Single-file ALP `-r` launch | auto-started; byte-identical to GUI baseline | PASS |

AnyLogic PLE 8.9.9 does not expose the native `Skip experiment screen and run
model` option for this Parameter Variation experiment. The tested model instead
uses a pinned GUI auto-start adapter: a private, non-repeating
`javax.swing.Timer` waits 300 ms for the visible experiment window to
initialize, stops itself, and invokes the documented
[`GatePV2x3.this.run()` API](https://anylogic.help/anylogic/experiments/parameter-variation.html)
once. The adapter is launch plumbing only; the independent validator returned
`PASS` for all 6 runs and 72 entity rows, and all three outputs remained
byte-identical to the reference run.

This is a tested visible command-line GUI launch path, not headless,
standalone, or native Parameter Variation skip-screen support. The separate
Simulation experiment `TwoStageDeterministic` uses its native
[`Skip experiment screen and run model`](https://anylogic.help/anylogic/experiments/simulation-experiment.html)
option. The two mechanisms are intentionally documented separately even
though both now reach `Finished` without a Play click.

## Reproducibility hashes

The first GUI run, second GUI run, and single-file ALP run produced the same
SHA-256 for every output:

| Output | SHA-256 |
|---|---|
| `entity_log.csv` | `8a86de72d6d0880f3b329f087a26163ea7a972c782fe0a1b448e4fcd540aba01` |
| `run_manifest.csv` | `16f7e18eecf6f902dcf716d644cecc9dce1de1f263f9b6dc456bb2c662f5af51` |
| `run_summary.csv` | `cda11567759a67f1814bb34ed4f6acfbda4c5e2e088c9b6c93893bb21bdb1a5e` |

Raw and intermediate results are intentionally Git-ignored. These hashes are
the sanitized, tracked evidence; reviewers can regenerate the files locally.

## Validation commands

After one execution:

```powershell
.\.venv\Scripts\python.exe -m src.analysis.validate_anylogic_gate
```

For a byte-identical rerun, preserve the first output before running the
experiment again:

```powershell
$reference = "results\intermediate\anylogic_gate\reference_run"
New-Item -ItemType Directory -Path $reference -Force | Out-Null
Copy-Item "results\raw\anylogic_gate\*.csv" $reference
```

Run `GatePV2x3` again, let the visible experiment auto-start and reach
`Finished`, then compare:

```powershell
.\.venv\Scripts\python.exe -m src.analysis.validate_anylogic_gate `
  --reference-dir results\intermediate\anylogic_gate\reference_run
```

Expected result:

```text
status = PASS
errors = []
reproducibility.byte_identical = true
```

`pairing_status` is `NOT_APPLICABLE_SINGLE_SCENARIO`; CRN alignment must be
verified later on the full multi-scenario model before paired inference is
allowed.
