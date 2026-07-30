# Third-party notices

This repository's original source code does not grant rights to the assessment
video, third-party model weights, simulation engine, or third-party packages.

## YOLOX

- Project: [Megvii YOLOX](https://github.com/Megvii-BaseDetection/YOLOX)
- Release asset used locally: `yolox_s.onnx`, release `0.1.1rc0`
- Upstream repository license: Apache License 2.0
- The model file is downloaded locally by `scripts/download_yolox_s.ps1` and is
  excluded from this repository.

## Ultralytics YOLO26 experimental comparison

- Project: [Ultralytics](https://github.com/ultralytics/ultralytics)
- Experimental local assets: `yolo26s.pt`, `yolo26s.onnx`, `yolo26m.pt`, and
  `yolo26m.onnx`
- Upstream software and trained models are AGPL-3.0 by default, with separate
  commercial licensing offered by Ultralytics.
- The recorded ByteTrack and BoT-SORT experiment imports their implementations
  from `ultralytics==8.4.107`; those implementations remain inside the same
  AGPL-3.0 package even though separately maintained upstream implementations
  of the algorithms use permissive licences.
- These assets are used only for a detector sensitivity experiment, are
  excluded from this repository, and are not the licensing baseline for the
  assessment deliverable.
- Ultralytics' official guidance lists private internal tools and R&D that is
  not fully open-sourced among the cases requiring either an applicable paid
  R&D licence for strictly non-operational research or an
  Enterprise/commercial licence for operational use. A notice does not remove
  that requirement.
- Do not incorporate this path into proprietary, internal-business, or
  production use without an appropriate licence determination:
  [Ultralytics Licensing](https://www.ultralytics.com/license).

See `LICENSING.md` for the repository-level deployment boundary.

## Supervision / ByteTrack sensitivity implementation

- Project: [Roboflow Supervision](https://github.com/roboflow/supervision)
- Version used for the optional ByteTrack cross-check: `0.25.1`
- Upstream repository license: MIT
- The canonical ByteTrack research implementation is
  [FoundationVision/ByteTrack](https://github.com/FoundationVision/ByteTrack)
  under MIT.

## Upstream BoT-SORT alternative

- Project: [NirAharon/BoT-SORT](https://github.com/NirAharon/BoT-SORT)
- Upstream repository licence: MIT
- This permissive upstream implementation is a candidate replacement for the
  experimental Ultralytics tracker implementation. It has not yet replaced or
  reproduced the recorded experiment, and its bundled components and
  transitive dependencies still require review before deployment.

## AnyLogic PLE

- Product: [AnyLogic Personal Learning Edition](https://www.anylogic.com/downloads/)
- AnyLogic PLE is external software and remains governed by AnyLogic's own
  software license agreement.
- The project uses PLE solely as a personal, non-production skills
  demonstration. No operational, commercial, or research reuse right is
  asserted or granted.

## Assessment input

`TestVidTask.mov`, annotated videos, bulk decoded-frame outputs, and review
packs are not redistributed. The Task 4 deck retains three exact-hash
screenshots solely to explain the supplied Task 1 inference workflow.

Source: `HTX TechnicalTestVideo`, supplied for Task 1. The original video is
not redistributed in this repository. The assessment-use screenshot
classification is a project release decision, not a general licence grant.

The repository's stricter public/private data boundary, including embedded
presentation-media checks, is documented in
[`docs/privacy_and_data_governance.md`](docs/privacy_and_data_governance.md).
