# Assessment Requirements Traceability

Status values: `PLANNED`, `IN PROGRESS`, `VERIFIED`.

## Assessment capabilities

| Requirement | Planned evidence | Status |
|---|---|---|
| Model a real operational system | Executable two-stage event-driven DES and explicit assumption boundary | VERIFIED |
| Basic AI inference for data collection | Person detection, tracking, directional aggregate, human adjudication and fallback audit | VERIFIED |
| Interactive simulation | Four-zone 2D process view, live state metrics, exactly five bounded pre-run controls, and built-in run controls | VERIFIED |
| Maintainable solution | External contracts, generated model fragments, schemas, validators and extension documentation | VERIFIED |
| Actionable insights | Controlled pilot scenarios, uncertainty and conditional findings | VERIFIED |
| Clear communication | Task 1-3 reports and five claim-driven content slides | COMPLETE |

`VERIFIED` here means that the stated software/evidence capability passed its
declared gate. It does not mean the model is calibrated to an HTX site.

## Task 1 - Data collection

- [x] Use the supplied short video to determine the accepted directional
      aggregate and the mapped short-window arrival-rate input.
- [x] Treat the observed crowd as characteristic only for the modelled baseline
      entrance area, while documenting the extrapolation limitation.
- [x] Record the primary YOLO26m/BoT-SORT candidate path, the licence-friendlier
      YOLOX-S/Supervision-ByteTrack fallback, human adjudication, estimates,
      limitations, and model use.

Task 1 is verified at aggregate level. The accepted evidence is not represented
as a signed event-time ledger, and the 24.922788889-second observed rate is not
claimed to estimate long-run checkpoint demand.

## Task 2 - Systems design

- [x] Version 0.4 maps the brief's five requested items directly to sections
  A-E in `docs/task2_system_design.md`.
- [x] Implemented pooled flow, proxy mechanisms, blocked inputs, and deferred
  extensions are visibly separated.
- [x] Major entities/resources, reference inputs, and the 15-scenario matrix.
- [x] Exported v1 outputs, replication estimands, and uncertainty method.
- [x] Classified assumptions, claim boundary, exclusions, and V&V status.

## Task 3 - Simulation implementation

### Core-requirement cross-check

| Brief minimum | Executed evidence | Status |
|---|---|---|
| 2D representation | Four labelled Arrival, Security, Immigration, and Exit zones in `OperationalInteractive` | VERIFIED |
| Traveller movement through both stages | Native `Source -> Service -> Service -> Sink` traveller flow | VERIFIED |
| Queueing at both stages | Pooled FCFS queues with live queue counts at Security and Immigration | VERIFIED |
| Finite processing resources | Separate finite AnyLogic `ResourcePool` objects for both stages | VERIFIED |
| User-adjustable inputs | Five genuine pre-run controls: demand, two capacities, uptake, and automation multiplier | VERIFIED |
| Operational outputs | Live state plus post-run queue, wait, utilization, throughput, cutoff, and recovery evidence | VERIFIED |
| Multiple scenarios / experiments | 15 × 10 pilot and frozen 4 × 3 × 50 confirmatory capacity study | VERIFIED |

The four-zone display is a schematic process view, not a calibrated physical
layout or spatial digital twin.

- [x] Native AnyLogic model opens, compiles, and runs in PLE 8.9.9.
- [x] GUI experiment executes two input samples × three replications.
- [x] Fixed-schema manifest, entity, and summary CSV export.
- [x] Explicit seed lineage and distinct replication fingerprints.
- [x] Byte-identical GUI rerun.
- [x] Single-file ALP `-r` visible-GUI launch path: `GatePV2x3` uses a tested
  one-shot timer adapter; `TwoStageDeterministic` uses its native Simulation
  experiment bypass; both auto-execute to `Finished`.
- [x] Exact six-traveller deterministic two-stage oracle.
- [x] Live 6.5-second cutoff snapshot and cutoff-flow conservation.
- [x] Full drain with exact per-traveller event-time validation.
- [x] Machine-readable model-run configuration contract with fail-fast
  readiness validation and no hidden operational defaults.
- [x] Deterministic-oracle inputs externalised as explicit parameters in both
  AnyLogic source formats; both post-refactor GUI runs are byte-identical.
- [x] Split-model HPP arrival-only demand mechanism at 1.364213/s with a live
  24.922788889-second cutoff, explicit `[0,T)` boundary, and 49000-arrival PLE
  guard.
- [x] Fixed-seed (`2026072710`) HPP run with 32 arrivals conserved across the
  ledger, manifest, Source, Sink, and summary.
