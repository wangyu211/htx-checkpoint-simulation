"""Validate and analyse the selected-cell peak-duration sensitivity study.

The analysis is deliberately fail-closed.  It accepts only the frozen
4-capacity-by-5-duration-by-50-replication design, validates every raw table
against the canonical result schemas, and reconstructs duration-specific queue
metrics from traveller event ledgers.  It never treats a long stationary-HPP
extension as observed time-of-day demand or an overloaded finite-horizon run
as a steady-state estimate.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from src.analysis.analyse_capacity_availability import (
    extract_waiting_intervals,
    queue_length_metrics_from_intervals,
    reconstruct_queue_length_metrics,
)
from src.analysis.analyse_operational_replications import (
    one_sample_summary,
    portable_path,
)
from src.analysis.capacity_response_surface_design import (
    DEFAULT_SCENARIOS as DEFAULT_PRIOR_SCENARIOS,
    load_response_surface_scenario_rows,
    response_scenario_id,
)
from src.analysis.peak_duration_sensitivity_design import (
    DEFAULT_DESIGN,
    DEFAULT_SCENARIOS,
    DEFAULT_SEED_MANIFEST,
    EXPECTED_CAPACITY_CELLS,
    EXPECTED_CUTOFF_SECONDS,
    EXPECTED_REPLICATIONS_PER_CELL,
    EXPECTED_RUN_COUNT,
    EXPECTED_TARGET_INPUT_SAMPLE_ID,
    SEED_COLUMNS,
    duration_scenario_id,
    load_design,
    load_peak_duration_scenario_rows,
    load_peak_duration_seed_rows,
    validate_peak_duration_design,
)
from src.analysis.validate_crn_alignment import (
    DRAW_FIELDS,
    STREAM_SEED_FIELDS,
)
from src.analysis.validate_operational_contract import scenario_config_sha256
from src.analysis.validate_operational_results import (
    DEFAULT_SCHEMA_REGISTRY,
    RESULT_FILES,
    load_result_schemas,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RESULTS_ROOT = (
    PROJECT_ROOT / "results" / "raw" / "peak_duration_sensitivity"
)
DEFAULT_OUTPUT_DIR = (
    PROJECT_ROOT / "results" / "analysis" / "peak_duration_sensitivity"
)
DEFAULT_PRIOR_RESULTS_ROOT = (
    PROJECT_ROOT / "results" / "raw" / "capacity_response_surface"
)

ANALYSIS_ID = "TASK3_PEAK_DURATION_SENSITIVITY_ANALYSIS_V1"
VALIDATION_ID = "TASK3_PEAK_DURATION_SENSITIVITY_INPUT_VALIDATION_V1"
CRN_VALIDATION_ID = "PEAK_DURATION_SENSITIVITY_CRN_ALIGNMENT_V1"
CROSS_BATCH_ID = "PEAK_DURATION_T300_CROSS_BATCH_REPRODUCIBILITY_V1"
SCHEMA_VERSION = "1.0"
DEFAULT_CI_LEVEL = 0.95
DEFAULT_NUMERIC_TOLERANCE = 1e-9
REPLICATION_IDS = tuple(range(1, EXPECTED_REPLICATIONS_PER_CELL + 1))
CAPACITY_CELLS = EXPECTED_CAPACITY_CELLS
CUTOFF_SECONDS = EXPECTED_CUTOFF_SECONDS
REFERENCE_CAPACITY = (36, 21)
PRIOR_INPUT_SAMPLE_ID = "LOCAL_WINDOW_HPP_BASE"

LINEAGE_FIELDS = (
    "schema_version",
    "config_id",
    "config_sha256",
    "model_version",
    "scenario_id",
    "input_sample_id",
    "replication_id",
)
COUNT_FIELDS = (
    "arrivals",
    "completed_at_cutoff",
    "security_queue_at_cutoff",
    "security_in_service_at_cutoff",
    "immigration_queue_at_cutoff",
    "immigration_in_service_at_cutoff",
    "wip_at_cutoff",
    "completed_after_drain",
    "rejected_or_dropped_count",
    "technology_count",
    "additional_check_count",
    "cutoff_backlog",
)
GROWTH_WINDOW_FIELDS = (
    "queue_mean_window_50_60",
    "queue_mean_window_60_70",
    "queue_mean_window_70_80",
    "queue_mean_window_80_90",
    "queue_mean_window_90_100",
)
ANALYSIS_METRICS = (
    "total_queue_wait_mean_seconds",
    "total_queue_wait_p95_seconds",
    "arrival_window_time_weighted_mean_total_waiting_queue",
    "arrival_window_peak_total_waiting_queue",
    "security_waiting_at_cutoff",
    "immigration_waiting_at_cutoff",
    "total_waiting_at_cutoff",
    "cutoff_backlog",
    "late_arrival_total_queue_wait_p95_seconds",
    "cohort_clear_time_after_cutoff_seconds",
    *GROWTH_WINDOW_FIELDS,
    "arrival_window_queue_growth_slope_travellers_per_second",
)
INCREMENT_METRICS = (
    "total_queue_wait_p95_seconds",
    "arrival_window_time_weighted_mean_total_waiting_queue",
    "arrival_window_peak_total_waiting_queue",
    "total_waiting_at_cutoff",
    "cutoff_backlog",
    "late_arrival_total_queue_wait_p95_seconds",
    "cohort_clear_time_after_cutoff_seconds",
    "arrival_window_queue_growth_slope_travellers_per_second",
)
CROSS_BATCH_METRICS = ANALYSIS_METRICS

REPLICATION_FIELDS = (
    "schema_version",
    "study_id",
    "scenario_id",
    "input_sample_id",
    "replication_id",
    "security_capacity",
    "immigration_capacity",
    "arrival_cutoff_seconds",
    "config_id",
    "config_sha256",
    "model_version",
    "master_seed",
    "arrival_seed",
    "service_seed",
    "routing_seed",
    "tie_seed",
    "arrival_guard",
    "security_queue_capacity",
    "immigration_queue_capacity",
    "arrivals",
    "completed_after_drain",
    "rejected_or_dropped_count",
    "total_queue_wait_mean_seconds",
    "total_queue_wait_p95_seconds",
    "arrival_window_time_weighted_mean_security_waiting_queue",
    "arrival_window_time_weighted_mean_immigration_waiting_queue",
    "arrival_window_time_weighted_mean_total_waiting_queue",
    "arrival_window_peak_security_waiting_queue",
    "arrival_window_peak_immigration_waiting_queue",
    "arrival_window_peak_total_waiting_queue",
    "security_waiting_at_cutoff",
    "immigration_waiting_at_cutoff",
    "total_waiting_at_cutoff",
    "cutoff_backlog",
    "late_arrival_count",
    "late_arrival_total_queue_wait_p95_seconds",
    "cohort_clear_time_after_cutoff_seconds",
    *GROWTH_WINDOW_FIELDS,
    "arrival_window_queue_growth_intercept",
    "arrival_window_queue_growth_slope_travellers_per_second",
    "security_rho_proxy",
    "immigration_rho_proxy",
    "rho_regime",
    "steady_state_claim_status",
)
ESTIMATE_FIELDS = (
    "schema_version",
    "study_id",
    "scenario_id",
    "input_sample_id",
    "security_capacity",
    "immigration_capacity",
    "arrival_cutoff_seconds",
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
    "security_rho_proxy",
    "immigration_rho_proxy",
    "rho_regime",
    "steady_state_claim_status",
    "analysis_role",
)
INCREMENT_FIELDS = (
    "schema_version",
    "study_id",
    "security_capacity",
    "immigration_capacity",
    "shorter_cutoff_seconds",
    "longer_cutoff_seconds",
    "shorter_scenario_id",
    "longer_scenario_id",
    "metric",
    "contrast",
    "n_pairs",
    "mean_increment",
    "standard_deviation",
    "standard_error",
    "degrees_of_freedom",
    "ci_level",
    "ci_low",
    "ci_high",
    "crn_alignment_status",
    "analysis_role",
)
GROWTH_DIAGNOSTIC_FIELDS = (
    "schema_version",
    "study_id",
    "scenario_id",
    "security_capacity",
    "immigration_capacity",
    "arrival_cutoff_seconds",
    "n_replications",
    "mean_growth_slope_travellers_per_second",
    "standard_deviation",
    "standard_error",
    "degrees_of_freedom",
    "ci_level",
    "ci_low",
    "ci_high",
    "mean_last_minus_first_window_queue",
    "last_minus_first_ci_low",
    "last_minus_first_ci_high",
    "growth_classification",
    "security_rho_proxy",
    "immigration_rho_proxy",
    "rho_regime",
    "steady_state_claim_status",
)
RAW_ARTIFACT_FIELDS = (
    "schema_version",
    "study_id",
    "scenario_id",
    "input_sample_id",
    "replication_id",
    "table_name",
    "path",
    "sha256",
    "row_count",
)

Capacity = tuple[int, int]
RunKey = tuple[Capacity, int, int]
PrefixKey = tuple[Capacity, int, int, int]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _tree_digest(entries: Sequence[Mapping[str, object]]) -> str:
    payload = json.dumps(
        sorted(
            [
                [str(row["path"]), str(row["sha256"])]
                for row in entries
            ]
        ),
        ensure_ascii=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _float(value: object, label: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{label} must be numeric") from error
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite")
    return result


def _integer(value: object, label: str) -> int:
    raw = str(value).strip()
    try:
        return int(raw)
    except ValueError as error:
        raise ValueError(f"{label} must be an integer") from error


def _boolean(value: object, label: str) -> bool:
    raw = str(value).strip().lower()
    if raw == "true":
        return True
    if raw == "false":
        return False
    raise ValueError(f"{label} must be true or false")


def _same_number(
    left: object,
    right: object,
    *,
    tolerance: float = DEFAULT_NUMERIC_TOLERANCE,
) -> bool:
    try:
        return math.isclose(
            float(left),
            float(right),
            rel_tol=tolerance,
            abs_tol=tolerance,
        )
    except (TypeError, ValueError):
        return False


def _canonical_numeric(value: object) -> str:
    number = _float(value, "exogenous draw")
    return number.hex()


def _load_table(
    path: Path,
    table_name: str,
    schema: Sequence[Mapping[str, str]],
) -> list[dict[str, str]]:
    if not path.is_file():
        raise FileNotFoundError(path)
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        expected = [str(field["field_name"]) for field in schema]
        if list(reader.fieldnames or ()) != expected:
            raise ValueError(f"{path}: canonical {table_name} schema mismatch")
        rows: list[dict[str, str]] = []
        for line, raw in enumerate(reader, start=2):
            row = {field: (raw.get(field) or "").strip() for field in expected}
            for field in schema:
                name = str(field["field_name"])
                value = row[name]
                nullable = str(field["nullable"]) == "true"
                if not value:
                    if not nullable:
                        raise ValueError(
                            f"{path}:{line}:{name}: null is not allowed"
                        )
                    continue
                data_type = str(field["data_type"])
                if data_type == "integer":
                    _integer(value, f"{path}:{line}:{name}")
                elif data_type == "number":
                    _float(value, f"{path}:{line}:{name}")
                elif data_type == "boolean":
                    _boolean(value, f"{path}:{line}:{name}")
                elif data_type != "string":
                    raise ValueError(
                        f"{path}:{line}:{name}: unsupported type {data_type}"
                    )
            rows.append(row)
    return rows


def _require_one(
    rows: Sequence[dict[str, str]],
    path: Path,
) -> dict[str, str]:
    if len(rows) != 1:
        raise ValueError(f"{path}: expected exactly one data row")
    return rows[0]


def _nearest_rank_p95(values: Sequence[float]) -> float:
    if not values:
        raise ValueError("P95 requires at least one value")
    ordered = sorted(_float(value, "P95 value") for value in values)
    return ordered[max(0, math.ceil(0.95 * len(ordered)) - 1)]


def _ols_slope(
    x_values: Sequence[float],
    y_values: Sequence[float],
) -> tuple[float, float]:
    if len(x_values) != len(y_values) or len(x_values) < 2:
        raise ValueError("OLS requires equal x/y vectors with at least 2 rows")
    x = [_float(value, "OLS x") for value in x_values]
    y = [_float(value, "OLS y") for value in y_values]
    x_mean = statistics.fmean(x)
    y_mean = statistics.fmean(y)
    denominator = sum((value - x_mean) ** 2 for value in x)
    if denominator <= 0:
        raise ValueError("OLS x values must have positive variance")
    slope = sum(
        (x_value - x_mean) * (y_value - y_mean)
        for x_value, y_value in zip(x, y)
    ) / denominator
    return y_mean - slope * x_mean, slope


def _queue_window_metrics(
    entity_rows: Sequence[Mapping[str, object]],
    *,
    start_seconds: float,
    end_seconds: float,
) -> dict[str, float | int]:
    intervals = extract_waiting_intervals(
        entity_rows,
        cutoff_seconds=end_seconds,
        window_start_seconds=start_seconds,
    )
    return queue_length_metrics_from_intervals(
        intervals,
        cutoff_seconds=end_seconds,
        window_start_seconds=start_seconds,
    )


def derive_duration_metrics(
    entity_rows: Iterable[Mapping[str, object]],
    *,
    cutoff_seconds: float,
) -> dict[str, float | int]:
    """Reconstruct all duration KPIs from one entity event ledger."""

    cutoff = _float(cutoff_seconds, "cutoff_seconds")
    if cutoff <= 0:
        raise ValueError("cutoff_seconds must be positive")
    rows = [dict(row) for row in entity_rows]
    if not rows:
        raise ValueError("duration metrics require at least one traveller")

    arrival_window = _queue_window_metrics(
        rows,
        start_seconds=0.0,
        end_seconds=cutoff,
    )
    security_waits: list[float] = []
    immigration_waits: list[float] = []
    total_waits: list[float] = []
    late_waits: list[float] = []
    security_waiting_at_cutoff = 0
    immigration_waiting_at_cutoff = 0
    cutoff_backlog = 0
    completed_at_cutoff = 0
    security_in_service_at_cutoff = 0
    immigration_in_service_at_cutoff = 0
    last_exit = cutoff
    late_start = 0.8 * cutoff

    for row_index, row in enumerate(rows, start=1):
        arrival = _float(row["arrival_seconds"], f"entity {row_index}:arrival")
        security_join = _float(
            row["security_queue_join_seconds"],
            f"entity {row_index}:security_queue_join",
        )
        security_start = _float(
            row["security_start_seconds"],
            f"entity {row_index}:security_start",
        )
        immigration_join = _float(
            row["immigration_queue_join_seconds"],
            f"entity {row_index}:immigration_queue_join",
        )
        immigration_start = _float(
            row["immigration_start_seconds"],
            f"entity {row_index}:immigration_start",
        )
        security_end = _float(
            row.get("security_end_seconds", security_start),
            f"entity {row_index}:security_end",
        )
        immigration_end = _float(
            row.get("immigration_primary_end_seconds", immigration_start),
            f"entity {row_index}:immigration_end",
        )
        exit_seconds = _float(
            row["exit_seconds"], f"entity {row_index}:exit"
        )
        if not 0 <= arrival < cutoff:
            raise ValueError(
                f"entity {row_index}: arrival is outside [0, cutoff)"
            )
        security_wait = security_start - security_join
        immigration_wait = immigration_start - immigration_join
        if security_wait < 0 or immigration_wait < 0:
            raise ValueError(f"entity {row_index}: negative queue wait")
        total_wait = security_wait + immigration_wait
        security_waits.append(security_wait)
        immigration_waits.append(immigration_wait)
        total_waits.append(total_wait)
        if arrival >= late_start:
            late_waits.append(total_wait)
        if security_join <= cutoff < security_start:
            security_waiting_at_cutoff += 1
        if immigration_join <= cutoff < immigration_start:
            immigration_waiting_at_cutoff += 1
        if security_start <= cutoff < security_end:
            security_in_service_at_cutoff += 1
        if immigration_start <= cutoff < immigration_end:
            immigration_in_service_at_cutoff += 1
        if exit_seconds > cutoff:
            cutoff_backlog += 1
        else:
            completed_at_cutoff += 1
        last_exit = max(last_exit, exit_seconds)

    if not late_waits:
        raise ValueError("the final 20% arrival window contains no travellers")

    growth_means: list[float] = []
    growth_midpoints: list[float] = []
    for window_index in range(5, 10):
        start = cutoff * window_index / 10.0
        end = cutoff * (window_index + 1) / 10.0
        window = _queue_window_metrics(
            rows,
            start_seconds=start,
            end_seconds=end,
        )
        growth_means.append(
            float(window["time_weighted_mean_total_waiting_queue"])
        )
        growth_midpoints.append((start + end) / 2.0)
    intercept, slope = _ols_slope(growth_midpoints, growth_means)
    full_drain = reconstruct_queue_length_metrics(
        rows,
        cutoff_seconds=cutoff,
    )

    return {
        "total_queue_wait_mean_seconds": statistics.fmean(total_waits),
        "total_queue_wait_p95_seconds": _nearest_rank_p95(total_waits),
        "security_wait_mean_seconds": statistics.fmean(security_waits),
        "security_wait_p95_seconds": _nearest_rank_p95(security_waits),
        "immigration_wait_mean_seconds": statistics.fmean(immigration_waits),
        "immigration_wait_p95_seconds": _nearest_rank_p95(
            immigration_waits
        ),
        "arrival_window_time_weighted_mean_security_waiting_queue": (
            arrival_window["security_queue_time_weighted_mean"]
        ),
        "arrival_window_time_weighted_mean_immigration_waiting_queue": (
            arrival_window["immigration_queue_time_weighted_mean"]
        ),
        "arrival_window_time_weighted_mean_total_waiting_queue": (
            arrival_window["time_weighted_mean_total_waiting_queue"]
        ),
        "arrival_window_peak_security_waiting_queue": arrival_window[
            "peak_security_waiting_queue"
        ],
        "arrival_window_peak_immigration_waiting_queue": arrival_window[
            "peak_immigration_waiting_queue"
        ],
        "arrival_window_peak_total_waiting_queue": arrival_window[
            "peak_total_waiting_queue"
        ],
        "security_waiting_at_cutoff": security_waiting_at_cutoff,
        "immigration_waiting_at_cutoff": immigration_waiting_at_cutoff,
        "total_waiting_at_cutoff": (
            security_waiting_at_cutoff + immigration_waiting_at_cutoff
        ),
        "security_in_service_at_cutoff": security_in_service_at_cutoff,
        "immigration_in_service_at_cutoff": immigration_in_service_at_cutoff,
        "completed_at_cutoff": completed_at_cutoff,
        "cutoff_backlog": cutoff_backlog,
        "late_arrival_count": len(late_waits),
        "late_arrival_total_queue_wait_p95_seconds": _nearest_rank_p95(
            late_waits
        ),
        "cohort_clear_time_after_cutoff_seconds": max(
            0.0, last_exit - cutoff
        ),
        "last_exit_seconds": last_exit,
        "full_drain_peak_security_waiting_queue": full_drain[
            "peak_security_waiting_queue"
        ],
        "full_drain_peak_immigration_waiting_queue": full_drain[
            "peak_immigration_waiting_queue"
        ],
        **{
            field: growth_means[index]
            for index, field in enumerate(GROWTH_WINDOW_FIELDS)
        },
        "arrival_window_queue_growth_intercept": intercept,
        "arrival_window_queue_growth_slope_travellers_per_second": slope,
    }


def _validate_entity_chronology(
    row: Mapping[str, str],
    *,
    cutoff_seconds: float,
    drain_end_seconds: float,
    label: str,
) -> None:
    ordered_fields = (
        "arrival_seconds",
        "security_queue_join_seconds",
        "security_start_seconds",
        "security_end_seconds",
        "immigration_queue_join_seconds",
        "immigration_start_seconds",
        "immigration_primary_end_seconds",
        "exit_seconds",
    )
    times = [_float(row[field], f"{label}:{field}") for field in ordered_fields]
    if any(value < 0 for value in times):
        raise ValueError(f"{label}: event timestamps must be non-negative")
    if any(later < earlier for earlier, later in zip(times, times[1:])):
        raise ValueError(f"{label}: illegal event timestamp order")
    if times[0] >= cutoff_seconds:
        raise ValueError(f"{label}: arrival is outside [0, cutoff)")
    if times[-1] > drain_end_seconds + DEFAULT_NUMERIC_TOLERANCE:
        raise ValueError(f"{label}: exit occurs after recorded drain end")

    security_demand = _float(
        row["security_service_demand_seconds"],
        f"{label}:security_service_demand_seconds",
    )
    immigration_demand = _float(
        row["immigration_primary_service_demand_seconds"],
        f"{label}:immigration_primary_service_demand_seconds",
    )
    if not _same_number(times[3] - times[2], security_demand):
        raise ValueError(f"{label}: Security service duration is inconsistent")
    if not _same_number(times[6] - times[5], immigration_demand):
        raise ValueError(
            f"{label}: Immigration service duration is inconsistent"
        )
    for field in ("automation_u", "additional_check_u", "lane_tie_u"):
        draw = _float(row[field], f"{label}:{field}")
        if not 0 <= draw <= 1:
            raise ValueError(f"{label}:{field} must be in [0,1]")
    if _boolean(row["technology_flag"], f"{label}:technology_flag"):
        raise ValueError(f"{label}: technology routing must remain disabled")
    if _boolean(
        row["additional_check_flag"],
        f"{label}:additional_check_flag",
    ):
        raise ValueError(f"{label}: additional checks must remain disabled")
    if row["additional_check_service_demand_seconds"] or row[
        "additional_check_end_seconds"
    ]:
        raise ValueError(f"{label}: disabled additional-check fields not blank")


def _signature_for_rows(
    entity_rows: Sequence[Mapping[str, str]],
    *,
    label: str,
) -> tuple[int, str]:
    signatures: list[str] = []
    traveller_ids: set[str] = set()
    for row_index, row in enumerate(entity_rows, start=1):
        traveller_id = str(row.get("traveller_id", "")).strip()
        if not traveller_id:
            raise ValueError(f"{label}: entity {row_index} has no traveller_id")
        if traveller_id in traveller_ids:
            raise ValueError(
                f"{label}: duplicate traveller_id {traveller_id!r}"
            )
        traveller_ids.add(traveller_id)
        signatures.append(
            json.dumps(
                [
                    traveller_id,
                    *[
                        _canonical_numeric(row.get(field, ""))
                        for field in DRAW_FIELDS
                    ],
                ],
                ensure_ascii=True,
                separators=(",", ":"),
            )
        )
    digest = hashlib.sha256(
        ("\n".join(sorted(signatures)) + "\n").encode("utf-8")
    ).hexdigest()
    return len(signatures), digest


def _prefix_signatures(
    entity_rows: Sequence[Mapping[str, str]],
    *,
    thresholds: Sequence[int],
    label: str,
) -> dict[int, tuple[int, str]]:
    signatures: dict[int, tuple[int, str]] = {}
    for threshold in thresholds:
        prefix = [
            row
            for row in entity_rows
            if _float(row["arrival_seconds"], f"{label}:arrival")
            < threshold
        ]
        signatures[int(threshold)] = _signature_for_rows(
            prefix,
            label=f"{label}:prefix<{threshold}",
        )
    return signatures


def _run_directory(
    root: Path,
    scenario_id: str,
    input_sample_id: str,
    replication_id: int,
) -> Path:
    return (
        root
        / scenario_id
        / input_sample_id
        / f"replication_{replication_id:03d}"
    )


def _expected_run_directories(
    root: Path,
    *,
    capacities: Sequence[Capacity] = CAPACITY_CELLS,
    cutoffs: Sequence[int] = CUTOFF_SECONDS,
    replication_ids: Sequence[int] = REPLICATION_IDS,
) -> dict[Path, tuple[Capacity, int, int]]:
    return {
        _run_directory(
            root,
            duration_scenario_id(*capacity, cutoff),
            EXPECTED_TARGET_INPUT_SAMPLE_ID,
            replication_id,
        ): (capacity, cutoff, replication_id)
        for capacity in capacities
        for cutoff in cutoffs
        for replication_id in replication_ids
    }


def _validate_exact_coverage(
    results_root: Path,
    expected_directories: Mapping[Path, object],
) -> None:
    if not results_root.is_dir():
        raise FileNotFoundError(
            f"peak-duration raw results do not exist: {results_root}"
        )
    expected = {
        directory.resolve() / RESULT_FILES["run_manifest"]
        for directory in expected_directories
    }
    actual = {
        path.resolve()
        for path in results_root.rglob(RESULT_FILES["run_manifest"])
    }
    missing = sorted(expected - actual)
    unexpected = sorted(actual - expected)
    if missing:
        excerpt = ", ".join(str(path) for path in missing[:3])
        raise ValueError(
            f"peak-duration coverage is incomplete: {len(missing)} "
            f"run manifests are missing ({excerpt})"
        )
    if unexpected:
        excerpt = ", ".join(str(path) for path in unexpected[:3])
        raise ValueError(
            f"peak-duration coverage has {len(unexpected)} unexpected "
            f"runs ({excerpt})"
        )


def _rho_metadata(
    security_capacity: int,
    immigration_capacity: int,
    *,
    arrival_rate_per_second: float,
    security_service_seconds: float,
    immigration_service_seconds: float,
) -> dict[str, object]:
    security_rho = (
        arrival_rate_per_second
        * security_service_seconds
        / security_capacity
    )
    immigration_rho = (
        arrival_rate_per_second
        * immigration_service_seconds
        / immigration_capacity
    )
    overloaded = security_rho >= 1.0 or immigration_rho >= 1.0
    return {
        "security_rho_proxy": security_rho,
        "immigration_rho_proxy": immigration_rho,
        "rho_regime": (
            "RHO_GTE_ONE_FINITE_HORIZON_ONLY"
            if overloaded
            else "RHO_LT_ONE_TERMINATING_COHORT"
        ),
        "steady_state_claim_status": (
            "PROHIBITED_RHO_GTE_ONE"
            if overloaded
            else "NOT_ESTIMATED_TERMINATING_COHORT"
        ),
    }


def _validate_run_records(
    manifest: Mapping[str, str],
    kpi: Mapping[str, str],
    entities: Sequence[Mapping[str, str]],
    *,
    run_label: str,
    capacity: Capacity,
    cutoff_seconds: int,
    replication_id: int,
    scenario_row: Mapping[str, str],
    seed_row: Mapping[str, str],
    study_id: str,
    arrival_rate_per_second: float,
    security_service_seconds: float,
    immigration_service_seconds: float,
) -> tuple[dict[str, object], dict[int, tuple[int, str]]]:
    scenario_id = duration_scenario_id(*capacity, cutoff_seconds)
    expected_key = (
        scenario_id,
        str(scenario_row["input_sample_id"]),
        str(replication_id),
    )
    for label, row in (
        ("run_manifest", manifest),
        ("replication_kpis", kpi),
    ):
        actual_key = (
            str(row["scenario_id"]),
            str(row["input_sample_id"]),
            str(row["replication_id"]),
        )
        if actual_key != expected_key:
            raise ValueError(
                f"{run_label}/{label}: run key {actual_key} != {expected_key}"
            )

    expected_hash = scenario_config_sha256(scenario_row)
    if manifest["config_id"] != scenario_row["config_id"]:
        raise ValueError(f"{run_label}: config_id differs from frozen scenario")
    if manifest["config_sha256"] != expected_hash:
        raise ValueError(
            f"{run_label}: config_sha256 differs from frozen scenario"
        )
    for field in (
        "scenario_family",
        "reference_scenario_id",
        "arrival_mode",
        "drain_rule",
        "calibration_status",
        "claim_ceiling",
        "crn_alignment_status",
    ):
        if manifest[field] != scenario_row[field]:
            raise ValueError(
                f"{run_label}: manifest {field} differs from frozen scenario"
            )
    if manifest["start_state"] != "EMPTY_AND_IDLE":
        raise ValueError(f"{run_label}: start_state must be EMPTY_AND_IDLE")
    if manifest["run_status"] != "COMPLETE":
        raise ValueError(f"{run_label}: run_status must be COMPLETE")
    if not str(manifest["model_version"]).strip():
        raise ValueError(f"{run_label}: model_version is blank")
    if not _same_number(
        manifest["arrival_cutoff_seconds"],
        cutoff_seconds,
    ):
        raise ValueError(f"{run_label}: arrival cutoff drifted")
    for field in ("master_seed", *STREAM_SEED_FIELDS):
        if manifest[field] != seed_row[field]:
            raise ValueError(f"{run_label}: {field} differs from seed manifest")

    for field in LINEAGE_FIELDS:
        if kpi[field] != manifest[field]:
            raise ValueError(f"{run_label}: KPI {field} differs from manifest")
    if kpi["run_status"] != "COMPLETE":
        raise ValueError(f"{run_label}: KPI run_status must be COMPLETE")
    if not _boolean(
        kpi["conservation_pass"],
        f"{run_label}:conservation_pass",
    ):
        raise ValueError(f"{run_label}: conservation_pass must be true")
    if not _same_number(
        kpi["arrival_cutoff_seconds"],
        manifest["arrival_cutoff_seconds"],
    ) or not _same_number(
        kpi["drain_end_seconds"],
        manifest["drain_end_seconds"],
    ):
        raise ValueError(f"{run_label}: KPI timing lineage differs")

    counts = {
        field: _integer(kpi[field], f"{run_label}:{field}")
        for field in COUNT_FIELDS
    }
    if any(value < 0 for value in counts.values()):
        raise ValueError(f"{run_label}: KPI counts must be non-negative")
    if counts["rejected_or_dropped_count"] != 0:
        raise ValueError(f"{run_label}: rejected/dropped count must be zero")
    if counts["technology_count"] != 0:
        raise ValueError(f"{run_label}: technology count must be zero")
    if counts["additional_check_count"] != 0:
        raise ValueError(f"{run_label}: additional-check count must be zero")
    if len(entities) != counts["arrivals"]:
        raise ValueError(
            f"{run_label}: entity count {len(entities)} != "
            f"arrivals {counts['arrivals']}"
        )
    if counts["arrivals"] <= 0:
        raise ValueError(f"{run_label}: arrivals must be positive")
    if counts["arrivals"] >= int(scenario_row["arrival_guard"]):
        raise ValueError(f"{run_label}: arrival guard bound or was reached")

    wip_components = (
        counts["security_queue_at_cutoff"]
        + counts["security_in_service_at_cutoff"]
        + counts["immigration_queue_at_cutoff"]
        + counts["immigration_in_service_at_cutoff"]
    )
    if counts["wip_at_cutoff"] != wip_components:
        raise ValueError(f"{run_label}: cutoff WIP components do not sum")
    if counts["arrivals"] != (
        counts["completed_at_cutoff"] + counts["wip_at_cutoff"]
    ):
        raise ValueError(f"{run_label}: cutoff conservation fails")
    if counts["cutoff_backlog"] != counts["wip_at_cutoff"]:
        raise ValueError(f"{run_label}: cutoff backlog differs from WIP")
    if counts["completed_after_drain"] != counts["arrivals"]:
        raise ValueError(f"{run_label}: full-drain conservation fails")

    drain_end = _float(
        manifest["drain_end_seconds"],
        f"{run_label}:drain_end_seconds",
    )
    if drain_end < cutoff_seconds:
        raise ValueError(f"{run_label}: drain ends before cutoff")
    for row_index, entity in enumerate(entities, start=2):
        for field in LINEAGE_FIELDS:
            if entity[field] != manifest[field]:
                raise ValueError(
                    f"{run_label}/entity_log.csv:{row_index}: "
                    f"{field} differs from manifest"
                )
        _validate_entity_chronology(
            entity,
            cutoff_seconds=float(cutoff_seconds),
            drain_end_seconds=drain_end,
            label=f"{run_label}/entity_log.csv:{row_index}",
        )

    derived = derive_duration_metrics(
        entities,
        cutoff_seconds=float(cutoff_seconds),
    )
    for field in (
        "total_queue_wait_mean_seconds",
        "total_queue_wait_p95_seconds",
        "security_wait_mean_seconds",
        "security_wait_p95_seconds",
        "immigration_wait_mean_seconds",
        "immigration_wait_p95_seconds",
        "cutoff_backlog",
        "cohort_clear_time_after_cutoff_seconds",
    ):
        if not _same_number(kpi[field], derived[field]):
            raise ValueError(
                f"{run_label}: KPI {field} differs from entity reconstruction"
            )
    if counts["security_queue_at_cutoff"] != int(
        derived["security_waiting_at_cutoff"]
    ):
        raise ValueError(
            f"{run_label}: Security cutoff queue differs from ledger"
        )
    if counts["immigration_queue_at_cutoff"] != int(
        derived["immigration_waiting_at_cutoff"]
    ):
        raise ValueError(
            f"{run_label}: Immigration cutoff queue differs from ledger"
        )
    for field in (
        "completed_at_cutoff",
        "security_in_service_at_cutoff",
        "immigration_in_service_at_cutoff",
        "cutoff_backlog",
    ):
        if counts[field] != int(derived[field]):
            raise ValueError(
                f"{run_label}: KPI {field} differs from entity ledger"
            )
    expected_backlog_fraction = counts["cutoff_backlog"] / counts["arrivals"]
    if not _same_number(
        kpi["cutoff_backlog_fraction"],
        expected_backlog_fraction,
    ):
        raise ValueError(f"{run_label}: cutoff backlog fraction is wrong")
    if not _same_number(drain_end, derived["last_exit_seconds"]):
        raise ValueError(
            f"{run_label}: drain_end_seconds differs from last entity exit"
        )

    security_cap = int(scenario_row["security_queue_capacity"])
    immigration_cap = int(scenario_row["immigration_queue_capacity"])
    if int(derived["full_drain_peak_security_waiting_queue"]) >= (
        security_cap
    ):
        raise ValueError(f"{run_label}: Security queue guard was reached")
    if int(derived["full_drain_peak_immigration_waiting_queue"]) >= (
        immigration_cap
    ):
        raise ValueError(f"{run_label}: Immigration queue guard was reached")

    metadata = _rho_metadata(
        *capacity,
        arrival_rate_per_second=arrival_rate_per_second,
        security_service_seconds=security_service_seconds,
        immigration_service_seconds=immigration_service_seconds,
    )
    row: dict[str, object] = {
        **kpi,
        **derived,
        **metadata,
        "study_id": study_id,
        "security_capacity": capacity[0],
        "immigration_capacity": capacity[1],
        "arrival_cutoff_seconds": cutoff_seconds,
        "arrival_guard": int(scenario_row["arrival_guard"]),
        "security_queue_capacity": security_cap,
        "immigration_queue_capacity": immigration_cap,
        "master_seed": manifest["master_seed"],
        "arrival_seed": manifest["arrival_seed"],
        "service_seed": manifest["service_seed"],
        "routing_seed": manifest["routing_seed"],
        "tie_seed": manifest["tie_seed"],
    }
    prefixes = _prefix_signatures(
        entities,
        thresholds=[
            cutoff
            for cutoff in CUTOFF_SECONDS
            if cutoff <= cutoff_seconds
        ],
        label=f"{run_label}/entity_log.csv",
    )
    return row, prefixes


def _validate_one_run(
    run_dir: Path,
    *,
    capacity: Capacity,
    cutoff_seconds: int,
    replication_id: int,
    scenario_row: Mapping[str, str],
    seed_row: Mapping[str, str],
    schemas: Mapping[str, Sequence[Mapping[str, str]]],
    study_id: str,
    arrival_rate_per_second: float,
    security_service_seconds: float,
    immigration_service_seconds: float,
) -> tuple[
    dict[str, object],
    dict[int, tuple[int, str]],
    list[dict[str, object]],
]:
    paths = {
        table: run_dir / filename for table, filename in RESULT_FILES.items()
    }
    manifest = _require_one(
        _load_table(
            paths["run_manifest"],
            "run_manifest",
            schemas["run_manifest"],
        ),
        paths["run_manifest"],
    )
    kpi = _require_one(
        _load_table(
            paths["replication_kpis"],
            "replication_kpis",
            schemas["replication_kpis"],
        ),
        paths["replication_kpis"],
    )
    entities = _load_table(
        paths["entity_log"],
        "entity_log",
        schemas["entity_log"],
    )
    row, prefixes = _validate_run_records(
        manifest,
        kpi,
        entities,
        run_label=str(run_dir),
        capacity=capacity,
        cutoff_seconds=cutoff_seconds,
        replication_id=replication_id,
        scenario_row=scenario_row,
        seed_row=seed_row,
        study_id=study_id,
        arrival_rate_per_second=arrival_rate_per_second,
        security_service_seconds=security_service_seconds,
        immigration_service_seconds=immigration_service_seconds,
    )
    artifacts = [
        {
            "schema_version": SCHEMA_VERSION,
            "study_id": study_id,
            "scenario_id": row["scenario_id"],
            "input_sample_id": row["input_sample_id"],
            "replication_id": replication_id,
            "table_name": table,
            "path": portable_path(path),
            "sha256": _sha256(path),
            "row_count": (
                len(entities)
                if table == "entity_log"
                else 1
            ),
        }
        for table, path in paths.items()
    ]
    return row, prefixes, artifacts


def build_crn_alignment_report(
    prefix_signatures: Mapping[PrefixKey, tuple[int, str]],
    *,
    capacities: Sequence[Capacity],
    cutoffs: Sequence[int],
    replication_ids: Sequence[int],
    study_id: str,
) -> dict[str, object]:
    """Validate same-duration capacity CRN and all nested duration prefixes."""

    errors: list[str] = []
    cross_capacity_comparisons = 0
    cross_capacity_traveller_pairs = 0
    nested_prefix_comparisons = 0
    nested_prefix_traveller_pairs = 0
    ordered_cutoffs = tuple(sorted(int(value) for value in cutoffs))

    for cutoff in ordered_cutoffs:
        for replication_id in replication_ids:
            reference = prefix_signatures.get(
                (REFERENCE_CAPACITY, cutoff, replication_id, cutoff)
            )
            if reference is None:
                errors.append(
                    f"T={cutoff} replication {replication_id}: "
                    "reference full signature missing"
                )
                continue
            for capacity in capacities:
                if capacity == REFERENCE_CAPACITY:
                    continue
                current = prefix_signatures.get(
                    (capacity, cutoff, replication_id, cutoff)
                )
                if current != reference:
                    errors.append(
                        f"T={cutoff} replication {replication_id}: "
                        f"capacity {capacity} exogenous signature differs"
                    )
                    continue
                cross_capacity_comparisons += 1
                cross_capacity_traveller_pairs += reference[0]

    for capacity in capacities:
        for replication_id in replication_ids:
            for short_index, short_cutoff in enumerate(ordered_cutoffs[:-1]):
                short_signature = prefix_signatures.get(
                    (
                        capacity,
                        short_cutoff,
                        replication_id,
                        short_cutoff,
                    )
                )
                if short_signature is None:
                    errors.append(
                        f"{capacity} replication {replication_id}: "
                        f"T={short_cutoff} full signature missing"
                    )
                    continue
                for long_cutoff in ordered_cutoffs[short_index + 1 :]:
                    long_prefix = prefix_signatures.get(
                        (
                            capacity,
                            long_cutoff,
                            replication_id,
                            short_cutoff,
                        )
                    )
                    if long_prefix != short_signature:
                        errors.append(
                            f"{capacity} replication {replication_id}: "
                            f"T={long_cutoff} prefix below {short_cutoff} "
                            "differs from shorter run"
                        )
                        continue
                    nested_prefix_comparisons += 1
                    nested_prefix_traveller_pairs += short_signature[0]

    expected_cross_capacity = (
        len(ordered_cutoffs)
        * len(replication_ids)
        * (len(capacities) - 1)
    )
    expected_nested = (
        len(capacities)
        * len(replication_ids)
        * (len(ordered_cutoffs) * (len(ordered_cutoffs) - 1) // 2)
    )
    same_duration_pass = (
        cross_capacity_comparisons == expected_cross_capacity
    )
    nested_pass = nested_prefix_comparisons == expected_nested
    passed = not errors and same_duration_pass and nested_pass
    return {
        "schema_version": SCHEMA_VERSION,
        "validation": CRN_VALIDATION_ID,
        "study_id": study_id,
        "status": "PASS" if passed else "FAIL",
        "input_sample_id": EXPECTED_TARGET_INPUT_SAMPLE_ID,
        "coverage_pass": len(prefix_signatures)
        == (
            len(capacities)
            * len(replication_ids)
            * sum(range(1, len(ordered_cutoffs) + 1))
        ),
        "seed_alignment_pass": passed,
        "same_duration_cross_capacity_exogenous_crn_pass": (
            same_duration_pass and not errors
        ),
        "cross_duration_nested_arrival_prefix_pass": (
            nested_pass and not errors
        ),
        "canonical_draw_fields": list(DRAW_FIELDS),
        "cross_capacity_comparison_count": cross_capacity_comparisons,
        "expected_cross_capacity_comparison_count": (
            expected_cross_capacity
        ),
        "cross_capacity_compared_traveller_pairs": (
            cross_capacity_traveller_pairs
        ),
        "nested_prefix_comparison_count": nested_prefix_comparisons,
        "expected_nested_prefix_comparison_count": expected_nested,
        "nested_prefix_compared_traveller_pairs": (
            nested_prefix_traveller_pairs
        ),
        "comparison_strategy": (
            "Canonical numeric SHA-256 over traveller_id and all "
            "branch-invariant exogenous draws. Same-duration runs must match "
            "across capacities; every longer run filtered to arrival<Tshort "
            "must exactly match the corresponding shorter run."
        ),
        "errors": errors[:100],
        "error_count": len(errors),
        "paired_analysis_gate": (
            "Duration increments are emitted only after both exact CRN gates "
            "pass."
        ),
    }


def _replication_index(
    rows: Sequence[Mapping[str, object]],
    *,
    capacities: Sequence[Capacity],
    cutoffs: Sequence[int],
    replication_ids: Sequence[int],
) -> dict[RunKey, Mapping[str, object]]:
    expected = {
        (capacity, cutoff, replication_id)
        for capacity in capacities
        for cutoff in cutoffs
        for replication_id in replication_ids
    }
    index: dict[RunKey, Mapping[str, object]] = {}
    for row in rows:
        key = (
            (
                _integer(row["security_capacity"], "security_capacity"),
                _integer(row["immigration_capacity"], "immigration_capacity"),
            ),
            _integer(row["arrival_cutoff_seconds"], "arrival_cutoff_seconds"),
            _integer(row["replication_id"], "replication_id"),
        )
        if key in index:
            raise ValueError(f"duplicate replication row: {key}")
        index[key] = row
    missing = expected - set(index)
    unexpected = set(index) - expected
    if missing or unexpected:
        raise ValueError(
            f"replication grid mismatch: missing={len(missing)}, "
            f"unexpected={len(unexpected)}"
        )
    return index


def build_peak_duration_analysis(
    replication_rows: Sequence[Mapping[str, object]],
    *,
    capacities: Sequence[Capacity] = CAPACITY_CELLS,
    cutoffs: Sequence[int] = CUTOFF_SECONDS,
    replication_ids: Sequence[int] = REPLICATION_IDS,
    study_id: str,
    input_sample_id: str = EXPECTED_TARGET_INPUT_SAMPLE_ID,
    arrival_rate_per_second: float,
    security_service_seconds: float,
    immigration_service_seconds: float,
    ci_level: float = DEFAULT_CI_LEVEL,
    crn_alignment_status: str = "PASS",
) -> dict[str, object]:
    """Build replication-unit estimates, duration increments, and curves."""

    if crn_alignment_status != "PASS":
        raise ValueError("paired duration analysis requires CRN PASS")
    index = _replication_index(
        replication_rows,
        capacities=capacities,
        cutoffs=cutoffs,
        replication_ids=replication_ids,
    )
    estimates: list[dict[str, object]] = []
    increments: list[dict[str, object]] = []
    growth: list[dict[str, object]] = []
    estimate_lookup: dict[tuple[Capacity, int, str], dict[str, object]] = {}

    for capacity in capacities:
        rho = _rho_metadata(
            *capacity,
            arrival_rate_per_second=arrival_rate_per_second,
            security_service_seconds=security_service_seconds,
            immigration_service_seconds=immigration_service_seconds,
        )
        for cutoff in cutoffs:
            scenario_id = duration_scenario_id(*capacity, cutoff)
            cell_rows = [
                index[(capacity, cutoff, replication_id)]
                for replication_id in replication_ids
            ]
            for metric in ANALYSIS_METRICS:
                values = [
                    _float(
                        row[metric],
                        f"{capacity}/T={cutoff}/{metric}",
                    )
                    for row in cell_rows
                ]
                summary = one_sample_summary(values, ci_level=ci_level)
                estimate = {
                    "schema_version": SCHEMA_VERSION,
                    "study_id": study_id,
                    "scenario_id": scenario_id,
                    "input_sample_id": input_sample_id,
                    "security_capacity": capacity[0],
                    "immigration_capacity": capacity[1],
                    "arrival_cutoff_seconds": cutoff,
                    "metric": metric,
                    "estimand": "MEAN_OF_REPLICATION_LEVEL_METRIC",
                    "n_replications": summary["n"],
                    "mean": summary["mean"],
                    "standard_deviation": summary["standard_deviation"],
                    "standard_error": summary["standard_error"],
                    "degrees_of_freedom": summary["degrees_of_freedom"],
                    "ci_level": ci_level,
                    "ci_low": summary["ci_low"],
                    "ci_high": summary["ci_high"],
                    **rho,
                    "analysis_role": (
                        "EXPLORATORY_FINITE_HORIZON_NOT_STEADY_STATE"
                    ),
                }
                estimates.append(estimate)
                estimate_lookup[(capacity, cutoff, metric)] = estimate

            slopes = [
                _float(
                    row[
                        "arrival_window_queue_growth_slope_travellers_per_second"
                    ],
                    f"{capacity}/T={cutoff}/growth_slope",
                )
                for row in cell_rows
            ]
            slope_summary = one_sample_summary(slopes, ci_level=ci_level)
            deltas = [
                _float(row["queue_mean_window_90_100"], "last window")
                - _float(row["queue_mean_window_50_60"], "first window")
                for row in cell_rows
            ]
            delta_summary = one_sample_summary(deltas, ci_level=ci_level)
            if float(slope_summary["ci_low"]) > 0:
                classification = (
                    "POSITIVE_FINITE_HORIZON_QUEUE_GROWTH"
                )
            elif float(slope_summary["ci_high"]) < 0:
                classification = (
                    "NEGATIVE_FINITE_HORIZON_QUEUE_GROWTH"
                )
            else:
                classification = "NO_CLEAR_GROWTH_DIRECTION"
            growth.append(
                {
                    "schema_version": SCHEMA_VERSION,
                    "study_id": study_id,
                    "scenario_id": scenario_id,
                    "security_capacity": capacity[0],
                    "immigration_capacity": capacity[1],
                    "arrival_cutoff_seconds": cutoff,
                    "n_replications": slope_summary["n"],
                    "mean_growth_slope_travellers_per_second": (
                        slope_summary["mean"]
                    ),
                    "standard_deviation": slope_summary[
                        "standard_deviation"
                    ],
                    "standard_error": slope_summary["standard_error"],
                    "degrees_of_freedom": slope_summary[
                        "degrees_of_freedom"
                    ],
                    "ci_level": ci_level,
                    "ci_low": slope_summary["ci_low"],
                    "ci_high": slope_summary["ci_high"],
                    "mean_last_minus_first_window_queue": delta_summary[
                        "mean"
                    ],
                    "last_minus_first_ci_low": delta_summary["ci_low"],
                    "last_minus_first_ci_high": delta_summary["ci_high"],
                    "growth_classification": classification,
                    **rho,
                }
            )

        ordered_cutoffs = tuple(sorted(int(value) for value in cutoffs))
        for short, long in zip(ordered_cutoffs, ordered_cutoffs[1:]):
            for metric in INCREMENT_METRICS:
                differences = [
                    _float(
                        index[(capacity, long, replication_id)][metric],
                        f"{capacity}/T={long}/{metric}",
                    )
                    - _float(
                        index[(capacity, short, replication_id)][metric],
                        f"{capacity}/T={short}/{metric}",
                    )
                    for replication_id in replication_ids
                ]
                summary = one_sample_summary(
                    differences,
                    ci_level=ci_level,
                )
                increments.append(
                    {
                        "schema_version": SCHEMA_VERSION,
                        "study_id": study_id,
                        "security_capacity": capacity[0],
                        "immigration_capacity": capacity[1],
                        "shorter_cutoff_seconds": short,
                        "longer_cutoff_seconds": long,
                        "shorter_scenario_id": duration_scenario_id(
                            *capacity, short
                        ),
                        "longer_scenario_id": duration_scenario_id(
                            *capacity, long
                        ),
                        "metric": metric,
                        "contrast": "LONGER_MINUS_SHORTER",
                        "n_pairs": summary["n"],
                        "mean_increment": summary["mean"],
                        "standard_deviation": summary[
                            "standard_deviation"
                        ],
                        "standard_error": summary["standard_error"],
                        "degrees_of_freedom": summary[
                            "degrees_of_freedom"
                        ],
                        "ci_level": ci_level,
                        "ci_low": summary["ci_low"],
                        "ci_high": summary["ci_high"],
                        "crn_alignment_status": crn_alignment_status,
                        "analysis_role": (
                            "EXPLORATORY_PAIRED_FINITE_HORIZON_INCREMENT"
                        ),
                    }
                )

    curves = {
        "schema_version": SCHEMA_VERSION,
        "study_id": study_id,
        "status": "COMPLETE",
        "input_sample_id": input_sample_id,
        "analysis_role": (
            "EXPLORATORY_FINITE_HORIZON_DURATION_CURVES"
        ),
        "simulated_duration_seconds": list(cutoffs),
        "line_policy": (
            "Only listed duration points are simulated evidence; connecting "
            "lines are visual guides and do not represent intermediate runs."
        ),
        "steady_state_policy": (
            "No steady-state KPI is reported. For rho>=1, interpretation is "
            "restricted to finite-horizon accumulation and recovery."
        ),
        "series": [
            {
                "security_capacity": capacity[0],
                "immigration_capacity": capacity[1],
                **_rho_metadata(
                    *capacity,
                    arrival_rate_per_second=arrival_rate_per_second,
                    security_service_seconds=security_service_seconds,
                    immigration_service_seconds=immigration_service_seconds,
                ),
                "metrics": {
                    metric: [
                        {
                            "arrival_cutoff_seconds": cutoff,
                            "mean": estimate_lookup[
                                (capacity, cutoff, metric)
                            ]["mean"],
                            "ci_low": estimate_lookup[
                                (capacity, cutoff, metric)
                            ]["ci_low"],
                            "ci_high": estimate_lookup[
                                (capacity, cutoff, metric)
                            ]["ci_high"],
                            "n_replications": estimate_lookup[
                                (capacity, cutoff, metric)
                            ]["n_replications"],
                        }
                        for cutoff in cutoffs
                    ]
                    for metric in INCREMENT_METRICS
                },
            }
            for capacity in capacities
        ],
    }
    return {
        "estimates": estimates,
        "duration_increments": increments,
        "growth_diagnostics": growth,
        "curves_payload": curves,
    }


def _cross_batch_report(
    current_rows: Sequence[Mapping[str, object]],
    current_prefixes: Mapping[PrefixKey, tuple[int, str]],
    *,
    prior_results_root: Path,
    prior_scenarios_path: Path,
    schemas: Mapping[str, Sequence[Mapping[str, str]]],
    seed_rows: Mapping[int, Mapping[str, str]],
    study_id: str,
    arrival_rate_per_second: float,
    security_service_seconds: float,
    immigration_service_seconds: float,
    numeric_tolerance: float,
) -> dict[str, object]:
    current = {
        (
            (
                int(row["security_capacity"]),
                int(row["immigration_capacity"]),
            ),
            int(row["replication_id"]),
        ): row
        for row in current_rows
        if int(row["arrival_cutoff_seconds"]) == 300
    }
    if not prior_results_root.is_dir():
        return {
            "schema_version": SCHEMA_VERSION,
            "validation": CROSS_BATCH_ID,
            "study_id": study_id,
            "status": "NOT_AVAILABLE",
            "compared_run_count": 0,
            "expected_run_count_if_available": len(CAPACITY_CELLS)
            * len(REPLICATION_IDS),
            "errors": [
                f"prior response-surface root absent: {prior_results_root}"
            ],
            "analysis_inclusion_rule": (
                "Prior runs are validation-only and contribute no estimates."
            ),
        }

    prior_scenarios = {
        row["scenario_id"]: row
        for row in load_response_surface_scenario_rows(
            prior_scenarios_path
        )
    }
    errors: list[str] = []
    compared = 0
    max_difference = 0.0
    model_version_pairs: set[tuple[str, str]] = set()
    for capacity in CAPACITY_CELLS:
        prior_scenario_id = response_scenario_id(*capacity)
        prior_scenario = prior_scenarios.get(prior_scenario_id)
        if prior_scenario is None:
            errors.append(f"prior scenario missing: {prior_scenario_id}")
            continue
        for replication_id in REPLICATION_IDS:
            run_dir = _run_directory(
                prior_results_root,
                prior_scenario_id,
                PRIOR_INPUT_SAMPLE_ID,
                replication_id,
            )
            try:
                paths = {
                    table: run_dir / filename
                    for table, filename in RESULT_FILES.items()
                }
                manifest = _require_one(
                    _load_table(
                        paths["run_manifest"],
                        "run_manifest",
                        schemas["run_manifest"],
                    ),
                    paths["run_manifest"],
                )
                kpi = _require_one(
                    _load_table(
                        paths["replication_kpis"],
                        "replication_kpis",
                        schemas["replication_kpis"],
                    ),
                    paths["replication_kpis"],
                )
                entities = _load_table(
                    paths["entity_log"],
                    "entity_log",
                    schemas["entity_log"],
                )
                if manifest["config_sha256"] != scenario_config_sha256(
                    prior_scenario
                ):
                    raise ValueError("prior config hash differs")
                if manifest["scenario_id"] != prior_scenario_id:
                    raise ValueError("prior scenario identity differs")
                if manifest["input_sample_id"] != PRIOR_INPUT_SAMPLE_ID:
                    raise ValueError("prior input identity differs")
                for field in ("master_seed", *STREAM_SEED_FIELDS):
                    if manifest[field] != seed_rows[replication_id][field]:
                        raise ValueError(f"prior {field} differs")
                prior_derived = derive_duration_metrics(
                    entities,
                    cutoff_seconds=300.0,
                )
                prior_signature = _signature_for_rows(
                    entities,
                    label=str(paths["entity_log"]),
                )
                current_signature = current_prefixes[
                    (capacity, 300, replication_id, 300)
                ]
                if prior_signature != current_signature:
                    raise ValueError("T=300 exogenous signature differs")
                current_row = current[(capacity, replication_id)]
                model_version_pairs.add(
                    (
                        str(manifest["model_version"]),
                        str(current_row["model_version"]),
                    )
                )
                for metric in CROSS_BATCH_METRICS:
                    difference = abs(
                        _float(current_row[metric], f"current {metric}")
                        - _float(prior_derived[metric], f"prior {metric}")
                    )
                    max_difference = max(max_difference, difference)
                    if difference > numeric_tolerance:
                        raise ValueError(
                            f"{metric} differs by {difference:.12g}"
                        )
                compared += 1
            except (
                FileNotFoundError,
                KeyError,
                TypeError,
                ValueError,
            ) as error:
                errors.append(
                    f"{capacity} replication {replication_id}: {error}"
                )
    status = (
        "PASS"
        if not errors
        and compared == len(CAPACITY_CELLS) * len(REPLICATION_IDS)
        else "FAIL"
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "validation": CROSS_BATCH_ID,
        "study_id": study_id,
        "status": status,
        "compared_run_count": compared,
        "expected_run_count_if_available": len(CAPACITY_CELLS)
        * len(REPLICATION_IDS),
        "numeric_tolerance": numeric_tolerance,
        "maximum_absolute_metric_difference": max_difference,
        "metrics": list(CROSS_BATCH_METRICS),
        "model_version_pairs": [
            {"prior": prior, "current": current}
            for prior, current in sorted(model_version_pairs)
        ],
        "errors": errors[:100],
        "error_count": len(errors),
        "analysis_inclusion_rule": (
            "Prior T=300 response-surface runs are validation-only and "
            "contribute no rows to duration estimates."
        ),
        "input_identity_mapping": (
            "Prior LOCAL_WINDOW_HPP_BASE is compared with the explicitly "
            "separate LOCAL_WINDOW_HPP_BASE_STATIONARY_EXTENSION T=300 cell."
        ),
    }


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
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def package_peak_duration_sensitivity_analysis(
    results_root: Path = DEFAULT_RESULTS_ROOT,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    *,
    design_path: Path = DEFAULT_DESIGN,
    scenarios_path: Path = DEFAULT_SCENARIOS,
    seed_manifest_path: Path = DEFAULT_SEED_MANIFEST,
    schema_registry_path: Path = DEFAULT_SCHEMA_REGISTRY,
    prior_results_root: Path = DEFAULT_PRIOR_RESULTS_ROOT,
    prior_scenarios_path: Path = DEFAULT_PRIOR_SCENARIOS,
    ci_level: float = DEFAULT_CI_LEVEL,
    numeric_tolerance: float = DEFAULT_NUMERIC_TOLERANCE,
) -> dict[str, object]:
    """Validate 1000 raw runs and write the compact duration evidence set."""

    results_root = results_root.resolve()
    output_dir = output_dir.resolve()
    design_path = design_path.resolve()
    scenarios_path = scenarios_path.resolve()
    seed_manifest_path = seed_manifest_path.resolve()
    schema_registry_path = schema_registry_path.resolve()
    prior_results_root = prior_results_root.resolve()
    prior_scenarios_path = prior_scenarios_path.resolve()
    if not 0 < ci_level < 1:
        raise ValueError("ci_level must be between 0 and 1")
    if numeric_tolerance < 0 or not math.isfinite(numeric_tolerance):
        raise ValueError("numeric_tolerance must be finite and non-negative")

    design_validation = validate_peak_duration_design(
        design_path,
        scenarios_path,
        seed_manifest_path,
    )
    if design_validation["status"] != "PASS":
        raise ValueError(
            "frozen peak-duration design validation failed: "
            + "; ".join(map(str, design_validation["errors"]))
        )
    design = load_design(design_path)
    if design["execution_status"] != "NOT_EXECUTED":
        raise ValueError(
            "design execution_status must remain NOT_EXECUTED; raw evidence "
            "status is recorded only in the analysis package"
        )
    study_id = str(design["study_id"])
    fixed = design["fixed_inputs"]
    arrival_rate = _float(
        fixed["arrival_rate_per_second"],
        "arrival_rate_per_second",
    )
    security_service = _float(
        fixed["security_service_p1_seconds"],
        "security_service_p1_seconds",
    )
    immigration_service = _float(
        fixed["immigration_service_p1_seconds"],
        "immigration_service_p1_seconds",
    )

    expected_directories = _expected_run_directories(results_root)
    if len(expected_directories) != EXPECTED_RUN_COUNT:
        raise ValueError("internal expected coverage is not exactly 1000 runs")
    _validate_exact_coverage(results_root, expected_directories)

    schemas = load_result_schemas(schema_registry_path)
    if set(RESULT_FILES) - set(schemas):
        raise ValueError("result schema registry is missing a required table")
    scenarios = {
        row["scenario_id"]: row
        for row in load_peak_duration_scenario_rows(scenarios_path)
    }
    seeds = {
        int(row["replication_id"]): row
        for row in load_peak_duration_seed_rows(seed_manifest_path)
    }
    if set(seeds) != set(REPLICATION_IDS):
        raise ValueError("seed manifest does not contain replications 1..50")

    replication_rows: list[dict[str, object]] = []
    prefix_signatures: dict[PrefixKey, tuple[int, str]] = {}
    raw_artifacts: list[dict[str, object]] = []
    entity_row_count = 0
    model_versions: set[str] = set()
    for capacity in CAPACITY_CELLS:
        for cutoff in CUTOFF_SECONDS:
            scenario_id = duration_scenario_id(*capacity, cutoff)
            scenario = scenarios.get(scenario_id)
            if scenario is None:
                raise ValueError(f"frozen scenario row missing: {scenario_id}")
            for replication_id in REPLICATION_IDS:
                run_dir = _run_directory(
                    results_root,
                    scenario_id,
                    EXPECTED_TARGET_INPUT_SAMPLE_ID,
                    replication_id,
                )
                row, run_prefixes, artifacts = _validate_one_run(
                    run_dir,
                    capacity=capacity,
                    cutoff_seconds=cutoff,
                    replication_id=replication_id,
                    scenario_row=scenario,
                    seed_row=seeds[replication_id],
                    schemas=schemas,
                    study_id=study_id,
                    arrival_rate_per_second=arrival_rate,
                    security_service_seconds=security_service,
                    immigration_service_seconds=immigration_service,
                )
                replication_rows.append(row)
                model_versions.add(str(row["model_version"]))
                entity_row_count += int(row["arrivals"])
                raw_artifacts.extend(artifacts)
                for prefix_cutoff, signature in run_prefixes.items():
                    prefix_signatures[
                        (
                            capacity,
                            cutoff,
                            replication_id,
                            prefix_cutoff,
                        )
                    ] = signature
    if len(replication_rows) != EXPECTED_RUN_COUNT:
        raise ValueError("validated replication row count is not exactly 1000")
    if len(model_versions) != 1:
        raise ValueError(
            "all 1000 runs must use one exact nonblank model_version"
        )

    crn = build_crn_alignment_report(
        prefix_signatures,
        capacities=CAPACITY_CELLS,
        cutoffs=CUTOFF_SECONDS,
        replication_ids=REPLICATION_IDS,
        study_id=study_id,
    )
    if crn["status"] != "PASS":
        raise ValueError(
            "duration CRN/prefix alignment failed: "
            + "; ".join(map(str, crn["errors"][:5]))
        )

    cross_batch = _cross_batch_report(
        replication_rows,
        prefix_signatures,
        prior_results_root=prior_results_root,
        prior_scenarios_path=prior_scenarios_path,
        schemas=schemas,
        seed_rows=seeds,
        study_id=study_id,
        arrival_rate_per_second=arrival_rate,
        security_service_seconds=security_service,
        immigration_service_seconds=immigration_service,
        numeric_tolerance=numeric_tolerance,
    )
    if cross_batch["status"] == "FAIL":
        raise ValueError(
            "T=300 cross-batch reproducibility failed: "
            + "; ".join(map(str, cross_batch["errors"][:5]))
        )

    analysis = build_peak_duration_analysis(
        replication_rows,
        capacities=CAPACITY_CELLS,
        cutoffs=CUTOFF_SECONDS,
        replication_ids=REPLICATION_IDS,
        study_id=study_id,
        arrival_rate_per_second=arrival_rate,
        security_service_seconds=security_service,
        immigration_service_seconds=immigration_service,
        ci_level=ci_level,
        crn_alignment_status=str(crn["status"]),
    )
    validation = {
        "schema_version": SCHEMA_VERSION,
        "validation": VALIDATION_ID,
        "study_id": study_id,
        "status": "PASS",
        "coverage_status": "PASS",
        "canonical_schema_status": "PASS",
        "manifest_lineage_status": "PASS",
        "frozen_config_hash_status": "PASS",
        "single_model_version_status": "PASS",
        "seed_status": "PASS",
        "run_status": "PASS",
        "full_drain_status": "PASS",
        "guard_nonbinding_status": "PASS",
        "zero_drop_status": "PASS",
        "entity_reconstruction_status": "PASS",
        "crn_alignment_status": crn["status"],
        "cross_batch_reproducibility_status": cross_batch["status"],
        "capacity_cell_count": len(CAPACITY_CELLS),
        "duration_level_count": len(CUTOFF_SECONDS),
        "replications_per_cell": len(REPLICATION_IDS),
        "expected_run_count": EXPECTED_RUN_COUNT,
        "actual_run_count": len(replication_rows),
        "model_version": next(iter(model_versions)),
        "entity_row_count": entity_row_count,
        "raw_file_count": len(raw_artifacts),
        "raw_tree_sha256": _tree_digest(raw_artifacts),
        "artifact_hashes": {
            "design_sha256": _sha256(design_path),
            "scenarios_sha256": _sha256(scenarios_path),
            "seed_manifest_sha256": _sha256(seed_manifest_path),
            "schema_registry_sha256": _sha256(schema_registry_path),
        },
        "input_sample_id": EXPECTED_TARGET_INPUT_SAMPLE_ID,
        "errors": [],
        "claim_boundary": design["claim_ceiling"],
        "steady_state_policy": (
            "No steady-state KPI is emitted; rho>=1 cells are finite-horizon "
            "accumulation/recovery evidence only."
        ),
    }

    outputs: tuple[
        tuple[str, Sequence[Mapping[str, object]], Sequence[str]], ...
    ] = (
        (
            "peak_duration_by_replication.csv",
            replication_rows,
            REPLICATION_FIELDS,
        ),
        (
            "cell_estimates.csv",
            analysis["estimates"],
            ESTIMATE_FIELDS,
        ),
        (
            "duration_increments.csv",
            analysis["duration_increments"],
            INCREMENT_FIELDS,
        ),
        (
            "growth_diagnostics.csv",
            analysis["growth_diagnostics"],
            GROWTH_DIAGNOSTIC_FIELDS,
        ),
        (
            "raw_artifact_manifest.csv",
            raw_artifacts,
            RAW_ARTIFACT_FIELDS,
        ),
    )
    for filename, rows, fields in outputs:
        _write_csv(output_dir / filename, rows, fields)
    _write_json(output_dir / "validation.json", validation)
    _write_json(output_dir / "crn_alignment.json", crn)
    _write_json(
        output_dir / "cross_batch_reproducibility.json",
        cross_batch,
    )
    _write_json(
        output_dir / "curves_payload.json",
        analysis["curves_payload"],
    )

    output_paths = [
        output_dir / filename for filename, _, _ in outputs
    ] + [
        output_dir / "validation.json",
        output_dir / "crn_alignment.json",
        output_dir / "cross_batch_reproducibility.json",
        output_dir / "curves_payload.json",
    ]
    manifest: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "analysis": ANALYSIS_ID,
        "study_id": study_id,
        "status": "PASS",
        "analysis_role": design["analysis_role"],
        "claim_boundary": design["claim_ceiling"],
        "input_sample_id": EXPECTED_TARGET_INPUT_SAMPLE_ID,
        "coverage": {
            "capacity_cell_count": len(CAPACITY_CELLS),
            "duration_level_count": len(CUTOFF_SECONDS),
            "study_cell_count": len(CAPACITY_CELLS)
            * len(CUTOFF_SECONDS),
            "replications_per_cell": len(REPLICATION_IDS),
            "run_count": len(replication_rows),
        },
        "paired_analysis_gate": {
            "same_duration_cross_capacity_status": (
                "PASS"
                if crn[
                    "same_duration_cross_capacity_exogenous_crn_pass"
                ]
                else "FAIL"
            ),
            "cross_duration_nested_prefix_status": (
                "PASS"
                if crn["cross_duration_nested_arrival_prefix_pass"]
                else "FAIL"
            ),
            "comparison_method": "PAIRED_STUDENT_T",
        },
        "cross_batch_reproducibility_status": cross_batch["status"],
        "queue_reconstruction": {
            "time_weighted_mean_and_peak_window": "[0,T)",
            "cutoff_state": "queue and backlog reconstructed from entity ledger",
            "late_arrival_definition": "arrival_seconds in [0.8*T,T)",
            "growth_windows": [
                "[0.5T,0.6T)",
                "[0.6T,0.7T)",
                "[0.7T,0.8T)",
                "[0.8T,0.9T)",
                "[0.9T,T)",
            ],
            "growth_estimator": (
                "replication-level OLS slope of five window queue means "
                "against window midpoint seconds"
            ),
        },
        "steady_state_policy": (
            "No steady-state KPI. rho>=1 cells are reported only through "
            "finite-horizon queue, backlog, late-wait, and clear-time outputs."
        ),
        "source": {
            "raw_results_root": portable_path(results_root),
            "entity_row_count": entity_row_count,
            "entity_logs_copied_to_analysis_package": False,
            "raw_file_count": len(raw_artifacts),
            "raw_tree_sha256": validation["raw_tree_sha256"],
            "artifact_hashes": validation["artifact_hashes"],
        },
        "outputs": {
            path.name: {
                "path": portable_path(path),
                "sha256": _sha256(path),
                "row_count": (
                    next(
                        len(rows)
                        for filename, rows, _ in outputs
                        if filename == path.name
                    )
                    if any(
                        filename == path.name
                        for filename, _, _ in outputs
                    )
                    else 1
                ),
            }
            for path in output_paths
        },
    }
    _write_json(output_dir / "analysis_manifest.json", manifest)
    return manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-root", type=Path, default=DEFAULT_RESULTS_ROOT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--design", type=Path, default=DEFAULT_DESIGN)
    parser.add_argument("--scenarios", type=Path, default=DEFAULT_SCENARIOS)
    parser.add_argument(
        "--seed-manifest",
        type=Path,
        default=DEFAULT_SEED_MANIFEST,
    )
    parser.add_argument(
        "--schema-registry",
        type=Path,
        default=DEFAULT_SCHEMA_REGISTRY,
    )
    parser.add_argument(
        "--prior-results-root",
        type=Path,
        default=DEFAULT_PRIOR_RESULTS_ROOT,
    )
    parser.add_argument(
        "--prior-scenarios",
        type=Path,
        default=DEFAULT_PRIOR_SCENARIOS,
    )
    parser.add_argument("--ci-level", type=float, default=DEFAULT_CI_LEVEL)
    parser.add_argument(
        "--numeric-tolerance",
        type=float,
        default=DEFAULT_NUMERIC_TOLERANCE,
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        manifest = package_peak_duration_sensitivity_analysis(
            args.results_root,
            args.output_dir,
            design_path=args.design,
            scenarios_path=args.scenarios,
            seed_manifest_path=args.seed_manifest,
            schema_registry_path=args.schema_registry,
            prior_results_root=args.prior_results_root,
            prior_scenarios_path=args.prior_scenarios,
            ci_level=args.ci_level,
            numeric_tolerance=args.numeric_tolerance,
        )
    except (
        FileNotFoundError,
        KeyError,
        TypeError,
        ValueError,
    ) as error:
        failure = {
            "schema_version": SCHEMA_VERSION,
            "validation": VALIDATION_ID,
            "status": "FAIL",
            "expected_run_count": EXPECTED_RUN_COUNT,
            "actual_run_count": 0,
            "input_sample_id": EXPECTED_TARGET_INPUT_SAMPLE_ID,
            "errors": [str(error)],
            "claim_rule": (
                "No peak-duration estimate is released when validation fails."
            ),
        }
        _write_json(args.output_dir.resolve() / "validation.json", failure)
        print(json.dumps(failure, indent=2, sort_keys=True))
        return 1
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
