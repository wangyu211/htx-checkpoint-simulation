# AnyLogic deterministic two-stage verification

**Status:** PASS  
**Execution date:** 2026-07-27  
**Engine:** AnyLogic PLE 8.9.9.202607020720  
**Experiment:** `TwoStageDeterministic: CheckpointModel`

> Post-refactor note, 2026-07-27: the verified literal oracle inputs were
> externalised as explicit model/experiment parameters in the split ALPX and
> single-file ALP sources. Static XML, contract-alignment, and exact-arrival
> reconstruction tests pass. The post-refactor split ALPX GUI run reached
> `Finished`; the single-file ALP GUI run then did the same. All three output
> hashes below remained byte-identical after both runs.

## Claim boundary

This is an exact synthetic mechanism verification, not an operational
baseline, calibrated site forecast, or scenario result. It verifies that the
implemented discrete-event chain correctly handles two sequential finite
resources, queues, a live arrival cutoff, full drain, entity timestamps, output
schemas, and metric calculations.

It does not yet verify separate-versus-pooled Immigration queues, technology
uptake, additional checks, stochastic input sampling, CRN pairing, operational
parameters, the full dashboard, or external/site validity.

## Implemented mechanism

```text
travellerSource
  -> securityService [securityResources, capacity 1]
  -> immigrationService [immigrationResources, capacity 1]
  -> checkpointSink
```

The mechanism is isolated in `CheckpointModel` and uses
`CheckpointTraveller`, without changing `Main`, `Traveller`, or
`GatePV2x3`'s process flow, stochastic seeds, or export contract. The gate's
separate GUI auto-start adapter does not participate in this mechanism.

## Exact oracle

| Quantity | Expected |
|---|---:|
| Arrival times | 0, 0.5, 1.0, 1.5, 2.5, 3.5 s |
| Security demand | exactly 2 s |
| Immigration demand | exactly 3 s |
| Cutoff | 6.5 s |
| Completed at cutoff | 1 |
| Security queue / in service | 2 / 1 |
| Immigration queue / in service | 1 / 1 |
| WIP at cutoff | 5 |
| Exit times | 5, 8, 11, 14, 17, 20 s |
| Drain end | 20 s |
| Clear time after cutoff | 13.5 s |

Conservation at cutoff is exact:

```text
1 completed
+ 2 waiting at Security
+ 1 in Security service
+ 1 waiting at Immigration
+ 1 in Immigration service
= 6 admitted
```

## Validated output

The independent validator checks exact schemas and lineage, one manifest row,
one summary row, six unique traveller rows, every expected timestamp, legal
event order, both service demands, lane/resource labels, the cutoff tuple, full
drain, and every exported mean/P95 metric.

Observed summary:

| Metric | Observed |
|---|---:|
| Security wait mean / P95 | 3.5 / 6.5 s |
| Immigration wait mean / P95 | 2.5 / 5.0 s |
| Total queue wait mean / P95 | 6.0 / 11.5 s |
| System time mean / P95 | 11.0 / 16.5 s |
| Cutoff backlog | 5 |
| Clear time after cutoff | 13.5 s |

Run the validator from the repository root:

```powershell
.\.venv\Scripts\python.exe -m src.analysis.validate_anylogic_two_stage
```

Recorded result:

```text
status = PASS
errors = []
reproducibility.byte_identical = true
```

The split/single-file comparison is run with:

```powershell
.\.venv\Scripts\python.exe -m src.analysis.validate_anylogic_two_stage `
  --reference-dir results\intermediate\anylogic_two_stage_verification\reference_split_run
```

The tested single-file `-r` path opened a visible PLE window and auto-executed
to `Finished`; this is not a headless or standalone execution claim.

## Output hashes

Hashes below are SHA-256 for both the successful source-ALPX GUI run and the
single-file ALP `-r` run. All three files were byte-identical:

| File | SHA-256 |
|---|---|
| `run_manifest.csv` | `25e259657fa7accc549a357dd4fcd36b51387342ada1453182f56a7327f8e7af` |
| `entity_log.csv` | `e18668877d26f3c17df96b5f260e48109538e711e8f690f5309d53e3253fac17` |
| `run_summary.csv` | `2dfdd0ae5d510ab815d77d18854b99ba340894f0c137aed079907205d15a3e0e` |

The raw files are regenerated under
`results/raw/anylogic_two_stage_verification/`; the machine-readable validator
report is written under
`results/intermediate/anylogic_two_stage_verification/`.

## Defects caught during verification

The verification process caught two silent failure modes before this PASS:

1. the Event existed and was timed correctly, but its GUI Action was empty, so
   cutoff snapshots remained at their sentinel value;
2. Source evaluates its next interarrival expression before the `On exit`
   callback increments `admitted`, shifting the fifth and sixth arrivals by
   0.5 seconds until the threshold was corrected.

Both defects left the final drain time at 20 seconds, demonstrating why
per-entity logs and an exact independent oracle are necessary in addition to a
visually successful animation.
