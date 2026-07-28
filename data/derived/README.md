# Derived tabular evidence

This directory contains non-pixel numerical evidence that may be included in
the public repository.

- Source video frames and annotated videos remain local and are ignored.
- Appearance descriptions, face/biometric features, identity embeddings,
  cross-camera links, and permanent person identifiers are prohibited.
- Public reviewer identity is limited to a project-scoped role alias. Raw
  review-item notes and any alias mapping remain local.
- Files prefixed `candidate_` are not frozen model inputs.
- `ai_first_pass_*` fields record an AI-assisted screening pass, not a human
  audit or project-owner sign-off.
- `task1_final_aggregate.csv` is the accepted human-adjudicated aggregate:
  12 left-to-right and 34 right-to-left crossings over 24.922788889 seconds.
  `OWNER_REVIEWER_A`, the project-scoped role alias for the assessment
  candidate/project owner, froze this aggregate on 2026-07-27 after full-video
  directional review.
  The assessment entrance mapping uses `right_to_left`, giving the frozen
  short-window input `34 / 24.922788889 = 1.364213` travellers per second.
- The primary local automatic candidate path is YOLO26m with BoT-SORT. The
  licence-friendlier public fallback is YOLOX-S with Supervision ByteTrack; its
  reviewed distinct candidate set is 7 left-to-right and 24 right-to-left.
- The accepted file is an aggregate freeze, not a signed event-time ledger.
  Its observed-clip rates are not estimates of long-run checkpoint demand.
- Historical candidate-audit summaries use trajectory/occlusion wording only;
  local tracker tokens are confined to this single-video method audit and must
  not be treated as person identifiers.
- Earlier candidate totals and the 27/29 right-to-left review counts are
  superseded historical method/review evidence. They are not alternative
  statistical samples, confidence bounds, or approved simulation inputs.

See [`docs/privacy_and_data_governance.md`](../../docs/privacy_and_data_governance.md)
for the public/private boundary and fail-closed release audit.
