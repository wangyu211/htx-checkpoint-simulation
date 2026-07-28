from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.analysis.analyse_peak_duration_sensitivity import (
    ANALYSIS_METRICS,
    CAPACITY_CELLS,
    CUTOFF_SECONDS,
    EXPECTED_TARGET_INPUT_SAMPLE_ID,
    GROWTH_WINDOW_FIELDS,
    INCREMENT_METRICS,
    REFERENCE_CAPACITY,
    _expected_run_directories,
    _signature_for_rows,
    _validate_exact_coverage,
    _validate_run_records,
    build_crn_alignment_report,
    build_peak_duration_analysis,
    derive_duration_metrics,
    main,
)
from src.analysis.peak_duration_sensitivity_design import (
    build_peak_duration_scenario_rows,
    build_peak_duration_seed_rows,
)
from src.analysis.validate_operational_contract import scenario_config_sha256


class PeakDurationLedgerMetricTests(unittest.TestCase):
    @staticmethod
    def rows() -> list[dict[str, object]]:
        return [
            {
                "traveller_id": "T1",
                "arrival_seconds": 10,
                "security_queue_join_seconds": 10,
                "security_start_seconds": 20,
                "immigration_queue_join_seconds": 30,
                "immigration_start_seconds": 35,
                "exit_seconds": 50,
            },
            {
                "traveller_id": "T2",
                "arrival_seconds": 55,
                "security_queue_join_seconds": 55,
                "security_start_seconds": 75,
                "immigration_queue_join_seconds": 80,
                "immigration_start_seconds": 95,
                "exit_seconds": 110,
            },
            {
                "traveller_id": "T3",
                "arrival_seconds": 85,
                "security_queue_join_seconds": 85,
                "security_start_seconds": 105,
                "immigration_queue_join_seconds": 110,
                "immigration_start_seconds": 120,
                "exit_seconds": 140,
            },
        ]

    def test_reconstructs_arrival_window_cutoff_late_wait_and_growth(
        self,
    ) -> None:
        result = derive_duration_metrics(self.rows(), cutoff_seconds=100)

        self.assertAlmostEqual(
            float(
                result[
                    "arrival_window_time_weighted_mean_total_waiting_queue"
                ]
            ),
            0.65,
        )
        self.assertEqual(
            result["arrival_window_peak_total_waiting_queue"],
            2,
        )
        self.assertEqual(result["security_waiting_at_cutoff"], 1)
        self.assertEqual(result["immigration_waiting_at_cutoff"], 0)
        self.assertEqual(result["total_waiting_at_cutoff"], 1)
        self.assertEqual(result["cutoff_backlog"], 2)
        self.assertEqual(result["late_arrival_count"], 1)
        self.assertEqual(
            result["late_arrival_total_queue_wait_p95_seconds"],
            30,
        )
        self.assertEqual(
            result["cohort_clear_time_after_cutoff_seconds"],
            40,
        )
        self.assertEqual(
            [float(result[field]) for field in GROWTH_WINDOW_FIELDS],
            [0.5, 1.0, 0.5, 1.5, 1.5],
        )
        self.assertAlmostEqual(
            float(
                result[
                    "arrival_window_queue_growth_slope_travellers_per_second"
                ]
            ),
            0.025,
        )

    def test_rejects_arrival_outside_half_open_window(self) -> None:
        rows = self.rows()
        rows[-1]["arrival_seconds"] = 100
        with self.assertRaisesRegex(ValueError, r"outside \[0, cutoff\)"):
            derive_duration_metrics(rows, cutoff_seconds=100)


