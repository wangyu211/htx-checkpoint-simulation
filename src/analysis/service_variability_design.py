"""Build and validate the frozen service-variability sensitivity design.

This study is deliberately separate from the registered 300-second capacity
studies.  It keeps their canonical scenario schema and hashes untouched while
adding two study-local coefficient-of-variation fields.  The new fields are
part of a separate configuration hash and are not retrofitted into
``operational_scenarios.csv``.

The study is an assumption sensitivity, not a calibration claim.  It holds
the arithmetic service-time means fixed and crosses Security and Immigration
CV values ``{0, 0.5, 1.0}`` at the Base arrival input and 36/21 reference
capacity.  CV zero maps to fixed service.  Positive CV maps to a
mean-preserving lognormal family that will be implemented in the AnyLogic
runtime in a later, separately reviewed change.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
from typing import Mapping, Sequence

from src.analysis.validate_operational_contract import (
    DEFAULT_SCENARIOS as DEFAULT_OPERATIONAL_SCENARIOS,
    REFERENCE_SCENARIO_ID as OPERATIONAL_REFERENCE_SCENARIO_ID,
    SCENARIO_COLUMNS,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DESIGN = PROJECT_ROOT / "config" / "service_variability_study.json"
DEFAULT_SCENARIOS = (
    PROJECT_ROOT / "config" / "service_variability_scenarios.csv"
)
DEFAULT_SEED_MANIFEST = (
    PROJECT_ROOT / "config" / "service_variability_seed_manifest.csv"
)
DEFAULT_REFERENCE_SEED_MANIFEST = (
    PROJECT_ROOT / "config" / "confirmatory_seed_manifest.csv"
)

STUDY_ID = "TASK3_SERVICE_VARIABILITY_SENSITIVITY_V1"
MODEL_VERSION = "TASK3_OPERATIONAL_POOLED_SERVICE_VARIABILITY_V1"
REFERENCE_SCENARIO_ID = "SERVICE_VARIABILITY_SCV000_ICV000"
INPUT_SAMPLE_ID = "LOCAL_WINDOW_HPP_BASE"
CV_LEVELS = (0.0, 0.5, 1.0)
REPLICATION_IDS = tuple(range(1, 51))

# Appending study-local fields is intentional.  Never insert them into or
# otherwise mutate the frozen v1 SCENARIO_COLUMNS tuple.
SERVICE_SCENARIO_COLUMNS = (
    *SCENARIO_COLUMNS,
    "security_service_cv",
    "immigration_service_cv",
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


def _read_csv(path: Path) -> tuple[tuple[str, ...], list[dict[str, str]]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return tuple(reader.fieldnames or ()), [dict(row) for row in reader]


def _clean(row: Mapping[str, str]) -> dict[str, str]:
    return {key: (value or "").strip() for key, value in row.items()}


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


def _format_cv(value: float) -> str:
    return f"{value:g}"


def _cv_code(value: float) -> str:
    return f"{int(round(100.0 * value)):03d}"


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
        if row.get("scenario_id") == OPERATIONAL_REFERENCE_SCENARIO_ID
    ]
    if len(matches) != 1:
        raise ValueError("exactly one operational reference row is required")
    return matches[0]


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
        and row.get("input_sample_id") == INPUT_SAMPLE_ID
    ]
    if len(base) != 50:
        raise ValueError("reference manifest must contain 50 Base seed groups")
    if {row["replication_id"] for row in base} != {
        str(value) for value in REPLICATION_IDS
    }:
        raise ValueError("Base seed groups must be exactly replications 1..50")
    return base


def service_variability_scenario_id(
    security_cv: float,
    immigration_cv: float,
) -> str:
    return (
        "SERVICE_VARIABILITY_"
        f"SCV{_cv_code(security_cv)}_ICV{_cv_code(immigration_cv)}"
    )


def service_variability_config_id(
    security_cv: float,
    immigration_cv: float,
) -> str:
    return (
        "OP_SERVICE_VARIABILITY_"
        f"SCV{_cv_code(security_cv)}_ICV{_cv_code(immigration_cv)}"
    )


def study_cells(
    design_path: Path = DEFAULT_DESIGN,
) -> list[tuple[float, float]]:
    design = load_design(design_path)
    grid = design["service_cv_grid"]
    return [
        (float(security_cv), float(immigration_cv))
        for security_cv in grid["security_cv_levels"]
        for immigration_cv in grid["immigration_cv_levels"]
    ]


def execution_scenario_ids(
    design_path: Path = DEFAULT_DESIGN,
) -> tuple[str, ...]:
    return tuple(
        service_variability_scenario_id(security_cv, immigration_cv)
        for security_cv, immigration_cv in study_cells(design_path)
    )


def canonical_service_scenario_bytes(row: Mapping[str, str]) -> bytes:
    """Canonical bytes for the study-local configuration lineage."""

    payload = {
        field: (row.get(field) or "").strip()
        for field in SERVICE_SCENARIO_COLUMNS
    }
    return (
        json.dumps(
            payload,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def service_scenario_config_sha256(row: Mapping[str, str]) -> str:
    """Hash the exact extended service-variability scenario row."""

    return hashlib.sha256(canonical_service_scenario_bytes(row)).hexdigest()


def build_service_variability_scenario_rows(
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

    rows: list[dict[str, str]] = []
    for security_cv, immigration_cv in study_cells(design_path):
        scenario_id = service_variability_scenario_id(
            security_cv,
            immigration_cv,
        )
        row = dict(reference)
        row.update(
            {
                "config_id": service_variability_config_id(
                    security_cv,
                    immigration_cv,
                ),
                "scenario_id": scenario_id,
                "scenario_family": "SERVICE_VARIABILITY",
                "description": (
                    "Mean-preserving service-variability sensitivity with "
                    f"Security CV={security_cv:g} and "
                    f"Immigration CV={immigration_cv:g}"
                ),
                "reference_scenario_id": REFERENCE_SCENARIO_ID,
                "arrival_mode": str(fixed["arrival_mode"]),
                "arrival_rate_per_second": str(
                    fixed["arrival_rate_per_second"]
                ),
                "demand_multiplier": str(fixed["demand_multiplier"]),
                "arrival_cutoff_seconds": str(
                    fixed["arrival_cutoff_seconds"]
                ),
                "arrival_guard": str(fixed["arrival_guard"]),
                "drain_rule": str(fixed["drain_rule"]),
                "security_capacity": str(fixed["security_capacity"]),
                "security_queue_capacity": str(
                    fixed["security_queue_capacity"]
                ),
                "security_service_distribution": (
                    "FIXED" if security_cv == 0.0 else "LOGNORMAL_MEAN_CV"
                ),
                "security_service_p1_seconds": str(
                    fixed["security_service_mean_seconds"]
                ),
                "immigration_capacity": str(
                    fixed["immigration_capacity"]
                ),
                "immigration_queue_capacity": str(
                    fixed["immigration_queue_capacity"]
                ),
                "immigration_service_distribution": (
                    "FIXED" if immigration_cv == 0.0 else "LOGNORMAL_MEAN_CV"
                ),
                "immigration_service_p1_seconds": str(
                    fixed["immigration_service_mean_seconds"]
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
                "input_status": "FROZEN_SERVICE_VARIABILITY_DESIGN",
                "calibration_status": "NOT_CALIBRATED",
                "claim_ceiling": "COMPARATIVE_WHAT_IF_ONLY",
                "notes": (
                    f"{STUDY_ID}; transparent service-shape sensitivity, "
                    "not an observed site distribution; paired interpretation "
                    "requires explicit CRN alignment PASS"
                ),
                "security_service_cv": _format_cv(security_cv),
                "immigration_service_cv": _format_cv(immigration_cv),
            }
        )
        if tuple(row) != SERVICE_SCENARIO_COLUMNS:
            raise ValueError(
                "derived service-variability row lost the extended schema"
            )
        rows.append(row)
    return rows


def build_service_variability_seed_rows(
    design_path: Path = DEFAULT_DESIGN,
    reference_seed_manifest_path: Path = DEFAULT_REFERENCE_SEED_MANIFEST,
) -> list[dict[str, str]]:
    scenario_ids = "|".join(execution_scenario_ids(design_path))
    rows: list[dict[str, str]] = []
    for source in _base_reference_seed_rows(reference_seed_manifest_path):
        replication = int(source["replication_id"])
        rows.append(
            {
                **source,
                "study_id": STUDY_ID,
                "pairing_group_id": f"SV_CRN_BASE_R{replication:03d}",
                "scenario_ids": scenario_ids,
            }
        )
    return rows


def write_generated_artifacts(
    *,
    scenarios_path: Path = DEFAULT_SCENARIOS,
    seed_manifest_path: Path = DEFAULT_SEED_MANIFEST,
) -> None:
    artifacts = (
        (
            scenarios_path,
            SERVICE_SCENARIO_COLUMNS,
            build_service_variability_scenario_rows(),
        ),
        (
            seed_manifest_path,
            SEED_COLUMNS,
            build_service_variability_seed_rows(),
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


def load_service_variability_scenario_rows(
    path: Path = DEFAULT_SCENARIOS,
) -> list[dict[str, str]]:
    fields, rows = _read_csv(path)
    if fields != SERVICE_SCENARIO_COLUMNS:
        raise ValueError(
            "service-variability scenario header is not canonical"
        )
    return [_clean(row) for row in rows]


def load_service_variability_seed_rows(
    path: Path = DEFAULT_SEED_MANIFEST,
) -> list[dict[str, str]]:
    fields, rows = _read_csv(path)
    if fields != SEED_COLUMNS:
        raise ValueError(
            "service-variability seed header is not canonical"
        )
    return [_clean(row) for row in rows]


def validate_service_variability_design(
    design_path: Path = DEFAULT_DESIGN,
    scenarios_path: Path = DEFAULT_SCENARIOS,
    seed_manifest_path: Path = DEFAULT_SEED_MANIFEST,
    operational_scenarios_path: Path = DEFAULT_OPERATIONAL_SCENARIOS,
    reference_seed_manifest_path: Path = DEFAULT_REFERENCE_SEED_MANIFEST,
) -> dict[str, object]:
    """Fail closed on the frozen grid, fixed means, hashes, and seed reuse."""

    design = load_design(design_path)
    errors: list[str] = []

    if design.get("schema_version") != "1.0":
        errors.append("schema_version must remain 1.0")
    if design.get("study_id") != STUDY_ID:
        errors.append("study_id drifted")
    if design.get("model_version") != MODEL_VERSION:
        errors.append("model_version drifted")
    if design.get("design_status") != "FROZEN_PRE_RUN":
        errors.append("design status must remain FROZEN_PRE_RUN")
    if design.get("analysis_role") != (
        "EXPLORATORY_ASSUMPTION_SENSITIVITY_NOT_CALIBRATION"
    ):
        errors.append("analysis role must remain explicitly exploratory")
    if design.get("claim_ceiling") != (
        "CONDITIONAL_SERVICE_VARIABILITY_SENSITIVITY_ONLY"
    ):
        errors.append("claim ceiling drifted")

    grid = design.get("service_cv_grid", {})
    security_levels = tuple(
        float(value) for value in grid.get("security_cv_levels", [])
    )
    immigration_levels = tuple(
        float(value) for value in grid.get("immigration_cv_levels", [])
    )
    if security_levels != CV_LEVELS:
        errors.append("Security CV grid must remain {0, 0.5, 1.0}")
    if immigration_levels != CV_LEVELS:
        errors.append("Immigration CV grid must remain {0, 0.5, 1.0}")

    distribution = design.get("distribution_contract", {})
    expected_distribution = {
        "zero_cv_distribution": "FIXED",
        "positive_cv_distribution": "LOGNORMAL_MEAN_CV",
        "p1_semantics": "ARITHMETIC_MEAN_SECONDS",
        "mean_preserving_formula": (
            "sigma2=ln(1+cv^2); "
            "service=mean*exp(-0.5*sigma2+sqrt(sigma2)*z)"
        ),
        "support": "STRICTLY_POSITIVE_FOR_CV_GT_ZERO",
    }
    for field, expected in expected_distribution.items():
        if distribution.get(field) != expected:
            errors.append(f"distribution_contract.{field} drifted")

    fixed = design.get("fixed_inputs", {})
    expected_fixed = {
        "arrival_mode": "HPP",
        "input_sample_id": INPUT_SAMPLE_ID,
        "arrival_rate_per_second": 1.3642132969720073,
        "demand_multiplier": 1.0,
        "arrival_cutoff_seconds": 300,
        "arrival_guard": 5000,
        "drain_rule": "FULL_DRAIN",
        "security_capacity": 36,
        "security_queue_capacity": 5000,
        "security_service_mean_seconds": 21.818181818,
        "immigration_capacity": 21,
        "immigration_queue_capacity": 5000,
        "immigration_service_mean_seconds": 13,
        "queue_policy": "pooled",
        "automation_mapping_mode": "DISABLED",
        "additional_check_semantics": "NONE",
        "start_state": "EMPTY_AND_IDLE",
    }
    for field, expected in expected_fixed.items():
        actual = fixed.get(field)
        if isinstance(expected, float):
            if not _equal_float(actual, expected):
                errors.append(f"fixed_inputs.{field} drifted")
        elif actual != expected:
            errors.append(f"fixed_inputs.{field} drifted")

    expected_rows: list[dict[str, str]] = []
    try:
        expected_rows = build_service_variability_scenario_rows(
            design_path,
            operational_scenarios_path,
            reference_seed_manifest_path,
        )
    except (FileNotFoundError, KeyError, ValueError) as exc:
        errors.append(str(exc))

    try:
        fields, raw_rows = _read_csv(scenarios_path)
    except FileNotFoundError:
        fields, raw_rows = (), []
        errors.append(f"missing file: {scenarios_path}")
    if fields != SERVICE_SCENARIO_COLUMNS:
        errors.append("service-variability scenario header is not canonical")
    rows = [_clean(row) for row in raw_rows]
    if rows != expected_rows:
        errors.append(
            "service-variability scenarios differ from deterministic design"
        )
    if len(rows) != 9:
        errors.append("service-variability design must contain exactly 9 cells")
    if len({row.get("scenario_id", "") for row in rows}) != len(rows):
        errors.append("service-variability scenario IDs are not unique")
    if len({service_scenario_config_sha256(row) for row in rows}) != len(rows):
        errors.append("extended service-variability hashes are not unique")

    expected_seed_rows: list[dict[str, str]] = []
    try:
        expected_seed_rows = build_service_variability_seed_rows(
            design_path,
            reference_seed_manifest_path,
        )
    except (FileNotFoundError, KeyError, ValueError) as exc:
        errors.append(str(exc))

    try:
        seed_fields, raw_seed_rows = _read_csv(seed_manifest_path)
    except FileNotFoundError:
        seed_fields, raw_seed_rows = (), []
        errors.append(f"missing file: {seed_manifest_path}")
    if seed_fields != SEED_COLUMNS:
        errors.append("service-variability seed header is not canonical")
    seed_rows = [_clean(row) for row in raw_seed_rows]
    if seed_rows != expected_seed_rows:
        errors.append(
            "service-variability seed rows do not exactly reuse Base tuples"
        )
    if len(seed_rows) != 50:
        errors.append("service-variability design needs exactly 50 seed groups")

    execution = design.get("execution", {})
    expected_counts = {
        "study_cell_count": 9,
        "replications_per_cell": 50,
        "total_runs": 450,
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
        "model_version": design.get("model_version"),
        "errors": errors,
        "scenario_count": len(rows),
        "seed_group_count": len(seed_rows),
        "run_count": len(rows) * len(seed_rows),
        "analysis_role": design.get("analysis_role"),
        "old_scenario_schema_unchanged": (
            SERVICE_SCENARIO_COLUMNS[:-2] == SCENARIO_COLUMNS
        ),
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
    report = validate_service_variability_design()
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
