"""Validate and analyse the finite interstage-buffer AnyLogic batch.

This module intentionally consumes one compact, replication-level CSV rather
than reconstructing unobserved results.  The registered design is:

* two capacity regimes: S36/I16 and the S30/I21 negative control;
* four interstage waiting-space capacities: 25, 50, 100, and 5000;
* 50 common-random-number replications per cell.

The 5000 level is a computationally non-binding comparator, not a measured
physical space.  Analysis outputs are released only after exact coverage,
lineage, CRN, conservation, B100-versus-B5000 replay, and negative-control
invariance gates all pass.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
from collections import defaultdict
from pathlib import Path
from typing import Mapping, Sequence

from src.analysis.analyse_operational_replications import (
    one_sample_summary,
    portable_path,
)
from src.analysis.interstage_buffer_design import (
    BUFFER_LEVELS as REGISTERED_BUFFER_LEVELS,
    INPUT_SAMPLE_ID,
    MODEL_VERSION,
    REGIMES as REGISTERED_REGIMES,
    REPLICATION_IDS as REGISTERED_REPLICATION_IDS,
    STUDY_ID,
    interstage_scenario_config_sha256,
    load_interstage_buffer_scenario_rows,
    load_interstage_buffer_seed_rows,
    validate_interstage_buffer_design,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT_CSV = (
    PROJECT_ROOT
    / "results"
    / "raw"
    / "interstage_buffer_sensitivity_consolidated"
    / "interstage_buffer_by_replication.csv"
)
DEFAULT_OUTPUT_DIR = (
    PROJECT_ROOT / "results" / "analysis" / "interstage_buffer"
)

SCHEMA_VERSION = "1.0"
ANALYSIS_ID = "TASK3_INTERSTAGE_BUFFER_BAS_ANALYSIS_V1"
VALIDATION_ID = "TASK3_INTERSTAGE_BUFFER_IMPORT_VALIDATION_V1"
CRN_VALIDATION_ID = "TASK3_INTERSTAGE_BUFFER_CRN_ALIGNMENT_V1"
REPLAY_VALIDATION_ID = "TASK3_INTERSTAGE_BUFFER_EXACT_REPLAY_V1"
NEGATIVE_CONTROL_ID = "TASK3_INTERSTAGE_BUFFER_NEGATIVE_CONTROL_V1"
CLAIM_BOUNDARY = "CONDITIONAL_FINITE_BUFFER_SENSITIVITY_NOT_SITE_FORECAST"

REGIMES = tuple(
    (security, immigration)
    for _, security, immigration, _ in REGISTERED_REGIMES
)
REGIME_NAMES = {
    (security, immigration): regime_id
    for regime_id, security, immigration, _ in REGISTERED_REGIMES
}
BUFFER_LEVELS = REGISTERED_BUFFER_LEVELS
NONBINDING_BUFFER = 5000
EXACT_REPLAY_BUFFER = 100
REPLICATION_IDS = REGISTERED_REPLICATION_IDS
EXPECTED_RUN_COUNT = len(REGIMES) * len(BUFFER_LEVELS) * len(REPLICATION_IDS)
DEFAULT_CI_LEVEL = 0.95

# A negative control is useful only with a frozen practical-equivalence rule.
# The full paired 95% CI must fit inside the larger of 1 second or 1% of the
# negative-control non-binding mean.
NEGATIVE_CONTROL_ABSOLUTE_MARGIN_SECONDS = 1.0
NEGATIVE_CONTROL_RELATIVE_MARGIN = 0.01

SEED_FIELDS = (
    "master_seed",
    "arrival_seed",
    "service_seed",
    "routing_seed",
    "tie_seed",
)
CHART_METRICS = (
    "system_time_p95_seconds",
    "security_blocked_resource_fraction",
)
AUDIT_METRICS = (
    *CHART_METRICS,
    "security_blocked_resource_seconds",
    "security_busy_seconds",
    "last_exit_seconds",
    "security_blocked_share_of_occupied",
    "interstage_buffer_full_time_fraction",
    "time_weighted_mean_interstage_buffer_occupancy",
    "interstage_block_time_mean_seconds",
    "interstage_block_time_p95_seconds",
    "total_wait_including_interstage_mean_seconds",
    "total_wait_including_interstage_p95_seconds",
    "cohort_clear_time_after_cutoff_seconds",
)
EXACT_REPLAY_FIELDS = (
    "normalized_event_payload_sha256",
    "arrivals",
    "completed_after_drain",
    "rejected_or_dropped_count",
    "interstage_buffer_peak_occupancy",
    *AUDIT_METRICS,
)

REQUIRED_FIELDS = (
    "schema_version",
    "study_id",
    "config_id",
    "config_sha256",
    "model_version",
    "scenario_id",
    "input_sample_id",
    "replication_id",
    "security_capacity",
    "immigration_capacity",
    "interstage_buffer_capacity",
    *SEED_FIELDS,
    "input_draws_sha256",
    "normalized_event_payload_sha256",
    "arrivals",
    "completed_after_drain",
    "rejected_or_dropped_count",
    "conservation_pass",
    "run_status",
    "interstage_buffer_peak_occupancy",
    *AUDIT_METRICS,
)

REPLICATION_FIELDS = REQUIRED_FIELDS
ESTIMATE_FIELDS = (
    "schema_version",
    "study_id",
    "regime",
    "security_capacity",
    "immigration_capacity",
    "interstage_buffer_capacity",
    "buffer_label",
    "metric",
    "estimand",
    "n_replications",
    "mean",
    "standard_deviation",
    "standard_error",
    "degrees_of_freedom",
    "ci_level",
    "ci_low",
    "ci_high",
    "analysis_role",
)
NEGATIVE_CONTROL_CONTRAST_FIELDS = (
    "schema_version",
    "study_id",
    "regime",
    "security_capacity",
    "immigration_capacity",
    "interstage_buffer_capacity",
    "reference_buffer_capacity",
    "metric",
    "contrast",
    "n_pairs",
    "mean_difference_seconds",
    "standard_deviation",
    "standard_error",
    "degrees_of_freedom",
    "ci_level",
    "ci_low_seconds",
    "ci_high_seconds",
    "equivalence_margin_seconds",
    "zero_buffer_full_status",
    "exact_replay_status",
    "equivalence_status",
)

RunKey = tuple[int, int, int, int]
Cell = tuple[int, int, int]


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError(f"{path} has no CSV header")
        missing = [field for field in REQUIRED_FIELDS if field not in reader.fieldnames]
        if missing:
            raise ValueError(
                f"{path} is missing required fields: {', '.join(missing)}"
            )
        return list(reader)


def _write_csv(
    path: Path,
    rows: Sequence[Mapping[str, object]],
    fields: Sequence[str],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=list(fields),
            extrasaction="ignore",
            lineterminator="\n",
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    field: (
                        f"{value:.12g}" if isinstance(value, float) else value
                    )
                    for field, value in row.items()
                    if field in fields
                }
            )
    temporary.replace(path)


def _write_json(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _integer(value: object, label: str) -> int:
    raw = str(value).strip()
    try:
        parsed = int(raw)
    except ValueError as error:
        raise ValueError(f"{label} must be an integer") from error
    return parsed


def _number(value: object, label: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{label} must be numeric") from error
    if not math.isfinite(parsed):
        raise ValueError(f"{label} must be finite")
    return parsed


def _boolean(value: object, label: str) -> bool:
    raw = str(value).strip().lower()
    if raw == "true":
        return True
    if raw == "false":
        return False
    raise ValueError(f"{label} must be true or false")


def _identifier(value: object, label: str) -> str:
    parsed = str(value).strip()
    if not parsed:
        raise ValueError(f"{label} must not be empty")
    return parsed


def _hex_digest(value: object, label: str) -> str:
    parsed = str(value).strip().lower()
    if re.fullmatch(r"[0-9a-f]{64}", parsed) is None:
        raise ValueError(f"{label} must be a 64-character SHA-256 digest")
    return parsed


def _cell(row: Mapping[str, object]) -> Cell:
    return (
        int(row["security_capacity"]),
        int(row["immigration_capacity"]),
        int(row["interstage_buffer_capacity"]),
    )


def _run_key(row: Mapping[str, object]) -> RunKey:
    security, immigration, buffer_capacity = _cell(row)
    return (
        security,
        immigration,
        buffer_capacity,
        int(row["replication_id"]),
    )


def _normalise_row(
    row: Mapping[str, object],
    *,
    row_number: int,
    expected_study_id: str,
) -> dict[str, object]:
    missing = [field for field in REQUIRED_FIELDS if field not in row]
    if missing:
        raise ValueError(
            f"row {row_number} is missing required fields: {', '.join(missing)}"
        )

    normalised: dict[str, object] = {
        "schema_version": _identifier(
            row["schema_version"], f"row {row_number} schema_version"
        ),
        "study_id": _identifier(row["study_id"], f"row {row_number} study_id"),
        "config_id": _identifier(row["config_id"], f"row {row_number} config_id"),
        "config_sha256": _hex_digest(
            row["config_sha256"], f"row {row_number} config_sha256"
        ),
        "model_version": _identifier(
            row["model_version"], f"row {row_number} model_version"
        ),
        "scenario_id": _identifier(
            row["scenario_id"], f"row {row_number} scenario_id"
        ),
        "input_sample_id": _identifier(
            row["input_sample_id"], f"row {row_number} input_sample_id"
        ),
        "replication_id": _integer(
            row["replication_id"], f"row {row_number} replication_id"
        ),
        "security_capacity": _integer(
            row["security_capacity"], f"row {row_number} security_capacity"
        ),
        "immigration_capacity": _integer(
            row["immigration_capacity"], f"row {row_number} immigration_capacity"
        ),
        "interstage_buffer_capacity": _integer(
            row["interstage_buffer_capacity"],
            f"row {row_number} interstage_buffer_capacity",
        ),
        "input_draws_sha256": _hex_digest(
            row["input_draws_sha256"],
            f"row {row_number} input_draws_sha256",
        ),
        "normalized_event_payload_sha256": _hex_digest(
            row["normalized_event_payload_sha256"],
            f"row {row_number} normalized_event_payload_sha256",
        ),
        "arrivals": _integer(row["arrivals"], f"row {row_number} arrivals"),
        "completed_after_drain": _integer(
            row["completed_after_drain"],
            f"row {row_number} completed_after_drain",
        ),
        "rejected_or_dropped_count": _integer(
            row["rejected_or_dropped_count"],
            f"row {row_number} rejected_or_dropped_count",
        ),
        "conservation_pass": _boolean(
            row["conservation_pass"], f"row {row_number} conservation_pass"
        ),
        "run_status": _identifier(
            row["run_status"], f"row {row_number} run_status"
        ),
        "system_time_p95_seconds": _number(
            row["system_time_p95_seconds"],
            f"row {row_number} system_time_p95_seconds",
        ),
        "security_blocked_resource_fraction": _number(
            row["security_blocked_resource_fraction"],
            f"row {row_number} security_blocked_resource_fraction",
        ),
        "interstage_buffer_peak_occupancy": _integer(
            row["interstage_buffer_peak_occupancy"],
            f"row {row_number} interstage_buffer_peak_occupancy",
        ),
    }
    for field in SEED_FIELDS:
        normalised[field] = _integer(row[field], f"row {row_number} {field}")
    for field in AUDIT_METRICS:
        if field in CHART_METRICS:
            continue
        normalised[field] = _number(
            row[field],
            f"row {row_number} {field}",
        )

    if normalised["schema_version"] != SCHEMA_VERSION:
        raise ValueError(
            f"row {row_number} schema_version must be {SCHEMA_VERSION}"
        )
    if normalised["study_id"] != expected_study_id:
        raise ValueError(
            f"row {row_number} study_id must be {expected_study_id}"
        )
    if normalised["model_version"] != MODEL_VERSION:
        raise ValueError(
            f"row {row_number} model_version must be {MODEL_VERSION}"
        )
    if normalised["input_sample_id"] != INPUT_SAMPLE_ID:
        raise ValueError(
            f"row {row_number} input_sample_id must be {INPUT_SAMPLE_ID}"
        )
    regime = (
        int(normalised["security_capacity"]),
        int(normalised["immigration_capacity"]),
    )
    if regime not in REGIMES:
        raise ValueError(f"row {row_number} has unregistered regime {regime}")
    if int(normalised["interstage_buffer_capacity"]) not in BUFFER_LEVELS:
        raise ValueError(
            f"row {row_number} has unregistered interstage buffer capacity"
        )
    if int(normalised["arrivals"]) <= 0:
        raise ValueError(f"row {row_number} must contain at least one arrival")
    if int(normalised["arrivals"]) != int(
        normalised["completed_after_drain"]
    ):
        raise ValueError(
            f"row {row_number} violates admitted-cohort full-drain conservation"
        )
    if int(normalised["rejected_or_dropped_count"]) != 0:
        raise ValueError(f"row {row_number} reports rejection or drop")
    if normalised["conservation_pass"] is not True:
        raise ValueError(f"row {row_number} conservation_pass must be true")
    if normalised["run_status"] != "COMPLETE":
        raise ValueError(f"row {row_number} run_status must be COMPLETE")
    if float(normalised["system_time_p95_seconds"]) < 0:
        raise ValueError(f"row {row_number} system_time_p95_seconds is negative")
    blocked_fraction = float(
        normalised["security_blocked_resource_fraction"]
    )
    if not 0 <= blocked_fraction <= 1:
        raise ValueError(
            f"row {row_number} security_blocked_resource_fraction must be "
            "in [0, 1]"
        )
    blocked_seconds = float(normalised["security_blocked_resource_seconds"])
    busy_seconds = float(normalised["security_busy_seconds"])
    last_exit_seconds = float(normalised["last_exit_seconds"])
    blocked_share = float(
        normalised["security_blocked_share_of_occupied"]
    )
    if blocked_seconds < 0 or busy_seconds < 0 or last_exit_seconds <= 0:
        raise ValueError(
            f"row {row_number} Security resource-time components must be "
            "nonnegative and last_exit_seconds must be positive"
        )
    resource_time_capacity = (
        int(normalised["security_capacity"]) * last_exit_seconds
    )
    if busy_seconds + blocked_seconds > resource_time_capacity + 1e-9:
        raise ValueError(
            f"row {row_number} Security busy plus blocked resource-time "
            "exceeds available resource-time"
        )
    expected_blocked_fraction = blocked_seconds / resource_time_capacity
    if not math.isclose(
        blocked_fraction,
        expected_blocked_fraction,
        rel_tol=1e-9,
        abs_tol=1e-9,
    ):
        raise ValueError(
            f"row {row_number} security_blocked_resource_fraction does not "
            "equal blocked_seconds / (security_capacity * last_exit_seconds)"
        )
    occupied_seconds = busy_seconds + blocked_seconds
    expected_blocked_share = (
        blocked_seconds / occupied_seconds if occupied_seconds > 0 else 0.0
    )
    if not 0 <= blocked_share <= 1 or not math.isclose(
        blocked_share,
        expected_blocked_share,
        rel_tol=1e-9,
        abs_tol=1e-9,
    ):
        raise ValueError(
            f"row {row_number} security_blocked_share_of_occupied does not "
            "equal blocked_seconds / (busy_seconds + blocked_seconds)"
        )
    full_fraction = float(
        normalised["interstage_buffer_full_time_fraction"]
    )
    if not 0 <= full_fraction <= 1:
        raise ValueError(
            f"row {row_number} interstage_buffer_full_time_fraction must be "
            "in [0, 1]"
        )
    buffer_capacity = int(normalised["interstage_buffer_capacity"])
    peak_occupancy = int(normalised["interstage_buffer_peak_occupancy"])
    mean_occupancy = float(
        normalised["time_weighted_mean_interstage_buffer_occupancy"]
    )
    if not 0 <= peak_occupancy <= buffer_capacity:
        raise ValueError(
            f"row {row_number} interstage_buffer_peak_occupancy must be "
            "between zero and its capacity"
        )
    if not 0 <= mean_occupancy <= peak_occupancy:
        raise ValueError(
            f"row {row_number} time-weighted buffer occupancy must be "
            "between zero and its observed peak"
        )
    if peak_occupancy < buffer_capacity and full_fraction != 0:
        raise ValueError(
            f"row {row_number} reports positive buffer-full time without "
            "reaching buffer capacity"
        )
    for field in (
        "interstage_block_time_mean_seconds",
        "interstage_block_time_p95_seconds",
        "total_wait_including_interstage_mean_seconds",
        "total_wait_including_interstage_p95_seconds",
        "cohort_clear_time_after_cutoff_seconds",
    ):
        if float(normalised[field]) < 0:
            raise ValueError(f"row {row_number} {field} is negative")
    return normalised


def validate_imported_rows(
    rows: Sequence[Mapping[str, object]],
    *,
    replication_ids: Sequence[int] = REPLICATION_IDS,
    expected_study_id: str = STUDY_ID,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    """Validate exact registered coverage and row-level run integrity."""

    expected_replications = tuple(int(value) for value in replication_ids)
    expected_keys = {
        (security, immigration, buffer_capacity, replication_id)
        for security, immigration in REGIMES
        for buffer_capacity in BUFFER_LEVELS
        for replication_id in expected_replications
    }
    if len(rows) != len(expected_keys):
        raise ValueError(
            "finite-buffer import must contain exactly "
            f"{len(expected_keys)} rows; found {len(rows)}"
        )

    normalised = [
        _normalise_row(
            row,
            row_number=index,
            expected_study_id=expected_study_id,
        )
        for index, row in enumerate(rows, start=2)
    ]
    keys = [_run_key(row) for row in normalised]
    if len(set(keys)) != len(keys):
        duplicates = sorted(key for key in set(keys) if keys.count(key) > 1)
        raise ValueError(f"duplicate registered run keys: {duplicates[:5]}")
    if set(keys) != expected_keys:
        missing = sorted(expected_keys - set(keys))
        unexpected = sorted(set(keys) - expected_keys)
        raise ValueError(
            "finite-buffer import does not have exact registered coverage; "
            f"missing={missing[:5]}, unexpected={unexpected[:5]}"
        )

    model_versions = {str(row["model_version"]) for row in normalised}
    input_samples = {str(row["input_sample_id"]) for row in normalised}
    if len(model_versions) != 1:
        raise ValueError("model_version must be constant across the batch")
    if len(input_samples) != 1:
        raise ValueError("input_sample_id must be constant across the batch")

    scenario_to_cell: dict[str, Cell] = {}
    cell_lineage: dict[Cell, set[tuple[str, str, str]]] = defaultdict(set)
    for row in normalised:
        cell = _cell(row)
        scenario_id = str(row["scenario_id"])
        prior_cell = scenario_to_cell.setdefault(scenario_id, cell)
        if prior_cell != cell:
            raise ValueError(
                f"scenario_id {scenario_id} maps to more than one design cell"
            )
        cell_lineage[cell].add(
            (
                scenario_id,
                str(row["config_id"]),
                str(row["config_sha256"]),
            )
        )
    if len(scenario_to_cell) != len(REGIMES) * len(BUFFER_LEVELS):
        raise ValueError("each design cell must have one unique scenario_id")
    for cell, lineage in cell_lineage.items():
        if len(lineage) != 1:
            raise ValueError(f"configuration lineage drifted within cell {cell}")

    normalised.sort(key=_run_key)
    validation = {
        "schema_version": SCHEMA_VERSION,
        "validation_id": VALIDATION_ID,
        "status": "PASS",
        "study_id": expected_study_id,
        "actual_run_count": len(normalised),
        "expected_run_count": len(expected_keys),
        "regime_count": len(REGIMES),
        "buffer_level_count": len(BUFFER_LEVELS),
        "replications_per_cell": len(expected_replications),
        "regimes": [
            {
                "security_capacity": security,
                "immigration_capacity": immigration,
                "regime": REGIME_NAMES[(security, immigration)],
            }
            for security, immigration in REGIMES
        ],
        "buffer_levels": list(BUFFER_LEVELS),
        "model_version": next(iter(model_versions)),
        "input_sample_id": next(iter(input_samples)),
        "conservation_rule": (
            "arrivals == completed_after_drain and "
            "rejected_or_dropped_count == 0"
        ),
        "blocking_metric_definitions": {
            "security_blocked_resource_fraction": (
                "security_blocked_resource_seconds / "
                "(security_capacity * last_exit_seconds)"
            ),
            "security_blocked_share_of_occupied": (
                "security_blocked_resource_seconds / "
                "(security_busy_seconds + security_blocked_resource_seconds); "
                "zero when the denominator is zero"
            ),
        },
        "claim_boundary": CLAIM_BOUNDARY,
        "errors": [],
    }
    return normalised, validation


def build_registered_contract_report(
    rows: Sequence[Mapping[str, object]],
    scenario_rows: Sequence[Mapping[str, str]],
    seed_rows: Sequence[Mapping[str, str]],
    *,
    study_id: str = STUDY_ID,
) -> dict[str, object]:
    """Validate imported lineage and seeds against the frozen study files."""

    errors: list[str] = []
    expected_scenarios = {
        str(row["scenario_id"]): row for row in scenario_rows
    }
    if len(expected_scenarios) != len(REGIMES) * len(BUFFER_LEVELS):
        errors.append("registered scenario file must contain exactly 8 cells")
    expected_seeds = {
        int(row["replication_id"]): row for row in seed_rows
    }
    if set(expected_seeds) != set(REPLICATION_IDS):
        errors.append("registered seed manifest must cover replications 1..50")

    observed_scenarios: set[str] = set()
    for row in rows:
        scenario_id = str(row["scenario_id"])
        observed_scenarios.add(scenario_id)
        scenario = expected_scenarios.get(scenario_id)
        if scenario is None:
            errors.append(f"unregistered scenario_id {scenario_id}")
            continue
        expected_cell = (
            int(scenario["security_capacity"]),
            int(scenario["immigration_capacity"]),
            int(scenario["interstage_buffer_capacity"]),
        )
        if _cell(row) != expected_cell:
            errors.append(f"{scenario_id}: capacity fields drifted")
        if str(row["config_id"]) != scenario["config_id"]:
            errors.append(f"{scenario_id}: config_id drifted")
        expected_hash = interstage_scenario_config_sha256(scenario)
        if str(row["config_sha256"]) != expected_hash:
            errors.append(f"{scenario_id}: config_sha256 drifted")
        replication_id = int(row["replication_id"])
        seed = expected_seeds.get(replication_id)
        if seed is None:
            errors.append(
                f"{scenario_id}: unregistered replication {replication_id}"
            )
            continue
        if seed["study_id"] != study_id:
            errors.append(
                f"replication {replication_id}: registered study_id drifted"
            )
        if seed["input_sample_id"] != row["input_sample_id"]:
            errors.append(
                f"replication {replication_id}: input_sample_id drifted"
            )
        for field in SEED_FIELDS:
            if int(row[field]) != int(seed[field]):
                errors.append(
                    f"{scenario_id} replication {replication_id}: "
                    f"{field} differs from registered seed manifest"
                )

    if observed_scenarios != set(expected_scenarios):
        errors.append("observed scenario IDs do not match the frozen design")
    return {
        "schema_version": SCHEMA_VERSION,
        "validation_id": "TASK3_INTERSTAGE_BUFFER_REGISTERED_CONTRACT_V1",
        "status": "PASS" if not errors else "FAIL",
        "study_id": study_id,
        "model_version": MODEL_VERSION,
        "registered_scenario_count": len(expected_scenarios),
        "registered_seed_group_count": len(expected_seeds),
        "validated_run_count": len(rows),
        "errors": errors,
    }


def build_crn_alignment_report(
    rows: Sequence[Mapping[str, object]],
    *,
    replication_ids: Sequence[int] = REPLICATION_IDS,
    study_id: str = STUDY_ID,
) -> dict[str, object]:
    """Require identical registered stream seeds and input draws per CRN pair."""

    by_replication: dict[int, list[Mapping[str, object]]] = defaultdict(list)
    for row in rows:
        by_replication[int(row["replication_id"])].append(row)

    errors: list[str] = []
    replication_reports: list[dict[str, object]] = []
    stream_tuples: dict[int, tuple[int, ...]] = {}
    input_hashes: dict[int, str] = {}
    expected_rows_per_replication = len(REGIMES) * len(BUFFER_LEVELS)
    for replication_id in replication_ids:
        replication_rows = by_replication.get(int(replication_id), [])
        if len(replication_rows) != expected_rows_per_replication:
            errors.append(
                f"replication {replication_id} has {len(replication_rows)} "
                f"rows, expected {expected_rows_per_replication}"
            )
            continue
        seed_values = {
            tuple(int(row[field]) for field in SEED_FIELDS)
            for row in replication_rows
        }
        draw_hash_values = {
            str(row["input_draws_sha256"]) for row in replication_rows
        }
        if len(seed_values) != 1:
            errors.append(
                f"replication {replication_id} has CRN seed drift across cells"
            )
        if len(draw_hash_values) != 1:
            errors.append(
                f"replication {replication_id} has input-draw drift across cells"
            )
        if len(seed_values) == 1 and len(draw_hash_values) == 1:
            stream_tuples[int(replication_id)] = next(iter(seed_values))
            input_hashes[int(replication_id)] = next(iter(draw_hash_values))
            replication_reports.append(
                {
                    "replication_id": int(replication_id),
                    "paired_cell_count": len(replication_rows),
                    "seed_alignment_status": "PASS",
                    "input_draw_alignment_status": "PASS",
                }
            )

    stream_only = {
        replication_id: values[1:]
        for replication_id, values in stream_tuples.items()
    }
    if len(set(stream_only.values())) != len(stream_only):
        errors.append("stream seed tuples are not unique across replications")
    if len(set(input_hashes.values())) != len(input_hashes):
        errors.append("input-draw digests are not unique across replications")

    return {
        "schema_version": SCHEMA_VERSION,
        "validation_id": CRN_VALIDATION_ID,
        "status": "PASS" if not errors else "FAIL",
        "study_id": study_id,
        "replication_count": len(tuple(replication_ids)),
        "paired_cells_per_replication": expected_rows_per_replication,
        "seed_fields": list(SEED_FIELDS),
        "input_draw_digest_field": "input_draws_sha256",
        "replications": replication_reports,
        "errors": errors,
    }


def build_exact_replay_report(
    rows: Sequence[Mapping[str, object]],
    *,
    replication_ids: Sequence[int] = REPLICATION_IDS,
    study_id: str = STUDY_ID,
) -> dict[str, object]:
    """Require B100 and B5000 to replay identically within every CRN run."""

    indexed = {_run_key(row): row for row in rows}
    errors: list[str] = []
    regimes: list[dict[str, object]] = []
    for security, immigration in REGIMES:
        matched_pairs = 0
        field_mismatches: dict[str, int] = defaultdict(int)
        for replication_id in replication_ids:
            replay = indexed[
                (
                    security,
                    immigration,
                    EXACT_REPLAY_BUFFER,
                    int(replication_id),
                )
            ]
            nonbinding = indexed[
                (
                    security,
                    immigration,
                    NONBINDING_BUFFER,
                    int(replication_id),
                )
            ]
            mismatched = []
            for field in EXACT_REPLAY_FIELDS:
                if replay[field] != nonbinding[field]:
                    mismatched.append(field)
                    field_mismatches[field] += 1
            if mismatched:
                errors.append(
                    f"S{security}/I{immigration} replication "
                    f"{replication_id}: B{EXACT_REPLAY_BUFFER} != "
                    f"B{NONBINDING_BUFFER} for {', '.join(mismatched)}"
                )
            else:
                matched_pairs += 1
        regimes.append(
            {
                "regime": REGIME_NAMES[(security, immigration)],
                "security_capacity": security,
                "immigration_capacity": immigration,
                "expected_pair_count": len(tuple(replication_ids)),
                "exactly_matched_pair_count": matched_pairs,
                "field_mismatch_counts": dict(sorted(field_mismatches.items())),
            }
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "validation_id": REPLAY_VALIDATION_ID,
        "status": "PASS" if not errors else "FAIL",
        "study_id": study_id,
        "replay_buffer_capacity": EXACT_REPLAY_BUFFER,
        "nonbinding_buffer_capacity": NONBINDING_BUFFER,
        "exact_fields": list(EXACT_REPLAY_FIELDS),
        "regimes": regimes,
        "errors": errors,
        "interpretation": (
            "B100 and B5000 must have identical event-only ledger digests and "
            "registered replay KPIs. This validates that B100 is already "
            "non-binding for this finite batch."
        ),
    }


def build_negative_control_report(
    rows: Sequence[Mapping[str, object]],
    *,
    replication_ids: Sequence[int] = REPLICATION_IDS,
    study_id: str = STUDY_ID,
    ci_level: float = DEFAULT_CI_LEVEL,
    absolute_margin_seconds: float = NEGATIVE_CONTROL_ABSOLUTE_MARGIN_SECONDS,
    relative_margin: float = NEGATIVE_CONTROL_RELATIVE_MARGIN,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    """Test practical invariance to B in the Security-limited control regime."""

    if absolute_margin_seconds < 0 or relative_margin < 0:
        raise ValueError("negative-control equivalence margins must be nonnegative")
    security, immigration = (30, 21)
    indexed = {_run_key(row): row for row in rows}
    baseline = [
        float(
            indexed[
                (
                    security,
                    immigration,
                    NONBINDING_BUFFER,
                    int(replication_id),
                )
            ]["system_time_p95_seconds"]
        )
        for replication_id in replication_ids
    ]
    baseline_mean = sum(baseline) / len(baseline)
    equivalence_margin = max(
        absolute_margin_seconds,
        relative_margin * abs(baseline_mean),
    )

    contrast_rows: list[dict[str, object]] = []
    errors: list[str] = []
    for buffer_capacity in BUFFER_LEVELS:
        if buffer_capacity == NONBINDING_BUFFER:
            continue
        differences: list[float] = []
        full_event_replications: list[int] = []
        exact_mismatch_replications: list[int] = []
        for replication_id in replication_ids:
            candidate = indexed[
                (
                    security,
                    immigration,
                    buffer_capacity,
                    int(replication_id),
                )
            ]
            reference = indexed[
                (
                    security,
                    immigration,
                    NONBINDING_BUFFER,
                    int(replication_id),
                )
            ]
            differences.append(
                float(candidate["system_time_p95_seconds"])
                - float(reference["system_time_p95_seconds"])
            )
            if (
                float(candidate["interstage_buffer_full_time_fraction"]) != 0
                or float(reference["interstage_buffer_full_time_fraction"]) != 0
            ):
                full_event_replications.append(int(replication_id))
            if any(
                candidate[field] != reference[field]
                for field in EXACT_REPLAY_FIELDS
            ):
                exact_mismatch_replications.append(int(replication_id))
        summary = one_sample_summary(differences, ci_level=ci_level)
        ci_low = float(summary["ci_low"])
        ci_high = float(summary["ci_high"])
        ci_equivalent = (
            ci_low >= -equivalence_margin and ci_high <= equivalence_margin
        )
        zero_buffer_full = not full_event_replications
        exact_replay = not exact_mismatch_replications
        equivalent = ci_equivalent and zero_buffer_full and exact_replay
        if not ci_equivalent:
            errors.append(
                f"S30/I21 B{buffer_capacity} minus B{NONBINDING_BUFFER} "
                f"95% CI [{ci_low:.6g}, {ci_high:.6g}] exceeds "
                f"+/-{equivalence_margin:.6g} seconds"
            )
        if not zero_buffer_full:
            errors.append(
                f"S30/I21 B{buffer_capacity} reports buffer-full time in "
                f"replications {full_event_replications[:10]}"
            )
        if not exact_replay:
            errors.append(
                f"S30/I21 B{buffer_capacity} is not an exact replay of "
                f"B{NONBINDING_BUFFER} in replications "
                f"{exact_mismatch_replications[:10]}"
            )
        contrast_rows.append(
            {
                "schema_version": SCHEMA_VERSION,
                "study_id": study_id,
                "regime": REGIME_NAMES[(security, immigration)],
                "security_capacity": security,
                "immigration_capacity": immigration,
                "interstage_buffer_capacity": buffer_capacity,
                "reference_buffer_capacity": NONBINDING_BUFFER,
                "metric": "system_time_p95_seconds",
                "contrast": (
                    f"B{buffer_capacity}_MINUS_B{NONBINDING_BUFFER}"
                ),
                "n_pairs": int(summary["n"]),
                "mean_difference_seconds": float(summary["mean"]),
                "standard_deviation": float(summary["standard_deviation"]),
                "standard_error": float(summary["standard_error"]),
                "degrees_of_freedom": float(summary["degrees_of_freedom"]),
                "ci_level": ci_level,
                "ci_low_seconds": ci_low,
                "ci_high_seconds": ci_high,
                "equivalence_margin_seconds": equivalence_margin,
                "zero_buffer_full_status": (
                    "PASS" if zero_buffer_full else "FAIL"
                ),
                "exact_replay_status": "PASS" if exact_replay else "FAIL",
                "equivalence_status": "PASS" if equivalent else "FAIL",
            }
        )

    report = {
        "schema_version": SCHEMA_VERSION,
        "validation_id": NEGATIVE_CONTROL_ID,
        "status": "PASS" if not errors else "FAIL",
        "study_id": study_id,
        "regime": REGIME_NAMES[(security, immigration)],
        "security_capacity": security,
        "immigration_capacity": immigration,
        "metric": "system_time_p95_seconds",
        "reference_buffer_capacity": NONBINDING_BUFFER,
        "baseline_mean_seconds": baseline_mean,
        "absolute_margin_floor_seconds": absolute_margin_seconds,
        "relative_margin_fraction": relative_margin,
        "equivalence_margin_seconds": equivalence_margin,
        "gate": (
            "The full paired two-sided 95% CI for every finite-B minus "
            "non-binding contrast must lie inside the registered practical-"
            "equivalence interval. Because this negative control must never "
            "fill, every finite arm must also exactly replay B5000."
        ),
        "contrasts": contrast_rows,
        "errors": errors,
    }
    return report, contrast_rows


def build_cell_estimates(
    rows: Sequence[Mapping[str, object]],
    *,
    replication_ids: Sequence[int] = REPLICATION_IDS,
    study_id: str = STUDY_ID,
    ci_level: float = DEFAULT_CI_LEVEL,
) -> list[dict[str, object]]:
    """Summarise replication-level KPIs after every validation gate passes."""

    by_cell: dict[Cell, list[Mapping[str, object]]] = defaultdict(list)
    for row in rows:
        by_cell[_cell(row)].append(row)

    estimates: list[dict[str, object]] = []
    for security, immigration in REGIMES:
        for buffer_capacity in BUFFER_LEVELS:
            cell = (security, immigration, buffer_capacity)
            cell_rows = sorted(
                by_cell[cell], key=lambda row: int(row["replication_id"])
            )
            if tuple(int(row["replication_id"]) for row in cell_rows) != tuple(
                int(value) for value in replication_ids
            ):
                raise ValueError(f"replication ordering/coverage drifted for {cell}")
            for metric in CHART_METRICS:
                summary = one_sample_summary(
                    [float(row[metric]) for row in cell_rows],
                    ci_level=ci_level,
                )
                estimates.append(
                    {
                        "schema_version": SCHEMA_VERSION,
                        "study_id": study_id,
                        "regime": REGIME_NAMES[(security, immigration)],
                        "security_capacity": security,
                        "immigration_capacity": immigration,
                        "interstage_buffer_capacity": buffer_capacity,
                        "buffer_label": (
                            "NONBINDING_5000"
                            if buffer_capacity == NONBINDING_BUFFER
                            else str(buffer_capacity)
                        ),
                        "metric": metric,
                        "estimand": "MEAN_OF_REPLICATION_LEVEL_METRIC",
                        "n_replications": int(summary["n"]),
                        "mean": float(summary["mean"]),
                        "standard_deviation": float(
                            summary["standard_deviation"]
                        ),
                        "standard_error": float(summary["standard_error"]),
                        "degrees_of_freedom": float(
                            summary["degrees_of_freedom"]
                        ),
                        "ci_level": ci_level,
                        "ci_low": float(summary["ci_low"]),
                        "ci_high": float(summary["ci_high"]),
                        "analysis_role": (
                            "PRIMARY" if metric == "system_time_p95_seconds"
                            else "MECHANISM_DIAGNOSTIC"
                        ),
                    }
                )
    return estimates


def build_chart_payload(
    estimates: Sequence[Mapping[str, object]],
    *,
    study_id: str = STUDY_ID,
) -> dict[str, object]:
    indexed = {
        (
            int(row["security_capacity"]),
            int(row["immigration_capacity"]),
            int(row["interstage_buffer_capacity"]),
            str(row["metric"]),
        ): row
        for row in estimates
    }
    series: list[dict[str, object]] = []
    for security, immigration in REGIMES:
        for metric in CHART_METRICS:
            points = []
            for buffer_capacity in BUFFER_LEVELS:
                row = indexed[
                    (security, immigration, buffer_capacity, metric)
                ]
                points.append(
                    {
                        "interstage_buffer_capacity": buffer_capacity,
                        "buffer_label": row["buffer_label"],
                        "mean": row["mean"],
                        "ci_low": row["ci_low"],
                        "ci_high": row["ci_high"],
                    }
                )
            series.append(
                {
                    "regime": REGIME_NAMES[(security, immigration)],
                    "security_capacity": security,
                    "immigration_capacity": immigration,
                    "metric": metric,
                    "points": points,
                }
            )
    return {
        "schema_version": SCHEMA_VERSION,
        "study_id": study_id,
        "chart_id": "CHART_D_INTERSTAGE_BUFFER_BAS_V1",
        "title": (
            "Finite interstage space creates spillback only under "
            "downstream pressure"
        ),
        "buffer_levels": list(BUFFER_LEVELS),
        "series": series,
        "claim_boundary": CLAIM_BOUNDARY,
    }


def _failure_manifest(
    *,
    input_csv: Path,
    stage: str,
    error: str,
) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "analysis_id": ANALYSIS_ID,
        "status": "FAIL",
        "failed_stage": stage,
        "input_csv": portable_path(input_csv),
        "input_sha256": _sha256(input_csv) if input_csv.exists() else None,
        "error": error,
        "claim_boundary": CLAIM_BOUNDARY,
    }


def analyse_csv(
    input_csv: Path = DEFAULT_INPUT_CSV,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
) -> dict[str, object]:
    """Validate one imported batch and write a plot-ready analysis package."""

    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        design_validation = validate_interstage_buffer_design()
        if design_validation["status"] != "PASS":
            raise ValueError(
                "frozen interstage-buffer design failed validation: "
                + "; ".join(str(value) for value in design_validation["errors"])
            )
        raw_rows = _read_csv(input_csv)
        rows, validation = validate_imported_rows(raw_rows)
        registered_contract = build_registered_contract_report(
            rows,
            load_interstage_buffer_scenario_rows(),
            load_interstage_buffer_seed_rows(),
        )
    except (OSError, ValueError) as error:
        failure = _failure_manifest(
            input_csv=input_csv,
            stage="IMPORT_VALIDATION",
            error=str(error),
        )
        _write_json(output_dir / "validation.json", failure)
        _write_json(output_dir / "analysis_manifest.json", failure)
        raise
    _write_json(output_dir / "validation.json", validation)
    _write_json(
        output_dir / "registered_contract.json",
        registered_contract,
    )

    crn = build_crn_alignment_report(rows)
    replay = build_exact_replay_report(rows)
    negative_control, contrast_rows = build_negative_control_report(rows)
    _write_json(output_dir / "crn_alignment.json", crn)
    _write_json(output_dir / "exact_replay_validation.json", replay)
    _write_json(
        output_dir / "negative_control_invariance.json",
        negative_control,
    )
    _write_csv(
        output_dir / "negative_control_contrasts.csv",
        contrast_rows,
        NEGATIVE_CONTROL_CONTRAST_FIELDS,
    )
    for stage, report in (
        ("REGISTERED_CONTRACT", registered_contract),
        ("CRN_ALIGNMENT", crn),
        ("EXACT_REPLAY", replay),
        ("NEGATIVE_CONTROL_INVARIANCE", negative_control),
    ):
        if report["status"] != "PASS":
            error = "; ".join(str(value) for value in report["errors"][:10])
            failure = _failure_manifest(
                input_csv=input_csv,
                stage=stage,
                error=error,
            )
            _write_json(output_dir / "analysis_manifest.json", failure)
            raise ValueError(f"{stage} failed: {error}")

    estimates = build_cell_estimates(rows)
    payload = build_chart_payload(estimates)
    _write_csv(
        output_dir / "replication_kpis.csv",
        rows,
        REPLICATION_FIELDS,
    )
    _write_csv(
        output_dir / "cell_estimates.csv",
        estimates,
        ESTIMATE_FIELDS,
    )
    _write_json(output_dir / "chart_d_payload.json", payload)

    output_filenames = (
        "validation.json",
        "registered_contract.json",
        "crn_alignment.json",
        "exact_replay_validation.json",
        "negative_control_invariance.json",
        "negative_control_contrasts.csv",
        "replication_kpis.csv",
        "cell_estimates.csv",
        "chart_d_payload.json",
    )
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "analysis_id": ANALYSIS_ID,
        "status": "PASS",
        "study_id": STUDY_ID,
        "input_csv": portable_path(input_csv),
        "input_sha256": _sha256(input_csv),
        "actual_run_count": len(rows),
        "expected_run_count": EXPECTED_RUN_COUNT,
        "cell_count": len(REGIMES) * len(BUFFER_LEVELS),
        "replications_per_cell": len(REPLICATION_IDS),
        "ci_level": DEFAULT_CI_LEVEL,
        "primary_metric": "system_time_p95_seconds",
        "mechanism_metric": "security_blocked_resource_fraction",
        "mechanism_metric_formula": (
            "security_blocked_resource_seconds / "
            "(security_capacity * last_exit_seconds)"
        ),
        "occupied_time_diagnostic": "security_blocked_share_of_occupied",
        "gates": {
            "import_validation": validation["status"],
            "registered_contract": registered_contract["status"],
            "crn_alignment": crn["status"],
            "exact_replay": replay["status"],
            "negative_control_invariance": negative_control["status"],
        },
        "outputs": [
            {
                "path": portable_path(output_dir / filename),
                "sha256": _sha256(output_dir / filename),
            }
            for filename in output_filenames
        ],
        "claim_boundary": CLAIM_BOUNDARY,
    }
    _write_json(output_dir / "analysis_manifest.json", manifest)
    return manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate the registered 400-run finite-buffer AnyLogic export "
            "and build compact Chart-D analysis inputs."
        )
    )
    parser.add_argument(
        "--input-csv",
        type=Path,
        default=DEFAULT_INPUT_CSV,
        help="Replication-level AnyLogic batch CSV.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Destination for validated analysis outputs.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    manifest = analyse_csv(args.input_csv, args.output_dir)
    print(
        "Validated "
        f"{manifest['actual_run_count']} finite-buffer runs; "
        f"analysis package: {args.output_dir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
