from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from src.analysis.capacity_availability_design import (
    ANALYSIS_SCENARIO_IDS,
    ARRIVAL_LEVEL_IDS,
    DEFAULT_ANALYSIS_SEED_MANIFEST,
    DEFAULT_DESIGN,
    DEFAULT_REFERENCE_SEED_MANIFEST,
    DEFAULT_SCENARIO_PROVENANCE,
    DEFAULT_SCENARIOS,
    DEFAULT_SEED_MANIFEST,
    EXECUTION_SCENARIO_IDS,
    SCENARIO_PROVENANCE_COLUMNS,
    SEED_COLUMNS,
    build_capacity_availability_provenance_rows,
    build_capacity_availability_analysis_seed_rows,
    build_capacity_availability_scenario_rows,
    build_capacity_availability_seed_rows,
    load_capacity_availability_scenario_rows,
    load_capacity_availability_analysis_seed_rows,
    load_capacity_availability_seed_rows,
    validate_capacity_availability_design,
)
from src.analysis.validate_operational_contract import SCENARIO_COLUMNS


class CapacityAvailabilityDesignTests(unittest.TestCase):
    def test_frozen_design_validates_12_execution_and_15_analysis_cells(
        self,
    ) -> None:
        report = validate_capacity_availability_design()

        self.assertEqual(report["status"], "PASS", report["errors"])
        self.assertEqual(report["execution_arm_count"], 4)
        self.assertEqual(report["arrival_level_count"], 3)
        self.assertEqual(report["execution_cell_count"], 12)
        self.assertEqual(report["analysis_cell_count"], 15)
        self.assertEqual(report["seed_group_count"], 150)
        self.assertEqual(report["analysis_seed_group_count"], 150)
        self.assertEqual(report["new_execution_run_count"], 600)
        self.assertEqual(report["reused_reference_run_count"], 150)
        self.assertEqual(report["analysis_run_count"], 750)
        self.assertFalse(report["adaptive_extension_allowed"])

    def test_execution_grid_has_exact_capacity_pairs_and_canonical_schema(
        self,
    ) -> None:
        rows = load_capacity_availability_scenario_rows()
        expected_pairs = {
            "CAPACITY_AVAIL_SECURITY_MINUS_4": (32, 21),
            "CAPACITY_AVAIL_IMMIGRATION_MINUS_3": (36, 18),
            "CAPACITY_AVAIL_JOINT_MINUS_4_MINUS_3": (32, 18),
            "CAPACITY_AVAIL_SEVERE_JOINT_30_17": (30, 17),
        }

        self.assertEqual(len(rows), 12)
        self.assertTrue(all(tuple(row) == SCENARIO_COLUMNS for row in rows))
        self.assertEqual(
            {
                (row["scenario_id"], row["input_sample_id"])
                for row in rows
            },
            {
                (scenario_id, sample_id)
                for scenario_id in EXECUTION_SCENARIO_IDS
                for sample_id in (
                    "LOCAL_WINDOW_HPP_EXACT95_LOW",
                    "LOCAL_WINDOW_HPP_BASE",
                    "LOCAL_WINDOW_HPP_EXACT95_HIGH",
                )
            },
        )
        for row in rows:
            expected = expected_pairs[row["scenario_id"]]
            self.assertEqual(
                (
                    int(row["security_capacity"]),
                    int(row["immigration_capacity"]),
                ),
                expected,
            )

    def test_generated_csv_files_equal_the_frozen_derivations(self) -> None:
        self.assertEqual(
            load_capacity_availability_scenario_rows(),
            build_capacity_availability_scenario_rows(),
        )
        self.assertEqual(
            load_capacity_availability_seed_rows(),
            build_capacity_availability_seed_rows(),
        )
        self.assertEqual(
            load_capacity_availability_analysis_seed_rows(),
            build_capacity_availability_analysis_seed_rows(),
        )
        with DEFAULT_SCENARIO_PROVENANCE.open(
            encoding="utf-8-sig", newline=""
        ) as handle:
            reader = csv.DictReader(handle)
            self.assertEqual(
                tuple(reader.fieldnames or ()),
                SCENARIO_PROVENANCE_COLUMNS,
            )
            self.assertEqual(
                list(reader),
                build_capacity_availability_provenance_rows(),
            )

    def test_every_new_arm_reuses_exact_part1_seed_tuple(self) -> None:
        availability = load_capacity_availability_seed_rows()
        with DEFAULT_REFERENCE_SEED_MANIFEST.open(
            encoding="utf-8-sig", newline=""
        ) as handle:
            reference = list(csv.DictReader(handle))
        source_by_key = {
            (row["arrival_level_id"], row["replication_id"]): row
            for row in reference
        }

        self.assertEqual(len(availability), 150)
        self.assertEqual(
            {
                (row["arrival_level_id"], row["replication_id"])
                for row in availability
            },
            {
                (level_id, str(replication))
                for level_id in ARRIVAL_LEVEL_IDS
                for replication in range(1, 51)
            },
        )
        for row in availability:
            source = source_by_key[
                (row["arrival_level_id"], row["replication_id"])
            ]
            self.assertEqual(
                tuple(
                    row[field]
                    for field in (
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
                        "master_seed",
                        "arrival_seed",
                        "service_seed",
                        "routing_seed",
                        "tie_seed",
                    )
                ),
            )
            self.assertEqual(
                row["scenario_ids"],
                "|".join(EXECUTION_SCENARIO_IDS),
            )

        analysis_rows = load_capacity_availability_analysis_seed_rows()
        self.assertEqual(len(analysis_rows), 150)
        self.assertTrue(
            all(
                row["scenario_ids"] == "|".join(ANALYSIS_SCENARIO_IDS)
                for row in analysis_rows
            )
        )
        self.assertTrue(DEFAULT_ANALYSIS_SEED_MANIFEST.is_file())

    def test_primary_is_base_joint_reduction_minus_reused_reference_queue_peak(
        self,
    ) -> None:
        design = json.loads(DEFAULT_DESIGN.read_text(encoding="utf-8"))
        primary = design["primary_analysis"]

        self.assertEqual(primary["input_level_id"], "MLE_BASE")
        self.assertEqual(
            primary["scenario_id"],
            "CAPACITY_AVAIL_JOINT_MINUS_4_MINUS_3",
        )
        self.assertEqual(
            primary["reference_scenario_id"],
            "REFERENCE_ASSUMPTION_SANDBOX_V1",
        )
        self.assertEqual(primary["metric"], "peak_total_waiting_queue")
        self.assertEqual(len(ANALYSIS_SCENARIO_IDS) * 3, 15)

    def test_reference_provenance_is_derived_not_observed_roster(self) -> None:
        rows = build_capacity_availability_provenance_rows()
        reference = [
            row
            for row in rows
            if row["scenario_id"] == "REFERENCE_ASSUMPTION_SANDBOX_V1"
        ]

        self.assertEqual(
            {
                (row["parameter_name"], row["parameter_value"])
                for row in reference
            },
            {
                ("security_capacity", "36"),
                ("immigration_capacity", "21"),
            },
        )
        self.assertTrue(
            all(
                row["mapping_role"] == "DERIVED"
                and "Target-utilisation-derived" in row["notes"]
                and "not an observed HTX roster" in row["notes"]
                for row in reference
            )
        )

    def test_validation_rejects_adaptive_extension_and_primary_drift(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            design_path = Path(directory) / "design.json"
            design = json.loads(DEFAULT_DESIGN.read_text(encoding="utf-8"))
            design["run_cap"]["adaptive_extension_allowed"] = True
            design["primary_analysis"]["metric"] = "utilisation"
            design_path.write_text(json.dumps(design), encoding="utf-8")

            report = validate_capacity_availability_design(
                design_path=design_path
            )

        self.assertEqual(report["status"], "FAIL")
        errors = "\n".join(report["errors"])
        self.assertIn("adaptive extension", errors)
        self.assertIn("primary_analysis.metric", errors)

    def test_validation_rejects_seed_tuple_drift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manifest_path = Path(directory) / "seeds.csv"
            with DEFAULT_SEED_MANIFEST.open(
                encoding="utf-8-sig", newline=""
            ) as handle:
                rows = list(csv.DictReader(handle))
            rows[0]["arrival_seed"] = "1"
            with manifest_path.open(
                "w", encoding="utf-8", newline=""
            ) as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=SEED_COLUMNS,
                    lineterminator="\n",
                )
                writer.writeheader()
                writer.writerows(rows)

            report = validate_capacity_availability_design(
                seed_manifest_path=manifest_path
            )

        self.assertEqual(report["status"], "FAIL")
        self.assertIn(
            "arrival_seed does not exactly reuse Part 1",
            "\n".join(report["errors"]),
        )

    def test_checked_in_headers_are_explicit(self) -> None:
        with DEFAULT_SCENARIOS.open(
            encoding="utf-8-sig", newline=""
        ) as handle:
            self.assertEqual(
                tuple(csv.DictReader(handle).fieldnames or ()),
                SCENARIO_COLUMNS,
            )
        with DEFAULT_SEED_MANIFEST.open(
            encoding="utf-8-sig", newline=""
        ) as handle:
            self.assertEqual(
                tuple(csv.DictReader(handle).fieldnames or ()),
                SEED_COLUMNS,
            )


if __name__ == "__main__":
    unittest.main()
