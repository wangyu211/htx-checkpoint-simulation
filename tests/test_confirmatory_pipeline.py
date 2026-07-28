from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from src.analysis.analyse_confirmatory_capacity import (
    build_confirmatory_analysis,
    confirmatory_alignment_report_passes,
)
from src.analysis.analyse_operational_replications import METRICS
from src.analysis.confirmatory_design import (
    CAPACITY_SCENARIO_IDS,
    DEFAULT_DESIGN,
    build_confirmatory_scenario_rows,
    load_confirmatory_seed_rows,
)
from src.analysis.validate_operational_contract import scenario_config_sha256
from src.analysis.validate_operational_results import (
    validate_confirmatory_coverage,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ConfirmatoryCoverageTests(unittest.TestCase):
    def _manifests(self) -> list[dict[str, str]]:
        scenario_rows = {
            (row["scenario_id"], row["input_sample_id"]): row
            for row in build_confirmatory_scenario_rows()
        }
        manifests: list[dict[str, str]] = []
        for seed in load_confirmatory_seed_rows():
            for scenario_id in seed["scenario_ids"].split("|"):
                scenario = scenario_rows[
                    (scenario_id, seed["input_sample_id"])
                ]
                manifests.append(
                    {
                        "schema_version": scenario["schema_version"],
                        "config_id": scenario["config_id"],
                        "config_sha256": scenario_config_sha256(scenario),
                        "model_version": "TASK3_OPERATIONAL_POOLED_V1",
                        "scenario_id": scenario_id,
                        "scenario_family": scenario["scenario_family"],
                        "reference_scenario_id": scenario[
                            "reference_scenario_id"
                        ],
                        "input_sample_id": seed["input_sample_id"],
                        "replication_id": seed["replication_id"],
                        "master_seed": seed["master_seed"],
                        "arrival_seed": seed["arrival_seed"],
                        "service_seed": seed["service_seed"],
                        "routing_seed": seed["routing_seed"],
                        "tie_seed": seed["tie_seed"],
                        "start_state": "EMPTY_AND_IDLE",
                        "arrival_mode": scenario["arrival_mode"],
                        "calibration_status": scenario[
                            "calibration_status"
                        ],
                        "claim_ceiling": scenario["claim_ceiling"],
                        "crn_alignment_status": scenario[
                            "crn_alignment_status"
                        ],
                    }
                )
        return manifests

    def test_exact_600_run_composite_key_contract_passes(self) -> None:
        scenario_rows = build_confirmatory_scenario_rows()
        seed_rows = load_confirmatory_seed_rows()
        manifests = self._manifests()

        self.assertEqual(len(manifests), 600)
        self.assertEqual(
            len(
                {
                    (
                        row["scenario_id"],
                        row["input_sample_id"],
                        row["replication_id"],
                    )
                    for row in manifests
                }
            ),
            600,
        )
        self.assertEqual(
            validate_confirmatory_coverage(
                manifests,
                scenario_rows,
                seed_rows,
            ),
            [],
        )

    def test_missing_run_and_wrong_stream_seed_fail_closed(self) -> None:
        scenario_rows = build_confirmatory_scenario_rows()
        seed_rows = load_confirmatory_seed_rows()
        manifests = self._manifests()
        manifests[0]["service_seed"] = "1"
        manifests.pop()

        errors = validate_confirmatory_coverage(
            manifests,
            scenario_rows,
            seed_rows,
        )

        joined = "\n".join(errors)
        self.assertIn("coverage is missing 1 run keys", joined)
        self.assertIn("service_seed", joined)

    def test_scenario_id_alone_is_not_a_valid_cell_key(self) -> None:
        scenario_rows = build_confirmatory_scenario_rows()
        collapsed = {
            row["scenario_id"]: row for row in scenario_rows
        }

        self.assertEqual(len(collapsed), 4)
        self.assertEqual(
            len(
                {
                    (row["scenario_id"], row["input_sample_id"])
                    for row in scenario_rows
                }
            ),
            12,
        )


class ConfirmatoryAnalysisTests(unittest.TestCase):
    def setUp(self) -> None:
        self.design = json.loads(DEFAULT_DESIGN.read_text(encoding="utf-8"))
        self.samples = {
            level["level_id"]: level["input_sample_id"]
            for level in self.design["arrival_rate_uncertainty"]["levels"]
        }

    def _kpis(
        self,
        *,
        reverse_high_rate: bool = False,
    ) -> list[dict[str, str]]:
        base_by_scenario = {
            "REFERENCE_ASSUMPTION_SANDBOX_V1": 40.0,
            "CAPACITY_SECURITY_PLUS_4": 30.0,
            "CAPACITY_IMMIGRATION_PLUS_3": 20.0,
            "CAPACITY_BOTH_PLUS": 10.0,
        }
        rows: list[dict[str, str]] = []
        for level_index, (level_id, sample_id) in enumerate(
            self.samples.items()
        ):
            for scenario_index, scenario_id in enumerate(
                CAPACITY_SCENARIO_IDS
            ):
                scenario_base = base_by_scenario[scenario_id]
                if reverse_high_rate and level_id == "EXACT95_HIGH":
                    scenario_base = 10.0 * (scenario_index + 1)
                for replication in range(1, 51):
                    primary_value = (
                        scenario_base
                        + 100.0 * level_index
                        + 0.1 * replication
                    )
                    row = {
                        "scenario_id": scenario_id,
                        "input_sample_id": sample_id,
                        "replication_id": str(replication),
                    }
                    row.update(
                        {
                            metric: str(
                                primary_value
                                if metric
                                == "total_queue_wait_p95_seconds"
                                else 0.01 * replication
                            )
                            for metric in METRICS
                        }
                    )
                    rows.append(row)
        return rows

    def test_verified_alignment_uses_paired_primary_and_reports_precision(
        self,
    ) -> None:
        analysis = build_confirmatory_analysis(
            self._kpis(),
            self.design,
            alignment_verified=True,
        )

        primary = analysis["primary"]
        self.assertEqual(primary["comparison_method"], "PAIRED_STUDENT_T")
        self.assertEqual(primary["alignment_status"], "PASS")
        self.assertEqual(primary["difference_mean_seconds"], -30.0)
        self.assertTrue(primary["precision_target_met"])
        self.assertEqual(len(analysis["rankings"]), 12)
        self.assertEqual(len(analysis["pairwise"]), 18)
        self.assertTrue(
            analysis["stability"]["point_order_stable_across_rates"]
        )
        self.assertTrue(
            analysis["stability"][
                "pairwise_point_direction_stable_across_rates"
            ]
        )

    def test_unverified_alignment_falls_back_to_welch(self) -> None:
        analysis = build_confirmatory_analysis(
            self._kpis(),
            self.design,
            alignment_verified=False,
        )

        self.assertEqual(
            analysis["primary"]["comparison_method"],
            "INDEPENDENT_WELCH_T",
        )
        self.assertEqual(
            analysis["primary"]["alignment_status"],
            "NOT_VERIFIED",
        )
        self.assertTrue(
            all(
                row["comparison_method"] == "INDEPENDENT_WELCH_T"
                for row in analysis["pairwise"]
            )
        )

    def test_rate_specific_ranking_reversal_is_reported(self) -> None:
        analysis = build_confirmatory_analysis(
            self._kpis(reverse_high_rate=True),
            self.design,
            alignment_verified=True,
        )

        self.assertFalse(
            analysis["stability"]["point_order_stable_across_rates"]
        )
        self.assertFalse(
            analysis["stability"][
                "pairwise_point_direction_stable_across_rates"
            ]
        )
        self.assertTrue(
            any(
                row["rank_delta_from_base"] != 0
                for row in analysis["rankings"]
                if row["arrival_level_id"] == "EXACT95_HIGH"
            )
        )

    def test_equal_point_estimates_receive_a_shared_rank(self) -> None:
        rows = self._kpis()
        low_sample = "LOCAL_WINDOW_HPP_EXACT95_LOW"
        for row in rows:
            if (
                row["input_sample_id"] == low_sample
                and row["scenario_id"]
                in {
                    "CAPACITY_BOTH_PLUS",
                    "CAPACITY_IMMIGRATION_PLUS_3",
                }
            ):
                row["total_queue_wait_p95_seconds"] = "0"

        analysis = build_confirmatory_analysis(
            rows,
            self.design,
            alignment_verified=True,
        )
        low_rows = {
            row["scenario_id"]: row
            for row in analysis["rankings"]
            if row["arrival_level_id"] == "EXACT95_LOW"
        }
        self.assertEqual(
            low_rows["CAPACITY_BOTH_PLUS"]["point_estimate_rank"],
            1,
        )
        self.assertEqual(
            low_rows["CAPACITY_IMMIGRATION_PLUS_3"][
                "point_estimate_rank"
            ],
            1,
        )
        self.assertFalse(
            analysis["stability"]["point_order_stable_across_rates"]
        )
        self.assertEqual(
            analysis["stability"]["tie_groups_by_level"]["EXACT95_LOW"][0],
            [
                "CAPACITY_BOTH_PLUS",
                "CAPACITY_IMMIGRATION_PLUS_3",
            ],
        )

    def test_alignment_gate_rejects_stale_artifact_hash(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            design_path = root / "design.json"
            seed_path = root / "seeds.csv"
            results = root / "results"
            results.mkdir()
            design_path.write_text("design", encoding="utf-8")
            seed_path.write_text("seeds", encoding="utf-8")
            (results / "run_manifest.csv").write_text(
                "manifest",
                encoding="utf-8",
            )
            (results / "entity_log.csv").write_text(
                "entities",
                encoding="utf-8",
            )
            report = {
                "status": "PASS",
                "validation": "CONFIRMATORY_CAPACITY_CRN_ALIGNMENT_V1",
                "study_id": "STUDY",
                "coverage_pass": True,
                "seed_alignment_pass": True,
                "traveller_level_alignment_pass": True,
                "branch_invariant_draws_pass": True,
                "errors": [],
                "artifact_hashes": {
                    "design_sha256": _sha256(design_path),
                    "seed_manifest_sha256": _sha256(seed_path),
                    "run_manifest_sha256": _sha256(
                        results / "run_manifest.csv"
                    ),
                    "entity_log_sha256": _sha256(
                        results / "entity_log.csv"
                    ),
                },
                "expected_run_key_sha256": "same",
                "actual_run_key_sha256": "same",
            }
            self.assertTrue(
                confirmatory_alignment_report_passes(
                    report,
                    study_id="STUDY",
                    design_path=design_path,
                    seed_manifest_path=seed_path,
                    results_dir=results,
                )
            )

            (results / "entity_log.csv").write_text(
                "changed",
                encoding="utf-8",
            )
            self.assertFalse(
                confirmatory_alignment_report_passes(
                    report,
                    study_id="STUDY",
                    design_path=design_path,
                    seed_manifest_path=seed_path,
                    results_dir=results,
                )
            )


if __name__ == "__main__":
    unittest.main()
