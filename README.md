# HTX Immigration Checkpoint Decision Simulation

An evidence-informed, interactive discrete-event simulation of a two-stage
immigration checkpoint:

```text
Arrival -> Security -> Immigration -> Exit
```

The project is structured around four assessment deliverables:

1. video-based data collection and audit;
2. system design and documented assumptions;
3. an executable interactive simulation;
4. a five-slide operational-insights presentation.

## Project status

The Task 1 aggregate measurement is frozen. Within the upper-corridor ROI at
`x = 640`, human adjudication accepted 12 left-to-right and 34 right-to-left
crossings over 24.922788889 seconds, or 46 bidirectional crossings. The
assessment entrance mapping uses `right_to_left`, so the short-window arrival
input is `34 / 24.922788889 = 1.364213` travellers per second. The tracked
evidence is `data/derived/task1_final_aggregate.csv`. This is an accepted
aggregate without a signed event-time ledger, and the short clip does not
establish long-run checkpoint demand.

The primary local automatic candidate path is YOLO26m with BoT-SORT, followed
by human adjudication. A licence-friendlier public fallback uses YOLOX-S with
Supervision ByteTrack; its reviewed distinct candidate set is 7
left-to-right and 24 right-to-left. Candidate outputs from either path are not
treated as ground truth.

On 2026-07-27, the synthetic AnyLogic execution/export/seed gate passed in PLE
8.9.9. `GatePV2x3` runs a native `Source -> Queue -> Delay -> Sink` flow for
two input samples and three replications each, exporting six run records and
72 traveller records. A second GUI execution and the exported single-file ALP
launch produced byte-identical CSV outputs, and the independent validator
returned `PASS`. The visible Parameter Variation window now starts
automatically through a pinned, one-shot GUI adapter; this does not imply
native skip-screen or headless support.

The separate `TwoStageDeterministic` experiment now also passes an exact
Security-to-Immigration finite-resource oracle, including a live cutoff, full
drain, per-traveller timestamps, and byte-identical split/single-file outputs.
Both remain synthetic verification evidence rather than operational results.

The Task 3 `OperationalPilot` has also completed: 15 registered assumption
scenarios × 10 independent replications produced 150/150 valid runs and
61,218 traveller rows. The implementation is a pooled-FCFS, two-stage DES
with a 300-second HPP arrival window followed by full drain. Strict schema,
scenario, seed, conservation, and drain validation returned `PASS`. These are
comparative pilot results conditional on declared literature-context and
transparent assumptions—not a calibrated HTX baseline, site forecast, or
staffing recommendation. See
[`results/analysis/operational/README.md`](results/analysis/operational/README.md)
and the
[`operational dashboard`](results/analysis/operational/operational_dashboard.png).
The reviewer-facing interpretation, including the bottleneck-migration result
and guardrail diagnosis, is in
[`docs/task3_results.md`](docs/task3_results.md).

## Licensing and deployment boundary

The licence-friendlier public evidence pipeline does not require Ultralytics.
The primary local measurement path uses YOLO26m and the Ultralytics BoT-SORT
implementation, governed by AGPL-3.0 or a separate Ultralytics commercial
licence; its weights are excluded from Git. “BoT-SORT primary” refers to the
local measurement experiment, not approval to deploy the Ultralytics
implementation in a private HTX system.

For proprietary, internal-business, or operational use, either obtain an
applicable paid R&D licence for a strictly non-operational proof of concept,
obtain an Enterprise/commercial licence for operational use, or substitute
licence-approved detector and tracker implementations and revalidate them. See
`LICENSING.md` and `THIRD_PARTY_NOTICES.md`. This is a technical boundary
statement, not legal advice.

## Setup

### Python evidence pipelines

Requirements: Windows x64 and Python 3.12.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip check
```

This base environment provides the licence-friendlier YOLOX-S reference path
with `opencv-python-headless` and the transparent Hungarian candidate tracker.
It is a reproducible public baseline, not the primary local candidate path used
for the accepted aggregate.

For the YOLOX-S plus Supervision ByteTrack fallback, use a separate
environment:

```powershell
python -m venv .venv-bytetrack
.\.venv-bytetrack\Scripts\python.exe -m pip install -r requirements-bytetrack.txt
.\.venv-bytetrack\Scripts\python.exe -m pip check
```

Do not install both OpenCV packages into one environment: `opencv-python` and
`opencv-python-headless` provide the same `cv2` namespace.

Place the assessment video at `data/raw/TestVidTask.mov`. Download the pinned
official YOLOX-S ONNX release asset and verify its byte length and SHA-256:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\download_yolox_s.ps1
```

Model weights are deliberately excluded from Git. See
`LICENSING.md` and `THIRD_PARTY_NOTICES.md` for upstream projects and licence
boundaries.