- [x] Two split HPP runs plus the synchronized single-file ALP run with three
  byte-identical CSV outputs and independent validator `PASS` under the
  explicit `ARRIVAL_ONLY` readiness scope.
- [ ] Headless or standalone execution; not claimed by the current evidence.
- [x] Executable pooled-FCFS two-stage Task 3 mechanism with HPP arrivals,
  finite resources, a live 300-second cutoff, and full drain.
- [x] Task 2-to-Task 3 consistency for the implemented v1 pooled flow,
  technology service multiplier, and counter-held additional-work proxy.
- [x] `OperationalInteractive` four-zone 2D
  Arrival → Security → Immigration → Exit presentation.
- [x] Traveller flow through Security and Immigration for the deterministic
  mechanism milestone.
- [x] Queueing and one-unit finite resource constraints at both stages for the
  deterministic mechanism milestone.
- [x] Registered v1 operational assumption parameters externalised in
  `config/operational_scenarios.csv`, with provenance and fail-closed
  canonical-hash validation.
- [x] `OperationalPilot` completed 15 registered scenarios × 10 independent
  replications: 150/150 runs and 61,218 traveller rows passed strict schema,
  lineage, seed, event-order, conservation, zero-loss, and full-drain
  validation. AnyLogic enforces finite-resource operation; an independent
  per-resource interval-overlap audit has not been performed.
- [x] Post-run scenario dashboard, replication-level estimates, 95% confidence
  intervals, and scenario contrasts.
- [ ] Genuinely separate per-counter queues versus pooled FCFS; v1 implements
  pooled FCFS only, so no queue-policy effect is claimed.
- [ ] Pilot traveller-level common-random-number alignment; pilot status
  remains `NOT_TESTED`, so its contrasts use independent Welch intervals.
- [x] `CapacityRobustnessConfirmatory` auto-starts in the visible Parameter
  Variation window and executes 12 cells × 50 replications serially. Exact
  600/600 coverage and 253,756 entities passed strict validation.
- [x] Confirmatory traveller-level CRN alignment: `PASS` across 150 within-rate
  replication groups, enabling the pre-specified paired analysis.
- [x] Interactive controls and live state: exactly five genuine pre-run fields
  (`demand_multiplier`, `security_capacity`, `immigration_capacity`,
  `automation_uptake`, and `automation_multiplier`) plus live queue,
  in-service, completed, and status metrics.
- [x] Pooled FCFS is the only implemented queue policy; no fake queue-policy
  selector is exposed.

The historical HPP milestone still verifies only the demand mechanism. The
operational pilot and confirmatory study are separate, not-calibrated
assumption-sandbox executions: their service times, capacities, queue guards,
automation mappings, and risk bounds are registered context or transparent
sensitivity inputs, not parameters identified from the video. The interactive
run is exploratory/ad-hoc; reportable claims come from validated replication
outputs. Results remain comparative and conditional, not site forecasts or
final staffing recommendations.

Recorded evidence:

- [`Task 3 results report`](task3_results.md)
- [`results/analysis/operational/README.md`](../results/analysis/operational/README.md)
- [`operational dashboard`](../results/analysis/operational/operational_dashboard.png)
- [`strict validation report`](../results/analysis/operational/validation.json)
- [`confirmatory compact audit manifest`](../results/analysis/confirmatory_capacity/audit_manifest.json)
- [`confirmatory strict validation`](../results/analysis/confirmatory_capacity/validation.json)
- [`confirmatory CRN alignment`](../results/analysis/confirmatory_capacity/crn_alignment.json)
- [`confirmatory primary result`](../results/analysis/confirmatory_capacity/primary_result.json)

## Task 4 - presentation

- [x] Maximum five content slides.
- [x] Problem overview.
- [x] Simulation design and assumptions.
- [x] Baseline performance.
- [x] Scenario comparison.
- [x] Recommendations and operational insights.

Evidence:

- [`HTX_Task4_Operational_Insights.pptx`](../slides/HTX_Task4_Operational_Insights.pptx)

## Public repository

- [x] Separate public-delivery directory from private working material.
- [x] README: setup, engine version, run/build instructions, parameter changes.
- [x] Source and split AnyLogic project files needed for the documented GUI
  workflow.
- [x] Task 1 approach/results.
- [x] Task 2 requirements/design.
- [x] Task 3 simulation logic and key outputs/metrics.
- [x] Task 4 slides.
- [x] Current release commit passes the clean-clone precheck: clean tree,
  129 tests, 143 local links, and all compact-evidence hash contracts.
- [ ] Repository URL ready for submission by email.
