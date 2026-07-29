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

The result-blind confirmatory capacity study has now also completed. Four
capacity alternatives were crossed with the exact low/base/high
count-rate levels, with 50 replications per cell: 600/600 runs and 253,756
traveller rows passed strict validation. Traveller-level common-random-number
alignment passed across all 150 within-rate replication groups, so the
pre-specified paired analysis was authorised. At the base rate, joint
`Security +4 / Immigration +3` minus reference changed the mean
replication-level total queue-wait P95 by `-2.678732 s` (paired 95% CI
`[-3.060892, -2.296573]`, `n=50`); the achieved half-width was `0.382160 s`,
within the frozen `1.0 s` target. This is conditional capacity-mechanism
evidence, not a calibrated staffing result. See the
[`confirmatory design`](docs/task3_confirmatory_design.md) and
[`compact audit package`](results/analysis/confirmatory_capacity/README.md).

Part 2 is a separately registered capacity-availability stress study. Its
600/600 new runs and the 150 immutable Reference runs produced a validated
750-run analytical dataset. Hash, lineage, coverage, conservation, full-drain,
seed, traveller-level, and branch-invariant CRN gates all passed. At the base
arrival rate, joint `32 / 18 minus 36 / 21` increased the mean
replication-level simultaneous peak total waiting queue by `10.10` travellers
(paired 95% CI `[8.23, 11.97]`, `n=50`). Immigration availability was the
stronger near-saturation constraint under the registered assumptions, and the
effect grew sharply at the high arrival boundary. These are conditional
capacity-resilience results, not an observed roster or staffing
recommendation. See the
[`Part 2 design and results`](docs/task3_capacity_availability_design.md) and
[`compact audit package`](results/analysis/capacity_availability/README.md).

The completed post-outcome capacity response surface then resolves the
base-demand mechanism at every integer combination of Security `36` to `28`
and Immigration `21` to `16`: `54 cells × 50 replications = 2,700` new
AnyLogic runs and `1,113,588` traveller rows. Exact coverage, frozen hashes,
lineage, conservation, full drain, seeds, traveller-level CRN alignment, and
five-cell cross-batch reproducibility all returned `PASS`. On the
single-stage slices, the mean replication-level total queue-wait P95 rises
from `3.929 s` at `36 / 21` to `24.434 s` at `28 / 21`, and to `35.609 s` at
`36 / 16`. The penalty per next closed position accelerates from
`0.291 s` to `6.975 s` for Security and from `1.313 s` to `14.682 s` for
Immigration. This curvature appears around the offered-workload boundaries
`29.765` Security positions and `17.735` Immigration positions.

The full surface adds a serial-system insight that endpoint comparisons
cannot show: the active bottleneck migrates, and the upstream Security stage
meters flow into Immigration. Consequently joint deterioration is generally
not additive. For example, the local interaction for reducing `30 / 18` to
`29 / 17` is `-4.021 s` (paired 95% CI `[-4.721, -3.320]`); the negative sign
is evidence of sub-additivity under this flow structure, not a beneficial
staffing synergy. A deterministic ideal comparator with perfectly regular
arrivals and the same fixed service times separates the straight-line
throughput benchmark from queueing delay: ideal P95 stays zero through
`30 / 21` and `36 / 18`, then rises after saturation. AnyLogic minus ideal is
reported only as a variability/congestion penalty. This response surface is
exploratory, fixed at the Base demand input, and is not a calibrated forecast,
observed roster, causal staffing effect, or staffing recommendation. See the
[`exploratory design and execution record`](docs/task3_capacity_response_surface_design.md)
and [`compact analysis package`](results/analysis/capacity_response_surface/README.md).

The independent mean-preserving service-variability sensitivity has also
completed: `3 × 3` Security/Immigration CV assumptions with 50 paired
replications per cell produced 450/450 valid AnyLogic runs and 185,598
traveller rows. Coverage, conservation, full drain, traveller-level
common-random-number alignment, and exact cross-batch reproduction of the
fixed-service `36 / 21` reference all returned `PASS`. Relative to CV `0 / 0`,
joint CV `1 / 1` increased mean replication-level total queue-wait P95 by
`1.668 s` (paired 95% CI `[0.677, 2.660]`), system-time P95 by `43.471 s`
(`[41.565, 45.376]`), and post-cutoff clearance by `95.993 s`
(`[81.162, 110.823]`). The queue effect came primarily from the Immigration
CV assumption at this reference cell; the CV `1 × 1` queue-wait interaction
was unresolved. These CVs are transparent mean-preserving lognormal
assumptions, not measured service distributions. The study is exploratory,
uncalibrated, and not a site forecast or staffing recommendation. See the
[`frozen design and execution record`](docs/task3_service_variability_design.md)
and [`compact analysis package`](results/analysis/service_variability/README.md).

