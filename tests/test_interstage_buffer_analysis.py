from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from src.analysis.analyse_interstage_buffer import (
    BUFFER_LEVELS,
    EXPECTED_RUN_COUNT,
    REGIMES,
    REPLICATION_FIELDS,
    REPLICATION_IDS,
    STUDY_ID,
    _write_csv,
    analyse_csv,
    build_crn_alignment_report,
    build_exact_replay_report,
    build_negative_control_report,
    validate_imported_rows,
)
from src.analysis.plot_interstage_buffer import (
    _estimate_grid,
    _require_pass,
    render_chart_d,
)
from src.analysis.consolidate_interstage_buffer_results import (
    consolidate_interstage_buffer_results,
)
from src.analysis.interstage_buffer_design import (
    MODEL_VERSION,
    interstage_scenario_config_sha256,
    load_interstage_buffer_scenario_rows,
    load_interstage_buffer_seed_rows,
)


def _digest(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _synthetic_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    scenario_rows = {
        (
            int(row["security_capacity"]),
            int(row["immigration_capacity"]),
            int(row["interstage_buffer_capacity"]),
        ): row
        for row in load_interstage_buffer_scenario_rows()
    }
    seed_rows = {
        int(row["replication_id"]): row
        for row in load_interstage_buffer_seed_rows()
    }
    for replication_id in REPLICATION_IDS:
        input_digest = _digest(f"input-draws-{replication_id}")
        seed = seed_rows[replication_id]
        for security, immigration in REGIMES:
            positive = (security, immigration) == (36, 16)
            base_system_time = 180.0 + replication_id / 10.0
            for buffer_capacity in BUFFER_LEVELS:
                if positive:
                    system_penalty = {25: 45.0, 50: 18.0, 100: 0.0, 5000: 0.0}[
                        buffer_capacity
                    ]
                    blocked_fraction = {
                        25: 0.18,
                        50: 0.07,
                        100: 0.0,
                        5000: 0.0,
                    }[buffer_capacity]
                    peak_occupancy = {
                        25: 25,
                        50: 50,
                        100: 60,
                        5000: 60,
                    }[buffer_capacity]
                    mean_occupancy = {
                        25: 19.0,
                        50: 31.0,
                        100: 40.0,
                        5000: 40.0,
                    }[buffer_capacity]
                    full_fraction = {
                        25: 0.10,
                        50: 0.03,
                        100: 0.0,
                        5000: 0.0,
                    }[buffer_capacity]
                    block_mean = {
                        25: 8.0,
                        50: 3.0,
                        100: 0.0,
                        5000: 0.0,
                    }[buffer_capacity]
                    block_p95 = {
                        25: 30.0,
                        50: 12.0,
                        100: 0.0,
                        5000: 0.0,
                    }[buffer_capacity]
                    event_level = (
                        100 if buffer_capacity in (100, 5000) else buffer_capacity
                    )
                else:
                    system_penalty = 0.0
                    blocked_fraction = 0.0
                    peak_occupancy = 10
                    mean_occupancy = 5.0
                    full_fraction = 0.0
                    block_mean = 0.0
                    block_p95 = 0.0
                    event_level = 100

                scenario_row = scenario_rows[
                    (security, immigration, buffer_capacity)
                ]
                scenario = scenario_row["scenario_id"]
                system_time = base_system_time + system_penalty
                last_exit_seconds = 360.0 + system_penalty
                blocked_seconds = (
                    blocked_fraction * security * last_exit_seconds
                )
                busy_seconds = 4000.0
                blocked_share = blocked_seconds / (
                    busy_seconds + blocked_seconds
                )
                rows.append(
                    {
                        "schema_version": "1.0",
                        "study_id": STUDY_ID,
                        "config_id": scenario_row["config_id"],
                        "config_sha256": interstage_scenario_config_sha256(
                            scenario_row
                        ),
                        "model_version": MODEL_VERSION,
                        "scenario_id": scenario,
                        "input_sample_id": "LOCAL_WINDOW_HPP_BASE",
                        "replication_id": replication_id,
                        "security_capacity": security,
                        "immigration_capacity": immigration,
                        "interstage_buffer_capacity": buffer_capacity,
                        "master_seed": int(seed["master_seed"]),
                        "arrival_seed": int(seed["arrival_seed"]),
                        "service_seed": int(seed["service_seed"]),
                        "routing_seed": int(seed["routing_seed"]),
                        "tie_seed": int(seed["tie_seed"]),
                        "input_draws_sha256": input_digest,
                        "normalized_event_payload_sha256": _digest(
                            f"events-{security}-{immigration}-"
                            f"{event_level}-{replication_id}"
                        ),
                        "arrivals": 100 + replication_id,
                        "completed_after_drain": 100 + replication_id,
                        "rejected_or_dropped_count": 0,
                        "conservation_pass": "true",
                        "run_status": "COMPLETE",
                        "interstage_buffer_peak_occupancy": peak_occupancy,
                        "system_time_p95_seconds": system_time,
                        "security_blocked_resource_fraction": blocked_fraction,
                        "security_blocked_resource_seconds": blocked_seconds,
                        "security_busy_seconds": busy_seconds,
                        "last_exit_seconds": last_exit_seconds,
                        "security_blocked_share_of_occupied": blocked_share,
                        "interstage_buffer_full_time_fraction": full_fraction,
                        "time_weighted_mean_interstage_buffer_occupancy": (
                            mean_occupancy
                        ),
                        "interstage_block_time_mean_seconds": block_mean,
                        "interstage_block_time_p95_seconds": block_p95,
                        "total_wait_including_interstage_mean_seconds": (
                            20.0 + system_penalty / 3.0
                        ),
                        "total_wait_including_interstage_p95_seconds": (
                            45.0 + system_penalty
                        ),
                        "cohort_clear_time_after_cutoff_seconds": (
                            60.0 + system_penalty
                        ),
                    }
                )
    return rows


class InterstageBufferValidationTests(unittest.TestCase):
    def test_registered_batch_passes_every_gate(self) -> None:
        rows, validation = validate_imported_rows(_synthetic_rows())
        self.assertEqual(len(rows), EXPECTED_RUN_COUNT)
        self.assertEqual(validation["status"], "PASS")
        self.assertEqual(
            build_crn_alignment_report(rows)["status"],
            "PASS",
        )
        replay = build_exact_replay_report(rows)
        self.assertEqual(replay["status"], "PASS")
        self.assertEqual(
            sum(
                int(regime["exactly_matched_pair_count"])
                for regime in replay["regimes"]
            ),
            2 * len(REPLICATION_IDS),
        )
        negative_control, contrasts = build_negative_control_report(rows)
        self.assertEqual(negative_control["status"], "PASS")
        self.assertEqual(len(contrasts), 3)

    def test_exact_coverage_and_conservation_fail_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "exactly 400 rows"):
            validate_imported_rows(_synthetic_rows()[:-1])

        rows = _synthetic_rows()
        rows[0]["completed_after_drain"] = int(rows[0]["arrivals"]) - 1
        with self.assertRaisesRegex(ValueError, "full-drain conservation"):
            validate_imported_rows(rows)

    def test_crn_seed_or_draw_drift_is_rejected(self) -> None:
        rows, _ = validate_imported_rows(_synthetic_rows())
        rows[0]["arrival_seed"] = int(rows[0]["arrival_seed"]) + 1
        report = build_crn_alignment_report(rows)
        self.assertEqual(report["status"], "FAIL")
        self.assertTrue(any("seed drift" in error for error in report["errors"]))

        rows, _ = validate_imported_rows(_synthetic_rows())
        rows[0]["input_draws_sha256"] = _digest("different-inputs")
        report = build_crn_alignment_report(rows)
        self.assertEqual(report["status"], "FAIL")
        self.assertTrue(any("input-draw drift" in error for error in report["errors"]))

    def test_exact_replay_and_negative_control_gates_fail_closed(self) -> None:
        rows, _ = validate_imported_rows(_synthetic_rows())
        replay_row = next(
            row
            for row in rows
            if int(row["security_capacity"]) == 36
            and int(row["immigration_capacity"]) == 16
            and int(row["interstage_buffer_capacity"]) == 100
            and int(row["replication_id"]) == 1
        )
        replay_row["normalized_event_payload_sha256"] = _digest(
            "replay-mismatch"
        )
        replay = build_exact_replay_report(rows)
        self.assertEqual(replay["status"], "FAIL")
        self.assertTrue(
            any("normalized_event_payload_sha256" in error for error in replay["errors"])
        )

        rows, _ = validate_imported_rows(_synthetic_rows())
        for row in rows:
            if (
                int(row["security_capacity"]) == 30
                and int(row["immigration_capacity"]) == 21
                and int(row["interstage_buffer_capacity"]) == 25
            ):
                row["system_time_p95_seconds"] = (
                    float(row["system_time_p95_seconds"]) + 10.0
                )
        control, _ = build_negative_control_report(rows)
        self.assertEqual(control["status"], "FAIL")
        self.assertTrue(control["errors"])


