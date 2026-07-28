from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from src.analysis.service_variability_design import (
    CV_LEVELS,
    DEFAULT_REFERENCE_SEED_MANIFEST,
    DEFAULT_SCENARIOS,
    MODEL_VERSION,
    REFERENCE_SCENARIO_ID,
    SERVICE_SCENARIO_COLUMNS,
    build_service_variability_scenario_rows,
    build_service_variability_seed_rows,
    load_design,
    service_scenario_config_sha256,
    study_cells,
    validate_service_variability_design,
)
from src.analysis.validate_operational_contract import (
    DEFAULT_SCENARIOS as DEFAULT_OPERATIONAL_SCENARIOS,
    SCENARIO_COLUMNS,
    scenario_config_sha256,
)


def read_rows(path: Path) -> tuple[tuple[str, ...], list[dict[str, str]]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return tuple(reader.fieldnames or ()), list(reader)


class ServiceVariabilityDesignTests(unittest.TestCase):
    def test_frozen_design_validates(self) -> None:
        report = validate_service_variability_design()

        self.assertEqual(report["status"], "PASS", report["errors"])
        self.assertEqual(report["scenario_count"], 9)
        self.assertEqual(report["seed_group_count"], 50)
        self.assertEqual(report["run_count"], 450)
        self.assertEqual(report["model_version"], MODEL_VERSION)
        self.assertTrue(report["old_scenario_schema_unchanged"])

    def test_study_schema_is_append_only_and_old_hash_is_unchanged(self) -> None:
        self.assertEqual(SERVICE_SCENARIO_COLUMNS[:-2], SCENARIO_COLUMNS)
        self.assertEqual(
            SERVICE_SCENARIO_COLUMNS[-2:],
            ("security_service_cv", "immigration_service_cv"),
        )
        self.assertNotIn("security_service_cv", SCENARIO_COLUMNS)
        self.assertNotIn("immigration_service_cv", SCENARIO_COLUMNS)

        fields, rows = read_rows(DEFAULT_OPERATIONAL_SCENARIOS)
        self.assertEqual(fields, SCENARIO_COLUMNS)
        reference = next(
            row
            for row in rows
            if row["scenario_id"] == "REFERENCE_ASSUMPTION_SANDBOX_V1"
        )
        self.assertEqual(
            scenario_config_sha256(reference),
            "166e6c918cff63041b08f31ff5c17fbea49008b8cdd3047b1082b326faae3460",
        )

    def test_full_factorial_preserves_means_and_maps_distributions(self) -> None:
        rows = build_service_variability_scenario_rows()
        self.assertEqual(
            study_cells(),
            [
                (security_cv, immigration_cv)
                for security_cv in CV_LEVELS
                for immigration_cv in CV_LEVELS
            ],
        )
        self.assertEqual(len(rows), 9)
        self.assertEqual(
            {
                (
                    float(row["security_service_cv"]),
                    float(row["immigration_service_cv"]),
                )
                for row in rows
            },
            set(study_cells()),
        )
        self.assertEqual(
            {row["security_service_p1_seconds"] for row in rows},
            {"21.818181818"},
        )
        self.assertEqual(
            {row["immigration_service_p1_seconds"] for row in rows},
            {"13"},
        )
        for row in rows:
            security_cv = float(row["security_service_cv"])
            immigration_cv = float(row["immigration_service_cv"])
            self.assertEqual(
                row["security_service_distribution"],
                "FIXED" if security_cv == 0 else "LOGNORMAL_MEAN_CV",
            )
            self.assertEqual(
                row["immigration_service_distribution"],
                "FIXED" if immigration_cv == 0 else "LOGNORMAL_MEAN_CV",
            )
            self.assertEqual(row["reference_scenario_id"], REFERENCE_SCENARIO_ID)
            self.assertEqual(
                row["input_status"],
                "FROZEN_SERVICE_VARIABILITY_DESIGN",
            )
            self.assertEqual(row["pilot_replications"], "50")

    def test_extended_hash_binds_both_cv_fields(self) -> None:
        rows = build_service_variability_scenario_rows()
        hashes = {service_scenario_config_sha256(row) for row in rows}
        self.assertEqual(len(hashes), 9)

        row = dict(rows[0])
        original = service_scenario_config_sha256(row)
        row["security_service_cv"] = "0.5"
        self.assertNotEqual(service_scenario_config_sha256(row), original)
        row = dict(rows[0])
        row["immigration_service_cv"] = "1"
        self.assertNotEqual(service_scenario_config_sha256(row), original)

    def test_seed_manifest_exactly_reuses_all_base_seed_tuples(self) -> None:
        generated = build_service_variability_seed_rows()
        fields, source_rows = read_rows(DEFAULT_REFERENCE_SEED_MANIFEST)
        self.assertTrue(fields)
        source = {
            row["replication_id"]: row
            for row in source_rows
            if row["arrival_level_id"] == "MLE_BASE"
            and row["input_sample_id"] == "LOCAL_WINDOW_HPP_BASE"
        }
        self.assertEqual(len(generated), 50)
        self.assertEqual(
            {row["replication_id"] for row in generated},
            {str(value) for value in range(1, 51)},
        )
        for row in generated:
            registered = source[row["replication_id"]]
            for field in (
                "master_seed",
                "arrival_seed",
                "service_seed",
                "routing_seed",
                "tie_seed",
            ):
                with self.subTest(replication=row["replication_id"], field=field):
                    self.assertEqual(row[field], registered[field])
            self.assertEqual(len(row["scenario_ids"].split("|")), 9)

    def test_distribution_mutation_fails_closed(self) -> None:
        fields, rows = read_rows(DEFAULT_SCENARIOS)
        row = next(
            item
            for item in rows
            if item["security_service_cv"] == "0.5"
        )
        row["security_service_distribution"] = "FIXED"

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "service_variability_scenarios.csv"
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=fields,
                    lineterminator="\n",
                )
                writer.writeheader()
                writer.writerows(rows)
            report = validate_service_variability_design(
                scenarios_path=path,
            )

        self.assertEqual(report["status"], "FAIL")
        self.assertTrue(
            any(
                "differ from deterministic design" in error
                for error in report["errors"]
            )
        )

    def test_model_version_mutation_fails_closed(self) -> None:
        design = load_design()
        design["model_version"] = design["study_id"]

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "service_variability_study.json"
            path.write_text(
                json.dumps(design, indent=2) + "\n",
                encoding="utf-8",
            )
            report = validate_service_variability_design(design_path=path)

        self.assertEqual(report["status"], "FAIL")
        self.assertIn("model_version drifted", report["errors"])

    def test_design_declares_no_calibration_or_adaptive_extension(self) -> None:
        design = load_design()
        self.assertEqual(design["design_status"], "FROZEN_PRE_RUN")
        self.assertEqual(design["model_version"], MODEL_VERSION)
        self.assertNotEqual(design["model_version"], design["study_id"])
        self.assertEqual(
            design["analysis_role"],
            "EXPLORATORY_ASSUMPTION_SENSITIVITY_NOT_CALIBRATION",
        )
        self.assertFalse(design["execution"]["adaptive_extension_allowed"])
        self.assertFalse(
            design["calibration_boundary"]["service_distribution_observed"]
        )
        self.assertFalse(
            design["calibration_boundary"]["service_cv_observed"]
        )


if __name__ == "__main__":
    unittest.main()
