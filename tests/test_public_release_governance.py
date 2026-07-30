from __future__ import annotations

import copy
import csv
import hashlib
import json
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path

from src.governance.public_release import audit_paths, load_policy


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class PublicReleaseGovernanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.base_policy = load_policy(PROJECT_ROOT)

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.policy = copy.deepcopy(self.base_policy)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def write_bytes(self, relative: str, content: bytes) -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def write_text(self, relative: str, content: str) -> Path:
        return self.write_bytes(relative, content.encode("utf-8"))

    def codes(self, paths: list[str]) -> set[str]:
        return {
            finding.code
            for finding in audit_paths(self.root, paths, policy=self.policy)
        }

    def test_aggregate_event_data_without_identity_fields_is_allowed(self) -> None:
        relative = "data/derived/task1_final_aggregate.csv"
        self.write_text(
            relative,
            "direction,count,rate_per_second\nright_to_left,34,1.364213\n",
        )
        self.assertEqual(self.codes([relative]), set())

    def test_tracked_video_fails_even_outside_raw_directory(self) -> None:
        relative = "slides/review.mp4"
        self.write_bytes(relative, b"not a real video")
        self.assertIn("TRACKED_AUDIO_VIDEO", self.codes([relative]))

    def test_restricted_raw_path_fails_closed(self) -> None:
        relative = "data/raw/private.csv"
        self.write_text(relative, "event_id\nE1\n")
        self.assertIn("RESTRICTED_PATH", self.codes([relative]))

    def test_private_raw_simulation_export_fails_closed(self) -> None:
        relative = "results/raw/entity_log.csv"
        self.write_text(relative, "traveller_id,arrival_time\n1,0.0\n")
        self.assertIn("RESTRICTED_PATH", self.codes([relative]))

    def test_unclassified_raster_fails_closed(self) -> None:
        relative = "docs/unreviewed.png"
        self.write_bytes(relative, b"unreviewed raster bytes")
        self.assertIn("UNCLASSIFIED_TRACKED_RASTER", self.codes([relative]))

    def test_svg_cannot_hide_embedded_source_pixels(self) -> None:
        relative = "docs/hidden_pixels.svg"
        self.write_text(
            relative,
            '<svg xmlns="http://www.w3.org/2000/svg">'
            '<image href="data:image/png;base64,AAAA"/></svg>',
        )
        self.assertIn("EMBEDDED_RASTER_IN_SVG", self.codes([relative]))

    def test_approved_non_pixel_raster_passes(self) -> None:
        relative = "docs/synthetic_chart.png"
        content = b"synthetic non-pixel chart fixture"
        digest = hashlib.sha256(content).hexdigest()
        self.policy["approved_non_pixel_media_sha256"][digest] = (
            "Synthetic unit-test chart"
        )
        self.write_bytes(relative, content)
        self.assertEqual(self.codes([relative]), set())

    def test_restricted_source_frame_inside_pptx_fails(self) -> None:
        relative = "slides/deck.pptx"
        content = b"restricted source-frame fixture"
        digest = hashlib.sha256(content).hexdigest()
        self.policy["restricted_content_sha256"][digest] = (
            "Synthetic restricted frame"
        )
        path = self.root / relative
        path.parent.mkdir(parents=True)
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("ppt/media/image1.jpeg", content)
        findings = audit_paths(self.root, [relative], policy=self.policy)
        self.assertTrue(
            any(
                finding.code == "RESTRICTED_CONTENT_HASH"
                and finding.path.endswith("!/ppt/media/image1.jpeg")
                for finding in findings
            )
        )

    def test_unclassified_embedded_raster_fails_closed(self) -> None:
        relative = "slides/deck.pptx"
        path = self.root / relative
        path.parent.mkdir(parents=True)
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("ppt/media/image1.png", b"unknown")
        self.assertIn("UNCLASSIFIED_EMBEDDED_RASTER", self.codes([relative]))

    def test_identity_or_biometric_structured_field_fails(self) -> None:
        relative = "data/derived/events.csv"
        self.write_text(relative, "event_id,identity_embedding\nE1,0.1;0.2\n")
        self.assertIn("RESTRICTED_STRUCTURED_FIELDS", self.codes([relative]))

    def test_face_prefixed_field_and_opaque_vector_container_fail(self) -> None:
        csv_relative = "data/derived/events.csv"
        vector_relative = "data/derived/features.npy"
        self.write_text(csv_relative, "event_id,face_bbox\nE1,1;2;3;4\n")
        self.write_bytes(vector_relative, b"opaque vector fixture")
        codes = self.codes([csv_relative, vector_relative])
        self.assertIn("RESTRICTED_STRUCTURED_FIELDS", codes)
        self.assertIn("OPAQUE_BINARY_DATA", codes)

    def test_public_ledger_requires_role_alias_and_rejects_track_id(self) -> None:
        relative = "data/derived/task1_signed_crossing_ledger_v1.csv"
        path = self.root / relative
        path.parent.mkdir(parents=True)
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(
                stream,
                fieldnames=["event_id", "reviewer_id", "track_id"],
            )
            writer.writeheader()
            writer.writerow(
                {
                    "event_id": "E1",
                    "reviewer_id": "person@example.com",
                    "track_id": "42",
                }
            )
        codes = self.codes([relative])
        self.assertIn("INVALID_REVIEWER_ALIAS", codes)
        self.assertIn("PROHIBITED_PUBLIC_LEDGER_FIELDS", codes)

    def test_project_scoped_role_alias_is_accepted(self) -> None:
        relative = "data/derived/task1_signed_crossing_ledger_v1.csv"
        self.write_text(relative, "event_id,reviewer_id\nE1,OWNER_REVIEWER_A\n")
        self.assertEqual(self.codes([relative]), set())

    def test_public_signoff_rejects_person_name(self) -> None:
        relative = "data/derived/task1_owner_signoff_v1.json"
        self.write_text(relative, json.dumps({"reviewer_id": "Wang Yu"}))
        self.assertIn("INVALID_REVIEWER_ALIAS", self.codes([relative]))

    def test_policy_prohibits_cross_camera_reidentification(self) -> None:
        task1 = self.base_policy["task1_public_artifacts"]
        self.assertIs(task1["cross_camera_reidentification_permitted"], False)
        self.assertIn(
            "30 calendar days",
            self.base_policy["retention_and_deletion"][
                "restricted_working_artifacts"
            ],
        )

    def test_current_repository_has_no_unregistered_privacy_findings(self) -> None:
        result = subprocess.run(
            ["git", "ls-files"],
            cwd=PROJECT_ROOT,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        tracked = [line for line in result.stdout.splitlines() if line]
        findings = audit_paths(PROJECT_ROOT, tracked)
        expected_private_deck_blockers = {
            "Source-video-derived 1280x720 frame embedded in the current "
            "Task 4 deck",
            "Supplied-video-derived full-frame ROI and count-line illustration "
            "in the private Task 4 deck",
            "Supplied-video-derived detector and tracker overlay in the private "
            "Task 4 deck",
            "Supplied-video-derived crossing-event sequence in the private "
            "Task 4 deck",
        }
        unexpected = [
            finding
            for finding in findings
            if not (
                finding.code == "RESTRICTED_CONTENT_HASH"
                and finding.detail in expected_private_deck_blockers
                and finding.path.startswith(
                    "slides/HTX_Task4_Operational_Insights.pptx!/"
                )
            )
        ]
        self.assertEqual(
            unexpected,
            [],
            "\n".join(finding.render() for finding in unexpected),
        )


if __name__ == "__main__":
    unittest.main()
