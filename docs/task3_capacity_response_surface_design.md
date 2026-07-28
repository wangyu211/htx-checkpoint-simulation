# Task 3 exploratory capacity response surface

## Status

`EXECUTED_AND_VALIDATED` on 2026-07-29.

This is a post-outcome exploratory extension. It does not alter the registered
Part 2 capacity-availability design, primary estimand, or completed 750-run
analysis.

The frozen contract was executed without changing the grid or replication
count. All `54 × 50 = 2,700` AnyLogic runs completed, and the compact analysis
package passed coverage, configuration-hash, lineage, seed, conservation,
full-drain, traveller-level CRN, and cross-batch reproducibility gates.

## Question

At the fixed Base arrival estimate, how does traveller delay change as the
number of concurrently open Security and Immigration service positions is
reduced? In particular:

1. Is the capacity-delay relationship approximately flat, gradual, or
   cliff-like?
2. Which stage becomes the active bottleneck first?
3. Does reducing both stages create additive delay, amplification, or upstream
   metering?

## Frozen grid

- Demand: `LOCAL_WINDOW_HPP_BASE`, 1.3642132969720073 travellers/second.
- Security capacity: every integer from 36 down to 28.
- Immigration capacity: every integer from 21 down to 16.
- Full factorial: 9 × 6 = 54 cells.
- Replications: 50 per cell, with common exogenous random-number streams.
- Reference: 36 Security / 21 Immigration.
- Exposure: arrivals on `[0, 300 s)` from an empty/idle start, then full drain.

The range crosses the approximate offered-workload thresholds:

- Security: `lambda × 21.818181818 = 29.7647` concurrent service positions.
- Immigration: `lambda × 13 = 17.7348` concurrent service positions.

This makes the design capable of revealing a performance cliff around
utilisation 1 instead of merely comparing a few arbitrary endpoints.

Capacity means concurrently open experimental service positions. It is not
evidence of an observed HTX roster, installed estate, one-to-one headcount
requirement, or realistic single-zone scale.

### Queueing-theory interpretation layer

For every simulated capacity point, the analysis reports:

- offered workload: `a = lambda × mean service time`;
- utilisation proxy: `rho = a / c`;
- safety capacity: `c - a`;
- square-root staffing index: `beta = (c - a) / sqrt(a)`.

For the reference Security setting, `a = 29.7647`, `c = 36`, and
`beta = 1.1429`. The same quantities will be shown for Immigration and all
reduced-capacity points, with the `rho = 1` boundary marked on the response
curves.

These quantities explain *where* accelerating delay should be expected and
provide a queueing-theory sanity check. They are not hard-coded into the DES.
The simulated waits remain the evidence, and `beta` is not treated as a
calibrated HTX service-level target.

### Ideal-case control

The analysis includes a separate deterministic ideal control with:

- perfectly regular arrivals spaced at `1 / lambda`;
- the same fixed service times;
- the same pooled parallel-server capacities and FCFS order;
- no arrival or service variability.

The stage throughput capacity `c / mean service time` is the straight-line
ideal benchmark against the fixed mean-demand line. The deterministic
two-stage queue oracle then shows what delay remains in that ideal system.
Only throughput capacity is forced to be linear: ideal queue delay can be flat
below saturation and increase after the threshold.

The comparison of stochastic HPP AnyLogic delay with this deterministic
control is labelled the variability/congestion penalty. The deterministic
oracle is an interpretive control, not a replacement for the AnyLogic
response-surface evidence.

## Self-contained execution and cross-batch validation

Five Base-demand cells already exist under validated configuration lineage and
common random numbers:

| Security | Immigration | Existing source |
|---:|---:|---|
| 36 | 21 | Registered Reference |
| 32 | 21 | Security -4 |
| 36 | 18 | Immigration -3 |
| 32 | 18 | Joint -4/-3 |
| 30 | 17 | Severe joint |

The response surface nevertheless reruns all 54 cells in one new AnyLogic
experiment:

- 54 cells × 50 replications = 2,700 new and analytical runs.
- Runs remain serial.
- All plotted response-surface values therefore come from one self-contained
  execution batch.
- The five old cells are not mixed into the surface. They serve as a
  cross-batch reproducibility check under exact configuration and seed tuples.

This costs only 250 more runs than a mixed-source surface and removes an
otherwise unnecessary batch-provenance complication.

## Outcomes

The primary descriptive outcome is the replication-level
`total_queue_wait_p95_seconds`. Supporting outcomes are:

- total mean queue wait;
- simultaneous peak total waiting queue;
- time-weighted mean total waiting queue;
- backlog at the arrival cutoff;
- cohort-clear time after cutoff;
- Security and Immigration stage-specific P95 waits.

The required views are:

1. Security-only slice with Immigration fixed at 21.
2. Immigration-only slice with Security fixed at 36.
3. A predeclared balanced joint-reduction path.
4. Full Security × Immigration delay heatmap.
5. Stage-bottleneck map.
6. Difference-in-differences interaction surface.
7. Queueing-theory overlay showing `rho`, safety capacity, and `beta`.
8. Stochastic AnyLogic response versus the deterministic ideal control.

