from __future__ import annotations

import unittest

from src.analysis.capacity_response_surface_design import (
    EXPECTED_IMMIGRATION_CAPACITIES,
    EXPECTED_SECURITY_CAPACITIES,
    build_response_surface_scenario_rows,
    build_response_surface_seed_rows,
    cross_batch_validation_cells,
    execution_cells,
    full_grid,
    load_design,
    validate_response_surface_design,
)
from src.analysis.validate_operational_contract import scenario_config_sha256


class CapacityResponseSurfaceDesignTests(unittest.TestCase):
    def test_frozen_design_validates(self) -> None:
        report = validate_response_surface_design()
        self.assertEqual(report["status"], "PASS", report["errors"])
        self.assertEqual(report["full_grid_cell_count"], 54)
        self.assertEqual(report["new_execution_cell_count"], 54)
        self.assertEqual(report["new_execution_run_count"], 2700)
        self.assertEqual(report["analysis_run_count"], 2700)

    def test_every_integer_capacity_across_threshold_region_is_run(self) -> None:
        expected = [
            (security, immigration)
            for security in EXPECTED_SECURITY_CAPACITIES
            for immigration in EXPECTED_IMMIGRATION_CAPACITIES
        ]
        self.assertEqual(full_grid(), expected)
        self.assertEqual(execution_cells(), expected)

    def test_response_rows_are_base_only_and_unique(self) -> None:
        rows = build_response_surface_scenario_rows()
        self.assertEqual(len(rows), 54)
        self.assertEqual(
            {row["input_sample_id"] for row in rows},
            {"LOCAL_WINDOW_HPP_BASE"},
        )
        self.assertEqual(
            {row["arrival_rate_per_second"] for row in rows},
            {"1.3642132969720073"},
        )
        self.assertEqual(
            {(int(row["security_capacity"]), int(row["immigration_capacity"]))
             for row in rows},
            set(full_grid()),
        )
        self.assertEqual(
            len({scenario_config_sha256(row) for row in rows}),
            54,
        )
        self.assertTrue(
            all(row["pilot_replications"] == "50" for row in rows)
        )
        self.assertTrue(
            all(
                row["input_status"] == "FROZEN_RESPONSE_SURFACE_DESIGN"
                for row in rows
            )
        )

    def test_all_cells_reuse_exact_base_seed_tuple_by_replication(self) -> None:
        rows = build_response_surface_seed_rows()
        self.assertEqual(len(rows), 50)
        self.assertEqual(
            {row["replication_id"] for row in rows},
            {str(value) for value in range(1, 51)},
        )
        self.assertEqual(
            {row["arrival_level_id"] for row in rows},
            {"MLE_BASE"},
        )
        self.assertEqual(
            {row["input_sample_id"] for row in rows},
            {"LOCAL_WINDOW_HPP_BASE"},
        )
        self.assertTrue(
            all(
                len(row["scenario_ids"].split("|")) == 54
                for row in rows
            )
        )

    def test_old_cells_are_validation_only(self) -> None:
        design = load_design()
        self.assertEqual(
            design["analysis_role"],
            "EXPLORATORY_SENSITIVITY_NOT_CONFIRMATORY",
        )
        self.assertFalse(design["execution"]["adaptive_extension_allowed"])
        self.assertEqual(
            design["analysis"]["ideal_case_comparator"]["name"],
            "DETERMINISTIC_IDEAL_CONTROL_V1",
        )
        self.assertTrue(
            design["analysis"]["ideal_case_comparator"]["same_capacity_grid"]
        )
        validation_cells = cross_batch_validation_cells()
        self.assertEqual(len(validation_cells), 5)
        self.assertTrue(set(validation_cells).issubset(set(execution_cells())))


if __name__ == "__main__":
    unittest.main()
