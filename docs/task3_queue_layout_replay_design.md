# Task 3 queue-layout replay — frozen two-cell design

Status: **both frozen cells executed; reference replay gate and both
within-cell CRN gates passed**. Evidence is in
`results/analysis/queue_layout_replay/`.

The executable contract is
[`config/queue_layout_replay_study.json`](../config/queue_layout_replay_study.json).
This note explains why the comparison is valid, what must pass before a
contrast exists, and why the first result is intentionally scale-bounded.

## Question

Holding the realised traveller population, arrival times, work requirements,
stage order and counter count fixed, how does this model change when each
stage uses:

1. one pooled first-come-first-served queue; or
2. one queue per counter, with join-the-shortest-lane assignment at arrival
   and no later jockeying?

This is a mechanism counterfactual, not a statement about the queue rule at an
HTX/ICA site and not a staffing recommendation.

## Why replay the entity ledger

The current `OperationalCheckpointModel` already writes the immutable
traveller inputs required for a common-random-numbers comparison:

- stable `traveller_id`;
- `arrival_seconds`;
- Security work demand;
- Immigration primary and selected additional-check work demand; and
- branch-invariant `lane_tie_u`.

Using this ledger avoids drawing a second population for the alternative
layout. Every traveller therefore has exactly the same arrival and service
requirements in both arms. Only queue topology and routing change.

For tracked-input replay from a clean Git clone, after the pinned Python
environment is installed, the command defaults to the minimum curated package
in
[`data/derived/queue_layout_replay_source/`](../data/derived/queue_layout_replay_source/).
It contains 20,622 simulated AnyLogic entity rows and 50 registered P95
values. A strict field allowlist removes resource IDs, branch uniforms,
unused KPIs and repeated metadata; its manifest records file hashes,
provenance hashes and a privacy audit. These are simulated model entities,
not video-person events, tracker IDs, appearance data or biometric data.

The design contains two explicitly separated cells. Cell A is deliberately the
registered reference:

- `REFERENCE_ASSUMPTION_SANDBOX_V1`;
- `LOCAL_WINDOW_HPP_BASE`;
- 50 replications;
- 300-second arrival window followed by full drain;
- 36 Security and 21 Immigration service positions; and
- the existing `TASK3_OPERATIONAL_POOLED_V1` entity ledger.

Cell B is
`ILLUSTRATIVE_NORMALIZED_SMALL_SCALE`: multiply every source
`arrival_seconds` by five, use a 1,500-second arrival window, and set Security
and Immigration capacity to 6 and 4. This is approximately 0.273 arrivals/s.
Service demands, additional-check flags and `lane_tie_u` remain unchanged.
Cell B may execute only after Cell A's exact pooled gate passes. It is labelled
`TRANSPARENT_ASSUMPTION_MECHANISM_ONLY`; its pooled trajectory is not claimed
to have been generated or site-validated in AnyLogic.

The 36/21 values are the current **reference assumptions**, not observed
staffing. At that high-capacity, short-window scale, both layouts may have
little or no waiting and their contrast may be small or zero. Cell B makes the
scale dependence visible without disguising a capacity/demand transformation
as site evidence. Neither cell may be generalized to heterogeneous counter
skills, physical queue-space constraints, or behavioural lane choice.

## Exact mechanisms

### Pooled FCFS

Each stage has one FCFS queue feeding all counters. Arrivals are ordered by
`(stage_arrival_seconds, traveller_id)`. The next traveller starts at the
earliest available counter; exact counter-availability ties use the lowest
counter ID.

The pooled replay is not accepted merely because its aggregate mean looks
similar. For every traveller it must reproduce, within `1e-6` seconds:

- Security start and completion;
- Immigration queue join and start; and
- final exit.

The replayed within-replication P95 total wait must also match the registered
`replication_kpis.csv` value. Both use the project/AnyLogic nearest-rank
definition with zero-based index `ceil(0.95*n) - 1`. Any timestamp or KPI
mismatch fails the gate and blocks all layout contrasts.

### Separate shortest queues

Each counter owns one FCFS lane. A traveller chooses once, at stage arrival:

1. For each lane, count assigned travellers whose service completion is later
   than the arrival instant. This includes at most one traveller in service
   and all travellers waiting.
2. Identify all lanes with the smallest count.
3. Sort tied counter IDs ascending.
4. Choose index
   `min(floor(lane_tie_u * number_tied), number_tied - 1)`.
5. Remain in that lane until service; jockeying is prohibited.

Using number-in-lane rather than waiting-only length matters: an idle counter
has length zero and cannot tie with a busy counter that merely has no one
waiting behind it.

The same stored `lane_tie_u` is reused at Security and Immigration. It is a
deterministic routing input, not a new random draw. Every event log records the
full lane-length snapshot, ordered tie candidates, draw, selected tie index,
counter, queue join, service start, completion and wait. This makes the
separate mechanism auditable rather than a label on a pooled model.

## Serial coupling

The replay is a genuine two-stage system:

```text
original arrival
    -> replayed Security queue/service
    -> replayed Security completion
    -> replayed Immigration queue/service
    -> replayed exit
```

