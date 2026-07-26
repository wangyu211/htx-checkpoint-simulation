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

Day 1 implementation is in progress. The video container, reflection-free ROI,
strict candidate ledger, low-confidence recall stress, and a complete
AI-assisted sequential visual sweep are recorded. Three recovered events and
the operational direction still require project-owner sign-off, so the arrival
input remains `TBD`. Quantitative inputs and recommendations will only be
frozen after that review, simulation verification, and the result-blind
analysis-plan freeze.

## Setup

### Python evidence pipeline (primary)

Requirements: Windows x64 and Python 3.12.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip check
```

This base environment uses `opencv-python-headless` and the transparent
Hungarian candidate tracker.

For the optional ByteTrack sensitivity check, use a separate environment:

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
`THIRD_PARTY_NOTICES.md` for upstream projects and license boundaries.

### Simulation engine

The primary engine is
[AnyLogic PLE 8.9.9 for Windows x64](https://www.anylogic.com/files/anylogic-ple-8.9.9.x86_64.exe).
The local installation identifies itself as
`8.9.9.202607020720`; the independent execution/export/seed smoke gate is still
in progress.

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
  execution/export/seed smoke test is pending.

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

Generate the current high-recall crossing candidates with the frozen Day-1
geometry (full upper corridor, two overlapping inference tiles, central line):

```powershell
.\.venv\Scripts\python.exe -m src.cv.audit_crossings `
  --video data/raw/TestVidTask.mov `
  --model models/yolox_s.onnx `
  --output-dir _work/cv_hungarian_x640
```

This command produces candidates, not an automatically accepted ground truth.
Reconcile its event evidence as described in `docs/task1_measurement.md`.

Run the optional conservative ByteTrack cross-check in its own environment:

```powershell
.\.venv-bytetrack\Scripts\python.exe -m src.cv.audit_crossings `
  --video data/raw/TestVidTask.mov `
  --model models/yolox_s.onnx `
  --output-dir _work/cv_bytetrack_x640 `
  --tracker bytetrack `
  --track-activation-threshold 0.10 `
  --min-hits 1
```

Run deterministic offline regression tests:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The simulation command will be promoted here after its acceptance gate passes.

## Build instructions

Not applicable for the Python evidence pipeline: it runs from source in the
locked virtual environment. AnyLogic PLE cannot export a standalone
application; reviewers will run the supplied model project in the documented
free engine version.

## How to modify simulation parameters

- Edit `config/parameter_registry.csv` for values, ranges, units, and evidence
  provenance.
- Edit `config/scenarios.csv` to define controlled scenario changes.
- Do not hard-code decision parameters in Python or the simulation model.
- UI controls and their exact mapping to these keys will be listed after the
  simulation smoke gate.

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
