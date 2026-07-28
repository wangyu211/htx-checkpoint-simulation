from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from src.analysis.analyse_operational_replications import (
    METRICS,
    alignment_report_passes,
    analyse_replication_rows,
    one_sample_summary,
)
from src.analysis.validate_operational_results import (
    DEFAULT_SCHEMA_REGISTRY,
    load_result_schemas,
    validate_operational_pilot_coverage,
    validate_operational_results,
)
from src.analysis.validate_operational_contract import DEFAULT_SCENARIOS


def analysis_row(
    scenario_id: str,
    replication_id: int,
    primary_p95: float,
    *,
    input_sample_id: str = "LOCAL_WINDOW_HPP_BASE",
) -> dict[str, str]:
    row = {
        "scenario_id": scenario_id,
        "input_sample_id": input_sample_id,
        "replication_id": str(replication_id),
    }
    for metric in METRICS:
        row[metric] = str(primary_p95 if metric == METRICS[0] else 0.1)
    return row


class ReplicationAnalysisTests(unittest.TestCase):
    def test_student_t_summary_uses_replications(self) -> None:
        summary = one_sample_summary([1.0, 2.0, 3.0])

        self.assertEqual(summary["n"], 3)
        self.assertAlmostEqual(float(summary["mean"]), 2.0)
        self.assertAlmostEqual(float(summary["standard_deviation"]), 1.0)
        self.assertAlmostEqual(float(summary["ci_low"]), -0.4841377117)
        self.assertAlmostEqual(float(summary["ci_high"]), 4.4841377117)

    def test_primary_estimand_is_mean_of_replication_p95_values(self) -> None:
        rows = [
            analysis_row("REFERENCE_ASSUMPTION_SANDBOX_V1", 1, 10),
            analysis_row("REFERENCE_ASSUMPTION_SANDBOX_V1", 2, 30),
            analysis_row("CAPACITY_SECURITY_PLUS_4", 1, 8),
            analysis_row("CAPACITY_SECURITY_PLUS_4", 2, 18),
        ]
        estimates, contrasts = analyse_replication_rows(rows)
        primary = next(
            row
            for row in estimates
            if row["scenario_id"] == "REFERENCE_ASSUMPTION_SANDBOX_V1"
            and row["metric"] == "total_queue_wait_p95_seconds"
        )
        contrast = next(
            row
            for row in contrasts
            if row["scenario_id"] == "CAPACITY_SECURITY_PLUS_4"
            and row["metric"] == "total_queue_wait_p95_seconds"
        )

        self.assertEqual(primary["mean"], 20.0)
        self.assertEqual(contrast["difference_mean"], -7.0)
        self.assertEqual(contrast["comparison_method"], "INDEPENDENT_WELCH_T")
        self.assertEqual(contrast["alignment_status"], "NOT_VERIFIED")

    def test_paired_interval_requires_explicit_alignment_gate(self) -> None:
        rows = [
            analysis_row("REFERENCE_ASSUMPTION_SANDBOX_V1", 1, 10),
            analysis_row("REFERENCE_ASSUMPTION_SANDBOX_V1", 2, 20),
            analysis_row("CAPACITY_SECURITY_PLUS_4", 1, 8),
            analysis_row("CAPACITY_SECURITY_PLUS_4", 2, 18),
        ]
        _, independent = analyse_replication_rows(
            rows, alignment_verified=False
        )
        _, paired = analyse_replication_rows(rows, alignment_verified=True)
        independent_primary = next(
            row
            for row in independent
            if row["metric"] == "total_queue_wait_p95_seconds"
        )
        paired_primary = next(
            row
            for row in paired
            if row["metric"] == "total_queue_wait_p95_seconds"
        )

        self.assertEqual(
            independent_primary["comparison_method"], "INDEPENDENT_WELCH_T"
        )
        self.assertEqual(paired_primary["comparison_method"], "PAIRED_STUDENT_T")
        self.assertEqual(paired_primary["ci_low"], -2.0)
        self.assertEqual(paired_primary["ci_high"], -2.0)

    def test_different_input_samples_cannot_be_paired(self) -> None:
        rows = [
            analysis_row("REFERENCE_ASSUMPTION_SANDBOX_V1", 1, 10),
            analysis_row("REFERENCE_ASSUMPTION_SANDBOX_V1", 2, 20),
            analysis_row(
                "DEMAND_HIGH_120",
                1,
                30,
                input_sample_id="LOCAL_WINDOW_HPP_HIGH",
            ),
            analysis_row(
                "DEMAND_HIGH_120",
                2,
                40,
                input_sample_id="LOCAL_WINDOW_HPP_HIGH",
            ),
        ]
        _, contrasts = analyse_replication_rows(
            rows, alignment_verified=True
        )
        primary = next(
            row
            for row in contrasts
            if row["metric"] == "total_queue_wait_p95_seconds"
        )

        self.assertEqual(primary["comparison_method"], "INDEPENDENT_WELCH_T")
        self.assertEqual(
            primary["alignment_status"],
            "NOT_APPLICABLE_DIFFERENT_INPUT_SAMPLE",
        )

    def test_generic_pass_string_is_not_enough_for_crn_claim(self) -> None:
        self.assertFalse(alignment_report_passes({"status": "PASS"}))
        self.assertTrue(
            alignment_report_passes(
                {
                    "status": "PASS",
                    "traveller_level_alignment_pass": True,
                    "branch_invariant_draws_pass": True,
                }
            )
        )


