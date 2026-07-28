from __future__ import annotations

import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from src.analysis.analyse_capacity_availability import (
    build_availability_by_replication,
    build_capacity_availability_analysis,
    package_capacity_availability_analysis,
    reconstruct_queue_length_metrics,
    replication_contrast_with_crn_gate,
)
from src.analysis.validate_operational_results import (
    DEFAULT_SCHEMA_REGISTRY,
    RESULT_FILES,
    load_result_schemas,
)


def entity_row(
    security_join: float,
    security_start: float,
    immigration_join: float,
    immigration_start: float,
) -> dict[str, str]:
    return {
        "security_queue_join_seconds": str(security_join),
        "security_start_seconds": str(security_start),
        "immigration_queue_join_seconds": str(immigration_join),
        "immigration_start_seconds": str(immigration_start),
    }


ALIGNMENT_PASS = {
    "status": "PASS",
    "traveller_level_alignment_pass": True,
    "branch_invariant_draws_pass": True,
}


class QueueLengthReconstructionTests(unittest.TestCase):
    def test_overlapping_waits_produce_peaks_and_time_weighted_means(
        self,
    ) -> None:
        rows = [
            entity_row(0, 4, 5, 7),
            entity_row(1, 3, 4, 6),
        ]

        metrics = reconstruct_queue_length_metrics(
            rows, cutoff_seconds=8
        )

        self.assertEqual(metrics["max_security_queue"], 2)
        self.assertEqual(metrics["max_immigration_queue"], 2)
        self.assertEqual(metrics["max_total_queue"], 2)
        self.assertEqual(metrics["peak_total_waiting_queue"], 2)
        self.assertAlmostEqual(
            float(metrics["security_queue_person_seconds"]), 6.0
        )
        self.assertAlmostEqual(
            float(metrics["immigration_queue_person_seconds"]), 4.0
        )
        self.assertAlmostEqual(
            float(metrics["security_queue_time_weighted_mean"]), 0.75
        )
        self.assertAlmostEqual(
            float(metrics["immigration_queue_time_weighted_mean"]), 0.5
        )
        self.assertAlmostEqual(
            float(metrics["total_queue_time_weighted_mean"]), 1.25
        )
        self.assertAlmostEqual(
            float(metrics["time_weighted_mean_total_waiting_queue"]), 1.25
        )

    def test_equal_timestamp_applies_ending_before_starting(self) -> None:
        # The traveller transfers from security waiting to immigration waiting
        # at t=2.  Under [join,start), the total queue never reaches two.
        rows = [entity_row(0, 2, 2, 4)]

        metrics = reconstruct_queue_length_metrics(
            rows, cutoff_seconds=4
        )

        self.assertEqual(metrics["max_security_queue"], 1)
        self.assertEqual(metrics["max_immigration_queue"], 1)
        self.assertEqual(metrics["max_total_queue"], 1)
        self.assertAlmostEqual(
            float(metrics["total_queue_person_seconds"]), 4.0
        )

    def test_zero_waits_are_ignored(self) -> None:
        metrics = reconstruct_queue_length_metrics(
            [entity_row(1, 1, 2, 2)],
            cutoff_seconds=5,
        )

        self.assertEqual(metrics["security_positive_wait_count"], 0)
        self.assertEqual(metrics["immigration_positive_wait_count"], 0)
        self.assertEqual(metrics["max_total_queue"], 0)
        self.assertEqual(metrics["total_queue_person_seconds"], 0.0)
        self.assertEqual(metrics["total_queue_time_weighted_mean"], 0.0)

    def test_total_peak_is_not_sum_of_distinct_stage_peaks(self) -> None:
        rows = [
            entity_row(0, 2, 5, 5),
            entity_row(0, 2, 5, 5),
            entity_row(3, 3, 3, 5),
            entity_row(3, 3, 3, 5),
        ]

        metrics = reconstruct_queue_length_metrics(
            rows, cutoff_seconds=6
        )

        self.assertEqual(metrics["max_security_queue"], 2)
        self.assertEqual(metrics["max_immigration_queue"], 2)
        self.assertEqual(metrics["max_total_queue"], 2)

    def test_intervals_are_clipped_to_arrival_window(self) -> None:
        # Security started waiting before t=0; immigration remains waiting
        # beyond the arrival cutoff at t=5.
        metrics = reconstruct_queue_length_metrics(
            [entity_row(-2, 2, 4, 7)],
            cutoff_seconds=5,
        )

        self.assertEqual(metrics["total_queue_person_seconds"], 3.0)
        self.assertAlmostEqual(
            float(metrics["total_queue_time_weighted_mean"]), 0.6
        )

    def test_peak_uses_full_drain_while_mean_uses_arrival_window(self) -> None:
        rows = [
            entity_row(0, 0, 6, 9),
            entity_row(0, 0, 7, 9),
        ]

        metrics = reconstruct_queue_length_metrics(
            rows,
            cutoff_seconds=5,
        )

        self.assertEqual(metrics["peak_total_waiting_queue"], 2)
        self.assertEqual(metrics["peak_immigration_waiting_queue"], 2)
        self.assertEqual(metrics["peak_window_end_seconds"], 9.0)
        self.assertEqual(
            metrics["time_weighted_mean_total_waiting_queue"],
            0.0,
        )

    def test_negative_wait_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "before"):
            reconstruct_queue_length_metrics(
                [entity_row(2, 1, 3, 3)],
                cutoff_seconds=5,
            )