class PeakDurationRunValidationTests(unittest.TestCase):
    @staticmethod
    def fixture() -> tuple[
        dict[str, str],
        dict[str, str],
        list[dict[str, str]],
        dict[str, str],
        dict[str, str],
    ]:
        scenario = next(
            row
            for row in build_peak_duration_scenario_rows()
            if row["security_capacity"] == "36"
            and row["immigration_capacity"] == "21"
            and row["arrival_cutoff_seconds"] == "300"
        )
        seed = build_peak_duration_seed_rows()[0]
        config_hash = scenario_config_sha256(scenario)
        lineage = {
            "schema_version": "1.0",
            "config_id": scenario["config_id"],
            "config_sha256": config_hash,
            "model_version": "SYNTHETIC_MODEL_V1",
            "scenario_id": scenario["scenario_id"],
            "input_sample_id": EXPECTED_TARGET_INPUT_SAMPLE_ID,
            "replication_id": "1",
        }
        manifest = {
            **lineage,
            "scenario_family": scenario["scenario_family"],
            "reference_scenario_id": scenario["reference_scenario_id"],
            "master_seed": seed["master_seed"],
            "arrival_seed": seed["arrival_seed"],
            "service_seed": seed["service_seed"],
            "routing_seed": seed["routing_seed"],
            "tie_seed": seed["tie_seed"],
            "start_state": "EMPTY_AND_IDLE",
            "arrival_mode": scenario["arrival_mode"],
            "arrival_cutoff_seconds": "300",
            "drain_end_seconds": "365",
            "drain_rule": scenario["drain_rule"],
            "engine_name": "AnyLogic",
            "engine_version": "synthetic",
            "calibration_status": scenario["calibration_status"],
            "claim_ceiling": scenario["claim_ceiling"],
            "crn_alignment_status": scenario["crn_alignment_status"],
            "run_status": "COMPLETE",
        }

        base_entities = [
            {
                "traveller_id": "T1",
                "arrival_seconds": "30",
                "security_queue_join_seconds": "30",
                "security_start_seconds": "60",
                "security_end_seconds": "70",
                "immigration_queue_join_seconds": "70",
                "immigration_start_seconds": "80",
                "immigration_primary_end_seconds": "85",
                "exit_seconds": "85",
            },
            {
                "traveller_id": "T2",
                "arrival_seconds": "165",
                "security_queue_join_seconds": "165",
                "security_start_seconds": "225",
                "security_end_seconds": "235",
                "immigration_queue_join_seconds": "240",
                "immigration_start_seconds": "285",
                "immigration_primary_end_seconds": "290",
                "exit_seconds": "290",
            },
            {
                "traveller_id": "T3",
                "arrival_seconds": "255",
                "security_queue_join_seconds": "255",
                "security_start_seconds": "315",
                "security_end_seconds": "325",
                "immigration_queue_join_seconds": "330",
                "immigration_start_seconds": "360",
                "immigration_primary_end_seconds": "365",
                "exit_seconds": "365",
            },
        ]
        entities: list[dict[str, str]] = []
        for index, base in enumerate(base_entities, start=1):
            entities.append(
                {
                    **lineage,
                    **base,
                    "security_service_demand_seconds": "10",
                    "immigration_conventional_service_demand_seconds": "5",
                    "automation_u": f"0.{index}",
                    "additional_check_u": f"0.{index + 1}",
                    "lane_tie_u": f"0.{index + 2}",
                    "immigration_lane_id": "pooled",
                    "technology_flag": "false",
                    "immigration_primary_service_demand_seconds": "5",
                    "additional_check_flag": "false",
                    "additional_check_service_demand_seconds": "",
                    "additional_check_end_seconds": "",
                    "security_resource_id": "S1",
                    "immigration_resource_id": "I1",
                }
            )

        derived = derive_duration_metrics(entities, cutoff_seconds=300)
        kpi = {
            **lineage,
            "arrival_cutoff_seconds": "300",
            "drain_end_seconds": "365",
            "arrivals": "3",
            "completed_at_cutoff": "2",
            "security_queue_at_cutoff": "1",
            "security_in_service_at_cutoff": "0",
            "immigration_queue_at_cutoff": "0",
            "immigration_in_service_at_cutoff": "0",
            "wip_at_cutoff": "1",
            "completed_after_drain": "3",
            "rejected_or_dropped_count": "0",
            "technology_count": "0",
            "additional_check_count": "0",
            "security_wait_mean_seconds": str(
                derived["security_wait_mean_seconds"]
            ),
            "security_wait_p95_seconds": str(
                derived["security_wait_p95_seconds"]
            ),
            "immigration_wait_mean_seconds": str(
                derived["immigration_wait_mean_seconds"]
            ),
            "immigration_wait_p95_seconds": str(
                derived["immigration_wait_p95_seconds"]
            ),
            "total_queue_wait_mean_seconds": str(
                derived["total_queue_wait_mean_seconds"]
            ),
            "total_queue_wait_p95_seconds": str(
                derived["total_queue_wait_p95_seconds"]
            ),
            "total_queue_wait_exceed_600_rate": "0",
            "total_queue_wait_exceed_900_rate": "0",
            "total_queue_wait_exceed_1200_rate": "0",
            "system_time_mean_seconds": "0",
            "system_time_p95_seconds": "0",
            "security_utilization": "0",
            "immigration_utilization": "0",
            "cutoff_backlog": "1",
            "cutoff_backlog_fraction": str(1 / 3),
            "cohort_clear_time_after_cutoff_seconds": "65",
            "conservation_pass": "true",
            "run_status": "COMPLETE",
        }
        return manifest, kpi, entities, scenario, seed

    def test_validates_config_seed_full_drain_and_zero_guard_drop(self) -> None:
        manifest, kpi, entities, scenario, seed = self.fixture()
        row, prefixes = _validate_run_records(
            manifest,
            kpi,
            entities,
            run_label="synthetic",
            capacity=(36, 21),
            cutoff_seconds=300,
            replication_id=1,
            scenario_row=scenario,
            seed_row=seed,
            study_id="SYNTHETIC",
            arrival_rate_per_second=1.0,
            security_service_seconds=10.0,
            immigration_service_seconds=5.0,
        )

        self.assertEqual(row["completed_after_drain"], "3")
        self.assertEqual(row["security_waiting_at_cutoff"], 1)
        self.assertIn(300, prefixes)

    def test_rejects_config_hash_seed_drop_and_incomplete_drain(self) -> None:
        for field, value, pattern in (
            ("config_sha256", "0" * 64, "config_sha256"),
            ("arrival_seed", "1", "arrival_seed"),
        ):
            manifest, kpi, entities, scenario, seed = self.fixture()
            manifest[field] = value
            with self.assertRaisesRegex(ValueError, pattern):
                _validate_run_records(
                    manifest,
                    kpi,
                    entities,
                    run_label="synthetic",
                    capacity=(36, 21),
                    cutoff_seconds=300,
                    replication_id=1,
                    scenario_row=scenario,
                    seed_row=seed,
                    study_id="SYNTHETIC",
                    arrival_rate_per_second=1.0,
                    security_service_seconds=10.0,
                    immigration_service_seconds=5.0,
                )

        for field, value, pattern in (
            ("rejected_or_dropped_count", "1", "dropped"),
            ("completed_after_drain", "2", "full-drain"),
        ):
            manifest, kpi, entities, scenario, seed = self.fixture()
            kpi[field] = value
            with self.assertRaisesRegex(ValueError, pattern):
                _validate_run_records(
                    manifest,
                    kpi,
                    entities,
                    run_label="synthetic",
                    capacity=(36, 21),
                    cutoff_seconds=300,
                    replication_id=1,
                    scenario_row=scenario,
                    seed_row=seed,
                    study_id="SYNTHETIC",
                    arrival_rate_per_second=1.0,
                    security_service_seconds=10.0,
                    immigration_service_seconds=5.0,
                )