Across the 54 cell estimates, mean replication-level total-wait P95 spans
`3.929–35.920 s` under a 300-second empty-start cohort; this is not a maximum
individual wait. The registered illustrative `600 / 900 / 1200 s` exceedance
rates are zero here, but they are not ICA service-level agreements. The
accepted `1.364213/s` input is a directional corridor cross-section aggregate
conditionally routed into one pooled model; processing-unit allocation is
unobserved. The
[`registered-threshold diagnostic`](results/analysis/capacity_response_surface/threshold_exceedance_diagnostics.json)
makes this boundary auditable.

The frozen grid already spans light through stressed conditions. Reference
nominal maximum offered load is `0.585 / 0.845 / 1.180` at low/base/high;
reference versus joint +4/+3 total-wait P95 is
`0.067/0.000 s`, `3.929/1.250 s`, and `51.671/18.513 s`.
At high load, single-stage expansion moves the bottleneck to the other stage,
whereas joint capacity reduces the modelled P95 by `33.158 s`
(`[31.410, 34.906]`). The resulting recommendation is conditional: carry the
joint mechanism into field calibration only where observed peak demand and
corridor-to-processing-unit allocation, service distributions, and
open-resource schedules reproduce material queues; do not infer a staffing
rollout. Post-hoc 15/30/60-second diagnostics are labelled as model-scale
supporting evidence, not ICA SLAs.

The independent peak-duration sensitivity has now also completed:
`4` selected capacity cells x `5` arrival-window durations x `50`
replications produced `1000/1000` valid AnyLogic runs and `3,768,780`
traveller rows. Exact CRN-prefix alignment, full drain, conservation,
zero-loss, computational-guard, and T=300 cross-batch reproduction gates all
returned `PASS`; the latter covered 200 runs and 82,488 traveller rows. The
result shows why the 300-second empty-start surface is not enough to
characterise sustained exposure. Under the model's maximum offered-work
`rho` proxy, `36/21` (`0.845`) remains stable across the tested horizons,
`30/18` (`0.992`) exhibits a long near-critical transient, and `29/17`
(`1.043`) plus `28/16` (`1.108`) accumulate backlog. Mean
replication-level total queue-wait P95 at 120 minutes is `4.472`, `55.910`,
`307.148`, and `748.204 s` respectively.

This is a conditional finite-horizon extension of the accepted short-window
rate as a stationary HPP, not an observed peak or time-of-day model. It emits
no steady-state SLA for `rho >= 1`, and it is not a site forecast or staffing
recommendation. The finite guard is computational, not a physical queue
capacity. See the
[`frozen design and execution record`](docs/task3_peak_duration_sensitivity_design.md)
and
[`compact analysis package`](results/analysis/peak_duration_sensitivity/README.md).

`OperationalInteractive` provides the reviewer-facing simulation surface:
four labelled Arrival → Security → Immigration → Exit zones, live queue and
in-service state, run status, and exactly five genuine pre-run controls
(demand multiplier, both capacities, automation uptake, and automation
multiplier). Within this AnyLogic surface, pooled FCFS is the only implemented
queue policy; no non-functional policy selector is shown. The separate-queue
mechanism exists
only as an exact-gated offline synthetic-ledger replay and does not identify
the current site policy. Interactive runs are exploratory and are excluded
from reportable replicated evidence.

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
$anyLogic = Join-Path $env:ProgramFiles `
  "AnyLogic 8.9 Personal Learning Edition\AnyLogic.exe"
if (-not (Test-Path -LiteralPath $anyLogic)) {
  throw "AnyLogic PLE 8.9.9 was not found under Program Files."
}
& $anyLogic `
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
[`strict validation report`](results/analysis/operational/validation.json).

Run the frozen confirmatory capacity study:

1. Open the split project in AnyLogic PLE 8.9.9 and run
   `CapacityRobustnessConfirmatory: OperationalCheckpointModel`. The visible
   Parameter Variation window starts the serial study automatically; wait for
   `Finished`. The fixed contract is 12 cells × 50 replications.
2. Consolidate, validate the exact 600-run coverage, enforce the
   traveller-level CRN gate, and analyse the registered contrast:

```powershell
.\.venv\Scripts\python.exe -m src.analysis.consolidate_operational_results `
  --confirmatory
.\.venv\Scripts\python.exe -m src.analysis.validate_operational_results `
  --results-dir results\raw\confirmatory_capacity_consolidated `
  --require-confirmatory-coverage `
  --report results\intermediate\confirmatory_capacity\validation.json
.\.venv\Scripts\python.exe -m src.analysis.analyse_confirmatory_capacity
```

The checked-in compact package records 600/600 valid runs, 253,756 entities,
CRN `PASS`, the primary paired interval, and supporting rate rankings. The
large consolidated entity ledger is not tracked; its SHA-256 and row count are
recorded in the
[`audit manifest`](results/analysis/confirmatory_capacity/audit_manifest.json).

Run the exploratory Base-demand capacity response surface:

1. In AnyLogic PLE 8.9.9, run
   `CapacityResponseSurfaceExploratory: OperationalCheckpointModel` and wait
   for `Finished`. The frozen contract is 54 cells × 50 serial replications.
2. Validate and package the complete result tree:

```powershell
.\.venv\Scripts\python.exe -m src.analysis.analyse_capacity_response_surface
```

