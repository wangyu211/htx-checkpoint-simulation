# Service-variability sensitivity evidence package

## Evidence status

`TASK3_SERVICE_VARIABILITY_SENSITIVITY_V1` was executed and validated on
2026-07-29.

| Gate | Outcome |
|---|---:|
| Factorial | Security CV `{0, 0.5, 1.0}` × Immigration CV `{0, 0.5, 1.0}` |
| Replications | `50` per cell |
| AnyLogic runs | `450 / 450` |
| Traveller entity rows | `185,598` |
| Raw result files | `1,350` |
| Strict validation | `PASS` |
| CRN alignment | `PASS` |
| Fixed-cell cross-batch reproducibility | `PASS` |

This is exploratory assumption-sensitivity evidence, not calibration. The
positive CV values are mean-preserving lognormal assumptions; they were not
measured in the supplied video or at an HTX checkpoint.

## Frozen question and mechanism

The study varies stage-local service-time CV while holding arithmetic mean
service demand and every other registered mechanism fixed:

- Base HPP arrival input: `1.3642132969720073 /s`;
- 300-second arrival window, empty/idle start, then full drain;
- pooled FCFS queues;
- Security: model-reference capacity `36`, mean demand
  `21.818181818 s`;
- Immigration: model-reference capacity `21`, mean demand `13 s`;
- automation disabled and no additional checks.

The `36/21` capacities are target-utilisation-derived model references, not an
observed roster, current deployment, or staffing recommendation.

## Main descriptive result

The pre-specified comparison is joint `CV=1.0` minus joint `CV=0`, using 50
paired replication-level differences and 95% Student-t intervals:

| Metric | CV zero | Joint CV 1.0 | Paired difference, 95% CI |
|---|---:|---:|---:|
| Total queue-wait P95 | `3.929 s` | `5.597 s` | `+1.668 s` `[0.677, 2.660]` |
| System-time P95 | `38.747 s` | `82.218 s` | `+43.471 s` `[41.565, 45.376]` |
| Peak total waiting queue | `9.34` | `12.08` | `+2.74` `[1.21, 4.27]` |
| Cohort clear after cutoff | `35.365 s` | `131.357 s` | `+95.993 s` `[81.162, 110.823]` |
| Cutoff backlog | `50.66` | `51.56` | `+0.90` `[-0.93, 2.73]` |

Under the frozen model, mean-preserving variability affects end-to-end tail
time and recovery much more strongly than the primary queue-wait P95. The
cutoff-backlog contrast remains unresolved, so no backlog-increase claim is
made.

Immigration-only `CV=1.0` increases total queue-wait P95 by `1.660 s`
(`[0.698, 2.623]`). The Security-only queue-wait contrast is unresolved at
`+0.042 s` (`[-0.410, 0.494]`), although Security-only system-time P95 rises
by `35.181 s` (`[33.614, 36.748]`). The queue-tail and end-to-end-tail metrics
therefore answer different questions.

The joint `CV=1.0` total-queue-P95 factorial interaction is unresolved:
`-0.033 s` (`[-0.618, 0.551]`). The package does not claim synergistic or
superlinear queue amplification.

## Package contents

- [`validation.json`](validation.json): fail-closed coverage, lineage,
  conservation, full-drain, guard, drop/rejection, service-demand, CRN, and
  cross-batch status.
- [`crn_alignment.json`](crn_alignment.json): exact arrival/routing/tie
  alignment and stage-local latent-normal alignment.
- [`cross_batch_reproducibility.json`](cross_batch_reproducibility.json):
  exact fixed-cell event-ledger and KPI reproduction against the prior
  `36/21` response-surface batch.
- [`analysis_manifest.json`](analysis_manifest.json): hashes, row counts,
  source lineage, and output inventory.
- [`raw_audit_manifest.json`](raw_audit_manifest.json): immutable raw-tree
  digest without copying raw entity ledgers into this compact package.
- [`service_variability_by_replication.csv`](service_variability_by_replication.csv):
  one validated KPI row per run.
- [`cell_estimates.csv`](cell_estimates.csv): cell-level estimates and
  across-replication intervals.
- [`paired_contrasts_vs_reference.csv`](paired_contrasts_vs_reference.csv):
  CRN-gated paired differences from `CV=0/0`.
- [`factorial_interactions.csv`](factorial_interactions.csv): descriptive
  paired factorial interactions.
- [`heatmap.csv`](heatmap.csv), [`security_only_slice.csv`](security_only_slice.csv),
  [`immigration_only_slice.csv`](immigration_only_slice.csv), and
  [`balanced_joint_slice.csv`](balanced_joint_slice.csv): compact plotting
  views for total queue-wait P95.
- [`analysis_payload.json`](analysis_payload.json): compact machine-readable
  plotting and reporting payload.

Raw run files remain under `results/raw/service_variability/`; they are
validated and hash-bound but are not duplicated in this compact package.

## Reproduce

Open the single-file AnyLogic model and run
`ServiceVariabilitySensitivity: OperationalCheckpointModel` until the
experiment reports `Finished`:

```text
simulation/anylogic/HTXCheckpointSimulationCLI/HTXCheckpointSimulationCLI.alp
```

Then rebuild the fail-closed analysis package from the repository root:

```powershell
.\.venv\Scripts\python.exe -m src.analysis.analyse_service_variability
```

The command refuses to emit paired results unless all 450 registered runs,
strict runtime validation, CRN alignment, and cross-batch reproducibility
pass.

## Interpretation limits

- CV `0.5` and `1.0` are uncalibrated assumptions, not observed variability.
- CV `1.0` uses a mean-preserving lognormal family; it is not an exponential
  service or M/M/c claim.
- The accepted corridor rate is conditionally routed into one pooled
  two-stage abstraction; processing-unit allocation is unobserved.
- The experiment is a terminating 300-second cohort, not a steady-state or
  time-of-day model.
- System-time and clear-time changes include service-tail effects; they must
  not be described as queue delay alone.
- Confidence intervals quantify Monte Carlo error conditional on fixed model
  inputs. They exclude input uncertainty and model-form error.
- No calibrated baseline, site forecast, staffing recommendation, cost
  optimum, or operational SLA claim is supported.
