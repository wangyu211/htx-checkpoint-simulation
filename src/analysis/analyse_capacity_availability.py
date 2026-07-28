"""Analyse and package the Part 2 capacity-availability study.

The Part 2 study asks what happens when fewer service positions are open.
Traveller waiting timestamps already contain the information needed to answer
that question without adding a new runtime logging schema:

* security waiting is ``[security_queue_join, security_start)``;
* immigration waiting is
  ``[immigration_queue_join, immigration_start)``.

The half-open convention matters.  When one wait ends at the exact instant
another starts, the ending is applied first so that a transient, impossible
extra person is not introduced into the reconstructed queue.  All means below
are time-weighted over the specified arrival window; they are not averages of
event-time snapshots.

The pure queue-reconstruction and contrast functions remain reusable.  The
file-based packaging layer is deliberately fail-closed: it accepts only the
audited 5-by-3-by-50 consolidated dataset, verifies the consolidation hashes,
emits an explicit traveller-level CRN report, and enables paired intervals
only when that report passes.  The large entity ledger is never copied into
the compact analysis package; its row count and SHA-256 digest are retained.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import shutil
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from src.analysis.analyse_operational_replications import (
    alignment_report_passes,
    independent_difference,
    one_sample_summary,
    paired_difference,
    portable_path,
)
from src.analysis.capacity_availability_design import (
    ANALYSIS_SCENARIO_IDS,
    DEFAULT_ANALYSIS_SEED_MANIFEST,
    DEFAULT_DESIGN,
)
from src.analysis.consolidate_capacity_availability_results import (
    DEFAULT_OUTPUT_DIR as DEFAULT_CONSOLIDATED_RESULTS_DIR,
    INPUT_SAMPLE_IDS,
    REPLICATION_IDS,
)
from src.analysis.validate_crn_alignment import validate_crn_alignment
from src.analysis.validate_operational_contract import REFERENCE_SCENARIO_ID
from src.analysis.validate_operational_results import (
    DEFAULT_SCHEMA_REGISTRY,
    RESULT_FILES,
    load_result_schemas,
    read_csv,
)


SECURITY = "security"
IMMIGRATION = "immigration"
STAGES = (SECURITY, IMMIGRATION)

QUEUE_TIMESTAMP_FIELDS = {
    SECURITY: (
        "security_queue_join_seconds",
        "security_start_seconds",
    ),
    IMMIGRATION: (
        "immigration_queue_join_seconds",
        "immigration_start_seconds",
    ),
}

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = (
    PROJECT_ROOT / "results" / "analysis" / "capacity_availability"
)
CONSOLIDATION_MANIFEST = "consolidation_manifest.json"
ANALYSIS_ID = "TASK3_CAPACITY_AVAILABILITY_ANALYSIS_V1"
INPUT_VALIDATION_ID = "TASK3_CAPACITY_AVAILABILITY_INPUT_VALIDATION_V1"
CRN_VALIDATION_ID = "CAPACITY_AVAILABILITY_CRN_ALIGNMENT_V1"
ANALYSIS_SCHEMA_VERSION = "1.0"
ESTIMAND = "MEAN_OF_REPLICATION_LEVEL_METRIC"
DEFAULT_CUTOFF_SECONDS = 300.0

QUEUE_ANALYSIS_FIELDS = (
    "analysis_window_start_seconds",
    "analysis_window_end_seconds",
    "peak_window_end_seconds",
    "security_positive_wait_count",
    "immigration_positive_wait_count",
    "peak_security_waiting_queue",
    "peak_immigration_waiting_queue",
    "peak_total_waiting_queue",
    "security_queue_person_seconds",
    "immigration_queue_person_seconds",
    "total_queue_person_seconds",
    "time_weighted_mean_security_waiting_queue",
    "time_weighted_mean_immigration_waiting_queue",
    "time_weighted_mean_total_waiting_queue",
)
ANALYSIS_METRICS = (
    "peak_security_waiting_queue",
    "peak_immigration_waiting_queue",
    "peak_total_waiting_queue",
    "time_weighted_mean_security_waiting_queue",
    "time_weighted_mean_immigration_waiting_queue",
    "time_weighted_mean_total_waiting_queue",
    "total_queue_wait_p95_seconds",
    "cutoff_backlog",
    "cohort_clear_time_after_cutoff_seconds",
    "security_utilization",
    "immigration_utilization",
)
ESTIMATE_FIELDS = (
    "schema_version",
    "study_id",
    "scenario_id",
    "input_sample_id",
    "metric",
    "estimand",
    "n_replications",
    "mean",
    "standard_deviation",
    "standard_error",
    "ci_level",
    "ci_low",
    "ci_high",
    "analysis_status",
)
CONTRAST_FIELDS = (
    "schema_version",
    "study_id",
    "scenario_id",
    "reference_scenario_id",
    "scenario_input_sample_id",
    "reference_input_sample_id",
    "metric",
    "difference_direction",
    "comparison_method",
    "alignment_status",
    "n_scenario",
    "n_reference",
    "difference_mean",
    "standard_error",
    "degrees_of_freedom",
    "ci_level",
    "ci_low",
    "ci_high",
    "analysis_status",
)


@dataclass(frozen=True)
class QueueInterval:
    """One positive-duration waiting interval inside the analysis window."""

    stage: str
    start_seconds: float
    end_seconds: float

    def __post_init__(self) -> None:
        if self.stage not in STAGES:
            raise ValueError(f"unsupported queue stage: {self.stage!r}")
        if not (
            math.isfinite(self.start_seconds)
            and math.isfinite(self.end_seconds)
        ):
            raise ValueError("queue interval timestamps must be finite")
        if self.end_seconds <= self.start_seconds:
            raise ValueError("queue interval must have positive duration")


def _finite_timestamp(value: object, field: str) -> float:
    """Coerce one ledger timestamp and reject blank or non-finite values."""

    if value is None or (isinstance(value, str) and not value.strip()):
        raise ValueError(f"{field} must contain a timestamp")
    try:
        timestamp = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field} must be numeric") from error
    if not math.isfinite(timestamp):
        raise ValueError(f"{field} must be finite")
    return timestamp


def _analysis_window(
    window_start_seconds: float, cutoff_seconds: float
) -> tuple[float, float]:
    start = _finite_timestamp(window_start_seconds, "window_start_seconds")
    end = _finite_timestamp(cutoff_seconds, "cutoff_seconds")
    if end <= start:
        raise ValueError("cutoff_seconds must be after window_start_seconds")
    return start, end


def extract_waiting_intervals(
    entity_rows: Iterable[Mapping[str, object]],
    *,
    cutoff_seconds: float,
    window_start_seconds: float = 0.0,
) -> list[QueueInterval]:
    """Extract and clip positive waits from traveller-level ledger rows.

    Zero-duration waits are intentionally ignored.  Negative waits indicate a
    broken event chronology and raise even when the interval would otherwise
    fall outside the requested window.
    """

    window_start, window_end = _analysis_window(
        window_start_seconds, cutoff_seconds
    )
    intervals: list[QueueInterval] = []
    for row_index, row in enumerate(entity_rows, start=1):
        for stage, (join_field, start_field) in QUEUE_TIMESTAMP_FIELDS.items():
            if join_field not in row:
                raise ValueError(
                    f"entity row {row_index} is missing {join_field}"
                )
            if start_field not in row:
                raise ValueError(
                    f"entity row {row_index} is missing {start_field}"
                )
            queue_join = _finite_timestamp(row[join_field], join_field)
            service_start = _finite_timestamp(row[start_field], start_field)
            if service_start < queue_join:
                raise ValueError(
                    f"entity row {row_index} has {start_field} before "
                    f"{join_field}"
                )
            if service_start == queue_join:
                continue

            clipped_start = max(queue_join, window_start)
            clipped_end = min(service_start, window_end)
            if clipped_end <= clipped_start:
                continue
            intervals.append(
                QueueInterval(stage, clipped_start, clipped_end)
            )
    return intervals


def queue_length_metrics_from_intervals(
    intervals: Iterable[QueueInterval],
    *,
    cutoff_seconds: float,
    window_start_seconds: float = 0.0,
) -> dict[str, float | int]:
    """Sweep interval endpoints into peak and time-weighted queue metrics.

    End events are processed before start events at equal timestamps.  Peaks
    are measured after all events at a timestamp have been applied, which is
    the queue state that exists at that instant under half-open intervals.
    """

    window_start, window_end = _analysis_window(
        window_start_seconds, cutoff_seconds
    )
    # event[time][stage] = [end_count, start_count]
    events: dict[str, dict[float, list[int]]] = {
        SECURITY: defaultdict(lambda: [0, 0]),
        IMMIGRATION: defaultdict(lambda: [0, 0]),
    }
    interval_counts = {SECURITY: 0, IMMIGRATION: 0}

    for interval in intervals:
        if interval.start_seconds < window_start:
            raise ValueError("queue interval starts before the analysis window")
        if interval.end_seconds > window_end:
            raise ValueError("queue interval ends after the analysis window")
        if interval.end_seconds <= interval.start_seconds:
            raise ValueError("queue interval must have positive duration")
        stage_events = events[interval.stage]
        stage_events[interval.start_seconds][1] += 1
        stage_events[interval.end_seconds][0] += 1
        interval_counts[interval.stage] += 1

    event_times = sorted(
        set(events[SECURITY]).union(events[IMMIGRATION])
    )
    current = {SECURITY: 0, IMMIGRATION: 0}
    peaks = {SECURITY: 0, IMMIGRATION: 0, "total": 0}
    person_seconds = {SECURITY: 0.0, IMMIGRATION: 0.0}
    previous_time = window_start

    for event_time in event_times:
        if event_time < previous_time or event_time > window_end:
            raise ValueError("queue event lies outside the analysis window")
        duration = event_time - previous_time
        person_seconds[SECURITY] += current[SECURITY] * duration
        person_seconds[IMMIGRATION] += current[IMMIGRATION] * duration

        # Half-open [join, start): remove endings before admitting starts.
        for stage in STAGES:
            end_count = events[stage][event_time][0]
            current[stage] -= end_count
            if current[stage] < 0:
                raise ValueError(
                    f"{stage} queue sweep became negative at {event_time}"
                )
        for stage in STAGES:
            start_count = events[stage][event_time][1]
            current[stage] += start_count

        peaks[SECURITY] = max(peaks[SECURITY], current[SECURITY])
        peaks[IMMIGRATION] = max(peaks[IMMIGRATION], current[IMMIGRATION])
        peaks["total"] = max(
            peaks["total"], current[SECURITY] + current[IMMIGRATION]
        )
        previous_time = event_time

    trailing_duration = window_end - previous_time
    person_seconds[SECURITY] += current[SECURITY] * trailing_duration
    person_seconds[IMMIGRATION] += current[IMMIGRATION] * trailing_duration
    if current[SECURITY] != 0 or current[IMMIGRATION] != 0:
        raise ValueError("queue intervals did not close by cutoff_seconds")

    window_duration = window_end - window_start
    total_person_seconds = (
        person_seconds[SECURITY] + person_seconds[IMMIGRATION]
    )
    return {
        "window_start_seconds": window_start,
        "cutoff_seconds": window_end,
        "window_duration_seconds": window_duration,
        "security_positive_wait_count": interval_counts[SECURITY],
        "immigration_positive_wait_count": interval_counts[IMMIGRATION],
        "max_security_queue": peaks[SECURITY],
        "max_immigration_queue": peaks[IMMIGRATION],
        "max_total_queue": peaks["total"],
        "peak_security_waiting_queue": peaks[SECURITY],
        "peak_immigration_waiting_queue": peaks[IMMIGRATION],
        "peak_total_waiting_queue": peaks["total"],
        "security_queue_person_seconds": person_seconds[SECURITY],
        "immigration_queue_person_seconds": person_seconds[IMMIGRATION],
        "total_queue_person_seconds": total_person_seconds,
        "security_queue_time_weighted_mean": (
            person_seconds[SECURITY] / window_duration
        ),
        "immigration_queue_time_weighted_mean": (
            person_seconds[IMMIGRATION] / window_duration
        ),
        "total_queue_time_weighted_mean": (
            total_person_seconds / window_duration
        ),
        "time_weighted_mean_total_waiting_queue": (
            total_person_seconds / window_duration
        ),
    }


def reconstruct_queue_length_metrics(
    entity_rows: Iterable[Mapping[str, object]],
    *,
    cutoff_seconds: float,
    window_start_seconds: float = 0.0,
) -> dict[str, float | int]:
    """Reconstruct full-drain peaks and arrival-window queue averages."""

    rows = list(entity_rows)
    window_intervals = extract_waiting_intervals(
        rows,
        cutoff_seconds=cutoff_seconds,
        window_start_seconds=window_start_seconds,
    )
    metrics = queue_length_metrics_from_intervals(
        window_intervals,
        cutoff_seconds=cutoff_seconds,
        window_start_seconds=window_start_seconds,
    )
    service_start_fields = tuple(
        start_field for _, start_field in QUEUE_TIMESTAMP_FIELDS.values()
    )
    peak_window_end = max(
        cutoff_seconds,
        *(
            _finite_timestamp(row[field], field)
            for row in rows
            for field in service_start_fields
        ),
    )
    full_intervals = extract_waiting_intervals(
        rows,
        cutoff_seconds=peak_window_end,
        window_start_seconds=window_start_seconds,
    )
    full_metrics = queue_length_metrics_from_intervals(
        full_intervals,
        cutoff_seconds=peak_window_end,
        window_start_seconds=window_start_seconds,
    )
    for field in (
        "security_positive_wait_count",
        "immigration_positive_wait_count",
        "max_security_queue",
        "max_immigration_queue",
        "max_total_queue",
        "peak_security_waiting_queue",
        "peak_immigration_waiting_queue",
        "peak_total_waiting_queue",
    ):
        metrics[field] = full_metrics[field]
    metrics["peak_window_end_seconds"] = peak_window_end
    return metrics


def _finite_replication_map(
    values: Mapping[str, float], label: str
) -> dict[str, float]:
    if len(values) < 2:
        raise ValueError(f"{label} requires at least two replications")
    finite: dict[str, float] = {}
    for replication_id, raw_value in values.items():
        value = float(raw_value)
        if not math.isfinite(value):
            raise ValueError(
                f"{label} replication {replication_id} is not finite"
            )
        finite[str(replication_id)] = value
    if len(finite) != len(values):
        raise ValueError(f"{label} has duplicate replication IDs")
    return finite


def replication_contrast_with_crn_gate(
    scenario_by_replication: Mapping[str, float],
    reference_by_replication: Mapping[str, float],
    *,
    alignment_report: Mapping[str, object] | None = None,
    same_input_sample: bool = True,
    ci_level: float = 0.95,
) -> dict[str, float | int | str]:
    """Return scenario-minus-reference contrast with an explicit CRN gate.

    A paired Student-t interval is used only when the external alignment report
    passes, both arms use the same exogenous input sample, and replication IDs
    match exactly.  Every other case safely falls back to an independent Welch
    interval.
    """

    scenario = _finite_replication_map(
        scenario_by_replication, "scenario arm"
    )
    reference = _finite_replication_map(
        reference_by_replication, "reference arm"
    )
    report_passes = alignment_report_passes(alignment_report)
    replication_ids_match = set(scenario) == set(reference)

    if same_input_sample and report_passes and replication_ids_match:
        result = paired_difference(
            scenario, reference, ci_level=ci_level
        )
        method = "PAIRED_STUDENT_T"
        alignment_status = "PASS"
    else:
        result = independent_difference(
            list(scenario.values()),
            list(reference.values()),
            ci_level=ci_level,
        )
        method = "INDEPENDENT_WELCH_T"
        if not same_input_sample:
            alignment_status = "NOT_APPLICABLE_DIFFERENT_INPUT_SAMPLE"
        elif report_passes and not replication_ids_match:
            alignment_status = "REPLICATION_ID_MISMATCH"
        else:
            alignment_status = "NOT_VERIFIED"

    return {
        **result,
        "comparison_method": method,
        "alignment_status": alignment_status,
        "difference_direction": "SCENARIO_MINUS_REFERENCE",
        "ci_level": ci_level,
    }


RunKey = tuple[str, str, int]


def _run_key(row: Mapping[str, object]) -> RunKey:
    try:
        scenario_id = str(row["scenario_id"]).strip()
        input_sample_id = str(row["input_sample_id"]).strip()
        replication_id = int(str(row["replication_id"]).strip())
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("row has an invalid run key") from error
    if not scenario_id or not input_sample_id or replication_id <= 0:
        raise ValueError("row has an invalid run key")
    return scenario_id, input_sample_id, replication_id


def _sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _expected_run_keys(
    scenario_ids: Sequence[str],
    input_sample_ids: Sequence[str],
    replication_ids: Sequence[int],
) -> set[RunKey]:
    return {
        (scenario_id, input_sample_id, replication_id)
        for scenario_id in scenario_ids
        for input_sample_id in input_sample_ids
        for replication_id in replication_ids
    }


def _index_unique_runs(
    rows: Sequence[Mapping[str, object]], label: str
) -> dict[RunKey, Mapping[str, object]]:
    indexed: dict[RunKey, Mapping[str, object]] = {}
    for row in rows:
        key = _run_key(row)
        if key in indexed:
            raise ValueError(f"{label} contains duplicate run key {key}")
        indexed[key] = row
    return indexed


def _format_run_keys(keys: Iterable[RunKey], limit: int = 5) -> str:
    ordered = sorted(keys)
    excerpt = ", ".join(repr(key) for key in ordered[:limit])
    if len(ordered) > limit:
        excerpt += f", ... ({len(ordered)} total)"
    return excerpt


def _require_exact_run_keys(
    actual: set[RunKey], expected: set[RunKey], label: str
) -> None:
    missing = expected - actual
    unexpected = actual - expected
    if missing:
        raise ValueError(
            f"{label} is missing run keys: {_format_run_keys(missing)}"
        )
    if unexpected:
        raise ValueError(
            f"{label} has unexpected run keys: "
            f"{_format_run_keys(unexpected)}"
        )


def _float_field(
    row: Mapping[str, object], field: str, *, label: str
) -> float:
    try:
        value = float(row[field])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(f"{label}: {field} must be numeric") from error
    if not math.isfinite(value):
        raise ValueError(f"{label}: {field} must be finite")
    return value


def _int_field(
    row: Mapping[str, object], field: str, *, label: str
) -> int:
    raw = _float_field(row, field, label=label)
    if not raw.is_integer():
        raise ValueError(f"{label}: {field} must be an integer")
    return int(raw)


def _is_true(value: object) -> bool:
    return str(value).strip().lower() == "true"


def _normalise_axes(
    scenario_ids: Sequence[str],
    input_sample_ids: Sequence[str],
    replication_ids: Sequence[int],
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[int, ...]]:
    scenarios = tuple(scenario_ids)
    samples = tuple(input_sample_ids)
    replications = tuple(replication_ids)
    if not scenarios or len(set(scenarios)) != len(scenarios):
        raise ValueError("scenario_ids must be non-empty and unique")
    if not samples or len(set(samples)) != len(samples):
        raise ValueError("input_sample_ids must be non-empty and unique")
    if not replications or len(set(replications)) != len(replications):
        raise ValueError("replication_ids must be non-empty and unique")
    if any(not value for value in scenarios + samples):
        raise ValueError("scenario and input-sample IDs must be non-empty")
    if any(
        isinstance(value, bool)
        or not isinstance(value, int)
        or value <= 0
        for value in replications
    ):
        raise ValueError("replication IDs must be positive integers")
    return scenarios, samples, replications


def _load_json_mapping(path: Path, label: str) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} is unavailable or invalid: {path}") from error
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must contain a JSON object")
    return payload


def _validate_consolidation_manifest(
    manifest: Mapping[str, object],
    *,
    results_dir: Path,
    row_counts: Mapping[str, int],
    expected_run_count: int,
    expected_scenario_count: int,
    expected_input_sample_count: int,
    expected_replications_per_cell: int,
) -> None:
    if manifest.get("status") != "PASS":
        raise ValueError("consolidation manifest status must be PASS")
    if manifest.get("lineage_status") != "PASS":
        raise ValueError("consolidation lineage_status must be PASS")
    if manifest.get("cross_scenario_seed_lineage_status") != "PASS":
        raise ValueError(
            "consolidation cross_scenario_seed_lineage_status must be PASS"
        )
    coverage = manifest.get("coverage")
    if not isinstance(coverage, Mapping):
        raise ValueError("consolidation manifest coverage is missing")
    required_coverage = {
        "analysis_run_count": expected_run_count,
        "scenario_count": expected_scenario_count,
        "input_sample_count": expected_input_sample_count,
        "replications_per_cell": expected_replications_per_cell,
        "coverage_status": "PASS",
    }
    for field, expected in required_coverage.items():
        if coverage.get(field) != expected:
            raise ValueError(
                f"consolidation coverage {field} must be {expected!r}"
            )

    outputs = manifest.get("outputs")
    if not isinstance(outputs, Mapping):
        raise ValueError("consolidation manifest outputs are missing")
    for filename in RESULT_FILES.values():
        metadata = outputs.get(filename)
        if not isinstance(metadata, Mapping):
            raise ValueError(
                f"consolidation manifest does not track {filename}"
            )
        path = results_dir / filename
        expected_hash = metadata.get("sha256")
        actual_hash = _sha256(path)
        if not expected_hash or actual_hash != expected_hash:
            raise ValueError(
                f"{filename} SHA-256 does not match consolidation manifest"
            )
        if metadata.get("row_count") != row_counts[filename]:
            raise ValueError(
                f"{filename} row count does not match consolidation manifest"
            )


def _load_and_validate_consolidated_inputs(
    results_dir: Path,
    *,
    schema_registry_path: Path,
    scenario_ids: Sequence[str],
    input_sample_ids: Sequence[str],
    replication_ids: Sequence[int],
    cutoff_seconds: float,
) -> tuple[
    dict[str, object],
    list[dict[str, str]],
    list[dict[str, str]],
    list[dict[str, str]],
]:
    scenarios, samples, replications = _normalise_axes(
        scenario_ids, input_sample_ids, replication_ids
    )
    if not math.isfinite(cutoff_seconds) or cutoff_seconds <= 0:
        raise ValueError("cutoff_seconds must be positive and finite")

    schemas = load_result_schemas(schema_registry_path)
    tables: dict[str, list[dict[str, str]]] = {}
    row_counts: dict[str, int] = {}
    artifact_hashes: dict[str, str | None] = {}
    for table, filename in RESULT_FILES.items():
        path = results_dir / filename
        expected_fields = [
            str(item["field_name"]) for item in schemas[table]
        ]
        actual_fields, rows = read_csv(path)
        if actual_fields != expected_fields:
            raise ValueError(
                f"{filename} schema mismatch; expected {expected_fields}, "
                f"found {actual_fields}"
            )
        tables[table] = rows
        row_counts[filename] = len(rows)
        artifact_hashes[f"{table}_sha256"] = _sha256(path)

    expected_keys = _expected_run_keys(scenarios, samples, replications)
    manifests = _index_unique_runs(tables["run_manifest"], "run_manifest.csv")
    kpis = _index_unique_runs(
        tables["replication_kpis"], "replication_kpis.csv"
    )
    _require_exact_run_keys(
        set(manifests), expected_keys, "run_manifest.csv"
    )
    _require_exact_run_keys(
        set(kpis), expected_keys, "replication_kpis.csv"
    )

    entity_counts: dict[RunKey, int] = defaultdict(int)
    seen_entities: set[tuple[RunKey, str]] = set()
    lineage_fields = ("config_id", "config_sha256", "model_version")
    for line, row in enumerate(tables["entity_log"], start=2):
        key = _run_key(row)
        if key not in expected_keys:
            raise ValueError(
                f"entity_log.csv:{line} has unexpected run key {key}"
            )
        traveller_id = row.get("traveller_id", "").strip()
        if not traveller_id:
            raise ValueError(
                f"entity_log.csv:{line} has an empty traveller_id"
            )
        entity_key = (key, traveller_id)
        if entity_key in seen_entities:
            raise ValueError(
                f"entity_log.csv:{line} duplicates traveller {entity_key}"
            )
        seen_entities.add(entity_key)
        entity_counts[key] += 1
        manifest_row = manifests[key]
        for field in lineage_fields:
            if row.get(field) != manifest_row.get(field):
                raise ValueError(
                    f"entity_log.csv:{line} {field} differs from manifest"
                )

    for key in sorted(expected_keys):
        manifest_row = manifests[key]
        kpi_row = kpis[key]
        for field in lineage_fields:
            if kpi_row.get(field) != manifest_row.get(field):
                raise ValueError(
                    f"replication_kpis.csv {key} {field} differs from manifest"
                )
        if manifest_row.get("run_status") != "COMPLETE":
            raise ValueError(f"run_manifest.csv {key} is not COMPLETE")
        if kpi_row.get("run_status") != "COMPLETE":
            raise ValueError(f"replication_kpis.csv {key} is not COMPLETE")
        if not _is_true(kpi_row.get("conservation_pass")):
            raise ValueError(
                f"replication_kpis.csv {key} failed conservation"
            )
        manifest_cutoff = _float_field(
            manifest_row,
            "arrival_cutoff_seconds",
            label=f"run_manifest.csv {key}",
        )
        kpi_cutoff = _float_field(
            kpi_row,
            "arrival_cutoff_seconds",
            label=f"replication_kpis.csv {key}",
        )
        if not math.isclose(
            manifest_cutoff,
            cutoff_seconds,
            rel_tol=0.0,
            abs_tol=1e-9,
        ) or not math.isclose(
            kpi_cutoff,
            cutoff_seconds,
            rel_tol=0.0,
            abs_tol=1e-9,
        ):
            raise ValueError(
                f"{key} does not use the registered {cutoff_seconds:g}s cutoff"
            )
        arrivals = _int_field(
            kpi_row, "arrivals", label=f"replication_kpis.csv {key}"
        )
        completed_after_drain = _int_field(
            kpi_row,
            "completed_after_drain",
            label=f"replication_kpis.csv {key}",
        )
        rejected_or_dropped = _int_field(
            kpi_row,
            "rejected_or_dropped_count",
            label=f"replication_kpis.csv {key}",
        )
        if rejected_or_dropped != 0:
            raise ValueError(
                f"replication_kpis.csv {key} has rejection/drop count "
                f"{rejected_or_dropped}"
            )
        if completed_after_drain != arrivals:
            raise ValueError(
                f"replication_kpis.csv {key} did not fully drain "
                f"({completed_after_drain}/{arrivals})"
            )
        if entity_counts[key] != arrivals:
            raise ValueError(
                f"{key} has {entity_counts[key]} entity rows but "
                f"{arrivals} admitted arrivals"
            )

    manifest_path = results_dir / CONSOLIDATION_MANIFEST
    consolidation = _load_json_mapping(
        manifest_path, "consolidation manifest"
    )
    row_counts[CONSOLIDATION_MANIFEST] = 1
    artifact_hashes["consolidation_manifest_sha256"] = _sha256(manifest_path)
    _validate_consolidation_manifest(
        consolidation,
        results_dir=results_dir,
        row_counts=row_counts,
        expected_run_count=len(expected_keys),
        expected_scenario_count=len(scenarios),
        expected_input_sample_count=len(samples),
        expected_replications_per_cell=len(replications),
    )

    validation: dict[str, object] = {
        "schema_version": ANALYSIS_SCHEMA_VERSION,
        "validation": INPUT_VALIDATION_ID,
        "status": "PASS",
        "coverage_pass": True,
        "consolidation_manifest_status": "PASS",
        "lineage_status": "PASS",
        "conservation_status": "PASS",
        "arrival_cutoff_seconds": cutoff_seconds,
        "scenario_count": len(scenarios),
        "input_sample_count": len(samples),
        "replications_per_cell": len(replications),
        "expected_run_count": len(expected_keys),
        "actual_run_count": len(manifests),
        "entity_row_count": len(tables["entity_log"]),
        "row_counts": row_counts,
        "artifact_hashes": artifact_hashes,
        "errors": [],
    }
    return (
        validation,
        tables["run_manifest"],
        tables["replication_kpis"],
        tables["entity_log"],
    )


def validate_capacity_availability_inputs(
    results_dir: Path = DEFAULT_CONSOLIDATED_RESULTS_DIR,
    *,
    schema_registry_path: Path = DEFAULT_SCHEMA_REGISTRY,
    scenario_ids: Sequence[str] = ANALYSIS_SCENARIO_IDS,
    input_sample_ids: Sequence[str] = INPUT_SAMPLE_IDS,
    replication_ids: Sequence[int] = REPLICATION_IDS,
    cutoff_seconds: float = DEFAULT_CUTOFF_SECONDS,
) -> dict[str, object]:
    """Validate the audited consolidated input before any statistical claim."""

    validation, _, _, _ = _load_and_validate_consolidated_inputs(
        results_dir.resolve(),
        schema_registry_path=schema_registry_path.resolve(),
        scenario_ids=scenario_ids,
        input_sample_ids=input_sample_ids,
        replication_ids=replication_ids,
        cutoff_seconds=cutoff_seconds,
    )
    return validation


def build_availability_by_replication(
    kpi_rows: Sequence[Mapping[str, object]],
    entity_rows: Sequence[Mapping[str, object]],
    *,
    cutoff_seconds: float = DEFAULT_CUTOFF_SECONDS,
    window_start_seconds: float = 0.0,
    expected_run_keys: set[RunKey] | None = None,
    scenario_order: Sequence[str] | None = None,
    input_sample_order: Sequence[str] | None = None,
) -> list[dict[str, object]]:
    """Merge canonical KPIs with reconstructed queue metrics for every run."""

    kpis = _index_unique_runs(kpi_rows, "replication KPI rows")
    if expected_run_keys is not None:
        _require_exact_run_keys(
            set(kpis), expected_run_keys, "replication KPI rows"
        )
    entities_by_run: dict[RunKey, list[Mapping[str, object]]] = defaultdict(list)
    seen_entities: set[tuple[RunKey, str]] = set()
    for row in entity_rows:
        key = _run_key(row)
        if key not in kpis:
            raise ValueError(f"entity row has no matching KPI run {key}")
        traveller_id = str(row.get("traveller_id", "")).strip()
        if traveller_id:
            entity_key = (key, traveller_id)
            if entity_key in seen_entities:
                raise ValueError(f"duplicate traveller row {entity_key}")
            seen_entities.add(entity_key)
        entities_by_run[key].append(row)
    missing_entity_runs = set(kpis) - set(entities_by_run)
    if missing_entity_runs:
        raise ValueError(
            "entity rows are missing runs: "
            f"{_format_run_keys(missing_entity_runs)}"
        )

    scenario_rank = {
        value: index for index, value in enumerate(scenario_order or ())
    }
    sample_rank = {
        value: index for index, value in enumerate(input_sample_order or ())
    }

    def sort_key(key: RunKey) -> tuple[int, str, int, str, int]:
        scenario_id, input_sample_id, replication_id = key
        return (
            scenario_rank.get(scenario_id, len(scenario_rank)),
            scenario_id,
            sample_rank.get(input_sample_id, len(sample_rank)),
            input_sample_id,
            replication_id,
        )

    rows: list[dict[str, object]] = []
    for key in sorted(kpis, key=sort_key):
        reconstructed = reconstruct_queue_length_metrics(
            entities_by_run[key],
            cutoff_seconds=cutoff_seconds,
            window_start_seconds=window_start_seconds,
        )
        row: dict[str, object] = dict(kpis[key])
        row.update(
            {
                "analysis_window_start_seconds": reconstructed[
                    "window_start_seconds"
                ],
                "analysis_window_end_seconds": reconstructed[
                    "cutoff_seconds"
                ],
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
            }
        )
        rows.append(row)
    return rows


def capacity_availability_alignment_report_passes(
    report: object,
    *,
    study_id: str | None = None,
    design_path: Path | None = None,
    seed_manifest_path: Path | None = None,
    results_dir: Path | None = None,
) -> bool:
    """Require a complete, study-specific and optionally current CRN PASS."""

    if not alignment_report_passes(report) or not isinstance(report, Mapping):
        return False
    if (
        report.get("validation") != CRN_VALIDATION_ID
        or report.get("coverage_pass") is not True
        or report.get("seed_alignment_pass") is not True
        or report.get("errors") != []
        or report.get("expected_run_key_sha256")
        != report.get("actual_run_key_sha256")
    ):
        return False
    if study_id is not None and report.get("study_id") != study_id:
        return False
    if any(
        value is not None
        for value in (design_path, seed_manifest_path, results_dir)
    ):
        if (
            design_path is None
            or seed_manifest_path is None
            or results_dir is None
        ):
            raise ValueError(
                "design, seed manifest and results dir must be supplied together"
            )
        expected_hashes = {
            "design_sha256": _sha256(design_path),
            "seed_manifest_sha256": _sha256(seed_manifest_path),
            "run_manifest_sha256": _sha256(
                results_dir / RESULT_FILES["run_manifest"]
            ),
            "entity_log_sha256": _sha256(
                results_dir / RESULT_FILES["entity_log"]
            ),
        }
        if report.get("artifact_hashes") != expected_hashes:
            return False
    return True


def _finite_metric_values(
    rows: Sequence[Mapping[str, object]], field: str
) -> list[float]:
    values = [
        _float_field(row, field, label=f"analysis metric {field}")
        for row in rows
    ]
    if len(values) < 2:
        raise ValueError(f"{field} requires at least two replications")
    return values


def build_capacity_availability_analysis(
    rows: Sequence[Mapping[str, object]],
    design: Mapping[str, object],
    *,
    alignment_report: Mapping[str, object] | None,
    alignment_verified: bool | None = None,
    scenario_ids: Sequence[str] = ANALYSIS_SCENARIO_IDS,
    input_sample_ids: Sequence[str] = INPUT_SAMPLE_IDS,
    replication_ids: Sequence[int] = REPLICATION_IDS,
    metrics: Sequence[str] = ANALYSIS_METRICS,
) -> dict[str, object]:
    """Build estimates, reference contrasts and the registered primary result."""

    scenarios, samples, replications = _normalise_axes(
        scenario_ids, input_sample_ids, replication_ids
    )
    expected_keys = _expected_run_keys(scenarios, samples, replications)
    indexed = _index_unique_runs(rows, "availability rows")
    _require_exact_run_keys(set(indexed), expected_keys, "availability rows")
    study_id = str(design["study_id"])
    ci_level = float(
        design["primary_analysis"]["confidence_level"]  # type: ignore[index]
    )
    if alignment_verified is None:
        alignment_verified = capacity_availability_alignment_report_passes(
            alignment_report, study_id=study_id
        )
    effective_alignment_report = (
        alignment_report if alignment_verified else None
    )

    grouped: dict[
        tuple[str, str], list[Mapping[str, object]]
    ] = defaultdict(list)
    for row in rows:
        grouped[(str(row["scenario_id"]), str(row["input_sample_id"]))].append(
            row
        )
    for group in grouped.values():
        group.sort(key=lambda row: int(str(row["replication_id"])))

    metric_names = tuple(metrics)
    if not metric_names or len(set(metric_names)) != len(metric_names):
        raise ValueError("metrics must be non-empty and unique")

    estimates: list[dict[str, object]] = []
    for scenario_id in scenarios:
        for input_sample_id in samples:
            group = grouped[(scenario_id, input_sample_id)]
            for metric in metric_names:
                summary = one_sample_summary(
                    _finite_metric_values(group, metric),
                    ci_level=ci_level,
                )
                estimates.append(
                    {
                        "schema_version": ANALYSIS_SCHEMA_VERSION,
                        "study_id": study_id,
                        "scenario_id": scenario_id,
                        "input_sample_id": input_sample_id,
                        "metric": metric,
                        "estimand": ESTIMAND,
                        "n_replications": summary["n"],
                        "mean": summary["mean"],
                        "standard_deviation": summary[
                            "standard_deviation"
                        ],
                        "standard_error": summary["standard_error"],
                        "ci_level": ci_level,
                        "ci_low": summary["ci_low"],
                        "ci_high": summary["ci_high"],
                        "analysis_status": "COMPLETE",
                    }
                )

    primary_spec = design["primary_analysis"]  # type: ignore[index]
    reference_scenario_id = str(primary_spec["reference_scenario_id"])
    if reference_scenario_id not in scenarios:
        raise ValueError("registered reference scenario is absent")
    contrasts: list[dict[str, object]] = []
    for scenario_id in scenarios:
        if scenario_id == reference_scenario_id:
            continue
        for input_sample_id in samples:
            scenario_group = grouped[(scenario_id, input_sample_id)]
            reference_group = grouped[
                (reference_scenario_id, input_sample_id)
            ]
            for metric in metric_names:
                comparison = replication_contrast_with_crn_gate(
                    {
                        str(row["replication_id"]): _float_field(
                            row, metric, label=f"{scenario_id}/{metric}"
                        )
                        for row in scenario_group
                    },
                    {
                        str(row["replication_id"]): _float_field(
                            row,
                            metric,
                            label=f"{reference_scenario_id}/{metric}",
                        )
                        for row in reference_group
                    },
                    alignment_report=effective_alignment_report,
                    same_input_sample=True,
                    ci_level=ci_level,
                )
                contrasts.append(
                    {
                        "schema_version": ANALYSIS_SCHEMA_VERSION,
                        "study_id": study_id,
                        "scenario_id": scenario_id,
                        "reference_scenario_id": reference_scenario_id,
                        "scenario_input_sample_id": input_sample_id,
                        "reference_input_sample_id": input_sample_id,
                        "metric": metric,
                        **comparison,
                        "analysis_status": "COMPLETE",
                    }
                )

    level_to_sample = {
        str(level["level_id"]): str(level["input_sample_id"])
        for level in design["arrival_rate_uncertainty"]["levels"]  # type: ignore[index]
    }
    primary_sample = level_to_sample[str(primary_spec["input_level_id"])]
    primary_scenario = str(primary_spec["scenario_id"])
    primary_metric = str(primary_spec["metric"])
    try:
        primary_contrast = next(
            row
            for row in contrasts
            if row["scenario_id"] == primary_scenario
            and row["scenario_input_sample_id"] == primary_sample
            and row["metric"] == primary_metric
        )
    except StopIteration as error:
        raise ValueError("registered primary contrast was not constructed") from error
    primary: dict[str, object] = {
        "schema_version": ANALYSIS_SCHEMA_VERSION,
        "study_id": study_id,
        "analysis": ANALYSIS_ID,
        "scenario_id": primary_scenario,
        "reference_scenario_id": reference_scenario_id,
        "input_level_id": primary_spec["input_level_id"],
        "input_sample_id": primary_sample,
        "metric": primary_metric,
        "metric_unit": "travellers",
        "estimand": primary_spec["estimand"],
        "difference_direction": "SCENARIO_MINUS_REFERENCE",
        "comparison_method": primary_contrast["comparison_method"],
        "alignment_status": primary_contrast["alignment_status"],
        "n_scenario": primary_contrast["n_scenario"],
        "n_reference": primary_contrast["n_reference"],
        "difference_mean": primary_contrast["difference_mean"],
        "standard_error": primary_contrast["standard_error"],
        "degrees_of_freedom": primary_contrast["degrees_of_freedom"],
        "ci_level": primary_contrast["ci_level"],
        "ci_low": primary_contrast["ci_low"],
        "ci_high": primary_contrast["ci_high"],
        "difference_mean_travellers": primary_contrast["difference_mean"],
        "ci_low_travellers": primary_contrast["ci_low"],
        "ci_high_travellers": primary_contrast["ci_high"],
        "analysis_status": "COMPLETE",
        "claim_boundary": design["claim_ceiling"],
    }
    return {
        "estimates": estimates,
        "contrasts": contrasts,
        "primary": primary,
        "comparison_method": primary["comparison_method"],
        "alignment_verified": alignment_verified,
    }


def _write_json(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


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


def _atomic_copy(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    shutil.copyfile(source, temporary)
    temporary.replace(destination)


def _readme_text(
    primary: Mapping[str, object],
    *,
    entity_row_count: int,
    entity_sha256: str | None,
) -> str:
    difference = float(primary["difference_mean"])
    low = float(primary["ci_low"])
    high = float(primary["ci_high"])
    return (
        "# Capacity-availability analysis\n\n"
        "Part 2 quantifies what happens when fewer service positions are "
        "concurrently open. It is separate from the immutable Part 1 "
        "capacity-expansion experiment.\n\n"
        "## Registered primary result\n\n"
        f"At the base arrival-rate input, 32 Security / 18 Immigration "
        f"positions minus the 36 / 21 reference changed the mean "
        f"replication-level peak total waiting queue by {difference:.3f} "
        f"travellers (95% CI {low:.3f} to {high:.3f}; "
        f"{primary['comparison_method']}).\n\n"
        "Queue lengths are reconstructed from half-open traveller waiting "
        "intervals. Peak queues use the full-drain run; time-weighted means "
        "use the [0, 300) arrival window. Estimates are based on replications, "
        "not pooled travellers. Paired intervals are used only after the "
        "included CRN alignment report passes; otherwise contrasts use Welch "
        "intervals.\n\n"
        "The source entity ledger is intentionally not copied into this "
        f"compact package (rows: {entity_row_count}; SHA-256: "
        f"`{entity_sha256}`). These are conditional what-if results, not an "
        "observed HTX roster, calibrated site forecast, or staffing "
        "recommendation.\n"
    )


def package_capacity_availability_analysis(
    results_dir: Path = DEFAULT_CONSOLIDATED_RESULTS_DIR,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    *,
    design_path: Path = DEFAULT_DESIGN,
    seed_manifest_path: Path = DEFAULT_ANALYSIS_SEED_MANIFEST,
    schema_registry_path: Path = DEFAULT_SCHEMA_REGISTRY,
    scenario_ids: Sequence[str] = ANALYSIS_SCENARIO_IDS,
    input_sample_ids: Sequence[str] = INPUT_SAMPLE_IDS,
    replication_ids: Sequence[int] = REPLICATION_IDS,
    cutoff_seconds: float = DEFAULT_CUTOFF_SECONDS,
) -> dict[str, object]:
    """Validate, analyse and write the compact Part 2 evidence package."""

    results_dir = results_dir.resolve()
    output_dir = output_dir.resolve()
    design_path = design_path.resolve()
    seed_manifest_path = seed_manifest_path.resolve()
    schema_registry_path = schema_registry_path.resolve()
    scenarios, samples, replications = _normalise_axes(
        scenario_ids, input_sample_ids, replication_ids
    )
    validation, run_rows, kpi_rows, entity_rows = (
        _load_and_validate_consolidated_inputs(
            results_dir,
            schema_registry_path=schema_registry_path,
            scenario_ids=scenarios,
            input_sample_ids=samples,
            replication_ids=replications,
            cutoff_seconds=cutoff_seconds,
        )
    )
    design = _load_json_mapping(design_path, "capacity-availability design")
    if design.get("study_id") != "TASK3_CAPACITY_AVAILABILITY_STRESS_V1":
        raise ValueError("unexpected capacity-availability study_id")

    alignment = validate_crn_alignment(
        results_dir,
        seed_manifest_path,
        design_path=design_path,
        validation_id=CRN_VALIDATION_ID,
    )
    alignment_verified = capacity_availability_alignment_report_passes(
        alignment,
        study_id=str(design["study_id"]),
        design_path=design_path,
        seed_manifest_path=seed_manifest_path,
        results_dir=results_dir,
    )
    expected_keys = _expected_run_keys(scenarios, samples, replications)
    by_replication = build_availability_by_replication(
        kpi_rows,
        entity_rows,
        cutoff_seconds=cutoff_seconds,
        expected_run_keys=expected_keys,
        scenario_order=scenarios,
        input_sample_order=samples,
    )
    analysis = build_capacity_availability_analysis(
        by_replication,
        design,
        alignment_report=alignment,
        alignment_verified=alignment_verified,
        scenario_ids=scenarios,
        input_sample_ids=samples,
        replication_ids=replications,
    )

    schemas = load_result_schemas(schema_registry_path)
    kpi_fields = [
        str(item["field_name"]) for item in schemas["replication_kpis"]
    ]
    by_replication_path = output_dir / "availability_by_replication.csv"
    estimates_path = output_dir / "availability_estimates.csv"
    contrasts_path = output_dir / "availability_contrasts.csv"
    primary_path = output_dir / "primary_result.json"
    validation_path = output_dir / "validation.json"
    alignment_path = output_dir / "crn_alignment.json"
    readme_path = output_dir / "README.md"
    audit_manifest_path = output_dir / RESULT_FILES["run_manifest"]
    audit_kpis_path = output_dir / RESULT_FILES["replication_kpis"]

    _write_csv(
        by_replication_path,
        by_replication,
        (*kpi_fields, *QUEUE_ANALYSIS_FIELDS),
    )
    _write_csv(
        estimates_path,
        analysis["estimates"],  # type: ignore[arg-type]
        ESTIMATE_FIELDS,
    )
    _write_csv(
        contrasts_path,
        analysis["contrasts"],  # type: ignore[arg-type]
        CONTRAST_FIELDS,
    )
    _write_json(primary_path, analysis["primary"])  # type: ignore[arg-type]
    _write_json(validation_path, validation)
    _write_json(alignment_path, alignment)
    _atomic_copy(
        results_dir / RESULT_FILES["run_manifest"], audit_manifest_path
    )
    _atomic_copy(
        results_dir / RESULT_FILES["replication_kpis"], audit_kpis_path
    )
    entity_log_path = results_dir / RESULT_FILES["entity_log"]
    entity_sha256 = _sha256(entity_log_path)
    readme_path.write_text(
        _readme_text(
            analysis["primary"],  # type: ignore[arg-type]
            entity_row_count=len(entity_rows),
            entity_sha256=entity_sha256,
        ),
        encoding="utf-8",
        newline="\n",
    )

    output_paths = (
        by_replication_path,
        estimates_path,
        contrasts_path,
        primary_path,
        validation_path,
        alignment_path,
        readme_path,
        audit_manifest_path,
        audit_kpis_path,
    )
    output_metadata = {
        path.name: {
            "path": portable_path(path),
            "sha256": _sha256(path),
            "row_count": (
                len(by_replication)
                if path == by_replication_path
                else len(analysis["estimates"])
                if path == estimates_path
                else len(analysis["contrasts"])
                if path == contrasts_path
                else len(run_rows)
                if path == audit_manifest_path
                else len(kpi_rows)
                if path == audit_kpis_path
                else 1
            ),
        }
        for path in output_paths
    }
    report: dict[str, object] = {
        "schema_version": ANALYSIS_SCHEMA_VERSION,
        "analysis": ANALYSIS_ID,
        "study_id": design["study_id"],
        "status": "PASS",
        "validation_status": validation["status"],
        "consolidation_manifest_status": "PASS",
        "crn_alignment_status": alignment["status"],
        "alignment_verified_for_pairing": alignment_verified,
        "comparison_method": analysis["comparison_method"],
        "welch_fallback_reason": (
            None
            if alignment_verified
            else "Explicit current traveller-level CRN report did not PASS"
        ),
        "coverage": {
            "scenario_count": len(scenarios),
            "input_sample_count": len(samples),
            "replications_per_cell": len(replications),
            "run_count": len(expected_keys),
        },
        "queue_reconstruction": {
            "peak_window": "FULL_DRAIN",
            "time_weighted_mean_window": "[0,300)",
            "interval_semantics": (
                "[queue_join,service_start), end events before starts on ties"
            ),
            "replication_rows": len(by_replication),
        },
        "primary": analysis["primary"],
        "outputs": output_metadata,
        "source_entity_log": {
            "path": portable_path(entity_log_path),
            "copied_to_analysis_package": False,
            "row_count": len(entity_rows),
            "sha256": entity_sha256,
        },
        "input_artifact_hashes": validation["artifact_hashes"],
        "claim_boundary": design["claim_ceiling"],
    }
    _write_json(output_dir / "analysis_manifest.json", report)
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--results-dir",
        type=Path,
        default=DEFAULT_CONSOLIDATED_RESULTS_DIR,
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--design", type=Path, default=DEFAULT_DESIGN)
    parser.add_argument(
        "--seed-manifest",
        type=Path,
        default=DEFAULT_ANALYSIS_SEED_MANIFEST,
    )
    parser.add_argument(
        "--schema-registry",
        type=Path,
        default=DEFAULT_SCHEMA_REGISTRY,
    )
    parser.add_argument(
        "--cutoff-seconds",
        type=float,
        default=DEFAULT_CUTOFF_SECONDS,
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = package_capacity_availability_analysis(
            args.results_dir,
            args.output_dir,
            design_path=args.design,
            seed_manifest_path=args.seed_manifest,
            schema_registry_path=args.schema_registry,
            cutoff_seconds=args.cutoff_seconds,
        )
    except (FileNotFoundError, KeyError, TypeError, ValueError) as error:
        failure = {
            "schema_version": ANALYSIS_SCHEMA_VERSION,
            "validation": INPUT_VALIDATION_ID,
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
