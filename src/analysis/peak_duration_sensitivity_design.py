"""Build and validate the frozen selected-cell peak-duration design.

This module does not execute AnyLogic and does not modify the completed
300-second studies.  It freezes a separate Base-rate stationary-HPP extension
over four selected capacity cells and five terminating arrival windows.  The
generated scenario rows retain the canonical operational ``SCENARIO_COLUMNS``
contract and reuse the exact 50 Base seed tuples from the confirmatory study.
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
    scenario_config_sha256,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DESIGN = (
    PROJECT_ROOT / "config" / "peak_duration_sensitivity_study.json"
)
DEFAULT_SCENARIOS = (
    PROJECT_ROOT / "config" / "peak_duration_sensitivity_scenarios.csv"
)
DEFAULT_SEED_MANIFEST = (
    PROJECT_ROOT / "config" / "peak_duration_sensitivity_seed_manifest.csv"
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

EXPECTED_BASE_RATE = 1.3642132969720073
EXPECTED_TARGET_INPUT_SAMPLE_ID = (
    "LOCAL_WINDOW_HPP_BASE_STATIONARY_EXTENSION"
)
EXPECTED_CAPACITY_CELLS = (
    (36, 21),
    (30, 18),
    (29, 17),
    (28, 16),
)
EXPECTED_CUTOFF_SECONDS = (300, 900, 1800, 3600, 7200)
EXPECTED_REPLICATIONS_PER_CELL = 50
EXPECTED_STUDY_CELL_COUNT = 20
EXPECTED_RUN_COUNT = 1000
EXPECTED_GUARDS = {
    300: 5000,
    900: 5000,
    1800: 5000,
    3600: 5712,
    7200: 10914,
}


def _read_csv(path: Path) -> tuple[tuple[str, ...], list[dict[str, str]]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return tuple(reader.fieldnames or ()), [dict(row) for row in reader]


def _clean(row: Mapping[str, str]) -> dict[str, str]:
    return {key: (value or "").strip() for key, value in row.items()}


def load_design(path: Path = DEFAULT_DESIGN) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def arrival_guard(
    arrival_rate_per_second: float,
    cutoff_seconds: int,
    *,
    minimum_guard: int = 5000,
    standard_deviation_multiples: float = 10.0,
    fixed_margin: int = 100,
) -> int:
    """Return the registered non-binding HPP arrival/queue safety guard."""

    if (
        not math.isfinite(arrival_rate_per_second)
        or arrival_rate_per_second <= 0
    ):
        raise ValueError("arrival_rate_per_second must be finite and positive")
    if cutoff_seconds <= 0:
        raise ValueError("cutoff_seconds must be positive")
    if minimum_guard <= 0 or fixed_margin < 0:
        raise ValueError("guard floor must be positive and margin non-negative")
    if (
        not math.isfinite(standard_deviation_multiples)
        or standard_deviation_multiples < 0
    ):
        raise ValueError(
            "standard_deviation_multiples must be finite and non-negative"
        )

    mean_arrivals = arrival_rate_per_second * cutoff_seconds
    candidate = (
        mean_arrivals
        + standard_deviation_multiples * math.sqrt(mean_arrivals)
        + fixed_margin
    )
    return int(math.ceil(max(float(minimum_guard), candidate)))


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
    if len(base) != EXPECTED_REPLICATIONS_PER_CELL:
        raise ValueError("reference manifest must contain 50 Base seed groups")
    if {row["replication_id"] for row in base} != {
        str(value) for value in range(1, 51)
    }:
        raise ValueError("Base seed groups must be replications 1..50")
    return base


def selected_capacity_cells(
    design_path: Path = DEFAULT_DESIGN,
) -> list[tuple[int, int]]:
    design = load_design(design_path)
    return [
        (
            int(row["security_capacity"]),
            int(row["immigration_capacity"]),
        )
        for row in design["selected_capacity_cells"]
    ]


def cutoff_seconds(
    design_path: Path = DEFAULT_DESIGN,
) -> list[int]:
    design = load_design(design_path)
    return [
        int(value)
        for value in design["arrival_window"]["cutoff_seconds"]
    ]


def execution_cells(
    design_path: Path = DEFAULT_DESIGN,
) -> list[tuple[int, int, int]]:
    return [
        (security, immigration, cutoff)
        for security, immigration in selected_capacity_cells(design_path)
        for cutoff in cutoff_seconds(design_path)
    ]


def duration_scenario_id(
    security_capacity: int,
    immigration_capacity: int,
    arrival_cutoff_seconds: int,
) -> str:
    return (
        f"PEAK_DURATION_S{security_capacity}_I{immigration_capacity}"
        f"_T{arrival_cutoff_seconds}"
    )


def execution_scenario_ids(
    design_path: Path = DEFAULT_DESIGN,
) -> tuple[str, ...]:
    return tuple(
        duration_scenario_id(security, immigration, cutoff)
        for security, immigration, cutoff in execution_cells(design_path)
    )


def _guard_parameters(
    design: Mapping[str, object],
) -> tuple[int, float, int]:
    policy = design["guard_policy"]
    if not isinstance(policy, Mapping):
        raise ValueError("guard_policy must be an object")
    return (
        int(policy["minimum_guard"]),
        float(policy["standard_deviation_multiples"]),
        int(policy["fixed_margin"]),
    )


def build_peak_duration_scenario_rows(
    design_path: Path = DEFAULT_DESIGN,
    operational_scenarios_path: Path = DEFAULT_OPERATIONAL_SCENARIOS,
    reference_seed_manifest_path: Path = DEFAULT_REFERENCE_SEED_MANIFEST,
) -> list[dict[str, str]]:
    """Derive the 4-by-5 execution grid from the registered reference row."""

    design = load_design(design_path)
    fixed = design["fixed_inputs"]
    reference = _reference_scenario_row(operational_scenarios_path)
    seed_rows = _base_reference_seed_rows(reference_seed_manifest_path)
    master_seeds = {row["master_seed"] for row in seed_rows}
    if len(master_seeds) != 1:
        raise ValueError("Base seed groups have multiple master seeds")
    master_seed = master_seeds.pop()
    study_id = str(design["study_id"])
    replications = str(design["execution"]["replications_per_cell"])
    rate = float(fixed["arrival_rate_per_second"])
    minimum, multiples, margin = _guard_parameters(design)

    rows: list[dict[str, str]] = []
    for security, immigration, cutoff in execution_cells(design_path):
        guard = arrival_guard(
            rate,
            cutoff,
            minimum_guard=minimum,
            standard_deviation_multiples=multiples,
            fixed_margin=margin,
        )
        scenario_id = duration_scenario_id(
            security,
            immigration,
            cutoff,
        )
        row = dict(reference)
        row.update(
            {
                "config_id": (
                    f"OP_PEAK_DURATION_BASE_S{security}_I{immigration}"
                    f"_T{cutoff}"
                ),
                "scenario_id": scenario_id,
                "scenario_family": "PEAK_DURATION",
                "description": (
                    "Exploratory Base-rate stationary-HPP duration cell with "
                    f"{security} Security and {immigration} Immigration "
                    f"positions open for a {cutoff}-second arrival window"
                ),
                "arrival_mode": "HPP",
                "arrival_rate_per_second": str(
                    fixed["arrival_rate_per_second"]
                ),
                "demand_multiplier": "1.0",
                "arrival_cutoff_seconds": str(cutoff),
                "arrival_guard": str(guard),
                "drain_rule": str(fixed["drain_rule"]),
                "security_capacity": str(security),
                "security_queue_capacity": str(guard),
                "security_service_distribution": str(
                    fixed["security_service_distribution"]
                ),
                "security_service_p1_seconds": str(
                    fixed["security_service_p1_seconds"]
                ),
                "immigration_capacity": str(immigration),
                "immigration_queue_capacity": str(guard),
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
                "input_status": (
                    "FROZEN_PEAK_DURATION_SENSITIVITY_DESIGN"
                ),
                "calibration_status": "NOT_CALIBRATED",
                "claim_ceiling": "COMPARATIVE_WHAT_IF_ONLY",
                "notes": (
                    f"{study_id}; post-outcome exploratory duration "
                    "sensitivity; stationary short-window HPP rate is "
                    "extended as a controlled assumption, not an observed "
                    "peak or time-of-day profile; capacity is concurrently "
                    "open service positions, not an observed roster; paired "
                    "interpretation requires exact CRN alignment PASS"
                ),
            }
        )
        if tuple(row) != SCENARIO_COLUMNS:
            raise ValueError("derived duration row lost the canonical schema")
        rows.append(row)
    return rows


def build_peak_duration_seed_rows(
    design_path: Path = DEFAULT_DESIGN,
    reference_seed_manifest_path: Path = DEFAULT_REFERENCE_SEED_MANIFEST,
) -> list[dict[str, str]]:
    """Reuse each registered Base seed tuple across all 20 duration cells."""

    design = load_design(design_path)
    scenario_ids = "|".join(execution_scenario_ids(design_path))
    return [
        {
            **row,
            "study_id": str(design["study_id"]),
            "input_sample_id": str(
                design["fixed_inputs"]["input_sample_id"]
            ),
            "scenario_ids": scenario_ids,
        }
        for row in _base_reference_seed_rows(reference_seed_manifest_path)
    ]


def write_generated_artifacts(
    *,
    design_path: Path = DEFAULT_DESIGN,
    scenarios_path: Path = DEFAULT_SCENARIOS,
    seed_manifest_path: Path = DEFAULT_SEED_MANIFEST,
    operational_scenarios_path: Path = DEFAULT_OPERATIONAL_SCENARIOS,
    reference_seed_manifest_path: Path = DEFAULT_REFERENCE_SEED_MANIFEST,
) -> None:
    artifacts = (
        (
            scenarios_path,
            SCENARIO_COLUMNS,
            build_peak_duration_scenario_rows(
                design_path,
                operational_scenarios_path,
                reference_seed_manifest_path,
            ),
        ),
        (
            seed_manifest_path,
            SEED_COLUMNS,
            build_peak_duration_seed_rows(
                design_path,
                reference_seed_manifest_path,
            ),
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


def load_peak_duration_scenario_rows(
    path: Path = DEFAULT_SCENARIOS,
) -> list[dict[str, str]]:
    fields, rows = _read_csv(path)
    if fields != SCENARIO_COLUMNS:
        raise ValueError("peak-duration scenario header is not canonical")
    return [_clean(row) for row in rows]


def load_peak_duration_seed_rows(
    path: Path = DEFAULT_SEED_MANIFEST,
) -> list[dict[str, str]]:
    fields, rows = _read_csv(path)
    if fields != SEED_COLUMNS:
        raise ValueError("peak-duration seed header is not canonical")
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


def validate_peak_duration_design(
    design_path: Path = DEFAULT_DESIGN,
    scenarios_path: Path = DEFAULT_SCENARIOS,
    seed_manifest_path: Path = DEFAULT_SEED_MANIFEST,
    operational_scenarios_path: Path = DEFAULT_OPERATIONAL_SCENARIOS,
    reference_seed_manifest_path: Path = DEFAULT_REFERENCE_SEED_MANIFEST,
) -> dict[str, object]:
    """Fail closed on the frozen duration grid, guards, seeds, and boundaries."""

    design = load_design(design_path)
    errors: list[str] = []

    if design.get("design_status") != "FROZEN_PRE_RUN":
        errors.append("design status must remain FROZEN_PRE_RUN")
    if design.get("execution_status") != "NOT_EXECUTED":
        errors.append("execution status must remain NOT_EXECUTED before runs")
    if design.get("analysis_role") != (
        "EXPLORATORY_DURATION_SENSITIVITY_NOT_CONFIRMATORY"
    ):
        errors.append("analysis role must remain explicitly exploratory")

    fixed = design.get("fixed_inputs", {})
    if fixed.get("arrival_mode") != "HPP":
        errors.append("arrival mode must remain stationary HPP")
    if not _equal_float(
        fixed.get("arrival_rate_per_second"),
        EXPECTED_BASE_RATE,
    ):
        errors.append("Base arrival rate drifted")
    if fixed.get("input_sample_id") != EXPECTED_TARGET_INPUT_SAMPLE_ID:
        errors.append("stationary-extension input identity drifted")
    if fixed.get("start_state") != "EMPTY_AND_IDLE":
        errors.append("start state must remain EMPTY_AND_IDLE")
    if fixed.get("drain_rule") != "FULL_DRAIN":
        errors.append("drain rule must remain FULL_DRAIN")
    if fixed.get("queue_policy") != "pooled":
        errors.append("queue policy must remain pooled")
    if fixed.get("security_service_distribution") != "FIXED":
        errors.append("Security service distribution must remain FIXED")
    if fixed.get("immigration_service_distribution") != "FIXED":
        errors.append("Immigration service distribution must remain FIXED")

    seed_policy = design.get("seed_policy", {})
    if seed_policy.get("source_arrival_level_id") != "MLE_BASE":
        errors.append("seed source arrival level must remain MLE_BASE")
    if seed_policy.get("source_input_sample_id") != "LOCAL_WINDOW_HPP_BASE":
        errors.append("seed source input identity must remain the local Base")
    if seed_policy.get("target_input_sample_id") != (
        EXPECTED_TARGET_INPUT_SAMPLE_ID
    ):
        errors.append("seed target stationary-extension identity drifted")

    try:
        actual_capacities = tuple(selected_capacity_cells(design_path))
    except (KeyError, TypeError, ValueError) as exc:
        actual_capacities = ()
        errors.append(f"selected capacity cells are malformed: {exc}")
    if actual_capacities != EXPECTED_CAPACITY_CELLS:
        errors.append(
            "selected capacity cells must remain "
            "36/21, 30/18, 29/17, and 28/16 in that order"
        )

    try:
        actual_cutoffs = tuple(cutoff_seconds(design_path))
    except (KeyError, TypeError, ValueError) as exc:
        actual_cutoffs = ()
        errors.append(f"arrival cutoffs are malformed: {exc}")
    if actual_cutoffs != EXPECTED_CUTOFF_SECONDS:
        errors.append(
            "cutoffs must remain 300, 900, 1800, 3600, and 7200 seconds"
        )

    guard_policy = design.get("guard_policy", {})
    expected_formula = (
        "ceil(max(5000, lambda*T + 10*sqrt(lambda*T) + 100))"
    )
    if guard_policy.get("formula") != expected_formula:
        errors.append("registered guard formula drifted")
    if int(guard_policy.get("minimum_guard", -1)) != 5000:
        errors.append("guard floor must remain 5000")
    if not _equal_float(
        guard_policy.get("standard_deviation_multiples"),
        10.0,
    ):
        errors.append("guard standard-deviation multiple must remain 10")
    if int(guard_policy.get("fixed_margin", -1)) != 100:
        errors.append("guard fixed margin must remain 100")
    if guard_policy.get("queue_capacity_rule") != (
        "security_queue_capacity = immigration_queue_capacity = arrival_guard"
    ):
        errors.append("both queue capacities must stay synchronized to guard")
    configured_guards = {
        int(row["cutoff_seconds"]): int(row["arrival_and_queue_guard"])
        for row in guard_policy.get("computed_values", [])
    }
    if configured_guards != EXPECTED_GUARDS:
        errors.append("precomputed arrival/queue guards drifted")
    for cutoff, expected in EXPECTED_GUARDS.items():
        if arrival_guard(EXPECTED_BASE_RATE, cutoff) != expected:
            errors.append(f"guard arithmetic drifted at cutoff {cutoff}")

    expected_cells = [
        (security, immigration, cutoff)
        for security, immigration in EXPECTED_CAPACITY_CELLS
        for cutoff in EXPECTED_CUTOFF_SECONDS
    ]
    if execution_cells(design_path) != expected_cells:
        errors.append("execution cell ordering drifted")
    expected_ids = tuple(
        duration_scenario_id(*cell) for cell in expected_cells
    )

    try:
        scenario_fields, raw_scenario_rows = _read_csv(scenarios_path)
    except FileNotFoundError:
        scenario_fields, raw_scenario_rows = (), []
        errors.append(f"missing file: {scenarios_path}")
    if scenario_fields != SCENARIO_COLUMNS:
        errors.append("peak-duration scenario header is not canonical")
    scenario_rows = [_clean(row) for row in raw_scenario_rows]
    if len(scenario_rows) != EXPECTED_STUDY_CELL_COUNT:
        errors.append("peak-duration scenario count must remain 20")

    seen_ids: set[str] = set()
    seen_hashes: set[str] = set()
    seen_cells: set[tuple[int, int, int]] = set()
    for line, row in enumerate(scenario_rows, start=2):
        scenario_id = row.get("scenario_id", "")
        if scenario_id in seen_ids:
            errors.append(f"scenario line {line}: duplicate scenario_id")
        seen_ids.add(scenario_id)
        try:
            cell = (
                int(row.get("security_capacity", "-1")),
                int(row.get("immigration_capacity", "-1")),
                int(row.get("arrival_cutoff_seconds", "-1")),
            )
        except ValueError:
            errors.append(f"scenario line {line}: invalid capacity or cutoff")
            continue
        if cell in seen_cells:
            errors.append(f"scenario line {line}: duplicate study cell")
        seen_cells.add(cell)
        if cell not in expected_cells:
            errors.append(f"scenario line {line}: cell is outside frozen grid")
        if scenario_id != duration_scenario_id(*cell):
            errors.append(f"scenario line {line}: scenario_id/cell mismatch")
        guard = EXPECTED_GUARDS.get(cell[2])
        if guard is not None:
            for field in (
                "arrival_guard",
                "security_queue_capacity",
                "immigration_queue_capacity",
            ):
                if row.get(field) != str(guard):
                    errors.append(
                        f"scenario line {line}: {field} is not guard {guard}"
                    )
        if row.get("input_sample_id") != EXPECTED_TARGET_INPUT_SAMPLE_ID:
            errors.append(
                f"scenario line {line}: stationary-extension identity drift"
            )
        if not _equal_float(
            row.get("arrival_rate_per_second"),
            EXPECTED_BASE_RATE,
        ):
            errors.append(f"scenario line {line}: Base arrival-rate drift")
        if row.get("pilot_replications") != "50":
            errors.append(f"scenario line {line}: replication-count drift")
        if row.get("input_status") != (
            "FROZEN_PEAK_DURATION_SENSITIVITY_DESIGN"
        ):
            errors.append(f"scenario line {line}: input status is not frozen")
        if row.get("calibration_status") != "NOT_CALIBRATED":
            errors.append(f"scenario line {line}: calibration boundary drift")
        digest = scenario_config_sha256(row)
        if digest in seen_hashes:
            errors.append(f"scenario line {line}: duplicate canonical hash")
        seen_hashes.add(digest)
    if seen_cells != set(expected_cells):
        errors.append("execution scenario grid is incomplete")
    if tuple(row.get("scenario_id", "") for row in scenario_rows) != (
        expected_ids
    ):
        errors.append("execution scenario ordering drifted")

    try:
        built_scenarios = build_peak_duration_scenario_rows(
            design_path,
            operational_scenarios_path,
            reference_seed_manifest_path,
        )
    except (FileNotFoundError, KeyError, TypeError, ValueError) as exc:
        built_scenarios = []
        errors.append(f"could not derive frozen scenarios: {exc}")
    if scenario_rows != built_scenarios:
        errors.append("scenario CSV does not equal the frozen derivation")

    try:
        seed_fields, raw_seed_rows = _read_csv(seed_manifest_path)
    except FileNotFoundError:
        seed_fields, raw_seed_rows = (), []
        errors.append(f"missing file: {seed_manifest_path}")
    if seed_fields != SEED_COLUMNS:
        errors.append("peak-duration seed header is not canonical")
    seed_rows = [_clean(row) for row in raw_seed_rows]
    try:
        source_rows = _base_reference_seed_rows(
            reference_seed_manifest_path
        )
    except (FileNotFoundError, ValueError) as exc:
        source_rows = []
        errors.append(f"could not load Base seed groups: {exc}")
    source_by_replication = {
        row["replication_id"]: row for row in source_rows
    }
    expected_scenarios = "|".join(expected_ids)
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
        if row.get("input_sample_id") != EXPECTED_TARGET_INPUT_SAMPLE_ID:
            errors.append(
                f"seed line {line}: stationary-extension identity drift"
            )
        if row.get("scenario_ids") != expected_scenarios:
            errors.append(f"seed line {line}: scenario ordering drift")
        for field in (
            "pairing_group_id",
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

    try:
        built_seeds = build_peak_duration_seed_rows(
            design_path,
            reference_seed_manifest_path,
        )
    except (FileNotFoundError, KeyError, TypeError, ValueError) as exc:
        built_seeds = []
        errors.append(f"could not derive frozen seed manifest: {exc}")
    if seed_rows != built_seeds:
        errors.append("seed CSV does not equal the frozen Base-seed derivation")

    execution = design.get("execution", {})
    expected_counts = {
        "selected_capacity_cell_count": 4,
        "duration_level_count": 5,
        "study_cell_count": EXPECTED_STUDY_CELL_COUNT,
        "replications_per_cell": EXPECTED_REPLICATIONS_PER_CELL,
        "planned_run_count": EXPECTED_RUN_COUNT,
    }
    for field, expected in expected_counts.items():
        if int(execution.get(field, -1)) != expected:
            errors.append(f"execution.{field} must remain {expected}")
    if execution.get("parallel_evaluations") is not False:
        errors.append("parallel evaluations must remain disabled")
    if execution.get("adaptive_extension_allowed") is not False:
        errors.append("adaptive extension must remain disabled")
    if execution.get("completed_run_count") != 0:
        errors.append("completed_run_count must remain zero before execution")

    boundary = design.get("calibration_boundary", {})
    for field in (
        "stationary_rate_extension_is_observed_peak",
        "time_of_day_profile_claim",
        "steady_state_claim",
        "site_forecast_claim",
        "observed_roster_claim",
        "physical_queue_capacity_claim",
        "staffing_recommendation_claim",
    ):
        if boundary.get(field) is not False:
            errors.append(f"calibration_boundary.{field} must remain false")

    return {
        "status": "PASS" if not errors else "FAIL",
        "study_id": design.get("study_id"),
        "errors": errors,
        "selected_capacity_cell_count": len(actual_capacities),
        "duration_level_count": len(actual_cutoffs),
        "study_cell_count": len(expected_cells),
        "seed_group_count": len(seed_rows),
        "planned_run_count": len(expected_cells)
        * EXPECTED_REPLICATIONS_PER_CELL,
        "execution_status": design.get("execution_status"),
        "analysis_role": design.get("analysis_role"),
        "guard_by_cutoff_seconds": EXPECTED_GUARDS,
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
    report = validate_peak_duration_design()
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
