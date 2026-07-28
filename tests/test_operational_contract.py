from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from src.analysis.validate_operational_contract import (
    DEFAULT_PROVENANCE,
    DEFAULT_SCENARIOS,
    DEFAULT_SCENARIO_PROVENANCE,
    REFERENCE_SCENARIO_ID,
    validate_operational_contract,
)
from src.analysis.validate_operational_results import load_result_schemas


def read_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        return list(reader.fieldnames or ()), list(reader)


class OperationalScenarioContractTests(unittest.TestCase):
    def setUp(self) -> None:
        _, self.rows = read_rows(DEFAULT_SCENARIOS)
        self.by_id = {row["scenario_id"]: row for row in self.rows}

    def test_contract_passes_with_explicit_non_calibration_boundary(self) -> None:
        report = validate_operational_contract()

        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["scenario_count"], 15)
        self.assertEqual(report["reference_scenario_id"], REFERENCE_SCENARIO_ID)
        self.assertIn("not calibrated", report["claim_boundary"])
        self.assertTrue(
            all(len(row["config_sha256"]) == 64 for row in report["rows"])
        )

    def test_reference_is_executable_pooled_assumption_sandbox(self) -> None:
        row = self.by_id[REFERENCE_SCENARIO_ID]

        self.assertEqual(row["input_status"], "READY_ASSUMPTION_SANDBOX")
        self.assertEqual(row["calibration_status"], "NOT_CALIBRATED")
        self.assertEqual(row["claim_ceiling"], "COMPARATIVE_WHAT_IF_ONLY")
        self.assertEqual(row["queue_policy"], "pooled")
        self.assertEqual(row["security_capacity"], "36")
        self.assertEqual(row["immigration_capacity"], "21")
        self.assertEqual(row["security_service_p1_seconds"], "21.818181818")
        self.assertEqual(row["immigration_service_p1_seconds"], "13")

    def test_no_ready_scenario_depends_on_unimplemented_separate_lanes(
        self,
    ) -> None:
        self.assertTrue(self.rows)
        self.assertEqual({row["queue_policy"] for row in self.rows}, {"pooled"})
        self.assertNotIn("QUEUE_IMMIGRATION_POOLED", self.by_id)

    def test_named_sg_contexts_are_not_blended(self) -> None:
        expected = {
            REFERENCE_SCENARIO_ID: "13",
            "SERVICE_SG_BUS_QR_10S": "10",
            "SERVICE_SG_TRAIN_KIOSK_24S": "24",
            "SERVICE_SG_TRAIN_MANUAL_45S": "45",
        }
        self.assertEqual(
            {
                scenario_id: self.by_id[scenario_id][
                    "immigration_service_p1_seconds"
                ]
                for scenario_id in expected
            },
            expected,
        )

    def test_risk_is_counter_held_proxy_not_fake_secondary_capacity(
        self,
    ) -> None:
        self.assertNotIn("secondary_capacity", self.rows[0])
        for scenario_id in (
            "RISK_EXTERNAL_P02_D900",
            "RISK_EXTERNAL_P02_D7200",
        ):
            self.assertEqual(
                self.by_id[scenario_id]["additional_check_semantics"],
                "COUNTER_HELD_RISK_REFERRAL_PROXY",
            )

    def test_separate_policy_mutation_fails_contract(self) -> None:
        fieldnames, rows = read_rows(DEFAULT_SCENARIOS)
        rows[0]["queue_policy"] = "separate"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "operational_scenarios.csv"
            with path.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)
            report = validate_operational_contract(
                path, DEFAULT_PROVENANCE, DEFAULT_SCENARIO_PROVENANCE
            )

        self.assertEqual(report["status"], "FAIL")
        self.assertTrue(
            any("unimplemented v2 extension" in error for error in report["errors"])
        )

    def test_unnamed_blend_mutation_fails_named_anchor_and_provenance(
        self,
    ) -> None:
        fieldnames, rows = read_rows(DEFAULT_SCENARIOS)
        rows[0]["immigration_service_p1_seconds"] = "17.5"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "operational_scenarios.csv"
            with path.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)
            report = validate_operational_contract(
                path, DEFAULT_PROVENANCE, DEFAULT_SCENARIO_PROVENANCE
            )

        self.assertEqual(report["status"], "FAIL")
        self.assertTrue(
            any("named 13-second context" in error for error in report["errors"])
        )
        self.assertTrue(
            any("value does not match" in error for error in report["errors"])
        )


class OperationalResultSchemaTests(unittest.TestCase):
    def test_registry_has_ordered_required_tables(self) -> None:
        schemas = load_result_schemas()

        self.assertTrue(
            {
                "run_manifest",
                "entity_log",
                "replication_kpis",
                "scenario_estimates",
                "scenario_contrasts",
            }.issubset(schemas)
        )
        self.assertEqual(
            [row["field_name"] for row in schemas["replication_kpis"]][0:7],
            [
                "schema_version",
                "config_id",
                "config_sha256",
                "model_version",
                "scenario_id",
                "input_sample_id",
                "replication_id",
            ],
        )
        self.assertIn(
            "total_queue_wait_p95_seconds",
            [row["field_name"] for row in schemas["replication_kpis"]],
        )


if __name__ == "__main__":
    unittest.main()
