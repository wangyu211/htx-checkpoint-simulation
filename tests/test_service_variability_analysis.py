from __future__ import annotations

import json
import math
import tempfile
import unittest
from pathlib import Path

from src.analysis.analyse_service_variability import (
    ANALYSIS_METRICS,
    INVARIANT_DRAW_FIELDS,
    REFERENCE_CELL,
    _cross_batch_event_signature,
    _expected_run_paths,
    _service_latents,
    _validate_exact_coverage,
    build_crn_alignment_report,
    build_service_variability_analysis,
    implied_standard_normal,
    main,
)
from src.analysis.analyse_capacity_response_surface import (
    _validate_entity_chronology,
    _write_json,
)


class ServiceVariabilitySyntheticAnalysisTests(unittest.TestCase):
    CELLS = tuple(
        (security_cv, immigration_cv)
        for security_cv in (0.0, 0.5, 1.0)
        for immigration_cv in (0.0, 0.5, 1.0)
    )
    REPLICATIONS = (1, 2, 3, 4)

    @classmethod
    def rows(cls) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        for security_cv, immigration_cv in cls.CELLS:
            for replication in cls.REPLICATIONS:
                response = (
                    10.0
                    + replication / 10.0
                    + 10.0 * security_cv
                    + 20.0 * immigration_cv
                    + 30.0 * security_cv * immigration_cv
                )
                row: dict[str, object] = {
                    "security_service_cv": security_cv,
                    "immigration_service_cv": immigration_cv,
                    "replication_id": replication,
                }
                row.update(
                    {
                        metric: response + index / 100.0
                        for index, metric in enumerate(ANALYSIS_METRICS)
                    }
                )
                rows.append(row)
        return rows

    def test_builds_complete_estimates_contrasts_interactions_and_views(
        self,
    ) -> None:
        analysis = build_service_variability_analysis(
            self.rows(),
            cells=self.CELLS,
            replication_ids=self.REPLICATIONS,
            crn_alignment_status="PASS",
            study_id="SYNTHETIC_SERVICE_VARIABILITY",
        )

        self.assertEqual(
            len(analysis["estimates"]), 9 * len(ANALYSIS_METRICS)
        )
        self.assertEqual(
            len(analysis["contrasts"]), 8 * len(ANALYSIS_METRICS)
        )
        self.assertEqual(
            len(analysis["interactions"]), 4 * len(ANALYSIS_METRICS)
        )
        self.assertEqual(len(analysis["heatmap"]), 9)
        self.assertEqual(len(analysis["security_slice"]), 3)
        self.assertEqual(len(analysis["immigration_slice"]), 3)
        self.assertEqual(len(analysis["balanced_slice"]), 3)
        self.assertEqual(
            analysis["view_payload"]["crn_alignment_status"], "PASS"
        )

    def test_joint_contrast_and_factorial_interaction_are_paired(self) -> None:
        analysis = build_service_variability_analysis(
            self.rows(),
            cells=self.CELLS,
            replication_ids=self.REPLICATIONS,
            crn_alignment_status="PASS",
        )
        contrast = next(
            row
            for row in analysis["contrasts"]
            if row["security_service_cv"] == 1.0
            and row["immigration_service_cv"] == 1.0
            and row["metric"] == "total_queue_wait_p95_seconds"
        )
        self.assertAlmostEqual(float(contrast["difference_mean"]), 60.0)
        self.assertAlmostEqual(float(contrast["standard_error"]), 0.0)
        self.assertEqual(contrast["comparison_method"], "PAIRED_STUDENT_T")

        interaction = next(
            row
            for row in analysis["interactions"]
            if row["security_service_cv"] == 0.5
            and row["immigration_service_cv"] == 0.5
            and row["metric"] == "total_queue_wait_p95_seconds"
        )
        self.assertAlmostEqual(float(interaction["interaction_mean"]), 7.5)
        self.assertAlmostEqual(float(interaction["standard_error"]), 0.0)
        self.assertEqual(interaction["crn_alignment_status"], "PASS")

    def test_paired_outputs_fail_closed_without_crn_pass(self) -> None:
        with self.assertRaisesRegex(ValueError, "CRN status PASS"):
            build_service_variability_analysis(
                self.rows(),
                cells=self.CELLS,
                replication_ids=self.REPLICATIONS,
                crn_alignment_status="FAIL",
            )

    def test_duplicate_or_missing_replication_is_rejected(self) -> None:
        rows = self.rows()
        rows.append(dict(rows[0]))
        with self.assertRaisesRegex(ValueError, "duplicate"):
            build_service_variability_analysis(
                rows,
                cells=self.CELLS,
                replication_ids=self.REPLICATIONS,
                crn_alignment_status="PASS",
            )

        with self.assertRaisesRegex(ValueError, "exact registered coverage"):
            build_service_variability_analysis(
                self.rows()[1:],
                cells=self.CELLS,
                replication_ids=self.REPLICATIONS,
                crn_alignment_status="PASS",
            )


