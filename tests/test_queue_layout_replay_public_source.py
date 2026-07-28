from __future__ import annotations

import hashlib
import json
import unittest

from src.analysis.analyse_queue_layout_replay import (
    DEFAULT_ENTITY_LEDGER,
    DEFAULT_REPLICATION_KPIS,
    DEFAULT_SOURCE_MANIFEST,
    PROJECT_ROOT,
    build_parser,
    load_design,
)
from src.analysis.export_queue_layout_replay_source import (
    ENTITY_FIELDS,
    KPI_FIELDS,
    audit_curated_package,
)


class PublicQueueReplaySourceTests(unittest.TestCase):
    def test_curated_package_hashes_and_privacy_audit_pass(self) -> None:
        manifest = audit_curated_package(
            entity_path=DEFAULT_ENTITY_LEDGER,
            kpi_path=DEFAULT_REPLICATION_KPIS,
            manifest_path=DEFAULT_SOURCE_MANIFEST,
        )

        self.assertEqual(manifest["status"], "PASS")
        self.assertEqual(
            manifest["classification"],
            "SYNTHETIC_ANYLOGIC_EVENT_LEDGER",
        )
        self.assertEqual(
            manifest["files"]["entity_ledger.csv"]["row_count"],
            20622,
        )
        self.assertEqual(
            manifest["files"]["registered_p95.csv"]["row_count"],
            50,
        )
        self.assertFalse(
            manifest["privacy_audit"]["contains_video_person_data"]
        )
        self.assertFalse(
            manifest["privacy_audit"]["contains_real_person_identifiers"]
        )

    def test_curated_tables_are_minimum_allowlists_with_lf_endings(self) -> None:
        entity_header = DEFAULT_ENTITY_LEDGER.read_text(
            encoding="utf-8"
        ).splitlines()[0]
        kpi_header = DEFAULT_REPLICATION_KPIS.read_text(
            encoding="utf-8"
        ).splitlines()[0]

        self.assertEqual(entity_header.split(","), list(ENTITY_FIELDS))
        self.assertEqual(kpi_header.split(","), list(KPI_FIELDS))
        self.assertNotIn(b"\r\n", DEFAULT_ENTITY_LEDGER.read_bytes())
        self.assertNotIn(b"\r\n", DEFAULT_REPLICATION_KPIS.read_bytes())

    def test_cli_defaults_to_public_curated_inputs(self) -> None:
        args = build_parser().parse_args(
            ["--output-dir", "results/analysis/test_rerun"]
        )

        self.assertEqual(args.entity_log, DEFAULT_ENTITY_LEDGER)
        self.assertEqual(args.replication_kpis, DEFAULT_REPLICATION_KPIS)
        self.assertEqual(args.source_manifest, DEFAULT_SOURCE_MANIFEST)

    def test_design_claim_ceiling_covers_both_cells(self) -> None:
        design = load_design()

        self.assertEqual(
            design["claim_ceiling"],
            "CONDITIONAL_TWO_CELL_QUEUE_LAYOUT_COUNTERFACTUAL_ONLY",
        )
        self.assertEqual(
            design["public_curated_source"]["dataset_id"],
            "QUEUE_LAYOUT_REPLAY_CURATED_SYNTHETIC_LEDGER_V1",
        )

    def test_committed_analysis_manifest_hashes_every_public_artifact(
        self,
    ) -> None:
        output_dir = (
            PROJECT_ROOT / "results" / "analysis" / "queue_layout_replay"
        )
        manifest = json.loads(
            (output_dir / "analysis_manifest.json").read_text(encoding="utf-8")
        )

        self.assertEqual(manifest["status"], "PASS")
        self.assertEqual(manifest["source_privacy_audit_status"], "PASS")
        self.assertEqual(
            manifest["claim_ceiling"],
            "CONDITIONAL_TWO_CELL_QUEUE_LAYOUT_COUNTERFACTUAL_ONLY",
        )
        for filename, expected in manifest[
            "public_artifact_sha256"
        ].items():
            actual = hashlib.sha256(
                (output_dir / filename).read_bytes()
            ).hexdigest()
            self.assertEqual(actual, expected, filename)


if __name__ == "__main__":
    unittest.main()
