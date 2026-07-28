"""Validate and analyse the exploratory Base-demand capacity response surface.

The response-surface experiment is intentionally self-contained: all 54
Security-by-Immigration capacity cells are rerun with the same 50 registered
Base-demand seed tuples.  This module consumes the hierarchical AnyLogic
outputs directly.  It does not pool traveller records across runs and it does
not mix earlier batches into the estimates.

The validation layer is fail-closed.  It requires exact 54-by-50 coverage,
canonical CSV schemas, frozen scenario hashes, registered stream seeds,
complete/full-drain runs, conservation, and identical branch-invariant
traveller draws across every capacity cell within a replication.  Entity logs
are read one run at a time; only compact replication-level metrics and
cryptographic draw signatures are retained.

Earlier Base-demand batches are optional validation evidence.  When present,
the five frozen cross-batch cells are compared against the new experiment but
are never included in response-surface estimates.
"""

from __future__ import annotations

import argparse
import csv
import heapq
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from src.analysis.analyse_capacity_availability import (
    QUEUE_ANALYSIS_FIELDS,
    reconstruct_queue_length_metrics,
)
from src.analysis.analyse_operational_replications import (
    one_sample_summary,
    portable_path,
)
from src.analysis.capacity_response_surface_design import (
    DEFAULT_DESIGN,
    DEFAULT_SCENARIOS,
    DEFAULT_SEED_MANIFEST,
    cross_batch_validation_cells,
    full_grid,
    load_design,
    load_response_surface_scenario_rows,
    load_response_surface_seed_rows,
    response_scenario_id,
    validate_response_surface_design,
)
from src.analysis.validate_crn_alignment import DRAW_FIELDS, STREAM_SEED_FIELDS
from src.analysis.validate_operational_contract import scenario_config_sha256
from src.analysis.validate_operational_results import (
    DEFAULT_SCHEMA_REGISTRY,
    RESULT_FILES,
    load_result_schemas,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RESULTS_ROOT = (
    PROJECT_ROOT / "results" / "raw" / "capacity_response_surface"
)
DEFAULT_OUTPUT_DIR = (
    PROJECT_ROOT / "results" / "analysis" / "capacity_response_surface"
)
DEFAULT_PRIOR_ROOTS = {
    "confirmatory_capacity": (
        PROJECT_ROOT / "results" / "raw" / "confirmatory_capacity"
    ),
    "capacity_availability": (
        PROJECT_ROOT / "results" / "raw" / "capacity_availability"
    ),
}

ANALYSIS_ID = "TASK3_CAPACITY_RESPONSE_SURFACE_ANALYSIS_V1"
VALIDATION_ID = "TASK3_CAPACITY_RESPONSE_SURFACE_INPUT_VALIDATION_V1"
CRN_VALIDATION_ID = "CAPACITY_RESPONSE_SURFACE_CRN_ALIGNMENT_V1"
REPRODUCIBILITY_ID = "CAPACITY_RESPONSE_SURFACE_CROSS_BATCH_V1"
THRESHOLD_DIAGNOSTIC_ID = (
    "CAPACITY_RESPONSE_SURFACE_REGISTERED_EXCEEDANCE_DIAGNOSTIC_V1"
)
SCHEMA_VERSION = "1.0"
DEFAULT_CI_LEVEL = 0.95
DEFAULT_NUMERIC_TOLERANCE = 1e-9

INPUT_SAMPLE_ID = "LOCAL_WINDOW_HPP_BASE"
REPLICATION_IDS = tuple(range(1, 51))
REFERENCE_CELL = (36, 21)

ANALYSIS_METRICS = (
    "total_queue_wait_p95_seconds",
    "total_queue_wait_mean_seconds",
    "peak_total_waiting_queue",
    "time_weighted_mean_total_waiting_queue",
    "cutoff_backlog",
    "cohort_clear_time_after_cutoff_seconds",
    "security_wait_p95_seconds",
    "immigration_wait_p95_seconds",
)
REPRODUCIBILITY_METRICS = ANALYSIS_METRICS
THRESHOLD_EXCEEDANCE_FIELDS = (
    (600, "total_queue_wait_exceed_600_rate"),
    (900, "total_queue_wait_exceed_900_rate"),
    (1200, "total_queue_wait_exceed_1200_rate"),
)

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

REPLICATION_FIELDS = (
    "schema_version",
    "study_id",
    "scenario_id",
    "input_sample_id",
    "replication_id",
    "security_capacity",
    "immigration_capacity",
    "config_id",
    "config_sha256",
    "model_version",
    "master_seed",
    "arrival_seed",
    "service_seed",
    "routing_seed",
    "tie_seed",
    "arrivals",
    "completed_after_drain",
    "rejected_or_dropped_count",
    "total_queue_wait_p95_seconds",
    "total_queue_wait_mean_seconds",
    "total_queue_wait_exceed_600_rate",
    "total_queue_wait_exceed_900_rate",
    "total_queue_wait_exceed_1200_rate",
    "security_wait_p95_seconds",
    "immigration_wait_p95_seconds",
    "cutoff_backlog",
    "cohort_clear_time_after_cutoff_seconds",
    "security_utilization",
    "immigration_utilization",
    *QUEUE_ANALYSIS_FIELDS,
)
ESTIMATE_FIELDS = (
    "schema_version",
    "study_id",
    "security_capacity",
    "immigration_capacity",
    "scenario_id",
    "metric",
    "estimand",
    "n_replications",
    "mean",
    "standard_deviation",
    "standard_error",
    "ci_level",
    "ci_low",
    "ci_high",
    "analysis_role",
)
ADJACENT_FIELDS = (
    "schema_version",
    "study_id",
    "axis",
    "fixed_security_capacity",
    "fixed_immigration_capacity",
    "higher_capacity",
    "lower_capacity",
    "higher_scenario_id",
    "lower_scenario_id",
    "metric",
    "contrast",
    "n_pairs",
    "mean_penalty",
    "standard_deviation",
    "standard_error",
    "ci_level",
    "ci_low",
    "ci_high",
    "crn_alignment_status",
    "analysis_role",
)
SECOND_DIFFERENCE_FIELDS = (
    "schema_version",
    "study_id",
    "axis",
    "fixed_security_capacity",
    "fixed_immigration_capacity",
    "higher_capacity",
    "middle_capacity",
    "lower_capacity",
    "metric",
    "contrast",
    "n_pairs",
    "mean_second_difference",
    "standard_deviation",
    "standard_error",
    "ci_level",
    "ci_low",
    "ci_high",
    "crn_alignment_status",
    "analysis_role",
)
INTERACTION_FIELDS = (
    "schema_version",
    "study_id",
    "security_higher_capacity",
    "security_lower_capacity",
    "immigration_higher_capacity",
    "immigration_lower_capacity",
    "metric",
    "contrast",
    "n_pairs",
    "mean_interaction",
    "standard_deviation",
    "standard_error",
    "ci_level",
    "ci_low",
    "ci_high",
    "crn_alignment_status",
    "analysis_role",
)
VIEW_FIELDS = (
    "schema_version",
    "study_id",
    "view",
    "path_index",
    "security_capacity",
    "immigration_capacity",
    "security_reduction",
    "immigration_reduction",
    "security_offered_load_ratio",
    "immigration_offered_load_ratio",
    "scenario_id",
    "metric",
    "n_replications",
    "mean",
    "standard_error",
    "ci_level",
    "ci_low",
    "ci_high",
)
BOTTLENECK_FIELDS = (
    "schema_version",
    "study_id",
    "security_capacity",
    "immigration_capacity",
    "contrast",
    "n_pairs",
    "security_minus_immigration_p95_mean_seconds",
    "standard_error",
    "ci_level",
    "ci_low",
    "ci_high",
    "bottleneck_classification",
)
IDEAL_COMPARATOR_FIELDS = (
    "schema_version",
    "study_id",
    "comparator_id",
    "security_capacity",
    "immigration_capacity",
    "arrival_rate_per_second",
    "arrival_spacing_seconds",
    "arrival_cutoff_seconds",
    "deterministic_arrivals",
    "security_service_seconds",
    "immigration_service_seconds",
    "security_throughput_capacity_per_second",
    "immigration_throughput_capacity_per_second",
    "system_bottleneck_throughput_capacity_per_second",
    "security_throughput_headroom_per_second",
    "immigration_throughput_headroom_per_second",
    "security_offered_workload_a",
    "immigration_offered_workload_a",
    "security_rho",
    "immigration_rho",
    "security_capacity_minus_a",
    "immigration_capacity_minus_a",
    "security_beta",
    "immigration_beta",
    "ideal_security_wait_mean_seconds",
    "ideal_security_wait_p95_seconds",
    "ideal_immigration_wait_mean_seconds",
    "ideal_immigration_wait_p95_seconds",
    "ideal_total_queue_wait_mean_seconds",
    "ideal_total_queue_wait_p95_seconds",
    "ideal_peak_security_waiting_queue",
    "ideal_peak_immigration_waiting_queue",
    "ideal_peak_total_waiting_queue",
    "anylogic_total_queue_wait_mean_estimate_seconds",
    "anylogic_total_queue_wait_mean_ci_low_seconds",
    "anylogic_total_queue_wait_mean_ci_high_seconds",
    "anylogic_total_queue_wait_p95_estimate_seconds",
    "anylogic_total_queue_wait_p95_ci_low_seconds",
    "anylogic_total_queue_wait_p95_ci_high_seconds",
    "anylogic_peak_total_waiting_queue_estimate",
    "anylogic_peak_total_waiting_queue_ci_low",
    "anylogic_peak_total_waiting_queue_ci_high",
    "variability_congestion_penalty_mean_wait_seconds",
    "variability_congestion_penalty_mean_wait_ci_low_seconds",
    "variability_congestion_penalty_mean_wait_ci_high_seconds",
    "variability_congestion_penalty_p95_wait_seconds",
    "variability_congestion_penalty_p95_wait_ci_low_seconds",
    "variability_congestion_penalty_p95_wait_ci_high_seconds",
    "variability_congestion_penalty_peak_queue",
    "variability_congestion_penalty_peak_queue_ci_low",
    "variability_congestion_penalty_peak_queue_ci_high",
    "interpretation_role",
)
QUEUEING_OVERLAY_FIELDS = (
    "schema_version",
    "study_id",
    "security_capacity",
    "immigration_capacity",
    "arrival_rate_per_second",
    "security_service_seconds",
    "immigration_service_seconds",
    "security_throughput_capacity_per_second",
    "immigration_throughput_capacity_per_second",
    "system_bottleneck_throughput_capacity_per_second",
    "security_throughput_headroom_per_second",
    "immigration_throughput_headroom_per_second",
    "security_offered_workload_a",
    "immigration_offered_workload_a",
    "security_rho",
    "immigration_rho",
    "security_capacity_minus_a",
    "immigration_capacity_minus_a",
    "security_beta",
    "immigration_beta",
    "security_rho_threshold_crossed",
    "immigration_rho_threshold_crossed",
    "interpretation_role",
)

RunKey = tuple[str, str, int]
Cell = tuple[int, int]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _tree_digest(entries: Sequence[tuple[str, str]]) -> str:
    payload = json.dumps(
        sorted([list(entry) for entry in entries]),
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


def _canonical_numeric(value: str) -> str:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("exogenous draw is not finite")
    return number.hex()


def _load_table(
    path: Path,
    table_name: str,
    schema: Sequence[Mapping[str, str]],
) -> list[dict[str, str]]:
    """Read one run-local table and enforce the canonical schema and types."""

    if not path.is_file():
        raise FileNotFoundError(path)
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        actual = list(reader.fieldnames or ())
        expected = [str(field["field_name"]) for field in schema]
        if actual != expected:
            raise ValueError(
                f"{path}: canonical {table_name} schema mismatch"
            )
        rows: list[dict[str, str]] = []
        for line, raw_row in enumerate(reader, start=2):
            row = {
                name: (raw_row.get(name) or "").strip() for name in expected
            }
            for field in schema:
                name = str(field["field_name"])
                raw = row[name]
                nullable = str(field["nullable"]) == "true"
                if not raw:
                    if not nullable:
                        raise ValueError(
                            f"{path}:{line}:{name}: null is not allowed"
                        )
                    continue
                data_type = str(field["data_type"])
                if data_type == "integer":
                    _integer(raw, f"{path}:{line}:{name}")
                elif data_type == "number":
                    _float(raw, f"{path}:{line}:{name}")
                elif data_type == "boolean":
                    _boolean(raw, f"{path}:{line}:{name}")
                elif data_type != "string":
                    raise ValueError(
                        f"{path}:{line}:{name}: unsupported type {data_type}"
                    )
            rows.append(row)
    return rows


def _require_one(
    rows: Sequence[dict[str, str]], path: Path
) -> dict[str, str]:
    if len(rows) != 1:
        raise ValueError(f"{path}: expected exactly one data row")
    return rows[0]


def _run_directory(
    root: Path,
    scenario_id: str,
    replication_id: int,
    *,
    input_sample_id: str = INPUT_SAMPLE_ID,
) -> Path:
    return (
        root
        / scenario_id
        / input_sample_id
        / f"replication_{replication_id:03d}"
    )


def _expected_run_paths(
    root: Path,
    cells: Sequence[Cell],
    replication_ids: Sequence[int],
) -> dict[Path, tuple[Cell, int]]:
    return {
        _run_directory(
            root,
            response_scenario_id(*cell),
            replication_id,
        ): (cell, replication_id)
        for cell in cells
        for replication_id in replication_ids
    }


def _validate_exact_coverage(
    results_root: Path,
    expected_directories: Mapping[Path, tuple[Cell, int]],
) -> None:
    if not results_root.is_dir():
        raise FileNotFoundError(
            f"response-surface raw results do not exist: {results_root}"
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
            f"response-surface coverage is incomplete: {len(missing)} "
            f"run manifests are missing ({excerpt})"
        )
    if unexpected:
        excerpt = ", ".join(str(path) for path in unexpected[:3])
        raise ValueError(
            f"response-surface coverage has {len(unexpected)} unexpected "
            f"runs ({excerpt})"
        )


def _entity_draw_signature(
    entity_rows: Sequence[Mapping[str, str]],
    *,
    label: str,
) -> tuple[int, str]:
    """Build an order-independent digest of traveller IDs and exogenous draws."""

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
        values = [
            _canonical_numeric(str(row.get(field, "")).strip())
            for field in DRAW_FIELDS
        ]
        signatures.append(
            json.dumps(
                [traveller_id, *values],
                ensure_ascii=True,
                separators=(",", ":"),
            )
        )
    digest = hashlib.sha256(
        ("\n".join(sorted(signatures)) + "\n").encode("utf-8")
    ).hexdigest()
    return len(signatures), digest


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
        raise ValueError(f"{label}: exit occurs after the recorded drain end")

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
        row["additional_check_flag"], f"{label}:additional_check_flag"
    ):
        raise ValueError(f"{label}: additional checks must remain disabled")
    if (
        str(row["additional_check_service_demand_seconds"]).strip()
        or str(row["additional_check_end_seconds"]).strip()
    ):
        raise ValueError(
            f"{label}: disabled additional check fields must remain blank"
        )


def _paired_summary(
    values: Sequence[float],
    *,
    ci_level: float,
) -> dict[str, float | int]:
    if any(not math.isfinite(value) for value in values):
        raise ValueError("paired contrast contains a non-finite value")
    return one_sample_summary(list(values), ci_level=ci_level)


def _nearest_rank_p95(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, math.ceil(0.95 * len(ordered)) - 1)
    return ordered[index]


def deterministic_two_stage_oracle(
    *,
    arrival_rate_per_second: float,
    arrival_cutoff_seconds: float,
    security_capacity: int,
    immigration_capacity: int,
    security_service_seconds: float,
    immigration_service_seconds: float,
) -> dict[str, float | int]:
    """Run the deterministic ideal two-stage pooled-FCFS control.

    Arrivals occur at ``k / lambda`` for positive integers ``k`` while the
    timestamp remains strictly below the cutoff.  Both service stages use
    fixed durations and work-conserving pooled FCFS parallel servers.
    """

    arrival_rate = _float(
        arrival_rate_per_second, "arrival_rate_per_second"
    )
    cutoff = _float(arrival_cutoff_seconds, "arrival_cutoff_seconds")
    security_service = _float(
        security_service_seconds, "security_service_seconds"
    )
    immigration_service = _float(
        immigration_service_seconds, "immigration_service_seconds"
    )
    if arrival_rate <= 0 or cutoff <= 0:
        raise ValueError("arrival rate and cutoff must be positive")
    if security_service <= 0 or immigration_service <= 0:
        raise ValueError("service durations must be positive")
    if security_capacity <= 0 or immigration_capacity <= 0:
        raise ValueError("stage capacities must be positive integers")

    spacing = 1.0 / arrival_rate
    arrivals: list[float] = []
    arrival_index = 1
    while True:
        timestamp = arrival_index * spacing
        if timestamp >= cutoff:
            break
        arrivals.append(timestamp)
        arrival_index += 1

    security_available = [0.0] * security_capacity
    heapq.heapify(security_available)
    records: list[dict[str, float]] = []
    for arrival in arrivals:
        available = heapq.heappop(security_available)
        security_start = max(arrival, available)
        security_end = security_start + security_service
        heapq.heappush(security_available, security_end)
        records.append(
            {
                "arrival_seconds": arrival,
                "security_queue_join_seconds": arrival,
                "security_start_seconds": security_start,
                "security_end_seconds": security_end,
            }
        )

    immigration_available = [0.0] * immigration_capacity
    heapq.heapify(immigration_available)
    for traveller_index in sorted(
        range(len(records)),
        key=lambda index: (
            records[index]["security_end_seconds"],
            index,
        ),
    ):
        record = records[traveller_index]
        queue_join = record["security_end_seconds"]
        available = heapq.heappop(immigration_available)
        immigration_start = max(queue_join, available)
        immigration_end = immigration_start + immigration_service
        heapq.heappush(immigration_available, immigration_end)
        record.update(
            {
                "immigration_queue_join_seconds": queue_join,
                "immigration_start_seconds": immigration_start,
                "immigration_primary_end_seconds": immigration_end,
                "exit_seconds": immigration_end,
            }
        )

    security_waits = [
        record["security_start_seconds"]
        - record["security_queue_join_seconds"]
        for record in records
    ]
    immigration_waits = [
        record["immigration_start_seconds"]
        - record["immigration_queue_join_seconds"]
        for record in records
    ]
    total_waits = [
        security_wait + immigration_wait
        for security_wait, immigration_wait in zip(
            security_waits, immigration_waits
        )
    ]
    queue = reconstruct_queue_length_metrics(
        records, cutoff_seconds=cutoff
    )
    count = len(records)
    return {
        "arrival_spacing_seconds": spacing,
        "deterministic_arrivals": count,
        "security_wait_mean_seconds": (
            sum(security_waits) / count if count else 0.0
        ),
        "security_wait_p95_seconds": _nearest_rank_p95(security_waits),
        "immigration_wait_mean_seconds": (
            sum(immigration_waits) / count if count else 0.0
        ),
        "immigration_wait_p95_seconds": _nearest_rank_p95(immigration_waits),
        "total_queue_wait_mean_seconds": (
            sum(total_waits) / count if count else 0.0
        ),
        "total_queue_wait_p95_seconds": _nearest_rank_p95(total_waits),
        "peak_security_waiting_queue": queue[
            "peak_security_waiting_queue"
        ],
        "peak_immigration_waiting_queue": queue[
            "peak_immigration_waiting_queue"
        ],
        "peak_total_waiting_queue": queue["peak_total_waiting_queue"],
    }


def build_ideal_case_comparator(
    estimates: Sequence[Mapping[str, object]],
    *,
    security_capacities: Sequence[int],
    immigration_capacities: Sequence[int],
    study_id: str,
    arrival_rate_per_second: float,
    arrival_cutoff_seconds: float,
    security_service_seconds: float,
    immigration_service_seconds: float,
) -> list[dict[str, object]]:
    """Overlay linear capacity diagnostics and deterministic ideal delays."""

    estimate_index = {
        (
            _integer(row["security_capacity"], "security_capacity"),
            _integer(row["immigration_capacity"], "immigration_capacity"),
            str(row["metric"]),
        ): row
        for row in estimates
    }
    arrival_rate = _float(
        arrival_rate_per_second, "arrival_rate_per_second"
    )
    security_service = _float(
        security_service_seconds, "security_service_seconds"
    )
    immigration_service = _float(
        immigration_service_seconds, "immigration_service_seconds"
    )
    security_a = arrival_rate * security_service
    immigration_a = arrival_rate * immigration_service

    def estimate(cell: Cell, metric: str) -> Mapping[str, object]:
        try:
            return estimate_index[(*cell, metric)]
        except KeyError as error:
            raise ValueError(
                f"cell estimate is missing {cell}/{metric}"
            ) from error

    rows: list[dict[str, object]] = []
    for security_capacity in security_capacities:
        for immigration_capacity in immigration_capacities:
            cell = (security_capacity, immigration_capacity)
            ideal = deterministic_two_stage_oracle(
                arrival_rate_per_second=arrival_rate,
                arrival_cutoff_seconds=arrival_cutoff_seconds,
                security_capacity=security_capacity,
                immigration_capacity=immigration_capacity,
                security_service_seconds=security_service,
                immigration_service_seconds=immigration_service,
            )
            anylogic_mean = estimate(
                cell, "total_queue_wait_mean_seconds"
            )
            anylogic_p95 = estimate(
                cell, "total_queue_wait_p95_seconds"
            )
            anylogic_peak = estimate(cell, "peak_total_waiting_queue")
            ideal_mean = float(ideal["total_queue_wait_mean_seconds"])
            ideal_p95 = float(ideal["total_queue_wait_p95_seconds"])
            ideal_peak = float(ideal["peak_total_waiting_queue"])
            security_throughput = security_capacity / security_service
            immigration_throughput = (
                immigration_capacity / immigration_service
            )
            rows.append(
                {
                    "schema_version": SCHEMA_VERSION,
                    "study_id": study_id,
                    "comparator_id": "DETERMINISTIC_IDEAL_CONTROL_V1",
                    "security_capacity": security_capacity,
                    "immigration_capacity": immigration_capacity,
                    "arrival_rate_per_second": arrival_rate,
                    "arrival_spacing_seconds": ideal[
                        "arrival_spacing_seconds"
                    ],
                    "arrival_cutoff_seconds": arrival_cutoff_seconds,
                    "deterministic_arrivals": ideal[
                        "deterministic_arrivals"
                    ],
                    "security_service_seconds": security_service,
                    "immigration_service_seconds": immigration_service,
                    "security_throughput_capacity_per_second": (
                        security_throughput
                    ),
                    "immigration_throughput_capacity_per_second": (
                        immigration_throughput
                    ),
                    "system_bottleneck_throughput_capacity_per_second": min(
                        security_throughput, immigration_throughput
                    ),
                    "security_throughput_headroom_per_second": (
                        security_throughput - arrival_rate
                    ),
                    "immigration_throughput_headroom_per_second": (
                        immigration_throughput - arrival_rate
                    ),
                    "security_offered_workload_a": security_a,
                    "immigration_offered_workload_a": immigration_a,
                    "security_rho": security_a / security_capacity,
                    "immigration_rho": immigration_a
                    / immigration_capacity,
                    "security_capacity_minus_a": (
                        security_capacity - security_a
                    ),
                    "immigration_capacity_minus_a": (
                        immigration_capacity - immigration_a
                    ),
                    "security_beta": (
                        security_capacity - security_a
                    )
                    / math.sqrt(security_a),
                    "immigration_beta": (
                        immigration_capacity - immigration_a
                    )
                    / math.sqrt(immigration_a),
                    "security_rho_threshold_crossed": (
                        security_a >= security_capacity
                    ),
                    "immigration_rho_threshold_crossed": (
                        immigration_a >= immigration_capacity
                    ),
                    "ideal_security_wait_mean_seconds": ideal[
                        "security_wait_mean_seconds"
                    ],
                    "ideal_security_wait_p95_seconds": ideal[
                        "security_wait_p95_seconds"
                    ],
                    "ideal_immigration_wait_mean_seconds": ideal[
                        "immigration_wait_mean_seconds"
                    ],
                    "ideal_immigration_wait_p95_seconds": ideal[
                        "immigration_wait_p95_seconds"
                    ],
                    "ideal_total_queue_wait_mean_seconds": ideal_mean,
                    "ideal_total_queue_wait_p95_seconds": ideal_p95,
                    "ideal_peak_security_waiting_queue": ideal[
                        "peak_security_waiting_queue"
                    ],
                    "ideal_peak_immigration_waiting_queue": ideal[
                        "peak_immigration_waiting_queue"
                    ],
                    "ideal_peak_total_waiting_queue": ideal_peak,
                    "anylogic_total_queue_wait_mean_estimate_seconds": (
                        anylogic_mean["mean"]
                    ),
                    "anylogic_total_queue_wait_mean_ci_low_seconds": (
                        anylogic_mean["ci_low"]
                    ),
                    "anylogic_total_queue_wait_mean_ci_high_seconds": (
                        anylogic_mean["ci_high"]
                    ),
                    "anylogic_total_queue_wait_p95_estimate_seconds": (
                        anylogic_p95["mean"]
                    ),
                    "anylogic_total_queue_wait_p95_ci_low_seconds": (
                        anylogic_p95["ci_low"]
                    ),
                    "anylogic_total_queue_wait_p95_ci_high_seconds": (
                        anylogic_p95["ci_high"]
                    ),
                    "anylogic_peak_total_waiting_queue_estimate": (
                        anylogic_peak["mean"]
                    ),
                    "anylogic_peak_total_waiting_queue_ci_low": (
                        anylogic_peak["ci_low"]
                    ),
                    "anylogic_peak_total_waiting_queue_ci_high": (
                        anylogic_peak["ci_high"]
                    ),
                    "variability_congestion_penalty_mean_wait_seconds": (
                        float(anylogic_mean["mean"]) - ideal_mean
                    ),
                    "variability_congestion_penalty_mean_wait_ci_low_seconds": (
                        float(anylogic_mean["ci_low"]) - ideal_mean
                    ),
                    "variability_congestion_penalty_mean_wait_ci_high_seconds": (
                        float(anylogic_mean["ci_high"]) - ideal_mean
                    ),
                    "variability_congestion_penalty_p95_wait_seconds": (
                        float(anylogic_p95["mean"]) - ideal_p95
                    ),
                    "variability_congestion_penalty_p95_wait_ci_low_seconds": (
                        float(anylogic_p95["ci_low"]) - ideal_p95
                    ),
                    "variability_congestion_penalty_p95_wait_ci_high_seconds": (
                        float(anylogic_p95["ci_high"]) - ideal_p95
                    ),
                    "variability_congestion_penalty_peak_queue": (
                        float(anylogic_peak["mean"]) - ideal_peak
                    ),
                    "variability_congestion_penalty_peak_queue_ci_low": (
                        float(anylogic_peak["ci_low"]) - ideal_peak
                    ),
                    "variability_congestion_penalty_peak_queue_ci_high": (
                        float(anylogic_peak["ci_high"]) - ideal_peak
                    ),
                    "interpretation_role": (
                        "IDEAL_CONTROL_OVERLAY_NOT_CALIBRATED_FORECAST"
                    ),
                }
            )
    return rows


def _replication_value_index(
    rows: Sequence[Mapping[str, object]],
    *,
    cells: Sequence[Cell],
    replication_ids: Sequence[int],
    metrics: Sequence[str],
) -> dict[tuple[Cell, int, str], float]:
    expected = {
        (cell, replication_id)
        for cell in cells
        for replication_id in replication_ids
    }
    seen: set[tuple[Cell, int]] = set()
    values: dict[tuple[Cell, int, str], float] = {}
    for row in rows:
        cell = (
            _integer(row["security_capacity"], "security_capacity"),
            _integer(row["immigration_capacity"], "immigration_capacity"),
        )
        replication = _integer(row["replication_id"], "replication_id")
        key = (cell, replication)
        if key in seen:
            raise ValueError(f"duplicate response-surface replication {key}")
        seen.add(key)
        for metric in metrics:
            values[(cell, replication, metric)] = _float(
                row[metric], f"{key}/{metric}"
            )
    missing = expected - seen
    unexpected = seen - expected
    if missing or unexpected:
        raise ValueError(
            "replication rows do not have exact response-surface coverage "
            f"(missing={len(missing)}, unexpected={len(unexpected)})"
        )
    return values


def build_response_surface_analysis(
    replication_rows: Sequence[Mapping[str, object]],
    *,
    security_capacities: Sequence[int],
    immigration_capacities: Sequence[int],
    replication_ids: Sequence[int],
    balanced_joint_path: Sequence[Sequence[int]],
    study_id: str,
    metrics: Sequence[str] = ANALYSIS_METRICS,
    ci_level: float = DEFAULT_CI_LEVEL,
    security_offered_workload: float | None = None,
    immigration_offered_workload: float | None = None,
) -> dict[str, list[dict[str, object]]]:
    """Construct descriptive estimates and paired finite-difference views."""

    security = tuple(security_capacities)
    immigration = tuple(immigration_capacities)
    replications = tuple(replication_ids)
    metric_names = tuple(metrics)
    if len(security) < 3 or len(set(security)) != len(security):
        raise ValueError("at least three unique Security capacities are required")
    if len(immigration) < 3 or len(set(immigration)) != len(immigration):
        raise ValueError(
            "at least three unique Immigration capacities are required"
        )
    if tuple(sorted(security, reverse=True)) != security:
        raise ValueError("Security capacities must be in descending order")
    if tuple(sorted(immigration, reverse=True)) != immigration:
        raise ValueError("Immigration capacities must be in descending order")
    if len(replications) < 2 or len(set(replications)) != len(replications):
        raise ValueError("at least two unique replications are required")
    if not metric_names or len(set(metric_names)) != len(metric_names):
        raise ValueError("metrics must be non-empty and unique")

    cells = tuple((s, i) for s in security for i in immigration)
    value = _replication_value_index(
        replication_rows,
        cells=cells,
        replication_ids=replications,
        metrics=metric_names,
    )
    analysis_role = "EXPLORATORY_SENSITIVITY_NOT_CONFIRMATORY"

    def values_for(cell: Cell, metric: str) -> list[float]:
        return [value[(cell, replication, metric)] for replication in replications]

    def linear_values(
        terms: Sequence[tuple[float, Cell]], metric: str
    ) -> list[float]:
        return [
            sum(
                coefficient * value[(cell, replication, metric)]
                for coefficient, cell in terms
            )
            for replication in replications
        ]

    estimates: list[dict[str, object]] = []
    estimate_index: dict[tuple[Cell, str], dict[str, object]] = {}
    for cell in cells:
        for metric in metric_names:
            summary = _paired_summary(
                values_for(cell, metric), ci_level=ci_level
            )
            row: dict[str, object] = {
                "schema_version": SCHEMA_VERSION,
                "study_id": study_id,
                "security_capacity": cell[0],
                "immigration_capacity": cell[1],
                "scenario_id": response_scenario_id(*cell),
                "metric": metric,
                "estimand": "MEAN_OF_REPLICATION_LEVEL_METRIC",
                "n_replications": summary["n"],
                "mean": summary["mean"],
                "standard_deviation": summary["standard_deviation"],
                "standard_error": summary["standard_error"],
                "ci_level": ci_level,
                "ci_low": summary["ci_low"],
                "ci_high": summary["ci_high"],
                "analysis_role": analysis_role,
            }
            estimates.append(row)
            estimate_index[(cell, metric)] = row

    adjacent: list[dict[str, object]] = []
    for immigration_capacity in immigration:
        for higher, lower in zip(security, security[1:]):
            for metric in metric_names:
                summary = _paired_summary(
                    linear_values(
                        (
                            (1.0, (lower, immigration_capacity)),
                            (-1.0, (higher, immigration_capacity)),
                        ),
                        metric,
                    ),
                    ci_level=ci_level,
                )
                adjacent.append(
                    {
                        "schema_version": SCHEMA_VERSION,
                        "study_id": study_id,
                        "axis": "SECURITY",
                        "fixed_security_capacity": "",
                        "fixed_immigration_capacity": immigration_capacity,
                        "higher_capacity": higher,
                        "lower_capacity": lower,
                        "higher_scenario_id": response_scenario_id(
                            higher, immigration_capacity
                        ),
                        "lower_scenario_id": response_scenario_id(
                            lower, immigration_capacity
                        ),
                        "metric": metric,
                        "contrast": "LOWER_CAPACITY_MINUS_HIGHER_CAPACITY",
                        "n_pairs": summary["n"],
                        "mean_penalty": summary["mean"],
                        "standard_deviation": summary["standard_deviation"],
                        "standard_error": summary["standard_error"],
                        "ci_level": ci_level,
                        "ci_low": summary["ci_low"],
                        "ci_high": summary["ci_high"],
                        "crn_alignment_status": "PASS",
                        "analysis_role": analysis_role,
                    }
                )
    for security_capacity in security:
        for higher, lower in zip(immigration, immigration[1:]):
            for metric in metric_names:
                summary = _paired_summary(
                    linear_values(
                        (
                            (1.0, (security_capacity, lower)),
                            (-1.0, (security_capacity, higher)),
                        ),
                        metric,
                    ),
                    ci_level=ci_level,
                )
                adjacent.append(
                    {
                        "schema_version": SCHEMA_VERSION,
                        "study_id": study_id,
                        "axis": "IMMIGRATION",
                        "fixed_security_capacity": security_capacity,
                        "fixed_immigration_capacity": "",
                        "higher_capacity": higher,
                        "lower_capacity": lower,
                        "higher_scenario_id": response_scenario_id(
                            security_capacity, higher
                        ),
                        "lower_scenario_id": response_scenario_id(
                            security_capacity, lower
                        ),
                        "metric": metric,
                        "contrast": "LOWER_CAPACITY_MINUS_HIGHER_CAPACITY",
                        "n_pairs": summary["n"],
                        "mean_penalty": summary["mean"],
                        "standard_deviation": summary["standard_deviation"],
                        "standard_error": summary["standard_error"],
                        "ci_level": ci_level,
                        "ci_low": summary["ci_low"],
                        "ci_high": summary["ci_high"],
                        "crn_alignment_status": "PASS",
                        "analysis_role": analysis_role,
                    }
                )

    second_differences: list[dict[str, object]] = []
    for immigration_capacity in immigration:
        for higher, middle, lower in zip(
            security, security[1:], security[2:]
        ):
            for metric in metric_names:
                summary = _paired_summary(
                    linear_values(
                        (
                            (1.0, (lower, immigration_capacity)),
                            (-2.0, (middle, immigration_capacity)),
                            (1.0, (higher, immigration_capacity)),
                        ),
                        metric,
                    ),
                    ci_level=ci_level,
                )
                second_differences.append(
                    {
                        "schema_version": SCHEMA_VERSION,
                        "study_id": study_id,
                        "axis": "SECURITY",
                        "fixed_security_capacity": "",
                        "fixed_immigration_capacity": immigration_capacity,
                        "higher_capacity": higher,
                        "middle_capacity": middle,
                        "lower_capacity": lower,
                        "metric": metric,
                        "contrast": "LOWER_MINUS_2_MIDDLE_PLUS_HIGHER",
                        "n_pairs": summary["n"],
                        "mean_second_difference": summary["mean"],
                        "standard_deviation": summary["standard_deviation"],
                        "standard_error": summary["standard_error"],
                        "ci_level": ci_level,
                        "ci_low": summary["ci_low"],
                        "ci_high": summary["ci_high"],
                        "crn_alignment_status": "PASS",
                        "analysis_role": analysis_role,
                    }
                )
    for security_capacity in security:
        for higher, middle, lower in zip(
            immigration, immigration[1:], immigration[2:]
        ):
            for metric in metric_names:
                summary = _paired_summary(
                    linear_values(
                        (
                            (1.0, (security_capacity, lower)),
                            (-2.0, (security_capacity, middle)),
                            (1.0, (security_capacity, higher)),
                        ),
                        metric,
                    ),
                    ci_level=ci_level,
                )
                second_differences.append(
                    {
                        "schema_version": SCHEMA_VERSION,
                        "study_id": study_id,
                        "axis": "IMMIGRATION",
                        "fixed_security_capacity": security_capacity,
                        "fixed_immigration_capacity": "",
                        "higher_capacity": higher,
                        "middle_capacity": middle,
                        "lower_capacity": lower,
                        "metric": metric,
                        "contrast": "LOWER_MINUS_2_MIDDLE_PLUS_HIGHER",
                        "n_pairs": summary["n"],
                        "mean_second_difference": summary["mean"],
                        "standard_deviation": summary["standard_deviation"],
                        "standard_error": summary["standard_error"],
                        "ci_level": ci_level,
                        "ci_low": summary["ci_low"],
                        "ci_high": summary["ci_high"],
                        "crn_alignment_status": "PASS",
                        "analysis_role": analysis_role,
                    }
                )

    interactions: list[dict[str, object]] = []
    for security_higher, security_lower in zip(security, security[1:]):
        for immigration_higher, immigration_lower in zip(
            immigration, immigration[1:]
        ):
            for metric in metric_names:
                summary = _paired_summary(
                    linear_values(
                        (
                            (1.0, (security_lower, immigration_lower)),
                            (-1.0, (security_higher, immigration_lower)),
                            (-1.0, (security_lower, immigration_higher)),
                            (1.0, (security_higher, immigration_higher)),
                        ),
                        metric,
                    ),
                    ci_level=ci_level,
                )
                interactions.append(
                    {
                        "schema_version": SCHEMA_VERSION,
                        "study_id": study_id,
                        "security_higher_capacity": security_higher,
                        "security_lower_capacity": security_lower,
                        "immigration_higher_capacity": immigration_higher,
                        "immigration_lower_capacity": immigration_lower,
                        "metric": metric,
                        "contrast": (
                            "JOINT_REDUCTION_MINUS_SUM_OF_LOCAL_MAIN_EFFECTS"
                        ),
                        "n_pairs": summary["n"],
                        "mean_interaction": summary["mean"],
                        "standard_deviation": summary["standard_deviation"],
                        "standard_error": summary["standard_error"],
                        "ci_level": ci_level,
                        "ci_low": summary["ci_low"],
                        "ci_high": summary["ci_high"],
                        "crn_alignment_status": "PASS",
                        "analysis_role": analysis_role,
                    }
                )

    primary_metric = "total_queue_wait_p95_seconds"
    if primary_metric not in metric_names:
        raise ValueError(f"required primary metric {primary_metric} is absent")
    if security_offered_workload is None:
        security_offered_workload = math.nan
    if immigration_offered_workload is None:
        immigration_offered_workload = math.nan

    def view_row(
        view: str, path_index: int, cell: Cell
    ) -> dict[str, object]:
        estimate = estimate_index[(cell, primary_metric)]
        return {
            "schema_version": SCHEMA_VERSION,
            "study_id": study_id,
            "view": view,
            "path_index": path_index,
            "security_capacity": cell[0],
            "immigration_capacity": cell[1],
            "security_reduction": security[0] - cell[0],
            "immigration_reduction": immigration[0] - cell[1],
            "security_offered_load_ratio": (
                security_offered_workload / cell[0]
            ),
            "immigration_offered_load_ratio": (
                immigration_offered_workload / cell[1]
            ),
            "scenario_id": response_scenario_id(*cell),
            "metric": primary_metric,
            "n_replications": estimate["n_replications"],
            "mean": estimate["mean"],
            "standard_error": estimate["standard_error"],
            "ci_level": estimate["ci_level"],
            "ci_low": estimate["ci_low"],
            "ci_high": estimate["ci_high"],
        }

    security_slice = [
        view_row(
            "SECURITY_ONLY_AT_IMMIGRATION_REFERENCE",
            index,
            (security_capacity, immigration[0]),
        )
        for index, security_capacity in enumerate(security)
    ]
    immigration_slice = [
        view_row(
            "IMMIGRATION_ONLY_AT_SECURITY_REFERENCE",
            index,
            (security[0], immigration_capacity),
        )
        for index, immigration_capacity in enumerate(immigration)
    ]
    joint_cells = [tuple(map(int, pair)) for pair in balanced_joint_path]
    if any(cell not in cells for cell in joint_cells):
        raise ValueError("balanced joint path contains a cell outside the grid")
    balanced_slice = [
        view_row("BALANCED_JOINT_REDUCTION_PATH", index, cell)
        for index, cell in enumerate(joint_cells)
    ]
    heatmap = [
        view_row("FULL_RESPONSE_SURFACE", index, cell)
        for index, cell in enumerate(cells)
    ]

    bottleneck_map: list[dict[str, object]] = []
    for cell in cells:
        stage_differences = [
            value[(cell, replication, "security_wait_p95_seconds")]
            - value[(cell, replication, "immigration_wait_p95_seconds")]
            for replication in replications
        ]
        summary = _paired_summary(stage_differences, ci_level=ci_level)
        if float(summary["ci_low"]) > 0:
            classification = "SECURITY_WAIT_DOMINANT"
        elif float(summary["ci_high"]) < 0:
            classification = "IMMIGRATION_WAIT_DOMINANT"
        else:
            classification = "UNRESOLVED_AT_95_PERCENT"
        bottleneck_map.append(
            {
                "schema_version": SCHEMA_VERSION,
                "study_id": study_id,
                "security_capacity": cell[0],
                "immigration_capacity": cell[1],
                "contrast": "SECURITY_P95_MINUS_IMMIGRATION_P95",
                "n_pairs": summary["n"],
                "security_minus_immigration_p95_mean_seconds": summary["mean"],
                "standard_error": summary["standard_error"],
                "ci_level": ci_level,
                "ci_low": summary["ci_low"],
                "ci_high": summary["ci_high"],
                "bottleneck_classification": classification,
            }
        )

    return {
        "estimates": estimates,
        "adjacent_penalties": adjacent,
        "second_differences": second_differences,
        "interactions": interactions,
        "security_slice": security_slice,
        "immigration_slice": immigration_slice,
        "balanced_slice": balanced_slice,
        "heatmap": heatmap,
        "bottleneck_map": bottleneck_map,
    }


def _validate_one_run(
    run_dir: Path,
    *,
    cell: Cell,
    replication_id: int,
    scenario_row: Mapping[str, str],
    seed_row: Mapping[str, str],
    schemas: Mapping[str, Sequence[Mapping[str, str]]],
    study_id: str,
    cutoff_seconds: float,
) -> tuple[
    dict[str, object],
    tuple[int, str],
    list[tuple[str, str]],
]:
    paths = {
        table: run_dir / filename for table, filename in RESULT_FILES.items()
    }
    manifest = _require_one(
        _load_table(paths["run_manifest"], "run_manifest", schemas["run_manifest"]),
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
        paths["entity_log"], "entity_log", schemas["entity_log"]
    )
    scenario_id = response_scenario_id(*cell)
    expected_key = (scenario_id, INPUT_SAMPLE_ID, str(replication_id))
    for label, row in (
        ("run_manifest", manifest),
        ("replication_kpis", kpi),
    ):
        actual_key = (
            row["scenario_id"],
            row["input_sample_id"],
            row["replication_id"],
        )
        if actual_key != expected_key:
            raise ValueError(
                f"{run_dir}/{label}: run key {actual_key} != {expected_key}"
            )

    expected_hash = scenario_config_sha256(scenario_row)
    if manifest["config_id"] != scenario_row["config_id"]:
        raise ValueError(f"{run_dir}: config_id differs from frozen scenario")
    if manifest["config_sha256"] != expected_hash:
        raise ValueError(
            f"{run_dir}: config_sha256 differs from frozen scenario row"
        )
    for field in (
        "scenario_family",
        "reference_scenario_id",
        "drain_rule",
        "calibration_status",
        "claim_ceiling",
    ):
        if manifest[field] != scenario_row[field]:
            raise ValueError(
                f"{run_dir}: manifest {field} differs from frozen scenario"
            )
    if manifest["run_status"] != "COMPLETE":
        raise ValueError(f"{run_dir}: run_status must be COMPLETE")
    if not _same_number(manifest["arrival_cutoff_seconds"], cutoff_seconds):
        raise ValueError(f"{run_dir}: arrival cutoff drifted")
    for field in ("master_seed", *STREAM_SEED_FIELDS):
        if manifest[field] != seed_row[field]:
            raise ValueError(f"{run_dir}: {field} differs from seed manifest")

    for field in LINEAGE_FIELDS:
        if kpi[field] != manifest[field]:
            raise ValueError(f"{run_dir}: KPI {field} differs from manifest")
    if kpi["run_status"] != "COMPLETE":
        raise ValueError(f"{run_dir}: KPI run_status must be COMPLETE")
    if not _boolean(kpi["conservation_pass"], f"{run_dir}:conservation_pass"):
        raise ValueError(f"{run_dir}: conservation_pass must be true")
    if not _same_number(
        kpi["arrival_cutoff_seconds"], manifest["arrival_cutoff_seconds"]
    ) or not _same_number(kpi["drain_end_seconds"], manifest["drain_end_seconds"]):
        raise ValueError(f"{run_dir}: KPI timing lineage differs from manifest")

    counts = {
        field: _integer(kpi[field], f"{run_dir}:{field}")
        for field in COUNT_FIELDS
    }
    if any(value < 0 for value in counts.values()):
        raise ValueError(f"{run_dir}: KPI counts must be non-negative")
    wip_components = (
        counts["security_queue_at_cutoff"]
        + counts["security_in_service_at_cutoff"]
        + counts["immigration_queue_at_cutoff"]
        + counts["immigration_in_service_at_cutoff"]
    )
    if counts["wip_at_cutoff"] != wip_components:
        raise ValueError(f"{run_dir}: cutoff WIP components do not sum")
    if counts["arrivals"] != (
        counts["completed_at_cutoff"] + counts["wip_at_cutoff"]
    ):
        raise ValueError(f"{run_dir}: cutoff conservation fails")
    if counts["cutoff_backlog"] != counts["wip_at_cutoff"]:
        raise ValueError(f"{run_dir}: cutoff backlog differs from WIP")
    if counts["rejected_or_dropped_count"] != 0:
        raise ValueError(f"{run_dir}: rejected/dropped travellers are prohibited")
    if counts["completed_after_drain"] != counts["arrivals"]:
        raise ValueError(f"{run_dir}: full-drain conservation fails")
    if len(entities) != counts["arrivals"]:
        raise ValueError(
            f"{run_dir}: entity count {len(entities)} != arrivals "
            f"{counts['arrivals']}"
        )
    expected_fraction = (
        counts["cutoff_backlog"] / counts["arrivals"]
        if counts["arrivals"]
        else 0.0
    )
    if not _same_number(kpi["cutoff_backlog_fraction"], expected_fraction):
        raise ValueError(f"{run_dir}: cutoff backlog fraction is wrong")

    drain_end_seconds = _float(
        manifest["drain_end_seconds"], f"{run_dir}:drain_end_seconds"
    )
    if drain_end_seconds < cutoff_seconds:
        raise ValueError(f"{run_dir}: drain ends before the arrival cutoff")
    for row_index, entity in enumerate(entities, start=2):
        for field in LINEAGE_FIELDS:
            if entity[field] != manifest[field]:
                raise ValueError(
                    f"{run_dir}/entity_log.csv:{row_index}: "
                    f"{field} differs from manifest"
                )
        _validate_entity_chronology(
            entity,
            cutoff_seconds=cutoff_seconds,
            drain_end_seconds=drain_end_seconds,
            label=f"{run_dir}/entity_log.csv:{row_index}",
        )

    reconstructed = reconstruct_queue_length_metrics(
        entities, cutoff_seconds=cutoff_seconds
    )
    row: dict[str, object] = {
        **kpi,
        "study_id": study_id,
        "security_capacity": cell[0],
        "immigration_capacity": cell[1],
        **{
            "analysis_window_start_seconds": reconstructed[
                "window_start_seconds"
            ],
            "analysis_window_end_seconds": reconstructed["cutoff_seconds"],
            "peak_window_end_seconds": reconstructed[
                "peak_window_end_seconds"
            ],
            "security_positive_wait_count": reconstructed[
                "security_positive_wait_count"
            ],
            "immigration_positive_wait_count": reconstructed[
                "immigration_positive_wait_count"
            ],
            "peak_security_waiting_queue": reconstructed[
                "peak_security_waiting_queue"
            ],
            "peak_immigration_waiting_queue": reconstructed[
                "peak_immigration_waiting_queue"
            ],
            "peak_total_waiting_queue": reconstructed[
                "peak_total_waiting_queue"
            ],
            "security_queue_person_seconds": reconstructed[
                "security_queue_person_seconds"
            ],
            "immigration_queue_person_seconds": reconstructed[
                "immigration_queue_person_seconds"
            ],
            "total_queue_person_seconds": reconstructed[
                "total_queue_person_seconds"
            ],
            "time_weighted_mean_security_waiting_queue": reconstructed[
                "security_queue_time_weighted_mean"
            ],
            "time_weighted_mean_immigration_waiting_queue": reconstructed[
                "immigration_queue_time_weighted_mean"
            ],
            "time_weighted_mean_total_waiting_queue": reconstructed[
                "time_weighted_mean_total_waiting_queue"
            ],
        },
        "master_seed": manifest["master_seed"],
        "arrival_seed": manifest["arrival_seed"],
        "service_seed": manifest["service_seed"],
        "routing_seed": manifest["routing_seed"],
        "tie_seed": manifest["tie_seed"],
    }
    draw_signature = _entity_draw_signature(
        entities,
        label=f"{run_dir}/entity_log.csv",
    )
    artifacts = [
        (portable_path(path), _sha256(path)) for path in paths.values()
    ]
    return row, draw_signature, artifacts


def _crn_report(
    draw_signatures: Mapping[tuple[Cell, int], tuple[int, str]],
    *,
    cells: Sequence[Cell],
    replication_ids: Sequence[int],
    study_id: str,
) -> dict[str, object]:
    errors: list[str] = []
    compared_pairs = 0
    compared_draw_values = 0
    for replication_id in replication_ids:
        reference = draw_signatures.get((REFERENCE_CELL, replication_id))
        if reference is None:
            errors.append(
                f"replication {replication_id}: reference draw signature missing"
            )
            continue
        reference_count, reference_digest = reference
        for cell in cells:
            if cell == REFERENCE_CELL:
                continue
            current = draw_signatures.get((cell, replication_id))
            if current is None:
                errors.append(
                    f"replication {replication_id}: {cell} signature missing"
                )
                continue
            count, digest = current
            if count != reference_count:
                errors.append(
                    f"replication {replication_id}: {cell} traveller count "
                    f"{count} differs from reference {reference_count}"
                )
                continue
            if digest != reference_digest:
                errors.append(
                    f"replication {replication_id}: {cell} exogenous draw "
                    "digest differs from reference"
                )
                continue
            compared_pairs += count
            compared_draw_values += count * len(DRAW_FIELDS)
    expected_comparisons = (
        sum(
            draw_signatures[(REFERENCE_CELL, replication_id)][0]
            for replication_id in replication_ids
            if (REFERENCE_CELL, replication_id) in draw_signatures
        )
        * (len(cells) - 1)
    )
    passed = not errors and compared_pairs == expected_comparisons
    return {
        "schema_version": SCHEMA_VERSION,
        "validation": CRN_VALIDATION_ID,
        "study_id": study_id,
        "status": "PASS" if passed else "FAIL",
        "coverage_pass": len(draw_signatures)
        == len(cells) * len(replication_ids),
        "seed_alignment_pass": passed,
        "traveller_level_alignment_pass": passed,
        "branch_invariant_draws_pass": passed,
        "comparison_strategy": (
            "Per-run order-independent SHA-256 over traveller_id and "
            "canonical numeric branch-invariant draws; only one run ledger "
            "is resident at a time."
        ),
        "reference_cell": {
            "security_capacity": REFERENCE_CELL[0],
            "immigration_capacity": REFERENCE_CELL[1],
        },
        "cell_count": len(cells),
        "replication_count": len(replication_ids),
        "draw_fields": list(DRAW_FIELDS),
        "compared_traveller_pairs": compared_pairs,
        "compared_draw_values": compared_draw_values,
        "expected_compared_traveller_pairs": expected_comparisons,
        "errors": errors,
        "claim_rule": (
            "Paired finite differences and interactions are emitted only "
            "when this exact traveller/draw alignment gate passes."
        ),
    }


def _prior_run_metrics(
    run_dir: Path,
    *,
    schemas: Mapping[str, Sequence[Mapping[str, str]]],
    cutoff_seconds: float,
) -> tuple[dict[str, float], tuple[int, str], dict[str, str]]:
    manifest_path = run_dir / RESULT_FILES["run_manifest"]
    kpi_path = run_dir / RESULT_FILES["replication_kpis"]
    entity_path = run_dir / RESULT_FILES["entity_log"]
    manifest = _require_one(
        _load_table(manifest_path, "run_manifest", schemas["run_manifest"]),
        manifest_path,
    )
    kpi = _require_one(
        _load_table(kpi_path, "replication_kpis", schemas["replication_kpis"]),
        kpi_path,
    )
    entities = _load_table(entity_path, "entity_log", schemas["entity_log"])
    reconstructed = reconstruct_queue_length_metrics(
        entities, cutoff_seconds=cutoff_seconds
    )
    metrics = {
        metric: (
            float(reconstructed[metric])
            if metric in reconstructed
            else _float(kpi[metric], f"{run_dir}:{metric}")
        )
        for metric in REPRODUCIBILITY_METRICS
    }
    return (
        metrics,
        _entity_draw_signature(entities, label=str(entity_path)),
        manifest,
    )


def _cross_batch_report(
    replication_rows: Sequence[Mapping[str, object]],
    draw_signatures: Mapping[tuple[Cell, int], tuple[int, str]],
    *,
    design_path: Path,
    schemas: Mapping[str, Sequence[Mapping[str, str]]],
    replication_ids: Sequence[int],
    prior_roots: Mapping[str, Path],
    cutoff_seconds: float,
    numeric_tolerance: float,
) -> dict[str, object]:
    design = load_design(design_path)
    study_id = str(design["study_id"])
    current = {
        (
            _integer(row["security_capacity"], "security_capacity"),
            _integer(row["immigration_capacity"], "immigration_capacity"),
            _integer(row["replication_id"], "replication_id"),
        ): row
        for row in replication_rows
    }
    cells_report: list[dict[str, object]] = []
    errors: list[str] = []
    available_cells = 0
    compared_runs = 0
    for cell, specification in cross_batch_validation_cells(
        design_path
    ).items():
        collection = str(specification["source_collection"])
        source_scenario = str(specification["source_scenario_id"])
        source_root = prior_roots.get(collection)
        cell_errors: list[str] = []
        if source_root is None:
            cells_report.append(
                {
                    "security_capacity": cell[0],
                    "immigration_capacity": cell[1],
                    "source_collection": collection,
                    "source_scenario_id": source_scenario,
                    "status": "NOT_AVAILABLE",
                    "compared_runs": 0,
                    "max_absolute_metric_difference": None,
                    "errors": ["source root was not supplied"],
                }
            )
            continue
        sample_root = source_root / source_scenario / INPUT_SAMPLE_ID
        if not sample_root.is_dir():
            cells_report.append(
                {
                    "security_capacity": cell[0],
                    "immigration_capacity": cell[1],
                    "source_collection": collection,
                    "source_scenario_id": source_scenario,
                    "status": "NOT_AVAILABLE",
                    "compared_runs": 0,
                    "max_absolute_metric_difference": None,
                    "errors": [f"source results are absent: {sample_root}"],
                }
            )
            continue
        available_cells += 1
        maximum_difference = 0.0
        for replication_id in replication_ids:
            prior_dir = (
                sample_root / f"replication_{replication_id:03d}"
            )
            try:
                prior_metrics, prior_signature, prior_manifest = (
                    _prior_run_metrics(
                        prior_dir,
                        schemas=schemas,
                        cutoff_seconds=cutoff_seconds,
                    )
                )
                current_row = current[(*cell, replication_id)]
                current_signature = draw_signatures[(cell, replication_id)]
                for field in ("master_seed", *STREAM_SEED_FIELDS):
                    if str(current_row[field]) != prior_manifest[field]:
                        cell_errors.append(
                            f"replication {replication_id}: {field} differs"
                        )
                if current_signature != prior_signature:
                    cell_errors.append(
                        f"replication {replication_id}: exogenous draws differ"
                    )
                for metric, prior_value in prior_metrics.items():
                    difference = abs(
                        _float(
                            current_row[metric],
                            f"current {cell}/{replication_id}/{metric}",
                        )
                        - prior_value
                    )
                    maximum_difference = max(maximum_difference, difference)
                    if difference > numeric_tolerance:
                        cell_errors.append(
                            f"replication {replication_id}: {metric} differs "
                            f"by {difference:.12g}"
                        )
                compared_runs += 1
            except (FileNotFoundError, KeyError, TypeError, ValueError) as error:
                cell_errors.append(
                    f"replication {replication_id}: {error}"
                )
        cell_status = "PASS" if not cell_errors else "FAIL"
        if cell_errors:
            errors.extend(
                [f"{cell}: {message}" for message in cell_errors[:25]]
            )
            if len(cell_errors) > 25:
                errors.append(
                    f"{cell}: {len(cell_errors) - 25} further errors omitted"
                )
        cells_report.append(
            {
                "security_capacity": cell[0],
                "immigration_capacity": cell[1],
                "source_collection": collection,
                "source_scenario_id": source_scenario,
                "status": cell_status,
                "compared_runs": len(replication_ids),
                "max_absolute_metric_difference": maximum_difference,
                "errors": cell_errors[:25],
            }
        )
    if available_cells == 0:
        status = "NOT_AVAILABLE"
    elif available_cells != len(cells_report):
        status = "PARTIAL"
        errors.append(
            "only some frozen cross-batch validation cells were available"
        )
    else:
        status = "PASS" if not errors else "FAIL"
    return {
        "schema_version": SCHEMA_VERSION,
        "validation": REPRODUCIBILITY_ID,
        "study_id": study_id,
        "status": status,
        "available_cell_count": available_cells,
        "expected_cell_count": len(cells_report),
        "compared_run_count": compared_runs,
        "expected_run_count_if_available": (
            len(cells_report) * len(replication_ids)
        ),
        "numeric_tolerance": numeric_tolerance,
        "metrics": list(REPRODUCIBILITY_METRICS),
        "cells": cells_report,
        "errors": errors,
        "analysis_inclusion_rule": (
            "Prior batches are validation-only and contribute zero rows to "
            "the response-surface estimates."
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


def build_threshold_exceedance_diagnostics(
    replication_rows: Sequence[Mapping[str, object]],
    *,
    study_id: str,
    entity_row_count: int,
) -> dict[str, object]:
    """Summarise registered illustrative wait thresholds without testing them."""

    if not replication_rows:
        raise ValueError("threshold diagnostics require replication rows")

    thresholds: list[dict[str, object]] = []
    for threshold_seconds, metric in THRESHOLD_EXCEEDANCE_FIELDS:
        rates = [
            _float(row[metric], f"{metric} replication {index}")
            for index, row in enumerate(replication_rows, start=1)
        ]
        if any(rate < 0.0 or rate > 1.0 for rate in rates):
            raise ValueError(f"{metric} must be within [0, 1]")
        nonzero_count = sum(rate > 0.0 for rate in rates)
        thresholds.append(
            {
                "threshold_seconds": threshold_seconds,
                "metric": metric,
                "mean_replication_rate": sum(rates) / len(rates),
                "maximum_replication_rate": max(rates),
                "nonzero_replication_count": nonzero_count,
                "all_replication_rates_zero": nonzero_count == 0,
            }
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "diagnostic": THRESHOLD_DIAGNOSTIC_ID,
        "study_id": study_id,
        "status": "COMPLETE",
        "role": "REGISTERED_ILLUSTRATIVE_DIAGNOSTIC_NOT_ICA_SLA",
        "estimand": "WITHIN_REPLICATION_TRAVELLER_EXCEEDANCE_RATE",
        "replication_count": len(replication_rows),
        "entity_row_count": entity_row_count,
        "all_thresholds_zero": all(
            bool(row["all_replication_rates_zero"]) for row in thresholds
        ),
        "thresholds": thresholds,
    }


def _readme_text(
    *,
    study_id: str,
    run_count: int,
    entity_row_count: int,
    cross_batch_status: str,
    threshold_diagnostics: Mapping[str, object],
) -> str:
    threshold_summary = (
        "All registered illustrative 600/900/1200-second traveller-level "
        "exceedance rates are zero in these runs. "
        if threshold_diagnostics["all_thresholds_zero"]
        else "At least one registered illustrative traveller-level "
        "exceedance rate is non-zero in these runs. "
    )
    return (
        "# Capacity response-surface analysis\n\n"
        f"`{study_id}` is a post-outcome exploratory sensitivity study at "
        "fixed Base demand. It maps the 9 Security capacities (36 to 28) by "
        "6 Immigration capacities (21 to 16), with 50 replications per cell "
        f"({run_count:,} AnyLogic runs).\n\n"
        "The primary descriptive response is the mean replication-level P95 "
        "total queue wait. Cell intervals, one-position marginal penalties, "
        "second finite differences, and local difference-in-differences "
        "interactions all use the 50 replication units. Paired quantities are "
        "released only after exact registered seeds and traveller-level "
        "branch-invariant draws align across all cells.\n\n"
        "Every cell uses a 300-second terminating arrival cohort from an "
        "empty and idle start, followed by full drain. The accepted "
        "1.364213/s directional corridor crossing rate is mapped "
        "conditionally into one pooled two-stage processing abstraction; "
        "physical processing-unit allocation, routing, and resource sharing "
        "were not observed in the source video.\n\n"
        "Queue peaks are reconstructed from half-open waiting intervals over "
        "the full drain. Time-weighted queue means use the [0, 300) arrival "
        "window. The source entity ledgers are intentionally not copied into "
        f"this compact package; {entity_row_count:,} rows were streamed one "
        "run at a time and retained only through metrics and audit hashes.\n\n"
        f"{threshold_summary}"
        "These thresholds are supporting diagnostics, not ICA service-level "
        "agreements; their auditable summary is in "
        "`threshold_exceedance_diagnostics.json`.\n\n"
        f"Cross-batch validation status: `{cross_batch_status}`. Earlier "
        "results are validation-only and contribute no observations to these "
        "estimates.\n\n"
        "The deterministic ideal comparator sends perfectly regular arrivals "
        "through the same two fixed-service pooled-FCFS stages. Stage "
        "throughput capacity (`c / service time`) is linear in `c`; its delay "
        "is computed by the queueing oracle and is not forced to be linear. "
        "AnyLogic minus ideal is labelled a variability/congestion penalty, "
        "not an estimator of one uniquely causal mechanism.\n\n"
        "These integer-capacity simulation points can reveal thresholds and "
        "curvature inside the tested sandbox. They are not a calibrated site "
        "forecast, an observed roster, a causal staffing estimate, or an HTX "
        "staffing recommendation. Any curve drawn between integer capacities "
        "is a labelled visual guide, not simulated evidence at fractional "
        "positions.\n"
    )


def package_capacity_response_surface_analysis(
    results_root: Path = DEFAULT_RESULTS_ROOT,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    *,
    design_path: Path = DEFAULT_DESIGN,
    scenarios_path: Path = DEFAULT_SCENARIOS,
    seed_manifest_path: Path = DEFAULT_SEED_MANIFEST,
    schema_registry_path: Path = DEFAULT_SCHEMA_REGISTRY,
    prior_roots: Mapping[str, Path] = DEFAULT_PRIOR_ROOTS,
    ci_level: float = DEFAULT_CI_LEVEL,
    numeric_tolerance: float = DEFAULT_NUMERIC_TOLERANCE,
) -> dict[str, object]:
    """Validate all raw runs and write the compact exploratory evidence set."""

    results_root = results_root.resolve()
    output_dir = output_dir.resolve()
    design_path = design_path.resolve()
    scenarios_path = scenarios_path.resolve()
    seed_manifest_path = seed_manifest_path.resolve()
    schema_registry_path = schema_registry_path.resolve()
    if not 0 < ci_level < 1:
        raise ValueError("ci_level must be between 0 and 1")
    if numeric_tolerance < 0 or not math.isfinite(numeric_tolerance):
        raise ValueError("numeric_tolerance must be finite and non-negative")

    design_validation = validate_response_surface_design(
        design_path,
        scenarios_path,
        seed_manifest_path,
    )
    if design_validation["status"] != "PASS":
        raise ValueError(
            "frozen response-surface design validation failed: "
            + "; ".join(map(str, design_validation["errors"]))
        )
    design = load_design(design_path)
    study_id = str(design["study_id"])
    fixed = design["fixed_inputs"]
    cutoff_seconds = _float(
        fixed["arrival_cutoff_seconds"], "arrival_cutoff_seconds"
    )
    cells = tuple(full_grid(design_path))
    security_capacities = tuple(
        int(value) for value in design["capacity_grid"]["security_capacities"]
    )
    immigration_capacities = tuple(
        int(value)
        for value in design["capacity_grid"]["immigration_capacities"]
    )
    expected_directories = _expected_run_paths(
        results_root, cells, REPLICATION_IDS
    )
    _validate_exact_coverage(results_root, expected_directories)

    schemas = load_result_schemas(schema_registry_path)
    if set(RESULT_FILES) - set(schemas):
        raise ValueError("result schema registry is missing a required table")
    scenario_rows = {
        row["scenario_id"]: row
        for row in load_response_surface_scenario_rows(scenarios_path)
    }
    seed_rows = {
        int(row["replication_id"]): row
        for row in load_response_surface_seed_rows(seed_manifest_path)
    }
    if set(seed_rows) != set(REPLICATION_IDS):
        raise ValueError("seed manifest does not contain replications 1..50")

    replication_rows: list[dict[str, object]] = []
    draw_signatures: dict[tuple[Cell, int], tuple[int, str]] = {}
    artifact_entries: list[tuple[str, str]] = []
    entity_row_count = 0
    for cell in cells:
        scenario_id = response_scenario_id(*cell)
        scenario = scenario_rows.get(scenario_id)
        if scenario is None:
            raise ValueError(f"frozen scenario row is missing: {scenario_id}")
        for replication_id in REPLICATION_IDS:
            run_dir = _run_directory(
                results_root, scenario_id, replication_id
            )
            row, signature, artifacts = _validate_one_run(
                run_dir,
                cell=cell,
                replication_id=replication_id,
                scenario_row=scenario,
                seed_row=seed_rows[replication_id],
                schemas=schemas,
                study_id=study_id,
                cutoff_seconds=cutoff_seconds,
            )
            replication_rows.append(row)
            draw_signatures[(cell, replication_id)] = signature
            entity_row_count += signature[0]
            artifact_entries.extend(artifacts)

    crn = _crn_report(
        draw_signatures,
        cells=cells,
        replication_ids=REPLICATION_IDS,
        study_id=study_id,
    )
    if crn["status"] != "PASS":
        raise ValueError(
            "traveller-level CRN alignment failed: "
            + "; ".join(map(str, crn["errors"][:5]))
        )

    cross_batch = _cross_batch_report(
        replication_rows,
        draw_signatures,
        design_path=design_path,
        schemas=schemas,
        replication_ids=REPLICATION_IDS,
        prior_roots={
            key: value.resolve() for key, value in prior_roots.items()
        },
        cutoff_seconds=cutoff_seconds,
        numeric_tolerance=numeric_tolerance,
    )
    if cross_batch["status"] in {"FAIL", "PARTIAL"}:
        raise ValueError(
            "cross-batch reproducibility validation failed: "
            + "; ".join(map(str, cross_batch["errors"][:5]))
        )

    workload = design["capacity_grid"]["selection_rationale"]
    analysis = build_response_surface_analysis(
        replication_rows,
        security_capacities=security_capacities,
        immigration_capacities=immigration_capacities,
        replication_ids=REPLICATION_IDS,
        balanced_joint_path=design["analysis"]["balanced_joint_path"],
        study_id=study_id,
        ci_level=ci_level,
        security_offered_workload=_float(
            workload["security_offered_workload_positions"],
            "security offered workload",
        ),
        immigration_offered_workload=_float(
            workload["immigration_offered_workload_positions"],
            "immigration offered workload",
        ),
    )
    ideal_comparator = build_ideal_case_comparator(
        analysis["estimates"],
        security_capacities=security_capacities,
        immigration_capacities=immigration_capacities,
        study_id=study_id,
        arrival_rate_per_second=_float(
            fixed["arrival_rate_per_second"], "arrival_rate_per_second"
        ),
        arrival_cutoff_seconds=cutoff_seconds,
        security_service_seconds=_float(
            fixed["security_service_p1_seconds"],
            "security_service_p1_seconds",
        ),
        immigration_service_seconds=_float(
            fixed["immigration_service_p1_seconds"],
            "immigration_service_p1_seconds",
        ),
    )
    threshold_diagnostics = build_threshold_exceedance_diagnostics(
        replication_rows,
        study_id=study_id,
        entity_row_count=entity_row_count,
    )

    validation = {
        "schema_version": SCHEMA_VERSION,
        "validation": VALIDATION_ID,
        "study_id": study_id,
        "status": "PASS",
        "coverage_status": "PASS",
        "canonical_schema_status": "PASS",
        "lineage_status": "PASS",
        "frozen_config_hash_status": "PASS",
        "seed_status": "PASS",
        "run_status": "PASS",
        "conservation_status": "PASS",
        "full_drain_status": "PASS",
        "crn_alignment_status": crn["status"],
        "cross_batch_reproducibility_status": cross_batch["status"],
        "scenario_count": len(cells),
        "input_sample_count": 1,
        "replications_per_cell": len(REPLICATION_IDS),
        "expected_run_count": len(cells) * len(REPLICATION_IDS),
        "actual_run_count": len(replication_rows),
        "entity_row_count": entity_row_count,
        "raw_file_count": len(artifact_entries),
        "raw_tree_sha256": _tree_digest(artifact_entries),
        "artifact_hashes": {
            "design_sha256": _sha256(design_path),
            "scenarios_sha256": _sha256(scenarios_path),
            "seed_manifest_sha256": _sha256(seed_manifest_path),
            "schema_registry_sha256": _sha256(schema_registry_path),
        },
        "errors": [],
        "claim_boundary": design["claim_ceiling"],
    }

    outputs: tuple[
        tuple[str, Sequence[Mapping[str, object]], Sequence[str]], ...
    ] = (
        (
            "response_surface_by_replication.csv",
            replication_rows,
            REPLICATION_FIELDS,
        ),
        ("cell_estimates.csv", analysis["estimates"], ESTIMATE_FIELDS),
        (
            "adjacent_marginal_penalties.csv",
            analysis["adjacent_penalties"],
            ADJACENT_FIELDS,
        ),
        (
            "second_finite_differences.csv",
            analysis["second_differences"],
            SECOND_DIFFERENCE_FIELDS,
        ),
        (
            "local_interactions.csv",
            analysis["interactions"],
            INTERACTION_FIELDS,
        ),
        ("security_only_slice.csv", analysis["security_slice"], VIEW_FIELDS),
        (
            "immigration_only_slice.csv",
            analysis["immigration_slice"],
            VIEW_FIELDS,
        ),
        (
            "balanced_joint_slice.csv",
            analysis["balanced_slice"],
            VIEW_FIELDS,
        ),
        ("heatmap.csv", analysis["heatmap"], VIEW_FIELDS),
        (
            "stage_bottleneck_map.csv",
            analysis["bottleneck_map"],
            BOTTLENECK_FIELDS,
        ),
        (
            "ideal_case_comparator.csv",
            ideal_comparator,
            IDEAL_COMPARATOR_FIELDS,
        ),
        (
            "queueing_theory_overlay.csv",
            ideal_comparator,
            QUEUEING_OVERLAY_FIELDS,
        ),
    )
    for filename, rows, fields in outputs:
        _write_csv(output_dir / filename, rows, fields)
    _write_json(output_dir / "validation.json", validation)
    _write_json(output_dir / "crn_alignment.json", crn)
    _write_json(
        output_dir / "cross_batch_reproducibility.json", cross_batch
    )
    _write_json(
        output_dir / "threshold_exceedance_diagnostics.json",
        threshold_diagnostics,
    )
    readme_path = output_dir / "README.md"
    readme_path.write_text(
        _readme_text(
            study_id=study_id,
            run_count=len(replication_rows),
            entity_row_count=entity_row_count,
            cross_batch_status=str(cross_batch["status"]),
            threshold_diagnostics=threshold_diagnostics,
        ),
        encoding="utf-8",
        newline="\n",
    )

    output_paths = [
        output_dir / filename for filename, _, _ in outputs
    ] + [
        output_dir / "validation.json",
        output_dir / "crn_alignment.json",
        output_dir / "cross_batch_reproducibility.json",
        output_dir / "threshold_exceedance_diagnostics.json",
        readme_path,
    ]
    manifest: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "analysis": ANALYSIS_ID,
        "study_id": study_id,
        "status": "PASS",
        "analysis_role": design["analysis_role"],
        "claim_boundary": design["claim_ceiling"],
        "coverage": {
            "security_capacity_count": len(security_capacities),
            "immigration_capacity_count": len(immigration_capacities),
            "cell_count": len(cells),
            "replications_per_cell": len(REPLICATION_IDS),
            "run_count": len(replication_rows),
        },
        "paired_analysis_gate": {
            "crn_alignment_status": crn["status"],
            "comparison_method": "PAIRED_STUDENT_T",
        },
        "cross_batch_reproducibility_status": cross_batch["status"],
        "threshold_exceedance_diagnostics": {
            "role": threshold_diagnostics["role"],
            "thresholds_seconds": [
                row["threshold_seconds"]
                for row in threshold_diagnostics["thresholds"]
            ],
            "all_thresholds_zero": threshold_diagnostics[
                "all_thresholds_zero"
            ],
        },
        "queue_reconstruction": {
            "peak_window": "FULL_DRAIN",
            "time_weighted_mean_window": "[0,300)",
            "interval_semantics": (
                "[queue_join,service_start), end events before starts on ties"
            ),
        },
        "ideal_case_comparator": {
            "comparator_id": "DETERMINISTIC_IDEAL_CONTROL_V1",
            "cell_count": len(ideal_comparator),
            "arrival_process": (
                "Perfectly regular arrivals at k/lambda for positive k "
                "strictly before the cutoff"
            ),
            "service_process": (
                "Fixed service times; work-conserving pooled FCFS servers"
            ),
            "linear_quantity": "stage throughput capacity c/service_time",
            "nonlinear_quantity": (
                "delay and queue outcomes are computed, never linearly forced"
            ),
        },
        "source": {
            "raw_results_root": portable_path(results_root),
            "entity_row_count": entity_row_count,
            "entity_logs_copied_to_analysis_package": False,
            "raw_file_count": len(artifact_entries),
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
                    if any(filename == path.name for filename, _, _ in outputs)
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
        "--seed-manifest", type=Path, default=DEFAULT_SEED_MANIFEST
    )
    parser.add_argument(
        "--schema-registry", type=Path, default=DEFAULT_SCHEMA_REGISTRY
    )
    parser.add_argument(
        "--confirmatory-root",
        type=Path,
        default=DEFAULT_PRIOR_ROOTS["confirmatory_capacity"],
    )
    parser.add_argument(
        "--availability-root",
        type=Path,
        default=DEFAULT_PRIOR_ROOTS["capacity_availability"],
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
        report = package_capacity_response_surface_analysis(
            args.results_root,
            args.output_dir,
            design_path=args.design,
            scenarios_path=args.scenarios,
            seed_manifest_path=args.seed_manifest,
            schema_registry_path=args.schema_registry,
            prior_roots={
                "confirmatory_capacity": args.confirmatory_root,
                "capacity_availability": args.availability_root,
            },
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
            "errors": [str(error)],
        }
        _write_json(args.output_dir / "validation.json", failure)
        print(json.dumps(failure, indent=2, sort_keys=True))
        return 1
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