class ServiceLatentContractTests(unittest.TestCase):
    SECURITY_MEAN = 20.0
    IMMIGRATION_MEAN = 10.0

    @staticmethod
    def demand(mean: float, cv: float, latent: float) -> float:
        sigma2 = math.log1p(cv * cv)
        return mean * math.exp(
            -0.5 * sigma2 + math.sqrt(sigma2) * latent
        )

    def test_inverse_transform_recovers_latent(self) -> None:
        demand = self.demand(self.SECURITY_MEAN, 0.5, 0.75)
        self.assertAlmostEqual(
            implied_standard_normal(
                demand,
                mean_seconds=self.SECURITY_MEAN,
                cv=0.5,
            ),
            0.75,
        )

    def test_fixed_and_positive_demands_validate(self) -> None:
        security_demand = self.demand(self.SECURITY_MEAN, 0.5, -0.25)
        rows = [
            {
                "traveller_id": "T1",
                "security_service_demand_seconds": str(security_demand),
                "immigration_conventional_service_demand_seconds": "10",
                "immigration_primary_service_demand_seconds": "10",
            }
        ]
        latent = _service_latents(
            rows,
            cell=(0.5, 0.0),
            security_mean_seconds=self.SECURITY_MEAN,
            immigration_mean_seconds=self.IMMIGRATION_MEAN,
            numeric_tolerance=1e-9,
            label="synthetic",
        )
        self.assertAlmostEqual(latent["security"]["T1"], -0.25)
        self.assertEqual(latent["immigration"], {})

    def test_cv_zero_demand_drift_is_rejected(self) -> None:
        rows = [
            {
                "traveller_id": "T1",
                "security_service_demand_seconds": "19",
                "immigration_conventional_service_demand_seconds": "10",
                "immigration_primary_service_demand_seconds": "10",
            }
        ]
        with self.assertRaisesRegex(ValueError, "CV-zero Security"):
            _service_latents(
                rows,
                cell=(0.0, 0.0),
                security_mean_seconds=self.SECURITY_MEAN,
                immigration_mean_seconds=self.IMMIGRATION_MEAN,
                numeric_tolerance=1e-9,
                label="synthetic",
            )

    def test_nonpositive_variable_demand_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "strictly positive"):
            implied_standard_normal(
                0,
                mean_seconds=self.SECURITY_MEAN,
                cv=1.0,
            )

    def test_chronology_tolerance_accounts_for_nine_decimal_csv_rounding(
        self,
    ) -> None:
        row = {
            "arrival_seconds": "0.000000000",
            "security_queue_join_seconds": "0.000000000",
            "security_start_seconds": "0.000000000",
            "security_end_seconds": "1.000000000",
            "immigration_queue_join_seconds": "1.000000000",
            "immigration_start_seconds": "172.235724382",
            "immigration_primary_end_seconds": "172.932797406",
            "exit_seconds": "172.932797406",
            "security_service_demand_seconds": "1.000000000",
            "immigration_primary_service_demand_seconds": "0.697073025",
            "automation_u": "0.5",
            "additional_check_u": "0.5",
            "lane_tie_u": "0.5",
            "technology_flag": "false",
            "additional_check_flag": "false",
            "additional_check_service_demand_seconds": "",
            "additional_check_end_seconds": "",
        }

        _validate_entity_chronology(
            row,
            cutoff_seconds=300.0,
            drain_end_seconds=200.0,
            label="nine-decimal-rounding",
            duration_tolerance=2e-9,
        )

        materially_inconsistent = dict(row)
        materially_inconsistent["immigration_primary_end_seconds"] = (
            "172.932798406"
        )
        materially_inconsistent["exit_seconds"] = "172.932798406"
        with self.assertRaisesRegex(
            ValueError,
            "Immigration service duration is inconsistent",
        ):
            _validate_entity_chronology(
                materially_inconsistent,
                cutoff_seconds=300.0,
                drain_end_seconds=200.0,
                label="material-duration-error",
                duration_tolerance=2e-9,
            )

    def test_cross_batch_signature_excludes_lineage_but_not_events(self) -> None:
        row = {
            "traveller_id": "T1",
            "arrival_seconds": "1.000000000",
            "security_service_demand_seconds": "2.000000000",
            "immigration_conventional_service_demand_seconds": "3.000000000",
            "automation_u": "0.1",
            "additional_check_u": "0.2",
            "lane_tie_u": "0.3",
            "security_queue_join_seconds": "1.000000000",
            "security_start_seconds": "1.000000000",
            "security_end_seconds": "3.000000000",
            "immigration_queue_join_seconds": "3.000000000",
            "immigration_lane_id": "IMMIGRATION_POOLED",
            "immigration_start_seconds": "3.000000000",
            "technology_flag": "false",
            "immigration_primary_service_demand_seconds": "3.000000000",
            "immigration_primary_end_seconds": "6.000000000",
            "additional_check_flag": "false",
            "additional_check_service_demand_seconds": "",
            "additional_check_end_seconds": "",
            "exit_seconds": "6.000000000",
            "config_id": "CURRENT",
            "security_resource_id": "SECURITY_CURRENT",
        }
        prior = dict(row)
        prior["config_id"] = "PRIOR"
        prior["security_resource_id"] = "SECURITY_PRIOR"
        self.assertEqual(
            _cross_batch_event_signature([row], label="current"),
            _cross_batch_event_signature([prior], label="prior"),
        )

        prior["exit_seconds"] = "6.000000001"
        self.assertNotEqual(
            _cross_batch_event_signature([row], label="current"),
            _cross_batch_event_signature([prior], label="prior"),
        )

    def test_json_writer_uses_repository_canonical_lf_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "report.json"
            _write_json(path, {"status": "PASS", "rows": [1, 2]})
            payload = path.read_bytes()
        self.assertIn(b"\n", payload)
        self.assertNotIn(b"\r\n", payload)


