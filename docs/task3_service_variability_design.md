# Task 3 service-variability sensitivity — frozen design

## Status and purpose

Study ID: `TASK3_SERVICE_VARIABILITY_SENSITIVITY_V1`

Model version: `TASK3_OPERATIONAL_POOLED_SERVICE_VARIABILITY_V1`

Design status: `FROZEN_PRE_RUN`
Analysis role: `EXPLORATORY_ASSUMPTION_SENSITIVITY_NOT_CALIBRATION`

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

## Cross-batch check

The new `(CV Security=0, CV Immigration=0)` cell must reproduce the existing
Base `36/21` response-surface cell under the same seed tuples. The comparison
is a numerical reproducibility gate only. Old results are not copied into the
new estimates and are never overwritten.

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

This document freezes design intent only. It does not claim that the AnyLogic
service sampler or the 450-run experiment has already been implemented or run.
