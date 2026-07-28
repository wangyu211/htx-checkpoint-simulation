from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from src.analysis.confirmatory_design import (
    CAPACITY_SCENARIO_IDS,
    DEFAULT_DESIGN,
    DEFAULT_SEED_MANIFEST,
    build_confirmatory_scenario_rows,
    conservative_independent_half_width,
    exact_poisson_rate_interval,
    minimum_equal_arm_replications,
    validate_confirmatory_design,
)
from src.analysis.validate_operational_contract import (
    SCENARIO_COLUMNS,
    scenario_config_sha256,
)


class ConfirmatoryDesignTests(unittest.TestCase):
    def test_exact_poisson_rate_interval_matches_frozen_levels(self) -> None:
        low, high = exact_poisson_rate_interval(34, 24.922788889)

        self.assertAlmostEqual(low, 0.9447573660171154, places=12)
        self.assertAlmostEqual(34 / 24.922788889, 1.3642132969720073, places=12)
        self.assertAlmostEqual(high, 1.90635134401724, places=12)

    def test_precision_plan_uses_independent_worst_arm_envelope(self) -> None:
        pilot_envelope = 2.44782200108

        self.assertEqual(
            minimum_equal_arm_replications(pilot_envelope, 1.0),
            48,
        )
        self.assertGreater(
            conservative_independent_half_width(pilot_envelope, 47),
            1.0,
        )
        self.assertLessEqual(
            conservative_independent_half_width(pilot_envelope, 50),
            1.0,
        )

    def test_frozen_design_and_seed_manifest_are_internally_consistent(
        self,
    ) -> None:
        report = validate_confirmatory_design()

        self.assertEqual(report["status"], "PASS", report["errors"])
        self.assertEqual(report["study_cell_count"], 12)
        self.assertEqual(report["seed_group_count"], 150)
        self.assertEqual(report["total_run_cap"], 600)
        self.assertEqual(
            report["independent_precision_plan"][
                "minimum_replications_per_arm"
            ],
            48,
        )

    def test_design_explicitly_excludes_human_adjudication_error(self) -> None:
        design = json.loads(DEFAULT_DESIGN.read_text(encoding="utf-8"))
        uncertainty = design["arrival_rate_uncertainty"]

        self.assertEqual(
            uncertainty["uncertainty_scope"],
            "HPP_COUNTING_PROCESS_ONLY",
        )
        self.assertIn(
            "HUMAN_ADJUDICATION_ERROR",
            uncertainty["explicit_exclusions"],
        )

    def test_derived_rows_are_a_unique_three_by_four_frozen_grid(self) -> None:
        rows = build_confirmatory_scenario_rows()

        self.assertEqual(len(rows), 12)
        self.assertTrue(
            all(tuple(row) == SCENARIO_COLUMNS for row in rows)
        )
        self.assertEqual(
            {
                (row["scenario_id"], row["input_sample_id"])
                for row in rows
            },
            {
                (scenario_id, sample_id)
                for scenario_id in CAPACITY_SCENARIO_IDS
                for sample_id in (
                    "LOCAL_WINDOW_HPP_EXACT95_LOW",
                    "LOCAL_WINDOW_HPP_BASE",
                    "LOCAL_WINDOW_HPP_EXACT95_HIGH",
                )
            },
        )
        self.assertEqual(
            len({row["config_id"] for row in rows}),
            12,
        )
        self.assertEqual(
            len({scenario_config_sha256(row) for row in rows}),
            12,
        )
        self.assertTrue(
            all(
                row["crn_alignment_status"] == "PENDING_VALIDATION"
                and row["pilot_replications"] == "50"
                and row["input_status"] == "FROZEN_CONFIRMATORY_DESIGN"
                for row in rows
            )
        )

    def test_seed_manifest_rejects_wrong_lineage_even_at_150_rows(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_path = root / "seed_manifest.csv"
            with DEFAULT_SEED_MANIFEST.open(
                encoding="utf-8-sig", newline=""
            ) as handle:
                reader = csv.DictReader(handle)
                fields = list(reader.fieldnames or ())
                rows = list(reader)

            rows[0]["study_id"] = "FOREIGN_STUDY"
            rows[1]["input_sample_id"] = "WRONG_SAMPLE"
            rows[2]["arrival_level_id"] = "MLE_BASE"
            with manifest_path.open(
                "w", encoding="utf-8", newline=""
            ) as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=fields,
                    lineterminator="\n",
                )
                writer.writeheader()
                writer.writerows(rows)

            report = validate_confirmatory_design(
                DEFAULT_DESIGN,
                manifest_path,
            )

        self.assertEqual(report["status"], "FAIL")
        errors = "\n".join(report["errors"])
        self.assertIn("study_id does not match", errors)
        self.assertIn("input_sample_id does not match", errors)
        self.assertIn("duplicate arrival-level/replication group", errors)
        self.assertIn("seed manifest is missing", errors)

    def test_design_rejects_duplicate_cell_and_run_cap_drift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            design_path = Path(directory) / "design.json"
            design = json.loads(DEFAULT_DESIGN.read_text(encoding="utf-8"))
            design["study_cells"][1] = dict(design["study_cells"][0])
            design["run_cap"]["study_cell_count"] = 11
            design["run_cap"]["adaptive_extension_allowed"] = True
            design_path.write_text(
                json.dumps(design),
                encoding="utf-8",
            )

            report = validate_confirmatory_design(
                design_path,
                DEFAULT_SEED_MANIFEST,
            )

        self.assertEqual(report["status"], "FAIL")
        errors = "\n".join(report["errors"])
        self.assertIn("duplicate study cell_id", errors)
        self.assertIn("duplicate study cell for", errors)
        self.assertIn("study_cell_count", errors)
        self.assertIn("adaptive extension", errors)


if __name__ == "__main__":
    unittest.main()
