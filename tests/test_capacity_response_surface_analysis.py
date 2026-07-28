from __future__ import annotations

import csv
import json
import math
import tempfile
import unittest
from pathlib import Path

from src.analysis.analyse_capacity_response_surface import (
    ANALYSIS_METRICS,
    REFERENCE_CELL,
    _crn_report,
    _entity_draw_signature,
    build_ideal_case_comparator,
    build_response_surface_analysis,
    deterministic_two_stage_oracle,
    main,
)


class ResponseSurfaceFiniteDifferenceTests(unittest.TestCase):
    SECURITY = (3, 2, 1)
    IMMIGRATION = (3, 2, 1)
    REPLICATIONS = (1, 2, 3, 4)

    @classmethod
    def rows(cls) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        for security in cls.SECURITY:
            for immigration in cls.IMMIGRATION:
                security_reduction = 3 - security
                immigration_reduction = 3 - immigration
                for replication in cls.REPLICATIONS:
                    response = (
                        10
                        + security_reduction**2
                        + 2 * immigration_reduction**2
                        + 3
                        * security_reduction
                        * immigration_reduction
                        + replication / 10
                    )
                    rows.append(
                        {
                            "security_capacity": security,
                            "immigration_capacity": immigration,
                            "replication_id": replication,
                            "total_queue_wait_p95_seconds": response,
                            "total_queue_wait_mean_seconds": response / 2,
                            "peak_total_waiting_queue": response + 1,
                            "time_weighted_mean_total_waiting_queue": (
                                response / 3
                            ),
                            "cutoff_backlog": response + 2,
                            "cohort_clear_time_after_cutoff_seconds": (
                                response + 3
                            ),
                            "security_wait_p95_seconds": (
                                5
                                + security_reduction**2
                                + replication / 10
                            ),
                            "immigration_wait_p95_seconds": (
                                4
                                + 2 * immigration_reduction**2
                                + replication / 10
                            ),
                        }
                    )
        return rows

    @classmethod
    def analysis(cls) -> dict[str, list[dict[str, object]]]:
        return build_response_surface_analysis(
            cls.rows(),
            security_capacities=cls.SECURITY,
            immigration_capacities=cls.IMMIGRATION,
            replication_ids=cls.REPLICATIONS,
            balanced_joint_path=((3, 3), (2, 2), (1, 1)),
            study_id="SYNTHETIC_SURFACE",
            security_offered_workload=1.5,
            immigration_offered_workload=1.0,
        )

    def test_builds_complete_cell_and_view_outputs(self) -> None:
        analysis = self.analysis()
        self.assertEqual(
            len(analysis["estimates"]),
            9 * len(ANALYSIS_METRICS),
        )
        self.assertEqual(
            len(analysis["adjacent_penalties"]),
            12 * len(ANALYSIS_METRICS),
        )
        self.assertEqual(
            len(analysis["second_differences"]),
            6 * len(ANALYSIS_METRICS),
        )
        self.assertEqual(
            len(analysis["interactions"]),
            4 * len(ANALYSIS_METRICS),
        )
        self.assertEqual(len(analysis["security_slice"]), 3)
        self.assertEqual(len(analysis["immigration_slice"]), 3)
        self.assertEqual(len(analysis["balanced_slice"]), 3)
        self.assertEqual(len(analysis["heatmap"]), 9)
        self.assertEqual(len(analysis["bottleneck_map"]), 9)

    def test_adjacent_penalties_reveal_acceleration(self) -> None:
        rows = [
            row
            for row in self.analysis()["adjacent_penalties"]
            if row["axis"] == "SECURITY"
            and row["fixed_immigration_capacity"] == 3
            and row["metric"] == "total_queue_wait_p95_seconds"
        ]
        by_step = {
            (row["higher_capacity"], row["lower_capacity"]): row
            for row in rows
        }
        self.assertAlmostEqual(
            float(by_step[(3, 2)]["mean_penalty"]), 1.0
        )
        self.assertAlmostEqual(
            float(by_step[(2, 1)]["mean_penalty"]), 3.0
        )
        self.assertEqual(
            by_step[(2, 1)]["crn_alignment_status"], "PASS"
        )

    def test_second_difference_and_local_interaction_are_paired(self) -> None:
        analysis = self.analysis()
        curvature = next(
            row
            for row in analysis["second_differences"]
            if row["axis"] == "SECURITY"
            and row["fixed_immigration_capacity"] == 3
            and row["metric"] == "total_queue_wait_p95_seconds"
        )
        self.assertAlmostEqual(
            float(curvature["mean_second_difference"]), 2.0
        )
        self.assertAlmostEqual(float(curvature["standard_error"]), 0.0)

        interaction = next(
            row
            for row in analysis["interactions"]
            if row["security_higher_capacity"] == 3
            and row["security_lower_capacity"] == 2
            and row["immigration_higher_capacity"] == 3
            and row["immigration_lower_capacity"] == 2
            and row["metric"] == "total_queue_wait_p95_seconds"
        )
        self.assertAlmostEqual(float(interaction["mean_interaction"]), 3.0)
        self.assertAlmostEqual(float(interaction["standard_error"]), 0.0)

    def test_duplicate_replication_is_rejected(self) -> None:
        rows = self.rows()
        rows.append(dict(rows[0]))
        with self.assertRaisesRegex(ValueError, "duplicate"):
            build_response_surface_analysis(
                rows,
                security_capacities=self.SECURITY,
                immigration_capacities=self.IMMIGRATION,
                replication_ids=self.REPLICATIONS,
                balanced_joint_path=((3, 3),),
                study_id="SYNTHETIC_SURFACE",
            )


