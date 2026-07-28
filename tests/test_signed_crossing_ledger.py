from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from src.cv.signed_crossing_ledger import (
    DEFAULT_PROTOCOL,
    LEDGER_SCHEMA_VERSION,
    SIGNOFF_SCHEMA_VERSION,
    TRACE_FIELDS,
    canonical_csv_bytes,
    create_signoff_package,
    export_arrival_trace,
    load_protocol,
    validate_accepted_ledger,
    validate_arrival_trace,
    validate_review_items,
    validate_signed_package,
)


PROTOCOL = load_protocol(DEFAULT_PROTOCOL)
LEDGER_FIELDS = tuple(
    PROTOCOL["public_ledger_contract"]["fields_in_order"]  # type: ignore[index]
)
REVIEW_FIELDS = tuple(
    PROTOCOL["review_item_contract"]["fields_in_order"]  # type: ignore[index]
)
SOURCE_HASH = PROTOCOL["source_video"]["sha256"]  # type: ignore[index]
ATTESTATION = PROTOCOL["detached_signoff_contract"]["attestation"]  # type: ignore[index]


def synthetic_ledger_rows() -> list[dict[str, object]]:
    return [
        {
            "schema_version": LEDGER_SCHEMA_VERSION,
            "ledger_version": "SYNTHETIC_V1",
            "event_id": "EVENT_001",
            "source_video_sha256": SOURCE_HASH,
            "frame_index": "38",
            "pts_seconds": "1.25",
            "time_lower_seconds": "1.25",
            "time_upper_seconds": "1.25",
            "time_resolution": "EXACT_FRAME",
            "image_direction": "right_to_left",
            "operational_stream_mapping": "arrival",
            "crossing_y_px": "120",
            "line_x": "640",
            "roi_xyxy": "0,0,1280,310",
            "continuity_class": "CLEAR_CONTINUOUS",
            "boundary_flags": "NONE",
            "evidence_packet_id": "PACKET_001",
            "decision": "ACCEPT",
            "decision_reason_code": "CLEAR_CONTINUOUS_CROSSING",
            "reviewer_id": "PROJECT_OWNER",
            "reviewed_at_utc": "2026-07-29T01:02:03Z",
        },
        {
            "schema_version": LEDGER_SCHEMA_VERSION,
            "ledger_version": "SYNTHETIC_V1",
            "event_id": "EVENT_002",
            "source_video_sha256": SOURCE_HASH,
            "frame_index": "",
            "pts_seconds": "",
            "time_lower_seconds": "4.4",
            "time_upper_seconds": "4.6",
            "time_resolution": "INTERVAL_CENSORED",
            "image_direction": "right_to_left",
            "operational_stream_mapping": "arrival",
            "crossing_y_px": "180",
            "line_x": "640",
            "roi_xyxy": "0,0,1280,310",
            "continuity_class": "OCCLUDED_RESOLVED",
            "boundary_flags": "NONE",
            "evidence_packet_id": "PACKET_002",
            "decision": "ACCEPT",
            "decision_reason_code": "OCCLUDED_CONTINUITY_RESOLVED",
            "reviewer_id": "PROJECT_OWNER",
            "reviewed_at_utc": "2026-07-29T01:03:04Z",
        },
        {
            "schema_version": LEDGER_SCHEMA_VERSION,
            "ledger_version": "SYNTHETIC_V1",
            "event_id": "EVENT_003",
            "source_video_sha256": SOURCE_HASH,
            "frame_index": "263",
            "pts_seconds": "8.75",
            "time_lower_seconds": "8.75",
            "time_upper_seconds": "8.75",
            "time_resolution": "EXACT_FRAME",
            "image_direction": "right_to_left",
            "operational_stream_mapping": "arrival",
            "crossing_y_px": "305",
            "line_x": "640",
            "roi_xyxy": "0,0,1280,310",
            "continuity_class": "ROI_BOUNDARY_PARTIAL_RESOLVED",
            "boundary_flags": "ROI_BOUNDARY_PARTIAL",
            "evidence_packet_id": "PACKET_003",
            "decision": "ACCEPT",
            "decision_reason_code": "ROI_BOUNDARY_PARTIAL_BUT_CLEAR",
            "reviewer_id": "PROJECT_OWNER",
            "reviewed_at_utc": "2026-07-29T01:04:05Z",
        },
    ]


