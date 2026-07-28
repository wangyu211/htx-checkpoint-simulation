from __future__ import annotations

import csv
import shutil
import tempfile
import unittest
from pathlib import Path

from src.analysis.validate_anylogic_hpp_arrival import (
    EXPECTED_ASSUMPTION,
    EXPECTED_COUNT,
    EXPECTED_CUTOFF_SECONDS,
    EXPECTED_EVIDENCE,
    EXPECTED_RATE_PER_SECOND,
    LEDGER_COLUMNS,
    MANIFEST_COLUMNS,
    SUMMARY_COLUMNS,
    validate_hpp_arrival,
)


def write_csv(
    path: Path,
    columns: tuple[str, ...],
    rows: list[dict[str, str]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def base_lineage() -> dict[str, str]:
    return {
        "schema_version": "1.0",
        "experiment_role": "DEMAND_MECHANISM_VERIFICATION",
        "readiness_scope": "ARRIVAL_ONLY",
        "source_config_id": "BASELINE_LOCAL_WINDOW_HPP",
        "input_sample_id": "HPP_SYNTHETIC_A",
        "replication_id": "1",
        "arrival_seed": "2026072710",
    }


def write_valid_outputs(
    root: Path,
    arrivals: tuple[float, ...] = (0.25, 1.5, 2.75),
    *,
    manifest_overrides: dict[str, str] | None = None,
    summary_overrides: dict[str, str] | None = None,
    ledger_overrides: dict[int, dict[str, str]] | None = None,
    manifest_columns: tuple[str, ...] = MANIFEST_COLUMNS,
) -> None:
    count = len(arrivals)
    expected_count = f"{EXPECTED_COUNT:.9f}"
    manifest = {
        **base_lineage(),
        "arrival_evidence_id": EXPECTED_EVIDENCE,
        "arrival_assumption": EXPECTED_ASSUMPTION,
        "arrival_rate_per_second": f"{EXPECTED_RATE_PER_SECOND:.9f}",
        "arrival_cutoff_seconds": f"{EXPECTED_CUTOFF_SECONDS:.9f}",
        "expected_count": expected_count,
        "realized_count": str(count),
        "guard_limit": "49000",
        "guard_hit": "false",
        "engine_version": "AnyLogic PLE 8.9.9.202607020720",
    }
    manifest.update(manifest_overrides or {})

    ledger_rows: list[dict[str, str]] = []
    for position, arrival in enumerate(arrivals, start=1):
        row = {
            **base_lineage(),
            "sequence": str(position),
            "arrival_time": f"{arrival:.9f}",
        }
        row.update((ledger_overrides or {}).get(position, {}))
        ledger_rows.append(row)

    summary = {
        **base_lineage(),
        "arrival_rate_per_second": f"{EXPECTED_RATE_PER_SECOND:.9f}",
        "arrival_cutoff_seconds": f"{EXPECTED_CUTOFF_SECONDS:.9f}",
        "expected_count": expected_count,
        "realized_count": str(count),
        "source_count": str(count),
        "sink_count": str(count),
        "guard_hit": "false",
    }
    summary.update(summary_overrides or {})

    write_csv(root / "run_manifest.csv", manifest_columns, [manifest])
    write_csv(root / "arrival_ledger.csv", LEDGER_COLUMNS, ledger_rows)
    write_csv(root / "run_summary.csv", SUMMARY_COLUMNS, [summary])


class AnyLogicHPPArrivalValidatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.results_dir = Path(self.temporary_directory.name) / "results"

    def test_non_34_realization_passes_without_forcing_observed_count(
        self,
    ) -> None:
        write_valid_outputs(self.results_dir)

        report = validate_hpp_arrival(self.results_dir)

        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["realized_count"], 3)
        self.assertAlmostEqual(report["expected_count"], EXPECTED_COUNT)
        self.assertNotEqual(report["expected_count"], 34.0)
        self.assertEqual(report["errors"], [])

    def test_exact_schema_rejects_extra_or_reordered_columns(self) -> None:
        columns = (*MANIFEST_COLUMNS, "unexpected")
        write_valid_outputs(self.results_dir, manifest_columns=columns)

        report = validate_hpp_arrival(self.results_dir)

        self.assertEqual(report["status"], "FAIL")
        self.assertTrue(
            any(
                "run_manifest.csv: schema mismatch" in error
                for error in report["errors"]
            )
        )

    def test_lineage_and_arrival_only_scope_are_enforced(self) -> None:
        write_valid_outputs(
            self.results_dir,
            manifest_overrides={
                "arrival_assumption": "UNDECLARED_PROCESS",
            },
            summary_overrides={
                "readiness_scope": "OPERATIONAL_BASELINE",
            },
            ledger_overrides={
                1: {"experiment_role": "ASSESSMENT_STUDY"},
            },
        )

        report = validate_hpp_arrival(self.results_dir)

        self.assertEqual(report["status"], "FAIL")
        errors = "\n".join(report["errors"])
        self.assertIn("arrival_assumption", errors)
        self.assertIn("readiness_scope", errors)
        self.assertIn("experiment_role", errors)

    def test_expected_count_must_equal_lambda_times_cutoff(self) -> None:
        write_valid_outputs(
            self.results_dir,
            manifest_overrides={"expected_count": "34.000000000"},
            summary_overrides={"expected_count": "34.000000000"},
        )

        report = validate_hpp_arrival(self.results_dir)

        self.assertEqual(report["status"], "FAIL")
        self.assertGreaterEqual(
            sum("expected_count" in error for error in report["errors"]),
            2,
        )

    def test_arrivals_must_be_sequenced_and_strictly_inside_half_open_window(
        self,
    ) -> None:
        write_valid_outputs(
            self.results_dir,
            arrivals=(0.5, 0.5, EXPECTED_CUTOFF_SECONDS),
            ledger_overrides={2: {"sequence": "3"}},
        )

        report = validate_hpp_arrival(self.results_dir)

        self.assertEqual(report["status"], "FAIL")
        errors = "\n".join(report["errors"])
        self.assertIn("timestamps must be strictly increasing", errors)
        self.assertIn("must be inside [0, T)", errors)
        self.assertIn("sequence: expected 2", errors)

    def test_counts_and_guard_state_must_conserve_the_ledger(self) -> None:
        write_valid_outputs(
            self.results_dir,
            manifest_overrides={
                "realized_count": "4",
                "guard_hit": "true",
            },
            summary_overrides={
                "source_count": "2",
                "guard_hit": "true",
            },
        )

        report = validate_hpp_arrival(self.results_dir)

        self.assertEqual(report["status"], "FAIL")
        errors = "\n".join(report["errors"])
        self.assertIn("guard_hit", errors)
        self.assertIn("conserved ledger count 3, got 4", errors)
        self.assertIn("conserved ledger count 3, got 2", errors)

    def test_guard_limit_must_remain_below_ple_limit_and_above_exposure(
        self,
    ) -> None:
        write_valid_outputs(
            self.results_dir,
            manifest_overrides={"guard_limit": "50000"},
        )

        report = validate_hpp_arrival(self.results_dir)

        self.assertEqual(report["status"], "FAIL")
        self.assertTrue(
            any("must be in (0, 50000)" in error for error in report["errors"])
        )

    def test_optional_reference_requires_byte_identical_outputs(self) -> None:
        write_valid_outputs(self.results_dir)
        reference_dir = Path(self.temporary_directory.name) / "reference"
        shutil.copytree(self.results_dir, reference_dir)

        identical = validate_hpp_arrival(
            self.results_dir,
            reference_dir=reference_dir,
        )
        self.assertEqual(identical["status"], "PASS")
        self.assertTrue(identical["reproducibility"]["byte_identical"])

        summary = reference_dir / "run_summary.csv"
        summary.write_text(
            summary.read_text(encoding="utf-8") + "\n",
            encoding="utf-8",
        )
        changed = validate_hpp_arrival(
            self.results_dir,
            reference_dir=reference_dir,
        )
        self.assertEqual(changed["status"], "FAIL")
        self.assertFalse(changed["reproducibility"]["byte_identical"])
        self.assertTrue(
            any("not byte-identical" in error for error in changed["errors"])
        )


if __name__ == "__main__":
    unittest.main()
