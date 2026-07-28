"""Validate the deterministic AnyLogic two-stage mechanism oracle.

This is a synthetic verification contract, not an operational baseline. It
checks the exact input ledger, both service stages, cutoff state, full drain,
lineage, schemas, and summary metrics emitted by ``TwoStageDeterministic``.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
from typing import Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RESULTS_DIR = (
    PROJECT_ROOT / "results" / "raw" / "anylogic_two_stage_verification"
)
DEFAULT_REPORT = (
    PROJECT_ROOT
    / "results"
    / "intermediate"
    / "anylogic_two_stage_verification"
    / "verification.json"
)

EXPECTED_ROLE = "SYNTHETIC_MECHANISM_VERIFICATION"
EXPECTED_SCENARIO = "VERIFY_2STAGE_C1"
EXPECTED_SAMPLE = "DETERMINISTIC_LEDGER_A"
EXPECTED_REPLICATION = "1"
EXPECTED_SEED = "fixed_oracle:2026072709"
EXPECTED_ARRIVALS = (0.0, 0.5, 1.0, 1.5, 2.5, 3.5)
EXPECTED_SECURITY_STARTS = (0.0, 2.0, 4.0, 6.0, 8.0, 10.0)
EXPECTED_SECURITY_ENDS = (2.0, 4.0, 6.0, 8.0, 10.0, 12.0)
EXPECTED_IMMIGRATION_STARTS = (2.0, 5.0, 8.0, 11.0, 14.0, 17.0)
EXPECTED_EXITS = (5.0, 8.0, 11.0, 14.0, 17.0, 20.0)

MANIFEST_COLUMNS = (
    "schema_version",
    "verification_contract_hash",
    "model_version",
    "experiment_role",
    "scenario_id",
    "input_sample_id",
    "replication_id",
    "stream_seed_ids",
    "start_state",
    "arrival_cutoff",
    "drain_end",
    "engine_version",
)

ENTITY_COLUMNS = (
    "schema_version",
    "experiment_role",
    "scenario_id",
    "input_sample_id",
    "replication_id",
    "stream_seed_ids",
    "traveller_id",
    "arrival",
    "security_queue_join",
    "security_start",
    "security_end",
    "immigration_queue_join",
    "immigration_lane",
    "immigration_start",
    "immigration_primary_end",
    "additional_check_flag",
    "additional_check_end",
    "technology_flag",
    "exit",
    "security_resource_id",
    "immigration_resource_id",
    "security_service_demand",
    "immigration_service_demand",
)

SUMMARY_COLUMNS = (
    "schema_version",
    "experiment_role",
    "scenario_id",
    "input_sample_id",
    "replication_id",
    "stream_seed_ids",
    "arrivals",
    "completed_at_cutoff",
    "security_queue_at_cutoff",
    "security_in_service_at_cutoff",
    "immigration_queue_at_cutoff",
    "immigration_in_service_at_cutoff",
    "wip_at_cutoff",
    "completed_after_drain",
    "security_wait_mean",
    "security_wait_p95",
    "immigration_wait_mean",
    "immigration_wait_p95",
    "total_queue_wait_mean",
    "total_queue_wait_p95",
    "system_time_mean",
    "system_time_p95",
    "cutoff_backlog",
    "cohort_clear_time_after_cutoff",
)


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    if not path.is_file():
        raise FileNotFoundError(path)
    with path.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames is None:
            raise ValueError(f"{path}: missing header")
        return reader.fieldnames, list(reader)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_exact_schema(
    path: Path,
    actual: Sequence[str],
    expected: Sequence[str],
    errors: list[str],
) -> None:
    if tuple(actual) != tuple(expected):
        errors.append(
            f"{path.name}: schema mismatch; expected {list(expected)}, "
            f"found {list(actual)}"
        )


def require_text(
    row: dict[str, str],
    field: str,
    expected: str,
    label: str,
    errors: list[str],
) -> None:
    if row.get(field) != expected:
        errors.append(
            f"{label}:{field}: expected {expected!r}, got {row.get(field)!r}"
        )


def require_float(
    row: dict[str, str],
    field: str,
    expected: float,
    label: str,
    errors: list[str],
    tolerance: float = 1e-9,
) -> None:
    raw = row.get(field, "")
    try:
        actual = float(raw)
    except (TypeError, ValueError):
        errors.append(f"{label}:{field}: expected number, got {raw!r}")
        return
    if not math.isfinite(actual) or abs(actual - expected) > tolerance:
        errors.append(
            f"{label}:{field}: expected {expected:.9f}, got {raw!r}"
        )


def require_lineage(
    row: dict[str, str],
    label: str,
    errors: list[str],
) -> None:
    for field, expected in (
        ("experiment_role", EXPECTED_ROLE),
        ("scenario_id", EXPECTED_SCENARIO),
        ("input_sample_id", EXPECTED_SAMPLE),
        ("replication_id", EXPECTED_REPLICATION),
        ("stream_seed_ids", EXPECTED_SEED),
    ):
        require_text(row, field, expected, label, errors)


def validate_two_stage(
    results_dir: Path,
    reference_dir: Path | None = None,
) -> dict[str, object]:
    errors: list[str] = []
    paths = {
        "manifest": results_dir / "run_manifest.csv",
        "entities": results_dir / "entity_log.csv",
        "summary": results_dir / "run_summary.csv",
    }
    expected_schemas = {
        "manifest": MANIFEST_COLUMNS,
        "entities": ENTITY_COLUMNS,
        "summary": SUMMARY_COLUMNS,
    }
    loaded: dict[str, list[dict[str, str]]] = {}

    for name, path in paths.items():
        try:
            fieldnames, rows = read_csv(path)
        except (FileNotFoundError, ValueError) as exc:
            errors.append(str(exc))
            continue
        require_exact_schema(path, fieldnames, expected_schemas[name], errors)
        loaded[name] = rows

    manifest_rows = loaded.get("manifest", [])
    summary_rows = loaded.get("summary", [])
    entity_rows = loaded.get("entities", [])
    if len(manifest_rows) != 1:
        errors.append(
            f"run_manifest.csv: expected 1 row, found {len(manifest_rows)}"
        )
    if len(summary_rows) != 1:
        errors.append(
            f"run_summary.csv: expected 1 row, found {len(summary_rows)}"
        )
    if len(entity_rows) != 6:
        errors.append(f"entity_log.csv: expected 6 rows, found {len(entity_rows)}")

    if len(manifest_rows) == 1:
        row = manifest_rows[0]
        require_lineage(row, "run_manifest.csv:2", errors)
        require_text(row, "schema_version", "1.0", "run_manifest.csv:2", errors)
        require_text(
            row,
            "model_version",
            "two-stage-verification-v0.1",
            "run_manifest.csv:2",
            errors,
        )
        require_text(row, "start_state", "EMPTY", "run_manifest.csv:2", errors)
        require_float(
            row, "arrival_cutoff", 6.5, "run_manifest.csv:2", errors
        )
        require_float(row, "drain_end", 20.0, "run_manifest.csv:2", errors)
        if not row.get("verification_contract_hash"):
            errors.append("run_manifest.csv:2: empty verification_contract_hash")
        if not row.get("engine_version"):
            errors.append("run_manifest.csv:2: empty engine_version")

    ordered_entities = sorted(
        entity_rows,
        key=lambda row: row.get("traveller_id", ""),
    )
    expected_ids = [f"VERIFY_R01_T{index:03d}" for index in range(1, 7)]
    if [row.get("traveller_id") for row in ordered_entities] != expected_ids:
        errors.append("entity_log.csv: traveller IDs are not the exact T001-T006 ledger")

    for index, row in enumerate(ordered_entities):
        label = f"entity_log.csv:{index + 2}"
        require_lineage(row, label, errors)
        if index >= len(EXPECTED_ARRIVALS):
            continue
        for field, expected in (
            ("arrival", EXPECTED_ARRIVALS[index]),
            ("security_queue_join", EXPECTED_ARRIVALS[index]),
            ("security_start", EXPECTED_SECURITY_STARTS[index]),
            ("security_end", EXPECTED_SECURITY_ENDS[index]),
            ("immigration_queue_join", EXPECTED_SECURITY_ENDS[index]),
            ("immigration_start", EXPECTED_IMMIGRATION_STARTS[index]),
            ("immigration_primary_end", EXPECTED_EXITS[index]),
            ("exit", EXPECTED_EXITS[index]),
            ("security_service_demand", 2.0),
            ("immigration_service_demand", 3.0),
        ):
            require_float(row, field, expected, label, errors)
        for field, expected in (
            ("immigration_lane", "IMM_01"),
            ("security_resource_id", "SECURITY_01"),
            ("immigration_resource_id", "IMMIGRATION_01"),
            ("additional_check_flag", "false"),
            ("technology_flag", "false"),
        ):
            require_text(row, field, expected, label, errors)

    if len(summary_rows) == 1:
        row = summary_rows[0]
        require_lineage(row, "run_summary.csv:2", errors)
        for field, expected in (
            ("arrivals", 6.0),
            ("completed_at_cutoff", 1.0),
            ("security_queue_at_cutoff", 2.0),
            ("security_in_service_at_cutoff", 1.0),
            ("immigration_queue_at_cutoff", 1.0),
            ("immigration_in_service_at_cutoff", 1.0),
            ("wip_at_cutoff", 5.0),
            ("completed_after_drain", 6.0),
            ("security_wait_mean", 3.5),
            ("security_wait_p95", 6.5),
            ("immigration_wait_mean", 2.5),
            ("immigration_wait_p95", 5.0),
            ("total_queue_wait_mean", 6.0),
            ("total_queue_wait_p95", 11.5),
            ("system_time_mean", 11.0),
            ("system_time_p95", 16.5),
            ("cutoff_backlog", 5.0),
            ("cohort_clear_time_after_cutoff", 13.5),
        ):
            require_float(row, field, expected, "run_summary.csv:2", errors)

    reproducibility: dict[str, object] = {
        "reference_supplied": reference_dir is not None,
        "byte_identical": None,
        "files": {},
    }
    if reference_dir is not None:
        byte_identical = True
        hashes: dict[str, dict[str, str]] = {}
        for name, path in paths.items():
            reference_path = reference_dir / path.name
            if not path.is_file() or not reference_path.is_file():
                errors.append(
                    f"reproducibility: missing {path.name} in current or reference"
                )
                byte_identical = False
                continue
            current_hash = file_sha256(path)
            reference_hash = file_sha256(reference_path)
            hashes[name] = {
                "current_sha256": current_hash,
                "reference_sha256": reference_hash,
            }
            if current_hash != reference_hash:
                errors.append(
                    f"reproducibility: {path.name} is not byte-identical"
                )
                byte_identical = False
        reproducibility = {
            "reference_supplied": True,
            "byte_identical": byte_identical,
            "files": hashes,
        }

    return {
        "verification": "ANYLOGIC_TWO_STAGE_DETERMINISTIC_ORACLE",
        "status": "PASS" if not errors else "FAIL",
        "results_dir": str(results_dir),
        "expected_arrivals": list(EXPECTED_ARRIVALS),
        "expected_exits": list(EXPECTED_EXITS),
        "expected_cutoff_state": {
            "completed": 1,
            "security_queue": 2,
            "security_in_service": 1,
            "immigration_queue": 1,
            "immigration_in_service": 1,
            "wip": 5,
        },
        "reproducibility": reproducibility,
        "errors": errors,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS_DIR)
    parser.add_argument(
        "--reference-dir",
        type=Path,
        help="Optional prior run directory for byte-identical comparison.",
    )
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    report = validate_two_stage(
        args.results_dir.resolve(),
        (
            args.reference_dir.resolve()
            if args.reference_dir is not None
            else None
        ),
    )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
