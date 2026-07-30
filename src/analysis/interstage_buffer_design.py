"""Build and validate the frozen finite interstage-buffer study design.

This module registers only the design/configuration layer.  It deliberately
does not modify the AnyLogic runtime.  The study crosses two capacity regimes
with four declared Security-to-Immigration waiting-space levels while copying
the exact registered Base seed tuple for every replication.

The local ``interstage_buffer_capacity`` and
``interstage_blocking_policy`` fields are appended to the frozen operational
scenario schema.  They are bound by a study-local hash and must not be inserted
into the v1 operational schema.  The future runtime must implement true
blocking-after-service; lowering the existing Service block queue capacity is
explicitly outside this design contract.
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
DEFAULT_DESIGN = PROJECT_ROOT / "config" / "interstage_buffer_study.json"
DEFAULT_SCENARIOS = (
    PROJECT_ROOT / "config" / "interstage_buffer_scenarios.csv"
)
DEFAULT_SEED_MANIFEST = (
    PROJECT_ROOT / "config" / "interstage_buffer_seed_manifest.csv"
)
DEFAULT_REFERENCE_SEED_MANIFEST = (
    PROJECT_ROOT / "config" / "confirmatory_seed_manifest.csv"
)

STUDY_ID = "TASK3_INTERSTAGE_BUFFER_SPILLBACK_SENSITIVITY_V1"
MODEL_VERSION = "TASK3_OPERATIONAL_POOLED_INTERSTAGE_BAS_V1"
INPUT_SAMPLE_ID = "LOCAL_WINDOW_HPP_BASE"
BLOCKING_POLICY = "BAS_HOLD_SECURITY_UNTIL_BUFFER_SLOT"
BUFFER_LEVELS = (25, 50, 100, 5000)
REPLICATION_IDS = tuple(range(1, 51))
REGIMES = (
    (
        "IMMIGRATION_BOTTLENECK_POSITIVE",
        36,
        16,
        "CAPACITY_RESPONSE_S36_I16",
    ),
    (
        "SECURITY_BOTTLENECK_NEGATIVE_CONTROL",
        30,
        21,
        "CAPACITY_RESPONSE_S30_I21",
    ),
)

# The study-local fields are append-only.  Never mutate the frozen v1 schema.
INTERSTAGE_SCENARIO_COLUMNS = (
    *SCENARIO_COLUMNS,
    "capacity_regime_id",
    "interstage_buffer_capacity",
    "interstage_blocking_policy",
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


def _buffer_code(buffer_capacity: int) -> str:
    return f"{buffer_capacity:04d}"


def interstage_scenario_id(
    security_capacity: int,
    immigration_capacity: int,
    buffer_capacity: int,
) -> str:
    return (
        f"INTERSTAGE_BUFFER_S{security_capacity}_I{immigration_capacity}_"
        f"B{_buffer_code(buffer_capacity)}"
    )


def interstage_config_id(
    security_capacity: int,
    immigration_capacity: int,
    buffer_capacity: int,
) -> str:
    return (
        f"OP_INTERSTAGE_BUFFER_S{security_capacity}_I{immigration_capacity}_"
        f"B{_buffer_code(buffer_capacity)}"
    )


def study_cells(
    design_path: Path = DEFAULT_DESIGN,
) -> list[tuple[str, int, int, str, int]]:
    design = load_design(design_path)
    return [
        (
            str(regime["capacity_regime_id"]),
            int(regime["security_capacity"]),
            int(regime["immigration_capacity"]),
            str(regime["reference_scenario_id"]),
            int(buffer_capacity),
        )
        for regime in design["capacity_regimes"]
        for buffer_capacity in design["interstage_buffer_grid"][
            "capacity_levels"
        ]
    ]


def execution_scenario_ids(
    design_path: Path = DEFAULT_DESIGN,
) -> tuple[str, ...]:
    return tuple(
        interstage_scenario_id(security, immigration, buffer_capacity)
        for _, security, immigration, _, buffer_capacity in study_cells(
            design_path
        )
    )


def canonical_interstage_scenario_bytes(
    row: Mapping[str, str],
) -> bytes:
    """Canonical bytes for the extended interstage configuration lineage."""

    payload = {
        field: (row.get(field) or "").strip()
        for field in INTERSTAGE_SCENARIO_COLUMNS
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


def interstage_scenario_config_sha256(
    row: Mapping[str, str],
) -> str:
    """Hash the exact extended interstage-buffer scenario row."""

    return hashlib.sha256(
        canonical_interstage_scenario_bytes(row)
    ).hexdigest()


def build_interstage_buffer_scenario_rows(
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
    for (
        regime_id,
        security,
        immigration,
        source_reference,
        buffer_capacity,
    ) in study_cells(design_path):
        scenario_id = interstage_scenario_id(
            security,
            immigration,
            buffer_capacity,
        )
        row = dict(reference)
        row.update(
            {
                "config_id": interstage_config_id(
                    security,
                    immigration,
                    buffer_capacity,
                ),
                "scenario_id": scenario_id,
                "scenario_family": "INTERSTAGE_BUFFER",
                "description": (
                    "Finite Security-to-Immigration buffer sensitivity with "
                    f"{security} Security positions, {immigration} "
                    f"Immigration positions, and B={buffer_capacity}"
                ),
                "reference_scenario_id": source_reference,
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
                "security_capacity": str(security),
                "security_queue_capacity": str(
                    fixed["security_queue_capacity"]
                ),
                "security_service_distribution": str(
                    fixed["security_service_distribution"]
                ),
                "security_service_p1_seconds": str(
                    fixed["security_service_p1_seconds"]
                ),
                "immigration_capacity": str(immigration),
                "immigration_queue_capacity": str(
                    fixed["immigration_queue_capacity"]
                ),
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
                "input_status": "FROZEN_INTERSTAGE_BUFFER_DESIGN",
                "calibration_status": "NOT_CALIBRATED",
                "claim_ceiling": "COMPARATIVE_WHAT_IF_ONLY",
                "notes": (
                    f"{STUDY_ID}; B={buffer_capacity} is a declared "
                    "sensitivity assumption, not measured site capacity; "
                    "execution requires the separately reviewed BAS runtime; "
                    "paired interpretation requires exact CRN alignment PASS"
                ),
                "capacity_regime_id": regime_id,
                "interstage_buffer_capacity": str(buffer_capacity),
                "interstage_blocking_policy": BLOCKING_POLICY,
            }
        )
        if tuple(row) != INTERSTAGE_SCENARIO_COLUMNS:
            raise ValueError(
                "derived interstage-buffer row lost the extended schema"
            )
        rows.append(row)
    return rows


def build_interstage_buffer_seed_rows(
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
                "pairing_group_id": f"IB_CRN_BASE_R{replication:03d}",
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
            INTERSTAGE_SCENARIO_COLUMNS,
            build_interstage_buffer_scenario_rows(),
        ),
        (
            seed_manifest_path,
            SEED_COLUMNS,
            build_interstage_buffer_seed_rows(),
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


def load_interstage_buffer_scenario_rows(
    path: Path = DEFAULT_SCENARIOS,
) -> list[dict[str, str]]:
    fields, rows = _read_csv(path)
    if fields != INTERSTAGE_SCENARIO_COLUMNS:
        raise ValueError("interstage-buffer scenario header is not canonical")
    return [_clean(row) for row in rows]


def load_interstage_buffer_seed_rows(
    path: Path = DEFAULT_SEED_MANIFEST,
) -> list[dict[str, str]]:
    fields, rows = _read_csv(path)
    if fields != SEED_COLUMNS:
        raise ValueError("interstage-buffer seed header is not canonical")
    return [_clean(row) for row in rows]


def validate_interstage_buffer_design(
    design_path: Path = DEFAULT_DESIGN,
    scenarios_path: Path = DEFAULT_SCENARIOS,
    seed_manifest_path: Path = DEFAULT_SEED_MANIFEST,
    operational_scenarios_path: Path = DEFAULT_OPERATIONAL_SCENARIOS,
    reference_seed_manifest_path: Path = DEFAULT_REFERENCE_SEED_MANIFEST,
) -> dict[str, object]:
    """Fail closed on the two regimes, buffer grid, BAS contract, and seeds."""

    design = load_design(design_path)
    errors: list[str] = []

    expected_identity = {
        "schema_version": "1.0",
        "study_id": STUDY_ID,
        "model_version": MODEL_VERSION,
        "design_status": "FROZEN_PRE_RUN",
        "analysis_role": (
            "EXPLORATORY_ASSUMPTION_SENSITIVITY_NOT_CALIBRATION"
        ),
        "claim_ceiling": (
            "CONDITIONAL_INTERSTAGE_SPACE_SENSITIVITY_ONLY"
        ),
    }
    for field, expected in expected_identity.items():
        if design.get(field) != expected:
            errors.append(f"{field} drifted")

    actual_regimes = tuple(
        (
            str(row.get("capacity_regime_id")),
            int(row.get("security_capacity", -1)),
            int(row.get("immigration_capacity", -1)),
            str(row.get("reference_scenario_id")),
        )
        for row in design.get("capacity_regimes", [])
    )
    if actual_regimes != REGIMES:
        errors.append("the positive and negative capacity regimes drifted")

    buffer_grid = design.get("interstage_buffer_grid", {})
    actual_levels = tuple(
        int(value) for value in buffer_grid.get("capacity_levels", [])
    )
    if actual_levels != BUFFER_LEVELS:
        errors.append("buffer grid must remain 25, 50, 100, 5000")
    if buffer_grid.get("capacity_unit") != (
        "travellers_waiting_between_security_and_immigration"
    ):
        errors.append("interstage buffer capacity unit drifted")
    if buffer_grid.get("measured_site_capacity") is not False:
        errors.append("buffer levels must remain unmeasured sensitivities")
    if int(buffer_grid.get("factorial_cell_count", -1)) != 8:
        errors.append("buffer grid must contain exactly eight cells")

    blocking = design.get("blocking_contract", {})
    if blocking.get("policy_id") != BLOCKING_POLICY:
        errors.append("blocking-after-service policy drifted")
    if blocking.get("policy_name") != "BLOCKING_AFTER_SERVICE":
        errors.append("blocking policy name drifted")
    if blocking.get("required_runtime_parameter") != (
        "interstage_buffer_capacity"
    ):
        errors.append("required runtime parameter drifted")
    if blocking.get("implementation_status") != (
        "REQUIRES_SEPARATELY_REVIEWED_ANYLOGIC_RUNTIME_CHANGE"
    ):
        errors.append("runtime implementation boundary drifted")
    if "solely" not in str(blocking.get("forbidden_shortcut", "")):
        errors.append("forbidden queueCapacity shortcut is not explicit")

    output_contract = design.get("runtime_output_contract", {})
    replay_digest = output_contract.get("exact_replay_digest", {})
    if replay_digest.get("field") != "normalized_event_payload_sha256":
        errors.append("normalized exact-replay digest contract drifted")
    if "not the raw event-ledger" not in str(
        replay_digest.get("comparison_rule", "")
    ):
        errors.append("raw event-ledger digest exclusion is not explicit")

    blocking_metrics = output_contract.get("blocking_metrics", {})
    blocked_fraction = blocking_metrics.get(
        "security_blocked_resource_fraction",
        {},
    )
    if blocked_fraction.get("formula") != (
        "security_blocked_resource_seconds / "
        "(security_capacity * last_exit_seconds)"
    ):
        errors.append("security blocked-resource fraction formula drifted")
    if blocked_fraction.get("zero_denominator_value") != 0:
        errors.append(
            "security blocked-resource fraction zero rule drifted"
        )

    blocked_share = blocking_metrics.get(
        "security_blocked_share_of_occupied",
        {},
    )
    if blocked_share.get("formula") != (
        "security_blocked_resource_seconds / "
        "(security_busy_seconds + security_blocked_resource_seconds)"
    ):
        errors.append("security blocked occupied-share formula drifted")
    if blocked_share.get("zero_denominator_value") != 0:
        errors.append("security blocked occupied-share zero rule drifted")

    supporting_metrics = design.get("analysis", {}).get(
        "supporting_metrics",
        [],
    )
    for metric in (
        "security_blocked_resource_fraction",
        "security_blocked_share_of_occupied",
    ):
        if metric not in supporting_metrics:
            errors.append(f"analysis supporting metric missing: {metric}")

    fixed = design.get("fixed_inputs", {})
    expected_fixed = {
        "arrival_mode": "HPP",
        "input_sample_id": INPUT_SAMPLE_ID,
        "arrival_rate_per_second": 1.3642132969720073,
        "demand_multiplier": 1.0,
        "arrival_cutoff_seconds": 300,
        "arrival_guard": 5000,
        "drain_rule": "FULL_DRAIN",
        "security_queue_capacity": 5000,
        "security_service_distribution": "FIXED",
        "security_service_p1_seconds": 21.818181818,
        "immigration_queue_capacity": 5000,
        "immigration_service_distribution": "FIXED",
        "immigration_service_p1_seconds": 13,
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
        expected_rows = build_interstage_buffer_scenario_rows(
            design_path,
            operational_scenarios_path,
            reference_seed_manifest_path,
        )
    except (FileNotFoundError, KeyError, TypeError, ValueError) as exc:
        errors.append(str(exc))

    try:
        fields, raw_rows = _read_csv(scenarios_path)
    except FileNotFoundError:
        fields, raw_rows = (), []
        errors.append(f"missing file: {scenarios_path}")
    if fields != INTERSTAGE_SCENARIO_COLUMNS:
        errors.append("interstage-buffer scenario header is not canonical")
    rows = [_clean(row) for row in raw_rows]
    if rows != expected_rows:
        errors.append(
            "interstage-buffer scenarios differ from deterministic design"
        )
    if len(rows) != 8:
        errors.append("interstage-buffer design must contain exactly 8 cells")
    if len({row.get("scenario_id", "") for row in rows}) != len(rows):
        errors.append("interstage-buffer scenario IDs are not unique")
    if len(
        {interstage_scenario_config_sha256(row) for row in rows}
    ) != len(rows):
        errors.append("extended interstage-buffer hashes are not unique")
    for line, row in enumerate(rows, start=2):
        if row.get("security_queue_capacity") != "5000":
            errors.append(f"scenario line {line}: Security guard drifted")
        if row.get("immigration_queue_capacity") != "5000":
            errors.append(f"scenario line {line}: Immigration guard drifted")
        if row.get("interstage_blocking_policy") != BLOCKING_POLICY:
            errors.append(f"scenario line {line}: BAS policy drifted")
        if row.get("calibration_status") != "NOT_CALIBRATED":
            errors.append(f"scenario line {line}: calibration boundary drifted")
        if row.get("input_status") != "FROZEN_INTERSTAGE_BUFFER_DESIGN":
            errors.append(f"scenario line {line}: input status is not frozen")

    expected_seed_rows: list[dict[str, str]] = []
    try:
        expected_seed_rows = build_interstage_buffer_seed_rows(
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
        errors.append("interstage-buffer seed header is not canonical")
    seed_rows = [_clean(row) for row in raw_seed_rows]
    if seed_rows != expected_seed_rows:
        errors.append(
            "interstage-buffer seed rows do not exactly reuse Base tuples"
        )
    if len(seed_rows) != 50:
        errors.append("interstage-buffer design needs 50 seed groups")

    execution = design.get("execution", {})
    expected_counts = {
        "study_cell_count": 8,
        "replications_per_cell": 50,
        "total_runs": 400,
    }
    for field, expected in expected_counts.items():
        if int(execution.get(field, -1)) != expected:
            errors.append(f"execution.{field} must remain {expected}")
    if execution.get("parallel_evaluations") is not False:
        errors.append("parallel evaluations must remain disabled")
    if execution.get("adaptive_extension_allowed") is not False:
        errors.append("adaptive extension must remain disabled")

    calibration = design.get("calibration_boundary", {})
    for field in (
        "interstage_capacity_observed",
        "usable_floor_area_observed",
        "safe_density_observed",
        "physical_layout_calibrated",
        "site_forecast_claim",
        "observed_roster_claim",
        "staffing_recommendation_claim",
    ):
        if calibration.get(field) is not False:
            errors.append(f"calibration_boundary.{field} must remain false")

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
            INTERSTAGE_SCENARIO_COLUMNS[:-3] == SCENARIO_COLUMNS
        ),
        "runtime_change_required": (
            blocking.get("implementation_status")
            == "REQUIRES_SEPARATELY_REVIEWED_ANYLOGIC_RUNTIME_CHANGE"
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
    report = validate_interstage_buffer_design()
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
