"""Consolidate the registered 400-run interstage-buffer AnyLogic batch.

Each AnyLogic run must write exactly one ``replication_kpis.csv`` below:

``results/raw/interstage_buffer/*/*/replication_*/``

The consolidator is fail-closed.  It validates the frozen design, exact file
and run-key coverage, registered scenario hashes and seeds, CRN input digests,
zero-loss conservation, B100/B5000 replay, and the negative-control
equivalence gate before publishing the single CSV consumed by
``analyse_interstage_buffer``.
"""

from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path
from typing import Sequence

from src.analysis.analyse_interstage_buffer import (
    DEFAULT_INPUT_CSV,
    EXPECTED_RUN_COUNT,
    REPLICATION_FIELDS,
    _sha256,
    _write_csv,
    _write_json,
    build_crn_alignment_report,
    build_exact_replay_report,
    build_negative_control_report,
    build_registered_contract_report,
    portable_path,
    validate_imported_rows,
)
from src.analysis.interstage_buffer_design import (
    load_interstage_buffer_scenario_rows,
    load_interstage_buffer_seed_rows,
    validate_interstage_buffer_design,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE_ROOT = (
    PROJECT_ROOT / "results" / "raw" / "interstage_buffer"
)
DEFAULT_MANIFEST = DEFAULT_INPUT_CSV.parent / "consolidation_manifest.json"
DEFAULT_ARTIFACT_MANIFEST = (
    DEFAULT_INPUT_CSV.parent / "raw_artifact_manifest.csv"
)
RUN_FILE_PATTERN = "*/*/replication_*/replication_kpis.csv"
REPLICATION_DIRECTORY = re.compile(r"^replication_(\d+)$")
ARTIFACT_FIELDS = (
    "scenario_id",
    "replication_id",
    "source_path",
    "source_sha256",
)


def _read_one_run(path: Path) -> tuple[dict[str, str], tuple[str, ...]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = tuple(reader.fieldnames or ())
        if not fields:
            raise ValueError(f"{path}: missing CSV header")
        if len(set(fields)) != len(fields):
            raise ValueError(f"{path}: duplicate CSV field names")
        missing = [field for field in REPLICATION_FIELDS if field not in fields]
        if missing:
            raise ValueError(
                f"{path}: missing required fields: {', '.join(missing)}"
            )
        rows = list(reader)
    if len(rows) != 1:
        raise ValueError(
            f"{path}: each run file must contain exactly one KPI row; "
            f"found {len(rows)}"
        )
    return rows[0], fields


def _failure_manifest(
    *,
    source_root: Path,
    output_csv: Path,
    error: str,
) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "contract": "TASK3_INTERSTAGE_BUFFER_CONSOLIDATION_V1",
        "status": "FAIL",
        "source_root": portable_path(source_root),
        "output_csv": portable_path(output_csv),
        "error": error,
    }


def consolidate_interstage_buffer_results(
    source_root: Path = DEFAULT_SOURCE_ROOT,
    output_csv: Path = DEFAULT_INPUT_CSV,
    manifest_path: Path | None = None,
    artifact_manifest_path: Path | None = None,
) -> dict[str, object]:
    """Strictly merge and validate all registered per-run KPI files."""

    manifest_path = manifest_path or output_csv.parent / DEFAULT_MANIFEST.name
    artifact_manifest_path = (
        artifact_manifest_path
        or output_csv.parent / DEFAULT_ARTIFACT_MANIFEST.name
    )
    try:
        design_validation = validate_interstage_buffer_design()
        if design_validation["status"] != "PASS":
            raise ValueError(
                "frozen interstage-buffer design failed validation: "
                + "; ".join(str(value) for value in design_validation["errors"])
            )
        if not source_root.is_dir():
            raise FileNotFoundError(
                f"interstage-buffer raw results root not found: {source_root}"
            )
        leaves = sorted(source_root.glob(RUN_FILE_PATTERN))
        if len(leaves) != EXPECTED_RUN_COUNT:
            raise ValueError(
                "expected exactly "
                f"{EXPECTED_RUN_COUNT} per-run KPI files matching "
                f"{RUN_FILE_PATTERN}; found {len(leaves)}"
            )

        raw_rows: list[dict[str, str]] = []
        artifacts: list[dict[str, object]] = []
        for path in leaves:
            match = REPLICATION_DIRECTORY.fullmatch(path.parent.name)
            if match is None:
                raise ValueError(
                    f"{path}: parent directory must be replication_<id>"
                )
            row, _ = _read_one_run(path)
            directory_replication = int(match.group(1))
            try:
                row_replication = int(row["replication_id"])
            except ValueError as error:
                raise ValueError(
                    f"{path}: replication_id must be an integer"
                ) from error
            if directory_replication != row_replication:
                raise ValueError(
                    f"{path}: directory replication {directory_replication} "
                    f"does not match row replication {row_replication}"
                )
            raw_rows.append(row)
            artifacts.append(
                {
                    "scenario_id": row["scenario_id"],
                    "replication_id": row_replication,
                    "source_path": portable_path(path),
                    "source_sha256": _sha256(path),
                }
            )

        rows, validation = validate_imported_rows(raw_rows)
        registered = build_registered_contract_report(
            rows,
            load_interstage_buffer_scenario_rows(),
            load_interstage_buffer_seed_rows(),
        )
        crn = build_crn_alignment_report(rows)
        replay = build_exact_replay_report(rows)
        negative_control, _ = build_negative_control_report(rows)
        reports = {
            "import_validation": validation,
            "registered_contract": registered,
            "crn_alignment": crn,
            "exact_replay": replay,
            "negative_control_invariance": negative_control,
        }
        failed = [
            (name, report)
            for name, report in reports.items()
            if report["status"] != "PASS"
        ]
        if failed:
            details = []
            for name, report in failed:
                report_errors = report.get("errors", [])
                details.append(
                    f"{name}: "
                    + "; ".join(str(value) for value in report_errors[:5])
                )
            raise ValueError("validation gate failed: " + " | ".join(details))
    except (OSError, ValueError) as error:
        failure = _failure_manifest(
            source_root=source_root,
            output_csv=output_csv,
            error=str(error),
        )
        _write_json(manifest_path, failure)
        raise

    _write_csv(output_csv, rows, REPLICATION_FIELDS)
    _write_csv(
        artifact_manifest_path,
        sorted(
            artifacts,
            key=lambda row: (
                str(row["scenario_id"]),
                int(row["replication_id"]),
            ),
        ),
        ARTIFACT_FIELDS,
    )
    manifest = {
        "schema_version": "1.0",
        "contract": "TASK3_INTERSTAGE_BUFFER_CONSOLIDATION_V1",
        "status": "PASS",
        "source_root": portable_path(source_root),
        "source_pattern": RUN_FILE_PATTERN,
        "source_file_count": len(leaves),
        "consolidated_row_count": len(rows),
        "output_csv": portable_path(output_csv),
        "output_sha256": _sha256(output_csv),
        "raw_artifact_manifest": portable_path(artifact_manifest_path),
        "raw_artifact_manifest_sha256": _sha256(artifact_manifest_path),
        "gates": {
            name: report["status"] for name, report in reports.items()
        },
        "claim_boundary": (
            "CONDITIONAL_FINITE_BUFFER_SENSITIVITY_NOT_SITE_FORECAST"
        ),
    }
    _write_json(manifest_path, manifest)
    return manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-root",
        type=Path,
        default=DEFAULT_SOURCE_ROOT,
        help="Root containing hierarchical per-run AnyLogic outputs.",
    )
    parser.add_argument(
        "--output-csv",
        type=Path,
        default=DEFAULT_INPUT_CSV,
        help="Consolidated 400-row replication-level CSV.",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help="Optional consolidation-manifest path.",
    )
    parser.add_argument(
        "--artifact-manifest",
        type=Path,
        default=None,
        help="Optional raw-artifact-manifest path.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    manifest = consolidate_interstage_buffer_results(
        args.source_root,
        args.output_csv,
        args.manifest,
        args.artifact_manifest,
    )
    print(
        "Consolidated "
        f"{manifest['source_file_count']} interstage-buffer run files -> "
        f"{args.output_csv}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