class InterstageBufferPackageAndPlotTests(unittest.TestCase):
    def test_consolidator_refuses_incomplete_raw_tree(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw_root = root / "raw"
            raw_root.mkdir()
            output_csv = root / "consolidated.csv"
            manifest_path = root / "consolidation_manifest.json"
            with self.assertRaisesRegex(ValueError, "exactly 400"):
                consolidate_interstage_buffer_results(
                    raw_root,
                    output_csv,
                    manifest_path,
                    root / "raw_artifact_manifest.csv",
                )
            self.assertFalse(output_csv.exists())
            manifest = json.loads(
                manifest_path.read_text(encoding="utf-8")
            )
            self.assertEqual(manifest["status"], "FAIL")

    def test_builds_plot_ready_package_and_vector_safe_chart(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw_root = root / "raw"
            input_csv = root / "interstage_buffer_by_replication.csv"
            analysis_dir = root / "analysis"
            figure_dir = root / "figures"
            for row in _synthetic_rows():
                run_path = (
                    raw_root
                    / (
                        f"S{row['security_capacity']}_"
                        f"I{row['immigration_capacity']}"
                    )
                    / str(row["scenario_id"])
                    / f"replication_{int(row['replication_id']):03d}"
                    / "replication_kpis.csv"
                )
                _write_csv(run_path, [row], REPLICATION_FIELDS)
            consolidation = consolidate_interstage_buffer_results(
                raw_root,
                input_csv,
                root / "consolidation_manifest.json",
                root / "raw_artifact_manifest.csv",
            )
            self.assertEqual(consolidation["status"], "PASS")
            self.assertEqual(consolidation["source_file_count"], 400)

            manifest = analyse_csv(input_csv, analysis_dir)
            self.assertEqual(manifest["status"], "PASS")
            self.assertEqual(manifest["actual_run_count"], EXPECTED_RUN_COUNT)
            _require_pass(analysis_dir)
            estimates = _estimate_grid(analysis_dir)
            self.assertEqual(len(estimates), 4)

            render_chart_d(analysis_dir, figure_dir)
            expected = {
                "interstage_buffer_chart_d.png",
                "interstage_buffer_chart_d.svg",
            }
            self.assertEqual(
                {path.name for path in figure_dir.iterdir()},
                expected,
            )
            for filename in expected:
                payload = (figure_dir / filename).read_bytes()
                self.assertGreater(len(payload), 10_000)
                if filename.endswith(".svg"):
                    self.assertNotIn(b"<image", payload.lower())
                    self.assertNotIn(b"data:image", payload.lower())
                    self.assertNotIn(b"\r\n", payload)

            validation = json.loads(
                (analysis_dir / "validation.json").read_text(encoding="utf-8")
            )
            self.assertEqual(validation["actual_run_count"], 400)

    def test_plotting_refuses_failed_validation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "validation.json").write_text(
                json.dumps({"status": "FAIL"}),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                ValueError,
                "validation.json must report PASS",
            ):
                _require_pass(root)


if __name__ == "__main__":
    unittest.main()
