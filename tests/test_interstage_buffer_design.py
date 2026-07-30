from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from src.analysis.interstage_buffer_design import (
    BLOCKING_POLICY,
    BUFFER_LEVELS,
    DEFAULT_REFERENCE_SEED_MANIFEST,
    DEFAULT_SCENARIOS,
    INTERSTAGE_SCENARIO_COLUMNS,
    MODEL_VERSION,
    REGIMES,
    build_interstage_buffer_scenario_rows,
    build_interstage_buffer_seed_rows,
    interstage_scenario_config_sha256,
    load_design,
    study_cells,
    validate_interstage_buffer_design,
)
from src.analysis.validate_operational_contract import (
    SCENARIO_COLUMNS,
)


def read_rows(path: Path) -> tuple[tuple[str, ...], list[dict[str, str]]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return tuple(reader.fieldnames or ()), list(reader)


class InterstageBufferDesignTests(unittest.TestCase):
    def test_frozen_design_validates(self) -> None:
        report = validate_interstage_buffer_design()

        self.assertEqual(report["status"], "PASS", report["errors"])
        self.assertEqual(report["scenario_count"], 8)
        self.assertEqual(report["seed_group_count"], 50)
        self.assertEqual(report["run_count"], 400)
        self.assertEqual(report["model_version"], MODEL_VERSION)
        self.assertTrue(report["old_scenario_schema_unchanged"])
        self.assertTrue(report["runtime_change_required"])

    def test_two_regimes_cross_four_buffer_levels(self) -> None:
        self.assertEqual(
            study_cells(),
            [
                (*regime, buffer_capacity)
                for regime in REGIMES
                for buffer_capacity in BUFFER_LEVELS
            ],
        )
        self.assertEqual(len(study_cells()), 8)

    def test_schema_is_append_only_and_guards_remain_nonbinding(self) -> None:
        self.assertEqual(
            INTERSTAGE_SCENARIO_COLUMNS[:-3],
            SCENARIO_COLUMNS,
        )
        self.assertEqual(
            INTERSTAGE_SCENARIO_COLUMNS[-3:],
            (
                "capacity_regime_id",
                "interstage_buffer_capacity",
                "interstage_blocking_policy",
            ),
        )

        rows = build_interstage_buffer_scenario_rows()
        self.assertEqual(len(rows), 8)
        self.assertEqual(
            {int(row["interstage_buffer_capacity"]) for row in rows},
            set(BUFFER_LEVELS),
        )
        self.assertEqual(
            {row["interstage_blocking_policy"] for row in rows},
            {BLOCKING_POLICY},
        )
        self.assertEqual(
            {row["security_queue_capacity"] for row in rows},
            {"5000"},
        )
        self.assertEqual(
            {row["immigration_queue_capacity"] for row in rows},
            {"5000"},
        )
        self.assertTrue(
            all(
                row["input_status"] == "FROZEN_INTERSTAGE_BUFFER_DESIGN"
                for row in rows
            )
        )
        self.assertTrue(
            all(
                "not measured site capacity" in row["notes"]
                for row in rows
            )
        )

    def test_extended_hash_binds_buffer_and_blocking_policy(self) -> None:
        rows = build_interstage_buffer_scenario_rows()
        hashes = {interstage_scenario_config_sha256(row) for row in rows}
        self.assertEqual(len(hashes), 8)

        row = dict(rows[0])
        original = interstage_scenario_config_sha256(row)
        row["interstage_buffer_capacity"] = "50"
        self.assertNotEqual(
            interstage_scenario_config_sha256(row),
            original,
        )
        row = dict(rows[0])
        row["interstage_blocking_policy"] = "DROP_WHEN_FULL"
        self.assertNotEqual(
            interstage_scenario_config_sha256(row),
            original,
        )

    def test_seed_manifest_reuses_exact_base_tuples(self) -> None:
        generated = build_interstage_buffer_seed_rows()
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
                with self.subTest(
                    replication=row["replication_id"],
                    field=field,
                ):
                    self.assertEqual(row[field], registered[field])
            self.assertEqual(len(row["scenario_ids"].split("|")), 8)

    def test_scenario_mutation_fails_closed(self) -> None:
        fields, rows = read_rows(DEFAULT_SCENARIOS)
        rows[0]["interstage_blocking_policy"] = "DROP_WHEN_FULL"

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "interstage_buffer_scenarios.csv"
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=fields,
                    lineterminator="\n",
                )
                writer.writeheader()
                writer.writerows(rows)
            report = validate_interstage_buffer_design(
                scenarios_path=path,
            )

        self.assertEqual(report["status"], "FAIL")
        self.assertTrue(
            any(
                "differ from deterministic design" in error
                for error in report["errors"]
            )
        )

    def test_measured_capacity_claim_fails_closed(self) -> None:
        design = load_design()
        design["interstage_buffer_grid"]["measured_site_capacity"] = True

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "interstage_buffer_study.json"
            path.write_text(
                json.dumps(design, indent=2) + "\n",
                encoding="utf-8",
            )
            report = validate_interstage_buffer_design(design_path=path)

        self.assertEqual(report["status"], "FAIL")
        self.assertIn(
            "buffer levels must remain unmeasured sensitivities",
            report["errors"],
        )

    def test_design_declares_runtime_boundary_and_no_calibration(self) -> None:
        design = load_design()
        self.assertEqual(design["model_version"], MODEL_VERSION)
        self.assertEqual(
            design["blocking_contract"]["policy_id"],
            BLOCKING_POLICY,
        )
        self.assertEqual(
            design["blocking_contract"]["implementation_status"],
            "REQUIRES_SEPARATELY_REVIEWED_ANYLOGIC_RUNTIME_CHANGE",
        )
        self.assertFalse(
            design["interstage_buffer_grid"]["measured_site_capacity"]
        )
        self.assertFalse(
            design["calibration_boundary"]["physical_layout_calibrated"]
        )
        self.assertFalse(design["execution"]["adaptive_extension_allowed"])

    def test_runtime_output_contract_separates_replay_and_blocking_metrics(
        self,
    ) -> None:
        design = load_design()
        output_contract = design["runtime_output_contract"]
        replay_digest = output_contract["exact_replay_digest"]
        self.assertEqual(
            replay_digest["field"],
            "normalized_event_payload_sha256",
        )
        self.assertIn(
            "not the raw event-ledger",
            replay_digest["comparison_rule"],
        )

        metrics = output_contract["blocking_metrics"]
        self.assertEqual(
            metrics["security_blocked_resource_fraction"]["formula"],
            "security_blocked_resource_seconds / "
            "(security_capacity * last_exit_seconds)",
        )
        self.assertEqual(
            metrics["security_blocked_share_of_occupied"]["formula"],
            "security_blocked_resource_seconds / "
            "(security_busy_seconds + security_blocked_resource_seconds)",
        )
        self.assertIn(
            "security_blocked_share_of_occupied",
            design["analysis"]["supporting_metrics"],
        )


if __name__ == "__main__":
    unittest.main()