Nonlinearity is described using adjacent marginal delay, second finite
differences, and threshold crossings. Simulation dots at integer capacities
are the evidence. Any shape-preserving smooth curve is only a visual guide and
must not imply that fractional service positions were simulated.

## Interpretation boundary

The accepted `1.364213/s` input is a directional corridor line-crossing rate,
not an observed arrival stream into a named processing unit. The experiment
conditionally maps the full rate into one pooled two-stage abstraction.
Physical processing-zone allocation, topology, routing, and sharing/overflow
rules are not identified by the clip.

Every cell uses a 300-second terminating arrival cohort from an empty and idle
start, followed by full drain. Fixed service requirements and homogeneous,
continuously available pooled resources further bound the interpretation.
Nominal `rho > 1` therefore marks a sustained-load stability warning even when
the finite cohort drains.

This study was designed after viewing Part 2 outcomes. It is therefore
exploratory sensitivity analysis: useful for operational insight and future
testable hypotheses, but not a new confirmatory finding. No multiplicity-free
p-value, calibrated site forecast, observed-roster inference, or staffing
recommendation is permitted.

The machine-readable frozen contract is
[`capacity_response_surface_study.json`](../config/capacity_response_surface_study.json).

## Executed evidence and interpretation

The run produced `8,100` fixed-schema raw files and `1,113,588` traveller
rows. The five previously available cells were used only for an external
reproducibility check; all `250` matched prior/new runs reproduced the checked
metrics exactly (maximum absolute difference `0.0`). They contribute no rows
to the response-surface estimates. The CRN gate compared `1,092,966`
traveller pairs and `6,557,796` branch-invariant random draws and returned
`PASS`, authorising paired finite differences and local interactions.

Across the 54 cell estimates, the mean replication-level total queue-wait P95
ranges from `3.929` to `35.920 s`, and the mean simultaneous peak total
waiting queue from `9.34` to `48.42` travellers. These are cell-level means,
not maxima over individual travellers or replications. The registered
illustrative `600 / 900 / 1200 s` exceedance rates are zero in the
[tracked diagnostic](../results/analysis/capacity_response_surface/threshold_exceedance_diagnostics.json);
they are not ICA service-level agreements.

At Immigration `21`, mean replication-level total queue-wait P95 rises from
`3.929 s` at Security `36` to `24.434 s` at Security `28`. At Security `36`,
it rises from `3.929 s` at Immigration `21` to `35.609 s` at Immigration
`16`. The one-position penalties accelerate monotonically across these
reference-stage slices:

| Reduction axis | First tested step | Mean paired penalty | Last tested step | Mean paired penalty |
|---|---:|---:|---:|---:|
| Security | `36 → 35` | `0.291 s` | `29 → 28` | `6.975 s` |
| Immigration | `21 → 20` | `1.313 s` | `17 → 16` | `14.682 s` |

The second finite differences for the primary P95 slice are positive, with
paired 95% intervals above zero. Within this fixed Base-demand sandbox, the
evidence therefore supports accelerating delay rather than a constant
seconds-per-position rule. The bend is consistent with the precomputed
offered-workload boundaries near Security `29.765` and Immigration `17.735`;
those queueing quantities are explanatory diagnostics, not fitted causes.

The full factorial surface also shows bottleneck migration. With Immigration
fixed at `16`, reducing Security from `36` to `31` barely changes total-wait
P95 (`35.609 s` to `35.613 s`) because Immigration dominates. Conversely,
with Security fixed at `28`, reducing Immigration from `21` to `17` changes
P95 only from `24.434 s` to `25.378 s` because Security dominates. Reducing
both stages is therefore not the sum of two isolated stage effects: upstream
Security capacity meters the arrival process seen by Immigration. For the
local `30/18 → 29/17` step, the paired difference-in-differences interaction
is `-4.021 s` (95% CI `[-4.721, -3.320]`). The negative sign is interpreted
as sub-additivity caused by serial flow and upstream metering, not as a
beneficial synergy.

The deterministic ideal control sharpens that interpretation. With regular
arrivals and fixed service, ideal total-wait mean and P95 are zero in `28` of
the `54` cells: Security `30–36` crossed with Immigration `18–21`. The other
`26` cells are exactly those where at least one nominal offered-load ratio
exceeds one; ideal total-wait P95 spans `7.287–30.519 s` there. The stochastic
AnyLogic surface already has positive delay below those ideal thresholds
because HPP arrival timing and count create transient queues. “AnyLogic minus
ideal” is consequently labelled a model-conditional stochastic-arrival /
congestion contrast with fixed service; it is not a paired causal
decomposition and does not measure service-time variability.

Auditable outputs are in the
[`capacity response-surface analysis package`](../results/analysis/capacity_response_surface/README.md).
