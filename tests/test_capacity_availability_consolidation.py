from __future__ import annotations

import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from src.analysis.consolidate_capacity_availability_results import (
    consolidate_capacity_availability_results,
)
from src.analysis.validate_operational_results import (
    DEFAULT_SCHEMA_REGISTRY,
    RESULT_FILES,
    load_result_schemas,
)


REFERENCE = "REFERENCE"
REDUCTIONS = ("SECURITY_DOWN", "JOINT_DOWN")
SAMPLES = ("LOW_SAMPLE", "BASE_SAMPLE")
REPLICATIONS = (1, 2)


class CapacityAvailabilityConsolidationTests(unittest.TestCase):
    def setUp(self) -> None:
        schemas = load_result_schemas(DEFAULT_SCHEMA_REGISTRY)
        self.fields = {
            table: [item["field_name"] for item in schemas[table]]
            for table in RESULT_FILES
        }
        self.types = {
            table: {
                item["field_name"]: item["data_type"]
                for item in schemas[table]
            }
            for table in RESULT_FILES
        }

    @staticmethod
    def _sha256(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def _row(
        self,
        table: str,
        scenario: str,
        sample: str,
        replication: int,
    ) -> dict[str, str]:
        defaults = {
            "string": "X",
            "integer": "0",
            "number": "0",
            "boolean": "false",
        }
        row = {
            field: defaults[self.types[table][field]]
            for field in self.fields[table]
        }
        row.update(
            {
                "config_id": f"CONFIG_{scenario}_{sample}",
                "config_sha256": hashlib.sha256(
                    f"{scenario}|{sample}".encode()
                ).hexdigest(),
                "model_version": "TEST_MODEL",
                "scenario_id": scenario,
                "input_sample_id": sample,
                "replication_id": str(replication),
            }
        )
        if table == "run_manifest":
            row["reference_scenario_id"] = REFERENCE
            row["run_status"] = "COMPLETE"
        elif table == "replication_kpis":
            row["conservation_pass"] = "true"
            row["run_status"] = "COMPLETE"
        elif table == "entity_log":
            row["traveller_id"] = f"T{replication:03d}"
        return row

    def _write_table(
        self,
        path: Path,
        table: str,
        rows: list[dict[str, str]],
    ) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(
                stream,
                fieldnames=self.fields[table],
                extrasaction="raise",
                lineterminator="\n",
            )
            writer.writeheader()
            writer.writerows(rows)

    def _write_reference_source(
        self,
        source_dir: Path,
        audit_path: Path,
    ) -> None:
        counts: dict[str, int] = {}
        for table, filename in RESULT_FILES.items():
            rows = [
                self._row(table, REFERENCE, sample, replication)
                for sample in SAMPLES
                for replication in REPLICATIONS
            ]
            self._write_table(source_dir / filename, table, rows)
            counts[table] = len(rows)
        audit = {
            "status": "PASS",
            "run_count": counts["run_manifest"],
            "source_entity_log": {
                "row_count": counts["entity_log"],
                "sha256": self._sha256(
                    source_dir / RESULT_FILES["entity_log"]
                ),
            },
            "tracked_artifacts": {
                RESULT_FILES["run_manifest"]: self._sha256(
                    source_dir / RESULT_FILES["run_manifest"]
                ),
                RESULT_FILES["replication_kpis"]: self._sha256(
                    source_dir / RESULT_FILES["replication_kpis"]
                ),
            },
        }
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        audit_path.write_text(
            json.dumps(audit, indent=2) + "\n", encoding="utf-8"
        )

    def _write_reduction_leaf(
        self,
        source_root: Path,
        scenario: str,
        sample: str,
        replication: int,
        *,
        directory_scenario: str | None = None,
    ) -> Path:
        leaf = (
            source_root
            / (directory_scenario or scenario)
            / sample
            / f"replication_{replication:03d}"
        )
        for table, filename in RESULT_FILES.items():
            self._write_table(
                leaf / filename,
                table,
                [self._row(table, scenario, sample, replication)],
            )
        return leaf

    def _write_complete_reduction_source(self, source_root: Path) -> None:
        for scenario in REDUCTIONS:
            for sample in SAMPLES:
                for replication in REPLICATIONS:
                    self._write_reduction_leaf(
                        source_root, scenario, sample, replication
                    )

    def _run(
        self,
        root: Path,
        *,
        source_root: Path | None = None,
        output_dir: Path | None = None,
    ) -> dict[str, object]:
        reference_dir = root / "part1_reference"
        audit_path = root / "audit" / "audit_manifest.json"
        reductions = source_root or root / "part2_raw"
        output = output_dir or root / "part2_consolidated"
        self._write_reference_source(reference_dir, audit_path)
        if source_root is None:
            self._write_complete_reduction_source(reductions)
        return consolidate_capacity_availability_results(
            reductions,
            reference_dir,
            output,
            audit_manifest_path=audit_path,
            reference_scenario_id=REFERENCE,
            reduction_scenario_ids=REDUCTIONS,
            input_sample_ids=SAMPLES,
            replication_ids=REPLICATIONS,
        )

    def test_merges_audited_reference_and_complete_reduction_design(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = self._run(root)
            output = root / "part2_consolidated"

            self.assertEqual(report["status"], "PASS")
            self.assertEqual(report["coverage"]["reference_run_count"], 4)
            self.assertEqual(report["coverage"]["new_reduction_run_count"], 8)
            self.assertEqual(report["coverage"]["analysis_run_count"], 12)
            self.assertEqual(
                report["sources"]["immutable_part1_reference"][
                    "hash_verification_status"
                ],
                "PASS",
            )
            for table, filename in RESULT_FILES.items():
                with (output / filename).open(
                    encoding="utf-8", newline=""
                ) as stream:
                    reader = csv.DictReader(stream)
                    self.assertEqual(reader.fieldnames, self.fields[table])
                    rows = list(reader)
                expected_count = 12
                self.assertEqual(len(rows), expected_count)
                self.assertEqual(
                    report["outputs"][filename]["row_count"],
                    expected_count,
                )
            manifest = json.loads(
                (output / "consolidation_manifest.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(manifest["lineage_status"], "PASS")
            self.assertEqual(
                manifest["sources"]["part2_reduced_capacity"]["leaf_count"],
                8,
            )

    def test_reference_hash_mismatch_is_rejected_before_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reference_dir = root / "part1_reference"
            audit_path = root / "audit" / "audit_manifest.json"
            reductions = root / "part2_raw"
            output = root / "part2_consolidated"
            self._write_reference_source(reference_dir, audit_path)
            self._write_complete_reduction_source(reductions)
            with (
                reference_dir / RESULT_FILES["run_manifest"]
            ).open("a", encoding="utf-8") as stream:
                stream.write("\n")

            with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
                consolidate_capacity_availability_results(
                    reductions,
                    reference_dir,
                    output,
                    audit_manifest_path=audit_path,
                    reference_scenario_id=REFERENCE,
                    reduction_scenario_ids=REDUCTIONS,
                    input_sample_ids=SAMPLES,
                    replication_ids=REPLICATIONS,
                )
            self.assertFalse(output.exists())

    def test_missing_reduction_run_key_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "part2_raw"
            for scenario in REDUCTIONS:
                for sample in SAMPLES:
                    for replication in REPLICATIONS:
                        if (scenario, sample, replication) != (
                            REDUCTIONS[-1],
                            SAMPLES[-1],
                            REPLICATIONS[-1],
                        ):
                            self._write_reduction_leaf(
                                source, scenario, sample, replication
                            )

            with self.assertRaisesRegex(ValueError, "missing run keys"):
                self._run(root, source_root=source)

    def test_unexpected_reduction_run_key_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "part2_raw"
            self._write_complete_reduction_source(source)
            self._write_reduction_leaf(
                source, "UNREGISTERED_ARM", SAMPLES[0], REPLICATIONS[0]
            )

            with self.assertRaisesRegex(ValueError, "unexpected run key"):
                self._run(root, source_root=source)

    def test_duplicate_reduction_run_key_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "part2_raw"
            self._write_complete_reduction_source(source)
            original = (
                source
                / REDUCTIONS[0]
                / SAMPLES[0]
                / "replication_001"
            )
            duplicate = (
                source
                / "duplicate_branch"
                / REDUCTIONS[0]
                / SAMPLES[0]
                / "replication_001"
            )
            for filename in RESULT_FILES.values():
                destination = duplicate / filename
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes((original / filename).read_bytes())

            with self.assertRaisesRegex(ValueError, "duplicate run key"):
                self._run(root, source_root=source)

    def test_cross_table_configuration_lineage_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "part2_raw"
            self._write_complete_reduction_source(source)
            kpi_path = (
                source
                / REDUCTIONS[0]
                / SAMPLES[0]
                / "replication_001"
                / RESULT_FILES["replication_kpis"]
            )
            with kpi_path.open(encoding="utf-8", newline="") as stream:
                reader = csv.DictReader(stream)
                fields = list(reader.fieldnames or [])
                row = next(reader)
            row["config_sha256"] = "0" * 64
            with kpi_path.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(
                    stream, fieldnames=fields, lineterminator="\n"
                )
                writer.writeheader()
                writer.writerow(row)

            with self.assertRaisesRegex(
                ValueError, "KPI config_sha256 does not match"
            ):
                self._run(root, source_root=source)

    def test_cross_scenario_seed_lineage_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "part2_raw"
            self._write_complete_reduction_source(source)
            manifest_path = (
                source
                / REDUCTIONS[0]
                / SAMPLES[0]
                / "replication_001"
                / RESULT_FILES["run_manifest"]
            )
            with manifest_path.open(encoding="utf-8", newline="") as stream:
                reader = csv.DictReader(stream)
                fields = list(reader.fieldnames or [])
                row = next(reader)
            row["arrival_seed"] = "999"
            with manifest_path.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(
                    stream, fieldnames=fields, lineterminator="\n"
                )
                writer.writeheader()
                writer.writerow(row)

            with self.assertRaisesRegex(
                ValueError, "Cross-scenario seed lineage mismatch"
            ):
                self._run(root, source_root=source)

    def test_part1_source_directory_cannot_be_an_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reference_dir = root / "part1_reference"
            audit_path = root / "audit" / "audit_manifest.json"
            reductions = root / "part2_raw"
            self._write_reference_source(reference_dir, audit_path)
            self._write_complete_reduction_source(reductions)

            with self.assertRaisesRegex(
                ValueError, "Refusing Part 2 output"
            ):
                consolidate_capacity_availability_results(
                    reductions,
                    reference_dir,
                    reference_dir,
                    audit_manifest_path=audit_path,
                    reference_scenario_id=REFERENCE,
                    reduction_scenario_ids=REDUCTIONS,
                    input_sample_ids=SAMPLES,
                    replication_ids=REPLICATIONS,
                )


if __name__ == "__main__":
    unittest.main()
