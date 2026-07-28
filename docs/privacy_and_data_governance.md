# Privacy and data governance

**Policy:** `HTX_PUBLIC_RELEASE_DATA_BOUNDARY_V1`

**Scope:** the supplied assessment video, Task 1 review material, derived
measurement artifacts, simulation exports, documentation, and presentation
media.

This project measures anonymous crossing **events**. It is not an identity,
surveillance, face-recognition, or re-identification system.

## Public/private boundary

| Eligible for public release | Restricted to local review |
|---|---|
| Protocols, schemas, parameter provenance, source hashes | Supplied video/audio and decoded source pixels |
| Aggregate counts/rates and de-identified numerical audits | Frames, crops, thumbnails, contact sheets, review videos, and evidence packets |
| Accepted-only non-pixel event ledger after registered review and detached sign-off | Raw review-item history, free-text reviewer notes, and unresolved items |
| Synthetic simulation inputs, run summaries, aggregate outputs, charts, and non-pixel schematics | Face/biometric data, appearance descriptions or features, identity embeddings, and re-ID features |
| Ledger-local event IDs and project-scoped reviewer role aliases | Persistent person IDs, cross-camera links, and alias-to-person mappings |

An event ID identifies one accepted crossing row inside one ledger. It must not
be reused as a person identifier or linked across videos, cameras, datasets, or
projects. Cross-camera re-identification is prohibited. The pipeline does not
need face detection, face recognition, gait recognition, appearance embeddings,
or biometric templates.

`source_video_sha256` is retained for provenance. A cryptographic hash is not
permission to redistribute the source or a pixel derivative.

## Task 1 reviewer identity

Public Task 1 artifacts use a project-scoped role alias matching
`^[A-Z][A-Z0-9_]{2,63}$`, for example `OWNER_REVIEWER_A`. Do not publish a
reviewer's name, email address, employee identifier, phone number, or a reusable
cross-project handle. If accountability requires an alias-to-person mapping,
store it locally with access control and never commit it.

An AI assistant may prepare review assets or challenge decisions, but it is not
a second human reviewer and must not be represented by a human reviewer alias.
When one owner performs both full-video passes, disclose
`SINGLE_REVIEWER_DOUBLE_PASS`.

The public signed ledger contains accepted, non-pixel events only. Rejected and
uncertain review items remain in the hash-bound local review record; their
free-text notes and source-local tracker IDs are not public release artifacts.

## Retention and deletion

Apply data minimisation:

1. Keep the supplied video and pixel-bearing derivatives only while required
   for registered review, issue resolution, and submission verification.
2. Delete restricted working artifacts within 30 calendar days after the later
   of final submission and closure of the assessment/review window. Delete
   earlier if the assessment issuer requires it. A documented legal hold is the
   only exception; delete when the hold ends.
3. Delete any private reviewer-alias mapping with the restricted review package
   when accountability no longer requires it.
4. Record only the deletion date and artifact classes. Do not put personal
   information or source-pixel filenames into the deletion record.
5. Protocols, hashes, aggregate data, signed accepted-event ledgers, and
   reproducible simulation summaries may remain as the non-pixel audit record.

Restricted artifacts must not be committed, placed in presentation archives,
uploaded to a public artifact store, or used to train/fine-tune a model.

## Fail-closed release gate

The machine-readable contract is
[`config/public_release_data_policy.json`](../config/public_release_data_policy.json).
Run:

```powershell
.\.venv\Scripts\python.exe tools\audit_public_release_data.py
```

The audit checks the Git index rather than ignored local files. It rejects:

- tracked raw/private path prefixes and audio/video formats;
- known restricted content hashes;
- unclassified direct raster images;
- restricted or unclassified media embedded inside `.pptx`, `.docx`, `.xlsx`,
  or `.zip` files;
- structured biometric, appearance, persistent-identity, or cross-camera
  fields; and
- invalid reviewer aliases or prohibited fields in a public signed ledger.

Raster images fail closed: every publishable chart or synthetic screenshot must
first be visually reviewed and registered by SHA-256 as non-pixel media. A hash
allow-list records classification, not a licence grant.

## Current release blocker (audit 2026-07-29)

The tracked canonical Task 4 deck currently embeds the same 1280x720
source-video-derived frame twice: `ppt/media/image.jpeg` on slide 1 and
`ppt/media/image2.jpeg` on slide 2.

`c6996d8d9afff105757b6e42fb4fd4957128aeafa57322b0e518ea1842f0b797`

It may be used only inside the intended assessment workflow if the assessment
terms permit that use. It blocks a **public repository release** until both
embedded copies are replaced with a non-pixel schematic (or other explicitly
approved media) and the new media hashes pass the release audit.

During this audit, three clothing/appearance descriptions in
`candidate_false_negative_sweep_x640.csv` were replaced with
trajectory/occlusion-only wording while preserving candidate ID, time,
direction, tracker-fragment, and analytical meaning.

## Roles and incident response

- The project owner approves the public artifact inventory and performs the
  final visual check of every newly registered raster.
- A reviewer records event decisions under a role alias and reports uncertainty
  rather than forcing an identity decision.
- Any accidental commit or upload of restricted data is a release incident:
  stop distribution, revoke shared artifacts where possible, rotate affected
  public archives, remove the data from Git history using an approved recovery
  procedure, and document the response without reproducing the restricted
  content.

This is a project engineering control, not legal advice. Assessment terms,
organisational policy, privacy law, and the source owner's instructions take
precedence.
