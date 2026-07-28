"""Build and validate the frozen Part 2 capacity-availability study.

Part 1 asks whether additional service capacity changes performance.  This
study keeps those results immutable and asks the complementary operational
question: what happens to waiting queues when fewer service positions are
available?

The four reduced-capacity arms are new executions.  The 36/21 reference is
reused from the frozen Part 1 study only when its configuration lineage and
the complete exogenous seed tuple align.  Capacity means concurrently open
service positions; it is not evidence of an observed roster or installed
estate.
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
    PROJECT_ROOT / "config" / "capacity_availability_study.json"
)
DEFAULT_SCENARIOS = (
    PROJECT_ROOT / "config" / "capacity_availability_scenarios.csv"
)
DEFAULT_SCENARIO_PROVENANCE = (
    PROJECT_ROOT
    / "config"
    / "capacity_availability_scenario_provenance.csv"
)
DEFAULT_SEED_MANIFEST = (
    PROJECT_ROOT / "config" / "capacity_availability_seed_manifest.csv"
)
DEFAULT_ANALYSIS_SEED_MANIFEST = (
    PROJECT_ROOT
    / "config"
    / "capacity_availability_analysis_seed_manifest.csv"
)
DEFAULT_REFERENCE_SEED_MANIFEST = (
    PROJECT_ROOT / "config" / "confirmatory_seed_manifest.csv"
)

EXECUTION_SCENARIO_IDS = (
    "CAPACITY_AVAIL_SECURITY_MINUS_4",
    "CAPACITY_AVAIL_IMMIGRATION_MINUS_3",
    "CAPACITY_AVAIL_JOINT_MINUS_4_MINUS_3",
    "CAPACITY_AVAIL_SEVERE_JOINT_30_17",
)
ANALYSIS_SCENARIO_IDS = (REFERENCE_SCENARIO_ID, *EXECUTION_SCENARIO_IDS)
ARRIVAL_LEVEL_IDS = ("EXACT95_LOW", "MLE_BASE", "EXACT95_HIGH")
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
SCENARIO_PROVENANCE_COLUMNS = (
    "scenario_id",
    "parameter_name",
    "parameter_value",
    "unit",
    "provenance_id",
    "mapping_role",
    "notes",
)


def _read_csv(path: Path) -> tuple[tuple[str, ...], list[dict[str, str]]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return tuple(reader.fieldnames or ()), [dict(row) for row in reader]


def _clean(row: Mapping[str, str]) -> dict[str, str]:
    return {key: (value or "").strip() for key, value in row.items()}


def _load_design(path: Path = DEFAULT_DESIGN) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _reference_scenario_row(
    operational_scenarios_path: Path = DEFAULT_OPERATIONAL_SCENARIOS,
) -> dict[str, str]:
    fields, rows = _read_csv(operational_scenarios_path)
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


def build_capacity_availability_scenario_rows(
    design_path: Path = DEFAULT_DESIGN,
    operational_scenarios_path: Path = DEFAULT_OPERATIONAL_SCENARIOS,
) -> list[dict[str, str]]:
    """Derive the 3-by-4 execution grid from the registered reference row."""

    design = _load_design(design_path)
    reference = _reference_scenario_row(operational_scenarios_path)
    levels = design["arrival_rate_uncertainty"]["levels"]
    arms = design["execution_arms"]
    replications = str(design["run_cap"]["replications_per_cell"])
    study_id = str(design["study_id"])
    master_seed = _reference_seed_master(
        Path(
            str(design["seed_policy"]["reuse_source_manifest"])
        )
        if Path(
            str(design["seed_policy"]["reuse_source_manifest"])
        ).is_absolute()
        else PROJECT_ROOT
        / str(design["seed_policy"]["reuse_source_manifest"])
    )

    rows: list[dict[str, str]] = []
    for level in levels:
        level_id = str(level["level_id"])
        input_sample_id = str(level["input_sample_id"])
        for arm in arms:
            scenario_id = str(arm["scenario_id"])
            row = dict(reference)
            row.update(
                {
                    "config_id": f"OP_AVAIL_{level_id}_{scenario_id}",
                    "scenario_id": scenario_id,
                    "scenario_family": "CAPACITY",
                    "description": (
                        "Capacity-availability stress cell with "
                        f"{arm['security_capacity']} Security and "
                        f"{arm['immigration_capacity']} Immigration "
                        "positions open"
                    ),
                    "arrival_rate_per_second": str(
                        level["arrival_rate_per_second"]
                    ),
                    "demand_multiplier": "1.0",
                    "security_capacity": str(arm["security_capacity"]),
                    "immigration_capacity": str(
                        arm["immigration_capacity"]
                    ),
                    "input_sample_id": input_sample_id,
                    "pilot_replications": replications,
                    "master_seed": str(master_seed),
                    "crn_alignment_status": "PENDING_VALIDATION",
                    "input_status": (
                        "FROZEN_CAPACITY_AVAILABILITY_DESIGN"
                    ),
                    "calibration_status": "NOT_CALIBRATED",
                    "claim_ceiling": "COMPARATIVE_WHAT_IF_ONLY",
                    "notes": (
                        f"{study_id} {level_id}; capacity is concurrently "
                        "open service positions, not an observed roster; "
                        "paired analysis requires explicit alignment PASS"
                    ),
                }
            )
            if tuple(row) != SCENARIO_COLUMNS:
                raise ValueError(
                    "derived availability row lost the canonical schema"
                )
            rows.append(row)
    return rows


def _reference_seed_master(path: Path) -> int:
    fields, rows = _read_csv(path)
    if fields != SEED_COLUMNS or not rows:
        raise ValueError("reference seed manifest is missing or malformed")
    masters = {int(row["master_seed"]) for row in rows}
    if len(masters) != 1:
        raise ValueError("reference seed manifest has multiple master seeds")
    return masters.pop()


def build_capacity_availability_seed_rows(
    design_path: Path = DEFAULT_DESIGN,
    reference_seed_manifest_path: Path = DEFAULT_REFERENCE_SEED_MANIFEST,
) -> list[dict[str, str]]:
    """Copy every Part 1 seed tuple while replacing only study/arm labels."""

    design = _load_design(design_path)
    fields, source_rows = _read_csv(reference_seed_manifest_path)
    if fields != SEED_COLUMNS:
        raise ValueError("reference seed manifest header is not canonical")
    scenario_ids = "|".join(EXECUTION_SCENARIO_IDS)
    study_id = str(design["study_id"])
    return [
        {
            **_clean(source),
            "study_id": study_id,
            "scenario_ids": scenario_ids,
        }
        for source in source_rows
    ]


def build_capacity_availability_analysis_seed_rows(
    design_path: Path = DEFAULT_DESIGN,
    reference_seed_manifest_path: Path = DEFAULT_REFERENCE_SEED_MANIFEST,
) -> list[dict[str, str]]:
    """Build the five-arm seed groups used by the merged CRN gate."""

    rows = build_capacity_availability_seed_rows(
        design_path,
        reference_seed_manifest_path,
    )
    scenario_ids = "|".join(ANALYSIS_SCENARIO_IDS)
    return [{**row, "scenario_ids": scenario_ids} for row in rows]


def build_capacity_availability_provenance_rows(
    design_path: Path = DEFAULT_DESIGN,
) -> list[dict[str, str]]:
    """Return capacity-only lineage, including the derived 36/21 reference."""

    design = _load_design(design_path)
    semantics = design["capacity_semantics"]
    provenance_id = str(semantics["reference_provenance_id"])
    boundary = str(semantics["reference_claim_boundary"])
    rows = [
        {
            "scenario_id": REFERENCE_SCENARIO_ID,
            "parameter_name": "security_capacity",
            "parameter_value": str(
                semantics["reference_security_capacity"]
            ),
            "unit": "concurrently_open_service_positions",
            "provenance_id": provenance_id,
            "mapping_role": "DERIVED",
            "notes": (
                "Target-utilisation-derived reference using "
                "ceil(lambda*mean_service/0.85). "
                f"{boundary}"
            ),
        },
        {
            "scenario_id": REFERENCE_SCENARIO_ID,
            "parameter_name": "immigration_capacity",
            "parameter_value": str(
                semantics["reference_immigration_capacity"]
            ),
            "unit": "concurrently_open_service_positions",
            "provenance_id": provenance_id,
            "mapping_role": "DERIVED",
            "notes": (
                "Target-utilisation-derived reference using "
                "ceil(lambda*mean_service/0.85). "
                f"{boundary}"
            ),
        },
    ]
    for arm in design["execution_arms"]:
        for parameter in ("security_capacity", "immigration_capacity"):
            reference_value = int(
                semantics[f"reference_{parameter}"]
            )
            value = int(arm[parameter])
            if value == reference_value:
                continue
            rows.append(
                {
                    "scenario_id": str(arm["scenario_id"]),
                    "parameter_name": parameter,
                    "parameter_value": str(value),
                    "unit": "concurrently_open_service_positions",
                    "provenance_id": provenance_id,
                    "mapping_role": "ILLUSTRATIVE_SCENARIO",
                    "notes": (
                        f"Reference-relative experimental reduction from "
                        f"{reference_value} to {value}; not observed staff "
                        "roster, installed capacity, or recommendation."
                    ),
                }
            )
    return rows


def write_generated_artifacts(
    *,
    scenarios_path: Path = DEFAULT_SCENARIOS,
    scenario_provenance_path: Path = DEFAULT_SCENARIO_PROVENANCE,
    seed_manifest_path: Path = DEFAULT_SEED_MANIFEST,
    analysis_seed_manifest_path: Path = DEFAULT_ANALYSIS_SEED_MANIFEST,
) -> None:
    """Write deterministic CSV artifacts derived from the frozen JSON."""

    artifacts = (
        (
            scenarios_path,
            SCENARIO_COLUMNS,
            build_capacity_availability_scenario_rows(),
        ),
        (
            scenario_provenance_path,
            SCENARIO_PROVENANCE_COLUMNS,
            build_capacity_availability_provenance_rows(),
        ),
        (
            seed_manifest_path,
            SEED_COLUMNS,
            build_capacity_availability_seed_rows(),
        ),
        (
            analysis_seed_manifest_path,
            SEED_COLUMNS,
            build_capacity_availability_analysis_seed_rows(),
        ),
    )
    for path, fields, rows in artifacts:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle, fieldnames=fields, lineterminator="\n"
            )
            writer.writeheader()
            writer.writerows(rows)


def load_capacity_availability_scenario_rows(
    path: Path = DEFAULT_SCENARIOS,
) -> list[dict[str, str]]:
    fields, rows = _read_csv(path)
    if fields != SCENARIO_COLUMNS:
        raise ValueError("capacity-availability scenario header is not canonical")
    return [_clean(row) for row in rows]


def load_capacity_availability_seed_rows(
    path: Path = DEFAULT_SEED_MANIFEST,
) -> list[dict[str, str]]:
    fields, rows = _read_csv(path)
    if fields != SEED_COLUMNS:
        raise ValueError("capacity-availability seed header is not canonical")
    return [_clean(row) for row in rows]


def load_capacity_availability_analysis_seed_rows(
    path: Path = DEFAULT_ANALYSIS_SEED_MANIFEST,
) -> list[dict[str, str]]:
    fields, rows = _read_csv(path)
    if fields != SEED_COLUMNS:
        raise ValueError(
            "capacity-availability analysis seed header is not canonical"
        )
    return [_clean(row) for row in rows]


def _equal_float(left: object, right: object) -> bool:
    try:
        return math.isclose(
            float(left), float(right), rel_tol=1e-12, abs_tol=1e-12
        )
    except (TypeError, ValueError):
        return False


def validate_capacity_availability_design(
    design_path: Path = DEFAULT_DESIGN,
    scenarios_path: Path = DEFAULT_SCENARIOS,
    scenario_provenance_path: Path = DEFAULT_SCENARIO_PROVENANCE,
    seed_manifest_path: Path = DEFAULT_SEED_MANIFEST,
    analysis_seed_manifest_path: Path = DEFAULT_ANALYSIS_SEED_MANIFEST,
    reference_seed_manifest_path: Path = DEFAULT_REFERENCE_SEED_MANIFEST,
) -> dict[str, object]:
    """Fail closed on study grid, reference reuse, and primary estimand."""

    design = _load_design(design_path)
    errors: list[str] = []

    arms = design.get("execution_arms", [])
    arm_by_id = {
        str(arm.get("scenario_id")): arm
        for arm in arms
    }
    if tuple(arm_by_id) != EXECUTION_SCENARIO_IDS:
        errors.append(
            "execution arms must be the four frozen reduced-capacity arms"
        )
    expected_capacities = {
        "CAPACITY_AVAIL_SECURITY_MINUS_4": (32, 21),
        "CAPACITY_AVAIL_IMMIGRATION_MINUS_3": (36, 18),
        "CAPACITY_AVAIL_JOINT_MINUS_4_MINUS_3": (32, 18),
        "CAPACITY_AVAIL_SEVERE_JOINT_30_17": (30, 17),
    }
    for scenario_id, expected in expected_capacities.items():
        arm = arm_by_id.get(scenario_id, {})
        actual = (
            int(arm.get("security_capacity", -1)),
            int(arm.get("immigration_capacity", -1)),
        )
        if actual != expected:
            errors.append(
                f"{scenario_id}: capacity pair must remain {expected}"
            )

    levels = design.get("arrival_rate_uncertainty", {}).get("levels", [])
    level_by_id = {
        str(level.get("level_id")): level
        for level in levels
    }
    if tuple(level_by_id) != ARRIVAL_LEVEL_IDS:
        errors.append("arrival levels must remain low, base, high in order")

    try:
        scenario_fields, scenario_rows = _read_csv(scenarios_path)
    except FileNotFoundError:
        scenario_fields, scenario_rows = (), []
        errors.append(f"missing file: {scenarios_path}")
    if scenario_fields != SCENARIO_COLUMNS:
        errors.append("capacity-availability scenario header is not canonical")
    expected_cells = {
        (
            scenario_id,
            str(level["input_sample_id"]),
        )
        for level in levels
        for scenario_id in EXECUTION_SCENARIO_IDS
    }
    actual_cells: set[tuple[str, str]] = set()
    seen_config_ids: set[str] = set()
    for line, raw_row in enumerate(scenario_rows, start=2):
        row = _clean(raw_row)
        key = (row.get("scenario_id", ""), row.get("input_sample_id", ""))
        if key in actual_cells:
            errors.append(f"scenario line {line}: duplicate execution cell")
        actual_cells.add(key)
        config_id = row.get("config_id", "")
        if config_id in seen_config_ids:
            errors.append(f"scenario line {line}: duplicate config_id")
        seen_config_ids.add(config_id)
        scenario_id, input_sample_id = key
        arm = arm_by_id.get(scenario_id)
        matching_levels = [
            level
            for level in levels
            if str(level.get("input_sample_id")) == input_sample_id
        ]
        if arm is None or len(matching_levels) != 1:
            errors.append(f"scenario line {line}: cell is outside frozen grid")
            continue
        level = matching_levels[0]
        if int(row.get("security_capacity", -1)) != int(
            arm["security_capacity"]
        ):
            errors.append(f"scenario line {line}: Security capacity drift")
        if int(row.get("immigration_capacity", -1)) != int(
            arm["immigration_capacity"]
        ):
            errors.append(f"scenario line {line}: Immigration capacity drift")
        if not _equal_float(
            row.get("arrival_rate_per_second"),
            level["arrival_rate_per_second"],
        ):
            errors.append(f"scenario line {line}: arrival-rate drift")
        if row.get("pilot_replications") != "50":
            errors.append(f"scenario line {line}: replication-count drift")
        if row.get("input_status") != (
            "FROZEN_CAPACITY_AVAILABILITY_DESIGN"
        ):
            errors.append(f"scenario line {line}: input status is not frozen")
        if row.get("calibration_status") != "NOT_CALIBRATED":
            errors.append(f"scenario line {line}: calibration boundary drift")
    missing_cells = expected_cells - actual_cells
    extra_cells = actual_cells - expected_cells
    if missing_cells:
        errors.append(f"scenario grid is missing {len(missing_cells)} cells")
    if extra_cells:
        errors.append(f"scenario grid has {len(extra_cells)} extra cells")

    try:
        provenance_fields, provenance_rows = _read_csv(
            scenario_provenance_path
        )
    except FileNotFoundError:
        provenance_fields, provenance_rows = (), []
        errors.append(f"missing file: {scenario_provenance_path}")
    if provenance_fields != SCENARIO_PROVENANCE_COLUMNS:
        errors.append("capacity-availability provenance header is not canonical")
    reference_capacity_mappings = {
        row.get("parameter_name"): row
        for row in provenance_rows
        if row.get("scenario_id") == REFERENCE_SCENARIO_ID
    }
    for parameter, expected_value in (
        ("security_capacity", "36"),
        ("immigration_capacity", "21"),
    ):
        mapping = reference_capacity_mappings.get(parameter)
        if mapping is None or mapping.get("parameter_value") != expected_value:
            errors.append(
                f"reference provenance must declare {parameter}={expected_value}"
            )
        elif (
            "target-utilisation-derived" not in mapping.get("notes", "")
            or "not an observed HTX roster" not in mapping.get("notes", "")
        ):
            errors.append(
                f"reference {parameter} provenance must reject roster inference"
            )

    try:
        seed_fields, seed_rows = _read_csv(seed_manifest_path)
    except FileNotFoundError:
        seed_fields, seed_rows = (), []
        errors.append(f"missing file: {seed_manifest_path}")
    try:
        reference_fields, reference_seed_rows = _read_csv(
            reference_seed_manifest_path
        )
    except FileNotFoundError:
        reference_fields, reference_seed_rows = (), []
        errors.append(f"missing file: {reference_seed_manifest_path}")
    try:
        analysis_seed_fields, analysis_seed_rows = _read_csv(
            analysis_seed_manifest_path
        )
    except FileNotFoundError:
        analysis_seed_fields, analysis_seed_rows = (), []
        errors.append(f"missing file: {analysis_seed_manifest_path}")
    if seed_fields != SEED_COLUMNS:
        errors.append("capacity-availability seed header is not canonical")
    if reference_fields != SEED_COLUMNS:
        errors.append("reference seed header is not canonical")
    if analysis_seed_fields != SEED_COLUMNS:
        errors.append(
            "capacity-availability analysis seed header is not canonical"
        )
    reference_by_key = {
        (row.get("arrival_level_id"), row.get("replication_id")): row
        for row in reference_seed_rows
    }
    seed_keys: set[tuple[str | None, str | None]] = set()
    expected_scenario_string = "|".join(EXECUTION_SCENARIO_IDS)
    seed_fields_to_match = (
        "master_seed",
        "arrival_seed",
        "service_seed",
        "routing_seed",
        "tie_seed",
    )
    for line, row in enumerate(seed_rows, start=2):
        key = (row.get("arrival_level_id"), row.get("replication_id"))
        if key in seed_keys:
            errors.append(f"seed line {line}: duplicate level/replication")
        seed_keys.add(key)
        source = reference_by_key.get(key)
        if source is None:
            errors.append(f"seed line {line}: no reusable Part 1 seed group")
            continue
        if row.get("study_id") != design.get("study_id"):
            errors.append(f"seed line {line}: study_id drift")
        if row.get("scenario_ids") != expected_scenario_string:
            errors.append(f"seed line {line}: execution-arm ordering drift")
        if row.get("input_sample_id") != source.get("input_sample_id"):
            errors.append(f"seed line {line}: input sample does not match source")
        for field in seed_fields_to_match:
            if row.get(field) != source.get(field):
                errors.append(
                    f"seed line {line}: {field} does not exactly reuse Part 1"
                )
    expected_seed_keys = {
        (level_id, str(replication))
        for level_id in ARRIVAL_LEVEL_IDS
        for replication in range(1, 51)
    }
    if seed_keys != expected_seed_keys:
        errors.append(
            "seed manifest must contain exactly 3 arrival levels x 50 groups"
        )
    analysis_seed_by_key = {
        (row.get("arrival_level_id"), row.get("replication_id")): row
        for row in analysis_seed_rows
    }
    if set(analysis_seed_by_key) != expected_seed_keys:
        errors.append(
            "analysis seed manifest must contain exactly "
            "3 arrival levels x 50 groups"
        )
    expected_analysis_scenarios = "|".join(ANALYSIS_SCENARIO_IDS)
    execution_seed_by_key = {
        (row.get("arrival_level_id"), row.get("replication_id")): row
        for row in seed_rows
    }
    for key, row in analysis_seed_by_key.items():
        execution = execution_seed_by_key.get(key)
        if execution is None:
            continue
        if row.get("study_id") != design.get("study_id"):
            errors.append(f"analysis seed {key}: study_id drift")
        if row.get("scenario_ids") != expected_analysis_scenarios:
            errors.append(f"analysis seed {key}: five-arm ordering drift")
        for field in (
            "input_sample_id",
            "master_seed",
            "arrival_seed",
            "service_seed",
            "routing_seed",
            "tie_seed",
        ):
            if row.get(field) != execution.get(field):
                errors.append(
                    f"analysis seed {key}: {field} differs from execution seed"
                )

    run_cap = design.get("run_cap", {})
    execution_cell_count = len(expected_cells)
    analysis_cell_count = len(levels) * len(ANALYSIS_SCENARIO_IDS)
    replications = int(run_cap.get("replications_per_cell", -1))
    expected_new_runs = execution_cell_count * replications
    expected_analysis_runs = analysis_cell_count * replications
    for field, expected in (
        ("execution_arm_count", 4),
        ("arrival_level_count", 3),
        ("execution_cell_count", 12),
        ("new_execution_runs", 600),
        ("reused_reference_cell_count", 3),
        ("analysis_cell_count", 15),
        ("reused_reference_runs", 150),
        ("analysis_run_count", 750),
    ):
        if int(run_cap.get(field, -1)) != expected:
            errors.append(f"run_cap.{field} must remain {expected}")
    if replications != 50:
        errors.append("run_cap.replications_per_cell must remain 50")
    if expected_new_runs != 600 or expected_analysis_runs != 750:
        errors.append("derived run counts do not match the frozen contract")
    if run_cap.get("adaptive_extension_allowed") is not False:
        errors.append("adaptive extension must remain disabled")

    primary = design.get("primary_analysis", {})
    expected_primary = {
        "input_level_id": "MLE_BASE",
        "scenario_id": "CAPACITY_AVAIL_JOINT_MINUS_4_MINUS_3",
        "reference_scenario_id": REFERENCE_SCENARIO_ID,
        "metric": "peak_total_waiting_queue",
    }
    for field, expected in expected_primary.items():
        if primary.get(field) != expected:
            errors.append(f"primary_analysis.{field} must remain {expected}")
    if (
        primary.get("metric_definition")
        != "max_t(security_waiting_queue(t) + immigration_waiting_queue(t)) over the full-drain run within one replication"
    ):
        errors.append("primary peak-total-queue metric definition drift")

    semantics = design.get("capacity_semantics", {})
    if semantics.get("unit") != "concurrently_open_service_positions":
        errors.append("capacity unit must be concurrently open service positions")
    if semantics.get("headcount_equivalence_claim") is not False:
        errors.append("capacity must not claim one-to-one headcount equivalence")
    boundary = str(semantics.get("reference_claim_boundary", ""))
    if (
        "target-utilisation-derived" not in boundary
        or "not an observed HTX roster" not in boundary
    ):
        errors.append("36/21 provenance must reject observed-roster claims")

    return {
        "status": "PASS" if not errors else "FAIL",
        "study_id": design.get("study_id"),
        "errors": errors,
        "execution_arm_count": len(arms),
        "arrival_level_count": len(levels),
        "execution_cell_count": execution_cell_count,
        "analysis_cell_count": analysis_cell_count,
        "seed_group_count": len(seed_rows),
        "analysis_seed_group_count": len(analysis_seed_rows),
        "new_execution_run_count": expected_new_runs,
        "reused_reference_run_count": 150,
        "analysis_run_count": expected_analysis_runs,
        "primary": expected_primary,
        "adaptive_extension_allowed": run_cap.get(
            "adaptive_extension_allowed"
        ),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write-generated",
        action="store_true",
        help="rewrite the four deterministic CSV artifacts before validation",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.write_generated:
        write_generated_artifacts()
    report = validate_capacity_availability_design()
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