The command fails closed unless all 2,700 runs, frozen hashes, seeds,
traveller-level branch-invariant draws, conservation, and full-drain checks
pass. It also validates five prior/new cells without mixing prior rows into
the estimates. The checked-in
[`compact package`](results/analysis/capacity_response_surface/README.md)
records the response slices, paired finite differences, interaction surface,
bottleneck map, and deterministic ideal comparator.

Run and validate the mean-preserving service-variability sensitivity:

1. In AnyLogic PLE 8.9.9, run
   `ServiceVariabilitySensitivity: OperationalCheckpointModel` and wait for
   `Finished`. The frozen contract is 9 CV cells × 50 serial replications.
2. Validate and package the complete result tree, then generate the two
   claim-bounded figures:

```powershell
.\.venv\Scripts\python.exe -m src.analysis.analyse_service_variability
.\.venv\Scripts\python.exe -m src.analysis.plot_service_variability_sensitivity
```

The analyser fails closed unless all 450 runs, frozen inputs, service-demand
contracts, conservation, full drain, traveller-level CRN alignment, and
cross-batch reproduction of the fixed-service reference pass. The
[`compact package`](results/analysis/service_variability/README.md) records
cell estimates, paired contrasts, factorial interactions, audit reports, and
the accepted figures.

Run and validate the selected-cell peak-duration sensitivity:

1. In AnyLogic PLE 8.9.9, run
   `PeakDurationSensitivity: OperationalCheckpointModel` and wait for
   `Finished`. The frozen contract is 20 cells x 50 serial replications.
2. Validate and package the complete result tree:

```powershell
.\.venv\Scripts\python.exe -m src.analysis.analyse_peak_duration_sensitivity
.\.venv\Scripts\python.exe -m src.analysis.plot_peak_duration_sensitivity
```

The analyser fails closed unless all 1,000 runs, frozen inputs, lineage,
entity-ledger reconstruction, conservation, zero-loss, full drain,
computational guards, exact same-duration/nested-prefix CRN alignment, and
T=300 cross-batch reproduction pass. The
[`compact package`](results/analysis/peak_duration_sensitivity/README.md)
records the 50-replication cell estimates, paired duration increments,
queue-growth diagnostics, audit reports, and the two claim-bounded figures.

Run the release gate. It includes a fail-closed check for tracked or embedded
source pixels, restricted media, identity/appearance fields, and reviewer alias
rules:

```powershell
.\.venv\Scripts\python.exe tools\precheck.py --run-tests
```

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
- Treat `config/confirmatory_capacity_study.json` and
  `config/confirmatory_seed_manifest.csv` as a frozen confirmatory contract;
  changing either creates a new study version and requires a full rerun.
- Treat `config/capacity_response_surface_study.json`, its scenario grid, and
  seed manifest as one frozen exploratory contract. Changing any of them
  creates a new response-surface study version and requires a full rerun.
- Treat `config/anylogic_gate_manifest.csv` only as a synthetic test oracle;
  it is not an approved operational parameter set.
- Do not hard-code decision parameters in Python or the simulation model.
- Regenerate the split AnyLogic fragments with
  `.\.venv\Scripts\python.exe scripts\generate_operational_anylogic.py` after
  an approved contract change, then rerun the contract and result gates.
- The interactive GUI is a four-zone mechanism demonstrator with live state
  and five real controls. It is not a calibrated physical checkpoint layout,
  spatial crowd model, digital twin, or standalone product.

## Restricted input

The target public release does not redistribute the assessment video.

1. Obtain `TestVidTask.mov` from the link supplied in the assessment.
2. Place it at `data/raw/TestVidTask.mov`.
3. Run the documented pipeline locally.

Generated videos or frames containing original pixels are also kept local.
Public documentation must use numerical audit tables and
trajectory/counting-line schematics that do not reproduce the source video.
The complete retention, reviewer-alias, no-re-identification, and release policy
is [`docs/privacy_and_data_governance.md`](docs/privacy_and_data_governance.md).

The two source-video-derived frames previously embedded in the canonical Task 4
deck were removed on 2026-07-29. They were replaced by a reviewed synthetic
AnyLogic screenshot and editable non-pixel measurement graphics. The
fail-closed public-media audit was rerun and returned zero findings. Remote
publication still requires final authorization and the clean-clone gate.

## Repository map

```text
config/       parameter provenance and scenario definitions
data/         local input instructions and generated tabular evidence
docs/         Task 1-3 reports and result-blind analysis plan
simulation/   selected simulation-engine project
src/          CV, input modelling, experiment, and analysis code
tests/        deterministic verification checks
results/      reproducible pilot and confirmatory evidence packages
slides/       Task 4 presentation
```

The assessment submission contains the Task 1 approach/results, Task 2 system
design, Task 3 design, execution and results documentation, and the Task 4
slide deck. Public release remains conditional on the governance and licensing
gates.
The completed five-slide deck is
[`slides/HTX_Task4_Operational_Insights.pptx`](slides/HTX_Task4_Operational_Insights.pptx).
