from __future__ import annotations

import csv
import json
import os
import tempfile
import unittest
from pathlib import Path

from src.analysis.validate_animation_speed_invariance import (
    CAPTURE_METADATA_FILE,
    DEFAULT_PROTOCOL,
    EXPECTED_TABLES,
    UI_EVIDENCE_FILE,
    _sha256,
    load_protocol,
    stage_capture,
    validate_evidence,
)
from src.analysis.validate_operational_results import (
    DEFAULT_SCHEMA_REGISTRY,
    RESULT_FILES,
    load_result_schemas,
)


MODEL_COMMIT = "1" * 40
CONFIG_SHA256 = "2" * 64
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


class AnimationSpeedInvarianceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.protocol = load_protocol(DEFAULT_PROTOCOL)
        self.schemas = load_result_schemas(DEFAULT_SCHEMA_REGISTRY)

    def _value(
        self, table: str, field: dict[str, str], row_index: int
    ) -> str:
        name = field["field_name"]
        special = {
            "schema_version": "1.0",
            "config_id": "OP_INTERACTIVE_AD_HOC_V1",
            "config_sha256": CONFIG_SHA256,
            "model_version": "TASK3_OPERATIONAL_POOLED_V1",
            "scenario_id": "INTERACTIVE_D100_SEC036_IMM021_U000_M100",
            "scenario_family": "INTERACTIVE_EXPLORATORY",
            "reference_scenario_id": "REFERENCE_ASSUMPTION_SANDBOX_V1",
            "input_sample_id": "LOCAL_WINDOW_HPP_BASE",
            "replication_id": "0",
            "traveller_id": f"LOCAL_WINDOW_HPP_BASE_R000_T{row_index:05d}",
            "immigration_lane_id": "IMMIGRATION_POOLED",
            "security_resource_id": f"SECURITY_{row_index:03d}",
            "immigration_resource_id": f"IMMIGRATION_{row_index:03d}",
            "start_state": "EMPTY_AND_IDLE",
            "arrival_mode": "HPP",
            "drain_rule": "FULL_DRAIN",
            "engine_name": "AnyLogic",
            "engine_version": "8.9.9.202607020720",
            "calibration_status": "NOT_CALIBRATED",
            "claim_ceiling": "COMPARATIVE_WHAT_IF_ONLY",
            "crn_alignment_status": "NOT_TESTED",
            "run_status": "COMPLETE",
            "conservation_pass": "true",
            "rejected_or_dropped_count": "0",
            "arrival_cutoff_seconds": "300.000000000",
            "drain_end_seconds": "301.000000000",
            "arrivals": "2",
            "completed_after_drain": "2",
            "completed_at_cutoff": "1",
        }
        if name in special:
            return special[name]
        if field["nullable"] == "true":
            return ""
        if field["data_type"] == "integer":
            return str(row_index)
        if field["data_type"] == "number":
            return f"{row_index + 0.125:.9f}"
        if field["data_type"] == "boolean":
            return "false"
        return f"{table}_{name}"

    def _table_rows(self, table: str) -> list[dict[str, str]]:
        count = 2 if table == "entity_log" else 1
        return [
            {
                field["field_name"]: self._value(table, field, row_index)
                for field in self.schemas[table]
            }
            for row_index in range(1, count + 1)
        ]

    def _write_core(self, directory: Path) -> dict[str, int]:
        directory.mkdir(parents=True, exist_ok=True)
        mtimes: dict[str, int] = {}
        for table in EXPECTED_TABLES:
            path = directory / RESULT_FILES[table]
            fields = [field["field_name"] for field in self.schemas[table]]
            with path.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=fields)
                writer.writeheader()
                writer.writerows(self._table_rows(table))
            mtimes[path.name] = path.stat().st_mtime_ns
        return mtimes

    def _write_capture(
        self,
        root: Path,
        mode_index: int,
        *,
        commit: str = MODEL_COMMIT,
        mtime_base: int = 10_000_000_000,
    ) -> Path:
        mode = self.protocol["required_run_order"][mode_index]
        directory = root / mode["directory_name"]
        self._write_core(directory)
        mtimes = {
            filename: mtime_base + mode_index * 1_000_000 + position
            for position, filename in enumerate(
                self.protocol["required_core_files"], start=1
            )
        }
        screenshot = directory / UI_EVIDENCE_FILE
        screenshot.write_bytes(
            PNG_SIGNATURE + f"mode-{mode_index}".encode("ascii")
        )
        metadata = {
            "schema_version": self.protocol["schema_version"],
            "contract_id": self.protocol["contract_id"],
            "evidence_id": self.protocol["evidence_id"],
            "experiment_name": self.protocol["experiment_name"],
            "run_mode": mode["run_mode"],
            "directory_name": mode["directory_name"],
            "execution_mode": mode["execution_mode"],
            "real_time_scale": mode["real_time_scale"],
            "animation_condition": mode["animation_condition"],
            "operator_role_alias": "model_owner",
            "model_git_commit": commit,
            "capture_utc": f"2026-07-29T0{mode_index}:00:00Z",
            "finished_confirmed": True,
            "source_run_directory": self.protocol["source_run_directory"],
            "source_file_mtime_ns": mtimes,
            "core_file_sha256": {
                filename: _sha256(directory / filename)
                for filename in self.protocol["required_core_files"]
            },
            "ui_evidence_sha256": _sha256(screenshot),
            "wall_clock_elapsed_seconds": 100.0 / (mode_index + 1),
            "wall_clock_excluded_from_model_equality": True,
        }
        (directory / CAPTURE_METADATA_FILE).write_text(
            json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
        )
        return directory

    def _write_all_captures(self, root: Path) -> None:
        for index in range(3):
            self._write_capture(root, index)

    def test_frozen_protocol_is_implemented_not_executed(self) -> None:
        self.assertEqual(
            self.protocol["current_evidence_state"],
            "IMPLEMENTED_NOT_EXECUTED",
        )
        self.assertEqual(
            [
                mode["run_mode"]
                for mode in self.protocol["required_run_order"]
            ],
            ["GUI_1X", "GUI_10X", "GUI_VIRTUAL_TIME"],
        )

    def test_missing_real_captures_remains_not_executed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            report = validate_evidence(
                DEFAULT_PROTOCOL, Path(directory) / "evidence"
            )
        self.assertEqual(report["status"], "NOT_EXECUTED")
        self.assertEqual(
            report["evidence_state"], "IMPLEMENTED_NOT_EXECUTED"
        )
        self.assertEqual(len(report["missing_run_modes"]), 3)

    def test_three_exact_core_runs_pass_despite_different_capture_metadata(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "evidence"
            self._write_all_captures(root)
            report = validate_evidence(DEFAULT_PROTOCOL, root)
        self.assertEqual(report["status"], "PASS", report["errors"])
        self.assertEqual(report["evidence_state"], "EVIDENCE_ACCEPTED")
        self.assertTrue(
            all(
                comparison["status"] == "PASS"
                for comparison in report["comparisons"]
            )
        )
        self.assertIn(
            "wall_clock_elapsed_seconds",
            report["excluded_from_core_equality"],
        )

    def test_entity_event_timestamp_difference_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "evidence"
            self._write_all_captures(root)
            candidate = (
                root
                / "02_gui_10x"
                / RESULT_FILES["entity_log"]
            )
            fields, rows = self._read_csv(candidate)
            rows[0]["arrival_seconds"] = "999.000000000"
            self._write_csv(candidate, fields, rows)
            self._refresh_hash(root / "02_gui_10x", candidate.name)
            report = validate_evidence(DEFAULT_PROTOCOL, root)
        self.assertEqual(report["status"], "FAIL")
        differences = report["comparisons"][0]["tables"][1][
            "first_differences"
        ]
        self.assertTrue(
            any(item.get("field") == "arrival_seconds" for item in differences)
        )

    def test_kpi_difference_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "evidence"
            self._write_all_captures(root)
            candidate = (
                root
                / "03_gui_virtual_time"
                / RESULT_FILES["replication_kpis"]
            )
            fields, rows = self._read_csv(candidate)
            rows[0]["total_queue_wait_p95_seconds"] = "8.000000000"
            self._write_csv(candidate, fields, rows)
            self._refresh_hash(root / "03_gui_virtual_time", candidate.name)
            report = validate_evidence(DEFAULT_PROTOCOL, root)
        self.assertEqual(report["status"], "FAIL")
        self.assertTrue(
            any("replication_kpis" in error for error in report["errors"])
        )

    def test_seed_difference_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "evidence"
            self._write_all_captures(root)
            candidate = root / "02_gui_10x" / RESULT_FILES["run_manifest"]
            fields, rows = self._read_csv(candidate)
            rows[0]["arrival_seed"] = "987654321"
            self._write_csv(candidate, fields, rows)
            self._refresh_hash(root / "02_gui_10x", candidate.name)
            report = validate_evidence(DEFAULT_PROTOCOL, root)
        self.assertEqual(report["status"], "FAIL")
        self.assertTrue(any("run_manifest" in error for error in report["errors"]))

    def test_reused_ui_screenshot_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "evidence"
            self._write_all_captures(root)
            source = root / "01_gui_1x" / UI_EVIDENCE_FILE
            target_dir = root / "02_gui_10x"
            (target_dir / UI_EVIDENCE_FILE).write_bytes(source.read_bytes())
            metadata_path = target_dir / CAPTURE_METADATA_FILE
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            metadata["ui_evidence_sha256"] = _sha256(
                target_dir / UI_EVIDENCE_FILE
            )
            metadata_path.write_text(
                json.dumps(metadata) + "\n", encoding="utf-8"
            )
            report = validate_evidence(DEFAULT_PROTOCOL, root)
        self.assertEqual(report["status"], "FAIL")
        self.assertTrue(
            any("screenshot appears reused" in error for error in report["errors"])
        )

    def test_same_source_mtimes_do_not_prove_three_gui_runs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "evidence"
            self._write_all_captures(root)
            first_metadata = json.loads(
                (root / "01_gui_1x" / CAPTURE_METADATA_FILE).read_text(
                    encoding="utf-8"
                )
            )
            second_path = root / "02_gui_10x" / CAPTURE_METADATA_FILE
            second = json.loads(second_path.read_text(encoding="utf-8"))
            second["source_file_mtime_ns"] = first_metadata[
                "source_file_mtime_ns"
            ]
            second_path.write_text(json.dumps(second) + "\n", encoding="utf-8")
            report = validate_evidence(DEFAULT_PROTOCOL, root)
        self.assertEqual(report["status"], "FAIL")
        self.assertTrue(
            any("not strictly increasing" in error for error in report["errors"])
        )

    def test_different_model_commits_fail(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "evidence"
            self._write_capture(root, 0)
            self._write_capture(root, 1, commit="3" * 40)
            self._write_capture(root, 2)
            report = validate_evidence(DEFAULT_PROTOCOL, root)
        self.assertEqual(report["status"], "FAIL")
        self.assertTrue(
            any("different model_git_commit" in error for error in report["errors"])
        )

    def test_stage_requires_new_export_before_next_mode(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            source = base / "source"
            self._write_core(source)
            screenshot1 = base / "one.png"
            screenshot1.write_bytes(PNG_SIGNATURE + b"one")
            root = base / "evidence"
            first = stage_capture(
                run_mode="GUI_1X",
                operator_role_alias="model_owner",
                model_git_commit=MODEL_COMMIT,
                ui_evidence=screenshot1,
                source_dir=source,
                evidence_root=root,
                confirm_finished=True,
            )
            self.assertTrue(first.is_dir())
            screenshot2 = base / "two.png"
            screenshot2.write_bytes(PNG_SIGNATURE + b"two")
            with self.assertRaisesRegex(
                ValueError, "modification times have not advanced"
            ):
                stage_capture(
                    run_mode="GUI_10X",
                    operator_role_alias="model_owner",
                    model_git_commit=MODEL_COMMIT,
                    ui_evidence=screenshot2,
                    source_dir=source,
                    evidence_root=root,
                    confirm_finished=True,
                )

    def test_stage_rejects_out_of_order_mode(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            source = base / "source"
            self._write_core(source)
            screenshot = base / "ten.png"
            screenshot.write_bytes(PNG_SIGNATURE + b"ten")
            with self.assertRaisesRegex(ValueError, "registered order"):
                stage_capture(
                    run_mode="GUI_10X",
                    operator_role_alias="model_owner",
                    model_git_commit=MODEL_COMMIT,
                    ui_evidence=screenshot,
                    source_dir=source,
                    evidence_root=base / "evidence",
                    confirm_finished=True,
                )

    @staticmethod
    def _read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
        with path.open(encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream)
            return list(reader.fieldnames or ()), list(reader)

    @staticmethod
    def _write_csv(
        path: Path, fields: list[str], rows: list[dict[str, str]]
    ) -> None:
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)

    @staticmethod
    def _refresh_hash(run_dir: Path, filename: str) -> None:
        metadata_path = run_dir / CAPTURE_METADATA_FILE
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        metadata["core_file_sha256"][filename] = _sha256(run_dir / filename)
        metadata_path.write_text(json.dumps(metadata) + "\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
