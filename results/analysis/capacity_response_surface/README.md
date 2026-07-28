# Capacity response-surface analysis

`TASK3_CAPACITY_RESPONSE_SURFACE_EXPLORATORY_V1` is a post-outcome exploratory sensitivity study at fixed Base demand. It maps the 9 Security capacities (36 to 28) by 6 Immigration capacities (21 to 16), with 50 replications per cell (2,700 AnyLogic runs).

The primary descriptive response is the mean replication-level P95 total queue wait. Cell intervals, one-position marginal penalties, second finite differences, and local difference-in-differences interactions all use the 50 replication units. Paired quantities are released only after exact registered seeds and traveller-level branch-invariant draws align across all cells.

Queue peaks are reconstructed from half-open waiting intervals over the full drain. Time-weighted queue means use the [0, 300) arrival window. The source entity ledgers are intentionally not copied into this compact package; 1,113,588 rows were streamed one run at a time and retained only through metrics and audit hashes.

Cross-batch validation status: `PASS`. Earlier results are validation-only and contribute no observations to these estimates.

The deterministic ideal comparator sends perfectly regular arrivals through the same two fixed-service pooled-FCFS stages. Stage throughput capacity (`c / service time`) is linear in `c`; its delay is computed by the queueing oracle and is not forced to be linear. AnyLogic minus ideal is labelled a variability/congestion penalty, not an estimator of one uniquely causal mechanism.

These integer-capacity simulation points can reveal thresholds and curvature inside the tested sandbox. They are not a calibrated site forecast, an observed roster, a causal staffing estimate, or an HTX staffing recommendation. Any curve drawn between integer capacities is a labelled visual guide, not simulated evidence at fractional positions.