class ServiceVariabilityCrnGateTests(unittest.TestCase):
    CELLS = tuple(
        (security_cv, immigration_cv)
        for security_cv in (0.0, 0.5, 1.0)
        for immigration_cv in (0.0, 0.5, 1.0)
    )
    REPLICATIONS = (1, 2)

    @classmethod
    def aligned_inputs(
        cls,
    ) -> tuple[
        dict[tuple[tuple[float, float], int], tuple[int, str]],
        dict[
            tuple[tuple[float, float], int],
            dict[str, dict[str, float]],
        ],
    ]:
        invariant: dict[
            tuple[tuple[float, float], int], tuple[int, str]
        ] = {}
        latents: dict[
            tuple[tuple[float, float], int],
            dict[str, dict[str, float]],
        ] = {}
        for replication in cls.REPLICATIONS:
            digest = f"{replication:064x}"
            for cell in cls.CELLS:
                invariant[(cell, replication)] = (2, digest)
                latents[(cell, replication)] = {
                    "security": (
                        {"T1": -0.2, "T2": 0.4}
                        if cell[0] > 0
                        else {}
                    ),
                    "immigration": (
                        {"T1": 0.3, "T2": -0.7}
                        if cell[1] > 0
                        else {}
                    ),
                }
        return invariant, latents

    def test_exact_invariants_and_stage_latents_pass(self) -> None:
        invariant, latents = self.aligned_inputs()
        report = build_crn_alignment_report(
            invariant,
            latents,
            cells=self.CELLS,
            replication_ids=self.REPLICATIONS,
            registered_seed_alignment_pass=True,
            service_demand_validation_pass=True,
        )

        self.assertEqual(report["status"], "PASS")
        self.assertTrue(report["arrival_routing_tie_exact_pass"])
        self.assertTrue(
            report["security_positive_cv_latent_alignment_pass"]
        )
        self.assertTrue(
            report["immigration_positive_cv_latent_alignment_pass"]
        )
        self.assertEqual(
            report["compared_invariant_draw_values"],
            2
            * (len(self.CELLS) - 1)
            * 2
            * len(INVARIANT_DRAW_FIELDS),
        )

    def test_one_latent_mismatch_fails(self) -> None:
        invariant, latents = self.aligned_inputs()
        latents[((1.0, 1.0), 2)]["security"]["T2"] = 0.401
        report = build_crn_alignment_report(
            invariant,
            latents,
            cells=self.CELLS,
            replication_ids=self.REPLICATIONS,
            registered_seed_alignment_pass=True,
            service_demand_validation_pass=True,
        )
        self.assertEqual(report["status"], "FAIL")
        self.assertTrue(
            any("latent z differs" in error for error in report["errors"])
        )

    def test_one_exact_invariant_mismatch_fails(self) -> None:
        invariant, latents = self.aligned_inputs()
        invariant[((0.5, 0.5), 1)] = (2, "f" * 64)
        report = build_crn_alignment_report(
            invariant,
            latents,
            cells=self.CELLS,
            replication_ids=self.REPLICATIONS,
            registered_seed_alignment_pass=True,
            service_demand_validation_pass=True,
        )
        self.assertEqual(report["status"], "FAIL")
        self.assertTrue(
            any(
                "arrival/routing/tie" in error for error in report["errors"]
            )
        )

    def test_upstream_seed_or_demand_validation_cannot_be_bypassed(
        self,
    ) -> None:
        invariant, latents = self.aligned_inputs()
        report = build_crn_alignment_report(
            invariant,
            latents,
            cells=self.CELLS,
            replication_ids=self.REPLICATIONS,
            registered_seed_alignment_pass=False,
            service_demand_validation_pass=True,
        )
        self.assertEqual(report["status"], "FAIL")
        self.assertFalse(report["seed_alignment_pass"])