class CapacityContrastGateTests(unittest.TestCase):
    def test_verified_alignment_uses_paired_contrast(self) -> None:
        result = replication_contrast_with_crn_gate(
            {"1": 8.0, "2": 18.0, "3": 28.0},
            {"1": 10.0, "2": 20.0, "3": 30.0},
            alignment_report=ALIGNMENT_PASS,
        )

        self.assertEqual(result["comparison_method"], "PAIRED_STUDENT_T")
        self.assertEqual(result["alignment_status"], "PASS")
        self.assertEqual(result["difference_mean"], -2.0)
        self.assertEqual(result["ci_low"], -2.0)
        self.assertEqual(result["ci_high"], -2.0)

    def test_unverified_alignment_falls_back_to_welch(self) -> None:
        result = replication_contrast_with_crn_gate(
            {"1": 8.0, "2": 18.0, "3": 28.0},
            {"1": 10.0, "2": 20.0, "3": 30.0},
            alignment_report={"status": "PASS"},
        )

        self.assertEqual(result["comparison_method"], "INDEPENDENT_WELCH_T")
        self.assertEqual(result["alignment_status"], "NOT_VERIFIED")
        self.assertEqual(result["difference_mean"], -2.0)

    def test_mismatched_replication_ids_block_pairing(self) -> None:
        result = replication_contrast_with_crn_gate(
            {"1": 8.0, "2": 18.0, "4": 28.0},
            {"1": 10.0, "2": 20.0, "3": 30.0},
            alignment_report=ALIGNMENT_PASS,
        )

        self.assertEqual(result["comparison_method"], "INDEPENDENT_WELCH_T")
        self.assertEqual(
            result["alignment_status"], "REPLICATION_ID_MISMATCH"
        )


