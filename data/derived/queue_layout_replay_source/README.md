# Queue-layout replay source

This directory is the public, minimum input package for the exact-gated
pooled-versus-separate queue replay.

It contains **synthetic AnyLogic events only**:

- `entity_ledger.csv`: 20,622 simulated traveller rows across 50 registered
  replications;
- `registered_p95.csv`: the 50 registered within-replication pooled P95 values
  used by the exact replay gate;
- `manifest.json`: field allowlists, row counts, source provenance hashes,
  byte-level file hashes, and the privacy audit.

`traveller_id` is a deterministic simulated-entity identifier. It is not a
name, face token, tracker identity, or permanent real-person identifier. The
package contains no video paths, frames, appearance descriptions, biometric
features, embeddings, resource identifiers, or observed-person event data.
The broad local AnyLogic ledger was reduced to only replication, immutable
service inputs, and the six pooled event timestamps needed for replay and
validation.

From a clean clone, the queue-layout study can use these inputs by default:

```powershell
python -m src.analysis.analyse_queue_layout_replay `
  --output-dir results/analysis/queue_layout_replay_rerun
```

The output remains a conditional two-cell mechanism counterfactual. This
public source does not convert the assumption sandbox into site validation,
identify the current HTX/ICA queue policy, or support a staffing decision.
