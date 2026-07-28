# Licensing and deployment boundary

This is a technical risk disclosure, not legal advice. A production owner
should obtain a licence determination from legal/procurement and, where
necessary, from the upstream vendor.

## Current repository posture

This repository does not currently contain a top-level open-source `LICENSE`.
Accordingly, it makes no blanket MIT, Apache-2.0, or AGPL-3.0 grant over the
whole repository.

The default reproducible pipeline is intentionally separated from the
Ultralytics experiment:

- default `requirements.txt` does not install `ultralytics`;
- YOLO26 `.pt` and `.onnx` files are Git-ignored and are not redistributed;
- the documented default detector is YOLOX-S through ONNX Runtime;
- Ultralytics YOLO26 and the Ultralytics tracker implementations were used
  only in a local sensitivity experiment.

This separation improves disclosure and prevents an accidental dependency,
but it does **not** turn Ultralytics code or models into permissively licensed
components.

## Component boundary

| Component | Upstream licence posture | Role here |
|---|---|---|
| Ultralytics YOLO26 code and trained models | AGPL-3.0 by default, or a separate Ultralytics commercial licence | Local experimental detector only |
| Ultralytics ByteTrack / BoT-SORT implementation | Part of the AGPL-3.0 `ultralytics` package | Local tracker sensitivity only |
| Upstream BoT-SORT research code | MIT | Candidate replacement implementation; not the implementation used in the recorded YOLO26m experiment |
| Supervision ByteTrack implementation | MIT | Optional permissive tracker cross-check |
| Upstream ByteTrack research code | MIT | Algorithm/reference implementation |
| YOLOX software repository | Apache-2.0 | Default detector software baseline; confirm model-weight and data terms separately for production |
| AnyLogic PLE | AnyLogic's own PLE terms | Personal, non-production simulation demonstration only |

An algorithm name is not a licence. BoT-SORT and ByteTrack have permissive
upstream implementations, but the exact BoT-SORT and ByteTrack classes used in
the YOLO26m comparison came from `ultralytics==8.4.107` and therefore inherit
that package's licence boundary.

## Ultralytics-specific risk

Ultralytics' current official licensing guidance says that use of its code,
models, architectures, training pipelines, or trained models requires either:

1. releasing the entire relevant project under AGPL-3.0 with the required
   corresponding source; or
2. obtaining the applicable paid Ultralytics R&D licence for strictly
   non-operational research, or an Enterprise/commercial licence for
   operational use.

Its guidance expressly includes proprietary software, private internal tools,
and R&D that is not fully open-sourced. It also states that Ultralytics trained
models are AGPL-3.0 by default.

References:

- [Ultralytics licensing](https://www.ultralytics.com/license)
- [Ultralytics single-project R&D terms](https://www.ultralytics.com/legal/ultralytics-rd-license-terms-single-project)
- [Ultralytics repository licence statement](https://github.com/ultralytics/ultralytics#-license)
- [YOLO26 documentation licence statement](https://github.com/ultralytics/ultralytics/blob/main/docs/en/models/yolo26.md)

The GNU AGPL text and general GNU FAQ distinguish private use, conveying a
copy, and remote-network interaction. How those rules apply to a particular
wrapper, exported model, assessment handoff, or government deployment is a
fact-specific legal question. This project therefore does not claim that a
notice alone resolves the issue.

The AGPL text permits private running of covered works that are not conveyed,
subject to the licence remaining in force. It also treats program output as
covered only when the output's content is itself a covered work. Consequently,
a local personal experiment and a numerical methods report present a
materially different risk from handing an integrated package or model weights
to another organisation. The assessment video has its own separate copyright
boundary. Its stricter non-redistribution, privacy, retention, and embedded
media controls are documented in
[`docs/privacy_and_data_governance.md`](docs/privacy_and_data_governance.md).

## Use-case boundary

| Scenario | Current interpretation |
|---|---|
| Local personal learning / assessment experiment, not conveyed | Keep Ultralytics tools and weights local, preserve notices, and report the path as experimental |
| Public repository that retains the Ultralytics imports or YOLO26 integration | Follow Ultralytics' AGPL guidance for the entire relevant project and provide corresponding source/notices, or remove that integration from the distributable version |
| Private HTX research or proof of concept | Obtain an applicable paid R&D licence unless the complete relevant project can be released under AGPL-3.0; the R&D terms prohibit operational use |
| HTX operational, production, cost-reduction, or live-system use | Obtain an Enterprise/commercial licence or replace the components and revalidate |

## Approved architectural interpretation

“BoT-SORT is the primary tracker” means:

- it is the preferred association method in the recorded **local measurement
  experiment**; and
- it is an interface-level design choice, not approval to deploy the
  Ultralytics implementation inside HTX.

For a private, proprietary, or operational HTX system, use one of these paths:

1. procure an applicable Ultralytics R&D licence for a strictly
   non-operational proof of concept, or an Enterprise/commercial licence for
   operational use;
2. replace both the detector and tracker implementation with licence-approved
   components, then re-run event-level validation; or
3. release the complete relevant project under AGPL-3.0, only if security,
   procurement, and legal owners explicitly approve that model.

The proposed permissive replacement path is:

```text
licence-approved detector
    -> tracker interface
        -> upstream MIT BoT-SORT or MIT ByteTrack implementation
            -> event ledger and audit
```

YOLOX-S remains the current software baseline because its upstream repository
is Apache-2.0. Before production, the exact model-weight provenance and every
transitive dependency still require a software-composition review.

## Assessment handoff rules

Until a formal licence decision is made:

- do not commit or distribute Ultralytics `.pt` or `.onnx` weights;
- do not add `ultralytics` to the default runtime requirements;
- label YOLO26/Ultralytics outputs as experimental sensitivity evidence;
- do not describe the Ultralytics path as deployment-ready for HTX;
- keep the default runnable path independent of Ultralytics;
- if publishing under a permissive repository licence, remove the Ultralytics
  integration from that distributable version rather than merely calling it
  optional;
- do not add a blanket MIT or Apache-2.0 repository licence that purports to
  relicense AGPL-covered materials;
- preserve upstream notices and request legal/procurement review before any
  external, internal-business, or operational deployment.

MIT and Apache-2.0 components can coexist. The problem is not the presence of
two permissive licences; it is incorrectly applying a permissive repository
licence to an AGPL-covered combined work or redistributing third-party
materials without satisfying their terms.