class CapacityAvailabilityBuilderTests(unittest.TestCase):
    SCENARIOS = ("REFERENCE", "JOINT_32_18")
    SAMPLES = ("BASE",)
    REPLICATIONS = (1, 2, 3)

    @staticmethod
    def _kpi_row(
        scenario: str, replication: int, *, peak_offset: float
    ) -> dict[str, object]:
        return {
            "scenario_id": scenario,
            "input_sample_id": "BASE",
            "replication_id": str(replication),
            "total_queue_wait_p95_seconds": str(10 + peak_offset),
            "cutoff_backlog": str(int(peak_offset)),
            "cohort_clear_time_after_cutoff_seconds": str(peak_offset),
            "security_utilization": "0.8",
            "immigration_utilization": "0.8",
        }

    @staticmethod
    def _entity(
        scenario: str,
        replication: int,
        traveller: str,
        security_join: float,
        security_start: float,
        immigration_join: float,
        immigration_start: float,
    ) -> dict[str, object]:
        return {
            "scenario_id": scenario,
            "input_sample_id": "BASE",
            "replication_id": str(replication),
            "traveller_id": traveller,
            **entity_row(
                security_join,
                security_start,
                immigration_join,
                immigration_start,
            ),
        }

    @staticmethod
    def _design() -> dict[str, object]:
        return {
            "study_id": "TEST_AVAILABILITY",
            "claim_ceiling": "TEST_ONLY",
            "arrival_rate_uncertainty": {
                "levels": [
                    {
                        "level_id": "MLE_BASE",
                        "input_sample_id": "BASE",
                    }
                ]
            },
            "primary_analysis": {
                "confidence_level": 0.95,
                "reference_scenario_id": "REFERENCE",
                "scenario_id": "JOINT_32_18",
                "input_level_id": "MLE_BASE",
                "metric": "peak_total_waiting_queue",
                "estimand": "scenario minus reference",
            },
        }

    def test_merges_reconstructed_queue_metrics_with_kpis(self) -> None:
        kpis = [self._kpi_row("REFERENCE", 1, peak_offset=0)]
        entities = [
            self._entity("REFERENCE", 1, "T1", 0, 4, 5, 7),
            self._entity("REFERENCE", 1, "T2", 1, 3, 4, 6),
        ]

        rows = build_availability_by_replication(
            kpis,
            entities,
            cutoff_seconds=8,
            expected_run_keys={("REFERENCE", "BASE", 1)},
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["total_queue_wait_p95_seconds"], "10")
        self.assertEqual(rows[0]["peak_security_waiting_queue"], 2)
        self.assertEqual(rows[0]["peak_immigration_waiting_queue"], 2)
        self.assertEqual(rows[0]["peak_total_waiting_queue"], 2)
        self.assertAlmostEqual(
            float(rows[0]["time_weighted_mean_total_waiting_queue"]),
            1.25,
        )

    def _analysis_rows(self) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        for scenario in self.SCENARIOS:
            for replication in self.REPLICATIONS:
                peak = (
                    float(replication)
                    if scenario == "REFERENCE"
                    else float(replication + 4)
                )
                row = self._kpi_row(
                    scenario, replication, peak_offset=peak
                )
                row.update(
                    {
                        "peak_security_waiting_queue": peak,
                        "peak_immigration_waiting_queue": peak,
                        "peak_total_waiting_queue": peak,
                        "time_weighted_mean_security_waiting_queue": peak / 2,
                        "time_weighted_mean_immigration_waiting_queue": peak / 2,
                        "time_weighted_mean_total_waiting_queue": peak,
                    }
                )
                rows.append(row)
        return rows

    def test_registered_primary_uses_paired_difference_after_gate(self) -> None:
        analysis = build_capacity_availability_analysis(
            self._analysis_rows(),
            self._design(),
            alignment_report=ALIGNMENT_PASS,
            alignment_verified=True,
            scenario_ids=self.SCENARIOS,
            input_sample_ids=self.SAMPLES,
            replication_ids=self.REPLICATIONS,
        )

        primary = analysis["primary"]
        self.assertEqual(primary["metric"], "peak_total_waiting_queue")
        self.assertEqual(primary["comparison_method"], "PAIRED_STUDENT_T")
        self.assertEqual(primary["difference_mean"], 4.0)
        self.assertEqual(primary["ci_low"], 4.0)
        self.assertEqual(primary["ci_high"], 4.0)
        self.assertEqual(len(analysis["estimates"]), 22)
        self.assertEqual(len(analysis["contrasts"]), 11)

    def test_unverified_primary_uses_welch(self) -> None:
        analysis = build_capacity_availability_analysis(
            self._analysis_rows(),
            self._design(),
            alignment_report={"status": "FAIL"},
            alignment_verified=False,
            scenario_ids=self.SCENARIOS,
            input_sample_ids=self.SAMPLES,
            replication_ids=self.REPLICATIONS,
        )

        self.assertEqual(
            analysis["primary"]["comparison_method"],
            "INDEPENDENT_WELCH_T",
        )
        self.assertEqual(
            analysis["primary"]["alignment_status"], "NOT_VERIFIED"
        )


