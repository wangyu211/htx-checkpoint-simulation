# Final hardening register

This register separates four states that must never be conflated:

- `EVIDENCE_ACCEPTED`: implemented, executed, validated, and safe to report;
- `EVIDENCE_ACCEPTED_CONDITIONAL_REPLAY`: an executed, exactly gated
  counterfactual replay that is safe to report only with its model/scale
  boundary and is not evidence of the current site mechanism;
- `IMPLEMENTED_NOT_EXECUTED`: executable and contract-tested, but has no
  accepted real result;
- `RELEASE_BLOCKED`: the release audit has executed and found a concrete
  public-delivery blocker that must be removed before submission;
- `INFRASTRUCTURE_READY_HUMAN_REVIEW_PENDING`: tooling exists, but a required
  human adjudication has not been signed;
- `DEFERRED_ABSENT_EVIDENCE`: deliberately not represented as a calibrated
  mechanism because the supplied material does not identify its parameters.

It is an internal release gate, not an assessment result.

| Assessment surface | Current state | Release gate / reason |
|---|---|---|
| Directional aggregate, 12 L→R / 34 R→L | `EVIDENCE_ACCEPTED` | Existing aggregate and provenance remain the current frozen Task 1 input. |
| Crossing-event ledger and trace replay | `INFRASTRUCTURE_READY_HUMAN_REVIEW_PENDING` | Count-blind full-video pass, independent all-frame pass, reconciliation, and detached sign-off are still required. No expected count is embedded in the protocol. |
| YOLO26m + BoT-SORT demonstration | `EVIDENCE_ACCEPTED_WITH_LICENSE_BOUNDARY` | Useful assessment evidence with human acceptance; not the default deployable public-sector component. YOLOX-S + ByteTrack remains the permissive reference path. |
| Two-stage traveller flow, pooled FCFS, finite resources | `EVIDENCE_ACCEPTED` | Executable AnyLogic mechanism, deterministic oracle, full-drain and conservation checks exist. |
| Top-down visual layout and state animation | `EVIDENCE_ACCEPTED_FOR_DEMONSTRATION` | Presentation tokens are driven by real DES state; animation is not an analysis source. |
| Configurable interactive inputs | `EVIDENCE_ACCEPTED_FOR_DEMONSTRATION` | Five inputs are exposed before an interactive run; structural inputs require stop/reopen. |
| In-model live metrics | `EVIDENCE_ACCEPTED_FOR_DEMONSTRATION` | Counters and resource utilisation update during a run; reported findings still come only from replication files. |
| Registered capacity studies and response surface | `EVIDENCE_ACCEPTED` | Frozen configurations, exact run coverage, CRN gates, uncertainty, and claim boundaries are checked in. |
| Mean-preserving service-time CV sensitivity | `EVIDENCE_ACCEPTED` | All 9×50 AnyLogic runs passed coverage, lineage, conservation, full-drain, traveller-level CRN, and cross-batch reference-reproduction gates. The result is an uncalibrated conditional assumption sensitivity, not evidence of measured HTX service distributions or a staffing recommendation. |
| 5–120 minute peak-duration sensitivity | `IMPLEMENTED_NOT_EXECUTED` | AnyLogic 20×50 batch and finite-horizon analyser exist; all 1,000 runs and nested-prefix checks must pass. |
| Pooled vs separate queue layout | `EVIDENCE_ACCEPTED_CONDITIONAL_REPLAY` | Reference pooled replay matched 164,976 timestamps/waits plus 50 registered P95s with zero mismatches; shortest-number-in-lane routing, deterministic ties, no jockeying, serial stages, counter logs, CRN gates and paired CIs are accepted. The `6/4` normalized cell is transparent mechanism-only; neither cell identifies the current site policy, and the AnyLogic UI remains pooled. |
| Traveller-type service effects | `DEFERRED_ABSENT_EVIDENCE` | Type shares and multipliers are not identified by the supplied clip; any future implementation must be labelled transparent sensitivity assumptions. |
| Time-of-day arrival pattern | `DEFERRED_ABSENT_EVIDENCE` | A 24.9-second clip cannot identify a daily profile. A signed event ledger can test only within-window timing, not time of day. |
| Physical walking time between stages | `DEFERRED_ABSENT_EVIDENCE` | Pixel speed lacks a checkpoint path/homography mapping; the current DES does not claim a calibrated walking delay. |
| Independent secondary-check resource | `DEFERRED_ABSENT_EVIDENCE` | The executable v1 exposes only a counter-held referral proxy; routing and service evidence for a real secondary system are absent. |
| Independent automated channel and fallback | `DEFERRED_ABSENT_EVIDENCE` | The executable v1 uses an uptake × service multiplier proxy and does not claim an eGate resource model. |
| Animation-speed invariance evidence | `IMPLEMENTED_NOT_EXECUTED` | The [registered three-run protocol](task3_animation_speed_invariance_protocol.md), immutable capture helper, exact field comparator, and fail-closed tests exist. No invariance claim is permitted until genuine GUI 1x, GUI 10x, and virtual-time captures pass together. |
| Privacy and retention release check | `RELEASE_BLOCKED` | Policy, scanner, retention boundary, role aliases, and event/aggregate-only public rules are implemented. The executed audit currently rejects two copies of a supplied-video-derived frame embedded in the canonical deck; replace them with a non-pixel schematic before release. |
| Linux clean-environment workflow | `PENDING_VERIFICATION` | Run after the final source and documentation set is frozen. |
| Final deck and short demonstration | `PENDING_FINAL_EVIDENCE` | Update only after new studies are accepted; do not place planned values on slides. |
| Remote publication | `NOT_AUTHORISED_YET` | Local commits are allowed. Do not push or make public until final approval. |

## Release rule

A planned mechanism or analysis may be described as implemented, but it may
not supply a number, direction, recommendation, or visual result until its
state is `EVIDENCE_ACCEPTED`. A deferred mechanism is a traceability decision,
not evidence that the real checkpoint lacks that mechanism.
