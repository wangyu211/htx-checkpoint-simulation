"""Validate the Task 2-to-Task 3 simulation configuration boundary.

The contract deliberately permits rows declared ``BLOCKED_INPUTS``.  This lets
the accepted arrival evidence enter the model without silently inventing
service times, resource capacities, or exception behaviour.  A blocked row is
a valid contract row, but it is not executable.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Mapping, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = PROJECT_ROOT / "config" / "model_run_configs.csv"
DEFAULT_REPORT = (
    PROJECT_ROOT
    / "results"
    / "intermediate"
    / "model_configuration"
    / "validation.json"
)

REQUIRED_COLUMNS = (
    "schema_version",
    "config_id",
    "purpose",
    "scenario_id",
    "arrival_mode",
    "arrival_rate_per_second",
    "arrival_assumption",
    "arrival_evidence_id",
    "arrival_fixture_id",
    "arrival_trace_path",
    "max_arrivals",
    "arrival_cutoff_seconds",
    "security_capacity",
    "immigration_capacity",
    "security_queue_capacity",
    "immigration_queue_capacity",
    "security_service_distribution",
    "security_service_p1_seconds",
    "immigration_service_distribution",
    "immigration_service_p1_seconds",
    "queue_policy",
    "automation_uptake",
    "automation_multiplier",
    "additional_check_probability",
    "additional_check_service_seconds",
    "random_seed",
    "input_status",
    "notes",
)

PURPOSES = {"SYNTHETIC_ORACLE", "ASSESSMENT_STUDY"}
ARRIVAL_MODES = {"DETERMINISTIC_FIXTURE", "HPP", "TRACE"}
QUEUE_POLICIES = {"pooled", "separate"}
SERVICE_DISTRIBUTIONS = {"UNSET", "FIXED"}
INPUT_STATUSES = {"READY", "BLOCKED_INPUTS"}


def _text(row: Mapping[str, str], field: str) -> str:
    return (row.get(field) or "").strip()


def _positive_float(
    row: Mapping[str, str],
    field: str,
    *,
    blockers: list[str],
    errors: list[str],
    required: bool = True,
) -> float | None:
    raw = _text(row, field)
    if not raw:
        if required:
            blockers.append(f"{field} is not frozen")
        return None
    try:
        value = float(raw)
    except ValueError:
        errors.append(f"{field} must be a finite positive number; got {raw!r}")
        return None
    if not math.isfinite(value) or value <= 0:
        errors.append(f"{field} must be a finite positive number; got {raw!r}")
        return None
    return value


def _probability(
    row: Mapping[str, str],
    field: str,
    *,
    blockers: list[str],
    errors: list[str],
) -> float | None:
    raw = _text(row, field)
    if not raw:
        blockers.append(f"{field} is not frozen")
        return None
    try:
        value = float(raw)
    except ValueError:
        errors.append(f"{field} must be between 0 and 1; got {raw!r}")
        return None
    if not math.isfinite(value) or not 0 <= value <= 1:
        errors.append(f"{field} must be between 0 and 1; got {raw!r}")
        return None
    return value


def _positive_integer(
    row: Mapping[str, str],
    field: str,
    *,
    blockers: list[str],
    errors: list[str],
    required: bool = True,
) -> int | None:
    raw = _text(row, field)
    if not raw:
        if required:
            blockers.append(f"{field} is not frozen")
        return None
    try:
        value = int(raw)
    except ValueError:
        errors.append(f"{field} must be a positive integer; got {raw!r}")
        return None
    if value <= 0:
        errors.append(f"{field} must be a positive integer; got {raw!r}")
        return None
    return value


def _validate_service(
    row: Mapping[str, str],
    stage: str,
    *,
    blockers: list[str],
    errors: list[str],
) -> None:
    distribution_field = f"{stage}_service_distribution"
    parameter_field = f"{stage}_service_p1_seconds"
    distribution = _text(row, distribution_field)

    if not distribution or distribution == "UNSET":
        blockers.append(f"{distribution_field} is not frozen")
        if _text(row, parameter_field):
            errors.append(
                f"{parameter_field} must be blank while "
                f"{distribution_field}=UNSET"
            )
        return
    if distribution not in SERVICE_DISTRIBUTIONS:
        errors.append(
            f"{distribution_field} must be one of "
            f"{sorted(SERVICE_DISTRIBUTIONS)}; got {distribution!r}"
        )
        return
    if distribution == "FIXED":
        _positive_float(
            row,
            parameter_field,
            blockers=blockers,
            errors=errors,
        )


def validate_config_row(
    row: Mapping[str, str],
    *,
    project_root: Path = PROJECT_ROOT,
) -> dict[str, object]:
    """Validate one configuration row and compute whether it is executable."""

    blockers: list[str] = []
    errors: list[str] = []

    config_id = _text(row, "config_id")
    if not config_id:
        errors.append("config_id is required")

    purpose = _text(row, "purpose")
    if purpose not in PURPOSES:
        errors.append(f"purpose must be one of {sorted(PURPOSES)}")

    if not _text(row, "scenario_id"):
        errors.append("scenario_id is required")
    if not _text(row, "arrival_evidence_id"):
        errors.append("arrival_evidence_id is required")
    if not _text(row, "arrival_assumption"):
        errors.append("arrival_assumption is required")

    arrival_mode = _text(row, "arrival_mode")
    if arrival_mode not in ARRIVAL_MODES:
        errors.append(f"arrival_mode must be one of {sorted(ARRIVAL_MODES)}")
    elif arrival_mode == "DETERMINISTIC_FIXTURE":
        if not _text(row, "arrival_fixture_id"):
            blockers.append("arrival_fixture_id is not frozen")
        _positive_integer(
            row,
            "max_arrivals",
            blockers=blockers,
            errors=errors,
        )
    elif arrival_mode == "HPP":
        _positive_float(
            row,
            "arrival_rate_per_second",
            blockers=blockers,
            errors=errors,
        )
    elif arrival_mode == "TRACE":
        trace_path = _text(row, "arrival_trace_path")
        if not trace_path:
            blockers.append("arrival_trace_path is not frozen")
        elif not (project_root / trace_path).is_file():
            blockers.append(f"arrival_trace_path does not exist: {trace_path}")

    _positive_float(
        row,
        "arrival_cutoff_seconds",
        blockers=blockers,
        errors=errors,
    )
    _positive_integer(
        row,
        "security_capacity",
        blockers=blockers,
        errors=errors,
    )
    _positive_integer(
        row,
        "immigration_capacity",
        blockers=blockers,
        errors=errors,
    )
    _positive_integer(
        row,
        "security_queue_capacity",
        blockers=blockers,
        errors=errors,
    )
    _positive_integer(
        row,
        "immigration_queue_capacity",
        blockers=blockers,
        errors=errors,
    )
    _validate_service(row, "security", blockers=blockers, errors=errors)
    _validate_service(row, "immigration", blockers=blockers, errors=errors)

    queue_policy = _text(row, "queue_policy")
    if queue_policy not in QUEUE_POLICIES:
        errors.append(
            f"queue_policy must be one of {sorted(QUEUE_POLICIES)}; "
            f"got {queue_policy!r}"
        )

    _probability(
        row,
        "automation_uptake",
        blockers=blockers,
        errors=errors,
    )
    _positive_float(
        row,
        "automation_multiplier",
        blockers=blockers,
        errors=errors,
    )
    additional_probability = _probability(
        row,
        "additional_check_probability",
        blockers=blockers,
        errors=errors,
    )
    if additional_probability is not None and additional_probability > 0:
        _positive_float(
            row,
            "additional_check_service_seconds",
            blockers=blockers,
            errors=errors,
        )
    elif additional_probability == 0 and _text(
        row, "additional_check_service_seconds"
    ):
        _positive_float(
            row,
            "additional_check_service_seconds",
            blockers=blockers,
            errors=errors,
        )

    _positive_integer(
        row,
        "random_seed",
        blockers=blockers,
        errors=errors,
    )

    computed_status = (
        "INVALID" if errors else "BLOCKED_INPUTS" if blockers else "READY"
    )
    declared_status = _text(row, "input_status")
    if declared_status not in INPUT_STATUSES:
        errors.append(f"input_status must be one of {sorted(INPUT_STATUSES)}")
    elif declared_status != computed_status:
        errors.append(
            f"input_status={declared_status} but computed readiness is "
            f"{computed_status}"
        )

    return {
        "config_id": config_id,
        "purpose": purpose,
        "declared_status": declared_status,
        "computed_status": computed_status,
        "executable": computed_status == "READY",
        "blockers": blockers,
        "errors": errors,
    }


def validate_config_contract(
    config_path: Path = DEFAULT_CONFIG,
    *,
    project_root: Path = PROJECT_ROOT,
) -> dict[str, object]:
    errors: list[str] = []
    if not config_path.is_file():
        return {
            "contract": "MODEL_RUN_CONFIGURATION_V1",
            "status": "FAIL",
            "config_path": str(config_path),
            "rows": [],
            "errors": [f"configuration file does not exist: {config_path}"],
        }

    with config_path.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        fieldnames: Sequence[str] = reader.fieldnames or ()
        missing = [name for name in REQUIRED_COLUMNS if name not in fieldnames]
        if missing:
            errors.append(f"missing required columns: {missing}")
        rows = list(reader)

    row_reports = [
        validate_config_row(row, project_root=project_root) for row in rows
    ]
    config_ids = [str(report["config_id"]) for report in row_reports]
    duplicate_ids = sorted(
        {config_id for config_id in config_ids if config_ids.count(config_id) > 1}
    )
    if duplicate_ids:
        errors.append(f"duplicate config_id values: {duplicate_ids}")
    if not rows:
        errors.append("configuration contract contains no rows")

    for index, report in enumerate(row_reports, start=2):
        for error in report["errors"]:  # type: ignore[union-attr]
            errors.append(f"line {index} ({report['config_id']}): {error}")

    ready = [
        report["config_id"]
        for report in row_reports
        if report["computed_status"] == "READY"
    ]
    blocked = [
        report["config_id"]
        for report in row_reports
        if report["computed_status"] == "BLOCKED_INPUTS"
    ]
    return {
        "contract": "MODEL_RUN_CONFIGURATION_V1",
        "status": "PASS" if not errors else "FAIL",
        "config_path": str(config_path),
        "ready_configs": ready,
        "blocked_configs": blocked,
        "rows": row_reports,
        "errors": errors,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    report = validate_config_contract(args.config.resolve())
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
