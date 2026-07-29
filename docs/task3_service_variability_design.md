# Task 3 service-variability sensitivity — frozen design and execution record

## Status and purpose

Study ID: `TASK3_SERVICE_VARIABILITY_SENSITIVITY_V1`

Model version: `TASK3_OPERATIONAL_POOLED_SERVICE_VARIABILITY_V1`

Design status: `FROZEN_EXECUTED`
Analysis role: `EXPLORATORY_ASSUMPTION_SENSITIVITY_NOT_CALIBRATION`
Execution status: `EXECUTED_AND_VALIDATED`
Execution date: `2026-07-29`

The `ServiceVariabilitySensitivity` AnyLogic experiment, the independent
stage-local service RNGs, and the fail-closed Python analysis layer were
executed without changing the frozen factorial. All `9 × 50 = 450` registered
runs and `185,598` traveller entity rows passed exact coverage, schema,
lineage, extended configuration-hash, registered-seed, conservation,
full-drain, guard, drop/rejection, service-demand, CRN-alignment, and
cross-batch reproducibility gates.

The registered 300-second capacity studies use fixed Security and Immigration
service demands. Fixed service is a low-variability modelling assumption; it
is not evidence that real processing times are constant. This independent
study asks whether the model's decision-facing delay and queue conclusions are
sensitive to positive service-time variability while holding the arithmetic
means and every other mechanism constant.

The study does **not** replace or alter the confirmatory capacity study, the
capacity-availability study, or the exploratory capacity response surface.
Their configurations, hashes, raw outputs, and interpretations remain frozen.
The independent model version distinguishes the new service-sampling
mechanism from both the study identifier and the existing fixed-service
`TASK3_OPERATIONAL_POOLED_V1` mechanism in future run manifests.

## Fixed mechanism

| Input | Frozen value |
|---|---:|
| Arrival process | HPP |
| Arrival input | `LOCAL_WINDOW_HPP_BASE` |
| Arrival rate | `1.3642132969720073 /s` |
| Arrival cutoff | `300 s` |
| Start / termination | empty and idle / full drain |
| Security capacity | `36` open positions |
| Security mean service demand | `21.818181818 s` |
| Immigration capacity | `21` open positions |
| Immigration mean service demand | `13 s` |
| Queue policy | pooled FCFS |
| Automation | disabled |
| Additional checks | none |
| Calibration status | not calibrated |

The 36/21 capacities are the existing target-utilisation-derived model
reference, not an observed roster or staffing recommendation.

## Frozen factorial

Security CV and Immigration CV are crossed independently:

```text
Security CV    = {0, 0.5, 1.0}
Immigration CV = {0, 0.5, 1.0}
```

This produces nine cells. Every cell has 50 replications, for 450 runs.
Parallel evaluations and adaptive post-outcome extensions are prohibited.

CV zero is the fixed-service reference. The positive CV values are transparent
sensitivity assumptions. They were not measured in the supplied corridor
video or at an HTX checkpoint.

## Distribution parameterisation

For CV zero, service demand equals the registered arithmetic mean.

For positive CV, the study uses a mean-preserving lognormal family:

```text
sigma²  = ln(1 + CV²)
service = mean × exp(-0.5 × sigma² + sqrt(sigma²) × Z)
Z       ~ Standard Normal
```

`security_service_p1_seconds` and
`immigration_service_p1_seconds` continue to mean arithmetic mean seconds.
Positive-CV service demands are strictly positive. `CV=1` is a lognormal
sensitivity, not an exponential-service or M/M/c claim.

## Configuration isolation

The frozen v1 `SCENARIO_COLUMNS` and `scenario_config_sha256()` are not
changed. This study appends two local fields:

```text
security_service_cv
immigration_service_cv
```

Its scenario rows use a separate canonical hash covering the old fields plus
both CV fields. This prevents the new sensitivity inputs from changing any
existing configuration hash while still binding every new result to the exact
CV settings that produced it.

## Seed and CRN contract

For each replication, all nine cells copy the exact Base tuple from
`config/confirmatory_seed_manifest.csv`:

```text
master_seed
arrival_seed
service_seed
routing_seed
tie_seed
```

The intended runtime implementation uses separate, deterministic
Security-service and Immigration-service RNGs derived from `service_seed`.
It must never use the AnyLogic default generator, which remains reserved for
the HPP arrival stream.

The implemented derivation is frozen and tested:

```text
Security RNG seed    = service_seed XOR 0x13579BDF2468ACE1
Immigration RNG seed = service_seed XOR 0x2468ACE113579BDF
normal draw          = explicit two-uniform Box-Muller transform
```

