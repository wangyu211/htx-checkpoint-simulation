from __future__ import annotations

import csv
import json
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
                "crossing_count_left_to_right",
                "crossing_count_right_to_left",
                "crossing_count_total",
                "arrival_direction",
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

    def test_frozen_arrival_input_matches_accepted_aggregate(self) -> None:
        by_key = {row["parameter"]: row for row in self.rows}

        self.assertEqual(by_key["crossing_count_left_to_right"]["value"], "12")
        self.assertEqual(by_key["crossing_count_right_to_left"]["value"], "34")
        self.assertEqual(by_key["crossing_count_total"]["value"], "46")
        self.assertEqual(by_key["arrival_direction"]["value"], "right_to_left")
        self.assertEqual(by_key["arrival_direction"]["status"], "VERIFIED")

        arrival = by_key["arrival_rate"]
        self.assertEqual(arrival["status"], "VERIFIED")
        self.assertEqual(arrival["value"], "1.364213")
        self.assertEqual(arrival["unit"], "travellers/second")
        self.assertAlmostEqual(
            float(arrival["value"]),
            34 / 24.922788889,
            places=6,
        )
        confirmatory = json.loads(
            (
                PROJECT_ROOT / "config" / "confirmatory_capacity_study.json"
            ).read_text(encoding="utf-8")
        )
        levels = {
            row["level_id"]: row["arrival_rate_per_second"]
            for row in confirmatory["arrival_rate_uncertainty"]["levels"]
        }
        self.assertAlmostEqual(
            float(arrival["lower"]),
            float(levels["EXACT95_LOW"]),
            places=9,
        )
        self.assertAlmostEqual(
            float(arrival["upper"]),
            float(levels["EXACT95_HIGH"]),
            places=9,
        )
        self.assertLess(float(arrival["lower"]), float(arrival["value"]))
        self.assertGreater(float(arrival["upper"]), float(arrival["value"]))


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


class AnyLogicGateManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.rows = read_csv("config/anylogic_gate_manifest.csv")

    def test_gate_is_exactly_two_inputs_by_three_replications(self) -> None:
        self.assertEqual(len(self.rows), 6)
        by_input: dict[str, set[int]] = {}
        for row in self.rows:
            by_input.setdefault(row["input_sample_id"], set()).add(
                int(row["replication_id"])
            )
        self.assertEqual(
            by_input,
            {
                "GATE_INPUT_A": {1, 2, 3},
                "GATE_INPUT_B": {1, 2, 3},
            },
        )

    def test_gate_seed_lineage_is_unique_and_deterministic(self) -> None:
        seeds = [int(row["run_seed"]) for row in self.rows]
        self.assertEqual(len(seeds), len(set(seeds)))
        for row in self.rows:
            expected = (
                202607270000
                + 100 * (int(row["input_sample_index"]) + 1)
                + int(row["replication_id"])
            )
            self.assertEqual(int(row["run_seed"]), expected)
            self.assertEqual(int(row["gate_entity_count"]), 12)


if __name__ == "__main__":
    unittest.main()
