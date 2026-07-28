"""Validate the pre-run design for the narrowed capacity mechanism study.

This module intentionally separates three uncertainty sources:

* the exact Poisson counting interval for an accepted count over a fixed
  exposure;
* Monte Carlo precision across simulation replications; and
* human adjudication/model-form uncertainty, which the first two do not cover.

The replication plan is sized from an independent two-arm variance envelope.
No common-random-number (CRN) variance reduction is assumed at design time.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Mapping, Sequence

from scipy.stats import chi2
from scipy.stats import t as student_t

from src.analysis.validate_operational_contract import (
    DEFAULT_SCENARIOS,
    SCENARIO_COLUMNS,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DESIGN = PROJECT_ROOT / "config" / "confirmatory_capacity_study.json"
DEFAULT_SEED_MANIFEST = (
    PROJECT_ROOT / "config" / "confirmatory_seed_manifest.csv"
)
CAPACITY_SCENARIO_IDS = (
    "REFERENCE_ASSUMPTION_SANDBOX_V1",
    "CAPACITY_SECURITY_PLUS_4",
    "CAPACITY_IMMIGRATION_PLUS_3",
    "CAPACITY_BOTH_PLUS",
)


def exact_poisson_rate_interval(
    count: int,
    exposure_seconds: float,
    *,
    confidence_level: float = 0.95,
) -> tuple[float, float]:
    """Return the two-sided Garwood exact interval for a Poisson rate."""

    if count < 0:
        raise ValueError("count must be non-negative")
    if exposure_seconds <= 0 or not math.isfinite(exposure_seconds):
        raise ValueError("exposure_seconds must be finite and positive")
    if not 0 < confidence_level < 1:
        raise ValueError("confidence_level must be between zero and one")

    alpha = 1.0 - confidence_level
    low = (
        0.0
        if count == 0
        else 0.5 * float(chi2.ppf(alpha / 2.0, 2 * count))
        / exposure_seconds
    )
    high = (
        0.5
        * float(chi2.ppf(1.0 - alpha / 2.0, 2 * (count + 1)))
        / exposure_seconds
    )
    return low, high


def conservative_independent_half_width(
    standard_deviation_envelope: float,
    replications_per_arm: int,
    *,
    confidence_level: float = 0.95,
) -> float:
    """Plan an equal-n two-arm t interval without assuming CRN pairing."""

    if standard_deviation_envelope < 0 or not math.isfinite(
        standard_deviation_envelope
    ):
        raise ValueError("standard_deviation_envelope must be finite and non-negative")
    if replications_per_arm < 2:
        raise ValueError("at least two replications per arm are required")
    if not 0 < confidence_level < 1:
        raise ValueError("confidence_level must be between zero and one")

    degrees_of_freedom = 2 * replications_per_arm - 2
    critical = float(
        student_t.ppf(0.5 + confidence_level / 2.0, degrees_of_freedom)
    )
    standard_error = math.sqrt(
        2.0
        * standard_deviation_envelope**2
        / replications_per_arm
    )
    return critical * standard_error


def minimum_equal_arm_replications(
    standard_deviation_envelope: float,
    target_half_width: float,
    *,
    confidence_level: float = 0.95,
    search_cap: int = 100_000,
) -> int:
    """Return the first equal arm size meeting the independent precision target."""

    if target_half_width <= 0 or not math.isfinite(target_half_width):
        raise ValueError("target_half_width must be finite and positive")
    for replications in range(2, search_cap + 1):
        if (
            conservative_independent_half_width(
                standard_deviation_envelope,
                replications,
                confidence_level=confidence_level,
            )
            <= target_half_width
        ):
            return replications
    raise ValueError("precision target was not met within search_cap")


def _read_seed_manifest(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def load_confirmatory_seed_rows(
    path: Path = DEFAULT_SEED_MANIFEST,
) -> list[dict[str, str]]:
    """Load the frozen explicit stream groups."""

    return _read_seed_manifest(path)


def build_confirmatory_scenario_rows(
    design_path: Path = DEFAULT_DESIGN,
    operational_scenarios_path: Path = DEFAULT_SCENARIOS,
) -> list[dict[str, str]]:
    """Derive 12 full parameter rows from four registered capacity arms."""

    design = json.loads(design_path.read_text(encoding="utf-8"))
    with operational_scenarios_path.open(
        "r", encoding="utf-8-sig", newline=""
    ) as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != SCENARIO_COLUMNS:
            raise ValueError("operational scenario header is not canonical")
        registered = {
            row["scenario_id"]: {
                key: (value or "").strip()
                for key, value in row.items()
            }
            for row in reader
            if row["scenario_id"] in CAPACITY_SCENARIO_IDS
        }
    if set(registered) != set(CAPACITY_SCENARIO_IDS):
        raise ValueError("the four registered capacity arms are incomplete")

    levels = {
        str(level["level_id"]): level
        for level in design["arrival_rate_uncertainty"]["levels"]
    }
    master_seed = str(design["seed_policy"]["master_seed"])
    replications = str(design["precision_plan"]["planned_replications_per_cell"])
    rows: list[dict[str, str]] = []
    seen_cells: set[tuple[str, str]] = set()
    for cell in design["study_cells"]:
        scenario_id = str(cell["scenario_id"])
        level_id = str(cell["arrival_level_id"])
        if scenario_id not in registered or level_id not in levels:
            raise ValueError(f"unknown confirmatory cell {level_id}/{scenario_id}")
        source = registered[scenario_id]
        if int(source["security_capacity"]) != int(cell["security_capacity"]):
            raise ValueError(f"{level_id}/{scenario_id}: Security capacity drift")
        if int(source["immigration_capacity"]) != int(
            cell["immigration_capacity"]
        ):
            raise ValueError(
                f"{level_id}/{scenario_id}: Immigration capacity drift"
            )
        level = levels[level_id]
        input_sample_id = str(level["input_sample_id"])
        cell_key = (scenario_id, input_sample_id)
        if cell_key in seen_cells:
            raise ValueError(f"duplicate confirmatory cell {cell_key}")
        seen_cells.add(cell_key)

        row = dict(source)
        row.update(
            {
                "config_id": f"OP_CONFIRM_{level_id}_{scenario_id}",
                "description": (
                    f"Confirmatory {level_id} capacity cell derived from "
                    f"{source['config_id']}"
                ),
                "arrival_rate_per_second": str(
                    level["arrival_rate_per_second"]
                ),
                "demand_multiplier": "1.0",
                "input_sample_id": input_sample_id,
                "pilot_replications": replications,
                "master_seed": master_seed,
                "crn_alignment_status": "PENDING_VALIDATION",
                "input_status": "FROZEN_CONFIRMATORY_DESIGN",
                "calibration_status": "NOT_CALIBRATED",
                "claim_ceiling": "COMPARATIVE_WHAT_IF_ONLY",
                "notes": (
                    f"{design['study_id']} cell {cell['cell_id']}; "
                    "paired analysis prohibited until explicit CRN PASS"
                ),
            }
        )
        if tuple(row) != SCENARIO_COLUMNS:
            raise ValueError("derived confirmatory row lost the canonical schema")
        rows.append(row)

    expected_cells = int(design["run_cap"]["study_cell_count"])
    if len(rows) != expected_cells:
        raise ValueError(
            f"derived {len(rows)} confirmatory rows; expected {expected_cells}"
        )
    return rows


def _close(actual: float, expected: float, tolerance: float = 1e-9) -> bool:
    return math.isclose(actual, expected, rel_tol=tolerance, abs_tol=tolerance)


def validate_confirmatory_design(
    design_path: Path = DEFAULT_DESIGN,
    seed_manifest_path: Path = DEFAULT_SEED_MANIFEST,
) -> dict[str, object]:
    """Validate the design arithmetic, study cells, and explicit seed manifest."""

    design = json.loads(design_path.read_text(encoding="utf-8"))
    manifest = _read_seed_manifest(seed_manifest_path)
    errors: list[str] = []

    arrival = design.get("arrival_rate_uncertainty", {})
    count = int(arrival.get("accepted_count", -1))
    exposure = float(arrival.get("exposure_seconds", 0))
    confidence_level = float(arrival.get("confidence_level", 0))
    exact_low, exact_high = exact_poisson_rate_interval(
        count,
        exposure,
        confidence_level=confidence_level,
    )
    exact_base = count / exposure
    level_rows = arrival.get("levels", [])
    declared_levels = {
        row["level_id"]: float(row["arrival_rate_per_second"])
        for row in level_rows
    }
    input_sample_by_level = {
        str(row["level_id"]): str(row["input_sample_id"])
        for row in level_rows
    }
    expected_levels = {
        "EXACT95_LOW": exact_low,
        "MLE_BASE": exact_base,
        "EXACT95_HIGH": exact_high,
    }
    if set(declared_levels) != set(expected_levels):
        errors.append("arrival levels must be EXACT95_LOW, MLE_BASE, EXACT95_HIGH")
    for level_id, expected in expected_levels.items():
        if level_id in declared_levels and not _close(
            declared_levels[level_id], expected
        ):
            errors.append(f"{level_id}: declared rate does not match exact calculation")
    if arrival.get("uncertainty_scope") != "HPP_COUNTING_PROCESS_ONLY":
        errors.append("arrival uncertainty_scope must be HPP_COUNTING_PROCESS_ONLY")
    exclusions = set(arrival.get("explicit_exclusions", []))
    if "HUMAN_ADJUDICATION_ERROR" not in exclusions:
        errors.append("human adjudication error must be explicitly excluded")

    precision = design.get("precision_plan", {})
    pilot_sds = [
        float(value)
        for value in precision.get(
            "pilot_primary_metric_standard_deviations_seconds", {}
        ).values()
    ]
    if not pilot_sds:
        errors.append("precision plan must declare pilot standard deviations")
        standard_deviation_envelope = math.nan
    else:
        standard_deviation_envelope = max(pilot_sds)
    declared_envelope = float(
        precision.get("independent_standard_deviation_envelope_seconds", math.nan)
    )
    if not _close(declared_envelope, standard_deviation_envelope):
        errors.append("precision envelope must equal the largest pilot arm SD")
    target = float(precision.get("target_two_sided_ci_half_width_seconds", 0))
    planned_per_cell = int(precision.get("planned_replications_per_cell", 0))
    required = minimum_equal_arm_replications(
        standard_deviation_envelope,
        target,
        confidence_level=float(precision.get("confidence_level", 0.95)),
    )
    if planned_per_cell < required:
        errors.append(
            "planned replications per cell do not meet the independent precision target"
        )
    if precision.get("variance_basis") != "INDEPENDENT_WORST_PILOT_ARM":
        errors.append("variance basis must not claim unverified CRN pairing")

    cells = design.get("study_cells", [])
    cells_by_level: dict[str, set[str]] = {}
    seen_cell_ids: set[str] = set()
    seen_cell_keys: set[tuple[str, str]] = set()
    for cell in cells:
        level_id = str(cell["arrival_level_id"])
        scenario_id = str(cell["scenario_id"])
        cell_id = str(cell["cell_id"])
        if cell_id in seen_cell_ids:
            errors.append(f"duplicate study cell_id {cell_id}")
        seen_cell_ids.add(cell_id)
        cell_key = (level_id, scenario_id)
        if cell_key in seen_cell_keys:
            errors.append(
                f"duplicate study cell for {level_id}/{scenario_id}"
            )
        seen_cell_keys.add(cell_key)
        cells_by_level.setdefault(level_id, set()).add(scenario_id)
    if set(cells_by_level) != set(expected_levels):
        errors.append("study cells must cover all three frozen arrival levels")
    for level_id in expected_levels:
        if cells_by_level.get(level_id) != set(CAPACITY_SCENARIO_IDS):
            errors.append(
                f"{level_id}: study cells must contain the four capacity arms"
            )
    expected_total_runs = len(cells) * planned_per_cell
    run_cap = design.get("run_cap", {})
    if int(run_cap.get("study_cell_count", -1)) != len(cells):
        errors.append("run-cap study_cell_count must equal the study-cell count")
    if int(run_cap.get("replications_per_cell", -1)) != planned_per_cell:
        errors.append(
            "run-cap replications_per_cell must equal the precision plan"
        )
    if int(run_cap.get("total_runs", -1)) != expected_total_runs:
        errors.append("total run cap must equal cells times planned replications")
    if run_cap.get("adaptive_extension_allowed") is not False:
        errors.append("adaptive extension must remain disabled")

    seed_policy = design.get("seed_policy", {})
    master_seed = int(seed_policy.get("master_seed", 0))
    level_offsets = {
        str(key): int(value)
        for key, value in seed_policy.get("level_offsets", {}).items()
    }
    stride = int(seed_policy.get("replication_stride", 0))
    stream_offsets = {
        str(key): int(value)
        for key, value in seed_policy.get("stream_offsets", {}).items()
    }
    expected_columns = (
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
    if manifest and tuple(manifest[0]) != expected_columns:
        errors.append("seed manifest columns do not match the frozen schema")

    expected_groups = len(cells_by_level) * planned_per_cell
    if len(manifest) != expected_groups:
        errors.append(
            f"seed manifest has {len(manifest)} rows; expected {expected_groups}"
        )
    seen_groups: set[str] = set()
    seen_level_replications: set[tuple[str, int]] = set()
    seen_seed_tuples: set[tuple[int, int, int, int]] = set()
    for line, row in enumerate(manifest, start=2):
        label = f"seed manifest line {line}"
        level_id = row.get("arrival_level_id", "")
        try:
            replication_id = int(row.get("replication_id", "0"))
        except ValueError:
            errors.append(f"{label}: replication_id is not an integer")
            continue
        group_id = row.get("pairing_group_id", "")
        if row.get("schema_version") != str(design.get("schema_version", "")):
            errors.append(f"{label}: schema_version does not match the design")
        if row.get("study_id") != str(design.get("study_id", "")):
            errors.append(f"{label}: study_id does not match the design")
        if group_id in seen_groups:
            errors.append(f"{label}: duplicate pairing_group_id")
        seen_groups.add(group_id)
        if not 1 <= replication_id <= planned_per_cell:
            errors.append(f"{label}: replication_id outside planned range")
        level_replication = (level_id, replication_id)
        if level_replication in seen_level_replications:
            errors.append(
                f"{label}: duplicate arrival-level/replication group"
            )
        seen_level_replications.add(level_replication)
        if row.get("input_sample_id") != input_sample_by_level.get(level_id):
            errors.append(
                f"{label}: input_sample_id does not match the arrival level"
            )
        expected_scenarios = cells_by_level.get(level_id)
        actual_scenario_sequence = tuple(
            value for value in row.get("scenario_ids", "").split("|") if value
        )
        actual_scenarios = set(actual_scenario_sequence)
        if (
            expected_scenarios is None
            or actual_scenarios != expected_scenarios
            or actual_scenario_sequence != CAPACITY_SCENARIO_IDS
        ):
            errors.append(f"{label}: scenario_ids do not match study cells")
        try:
            row_master_seed = int(row.get("master_seed", "0"))
        except ValueError:
            row_master_seed = 0
            errors.append(f"{label}: master_seed is not an integer")
        if row_master_seed != master_seed:
            errors.append(f"{label}: master_seed does not match seed policy")
        if level_id not in level_offsets:
            errors.append(f"{label}: unknown arrival level")
            continue
        base = master_seed + level_offsets[level_id] + replication_id * stride
        try:
            seed_tuple = tuple(
                int(row.get(f"{stream}_seed", "0"))
                for stream in ("arrival", "service", "routing", "tie")
            )
        except ValueError:
            errors.append(f"{label}: stream seed is not an integer")
            continue
        expected_tuple = tuple(
            base + stream_offsets[stream]
            for stream in ("arrival", "service", "routing", "tie")
        )
        if seed_tuple != expected_tuple:
            errors.append(f"{label}: stream seeds do not match frozen policy")
        if seed_tuple in seen_seed_tuples:
            errors.append(f"{label}: seed tuple is reused by another group")
        seen_seed_tuples.add(seed_tuple)
    expected_level_replications = {
        (level_id, replication_id)
        for level_id in expected_levels
        for replication_id in range(1, planned_per_cell + 1)
    }
    missing_level_replications = (
        expected_level_replications - seen_level_replications
    )
    extra_level_replications = (
        seen_level_replications - expected_level_replications
    )
    if missing_level_replications:
        errors.append(
            "seed manifest is missing "
            f"{len(missing_level_replications)} arrival-level/replication groups"
        )
    if extra_level_replications:
        errors.append(
            "seed manifest contains "
            f"{len(extra_level_replications)} unexpected groups"
        )

    return {
        "status": "PASS" if not errors else "FAIL",
        "study_id": design.get("study_id"),
        "errors": errors,
        "accepted_count": count,
        "exposure_seconds": exposure,
        "exact_rate_interval": {
            "confidence_level": confidence_level,
            "low": exact_low,
            "base_mle": exact_base,
            "high": exact_high,
        },
        "independent_precision_plan": {
            "standard_deviation_envelope_seconds": standard_deviation_envelope,
            "target_half_width_seconds": target,
            "minimum_replications_per_arm": required,
            "planned_replications_per_cell": planned_per_cell,
            "planned_half_width_seconds": conservative_independent_half_width(
                standard_deviation_envelope,
                planned_per_cell,
                confidence_level=float(
                    precision.get("confidence_level", 0.95)
                ),
            ),
        },
        "study_cell_count": len(cells),
        "seed_group_count": len(manifest),
        "total_run_cap": expected_total_runs,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate the confirmatory capacity-study design"
    )
    parser.add_argument("--design", type=Path, default=DEFAULT_DESIGN)
    parser.add_argument(
        "--seed-manifest", type=Path, default=DEFAULT_SEED_MANIFEST
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = validate_confirmatory_design(args.design, args.seed_manifest)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