class DeterministicIdealComparatorTests(unittest.TestCase):
    def test_underloaded_regular_system_has_zero_queue_wait(self) -> None:
        result = deterministic_two_stage_oracle(
            arrival_rate_per_second=1.0,
            arrival_cutoff_seconds=10.0,
            security_capacity=2,
            immigration_capacity=2,
            security_service_seconds=0.5,
            immigration_service_seconds=0.5,
        )
        self.assertEqual(result["deterministic_arrivals"], 9)
        self.assertEqual(result["total_queue_wait_mean_seconds"], 0.0)
        self.assertEqual(result["total_queue_wait_p95_seconds"], 0.0)
        self.assertEqual(result["peak_total_waiting_queue"], 0)

    def test_overloaded_regular_stage_has_computed_nonlinear_delay(self) -> None:
        result = deterministic_two_stage_oracle(
            arrival_rate_per_second=1.0,
            arrival_cutoff_seconds=10.0,
            security_capacity=1,
            immigration_capacity=10,
            security_service_seconds=2.0,
            immigration_service_seconds=0.1,
        )
        self.assertAlmostEqual(
            float(result["security_wait_mean_seconds"]), 4.0
        )
        self.assertAlmostEqual(
            float(result["security_wait_p95_seconds"]), 8.0
        )
        self.assertGreater(
            int(result["peak_total_waiting_queue"]), 0
        )

    def test_overlay_separates_linear_capacity_from_delay(self) -> None:
        analysis = ResponseSurfaceFiniteDifferenceTests.analysis()
        rows = build_ideal_case_comparator(
            analysis["estimates"],
            security_capacities=(3, 2, 1),
            immigration_capacities=(3, 2, 1),
            study_id="SYNTHETIC_SURFACE",
            arrival_rate_per_second=1.0,
            arrival_cutoff_seconds=10.0,
            security_service_seconds=2.0,
            immigration_service_seconds=1.0,
        )
        self.assertEqual(len(rows), 9)
        high = next(
            row
            for row in rows
            if row["security_capacity"] == 3
            and row["immigration_capacity"] == 3
        )
        low = next(
            row
            for row in rows
            if row["security_capacity"] == 1
            and row["immigration_capacity"] == 3
        )
        self.assertAlmostEqual(
            float(high["security_throughput_capacity_per_second"]), 1.5
        )
        self.assertAlmostEqual(
            float(low["security_throughput_capacity_per_second"]), 0.5
        )
        self.assertAlmostEqual(float(high["security_rho"]), 2 / 3)
        self.assertAlmostEqual(float(low["security_rho"]), 2.0)
        self.assertEqual(
            high["interpretation_role"],
            "IDEAL_CONTROL_OVERLAY_NOT_CALIBRATED_FORECAST",
        )
        expected_penalty = (
            float(high["anylogic_total_queue_wait_p95_estimate_seconds"])
            - float(high["ideal_total_queue_wait_p95_seconds"])
        )
        self.assertAlmostEqual(
            float(high["variability_congestion_penalty_p95_wait_seconds"]),
            expected_penalty,
        )


class StreamingAlignmentTests(unittest.TestCase):
    @staticmethod
    def entity(traveller_id: str, arrival: str) -> dict[str, str]:
        return {
            "traveller_id": traveller_id,
            "arrival_seconds": arrival,
            "security_service_demand_seconds": "2",
            "immigration_conventional_service_demand_seconds": "1",
            "automation_u": "0.1",
            "additional_check_u": "0.2",
            "lane_tie_u": "0.3",
        }

    def test_draw_digest_is_order_independent(self) -> None:
        first = [
            self.entity("T1", "1.0"),
            self.entity("T2", "2.0"),
        ]
        second = list(reversed(first))
        self.assertEqual(
            _entity_draw_signature(first, label="first"),
            _entity_draw_signature(second, label="second"),
        )

    def test_crn_report_detects_one_cell_mismatch(self) -> None:
        cells = (REFERENCE_CELL, (35, 21))
        signatures = {
            (REFERENCE_CELL, 1): (2, "a" * 64),
            ((35, 21), 1): (2, "b" * 64),
        }
        report = _crn_report(
            signatures,
            cells=cells,
            replication_ids=(1,),
            study_id="SYNTHETIC",
        )
        self.assertEqual(report["status"], "FAIL")
        self.assertFalse(report["branch_invariant_draws_pass"])
        self.assertTrue(report["errors"])


class ResponseSurfaceCliFailureTests(unittest.TestCase):
    def test_missing_raw_results_fail_cleanly(self) -> None:
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


if __name__ == "__main__":
    unittest.main()
