from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from src.analysis.peak_duration_sensitivity_design import (
    DEFAULT_DESIGN,
    DEFAULT_REFERENCE_SEED_MANIFEST,
    DEFAULT_SCENARIOS,
    DEFAULT_SEED_MANIFEST,
    EXPECTED_BASE_RATE,
    EXPECTED_CAPACITY_CELLS,
    EXPECTED_CUTOFF_SECONDS,
    EXPECTED_GUARDS,
    EXPECTED_TARGET_INPUT_SAMPLE_ID,
    SEED_COLUMNS,
    arrival_guard,
    build_peak_duration_scenario_rows,
    build_peak_duration_seed_rows,
    execution_cells,
    load_peak_duration_scenario_rows,
    load_peak_duration_seed_rows,
    validate_peak_duration_design,
    write_generated_artifacts,
)
from src.analysis.validate_operational_contract import (
    SCENARIO_COLUMNS,
    scenario_config_sha256,
)


class PeakDurationSensitivityDesignTests(unittest.TestCase):
    def test_frozen_design_validates_20_cells_and_1000_planned_runs(
        self,
    ) -> None:
        report = validate_peak_duration_design()

        self.assertEqual(report["status"], "PASS", report["errors"])
        self.assertEqual(report["selected_capacity_cell_count"], 4)
        self.assertEqual(report["duration_level_count"], 5)
        self.assertEqual(report["study_cell_count"], 20)
        self.assertEqual(report["seed_group_count"], 50)
        self.assertEqual(report["planned_run_count"], 1000)
        self.assertEqual(report["execution_status"], "NOT_EXECUTED")

    def test_exact_selected_cell_and_duration_order_is_frozen(self) -> None:
        expected = [
            (security, immigration, cutoff)
            for security, immigration in EXPECTED_CAPACITY_CELLS
            for cutoff in EXPECTED_CUTOFF_SECONDS
        ]
        self.assertEqual(execution_cells(), expected)

    def test_dynamic_guards_match_formula_and_synchronize_queue_caps(
        self,
    ) -> None:
        self.assertEqual(
            {
                cutoff: arrival_guard(EXPECTED_BASE_RATE, cutoff)
                for cutoff in EXPECTED_CUTOFF_SECONDS
            },
            EXPECTED_GUARDS,
        )

        rows = build_peak_duration_scenario_rows()
        for row in rows:
            expected = str(
                EXPECTED_GUARDS[int(row["arrival_cutoff_seconds"])]
            )
            self.assertEqual(row["arrival_guard"], expected)
            self.assertEqual(row["security_queue_capacity"], expected)
            self.assertEqual(row["immigration_queue_capacity"], expected)

    def test_scenarios_keep_canonical_schema_and_unique_hashes(self) -> None:
        rows = build_peak_duration_scenario_rows()

        self.assertEqual(len(rows), 20)
        self.assertTrue(all(tuple(row) == SCENARIO_COLUMNS for row in rows))
        self.assertEqual(
            {row["input_sample_id"] for row in rows},
            {EXPECTED_TARGET_INPUT_SAMPLE_ID},
        )
        self.assertEqual(
            {row["arrival_rate_per_second"] for row in rows},
            {"1.3642132969720073"},
        )
        self.assertEqual(
            len({scenario_config_sha256(row) for row in rows}),
            20,
        )
        self.assertTrue(
            all(
                row["input_status"]
                == "FROZEN_PEAK_DURATION_SENSITIVITY_DESIGN"
                for row in rows
            )
        )

    def test_all_cells_reuse_exact_base_seed_tuple_by_replication(
        self,
    ) -> None:
        design = json.loads(DEFAULT_DESIGN.read_text(encoding="utf-8"))
        self.assertEqual(
            design["seed_policy"]["source_input_sample_id"],
            "LOCAL_WINDOW_HPP_BASE",
        )
        self.assertEqual(
            design["seed_policy"]["target_input_sample_id"],
            EXPECTED_TARGET_INPUT_SAMPLE_ID,
        )
        rows = build_peak_duration_seed_rows()
        with DEFAULT_REFERENCE_SEED_MANIFEST.open(
            encoding="utf-8-sig",
            newline="",
        ) as handle:
            source_rows = [
                row
                for row in csv.DictReader(handle)
                if row["arrival_level_id"] == "MLE_BASE"
                and row["input_sample_id"] == "LOCAL_WINDOW_HPP_BASE"
            ]
        source_by_replication = {
            row["replication_id"]: row for row in source_rows
        }

        self.assertEqual(len(rows), 50)
        self.assertTrue(
            all(len(row["scenario_ids"].split("|")) == 20 for row in rows)
        )
        self.assertEqual(
            {row["input_sample_id"] for row in rows},
            {EXPECTED_TARGET_INPUT_SAMPLE_ID},
        )
        for row in rows:
            source = source_by_replication[row["replication_id"]]
            self.assertEqual(
                tuple(
                    row[field]
                    for field in (
                        "pairing_group_id",
                        "master_seed",
                        "arrival_seed",
                        "service_seed",
                        "routing_seed",
                        "tie_seed",
                    )
                ),
                tuple(
                    source[field]
                    for field in (
                        "pairing_group_id",
                        "master_seed",
                        "arrival_seed",
                        "service_seed",
                        "routing_seed",
                        "tie_seed",
                    )
                ),
            )

    def test_generated_csv_files_equal_frozen_derivations(self) -> None:
        self.assertEqual(
            load_peak_duration_scenario_rows(),
            build_peak_duration_scenario_rows(),
        )
        self.assertEqual(
            load_peak_duration_seed_rows(),
            build_peak_duration_seed_rows(),
        )

    def test_validator_rejects_guard_and_execution_status_drift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            design_path = root / "design.json"
            scenario_path = root / "scenarios.csv"
            seed_path = root / "seeds.csv"
            design = json.loads(DEFAULT_DESIGN.read_text(encoding="utf-8"))
            design["execution_status"] = "EXECUTED"
            design["guard_policy"]["computed_values"][-1][
                "arrival_and_queue_guard"
            ] = 5000
            design_path.write_text(json.dumps(design), encoding="utf-8")
            write_generated_artifacts(
                design_path=design_path,
                scenarios_path=scenario_path,
                seed_manifest_path=seed_path,
            )

            report = validate_peak_duration_design(
                design_path=design_path,
                scenarios_path=scenario_path,
                seed_manifest_path=seed_path,
            )

        self.assertEqual(report["status"], "FAIL")
        errors = "\n".join(report["errors"])
        self.assertIn("execution status", errors)
        self.assertIn("precomputed arrival/queue guards", errors)

    def test_validator_rejects_seed_tuple_and_scenario_hash_drift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            scenario_path = root / "scenarios.csv"
            seed_path = root / "seeds.csv"

            scenarios = build_peak_duration_scenario_rows()
            scenarios[0]["notes"] = "tampered"
            with scenario_path.open(
                "w",
                encoding="utf-8",
                newline="",
            ) as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=SCENARIO_COLUMNS,
                    lineterminator="\n",
                )
                writer.writeheader()
                writer.writerows(scenarios)

            seeds = build_peak_duration_seed_rows()
            seeds[0]["arrival_seed"] = "1"
            with seed_path.open(
                "w",
                encoding="utf-8",
                newline="",
            ) as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=SEED_COLUMNS,
                    lineterminator="\n",
                )
                writer.writeheader()
                writer.writerows(seeds)

            report = validate_peak_duration_design(
                scenarios_path=scenario_path,
                seed_manifest_path=seed_path,
            )

        self.assertEqual(report["status"], "FAIL")
        errors = "\n".join(report["errors"])
        self.assertIn("scenario CSV does not equal", errors)
        self.assertIn("arrival_seed does not exactly reuse Base", errors)
        self.assertIn("seed CSV does not equal", errors)


if __name__ == "__main__":
    unittest.main()