The fixed arm returns the arithmetic mean without consuming either service
stream. Positive-CV cells therefore share stage-local latent draws with one
another; the deterministic arm shares the arrival, routing, and tie streams
only.

The CRN gate must verify:

1. exact 9 × 50 coverage and registered seed tuples;
2. identical traveller IDs and arrival timestamps across all nine cells within
   a replication;
3. identical automation, additional-check, and tie draws;
4. within each stage, identical implied latent standard-normal values across
   the positive-CV cells;
5. fixed service demands equal the registered means in every CV-zero arm.

CV-zero service has no random shock. The fixed-versus-variable comparison
therefore claims shared arrival/routing/tie streams, not a fictitious service
shock in the deterministic arm. Paired intervals are enabled only after the
applicable alignment checks pass.

## Frozen analysis

The primary descriptive metric is the within-replication P95 total queue wait.
The principal descriptive comparison is joint CV 1.0 minus joint CV zero.

Supporting outputs include:

- stage-specific and total wait;
- peak and time-weighted queue;
- cutoff backlog and post-cutoff clear time;
- system-time P95, P99, and maximum;
- Security-only and Immigration-only CV slices;
- the balanced joint-CV path;
- the complete 3 × 3 heatmap;
- factorial interaction.

All uncertainty is calculated across independent replications. Results use
95% Student-t intervals. No confirmatory p-value, calibrated distribution
claim, or staffing recommendation is permitted.

## Accepted descriptive result

The pre-specified joint `CV=1.0` minus joint `CV=0` comparison uses 50 paired
replication-level differences:

| Metric | Joint CV zero | Joint CV 1.0 | Paired difference, 95% CI |
|---|---:|---:|---:|
| Total queue-wait P95 | `3.929 s` | `5.597 s` | `+1.668 s` `[0.677, 2.660]` |
| System-time P95 | `38.747 s` | `82.218 s` | `+43.471 s` `[41.565, 45.376]` |
| Peak total waiting queue | `9.34` | `12.08` | `+2.74` `[1.21, 4.27]` |
| Cohort clear after cutoff | `35.365 s` | `131.357 s` | `+95.993 s` `[81.162, 110.823]` |
| Cutoff backlog | `50.66` | `51.56` | `+0.90` `[-0.93, 2.73]` |

The model-conditional insight is that mean-preserving service-time
variability has a much larger effect on end-to-end tail time and post-cutoff
recovery than on the primary queue-wait P95. The unresolved cutoff-backlog
interval also shows that a count at one instant is not a substitute for a
full-drain recovery metric.

At `CV=1.0`, Immigration-only variability increases total queue-wait P95 by
`1.660 s` (95% CI `[0.698, 2.623]`), whereas the Security-only queue-wait
contrast is unresolved at `+0.042 s` (`[-0.410, 0.494]`). Security-only
variability nevertheless increases system-time P95 by `35.181 s`
(`[33.614, 36.748]`). Queueing tail and end-to-end service tail therefore
represent different risks in this sandbox.

The joint `CV=1.0` total-queue-P95 factorial interaction is `-0.033 s`
(`[-0.618, 0.551]`). No resolved synergy, amplification, or general
nonlinearity claim is made from this interaction.

## Cross-batch check

The new `(CV Security=0, CV Immigration=0)` cell reproduced the existing Base
`36/21` response-surface cell under the same seed tuples. The gate passed all
50 matched runs: seed tuples matched exactly, all `20,622 × 20` compared
entity-event values matched exactly, and 750 compared metric values had
maximum absolute difference `0.0`.

This is a numerical reproducibility gate only. The prior batch contributes
zero rows to the new estimates and was not overwritten.

## Runtime acceptance criteria

Before any result is interpreted:

- all 450 run directories must exist exactly once;
- every run must finish, fully drain, and pass conservation;
- no arrival guard, queue guard, rejection, or drop may occur;
- scenario hashes and all seed fields must match the frozen registries;
- fixed demands must equal the registered means exactly;
- variable demands must be finite and strictly positive;
- the cross-batch fixed-service check must pass;
- the applicable CRN alignment report must explicitly return `PASS`.

All criteria above returned `PASS` on 2026-07-29. The accepted evidence remains
an exploratory, non-calibrated assumption sensitivity. The `36/21` capacities
are a target-utilisation-derived model reference, not an observed roster or
staffing recommendation. The positive CVs are transparent mean-preserving
lognormal assumptions, not service distributions measured from the supplied
video or an HTX checkpoint. Confidence intervals quantify Monte Carlo error
conditional on the frozen inputs; they do not include input uncertainty or
model-form error.