def synthetic_review_items() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for index, ledger_row in enumerate(synthetic_ledger_rows(), start=1):
        rows.append(
            {
                "review_item_id": f"REVIEW_{index:03d}",
                "enumeration_pass_id": "BLIND_PASS_1",
                "approx_pts_seconds": (
                    ledger_row["pts_seconds"]
                    or ledger_row["time_lower_seconds"]
                ),
                "proposed_direction": ledger_row["image_direction"],
                "approx_crossing_y_px": ledger_row["crossing_y_px"],
                "proposal_sources": "MANUAL_ENUMERATION",
                "source_local_ids": "",
                "evidence_packet_id": ledger_row["evidence_packet_id"],
                "final_decision": "ACCEPT",
                "reason_code": ledger_row["decision_reason_code"],
                "duplicate_of_event_id": "",
                "reviewer_id": "PROJECT_OWNER",
                "reviewed_at_utc": ledger_row["reviewed_at_utc"],
                "reviewer_notes": "",
            }
        )
    rows.append(
        {
            "review_item_id": "REVIEW_004",
            "enumeration_pass_id": "BLIND_PASS_2",
            "approx_pts_seconds": "9.25",
            "proposed_direction": "left_to_right",
            "approx_crossing_y_px": "90",
            "proposal_sources": "MANUAL_ENUMERATION",
            "source_local_ids": "",
            "evidence_packet_id": "PACKET_004",
            "final_decision": "UNCERTAIN",
            "reason_code": "OCCLUSION_UNRESOLVED",
            "duplicate_of_event_id": "",
            "reviewer_id": "PROJECT_OWNER",
            "reviewed_at_utc": "2026-07-29T01:05:06Z",
            "reviewer_notes": "",
        }
    )
    return rows


def synthetic_request() -> dict[str, object]:
    return {
        "schema_version": SIGNOFF_SCHEMA_VERSION,
        "ledger_version": "SYNTHETIC_V1",
        "reviewer_id": "PROJECT_OWNER",
        "signed_at_utc": "2026-07-29T01:10:00Z",
        "attestation": ATTESTATION,
    }


