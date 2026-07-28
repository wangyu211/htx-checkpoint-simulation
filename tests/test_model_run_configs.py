from __future__ import annotations

import csv
import unittest
from pathlib import Path

from src.analysis.validate_model_run_configs import (
    DEFAULT_CONFIG,
    PROJECT_ROOT,
    validate_config_contract,
    validate_config_row,
)


def read_rows() -> list[dict[str, str]]:
    with DEFAULT_CONFIG.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


class ModelRunConfigurationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.rows = read_rows()
        self.by_id = {row["config_id"]: row for row in self.rows}

    def test_contract_is_valid_while_exposing_blocked_operational_inputs(
        self,
    ) -> None:
        report = validate_config_contract(DEFAULT_CONFIG)

        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["ready_configs"], ["VERIFY_TWO_STAGE_A"])
        self.assertEqual(
            report["blocked_configs"], ["BASELINE_LOCAL_WINDOW_HPP"]
        )

    def test_synthetic_oracle_preserves_exact_verified_values(self) -> None:
        row = self.by_id["VERIFY_TWO_STAGE_A"]

        self.assertEqual(row["purpose"], "SYNTHETIC_ORACLE")
        self.assertEqual(row["arrival_mode"], "DETERMINISTIC_FIXTURE")
        self.assertEqual(row["max_arrivals"], "6")
        self.assertEqual(row["arrival_cutoff_seconds"], "6.5")
        self.assertEqual(row["security_capacity"], "1")
        self.assertEqual(row["immigration_capacity"], "1")
        self.assertEqual(row["security_queue_capacity"], "6")
        self.assertEqual(row["immigration_queue_capacity"], "6")
        self.assertEqual(row["security_service_p1_seconds"], "2.0")
        self.assertEqual(row["immigration_service_p1_seconds"], "3.0")
        self.assertEqual(row["input_status"], "READY")

    def test_assessment_row_uses_only_frozen_arrival_evidence(self) -> None:
        row = self.by_id["BASELINE_LOCAL_WINDOW_HPP"]
        report = validate_config_row(row)

        self.assertEqual(row["arrival_evidence_id"], "task1_final_aggregate")
        self.assertEqual(row["arrival_mode"], "HPP")
        self.assertEqual(row["arrival_rate_per_second"], "1.364213")
        self.assertEqual(
            row["arrival_assumption"],
            "LOCAL_WINDOW_HPP_STATIONARY_INDEPENDENT",
        )
        self.assertEqual(row["max_arrivals"], "")
        self.assertEqual(report["computed_status"], "BLOCKED_INPUTS")
        self.assertFalse(report["executable"])
        self.assertIn(
            "security_capacity is not frozen",
            report["blockers"],
        )
        self.assertIn(
            "immigration_capacity is not frozen",
            report["blockers"],
        )
        self.assertIn(
            "security_queue_capacity is not frozen",
            report["blockers"],
        )
        self.assertIn(
            "immigration_queue_capacity is not frozen",
            report["blockers"],
        )
        self.assertIn(
            "security_service_distribution is not frozen",
            report["blockers"],
        )
        self.assertIn(
            "immigration_service_distribution is not frozen",
            report["blockers"],
        )
        self.assertIn(
            "additional_check_probability is not frozen",
            report["blockers"],
        )

    def test_trace_mode_cannot_be_ready_without_an_event_ledger(self) -> None:
        row = dict(self.by_id["BASELINE_LOCAL_WINDOW_HPP"])
        row["arrival_mode"] = "TRACE"
        row["arrival_rate_per_second"] = ""
        row["arrival_trace_path"] = ""
        row["input_status"] = "BLOCKED_INPUTS"

        report = validate_config_row(row, project_root=PROJECT_ROOT)

        self.assertIn("arrival_trace_path is not frozen", report["blockers"])
        self.assertFalse(report["executable"])

    def test_ready_declaration_fails_if_a_required_input_is_missing(self) -> None:
        row = dict(self.by_id["VERIFY_TWO_STAGE_A"])
        row["security_capacity"] = ""

        report = validate_config_row(row)

        self.assertEqual(report["computed_status"], "BLOCKED_INPUTS")
        self.assertTrue(
            any("input_status=READY" in error for error in report["errors"])
        )


if __name__ == "__main__":
    unittest.main()
