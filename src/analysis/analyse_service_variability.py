"""Validate and analyse the frozen service-variability sensitivity study.

This module is an analysis contract for a future 9-by-50 AnyLogic batch.  It
does not imply that the runtime sampler has been implemented or that the
batch has been run.  When raw results become available, the package step
fails closed unless all 450 registered runs are present exactly once and
their schemas, lineage, extended configuration hashes, model version, seeds,
full-drain identities, service-demand contracts, and guard/drop checks pass.

Common-random-number (CRN) validation is stricter than checking seed labels:

* traveller IDs, arrivals, routing draws, and tie draws must match exactly
  across all nine cells within a replication;
* fixed-service demands must equal the registered arithmetic means;
* positive-CV demands must be finite and strictly positive; and
* within each stage, inverse-transformed latent standard-normal values must
  align across every positive-CV cell.

Cell estimates are descriptive.  Paired contrasts and factorial interactions
are released only after the CRN report explicitly returns ``PASS``.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Mapping, Sequence

from src.analysis.analyse_capacity_availability import (
    QUEUE_ANALYSIS_FIELDS,
    reconstruct_queue_length_metrics,
)
from src.analysis.analyse_capacity_response_surface import (
    _boolean,
    _float,
    _integer,
    _load_table,
    _require_one,
    _same_number,
    _sha256,
    _tree_digest,
    _validate_entity_chronology,
    _write_csv,
    _write_json,
)
from src.analysis.analyse_operational_replications import (
    one_sample_summary,
    portable_path,
)
from src.analysis.service_variability_design import (
    DEFAULT_DESIGN,
    DEFAULT_SCENARIOS,
    DEFAULT_SEED_MANIFEST,
    INPUT_SAMPLE_ID,
    MODEL_VERSION,
    REFERENCE_SCENARIO_ID,
    REPLICATION_IDS,
    SERVICE_SCENARIO_COLUMNS,
    STUDY_ID,
    load_design,
    load_service_variability_scenario_rows,
    load_service_variability_seed_rows,
    service_scenario_config_sha256,
    service_variability_scenario_id,
    study_cells,
    validate_service_variability_design,
)
from src.analysis.validate_crn_alignment import STREAM_SEED_FIELDS
from src.analysis.validate_operational_results import (
    DEFAULT_SCHEMA_REGISTRY,
    RESULT_FILES,
    load_result_schemas,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RESULTS_ROOT = (
    PROJECT_ROOT / "results" / "raw" / "service_variability"
)
DEFAULT_OUTPUT_DIR = (
    PROJECT_ROOT / "results" / "analysis" / "service_variability"
)

SCHEMA_VERSION = "1.0"
ANALYSIS_ID = "TASK3_SERVICE_VARIABILITY_ANALYSIS_V1"
VALIDATION_ID = "TASK3_SERVICE_VARIABILITY_INPUT_VALIDATION_V1"
CRN_VALIDATION_ID = "TASK3_SERVICE_VARIABILITY_CRN_ALIGNMENT_V1"
RAW_AUDIT_ID = "TASK3_SERVICE_VARIABILITY_RAW_AUDIT_V1"
DEFAULT_CI_LEVEL = 0.95
DEFAULT_NUMERIC_TOLERANCE = 1e-9
DEFAULT_LATENT_TOLERANCE = 1e-8
REFERENCE_CELL = (0.0, 0.0)

Cell = tuple[float, float]
RunKey = tuple[Cell, int]

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
INVARIANT_DRAW_FIELDS = (
    "arrival_seconds",
    "automation_u",
    "additional_check_u",
    "lane_tie_u",
)

ANALYSIS_METRICS = (
    "total_queue_wait_p95_seconds",
    "total_queue_wait_mean_seconds",
    "security_wait_p95_seconds",
    "immigration_wait_p95_seconds",
    "peak_security_waiting_queue",
    "peak_immigration_waiting_queue",
    "peak_total_waiting_queue",
    "time_weighted_mean_security_waiting_queue",
    "time_weighted_mean_immigration_waiting_queue",
    "time_weighted_mean_total_waiting_queue",
    "system_time_p95_seconds",
    "system_time_p99_seconds",
    "system_time_max_seconds",
    "cutoff_backlog",
    "cohort_clear_time_after_cutoff_seconds",
)
PRIMARY_METRIC = "total_queue_wait_p95_seconds"

REPLICATION_FIELDS = (
    "schema_version",
    "study_id",
    "scenario_id",
    "input_sample_id",
    "replication_id",
    "security_service_cv",
    "immigration_service_cv",
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
    "security_wait_p95_seconds",
    "immigration_wait_p95_seconds",
    "system_time_p95_seconds",
    "system_time_p99_seconds",
    "system_time_max_seconds",
    "cutoff_backlog",
    "cohort_clear_time_after_cutoff_seconds",
    "security_utilization",
    "immigration_utilization",
    *QUEUE_ANALYSIS_FIELDS,
)
ESTIMATE_FIELDS = (
    "schema_version",
    "study_id",
    "security_service_cv",
    "immigration_service_cv",
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
CONTRAST_FIELDS = (
    "schema_version",
    "study_id",
    "security_service_cv",
    "immigration_service_cv",
    "scenario_id",
    "reference_scenario_id",
    "metric",
    "difference_direction",
    "comparison_method",
    "n_pairs",
    "difference_mean",
    "standard_deviation",
    "standard_error",
    "degrees_of_freedom",
    "ci_level",
    "ci_low",
    "ci_high",
    "crn_alignment_status",
    "analysis_role",
)
INTERACTION_FIELDS = (
    "schema_version",
    "study_id",
    "security_service_cv",
    "immigration_service_cv",
    "joint_scenario_id",
    "security_only_scenario_id",
    "immigration_only_scenario_id",
    "reference_scenario_id",
    "metric",
    "contrast",
    "n_pairs",
    "interaction_mean",
    "standard_deviation",
    "standard_error",
    "degrees_of_freedom",
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
    "security_service_cv",
    "immigration_service_cv",
    "scenario_id",
    "metric",
    "n_replications",
    "mean",
    "standard_error",
    "ci_level",
    "ci_low",
    "ci_high",
)


def _canonical_numeric(value: object, label: str) -> str:
    number = _float(value, label)
    return number.hex()


def _nearest_rank(values: Sequence[float], probability: float) -> float:
    if not 0 < probability <= 1:
        raise ValueError("nearest-rank probability must be in (0,1]")
    if not values:
        raise ValueError("nearest-rank statistic requires observations")
    ordered = sorted(values)
    return ordered[max(0, math.ceil(probability * len(ordered)) - 1)]


def _cell_from_row(row: Mapping[str, str]) -> Cell:
    return (
        _float(row["security_service_cv"], "security_service_cv"),
        _float(row["immigration_service_cv"], "immigration_service_cv"),
    )


def _run_directory(
    root: Path,
    cell: Cell,
    replication_id: int,
) -> Path:
    return (
        root
        / service_variability_scenario_id(*cell)
        / INPUT_SAMPLE_ID
        / f"replication_{replication_id:03d}"
    )


def _expected_run_paths(
    root: Path,
    cells: Sequence[Cell],
    replication_ids: Sequence[int],
) -> dict[Path, RunKey]:
    return {
        _run_directory(root, cell, replication_id): (cell, replication_id)
        for cell in cells
        for replication_id in replication_ids
    }


def _validate_exact_coverage(
    results_root: Path,
    expected_directories: Mapping[Path, RunKey],
) -> None:
    """Require the exact registered 9-by-50 run set and no extra manifests."""

    if not results_root.is_dir():
        raise FileNotFoundError(
            f"service-variability raw results do not exist: {results_root}"
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
            "service-variability coverage is incomplete: "
            f"{len(missing)} run manifests are missing ({excerpt})"
        )
    if unexpected:
        excerpt = ", ".join(str(path) for path in unexpected[:3])
        raise ValueError(
            "service-variability coverage has "
            f"{len(unexpected)} unexpected runs ({excerpt})"
        )
    if len(actual) != 450:
        raise ValueError(
            "service-variability coverage must contain exactly 450 runs"
        )


def _invariant_draw_signature(
    entity_rows: Sequence[Mapping[str, str]],
    *,
    label: str,
) -> tuple[int, str]:
    """Hash IDs and exact arrival/routing/tie draws, excluding service."""

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
            _canonical_numeric(
                row.get(field, ""),
                f"{label}:{traveller_id}:{field}",
            )
            for field in INVARIANT_DRAW_FIELDS
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


def implied_standard_normal(
    demand_seconds: object,
    *,
    mean_seconds: object,
    cv: object,
    label: str = "service demand",
) -> float:
    """Invert the registered mean/CV lognormal parameterisation."""

    demand = _float(demand_seconds, label)
    mean = _float(mean_seconds, f"{label} mean")
    coefficient = _float(cv, f"{label} CV")
    if mean <= 0:
        raise ValueError(f"{label} mean must be positive")
    if coefficient <= 0:
        raise ValueError(f"{label} CV must be positive for latent inversion")
    if demand <= 0:
        raise ValueError(f"{label} must be strictly positive for CV>0")
    sigma2 = math.log1p(coefficient * coefficient)
    latent = (math.log(demand / mean) + 0.5 * sigma2) / math.sqrt(
        sigma2
    )
    if not math.isfinite(latent):
        raise ValueError(f"{label} implied latent z must be finite")
    return latent


def _service_latents(
    entities: Sequence[Mapping[str, str]],
    *,
    cell: Cell,
    security_mean_seconds: float,
    immigration_mean_seconds: float,
    numeric_tolerance: float,
    label: str,
) -> dict[str, dict[str, float]]:
    """Validate service arms and return implied z maps for positive-CV arms."""

    security_cv, immigration_cv = cell
    latent: dict[str, dict[str, float]] = {
        "security": {},
        "immigration": {},
    }
    for row_index, entity in enumerate(entities, start=1):
        traveller_id = str(entity["traveller_id"]).strip()
        row_label = f"{label}:{row_index}:{traveller_id}"
        security_demand = _float(
            entity["security_service_demand_seconds"],
            f"{row_label}:security_service_demand_seconds",
        )
        immigration_conventional = _float(
            entity["immigration_conventional_service_demand_seconds"],
            (
                f"{row_label}:"
                "immigration_conventional_service_demand_seconds"
            ),
        )
        immigration_applied = _float(
            entity["immigration_primary_service_demand_seconds"],
            f"{row_label}:immigration_primary_service_demand_seconds",
        )
        if not _same_number(
            immigration_conventional,
            immigration_applied,
            tolerance=numeric_tolerance,
        ):
            raise ValueError(
                f"{row_label}: disabled-routing Immigration demand changed"
            )

        if security_cv == 0.0:
            if not _same_number(
                security_demand,
                security_mean_seconds,
                tolerance=numeric_tolerance,
            ):
                raise ValueError(
                    f"{row_label}: CV-zero Security demand differs from mean"
                )
        else:
            latent["security"][traveller_id] = implied_standard_normal(
                security_demand,
                mean_seconds=security_mean_seconds,
                cv=security_cv,
                label=f"{row_label}:Security",
            )

        if immigration_cv == 0.0:
            if not _same_number(
                immigration_applied,
                immigration_mean_seconds,
                tolerance=numeric_tolerance,
            ):
                raise ValueError(
                    f"{row_label}: CV-zero Immigration demand differs from mean"
                )
        else:
            latent["immigration"][traveller_id] = implied_standard_normal(
                immigration_applied,
                mean_seconds=immigration_mean_seconds,
                cv=immigration_cv,
                label=f"{row_label}:Immigration",
            )
    return latent


def _replication_metrics(
    entities: Sequence[Mapping[str, str]],
    kpi: Mapping[str, str],
    *,
    cutoff_seconds: float,
    numeric_tolerance: float,
    label: str,
) -> dict[str, float | int]:
    """Recompute ledger-derived tails and queue metrics for one replication."""

    if not entities:
        raise ValueError(f"{label}: entity ledger must not be empty")
    security_waits: list[float] = []
    immigration_waits: list[float] = []
    total_waits: list[float] = []
    system_times: list[float] = []
    for row_index, entity in enumerate(entities, start=1):
        row_label = f"{label}:entity:{row_index}"
        security_wait = _float(
            entity["security_start_seconds"],
            f"{row_label}:security_start_seconds",
        ) - _float(
            entity["security_queue_join_seconds"],
            f"{row_label}:security_queue_join_seconds",
        )
        immigration_wait = _float(
            entity["immigration_start_seconds"],
            f"{row_label}:immigration_start_seconds",
        ) - _float(
            entity["immigration_queue_join_seconds"],
            f"{row_label}:immigration_queue_join_seconds",
        )
        system_time = _float(
            entity["exit_seconds"], f"{row_label}:exit_seconds"
        ) - _float(
            entity["arrival_seconds"], f"{row_label}:arrival_seconds"
        )
        if min(security_wait, immigration_wait, system_time) < 0:
            raise ValueError(f"{row_label}: negative elapsed time")
        security_waits.append(security_wait)
        immigration_waits.append(immigration_wait)
        total_waits.append(security_wait + immigration_wait)
        system_times.append(system_time)

    calculated = {
        "security_wait_mean_seconds": sum(security_waits) / len(entities),
        "security_wait_p95_seconds": _nearest_rank(security_waits, 0.95),
        "immigration_wait_mean_seconds": (
            sum(immigration_waits) / len(entities)
        ),
        "immigration_wait_p95_seconds": _nearest_rank(
            immigration_waits, 0.95
        ),
        "total_queue_wait_mean_seconds": sum(total_waits) / len(entities),
        "total_queue_wait_p95_seconds": _nearest_rank(total_waits, 0.95),
        "system_time_mean_seconds": sum(system_times) / len(entities),
        "system_time_p95_seconds": _nearest_rank(system_times, 0.95),
        "system_time_p99_seconds": _nearest_rank(system_times, 0.99),
        "system_time_max_seconds": max(system_times),
    }
    for field in (
        "security_wait_mean_seconds",
        "security_wait_p95_seconds",
        "immigration_wait_mean_seconds",
        "immigration_wait_p95_seconds",
        "total_queue_wait_mean_seconds",
        "total_queue_wait_p95_seconds",
        "system_time_mean_seconds",
        "system_time_p95_seconds",
    ):
        if not _same_number(
            calculated[field],
            kpi[field],
            tolerance=numeric_tolerance,
        ):
            raise ValueError(f"{label}: KPI {field} differs from entity ledger")

    reconstructed = reconstruct_queue_length_metrics(
        entities, cutoff_seconds=cutoff_seconds
    )
    return {
        **calculated,
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
    }


def _validate_one_run(
    run_dir: Path,
    *,
    cell: Cell,
    replication_id: int,
    scenario_row: Mapping[str, str],
    seed_row: Mapping[str, str],
    schemas: Mapping[str, Sequence[Mapping[str, str]]],
    design: Mapping[str, object],
    numeric_tolerance: float,
) -> tuple[
    dict[str, object],
    tuple[int, str],
    dict[str, dict[str, float]],
    list[tuple[str, str]],
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
        paths["entity_log"], "entity_log", schemas["entity_log"]
    )

    scenario_id = service_variability_scenario_id(*cell)
    expected_key = (scenario_id, INPUT_SAMPLE_ID, str(replication_id))
    for table_name, row in (
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
                f"{run_dir}/{table_name}: run key {actual_key} "
                f"!= {expected_key}"
            )

    expected_hash = service_scenario_config_sha256(scenario_row)
    expected_manifest = {
        "schema_version": scenario_row["schema_version"],
        "config_id": scenario_row["config_id"],
        "config_sha256": expected_hash,
        "model_version": MODEL_VERSION,
        "scenario_id": scenario_id,
        "scenario_family": scenario_row["scenario_family"],
        "reference_scenario_id": scenario_row["reference_scenario_id"],
        "input_sample_id": scenario_row["input_sample_id"],
        "start_state": design["fixed_inputs"]["start_state"],
        "arrival_mode": scenario_row["arrival_mode"],
        "drain_rule": scenario_row["drain_rule"],
        "calibration_status": scenario_row["calibration_status"],
        "claim_ceiling": scenario_row["claim_ceiling"],
        "crn_alignment_status": scenario_row["crn_alignment_status"],
        "run_status": "COMPLETE",
    }
    for field, expected in expected_manifest.items():
        if manifest[field] != str(expected):
            raise ValueError(
                f"{run_dir}: manifest {field} differs from frozen design"
            )

    cutoff_seconds = _float(
        design["fixed_inputs"]["arrival_cutoff_seconds"],
        "arrival_cutoff_seconds",
    )
    if not _same_number(
        manifest["arrival_cutoff_seconds"],
        cutoff_seconds,
        tolerance=numeric_tolerance,
    ):
        raise ValueError(f"{run_dir}: arrival cutoff drifted")
    for field in ("master_seed", *STREAM_SEED_FIELDS):
        if manifest[field] != seed_row[field]:
            raise ValueError(f"{run_dir}: {field} differs from seed manifest")

    for field in LINEAGE_FIELDS:
        if kpi[field] != manifest[field]:
            raise ValueError(f"{run_dir}: KPI {field} differs from manifest")
    if kpi["run_status"] != "COMPLETE":
        raise ValueError(f"{run_dir}: KPI run_status must be COMPLETE")
    if not _boolean(kpi["conservation_pass"], f"{run_dir}:conservation"):
        raise ValueError(f"{run_dir}: conservation_pass must be true")
    if not _same_number(
        kpi["arrival_cutoff_seconds"],
        manifest["arrival_cutoff_seconds"],
        tolerance=numeric_tolerance,
    ) or not _same_number(
        kpi["drain_end_seconds"],
        manifest["drain_end_seconds"],
        tolerance=numeric_tolerance,
    ):
        raise ValueError(f"{run_dir}: KPI timing lineage differs from manifest")

    counts = {
        field: _integer(kpi[field], f"{run_dir}:{field}")
        for field in COUNT_FIELDS
    }
    if any(value < 0 for value in counts.values()):
        raise ValueError(f"{run_dir}: KPI counts must be non-negative")
    if counts["arrivals"] <= 0:
        raise ValueError(f"{run_dir}: an analysed replication must have arrivals")
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
    if counts["technology_count"] != 0:
        raise ValueError(f"{run_dir}: technology routing must remain disabled")
    if counts["additional_check_count"] != 0:
        raise ValueError(f"{run_dir}: additional checks must remain disabled")
    if counts["completed_after_drain"] != counts["arrivals"]:
        raise ValueError(f"{run_dir}: full-drain conservation fails")
    if len(entities) != counts["arrivals"]:
        raise ValueError(
            f"{run_dir}: entity count {len(entities)} "
            f"!= arrivals {counts['arrivals']}"
        )
    expected_fraction = counts["cutoff_backlog"] / counts["arrivals"]
    if not _same_number(
        kpi["cutoff_backlog_fraction"],
        expected_fraction,
        tolerance=numeric_tolerance,
    ):
        raise ValueError(f"{run_dir}: cutoff backlog fraction is wrong")

    arrival_guard = _integer(
        scenario_row["arrival_guard"], f"{run_dir}:arrival_guard"
    )
    if counts["arrivals"] >= arrival_guard:
        raise ValueError(
            f"{run_dir}: arrival count reached the configured guard"
        )
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

    ledger_metrics = _replication_metrics(
        entities,
        kpi,
        cutoff_seconds=cutoff_seconds,
        numeric_tolerance=numeric_tolerance,
        label=str(run_dir),
    )
    security_queue_guard = _integer(
        scenario_row["security_queue_capacity"],
        f"{run_dir}:security_queue_capacity",
    )
    immigration_queue_guard = _integer(
        scenario_row["immigration_queue_capacity"],
        f"{run_dir}:immigration_queue_capacity",
    )
    if (
        int(ledger_metrics["peak_security_waiting_queue"])
        >= security_queue_guard
    ):
        raise ValueError(f"{run_dir}: Security queue reached its guard")
    if (
        int(ledger_metrics["peak_immigration_waiting_queue"])
        >= immigration_queue_guard
    ):
        raise ValueError(f"{run_dir}: Immigration queue reached its guard")

    clear_time = max(
        0.0,
        max(
            _float(entity["exit_seconds"], f"{run_dir}:exit_seconds")
            for entity in entities
        )
        - cutoff_seconds,
    )
    if not _same_number(
        kpi["cohort_clear_time_after_cutoff_seconds"],
        clear_time,
        tolerance=numeric_tolerance,
    ):
        raise ValueError(f"{run_dir}: cohort clear time differs from ledger")

    latent = _service_latents(
        entities,
        cell=cell,
        security_mean_seconds=_float(
            design["fixed_inputs"]["security_service_mean_seconds"],
            "security_service_mean_seconds",
        ),
        immigration_mean_seconds=_float(
            design["fixed_inputs"]["immigration_service_mean_seconds"],
            "immigration_service_mean_seconds",
        ),
        numeric_tolerance=numeric_tolerance,
        label=str(run_dir),
    )
    row: dict[str, object] = {
        **kpi,
        **ledger_metrics,
        "study_id": STUDY_ID,
        "security_service_cv": cell[0],
        "immigration_service_cv": cell[1],
        "master_seed": manifest["master_seed"],
        "arrival_seed": manifest["arrival_seed"],
        "service_seed": manifest["service_seed"],
        "routing_seed": manifest["routing_seed"],
        "tie_seed": manifest["tie_seed"],
    }
    invariant_signature = _invariant_draw_signature(
        entities, label=f"{run_dir}/entity_log.csv"
    )
    artifacts = [
        (portable_path(path), _sha256(path)) for path in paths.values()
    ]
    return row, invariant_signature, latent, artifacts


def build_crn_alignment_report(
    invariant_signatures: Mapping[RunKey, tuple[int, str]],
    stage_latents: Mapping[
        RunKey, Mapping[str, Mapping[str, float]]
    ],
    *,
    cells: Sequence[Cell],
    replication_ids: Sequence[int],
    registered_seed_alignment_pass: bool,
    service_demand_validation_pass: bool,
    numeric_tolerance: float = DEFAULT_LATENT_TOLERANCE,
    study_id: str = STUDY_ID,
) -> dict[str, object]:
    """Validate exact invariants and same-stage positive-CV latent alignment."""

    if numeric_tolerance < 0 or not math.isfinite(numeric_tolerance):
        raise ValueError("numeric_tolerance must be finite and non-negative")
    cell_tuple = tuple(cells)
    replication_tuple = tuple(replication_ids)
    errors: list[str] = []
    if not registered_seed_alignment_pass:
        errors.append("registered manifest seed validation did not pass")
    if not service_demand_validation_pass:
        errors.append("per-run service-demand validation did not pass")
    invariant_pairs = 0
    invariant_values = 0
    latent_pairs = {"security": 0, "immigration": 0}

    for replication_id in replication_tuple:
        reference = invariant_signatures.get(
            (REFERENCE_CELL, replication_id)
        )
        if reference is None:
            errors.append(
                f"replication {replication_id}: invariant reference missing"
            )
            continue
        reference_count, reference_digest = reference
        if reference_count <= 0:
            errors.append(
                f"replication {replication_id}: invariant reference is empty"
            )
            continue
        for cell in cell_tuple:
            current = invariant_signatures.get((cell, replication_id))
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
                    f"replication {replication_id}: {cell} arrival/routing/tie "
                    "digest differs from reference"
                )
                continue
            if cell != REFERENCE_CELL:
                invariant_pairs += count
                invariant_values += count * len(INVARIANT_DRAW_FIELDS)

        for stage, axis in (("security", 0), ("immigration", 1)):
            positive_cells = [cell for cell in cell_tuple if cell[axis] > 0]
            if not positive_cells:
                errors.append(f"{stage}: no positive-CV cells are registered")
                continue
            latent_reference_cell = positive_cells[0]
            latent_reference = stage_latents.get(
                (latent_reference_cell, replication_id), {}
            ).get(stage)
            if latent_reference is None:
                errors.append(
                    f"replication {replication_id}: {stage} latent reference "
                    "missing"
                )
                continue
            if not latent_reference:
                errors.append(
                    f"replication {replication_id}: {stage} positive-CV "
                    "latent reference is empty"
                )
                continue
            for cell in positive_cells[1:]:
                current = stage_latents.get(
                    (cell, replication_id), {}
                ).get(stage)
                if current is None:
                    errors.append(
                        f"replication {replication_id}: {cell} {stage} "
                        "latents missing"
                    )
                    continue
                if set(current) != set(latent_reference):
                    errors.append(
                        f"replication {replication_id}: {cell} {stage} "
                        "latent traveller IDs differ"
                    )
                    continue
                mismatch = next(
                    (
                        traveller_id
                        for traveller_id in sorted(current)
                        if not math.isclose(
                            current[traveller_id],
                            latent_reference[traveller_id],
                            rel_tol=numeric_tolerance,
                            abs_tol=numeric_tolerance,
                        )
                    ),
                    None,
                )
                if mismatch is not None:
                    errors.append(
                        f"replication {replication_id}: {cell} {stage} "
                        f"implied latent z differs for {mismatch}"
                    )
                    continue
                latent_pairs[stage] += len(current)

    coverage_pass = (
        len(invariant_signatures)
        == len(cell_tuple) * len(replication_tuple)
        and len(stage_latents)
        == len(cell_tuple) * len(replication_tuple)
    )
    if not coverage_pass:
        errors.append("CRN input coverage is incomplete")
    passed = (
        coverage_pass
        and registered_seed_alignment_pass
        and service_demand_validation_pass
        and not errors
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "validation": CRN_VALIDATION_ID,
        "study_id": study_id,
        "status": "PASS" if passed else "FAIL",
        "coverage_pass": coverage_pass,
        "seed_alignment_pass": registered_seed_alignment_pass,
        "traveller_level_alignment_pass": passed,
        "branch_invariant_draws_pass": passed,
        "arrival_routing_tie_exact_pass": passed,
        "security_positive_cv_latent_alignment_pass": passed,
        "immigration_positive_cv_latent_alignment_pass": passed,
        "fixed_service_demand_pass": service_demand_validation_pass,
        "positive_service_demand_pass": service_demand_validation_pass,
        "cell_count": len(cell_tuple),
        "replication_count": len(replication_tuple),
        "invariant_draw_fields": list(INVARIANT_DRAW_FIELDS),
        "invariant_comparison": "EXACT_CANONICAL_IEEE754",
        "latent_comparison_numeric_tolerance": numeric_tolerance,
        "compared_invariant_traveller_pairs": invariant_pairs,
        "compared_invariant_draw_values": invariant_values,
        "compared_security_latent_pairs": latent_pairs["security"],
        "compared_immigration_latent_pairs": latent_pairs["immigration"],
        "errors": errors,
        "paired_analysis_gate": (
            "Paired contrasts and factorial interactions are emitted only "
            "when this report returns PASS."
        ),
    }


def _paired_summary(
    values: Sequence[float],
    *,
    ci_level: float,
) -> dict[str, float | int]:
    if any(not math.isfinite(value) for value in values):
        raise ValueError("paired quantity contains a non-finite value")
    return one_sample_summary(list(values), ci_level=ci_level)


def _estimate_lookup(
    estimates: Sequence[Mapping[str, object]],
) -> dict[tuple[Cell, str], Mapping[str, object]]:
    return {
        (
            (
                float(row["security_service_cv"]),
                float(row["immigration_service_cv"]),
            ),
            str(row["metric"]),
        ): row
        for row in estimates
    }


def build_service_variability_analysis(
    replication_rows: Sequence[Mapping[str, object]],
    *,
    cells: Sequence[Cell],
    replication_ids: Sequence[int],
    crn_alignment_status: str,
    study_id: str = STUDY_ID,
    ci_level: float = DEFAULT_CI_LEVEL,
) -> dict[str, object]:
    """Build estimates and CRN-gated paired response payloads."""

    if crn_alignment_status != "PASS":
        raise ValueError(
            "paired service-variability analysis requires CRN status PASS"
        )
    if not 0 < ci_level < 1:
        raise ValueError("ci_level must be between 0 and 1")
    expected = {
        (cell, replication_id)
        for cell in cells
        for replication_id in replication_ids
    }
    by_key: dict[RunKey, Mapping[str, object]] = {}
    for row in replication_rows:
        key = (
            (
                float(row["security_service_cv"]),
                float(row["immigration_service_cv"]),
            ),
            int(row["replication_id"]),
        )
        if key in by_key:
            raise ValueError(f"duplicate replication row: {key}")
        by_key[key] = row
    missing = expected - set(by_key)
    unexpected = set(by_key) - expected
    if missing or unexpected:
        raise ValueError(
            "replication rows do not match the exact registered coverage"
        )
    if REFERENCE_CELL not in set(cells):
        raise ValueError("service-variability reference cell is missing")

    estimates: list[dict[str, object]] = []
    for cell in cells:
        for metric in ANALYSIS_METRICS:
            values = [
                _float(
                    by_key[(cell, replication_id)][metric],
                    f"{cell}/{replication_id}/{metric}",
                )
                for replication_id in replication_ids
            ]
            summary = one_sample_summary(values, ci_level=ci_level)
            estimates.append(
                {
                    "schema_version": SCHEMA_VERSION,
                    "study_id": study_id,
                    "security_service_cv": cell[0],
                    "immigration_service_cv": cell[1],
                    "scenario_id": service_variability_scenario_id(*cell),
                    "metric": metric,
                    "estimand": "MEAN_OF_REPLICATION_LEVEL_METRIC",
                    "n_replications": summary["n"],
                    "mean": summary["mean"],
                    "standard_deviation": summary["standard_deviation"],
                    "standard_error": summary["standard_error"],
                    "ci_level": ci_level,
                    "ci_low": summary["ci_low"],
                    "ci_high": summary["ci_high"],
                    "analysis_role": (
                        "EXPLORATORY_ASSUMPTION_SENSITIVITY_NOT_CALIBRATION"
                    ),
                }
            )

    contrasts: list[dict[str, object]] = []
    for cell in cells:
        if cell == REFERENCE_CELL:
            continue
        for metric in ANALYSIS_METRICS:
            differences = [
                _float(
                    by_key[(cell, replication_id)][metric],
                    f"{cell}/{replication_id}/{metric}",
                )
                - _float(
                    by_key[(REFERENCE_CELL, replication_id)][metric],
                    f"{REFERENCE_CELL}/{replication_id}/{metric}",
                )
                for replication_id in replication_ids
            ]
            summary = _paired_summary(differences, ci_level=ci_level)
            contrasts.append(
                {
                    "schema_version": SCHEMA_VERSION,
                    "study_id": study_id,
                    "security_service_cv": cell[0],
                    "immigration_service_cv": cell[1],
                    "scenario_id": service_variability_scenario_id(*cell),
                    "reference_scenario_id": REFERENCE_SCENARIO_ID,
                    "metric": metric,
                    "difference_direction": "CELL_MINUS_CV_ZERO_REFERENCE",
                    "comparison_method": "PAIRED_STUDENT_T",
                    "n_pairs": summary["n"],
                    "difference_mean": summary["mean"],
                    "standard_deviation": summary["standard_deviation"],
                    "standard_error": summary["standard_error"],
                    "degrees_of_freedom": summary["degrees_of_freedom"],
                    "ci_level": ci_level,
                    "ci_low": summary["ci_low"],
                    "ci_high": summary["ci_high"],
                    "crn_alignment_status": "PASS",
                    "analysis_role": "DESCRIPTIVE_EXPLORATORY_CONTRAST",
                }
            )

    interactions: list[dict[str, object]] = []
    security_positive = sorted({cell[0] for cell in cells if cell[0] > 0})
    immigration_positive = sorted(
        {cell[1] for cell in cells if cell[1] > 0}
    )
    cell_set = set(cells)
    for security_cv in security_positive:
        for immigration_cv in immigration_positive:
            required = (
                (security_cv, immigration_cv),
                (security_cv, 0.0),
                (0.0, immigration_cv),
                REFERENCE_CELL,
            )
            if not set(required).issubset(cell_set):
                raise ValueError(
                    "factorial interaction is missing a required design cell"
                )
            joint, security_only, immigration_only, reference = required
            for metric in ANALYSIS_METRICS:
                differences = [
                    _float(
                        by_key[(joint, replication_id)][metric],
                        f"{joint}/{replication_id}/{metric}",
                    )
                    - _float(
                        by_key[(security_only, replication_id)][metric],
                        f"{security_only}/{replication_id}/{metric}",
                    )
                    - _float(
                        by_key[(immigration_only, replication_id)][metric],
                        f"{immigration_only}/{replication_id}/{metric}",
                    )
                    + _float(
                        by_key[(reference, replication_id)][metric],
                        f"{reference}/{replication_id}/{metric}",
                    )
                    for replication_id in replication_ids
                ]
                summary = _paired_summary(differences, ci_level=ci_level)
                interactions.append(
                    {
                        "schema_version": SCHEMA_VERSION,
                        "study_id": study_id,
                        "security_service_cv": security_cv,
                        "immigration_service_cv": immigration_cv,
                        "joint_scenario_id": (
                            service_variability_scenario_id(*joint)
                        ),
                        "security_only_scenario_id": (
                            service_variability_scenario_id(*security_only)
                        ),
                        "immigration_only_scenario_id": (
                            service_variability_scenario_id(*immigration_only)
                        ),
                        "reference_scenario_id": REFERENCE_SCENARIO_ID,
                        "metric": metric,
                        "contrast": (
                            "JOINT_MINUS_SECURITY_ONLY_MINUS_"
                            "IMMIGRATION_ONLY_PLUS_REFERENCE"
                        ),
                        "n_pairs": summary["n"],
                        "interaction_mean": summary["mean"],
                        "standard_deviation": summary["standard_deviation"],
                        "standard_error": summary["standard_error"],
                        "degrees_of_freedom": summary["degrees_of_freedom"],
                        "ci_level": ci_level,
                        "ci_low": summary["ci_low"],
                        "ci_high": summary["ci_high"],
                        "crn_alignment_status": "PASS",
                        "analysis_role": (
                            "DESCRIPTIVE_FACTORIAL_INTERACTION"
                        ),
                    }
                )

    lookup = _estimate_lookup(estimates)

    def view_row(view: str, index: int, cell: Cell) -> dict[str, object]:
        estimate = lookup[(cell, PRIMARY_METRIC)]
        return {
            "schema_version": SCHEMA_VERSION,
            "study_id": study_id,
            "view": view,
            "path_index": index,
            "security_service_cv": cell[0],
            "immigration_service_cv": cell[1],
            "scenario_id": service_variability_scenario_id(*cell),
            "metric": PRIMARY_METRIC,
            "n_replications": estimate["n_replications"],
            "mean": estimate["mean"],
            "standard_error": estimate["standard_error"],
            "ci_level": estimate["ci_level"],
            "ci_low": estimate["ci_low"],
            "ci_high": estimate["ci_high"],
        }

    heatmap_cells = sorted(cells, key=lambda cell: (cell[0], cell[1]))
    security_cells = sorted(
        (cell for cell in cells if cell[1] == 0.0),
        key=lambda cell: cell[0],
    )
    immigration_cells = sorted(
        (cell for cell in cells if cell[0] == 0.0),
        key=lambda cell: cell[1],
    )
    balanced_cells = sorted(
        (cell for cell in cells if cell[0] == cell[1]),
        key=lambda cell: cell[0],
    )
    heatmap = [
        view_row("FULL_FACTORIAL_HEATMAP", index, cell)
        for index, cell in enumerate(heatmap_cells)
    ]
    security_slice = [
        view_row("SECURITY_CV_AT_IMMIGRATION_CV_ZERO", index, cell)
        for index, cell in enumerate(security_cells)
    ]
    immigration_slice = [
        view_row("IMMIGRATION_CV_AT_SECURITY_CV_ZERO", index, cell)
        for index, cell in enumerate(immigration_cells)
    ]
    balanced_slice = [
        view_row("BALANCED_JOINT_CV_PATH", index, cell)
        for index, cell in enumerate(balanced_cells)
    ]
    primary_interactions = [
        row for row in interactions if row["metric"] == PRIMARY_METRIC
    ]
    return {
        "estimates": estimates,
        "contrasts": contrasts,
        "interactions": interactions,
        "heatmap": heatmap,
        "security_slice": security_slice,
        "immigration_slice": immigration_slice,
        "balanced_slice": balanced_slice,
        "view_payload": {
            "schema_version": SCHEMA_VERSION,
            "study_id": study_id,
            "analysis_role": (
                "EXPLORATORY_ASSUMPTION_SENSITIVITY_NOT_CALIBRATION"
            ),
            "metric": PRIMARY_METRIC,
            "crn_alignment_status": "PASS",
            "heatmap": heatmap,
            "security_only_slice": security_slice,
            "immigration_only_slice": immigration_slice,
            "balanced_joint_slice": balanced_slice,
            "factorial_interaction": primary_interactions,
        },
    }


def package_service_variability_analysis(
    results_root: Path = DEFAULT_RESULTS_ROOT,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    *,
    design_path: Path = DEFAULT_DESIGN,
    scenarios_path: Path = DEFAULT_SCENARIOS,
    seed_manifest_path: Path = DEFAULT_SEED_MANIFEST,
    schema_registry_path: Path = DEFAULT_SCHEMA_REGISTRY,
    ci_level: float = DEFAULT_CI_LEVEL,
    numeric_tolerance: float = DEFAULT_NUMERIC_TOLERANCE,
    latent_tolerance: float = DEFAULT_LATENT_TOLERANCE,
) -> dict[str, object]:
    """Validate the future raw batch and write compact auditable outputs."""

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
    if latent_tolerance < 0 or not math.isfinite(latent_tolerance):
        raise ValueError("latent_tolerance must be finite and non-negative")

    design_validation = validate_service_variability_design(
        design_path,
        scenarios_path,
        seed_manifest_path,
    )
    if design_validation["status"] != "PASS":
        raise ValueError(
            "frozen service-variability design validation failed: "
            + "; ".join(map(str, design_validation["errors"]))
        )
    design = load_design(design_path)
    if design["study_id"] != STUDY_ID:
        raise ValueError("service-variability study ID drifted")
    if design["model_version"] != MODEL_VERSION:
        raise ValueError("service-variability model version drifted")

    cells = tuple(study_cells(design_path))
    if len(cells) != 9 or set(cells) != {
        (security_cv, immigration_cv)
        for security_cv in (0.0, 0.5, 1.0)
        for immigration_cv in (0.0, 0.5, 1.0)
    }:
        raise ValueError("service-variability factorial must be exact 3-by-3")
    expected_directories = _expected_run_paths(
        results_root, cells, REPLICATION_IDS
    )
    _validate_exact_coverage(results_root, expected_directories)

    schemas = load_result_schemas(schema_registry_path)
    if set(RESULT_FILES) - set(schemas):
        raise ValueError("result schema registry is missing a required table")
    scenario_rows_list = load_service_variability_scenario_rows(
        scenarios_path
    )
    if tuple(scenario_rows_list[0]) != SERVICE_SCENARIO_COLUMNS:
        raise ValueError("service scenario schema drifted")
    scenario_rows = {
        _cell_from_row(row): row for row in scenario_rows_list
    }
    if set(scenario_rows) != set(cells):
        raise ValueError("service scenario cells differ from frozen factorial")
    seed_rows = {
        int(row["replication_id"]): row
        for row in load_service_variability_seed_rows(seed_manifest_path)
    }
    if set(seed_rows) != set(REPLICATION_IDS):
        raise ValueError("seed manifest does not contain replications 1..50")

    replication_rows: list[dict[str, object]] = []
    invariant_signatures: dict[RunKey, tuple[int, str]] = {}
    stage_latents: dict[
        RunKey, dict[str, dict[str, float]]
    ] = {}
    artifact_entries: list[tuple[str, str]] = []
    entity_row_count = 0
    for cell in cells:
        scenario = scenario_rows[cell]
        for replication_id in REPLICATION_IDS:
            run_dir = _run_directory(results_root, cell, replication_id)
            row, invariant, latent, artifacts = _validate_one_run(
                run_dir,
                cell=cell,
                replication_id=replication_id,
                scenario_row=scenario,
                seed_row=seed_rows[replication_id],
                schemas=schemas,
                design=design,
                numeric_tolerance=numeric_tolerance,
            )
            replication_rows.append(row)
            invariant_signatures[(cell, replication_id)] = invariant
            stage_latents[(cell, replication_id)] = latent
            entity_row_count += invariant[0]
            artifact_entries.extend(artifacts)

    if len(replication_rows) != 450:
        raise ValueError("validated replication count must equal 450")
    crn = build_crn_alignment_report(
        invariant_signatures,
        stage_latents,
        cells=cells,
        replication_ids=REPLICATION_IDS,
        registered_seed_alignment_pass=True,
        service_demand_validation_pass=True,
        numeric_tolerance=latent_tolerance,
        study_id=STUDY_ID,
    )
    if crn["status"] != "PASS":
        raise ValueError(
            "service-variability CRN alignment failed: "
            + "; ".join(map(str, crn["errors"][:5]))
        )

    analysis = build_service_variability_analysis(
        replication_rows,
        cells=cells,
        replication_ids=REPLICATION_IDS,
        crn_alignment_status=str(crn["status"]),
        study_id=STUDY_ID,
        ci_level=ci_level,
    )
    raw_tree_sha256 = _tree_digest(artifact_entries)
    artifact_hashes = {
        "design_sha256": _sha256(design_path),
        "scenarios_sha256": _sha256(scenarios_path),
        "seed_manifest_sha256": _sha256(seed_manifest_path),
        "schema_registry_sha256": _sha256(schema_registry_path),
    }
    validation = {
        "schema_version": SCHEMA_VERSION,
        "validation": VALIDATION_ID,
        "study_id": STUDY_ID,
        "model_version": MODEL_VERSION,
        "status": "PASS",
        "coverage_status": "PASS",
        "canonical_schema_status": "PASS",
        "lineage_and_extended_config_hash_status": "PASS",
        "registered_seed_status": "PASS",
        "run_completion_status": "PASS",
        "conservation_and_full_drain_status": "PASS",
        "arrival_and_queue_guard_status": "PASS",
        "drop_and_rejection_status": "PASS",
        "service_demand_contract_status": "PASS",
        "crn_alignment_status": crn["status"],
        "scenario_count": len(cells),
        "replications_per_cell": len(REPLICATION_IDS),
        "expected_run_count": 450,
        "actual_run_count": len(replication_rows),
        "entity_row_count": entity_row_count,
        "raw_file_count": len(artifact_entries),
        "raw_tree_sha256": raw_tree_sha256,
        "artifact_hashes": artifact_hashes,
        "errors": [],
        "claim_boundary": design["claim_ceiling"],
    }
    raw_audit = {
        "schema_version": SCHEMA_VERSION,
        "audit": RAW_AUDIT_ID,
        "study_id": STUDY_ID,
        "model_version": MODEL_VERSION,
        "status": "PASS",
        "raw_results_root": portable_path(results_root),
        "run_count": len(replication_rows),
        "entity_row_count": entity_row_count,
        "raw_file_count": len(artifact_entries),
        "raw_tree_sha256": raw_tree_sha256,
        "artifact_hashes": artifact_hashes,
        "configuration_hash_algorithm": (
            "SHA256_CANONICAL_EXTENDED_SERVICE_SCENARIO_ROW"
        ),
        "entity_logs_copied_to_analysis_package": False,
        "guard_semantics": {
            "arrival": "arrivals strictly below arrival_guard",
            "security_queue": (
                "reconstructed full-drain peak strictly below queue capacity"
            ),
            "immigration_queue": (
                "reconstructed full-drain peak strictly below queue capacity"
            ),
        },
    }

    outputs: tuple[
        tuple[str, Sequence[Mapping[str, object]], Sequence[str]], ...
    ] = (
        (
            "service_variability_by_replication.csv",
            replication_rows,
            REPLICATION_FIELDS,
        ),
        ("cell_estimates.csv", analysis["estimates"], ESTIMATE_FIELDS),
        (
            "paired_contrasts_vs_reference.csv",
            analysis["contrasts"],
            CONTRAST_FIELDS,
        ),
        (
            "factorial_interactions.csv",
            analysis["interactions"],
            INTERACTION_FIELDS,
        ),
        ("heatmap.csv", analysis["heatmap"], VIEW_FIELDS),
        (
            "security_only_slice.csv",
            analysis["security_slice"],
            VIEW_FIELDS,
        ),
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
    )
    for filename, rows, fields in outputs:
        _write_csv(output_dir / filename, rows, fields)
    _write_json(output_dir / "validation.json", validation)
    _write_json(output_dir / "crn_alignment.json", crn)
    _write_json(output_dir / "raw_audit_manifest.json", raw_audit)
    _write_json(output_dir / "analysis_payload.json", analysis["view_payload"])

    output_paths = [
        output_dir / filename for filename, _, _ in outputs
    ] + [
        output_dir / "validation.json",
        output_dir / "crn_alignment.json",
        output_dir / "raw_audit_manifest.json",
        output_dir / "analysis_payload.json",
    ]
    manifest: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "analysis": ANALYSIS_ID,
        "study_id": STUDY_ID,
        "model_version": MODEL_VERSION,
        "status": "PASS",
        "analysis_role": design["analysis_role"],
        "claim_boundary": design["claim_ceiling"],
        "coverage": {
            "cell_count": len(cells),
            "replications_per_cell": len(REPLICATION_IDS),
            "run_count": len(replication_rows),
        },
        "paired_analysis_gate": {
            "crn_alignment_status": crn["status"],
            "comparison_method": "PAIRED_STUDENT_T",
        },
        "queue_reconstruction": {
            "peak_window": "FULL_DRAIN",
            "time_weighted_mean_window": "[0,300)",
            "interval_semantics": (
                "[queue_join,service_start), end events before starts on ties"
            ),
        },
        "tail_metrics": {
            "within_replication_method": "NEAREST_RANK",
            "system_time_p99_and_max_reconstructed_from_entity_ledger": True,
        },
        "source": {
            "raw_results_root": portable_path(results_root),
            "entity_row_count": entity_row_count,
            "entity_logs_copied_to_analysis_package": False,
            "raw_file_count": len(artifact_entries),
            "raw_tree_sha256": raw_tree_sha256,
            "artifact_hashes": artifact_hashes,
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
    parser.add_argument("--ci-level", type=float, default=DEFAULT_CI_LEVEL)
    parser.add_argument(
        "--numeric-tolerance",
        type=float,
        default=DEFAULT_NUMERIC_TOLERANCE,
    )
    parser.add_argument(
        "--latent-tolerance",
        type=float,
        default=DEFAULT_LATENT_TOLERANCE,
        help=(
            "absolute/relative tolerance for inverse-transformed service "
            "latents; arrival/routing/tie comparison remains exact"
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = package_service_variability_analysis(
            args.results_root,
            args.output_dir,
            design_path=args.design,
            scenarios_path=args.scenarios,
            seed_manifest_path=args.seed_manifest,
            schema_registry_path=args.schema_registry,
            ci_level=args.ci_level,
            numeric_tolerance=args.numeric_tolerance,
            latent_tolerance=args.latent_tolerance,
        )
    except (FileNotFoundError, KeyError, TypeError, ValueError) as error:
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
