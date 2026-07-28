"""Build and validate the frozen exploratory capacity response-surface design.

The registered Part 2 study remains immutable. This module derives a
self-contained dense Security-by-Immigration Base-demand grid and copies the
exact registered Base-demand seed tuple for every replication. Five old cells
remain external and are used only for cross-batch reproducibility checks.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Mapping, Sequence

from src.analysis.validate_operational_contract import (
    DEFAULT_SCENARIOS as DEFAULT_OPERATIONAL_SCENARIOS,
    REFERENCE_SCENARIO_ID,
    SCENARIO_COLUMNS,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DESIGN = (
    PROJECT_ROOT / "config" / "capacity_response_surface_study.json"
)
DEFAULT_SCENARIOS = (
    PROJECT_ROOT / "config" / "capacity_response_surface_scenarios.csv"
)
DEFAULT_SEED_MANIFEST = (
    PROJECT_ROOT / "config" / "capacity_response_surface_seed_manifest.csv"
)
DEFAULT_REFERENCE_SEED_MANIFEST = (
    PROJECT_ROOT / "config" / "confirmatory_seed_manifest.csv"
)

SEED_COLUMNS = (
    "schema_version",
    "study_id",
    "pairing_group_id",
    "arrival_level_id",
    "input_sample_id",
    "replication_id",
    "scenario_ids",
    "master_seed",
    "arrival_seed",
    "service_seed",
    "routing_seed",
    "tie_seed",
)

EXPECTED_SECURITY_CAPACITIES = tuple(range(36, 27, -1))
EXPECTED_IMMIGRATION_CAPACITIES = tuple(range(21, 15, -1))
EXPECTED_REUSE = {
    (36, 21): (
        "REFERENCE_ASSUMPTION_SANDBOX_V1",
        "confirmatory_capacity",
    ),
    (32, 21): (
        "CAPACITY_AVAIL_SECURITY_MINUS_4",
        "capacity_availability",
    ),
    (36, 18): (
        "CAPACITY_AVAIL_IMMIGRATION_MINUS_3",
        "capacity_availability",
    ),
    (32, 18): (
        "CAPACITY_AVAIL_JOINT_MINUS_4_MINUS_3",
        "capacity_availability",
    ),
    (30, 17): (
        "CAPACITY_AVAIL_SEVERE_JOINT_30_17",
        "capacity_availability",
    ),
}


def _read_csv(path: Path) -> tuple[tuple[str, ...], list[dict[str, str]]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return tuple(reader.fieldnames or ()), [dict(row) for row in reader]


def _clean(row: Mapping[str, str]) -> dict[str, str]:
    return {key: (value or "").strip() for key, value in row.items()}


def load_design(path: Path = DEFAULT_DESIGN) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _reference_scenario_row(
    path: Path = DEFAULT_OPERATIONAL_SCENARIOS,
) -> dict[str, str]:
    fields, rows = _read_csv(path)
    if fields != SCENARIO_COLUMNS:
        raise ValueError("operational scenario header is not canonical")
    matches = [
        _clean(row)
        for row in rows
        if row.get("scenario_id") == REFERENCE_SCENARIO_ID
    ]
    if len(matches) != 1:
        raise ValueError("exactly one registered reference scenario is required")
    return matches[0]


def response_scenario_id(
    security_capacity: int,
    immigration_capacity: int,
) -> str:
    return (
        f"CAPACITY_RESPONSE_S{security_capacity}_I{immigration_capacity}"
    )


def full_grid(
    design_path: Path = DEFAULT_DESIGN,
) -> list[tuple[int, int]]:
    design = load_design(design_path)
    grid = design["capacity_grid"]
    return [
        (int(security), int(immigration))
        for security in grid["security_capacities"]
        for immigration in grid["immigration_capacities"]
    ]


def cross_batch_validation_cells(
    design_path: Path = DEFAULT_DESIGN,
) -> dict[tuple[int, int], dict[str, object]]:
    design = load_design(design_path)
    return {
        (
            int(row["security_capacity"]),
            int(row["immigration_capacity"]),
        ): dict(row)
        for row in design["cross_batch_validation_cells"]
    }


def execution_cells(
    design_path: Path = DEFAULT_DESIGN,
) -> list[tuple[int, int]]:
    return full_grid(design_path)


def execution_scenario_ids(
    design_path: Path = DEFAULT_DESIGN,
) -> tuple[str, ...]:
    return tuple(
        response_scenario_id(security, immigration)
        for security, immigration in execution_cells(design_path)
    )


def _base_reference_seed_rows(
    path: Path = DEFAULT_REFERENCE_SEED_MANIFEST,
) -> list[dict[str, str]]:
    fields, rows = _read_csv(path)
    if fields != SEED_COLUMNS:
        raise ValueError("reference seed manifest header is not canonical")
    base = [
        _clean(row)
        for row in rows
        if row.get("arrival_level_id") == "MLE_BASE"
        and row.get("input_sample_id") == "LOCAL_WINDOW_HPP_BASE"
    ]
    if len(base) != 50:
        raise ValueError("reference manifest must contain 50 Base seed groups")
    return base


def build_response_surface_scenario_rows(
    design_path: Path = DEFAULT_DESIGN,
    operational_scenarios_path: Path = DEFAULT_OPERATIONAL_SCENARIOS,
    reference_seed_manifest_path: Path = DEFAULT_REFERENCE_SEED_MANIFEST,
) -> list[dict[str, str]]:
    design = load_design(design_path)
    fixed = design["fixed_inputs"]
    reference = _reference_scenario_row(operational_scenarios_path)
    seed_rows = _base_reference_seed_rows(reference_seed_manifest_path)
    master_seeds = {row["master_seed"] for row in seed_rows}
    if len(master_seeds) != 1:
        raise ValueError("Base seed groups have multiple master seeds")
    master_seed = master_seeds.pop()
    replications = str(design["execution"]["replications_per_cell"])
    study_id = str(design["study_id"])

    rows: list[dict[str, str]] = []
    for security, immigration in execution_cells(design_path):
        scenario_id = response_scenario_id(security, immigration)
        row = dict(reference)
        row.update(
            {
                "config_id": (
                    f"OP_RESPONSE_MLE_BASE_S{security}_I{immigration}"
                ),
                "scenario_id": scenario_id,
                "scenario_family": "CAPACITY_RESPONSE",
                "description": (
                    "Exploratory Base-demand response-surface cell with "
                    f"{security} Security and {immigration} Immigration "
                    "positions open"
                ),
                "arrival_rate_per_second": str(
                    fixed["arrival_rate_per_second"]
                ),
                "demand_multiplier": "1.0",
                "arrival_cutoff_seconds": str(
                    fixed["arrival_cutoff_seconds"]
                ),
                "drain_rule": str(fixed["drain_rule"]),
                "security_capacity": str(security),
                "security_service_distribution": str(
                    fixed["security_service_distribution"]
                ),
                "security_service_p1_seconds": str(
                    fixed["security_service_p1_seconds"]
                ),
                "immigration_capacity": str(immigration),
                "immigration_service_distribution": str(
                    fixed["immigration_service_distribution"]
                ),
                "immigration_service_p1_seconds": str(
                    fixed["immigration_service_p1_seconds"]
                ),
                "queue_policy": str(fixed["queue_policy"]),
                "automation_mapping_mode": str(
                    fixed["automation_mapping_mode"]
                ),
                "automation_uptake": "0",
                "automation_multiplier": "1",
                "additional_check_semantics": str(
                    fixed["additional_check_semantics"]
                ),
                "additional_check_probability_conventional": "0",
                "additional_check_probability_technology": "0",
                "additional_check_service_distribution": "UNSET",
                "additional_check_service_p1_seconds": "",
                "input_sample_id": str(fixed["input_sample_id"]),
                "pilot_replications": replications,
                "master_seed": master_seed,
                "crn_alignment_status": "PENDING_VALIDATION",
                "input_status": "FROZEN_RESPONSE_SURFACE_DESIGN",
                "calibration_status": "NOT_CALIBRATED",
                "claim_ceiling": "COMPARATIVE_WHAT_IF_ONLY",
                "notes": (
                    f"{study_id}; post-outcome exploratory sensitivity; "
                    "capacity is concurrently open service positions, not an "
                    "observed roster; paired interpretation requires exact "
                    "CRN alignment PASS"
                ),
            }
        )
        if tuple(row) != SCENARIO_COLUMNS:
            raise ValueError("derived response row lost the canonical schema")
        rows.append(row)
    return rows


def build_response_surface_seed_rows(
    design_path: Path = DEFAULT_DESIGN,
    reference_seed_manifest_path: Path = DEFAULT_REFERENCE_SEED_MANIFEST,
) -> list[dict[str, str]]:
    design = load_design(design_path)
    scenario_ids = "|".join(execution_scenario_ids(design_path))
    return [
        {
            **row,
            "study_id": str(design["study_id"]),
            "scenario_ids": scenario_ids,
        }
        for row in _base_reference_seed_rows(reference_seed_manifest_path)
    ]


def write_generated_artifacts(
    *,
    scenarios_path: Path = DEFAULT_SCENARIOS,
    seed_manifest_path: Path = DEFAULT_SEED_MANIFEST,
) -> None:
    artifacts = (
        (
            scenarios_path,
            SCENARIO_COLUMNS,
            build_response_surface_scenario_rows(),
        ),
        (
            seed_manifest_path,
            SEED_COLUMNS,
            build_response_surface_seed_rows(),
        ),
    )
    for path, fields, rows in artifacts:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=fields,
                lineterminator="\n",
            )
            writer.writeheader()
            writer.writerows(rows)


def load_response_surface_scenario_rows(
    path: Path = DEFAULT_SCENARIOS,
) -> list[dict[str, str]]:
    fields, rows = _read_csv(path)
    if fields != SCENARIO_COLUMNS:
        raise ValueError("response-surface scenario header is not canonical")
    return [_clean(row) for row in rows]


def load_response_surface_seed_rows(
    path: Path = DEFAULT_SEED_MANIFEST,
) -> list[dict[str, str]]:
    fields, rows = _read_csv(path)
    if fields != SEED_COLUMNS:
        raise ValueError("response-surface seed header is not canonical")
    return [_clean(row) for row in rows]


def _equal_float(left: object, right: object) -> bool:
    try:
        return math.isclose(
            float(left),
            float(right),
            rel_tol=1e-12,
            abs_tol=1e-12,
        )
    except (TypeError, ValueError):
        return False


def validate_response_surface_design(
    design_path: Path = DEFAULT_DESIGN,
    scenarios_path: Path = DEFAULT_SCENARIOS,
    seed_manifest_path: Path = DEFAULT_SEED_MANIFEST,
    reference_seed_manifest_path: Path = DEFAULT_REFERENCE_SEED_MANIFEST,
) -> dict[str, object]:
    """Fail closed on the frozen grid, reuse set, execution cells, and seeds."""

    design = load_design(design_path)
    errors: list[str] = []
    grid = design.get("capacity_grid", {})
    security = tuple(int(value) for value in grid.get("security_capacities", []))
    immigration = tuple(
        int(value) for value in grid.get("immigration_capacities", [])
    )
    if security != EXPECTED_SECURITY_CAPACITIES:
        errors.append("Security grid must remain every integer from 36 to 28")
    if immigration != EXPECTED_IMMIGRATION_CAPACITIES:
        errors.append("Immigration grid must remain every integer from 21 to 16")
    if design.get("design_status") != "FROZEN_PRE_RUN":
        errors.append("design status must remain FROZEN_PRE_RUN")
    if design.get("analysis_role") != (
        "EXPLORATORY_SENSITIVITY_NOT_CONFIRMATORY"
    ):
        errors.append("analysis role must remain explicitly exploratory")
    ideal = design.get("analysis", {}).get("ideal_case_comparator", {})
    if ideal.get("name") != "DETERMINISTIC_IDEAL_CONTROL_V1":
        errors.append("deterministic ideal-control identity drifted")
    if ideal.get("same_capacity_grid") is not True:
        errors.append("deterministic ideal control must use the same grid")
    if ideal.get("implementation_role") != (
        "ANALYTICAL_DETERMINISTIC_ORACLE_NOT_A_SUBSTITUTE_FOR_ANYLOGIC"
    ):
        errors.append("ideal control must remain separate from AnyLogic evidence")

    actual_validation_cells = {
        cell: (
            str(row.get("source_scenario_id")),
            str(row.get("source_collection")),
        )
        for cell, row in cross_batch_validation_cells(design_path).items()
    }
    if actual_validation_cells != EXPECTED_REUSE:
        errors.append(
            "the five frozen cross-batch validation cells or sources drifted"
        )

    expected_execution_cells = execution_cells(design_path)
    expected_execution_ids = execution_scenario_ids(design_path)
    try:
        fields, raw_rows = _read_csv(scenarios_path)
    except FileNotFoundError:
        fields, raw_rows = (), []
        errors.append(f"missing file: {scenarios_path}")
    if fields != SCENARIO_COLUMNS:
        errors.append("response-surface scenario header is not canonical")
    rows = [_clean(row) for row in raw_rows]
    if len(rows) != len(expected_execution_cells):
        errors.append("response-surface scenario count must remain 54")
    seen_ids: set[str] = set()
    seen_cells: set[tuple[int, int]] = set()
    fixed = design["fixed_inputs"]
    for line, row in enumerate(rows, start=2):
        scenario_id = row.get("scenario_id", "")
        if scenario_id in seen_ids:
            errors.append(f"scenario line {line}: duplicate scenario_id")
        seen_ids.add(scenario_id)
        try:
            cell = (
                int(row.get("security_capacity", "-1")),
                int(row.get("immigration_capacity", "-1")),
            )
        except ValueError:
            errors.append(f"scenario line {line}: invalid capacity")
            continue
        if cell in seen_cells:
            errors.append(f"scenario line {line}: duplicate capacity cell")
        seen_cells.add(cell)
        if cell not in expected_execution_cells:
            errors.append(f"scenario line {line}: cell is outside execution grid")
        if scenario_id != response_scenario_id(*cell):
            errors.append(f"scenario line {line}: scenario_id/capacity mismatch")
        if row.get("input_sample_id") != fixed["input_sample_id"]:
            errors.append(f"scenario line {line}: Base input sample drift")
        if not _equal_float(
            row.get("arrival_rate_per_second"),
            fixed["arrival_rate_per_second"],
        ):
            errors.append(f"scenario line {line}: Base arrival-rate drift")
        if row.get("pilot_replications") != "50":
            errors.append(f"scenario line {line}: replication-count drift")
        if row.get("input_status") != "FROZEN_RESPONSE_SURFACE_DESIGN":
            errors.append(f"scenario line {line}: input status is not frozen")
        if row.get("calibration_status") != "NOT_CALIBRATED":
            errors.append(f"scenario line {line}: calibration boundary drift")
    if seen_cells != set(expected_execution_cells):
        errors.append("execution scenario grid is incomplete")
    if tuple(row.get("scenario_id", "") for row in rows) != (
        expected_execution_ids
    ):
        errors.append("execution scenario ordering drifted")

    try:
        seed_fields, raw_seed_rows = _read_csv(seed_manifest_path)
    except FileNotFoundError:
        seed_fields, raw_seed_rows = (), []
        errors.append(f"missing file: {seed_manifest_path}")
    if seed_fields != SEED_COLUMNS:
        errors.append("response-surface seed header is not canonical")
    seed_rows = [_clean(row) for row in raw_seed_rows]
    source_by_replication = {
        row["replication_id"]: row
        for row in _base_reference_seed_rows(reference_seed_manifest_path)
    }
    expected_scenarios = "|".join(expected_execution_ids)
    seen_replications: set[str] = set()
    for line, row in enumerate(seed_rows, start=2):
        replication = row.get("replication_id", "")
        if replication in seen_replications:
            errors.append(f"seed line {line}: duplicate replication")
        seen_replications.add(replication)
        source = source_by_replication.get(replication)
        if source is None:
            errors.append(f"seed line {line}: no registered Base seed group")
            continue
        if row.get("study_id") != design.get("study_id"):
            errors.append(f"seed line {line}: study_id drift")
        if row.get("arrival_level_id") != "MLE_BASE":
            errors.append(f"seed line {line}: arrival level is not MLE_BASE")
        if row.get("scenario_ids") != expected_scenarios:
            errors.append(f"seed line {line}: execution scenario ordering drift")
        for field in (
            "input_sample_id",
            "master_seed",
            "arrival_seed",
            "service_seed",
            "routing_seed",
            "tie_seed",
        ):
            if row.get(field) != source.get(field):
                errors.append(
                    f"seed line {line}: {field} does not exactly reuse Base"
                )
    if seen_replications != {str(value) for value in range(1, 51)}:
        errors.append("seed manifest must contain exactly replications 1..50")

    execution = design.get("execution", {})
    expected_counts = {
        "full_grid_cell_count": 54,
        "cross_batch_validation_cell_count": 5,
        "new_execution_cell_count": 54,
        "new_execution_run_count": 2700,
        "analysis_run_count": 2700,
        "replications_per_cell": 50,
    }
    for field, expected in expected_counts.items():
        if int(execution.get(field, -1)) != expected:
            errors.append(f"execution.{field} must remain {expected}")
    if execution.get("parallel_evaluations") is not False:
        errors.append("parallel evaluations must remain disabled")
    if execution.get("adaptive_extension_allowed") is not False:
        errors.append("adaptive extension must remain disabled")

    return {
        "status": "PASS" if not errors else "FAIL",
        "study_id": design.get("study_id"),
        "errors": errors,
        "full_grid_cell_count": len(full_grid(design_path)),
        "cross_batch_validation_cell_count": len(
            cross_batch_validation_cells(design_path)
        ),
        "new_execution_cell_count": len(expected_execution_cells),
        "seed_group_count": len(seed_rows),
        "new_execution_run_count": len(expected_execution_cells) * 50,
        "analysis_run_count": len(full_grid(design_path)) * 50,
        "analysis_role": design.get("analysis_role"),
        "ideal_control": ideal.get("name"),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write-generated",
        action="store_true",
        help="rewrite deterministic scenario and seed CSV artifacts",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.write_generated:
        write_generated_artifacts()
    report = validate_response_surface_design()
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