class OperationalResultValidationTests(unittest.TestCase):
    def _pilot_manifests(
        self,
    ) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
        with DEFAULT_SCENARIOS.open(encoding="utf-8", newline="") as stream:
            scenarios = list(csv.DictReader(stream))
        manifests: list[dict[str, str]] = []
        for index, scenario in enumerate(scenarios):
            master_seed = int(scenario["master_seed"])
            for replication in range(
                1,
                int(scenario["pilot_replications"]) + 1,
            ):
                stream_base = (
                    master_seed
                    + 100000 * index
                    + 100 * replication
                )
                manifests.append(
                    {
                        "schema_version": scenario["schema_version"],
                        "config_id": scenario["config_id"],
                        "model_version": "TASK3_OPERATIONAL_POOLED_V1",
                        "scenario_id": scenario["scenario_id"],
                        "scenario_family": scenario["scenario_family"],
                        "reference_scenario_id": scenario[
                            "reference_scenario_id"
                        ],
                        "input_sample_id": scenario["input_sample_id"],
                        "replication_id": str(replication),
                        "master_seed": scenario["master_seed"],
                        "arrival_seed": str(stream_base + 1),
                        "service_seed": str(stream_base + 2),
                        "routing_seed": str(stream_base + 3),
                        "tie_seed": str(stream_base + 4),
                        "start_state": "EMPTY_AND_IDLE",
                        "arrival_mode": scenario["arrival_mode"],
                        "arrival_cutoff_seconds": scenario[
                            "arrival_cutoff_seconds"
                        ],
                        "calibration_status": scenario[
                            "calibration_status"
                        ],
                        "claim_ceiling": scenario["claim_ceiling"],
                        "crn_alignment_status": scenario[
                            "crn_alignment_status"
                        ],
                    }
                )
        return manifests, scenarios

    def test_exact_operational_pilot_coverage_and_seed_contract(self) -> None:
        manifests, scenarios = self._pilot_manifests()
        self.assertEqual(len(manifests), 150)
        self.assertEqual(
            validate_operational_pilot_coverage(manifests, scenarios),
            [],
        )

        missing = validate_operational_pilot_coverage(
            manifests[:-1],
            scenarios,
        )
        self.assertTrue(any("missing 1 run keys" in error for error in missing))

        extra_row = dict(manifests[0])
        extra_row["replication_id"] = "0"
        extra = validate_operational_pilot_coverage(
            [*manifests, extra_row],
            scenarios,
        )
        self.assertTrue(
            any("unexpected run keys" in error for error in extra)
        )

        wrong_seed = [dict(row) for row in manifests]
        wrong_seed[0]["arrival_seed"] = "1"
        seed_errors = validate_operational_pilot_coverage(
            wrong_seed,
            scenarios,
        )
        self.assertTrue(
            any(":arrival_seed: expected" in error for error in seed_errors)
        )

    def _valid_rows(self) -> dict[str, list[dict[str, str]]]:
        common = {
            "schema_version": "1.0",
            "config_id": "OP_REFERENCE_ASSUMPTION_SANDBOX_V1",
            "config_sha256": (
                "166e6c918cff63041b08f31ff5c17fbea49008b8cdd3047b1082b326faae3460"
            ),
            "model_version": "operational-v1",
            "scenario_id": "REFERENCE_ASSUMPTION_SANDBOX_V1",
            "input_sample_id": "LOCAL_WINDOW_HPP_BASE",
            "replication_id": "1",
        }
        manifest = {
            **common,
            "scenario_family": "REFERENCE",
            "reference_scenario_id": "REFERENCE_ASSUMPTION_SANDBOX_V1",
            "master_seed": "2026072800",
            "arrival_seed": "2026072801",
            "service_seed": "2026072802",
            "routing_seed": "2026072803",
            "tie_seed": "2026072804",
            "start_state": "EMPTY",
            "arrival_mode": "HPP",
            "arrival_cutoff_seconds": "300",
            "drain_end_seconds": "300",
            "drain_rule": "FULL_DRAIN",
            "engine_name": "TEST",
            "engine_version": "1",
            "calibration_status": "NOT_CALIBRATED",
            "claim_ceiling": "COMPARATIVE_WHAT_IF_ONLY",
            "crn_alignment_status": "NOT_TESTED",
            "run_status": "COMPLETE",
        }
        entity = {
            **common,
            "traveller_id": "T001",
            "arrival_seconds": "1",
            "security_service_demand_seconds": "1",
            "immigration_conventional_service_demand_seconds": "1",
            "automation_u": "0.2",
            "additional_check_u": "0.3",
            "lane_tie_u": "0.4",
            "security_queue_join_seconds": "1",
            "security_start_seconds": "1",
            "security_end_seconds": "2",
            "immigration_queue_join_seconds": "2",
            "immigration_lane_id": "IMM_POOL",
            "immigration_start_seconds": "2",
            "technology_flag": "false",
            "immigration_primary_service_demand_seconds": "1",
            "immigration_primary_end_seconds": "3",
            "additional_check_flag": "false",
            "additional_check_service_demand_seconds": "",
            "additional_check_end_seconds": "",
            "exit_seconds": "3",
            "security_resource_id": "SEC_01",
            "immigration_resource_id": "IMM_01",
        }
        kpi = {
            **common,
            "arrival_cutoff_seconds": "300",
            "drain_end_seconds": "300",
            "arrivals": "1",
            "completed_at_cutoff": "1",
            "security_queue_at_cutoff": "0",
            "security_in_service_at_cutoff": "0",
            "immigration_queue_at_cutoff": "0",
            "immigration_in_service_at_cutoff": "0",
            "wip_at_cutoff": "0",
            "completed_after_drain": "1",
            "rejected_or_dropped_count": "0",
            "technology_count": "0",
            "additional_check_count": "0",
            "security_wait_mean_seconds": "0",
            "security_wait_p95_seconds": "0",
            "immigration_wait_mean_seconds": "0",
            "immigration_wait_p95_seconds": "0",
            "total_queue_wait_mean_seconds": "0",
            "total_queue_wait_p95_seconds": "0",
            "total_queue_wait_exceed_600_rate": "0",
            "total_queue_wait_exceed_900_rate": "0",
            "total_queue_wait_exceed_1200_rate": "0",
            "system_time_mean_seconds": "2",
            "system_time_p95_seconds": "2",
            "security_utilization": "0.1",
            "immigration_utilization": "0.1",
            "cutoff_backlog": "0",
            "cutoff_backlog_fraction": "0",
            "cohort_clear_time_after_cutoff_seconds": "0",
            "conservation_pass": "true",
            "run_status": "COMPLETE",
        }
        return {
            "run_manifest": [manifest],
            "entity_log": [entity],
            "replication_kpis": [kpi],
        }

    def _write_fixture(
        self, directory: Path, rows: dict[str, list[dict[str, str]]]
    ) -> None:
        schemas = load_result_schemas(DEFAULT_SCHEMA_REGISTRY)
        filenames = {
            "run_manifest": "run_manifest.csv",
            "entity_log": "entity_log.csv",
            "replication_kpis": "replication_kpis.csv",
        }
        for table, filename in filenames.items():
            fieldnames = [row["field_name"] for row in schemas[table]]
            with (directory / filename).open(
                "w", encoding="utf-8", newline=""
            ) as stream:
                writer = csv.DictWriter(stream, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows[table])

    def test_valid_fixture_passes_schema_and_invariants(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            self._write_fixture(path, self._valid_rows())
            report = validate_operational_results(path)

        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["run_count"], 1)
        self.assertEqual(report["entity_count"], 1)

    def test_dropped_traveller_is_rejected(self) -> None:
        rows = self._valid_rows()
        rows["replication_kpis"][0]["rejected_or_dropped_count"] = "1"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            self._write_fixture(path, rows)
            report = validate_operational_results(path)

        self.assertEqual(report["status"], "FAIL")
        self.assertTrue(
            any("dropped travellers are prohibited" in error for error in report["errors"])
        )

    def test_noncanonical_scenario_hash_is_rejected(self) -> None:
        rows = self._valid_rows()
        for table in ("run_manifest", "entity_log", "replication_kpis"):
            rows[table][0]["config_sha256"] = "b" * 64
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            self._write_fixture(path, rows)
            report = validate_operational_results(path)

        self.assertEqual(report["status"], "FAIL")
        self.assertTrue(
            any(
                "config_sha256 does not match the canonical scenario row"
                in error
                for error in report["errors"]
            )
        )

    def test_entity_lineage_must_match_the_run_manifest(self) -> None:
        rows = self._valid_rows()
        rows["entity_log"][0]["model_version"] = "mislabeled-model"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            self._write_fixture(path, rows)
            report = validate_operational_results(path)

        self.assertEqual(report["status"], "FAIL")
        self.assertTrue(
            any(
                "entity_log.csv:2:model_version: does not match "
                "run_manifest.csv" in error
                for error in report["errors"]
            )
        )


if __name__ == "__main__":
    unittest.main()
