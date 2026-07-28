from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from src.analysis.analyse_operational_replications import (
    alignment_report_passes,
)
from src.analysis.validate_crn_alignment import validate_crn_alignment


def write_csv(
    path: Path,
    fieldnames: list[str],
    rows: list[dict[str, str]],
) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


class CrnAlignmentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.results = self.root / "results"
        self.results.mkdir()
        self.seed_manifest = self.root / "confirmatory_seed_manifest.csv"
        self.design = self.root / "confirmatory_capacity_study.json"
        self.design.write_text(
            json.dumps({"study_id": "TEST_CONFIRMATORY"}),
            encoding="utf-8",
        )
        self.scenarios = ["REFERENCE", "CAPACITY_BOTH_PLUS"]
        self.seed_row = {
            "schema_version": "1.0",
            "study_id": "TEST_CONFIRMATORY",
            "pairing_group_id": "CRN_BASE_R001",
            "arrival_level_id": "MLE_BASE",
            "input_sample_id": "LOCAL_WINDOW_HPP_BASE",
            "replication_id": "1",
            "scenario_ids": "|".join(self.scenarios),
            "master_seed": "1000",
            "arrival_seed": "1011",
            "service_seed": "1012",
            "routing_seed": "1013",
            "tie_seed": "1014",
        }
        write_csv(
            self.seed_manifest,
            list(self.seed_row),
            [self.seed_row],
        )
        self.run_rows = []
        self.entity_rows = []
        for scenario_index, scenario_id in enumerate(self.scenarios):
            self.run_rows.append(
                {
                    "scenario_id": scenario_id,
                    "input_sample_id": "LOCAL_WINDOW_HPP_BASE",
                    "replication_id": "1",
                    "master_seed": "1000",
                    "arrival_seed": "1011",
                    "service_seed": "1012",
                    "routing_seed": "1013",
                    "tie_seed": "1014",
                    "run_status": "COMPLETE",
                }
            )
            for traveller_id, arrival in (("T001", "1.25"), ("T002", "2.5")):
                self.entity_rows.append(
                    {
                        "scenario_id": scenario_id,
                        "input_sample_id": "LOCAL_WINDOW_HPP_BASE",
                        "replication_id": "1",
                        "traveller_id": traveller_id,
                        "arrival_seconds": arrival,
                        "security_service_demand_seconds": "21.818181818",
                        "immigration_conventional_service_demand_seconds": "13",
                        "automation_u": "0.2",
                        "additional_check_u": "0.3",
                        "lane_tie_u": "0.4",
                        "security_start_seconds": str(
                            float(arrival) + scenario_index
                        ),
                    }
                )

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def write_results(self) -> None:
        write_csv(
            self.results / "run_manifest.csv",
            list(self.run_rows[0]),
            self.run_rows,
        )
        write_csv(
            self.results / "entity_log.csv",
            list(self.entity_rows[0]),
            self.entity_rows,
        )

    def test_pass_requires_seeds_travellers_and_branch_invariant_draws(
        self,
    ) -> None:
        self.write_results()

        report = validate_crn_alignment(
            self.results,
            self.seed_manifest,
            design_path=self.design,
        )

        self.assertEqual(report["status"], "PASS", report["errors"])
        self.assertTrue(report["coverage_pass"])
        self.assertTrue(report["seed_alignment_pass"])
        self.assertTrue(report["traveller_level_alignment_pass"])
        self.assertTrue(report["branch_invariant_draws_pass"])
        self.assertEqual(report["compared_traveller_pairs"], 2)
        self.assertEqual(report["compared_draw_values"], 12)
        self.assertTrue(alignment_report_passes(report))

    def test_shared_seed_claim_fails_when_a_stream_seed_differs(self) -> None:
        self.run_rows[1]["service_seed"] = "9999"
        self.write_results()

        report = validate_crn_alignment(
            self.results,
            self.seed_manifest,
            design_path=self.design,
        )

        self.assertEqual(report["status"], "FAIL")
        self.assertFalse(report["seed_alignment_pass"])
        self.assertTrue(
            any("service_seed mismatch" in error for error in report["errors"])
        )
        self.assertFalse(alignment_report_passes(report))

    def test_traveller_id_coverage_must_match(self) -> None:
        self.entity_rows = [
            row
            for row in self.entity_rows
            if not (
                row["scenario_id"] == "CAPACITY_BOTH_PLUS"
                and row["traveller_id"] == "T002"
            )
        ]
        self.write_results()

        report = validate_crn_alignment(
            self.results,
            self.seed_manifest,
            design_path=self.design,
        )

        self.assertEqual(report["status"], "FAIL")
        self.assertFalse(report["traveller_level_alignment_pass"])
        self.assertFalse(report["branch_invariant_draws_pass"])

    def test_branch_invariant_draw_mismatch_blocks_pairing(self) -> None:
        comparison = next(
            row
            for row in self.entity_rows
            if row["scenario_id"] == "CAPACITY_BOTH_PLUS"
            and row["traveller_id"] == "T001"
        )
        comparison["automation_u"] = "0.2001"
        self.write_results()

        report = validate_crn_alignment(
            self.results,
            self.seed_manifest,
            design_path=self.design,
        )

        self.assertEqual(report["status"], "FAIL")
        self.assertTrue(report["traveller_level_alignment_pass"])
        self.assertFalse(report["branch_invariant_draws_pass"])
        self.assertTrue(
            any("automation_u differs" in error for error in report["errors"])
        )


if __name__ == "__main__":
    unittest.main()
