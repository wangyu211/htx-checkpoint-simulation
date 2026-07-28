# Task 1 crossing-ledger review protocol

**Current assessment status:** the 2026-07-27 Task 1 decision is a frozen
human-adjudicated **aggregate** of 12 left-to-right and 34 right-to-left
crossings. No signed event-time ledger exists.

**Purpose of this protocol:** define the additional review required if a future
study needs a human-signed event ledger, without confusing algorithm agreement
with ground truth or retrofitting candidate IDs into the accepted aggregate.

The evidence images remain local because they reproduce pixels from the
assessment video. They are generated under:

```text
_work/cv_hungarian_x640_fixed_20260726/owner_review/
```

## Review order

1. Review the six `pages/audit_page_*.jpg` pages for the 36 strict, central-line
   candidates. Each event strip shows time-local frames with the target track
   highlighted.
2. For each event, record `ACCEPT`, `REJECT`, or `UNCERTAIN`.
3. Review the low-confidence recall queue documented in:

   ```text
   _work/cv_hungarian_x640_conf002/low_only_reconciliation/
   ```

   Do not add every low-threshold event. That run changes associations as well
   as detector recall; matched/unmatched trajectory IDs are not person IDs.
4. Review the independent sequential full-video sweep, including the first and
   last seconds, top/bottom ROI boundaries, occlusion intervals, and any event
   not proposed by either tracker.
5. Reconcile accepted events by physical crossing, not by track ID. One person
   crossing once is one event even if the detector fragments it into several
   tracks.
6. Record the operational direction mapping. For the current assessment,
   `right_to_left` is already mapped to arrivals; a later deployment must
   validate that mapping against its own camera orientation.

## Decision rules

**Accept** only when the same visible person can be followed from one stable
side of `x=640` to the other within the upper-corridor ROI.

**Reject** when the event is caused by:

- a one-frame or post-gap spatial jump;
- an ID switch between different visible people;
- a reflection or excluded-region detection;
- duplicate fragments of a crossing already accepted; or
- movement that approaches but does not cross the central line.

**Uncertain** when occlusion or frame-boundary truncation prevents a defensible
identity/trajectory decision. Preserve uncertain events separately; do not
silently force them into the baseline. They may define lower/upper count
scenarios.

## Future event-ledger products

The final public, non-pixel ledger must include:

```text
event_id
event_time_seconds
image_direction
decision
reason_code
reviewer
review_date
source_run_id
line_x
roi
```

Publish:

- accepted count by direction;
- unresolved-event count;
- point rate and explicit lower/upper measurement sensitivity;
- source video/model hashes and run configuration; and
- a statement that the short clip does not establish long-run stationarity.

Retain candidate, low-threshold, aggregate-freeze, and any future signed event
ledger as different files. Never overwrite candidate history or imply that its
IDs are the 46 final human-adjudicated people.