class CapacityAvailabilityPackagingTests(unittest.TestCase):
    SCENARIOS = ("REFERENCE", "JOINT_32_18")
    SAMPLE = "BASE"
    REPLICATIONS = (1, 2, 3)

    @staticmethod
    def _sha256(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    @staticmethod
    def _write_csv(
        path: Path, fields: list[str], rows: list[dict[str, str]]
    ) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(
                stream, fieldnames=fields, lineterminator="\n"
            )
            writer.writeheader()
            writer.writerows(rows)

    def _canonical_rows(
        self,
    ) -> tuple[
        dict[str, list[str]],
        dict[str, list[dict[str, str]]],
    ]:
        schemas = load_result_schemas(DEFAULT_SCHEMA_REGISTRY)
        fields = {
            table: [str(item["field_name"]) for item in schemas[table]]
            for table in RESULT_FILES
        }
        types = {
            table: {
                str(item["field_name"]): str(item["data_type"])
                for item in schemas[table]
            }
            for table in RESULT_FILES
        }
        defaults = {
            "string": "X",
            "integer": "0",
            "number": "0",
            "boolean": "false",
        }
        rows: dict[str, list[dict[str, str]]] = {
            table: [] for table in RESULT_FILES
        }
        for scenario in self.SCENARIOS:
            config_hash = hashlib.sha256(scenario.encode()).hexdigest()
            for replication in self.REPLICATIONS:
                seeds = {
                    "master_seed": "1000",
                    "arrival_seed": str(2000 + replication),
                    "service_seed": str(3000 + replication),
                    "routing_seed": str(4000 + replication),
                    "tie_seed": str(5000 + replication),
                }
                lineage = {
                    "schema_version": "1.0",
                    "config_id": f"CONFIG_{scenario}",
                    "config_sha256": config_hash,
                    "model_version": "TEST_MODEL",
                    "scenario_id": scenario,
                    "input_sample_id": self.SAMPLE,
                    "replication_id": str(replication),
                }
                manifest = {
                    field: defaults[types["run_manifest"][field]]
                    for field in fields["run_manifest"]
                }
                manifest.update(
                    {
                        **lineage,
                        **seeds,
                        "reference_scenario_id": "REFERENCE",
                        "arrival_cutoff_seconds": "300",
                        "drain_end_seconds": "310",
                        "run_status": "COMPLETE",
                    }
                )
                rows["run_manifest"].append(manifest)

                kpi = {
                    field: defaults[types["replication_kpis"][field]]
                    for field in fields["replication_kpis"]
                }
                kpi.update(
                    {
                        **lineage,
                        "arrival_cutoff_seconds": "300",
                        "drain_end_seconds": "310",
                        "arrivals": "2",
                        "completed_after_drain": "2",
                        "conservation_pass": "true",
                        "run_status": "COMPLETE",
                        "security_utilization": "0.8",
                        "immigration_utilization": "0.8",
                    }
                )
                rows["replication_kpis"].append(kpi)

                for traveller_index in (1, 2):
                    entity = {
                        field: defaults[types["entity_log"][field]]
                        for field in fields["entity_log"]
                    }
                    security_start = (
                        float(traveller_index)
                        if scenario == "REFERENCE"
                        else 4.0
                    )
                    entity.update(
                        {
                            **lineage,
                            "traveller_id": f"T{traveller_index}",
                            "arrival_seconds": str(traveller_index - 1),
                            "security_service_demand_seconds": "1",
                            "immigration_conventional_service_demand_seconds": "1",
                            "automation_u": f"0.{traveller_index}",
                            "additional_check_u": f"0.{traveller_index + 2}",
                            "lane_tie_u": f"0.{traveller_index + 4}",
                            "security_queue_join_seconds": str(
                                traveller_index - 1
                            ),
                            "security_start_seconds": str(security_start),
                            "security_end_seconds": str(security_start + 1),
                            "immigration_queue_join_seconds": "5",
                            "immigration_start_seconds": "5",
                            "immigration_primary_end_seconds": "6",
                            "exit_seconds": "6",
                        }
                    )
                    rows["entity_log"].append(entity)
        return fields, rows

    def test_packages_audited_inputs_and_explicit_crn_report(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            results = root / "consolidated"
            output = root / "analysis"
            fields, rows = self._canonical_rows()
            for table, filename in RESULT_FILES.items():
                self._write_csv(results / filename, fields[table], rows[table])

            consolidation = {
                "status": "PASS",
                "lineage_status": "PASS",
                "cross_scenario_seed_lineage_status": "PASS",
                "coverage": {
                    "analysis_run_count": 6,
                    "scenario_count": 2,
                    "input_sample_count": 1,
                    "replications_per_cell": 3,
                    "coverage_status": "PASS",
                },
                "outputs": {
                    filename: {
                        "row_count": len(rows[table]),
                        "sha256": self._sha256(results / filename),
                    }
                    for table, filename in RESULT_FILES.items()
                },
            }
            (results / "consolidation_manifest.json").write_text(
                json.dumps(consolidation), encoding="utf-8"
            )
            design = CapacityAvailabilityBuilderTests._design()
            design["study_id"] = "TASK3_CAPACITY_AVAILABILITY_STRESS_V1"
            design_path = root / "design.json"
            design_path.write_text(json.dumps(design), encoding="utf-8")
            seed_path = root / "seeds.csv"
            seed_fields = [
                "schema_version",
                "study_id",
                "pairing_group_id",
                "arrival_level_id",
                "input_sample_id",
                "replication_id",
                "scenario_ids",
                "master_seed",
                "arrival_seed",
                "service_seed",
                "routing_seed",
                "tie_seed",
            ]
            seed_rows = [
                {
                    "schema_version": "1.0",
                    "study_id": design["study_id"],
                    "pairing_group_id": f"PAIR_{replication}",
                    "arrival_level_id": "MLE_BASE",
                    "input_sample_id": self.SAMPLE,
                    "replication_id": str(replication),
                    "scenario_ids": "|".join(self.SCENARIOS),
                    "master_seed": "1000",
                    "arrival_seed": str(2000 + replication),
                    "service_seed": str(3000 + replication),
                    "routing_seed": str(4000 + replication),
                    "tie_seed": str(5000 + replication),
                }
                for replication in self.REPLICATIONS
            ]
            self._write_csv(seed_path, seed_fields, seed_rows)

            report = package_capacity_availability_analysis(
                results,
                output,
                design_path=design_path,
                seed_manifest_path=seed_path,
                scenario_ids=self.SCENARIOS,
                input_sample_ids=(self.SAMPLE,),
                replication_ids=self.REPLICATIONS,
            )

            self.assertEqual(report["status"], "PASS")
            self.assertTrue(report["alignment_verified_for_pairing"])
            self.assertEqual(report["comparison_method"], "PAIRED_STUDENT_T")
            self.assertEqual(
                report["primary"]["difference_mean_travellers"], 1.0
            )
            self.assertTrue((output / "availability_by_replication.csv").is_file())
            self.assertTrue((output / "availability_estimates.csv").is_file())
            self.assertTrue((output / "availability_contrasts.csv").is_file())
            self.assertTrue((output / "crn_alignment.json").is_file())
            self.assertTrue((output / "analysis_manifest.json").is_file())
            self.assertTrue((output / "README.md").is_file())
            self.assertFalse((output / "entity_log.csv").exists())
            self.assertEqual(
                report["source_entity_log"]["row_count"], 12
            )


if __name__ == "__main__":
    unittest.main()
