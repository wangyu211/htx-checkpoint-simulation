"""Validate the AnyLogic local-window HPP arrival-only verification outputs.

This contract verifies the demand generator and its cutoff, not checkpoint
service performance.  The observed Task 1 aggregate supplies ``lambda`` and
the video window supplies ``T``; the HPP realization count remains stochastic.
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
    PROJECT_ROOT / "results" / "raw" / "anylogic_hpp_arrival_verification"
)
DEFAULT_REPORT = (
    PROJECT_ROOT
    / "results"
    / "intermediate"
    / "anylogic_hpp_arrival_verification"
    / "verification.json"
)

EXPECTED_SCHEMA_VERSION = "1.0"
EXPECTED_ROLE = "DEMAND_MECHANISM_VERIFICATION"
EXPECTED_SCOPE = "ARRIVAL_ONLY"
EXPECTED_SOURCE_CONFIG = "BASELINE_LOCAL_WINDOW_HPP"
EXPECTED_INPUT_SAMPLE = "HPP_SYNTHETIC_A"
EXPECTED_REPLICATION = "1"
EXPECTED_EVIDENCE = "task1_final_aggregate"
EXPECTED_ASSUMPTION = "LOCAL_WINDOW_HPP_STATIONARY_INDEPENDENT"
EXPECTED_RATE_PER_SECOND = 1.364213
EXPECTED_CUTOFF_SECONDS = 24.922788889
EXPECTED_SEED = "2026072710"
EXPECTED_COUNT = EXPECTED_RATE_PER_SECOND * EXPECTED_CUTOFF_SECONDS
PLE_EVENT_LIMIT = 50_000

MANIFEST_COLUMNS = (
    "schema_version",
    "experiment_role",
    "readiness_scope",
    "source_config_id",
    "input_sample_id",
    "replication_id",
    "arrival_evidence_id",
    "arrival_assumption",
    "arrival_rate_per_second",
    "arrival_cutoff_seconds",
    "arrival_seed",
    "expected_count",
    "realized_count",
    "guard_limit",
    "guard_hit",
    "engine_version",
)

LEDGER_COLUMNS = (
    "schema_version",
    "experiment_role",
    "readiness_scope",
    "source_config_id",
    "input_sample_id",
    "replication_id",
    "arrival_seed",
    "sequence",
    "arrival_time",
)

SUMMARY_COLUMNS = (
    "schema_version",
    "experiment_role",
    "readiness_scope",
    "source_config_id",
    "input_sample_id",
    "replication_id",
    "arrival_seed",
    "arrival_rate_per_second",
    "arrival_cutoff_seconds",
    "expected_count",
    "realized_count",
    "source_count",
    "sink_count",
    "guard_hit",
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


def parse_float(
    row: dict[str, str],
    field: str,
    label: str,
    errors: list[str],
) -> float | None:
    raw = row.get(field, "")
    try:
        result = float(raw)
    except (TypeError, ValueError):
        errors.append(f"{label}:{field}: expected finite number, got {raw!r}")
        return None
    if not math.isfinite(result):
        errors.append(f"{label}:{field}: expected finite number, got {raw!r}")
        return None
    return result


def require_float(
    row: dict[str, str],
    field: str,
    expected: float,
    label: str,
    errors: list[str],
    tolerance: float = 1e-9,
) -> float | None:
    actual = parse_float(row, field, label, errors)
    if actual is not None and abs(actual - expected) > tolerance:
        errors.append(
            f"{label}:{field}: expected {expected:.9f}, "
            f"got {row.get(field)!r}"
        )
    return actual


def parse_nonnegative_int(
    row: dict[str, str],
    field: str,
    label: str,
    errors: list[str],
) -> int | None:
    raw = row.get(field, "")
    try:
        result = int(raw)
    except (TypeError, ValueError):
        errors.append(
            f"{label}:{field}: expected non-negative integer, got {raw!r}"
        )
        return None
    if result < 0:
        errors.append(
            f"{label}:{field}: expected non-negative integer, got {raw!r}"
        )
        return None
    return result


def require_lineage(
    row: dict[str, str],
    label: str,
    errors: list[str],
) -> None:
    for field, expected in (
        ("schema_version", EXPECTED_SCHEMA_VERSION),
        ("experiment_role", EXPECTED_ROLE),
        ("readiness_scope", EXPECTED_SCOPE),
        ("source_config_id", EXPECTED_SOURCE_CONFIG),
        ("input_sample_id", EXPECTED_INPUT_SAMPLE),
        ("replication_id", EXPECTED_REPLICATION),
        ("arrival_seed", EXPECTED_SEED),
    ):
        require_text(row, field, expected, label, errors)


def validate_hpp_arrival(
    results_dir: Path,
    reference_dir: Path | None = None,
) -> dict[str, object]:
    """Validate schemas, lineage, HPP exposure, cutoff, and flow conservation."""

    errors: list[str] = []
    paths = {
        "manifest": results_dir / "run_manifest.csv",
        "ledger": results_dir / "arrival_ledger.csv",
        "summary": results_dir / "run_summary.csv",
    }
    expected_schemas = {
        "manifest": MANIFEST_COLUMNS,
        "ledger": LEDGER_COLUMNS,
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
    ledger_rows = loaded.get("ledger", [])
    summary_rows = loaded.get("summary", [])

    if len(manifest_rows) != 1:
        errors.append(
            f"run_manifest.csv: expected 1 row, found {len(manifest_rows)}"
        )
    if len(summary_rows) != 1:
        errors.append(
            f"run_summary.csv: expected 1 row, found {len(summary_rows)}"
        )

    manifest_realized: int | None = None
    guard_limit: int | None = None
    if len(manifest_rows) == 1:
        row = manifest_rows[0]
        label = "run_manifest.csv:2"
        require_lineage(row, label, errors)
        require_text(
            row,
            "arrival_evidence_id",
            EXPECTED_EVIDENCE,
            label,
            errors,
        )
        require_text(
            row,
            "arrival_assumption",
            EXPECTED_ASSUMPTION,
            label,
            errors,
        )
        require_float(
            row,
            "arrival_rate_per_second",
            EXPECTED_RATE_PER_SECOND,
            label,
            errors,
        )
        require_float(
            row,
            "arrival_cutoff_seconds",
            EXPECTED_CUTOFF_SECONDS,
            label,
            errors,
        )
        require_float(
            row,
            "expected_count",
            EXPECTED_COUNT,
            label,
            errors,
        )
        manifest_realized = parse_nonnegative_int(
            row, "realized_count", label, errors
        )
        guard_limit = parse_nonnegative_int(
            row, "guard_limit", label, errors
        )
        require_text(row, "guard_hit", "false", label, errors)
        if not row.get("engine_version"):
            errors.append(f"{label}:engine_version: must not be empty")

        if guard_limit is not None:
            if not 0 < guard_limit < PLE_EVENT_LIMIT:
                errors.append(
                    f"{label}:guard_limit: must be in (0, {PLE_EVENT_LIMIT})"
                )
            safety_bound = EXPECTED_COUNT + 10.0 * math.sqrt(EXPECTED_COUNT)
            if guard_limit <= safety_bound:
                errors.append(
                    f"{label}:guard_limit: does not clear the HPP safety bound"
                )
            if (
                manifest_realized is not None
                and manifest_realized >= guard_limit
            ):
                errors.append(
                    f"{label}: realized_count must be below guard_limit"
                )

    previous_time = -math.inf
    for position, row in enumerate(ledger_rows, start=1):
        label = f"arrival_ledger.csv:{position + 1}"
        require_lineage(row, label, errors)
        sequence = parse_nonnegative_int(row, "sequence", label, errors)
        if sequence is not None and sequence != position:
            errors.append(
                f"{label}:sequence: expected {position}, got {sequence}"
            )
        arrival_time = parse_float(row, "arrival_time", label, errors)
        if arrival_time is None:
            continue
        if not 0.0 <= arrival_time < EXPECTED_CUTOFF_SECONDS:
            errors.append(
                f"{label}:arrival_time: must be inside [0, T)"
            )
        if arrival_time <= previous_time:
            errors.append(
                f"{label}:arrival_time: timestamps must be strictly increasing"
            )
        previous_time = arrival_time

    summary_realized: int | None = None
    source_count: int | None = None
    sink_count: int | None = None
    if len(summary_rows) == 1:
        row = summary_rows[0]
        label = "run_summary.csv:2"
        require_lineage(row, label, errors)
        require_float(
            row,
            "arrival_rate_per_second",
            EXPECTED_RATE_PER_SECOND,
            label,
            errors,
        )
        require_float(
            row,
            "arrival_cutoff_seconds",
            EXPECTED_CUTOFF_SECONDS,
            label,
            errors,
        )
        require_float(
            row,
            "expected_count",
            EXPECTED_COUNT,
            label,
            errors,
        )
        summary_realized = parse_nonnegative_int(
            row, "realized_count", label, errors
        )
        source_count = parse_nonnegative_int(
            row, "source_count", label, errors
        )
        sink_count = parse_nonnegative_int(
            row, "sink_count", label, errors
        )
        require_text(row, "guard_hit", "false", label, errors)

    ledger_count = len(ledger_rows)
    for label, value in (
        ("run_manifest.csv:2:realized_count", manifest_realized),
        ("run_summary.csv:2:realized_count", summary_realized),
        ("run_summary.csv:2:source_count", source_count),
        ("run_summary.csv:2:sink_count", sink_count),
    ):
        if value is not None and value != ledger_count:
            errors.append(
                f"{label}: expected conserved ledger count "
                f"{ledger_count}, got {value}"
            )

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
        "verification": "ANYLOGIC_HPP_ARRIVAL_ONLY",
        "status": "PASS" if not errors else "FAIL",
        "readiness_scope": EXPECTED_SCOPE,
        "results_dir": str(results_dir),
        "rate_per_second": EXPECTED_RATE_PER_SECOND,
        "cutoff_seconds": EXPECTED_CUTOFF_SECONDS,
        "expected_count": EXPECTED_COUNT,
        "realized_count": (
            manifest_realized
            if manifest_realized is not None
            else ledger_count
        ),
        "count_conservation": {
            "ledger": ledger_count,
            "manifest": manifest_realized,
            "summary": summary_realized,
            "source": source_count,
            "sink": sink_count,
        },
        "guard_limit": guard_limit,
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
    report = validate_hpp_arrival(
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