class SignedCrossingLedgerTests(unittest.TestCase):
    def test_synthetic_three_event_non_target_fit_ledger_passes(self) -> None:
        report = validate_accepted_ledger(
            synthetic_ledger_rows(),
            PROTOCOL,
            fields=LEDGER_FIELDS,
        )

        self.assertEqual(report["contract"], LEDGER_SCHEMA_VERSION)
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["ledger_row_count"], 3)
        self.assertEqual(
            report["accepted_counts_by_direction"],
            {"left_to_right": 0, "right_to_left": 3},
        )
        self.assertEqual(report["interval_censored_count"], 1)
        self.assertNotIn("46", json.dumps(report))
        self.assertIsNone(
            PROTOCOL["signoff_requirements"]["expected_total_for_validation"]  # type: ignore[index]
        )

    def test_protocol_reason_codes_and_review_history_are_enforced(self) -> None:
        rows = synthetic_review_items()
        rows[0]["final_decision"] = "REVIEW"
        rows[0]["reason_code"] = ""
        rows[1]["reviewer_id"] = "reviewer@example.com"

        report = validate_review_items(rows, PROTOCOL, fields=REVIEW_FIELDS)

        self.assertEqual(report["status"], "FAIL")
        self.assertTrue(
            any("final_decision" in error for error in report["errors"])
        )
        self.assertTrue(
            any("non-PII uppercase role alias" in error for error in report["errors"])
        )
        self.assertIsNone(report["accepted_review_item_count"])
        self.assertIsNone(report["uncertain_count"])
        self.assertEqual(report["accepted_evidence_packet_ids"], [])

    def test_static_schema_columns_match_registered_protocol(self) -> None:
        schema_path = (
            DEFAULT_PROTOCOL.parent
            / "task1_signed_crossing_ledger.schema.json"
        )
        schema = json.loads(schema_path.read_text(encoding="utf-8"))

        self.assertEqual(
            schema["x-csv-columns-in-order"],
            list(LEDGER_FIELDS),
        )
        self.assertNotIn(
            "expected_total",
            json.dumps(schema, sort_keys=True),
        )
        forbidden = {
            "track_id",
            "reviewer_notes",
            "source_pixel_path",
            "person_id",
        }
        self.assertTrue(forbidden.isdisjoint(schema["x-csv-columns-in-order"]))

    def test_interval_censored_timing_cannot_claim_an_exact_frame(self) -> None:
        rows = synthetic_ledger_rows()
        rows[1]["frame_index"] = "132"
        rows[1]["pts_seconds"] = "4.5"

        report = validate_accepted_ledger(rows, PROTOCOL, fields=LEDGER_FIELDS)

        self.assertEqual(report["status"], "FAIL")
        self.assertTrue(
            any(
                "interval-censored frame_index and pts_seconds must be blank"
                in error
                for error in report["errors"]
            )
        )

    def test_signoff_and_interval_preserving_trace_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            draft = root / "ledger_draft.csv"
            review_items = root / "review_items.csv"
            evidence_manifest = root / "evidence_manifest.json"
            request = root / "signoff_request.json"
            ledger = root / "signed_ledger.csv"
            signoff = root / "detached_signoff.json"
            trace = root / "arrival_trace.csv"
            trace_manifest = root / "arrival_trace.manifest.json"

            draft.write_bytes(
                canonical_csv_bytes(synthetic_ledger_rows(), LEDGER_FIELDS)
            )
            review_items.write_bytes(
                canonical_csv_bytes(synthetic_review_items(), REVIEW_FIELDS)
            )
            evidence_manifest.write_text(
                json.dumps(
                    {
                        "artifact_type": "LOCAL_EVIDENCE_MANIFEST",
                        "packet_ids": [
                            "PACKET_001",
                            "PACKET_002",
                            "PACKET_003",
                            "PACKET_004",
                        ],
                    }
                ),
                encoding="utf-8",
            )
            request.write_text(
                json.dumps(synthetic_request()),
                encoding="utf-8",
            )

            signoff_report = create_signoff_package(
                draft,
                review_items,
                evidence_manifest,
                request,
                ledger,
                signoff,
            )
            trace_report = export_arrival_trace(
                ledger,
                review_items,
                evidence_manifest,
                signoff,
                trace,
                trace_manifest,
            )

            self.assertEqual(signoff_report["status"], "PASS")
            self.assertEqual(
                validate_signed_package(
                    ledger,
                    review_items,
                    evidence_manifest,
                    signoff,
                )["status"],
                "PASS",
            )
            self.assertEqual(trace_report["status"], "PASS")
            self.assertEqual(trace_report["event_count"], 3)
            self.assertEqual(trace_report["interval_censored_event_count"], 1)
            self.assertEqual(
                validate_arrival_trace(trace, trace_manifest)["status"],
                "PASS",
            )
            with trace.open(newline="", encoding="utf-8") as stream:
                reader = csv.DictReader(stream)
                self.assertEqual(tuple(reader.fieldnames or ()), TRACE_FIELDS)
                rows = list(reader)
            self.assertEqual(rows[0]["arrival_seconds"], "1.25")
            self.assertEqual(rows[1]["arrival_seconds"], "")
            self.assertEqual(rows[1]["time_lower_seconds"], "4.4")
            self.assertEqual(rows[1]["time_upper_seconds"], "4.6")
            self.assertEqual(rows[2]["arrival_seconds"], "8.75")

    def test_detached_signoff_tampering_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            draft = root / "draft.csv"
            review_items = root / "review.csv"
            evidence = root / "evidence.json"
            request = root / "request.json"
            ledger = root / "signed.csv"
            signoff = root / "signoff.json"
            draft.write_bytes(
                canonical_csv_bytes(synthetic_ledger_rows(), LEDGER_FIELDS)
            )
            review_items.write_bytes(
                canonical_csv_bytes(synthetic_review_items(), REVIEW_FIELDS)
            )
            evidence.write_text("{}", encoding="utf-8")
            request.write_text(
                json.dumps(synthetic_request()),
                encoding="utf-8",
            )
            create_signoff_package(
                draft,
                review_items,
                evidence,
                request,
                ledger,
                signoff,
            )
            payload = json.loads(signoff.read_text(encoding="utf-8"))
            payload["accepted_counts_by_direction"]["right_to_left"] = 46
            signoff.write_text(json.dumps(payload), encoding="utf-8")

            report = validate_signed_package(
                ledger,
                review_items,
                evidence,
                signoff,
            )

            self.assertEqual(report["status"], "FAIL")
            self.assertTrue(
                any(
                    "accepted_counts_by_direction" in error
                    for error in report["errors"]
                )
            )

    def test_signoff_never_overwrites_review_history_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            draft = root / "draft.csv"
            review_items = root / "review.csv"
            evidence = root / "evidence.json"
            request = root / "request.json"
            ledger = root / "signed.csv"
            signoff = root / "signoff.json"
            draft.write_bytes(
                canonical_csv_bytes(synthetic_ledger_rows(), LEDGER_FIELDS)
            )
            review_items.write_bytes(
                canonical_csv_bytes(synthetic_review_items(), REVIEW_FIELDS)
            )
            evidence.write_text("{}", encoding="utf-8")
            request.write_text(
                json.dumps(synthetic_request()),
                encoding="utf-8",
            )
            create_signoff_package(
                draft,
                review_items,
                evidence,
                request,
                ledger,
                signoff,
            )

            with self.assertRaisesRegex(FileExistsError, "refusing to overwrite"):
                create_signoff_package(
                    draft,
                    review_items,
                    evidence,
                    request,
                    ledger,
                    signoff,
                )


if __name__ == "__main__":
    unittest.main()