class ServiceVariabilityCoverageTests(unittest.TestCase):
    CELLS = tuple(
        (security_cv, immigration_cv)
        for security_cv in (0.0, 0.5, 1.0)
        for immigration_cv in (0.0, 0.5, 1.0)
    )
    REPLICATIONS = tuple(range(1, 51))

    def test_exact_450_manifest_coverage_passes_and_missing_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            expected = _expected_run_paths(
                root, self.CELLS, self.REPLICATIONS
            )
            for run_dir in expected:
                run_dir.mkdir(parents=True, exist_ok=True)
                (run_dir / "run_manifest.csv").write_text(
                    "synthetic\n", encoding="utf-8"
                )

            _validate_exact_coverage(root, expected)
            missing = next(iter(expected)) / "run_manifest.csv"
            missing.unlink()
            with self.assertRaisesRegex(ValueError, "incomplete"):
                _validate_exact_coverage(root, expected)


class ServiceVariabilityCliFailureTests(unittest.TestCase):
    def test_missing_raw_results_fail_cleanly_without_analysis_claim(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "analysis"
            exit_code = main(
                [
                    "--results-root",
                    str(root / "missing"),
                    "--output-dir",
                    str(output),
                ]
            )
            self.assertEqual(exit_code, 1)
            validation = json.loads(
                (output / "validation.json").read_text(encoding="utf-8")
            )
            self.assertEqual(validation["status"], "FAIL")
            self.assertIn(
                "raw results do not exist", validation["errors"][0]
            )
            self.assertFalse((output / "analysis_manifest.json").exists())


if __name__ == "__main__":
    unittest.main()
