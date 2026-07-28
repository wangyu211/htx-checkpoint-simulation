from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from src.analysis.consolidate_operational_results import (
    consolidate_operational_results,
)
from src.analysis.validate_operational_results import (
    DEFAULT_SCHEMA_REGISTRY,
    RESULT_FILES,
    load_result_schemas,
)


class OperationalConsolidationTests(unittest.TestCase):
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
                "scenario_id": scenario,
                "input_sample_id": sample,
                "replication_id": str(replication),
            }
        )
        if table == "entity_log":
            row["traveller_id"] = f"T{replication:03d}"
        return row

    def _write_leaf(
        self,
        source: Path,
        scenario: str,
        sample: str,
        replication: int,
    ) -> Path:
        leaf = (
            source
            / scenario
            / sample
            / f"replication_{replication:03d}"
        )
        leaf.mkdir(parents=True)
        for table, filename in RESULT_FILES.items():
            with (leaf / filename).open(
                "w", encoding="utf-8", newline=""
            ) as stream:
                writer = csv.DictWriter(
                    stream,
                    fieldnames=self.fields[table],
                    lineterminator="\n",
                )
                writer.writeheader()
                writer.writerow(
                    self._row(table, scenario, sample, replication)
                )
        return leaf

    def test_nested_leaves_are_merged_in_deterministic_run_order(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            output = root / "output"
            self._write_leaf(source, "SCENARIO_B", "SAMPLE", 2)
            self._write_leaf(source, "SCENARIO_A", "SAMPLE", 1)

            report = consolidate_operational_results(source, output)

            self.assertEqual(report["run_count"], 2)
            self.assertEqual(report["entity_count"], 2)
            for table, filename in RESULT_FILES.items():
                with (output / filename).open(
                    encoding="utf-8", newline=""
                ) as stream:
                    reader = csv.DictReader(stream)
                    self.assertEqual(reader.fieldnames, self.fields[table])
                    rows = list(reader)
                self.assertEqual(
                    [row["scenario_id"] for row in rows],
                    ["SCENARIO_A", "SCENARIO_B"],
                )

    def test_duplicate_run_keys_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            output = root / "output"
            first = self._write_leaf(source, "SCENARIO_A", "SAMPLE", 1)
            duplicate = (
                source
                / "nested"
                / "SCENARIO_A"
                / "SAMPLE"
                / "replication_001"
            )
            duplicate.mkdir(parents=True)
            for filename in RESULT_FILES.values():
                (duplicate / filename).write_bytes((first / filename).read_bytes())

            with self.assertRaisesRegex(ValueError, "duplicate run key"):
                consolidate_operational_results(source, output)

    def test_directory_lineage_must_match_the_csv_key(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            output = root / "output"
            leaf = self._write_leaf(source, "SCENARIO_A", "SAMPLE", 1)
            manifest_path = leaf / RESULT_FILES["run_manifest"]
            with manifest_path.open(encoding="utf-8", newline="") as stream:
                reader = csv.DictReader(stream)
                fields = list(reader.fieldnames or [])
                row = next(reader)
            row["scenario_id"] = "WRONG_SCENARIO"
            with manifest_path.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(
                    stream, fieldnames=fields, lineterminator="\n"
                )
                writer.writeheader()
                writer.writerow(row)

            with self.assertRaisesRegex(
                ValueError,
                "manifest and KPI run keys differ",
            ):
                consolidate_operational_results(source, output)


if __name__ == "__main__":
    unittest.main()