class PeakDurationCrnTests(unittest.TestCase):
    @staticmethod
    def entity(
        traveller_id: str,
        arrival_seconds: float,
    ) -> dict[str, str]:
        return {
            "traveller_id": traveller_id,
            "arrival_seconds": str(arrival_seconds),
            "security_service_demand_seconds": "2",
            "immigration_conventional_service_demand_seconds": "1",
            "automation_u": "0.1",
            "additional_check_u": "0.2",
            "lane_tie_u": "0.3",
        }

    def signatures(self) -> dict[
        tuple[tuple[int, int], int, int, int],
        tuple[int, str],
    ]:
        short = [self.entity("T1", 1.0)]
        long = [*short, self.entity("T2", 15.0)]
        short_signature = _signature_for_rows(short, label="short")
        long_signature = _signature_for_rows(long, label="long")
        signatures = {}
        for capacity in (REFERENCE_CAPACITY, (30, 18)):
            signatures[(capacity, 10, 1, 10)] = short_signature
            signatures[(capacity, 20, 1, 10)] = short_signature
            signatures[(capacity, 20, 1, 20)] = long_signature
        return signatures

    def test_exact_same_duration_and_nested_prefix_pass(self) -> None:
        report = build_crn_alignment_report(
            self.signatures(),
            capacities=(REFERENCE_CAPACITY, (30, 18)),
            cutoffs=(10, 20),
            replication_ids=(1,),
            study_id="SYNTHETIC",
        )

        self.assertEqual(report["status"], "PASS", report["errors"])
        self.assertTrue(
            report["same_duration_cross_capacity_exogenous_crn_pass"]
        )
        self.assertTrue(
            report["cross_duration_nested_arrival_prefix_pass"]
        )

    def test_nested_prefix_drift_fails(self) -> None:
        signatures = self.signatures()
        signatures[((30, 18), 20, 1, 10)] = (
            1,
            "0" * 64,
        )
        report = build_crn_alignment_report(
            signatures,
            capacities=(REFERENCE_CAPACITY, (30, 18)),
            cutoffs=(10, 20),
            replication_ids=(1,),
            study_id="SYNTHETIC",
        )

        self.assertEqual(report["status"], "FAIL")
        self.assertFalse(
            report["cross_duration_nested_arrival_prefix_pass"]
        )