### Simulation engine

The primary engine is
[AnyLogic PLE 8.9.9 for Windows x64](https://www.anylogic.com/files/anylogic-ple-8.9.9.x86_64.exe).
The local installation identifies itself as
`8.9.9.202607020720`. The GUI execution/export/seed/reproducibility gate and
the documented single-file ALP `-r` launch path passed locally on 2026-07-27.

Built with AnyLogic PLE solely as a personal, non-production skills
demonstration. PLE remains subject to AnyLogic's use restrictions; no
operational, commercial, or research reuse is asserted or granted.

## Engine and framework versions

- Python: 3.12.13 during development.
- OpenCV: 4.13.0.92.
- ONNX Runtime: 1.28.0, CPU execution provider.
- YOLOX-S ONNX: official YOLOX `0.1.1rc0` release asset; SHA-256 is recorded by
  the download workflow.
- Simulation engine: AnyLogic PLE 8.9.9 (`8.9.9.202607020720`); local
  GUI and single-file ALP launch gates passed on 2026-07-27.

## Architecture

- Python: video inference, manual-count reconciliation, input modelling,
  statistical analysis, and figure generation.
- AnyLogic PLE: primary interactive discrete-event simulation engine.
- SimPy plus an equivalent browser UI: fallback if the required batch-export
  workflow cannot be validated or an appropriate engine-use basis is not
  available.

## Run instructions

Extract deterministic metadata and a local contact sheet:

```powershell
.\.venv\Scripts\python.exe -m src.cv.extract_contact_sheet `
  --video data/raw/TestVidTask.mov `
  --output-dir _work/video_audit `
  --sample-count 16
```

Generate the transparent YOLOX-S/Hungarian reference candidates with the
frozen geometry (full upper corridor, two overlapping inference tiles,
central line):

```powershell
.\.venv\Scripts\python.exe -m src.cv.audit_crossings `
  --video data/raw/TestVidTask.mov `
  --model models/yolox_s.onnx `
  --output-dir _work/cv_hungarian_x640
```

This command reproduces a candidate baseline, not the accepted aggregate or an
automatically accepted ground truth. The historical Day-1 reconciliation is
described in `docs/task1_measurement.md`; the frozen aggregate is
`data/derived/task1_final_aggregate.csv`.

The primary local automatic candidate path uses YOLO26m with BoT-SORT. Its
detector comparison is recorded in `docs/yolo26_detector_ab.md`, and the
follow-on three-tracker experiment is recorded in
`docs/yolo26m_tracker_sensitivity.md`; all trackers replay the same hashed
YOLO26m detection cache. This local path informs human adjudication but does
not itself define the accepted count. Its Ultralytics licence boundary is
documented in `LICENSING.md` and `THIRD_PARTY_NOTICES.md`.

Run the licence-friendlier YOLOX-S/Supervision-ByteTrack fallback in its own
environment:

```powershell
.\.venv-bytetrack\Scripts\python.exe -m src.cv.audit_crossings `
  --video data/raw/TestVidTask.mov `
  --model models/yolox_s.onnx `
  --output-dir _work/cv_yoloxs_bytetrack_fallback `
  --tracker bytetrack `
  --track-activation-threshold 0.15 `
  --minimum-matching-threshold 0.90 `
  --min-hits 1
```

After removing one visually confirmed right-to-left handover duplicate, this
fallback has 7 reviewed left-to-right and 24 reviewed right-to-left distinct
candidates. It is a conservative cross-check, not a statistical lower bound.

Run deterministic offline regression tests:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Run the synthetic AnyLogic technical gate:

1. Open
   `simulation/anylogic/HTXCheckpointSimulation/HTXCheckpointSimulation.alpx`
   in AnyLogic PLE 8.9.9. Keep its adjacent `_alp/` directory intact.
2. Run `GatePV2x3`; its visible experiment window starts the run
   automatically. Wait for `Finished`.
3. Validate the files written to `results/raw/anylogic_gate/`:

```powershell
.\.venv\Scripts\python.exe -m src.analysis.validate_anylogic_gate
```

The reviewer-friendly single-file copy can be launched from the repository
root with:

```powershell
& "C:\Program Files\AnyLogic 8.9 Personal Learning Edition\AnyLogic.exe" `
  -r "$PWD\simulation\anylogic\HTXCheckpointSimulationCLI\HTXCheckpointSimulationCLI.alp" `
  "GatePV2x3"
```

For `GatePV2x3`, this `-r` path opens the visible Parameter Variation
experiment and a pinned one-shot `javax.swing.Timer` adapter invokes its
documented
[`run()` API](https://anylogic.help/anylogic/experiments/parameter-variation.html)
after 300 ms, then stops itself. AnyLogic PLE 8.9.9 does not expose the native
`Skip experiment screen and run model` option for Parameter Variation
experiments. `TwoStageDeterministic`, by contrast, is a Simulation experiment
and uses that native initial-screen bypass. Both reach `Finished` without a
Play click, but both remain visible PLE GUI launches—not headless, standalone,
or native Parameter Variation skip-screen support.
See `simulation/README.md` for the byte-identical rerun procedure and
`docs/anylogic_gate_verification.md` for the recorded evidence and scope.

Run the deterministic two-stage mechanism verification:

1. In the same split project, run
   `TwoStageDeterministic: CheckpointModel` and wait for `Finished`.
2. Validate the exact six-traveller ledger, both service stages, the 6.5-second
   cutoff state, full drain, schemas, lineage, and derived metrics:

```powershell
.\.venv\Scripts\python.exe -m src.analysis.validate_anylogic_two_stage
```

The expected result is `status: PASS` with an empty `errors` list. This is a
synthetic mechanism oracle, not an operational baseline. Recorded evidence is
in `docs/anylogic_two_stage_verification.md`.

Run and analyse the Task 3 operational assumption pilot:

1. In the same split project, run
   `OperationalPilot: OperationalCheckpointModel` and wait for `Finished`.
   It executes the 15 registered scenarios with 10 independent replications
   each and writes run folders below
   `results/raw/anylogic_operational_batch/`.
2. From the repository root, run the fail-closed contract, consolidation,
   strict coverage validation, replication analysis, and dashboard build:

```powershell
.\.venv\Scripts\python.exe -m src.analysis.validate_operational_contract
.\.venv\Scripts\python.exe -m src.analysis.consolidate_operational_results
.\.venv\Scripts\python.exe -m src.analysis.validate_operational_results `
  --require-pilot-coverage
.\.venv\Scripts\python.exe -m src.analysis.analyse_operational_replications
.\.venv\Scripts\python.exe -m src.analysis.build_operational_dashboard
```

The recorded batch has 150/150 valid runs and 61,218 traveller rows. The
analysis uses independent Welch intervals because traveller-level common
random-number alignment remains `NOT_TESTED`; no paired-CRN precision claim is
made. The primary outputs are the
[`scenario estimates`](results/analysis/operational/scenario_estimates.csv),
[`scenario contrasts`](results/analysis/operational/scenario_contrasts.csv),
[`dashboard`](results/analysis/operational/operational_dashboard.png), and
[`strict validation report`](results/intermediate/operational_results/validation.json).

## Build instructions

Not applicable for the Python evidence pipeline: it runs from source in the
locked virtual environment. AnyLogic PLE cannot export a standalone
application; reviewers will run the supplied model project in the documented
free engine version. The tracked `.alp` is a single-file model copy for easier
launching, not a standalone application.

## How to modify simulation parameters

- Edit `config/parameter_registry.csv` for values, ranges, units, and evidence
  provenance.
- Edit `config/operational_scenarios.csv` and
  `config/scenario_provenance.csv` to define controlled operational-assumption
  scenarios and their provenance.
- Treat `config/anylogic_gate_manifest.csv` only as a synthetic test oracle;
  it is not an approved operational parameter set.
- Do not hard-code decision parameters in Python or the simulation model.
- Regenerate the split AnyLogic fragments with
  `.\.venv\Scripts\python.exe scripts\generate_operational_anylogic.py` after
  an approved contract change, then rerun the contract and result gates.
- The current interactive GUI is intentionally minimal. It is not evidence of
  a polished control panel, visual checkpoint layout, or standalone product.

## Restricted input

The assessment video is not redistributed in this public repository.

1. Obtain `TestVidTask.mov` from the link supplied in the assessment.
2. Place it at `data/raw/TestVidTask.mov`.
3. Run the documented pipeline locally.

Generated videos or frames containing original pixels are also kept local.
Public documentation uses numerical audit tables and trajectory/counting-line
schematics that do not reproduce the source video.

## Repository map

```text
config/       parameter provenance and scenario definitions
data/         local input instructions and generated tabular evidence
docs/         Task 1-3 reports and result-blind analysis plan
simulation/   selected simulation-engine project
src/          CV, input modelling, experiment, and analysis code
tests/        deterministic verification checks
results/      reproducible tables and figures
slides/       Task 4 presentation
```

The public release will also contain the Task 1 approach/results, Task 2 short
design document, Task 3 logic/metrics documentation, and the Task 4 slide deck.
The completed five-slide deck is
[`slides/HTX_Task4_Operational_Insights.pptx`](slides/HTX_Task4_Operational_Insights.pptx).