Immigration never receives the original logged join time in the alternative
arm; it receives the Security completion generated by that arm. Immigration
holds its counter for primary work plus any selected additional-check work,
matching the existing model semantics.

## Metrics

All metrics are computed within each replication before inference:

- nearest-rank P95 total Security-plus-Immigration queue wait;
- peak Security, Immigration and combined waiting queues;
- peak waiting in any single Security or Immigration lane; and
- fragmentation seconds at each stage and in total.
- stage-specific fragmentation fractions and a total stage-weighted fraction.

A waiting interval is half-open: `[queue_join, service_start)`. End events are
applied before starts at equal timestamps.

Fragmentation is the time measure for which at least one counter is idle while
a **different** counter's lane has someone waiting. It is exactly zero for a
work-conserving pooled queue by mechanism. For separate lanes it directly
quantifies stranded capacity caused by non-jockeying lane assignment. The
integration window is first stage arrival through final stage completion.
The Security and Immigration fractions divide by their own
`final_completion - first_arrival` spans. The total fraction divides the sum
of both fragmentation durations by the sum of both stage spans.

## Fail-closed inference

For Cell A, paired Student-t intervals for `separate minus pooled` are produced
only when all three conditions pass:

1. every pooled timestamp and the registered P95 replay exactly;
2. traveller sets and SHA-256 hashes of sorted immutable traveller inputs are
   identical across layouts; and
3. the exact frozen replication set `1..50` is present.

Cell B is not executed at all until Cell A's exact gate passes. Its own paired
contrast additionally requires an identical transformed traveller set/hash
between layouts and the exact 50 replications. There is no automatic Welch
fallback. If any gate fails,
`paired_contrasts.csv` is not written and the requested output directory is
not created. This prevents a partially validated folder from looking like a
completed result.

`cross_scale_mechanism_summary.csv` then reports, for each comparable metric, the
reference layout effect, the illustrative layout effect, and their paired
difference. Its claim boundary explicitly says that the normalized small scale
is a transparent mechanism probe, not AnyLogic or site validation. Raw
fragmentation seconds remain available within each cell but are deliberately
excluded from the cross-scale summary because the observation horizons are
300 versus 1,500 seconds. Only dimensionless fragmentation fractions are
compared across scales.

## Run contract

The public curated source tables and their privacy/hash manifest are the CLI
defaults. After installing the pinned Python environment, a clean Git clone
therefore needs only an explicitly new output directory:

```powershell
.\.venv\Scripts\python.exe -m src.analysis.analyse_queue_layout_replay `
  --output-dir <new-audited-output-directory>
```

The analyser verifies the curated entity-ledger hash, registered-P95 hash,
manifest hash, field allowlists, synthetic-ID pattern and privacy status
before parsing a traveller. Custom source tables must provide a matching
`--source-manifest`; the broad ignored local ledger is no longer required for
public reproduction.

On a complete pass it writes:

- local-only
  `results/intermediate/queue_layout_replay/replay_events.public_source_lf.csv`
  — counter-specific events for both stages and layouts;
- `replication_metrics.csv`;
- `pooled_replay_validation.json`;
- `crn_validation.json`;
- `paired_contrasts.csv`;
- `cross_scale_mechanism_summary.csv`;
- `counter_event_audit_digest.json`; and
- `analysis_manifest.json` with input/design hashes and the claim ceiling.

The full counter-event ledger is about 70 MB and is intentionally ignored as
a local intermediate. It must not enter the public repository or submission
ZIP. The compact public digest records its SHA-256, row count and coverage by
cell/layout/stage so the local evidence remains attributable.

## Executed evidence

The frozen command completed across 50 replications per cell:

- Reference pooled replay: `PASS`; 164,976 traveller timestamp/wait
  comparisons plus 50 registered P95 comparisons, zero mismatches, maximum
  absolute error about `1.01e-9` seconds.
- Reference within-cell CRN: `PASS`.
- Illustrative normalized small-scale within-cell CRN: `PASS`.

At reference scale, separate minus pooled increased the mean
within-replication P95 total wait by **7.58 seconds** (95% paired CI
**6.97 to 8.19**) and peak total queue by **1.78 travellers** (95% CI
**1.35 to 2.21**). At illustrative normalized small scale, the corresponding
P95 contrast was **7.04 seconds** (95% CI **6.24 to 7.84**) and the peak-total
contrast was **1.62** (95% CI **1.38 to 1.86**).

Separate-lane fragmentation occupied an additional **0.289** of the summed
stage observation spans at reference scale (95% CI **0.264 to 0.314**) and
**0.143** at the illustrative normalized scale (95% CI **0.136 to 0.149**).
The raw fragmentation seconds are retained within each cell, but the
cross-scale table intentionally compares these dimensionless fractions
instead of conflating a 300-second and 1,500-second horizon.

These are conditional model-mechanism results. The second cell remains a
transparent assumption probe, and neither cell establishes the site's actual
queue policy, staffing, service-time distribution, or forecast performance.