class PeakDurationAnalysisTests(unittest.TestCase):
    CAPACITIES = (REFERENCE_CAPACITY, (29, 17))
    CUTOFFS = (10, 20)
    REPLICATIONS = (1, 2, 3)

    @classmethod
    def rows(cls) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        for capacity_index, capacity in enumerate(cls.CAPACITIES):
            for cutoff in cls.CUTOFFS:
                for replication in cls.REPLICATIONS:
                    base = (
                        capacity_index * 10
                        + cutoff / 10
                        + replication
                    )
                    row: dict[str, object] = {
                        "security_capacity": capacity[0],
                        "immigration_capacity": capacity[1],
                        "arrival_cutoff_seconds": cutoff,
                        "replication_id": replication,
                    }
                    for metric_index, metric in enumerate(ANALYSIS_METRICS):
                        row[metric] = base + metric_index / 100
                    row["queue_mean_window_50_60"] = base
                    row["queue_mean_window_90_100"] = base + 4
                    rows.append(row)
        return rows

    def test_builds_replication_t_intervals_increments_and_curves(self) -> None:
        analysis = build_peak_duration_analysis(
            self.rows(),
            capacities=self.CAPACITIES,
            cutoffs=self.CUTOFFS,
            replication_ids=self.REPLICATIONS,
            study_id="SYNTHETIC",
            arrival_rate_per_second=1.3642132969720073,
            security_service_seconds=21.818181818,
            immigration_service_seconds=13.0,
        )

        self.assertEqual(
            len(analysis["estimates"]),
            len(self.CAPACITIES) * len(self.CUTOFFS) * len(ANALYSIS_METRICS),
        )
        self.assertEqual(
            len(analysis["duration_increments"]),
            len(self.CAPACITIES) * len(INCREMENT_METRICS),
        )
        self.assertEqual(
            len(analysis["growth_diagnostics"]),
            len(self.CAPACITIES) * len(self.CUTOFFS),
        )
        increment = next(
            row
            for row in analysis["duration_increments"]
            if row["security_capacity"] == 36
            and row["metric"] == "total_queue_wait_p95_seconds"
        )
        self.assertAlmostEqual(float(increment["mean_increment"]), 1.0)
        overloaded = next(
            row
            for row in analysis["growth_diagnostics"]
            if row["security_capacity"] == 29
        )
        self.assertEqual(
            overloaded["rho_regime"],
            "RHO_GTE_ONE_FINITE_HORIZON_ONLY",
        )
        self.assertEqual(
            overloaded["steady_state_claim_status"],
            "PROHIBITED_RHO_GTE_ONE",
        )
        self.assertEqual(
            len(analysis["curves_payload"]["series"]),
            len(self.CAPACITIES),
        )

    def test_duplicate_replication_fails_closed(self) -> None:
        rows = self.rows()
        rows.append(dict(rows[0]))
        with self.assertRaisesRegex(ValueError, "duplicate"):
            build_peak_duration_analysis(
                rows,
                capacities=self.CAPACITIES,
                cutoffs=self.CUTOFFS,
                replication_ids=self.REPLICATIONS,
                study_id="SYNTHETIC",
                arrival_rate_per_second=1.0,
                security_service_seconds=1.0,
                immigration_service_seconds=1.0,
            )


class PeakDurationCoverageAndCliTests(unittest.TestCase):
    def test_exact_coverage_rejects_unexpected_run(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            expected = _expected_run_directories(
                root,
                capacities=(CAPACITY_CELLS[0],),
                cutoffs=(CUTOFF_SECONDS[0],),
                replication_ids=(1, 2),
            )
            for run_dir in expected:
                run_dir.mkdir(parents=True)
                (run_dir / "run_manifest.csv").write_text(
                    "header\n",
                    encoding="utf-8",
                )
            _validate_exact_coverage(root, expected)

            unexpected = root / "unexpected" / "run_manifest.csv"
            unexpected.parent.mkdir(parents=True)
            unexpected.write_text("header\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "unexpected"):
                _validate_exact_coverage(root, expected)

    def test_missing_raw_results_fail_without_estimate_release(self) -> None:
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
            self.assertEqual(validation["expected_run_count"], 1000)
            self.assertFalse((output / "cell_estimates.csv").exists())


if __name__ == "__main__":
    unittest.main()
