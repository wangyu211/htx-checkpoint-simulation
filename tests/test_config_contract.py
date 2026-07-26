from __future__ import annotations

import csv
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def read_csv(name: str) -> list[dict[str, str]]:
    with (PROJECT_ROOT / name).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


class ParameterRegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.rows = read_csv("config/parameter_registry.csv")

    def test_parameter_keys_are_unique_and_required_keys_exist(self) -> None:
        keys = [row["parameter"] for row in self.rows]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertTrue(
            {
                "video_sha256",
                "video_duration",
                "arrival_rate",
                "security_capacity",
                "immigration_capacity",
                "security_service_time",
                "immigration_service_time",
                "automation_uptake",
                "automation_multiplier",
                "demand_multiplier",
            }.issubset(keys)
        )

    def test_status_and_source_classes_are_declared(self) -> None:
        allowed_status = {"VERIFIED", "WORKING", "PLANNED", "TBD"}
        allowed_source_class = {
            "MEASURED_METADATA",
            "MEASURED_VIDEO",
            "TRANSPARENT_ASSUMPTION",
            "EXTERNAL_SCENARIO_ANCHOR",
            "ILLUSTRATIVE_SCENARIO",
        }
        self.assertFalse(
            {row["status"] for row in self.rows} - allowed_status
        )
        self.assertFalse(
            {row["source_class"] for row in self.rows} - allowed_source_class
        )

    def test_unfrozen_arrival_input_has_no_hidden_value(self) -> None:
        arrival = next(row for row in self.rows if row["parameter"] == "arrival_rate")
        self.assertEqual(arrival["status"], "TBD")
        self.assertEqual(arrival["value"], "")


class ScenarioRegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.rows = read_csv("config/scenarios.csv")

    def test_scenario_ids_are_unique(self) -> None:
        ids = [row["scenario_id"] for row in self.rows]
        self.assertEqual(len(ids), len(set(ids)))

    def test_scenario_values_stay_inside_schema_domain(self) -> None:
        for row in self.rows:
            with self.subTest(scenario_id=row["scenario_id"]):
                self.assertGreater(float(row["demand_multiplier"]), 0.0)
                self.assertGreaterEqual(int(row["security_capacity_delta"]), 0)
                self.assertGreaterEqual(int(row["immigration_capacity_delta"]), 0)
                self.assertIn(row["queue_policy"], {"separate", "pooled"})
                self.assertGreaterEqual(float(row["automation_uptake"]), 0.0)
                self.assertLessEqual(float(row["automation_uptake"]), 1.0)
                self.assertGreater(float(row["automation_multiplier"]), 0.0)
                self.assertEqual(row["status"], "PLANNED")


if __name__ == "__main__":
    unittest.main()
