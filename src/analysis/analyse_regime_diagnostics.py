"""Build post-hoc load-regime diagnostics from the frozen entity ledger.

This supplement does not alter the pre-specified confirmatory estimand.  It
uses the immutable traveller ledger to explain when capacity becomes
operationally consequential and to add model-scale 15/30/60-second waiting
diagnostics.  Those thresholds are supporting diagnostics, not ICA service
standards or prospectively registered decision rules.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from src.analysis.analyse_operational_replications import (
    one_sample_summary,
    paired_difference,
    portable_path,
)
from src.analysis.confirmatory_design import DEFAULT_DESIGN


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ENTITY_LOG = (
    PROJECT_ROOT
    / "results"
    / "raw"
    / "confirmatory_capacity_consolidated"
    / "entity_log.csv"
)
DEFAULT_OUTPUT_DIR = (
    PROJECT_ROOT / "results" / "analysis" / "confirmatory_capacity"
)
DEFAULT_AUDIT_MANIFEST = DEFAULT_OUTPUT_DIR / "audit_manifest.json"
REFERENCE_SCENARIO_ID = "REFERENCE_ASSUMPTION_SANDBOX_V1"
JOINT_SCENARIO_ID = "CAPACITY_BOTH_PLUS"
THRESHOLDS_SECONDS = (15.0, 30.0, 60.0)

REPLICATION_FIELDS = (
    "schema_version",
    "study_id",
    "analysis_role",
    "scenario_id",
    "arrival_level_id",
    "input_sample_id",
    "replication_id",
    "arrival_rate_per_second",
    "arrivals",
    "security_capacity",
    "immigration_capacity",
    "security_nominal_offered_load",
    "immigration_nominal_offered_load",
    "security_arrival_window_utilization",
    "immigration_arrival_window_utilization",
    "total_queue_wait_exceed_15_rate",
    "total_queue_wait_exceed_30_rate",
    "total_queue_wait_exceed_60_rate",
)
ESTIMATE_FIELDS = (
    "schema_version",
    "study_id",
    "analysis_role",
    "scenario_id",
    "arrival_level_id",
    "input_sample_id",
    "metric",
    "n_replications",
    "mean",
    "standard_deviation",
    "standard_error",
    "ci_level",
    "ci_low",
    "ci_high",
)
CONTRAST_FIELDS = (
    "schema_version",
    "study_id",
    "analysis_role",
    "arrival_level_id",
    "input_sample_id",
    "metric",
    "difference_direction",
    "comparison_method",
    "n_pairs",
    "difference_mean_percentage_points",
    "ci_level",
    "ci_low_percentage_points",
    "ci_high_percentage_points",
)
REGIME_METRICS = (
    "security_nominal_offered_load",
    "immigration_nominal_offered_load",
    "security_arrival_window_utilization",
    "immigration_arrival_window_utilization",
    "total_queue_wait_exceed_15_rate",
    "total_queue_wait_exceed_30_rate",
    "total_queue_wait_exceed_60_rate",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_json(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def _write_csv(
    path: Path,
    rows: Iterable[Mapping[str, object]],
    fields: Sequence[str],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(fields),
            extrasaction="raise",
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
                }
            )
    temporary.replace(path)


def _finite(value: str, field: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{field} must be finite")
    return number


def interval_overlap(
    start: float,
    end: float,
    window_start: float,
    window_end: float,
) -> float:
    """Return the non-negative overlap of two half-open time intervals."""

    if end < start:
        raise ValueError("service interval ends before it starts")
    return max(0.0, min(end, window_end) - max(start, window_start))


def _design_maps(
    design: Mapping[str, object],
) -> tuple[
    dict[str, tuple[str, float]],
    dict[tuple[str, str], tuple[int, int]],
    str,
]:
    study_id = str(design["study_id"])
    levels = {
        str(level["input_sample_id"]): (
            str(level["level_id"]),
            float(level["arrival_rate_per_second"]),
        )
        for level in design["arrival_rate_uncertainty"]["levels"]  # type: ignore[index]
    }
    input_sample_by_level = {
        level_id: input_sample_id
        for input_sample_id, (level_id, _) in levels.items()
    }
    cells = {
        (
            str(cell["scenario_id"]),
            input_sample_by_level[str(cell["arrival_level_id"])],
        ): (
            int(cell["security_capacity"]),
            int(cell["immigration_capacity"]),
        )
        for cell in design["study_cells"]  # type: ignore[index]
    }
    return levels, cells, study_id


def build_replication_diagnostics(
    entity_log_path: Path,
    design: Mapping[str, object],
) -> tuple[list[dict[str, object]], int]:
    """Aggregate traveller rows into one diagnostic record per run."""

    levels, cells, study_id = _design_maps(design)
    accumulators: dict[tuple[str, str, str], dict[str, object]] = {}
    row_count = 0
    with entity_log_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {
            "scenario_id",
            "input_sample_id",
            "replication_id",
            "arrival_seconds",
            "security_service_demand_seconds",
            "immigration_primary_service_demand_seconds",
            "additional_check_service_demand_seconds",
            "security_queue_join_seconds",
            "security_start_seconds",
            "security_end_seconds",
            "immigration_queue_join_seconds",
            "immigration_start_seconds",
            "exit_seconds",
        }
        if reader.fieldnames is None or not required.issubset(
            set(reader.fieldnames)
        ):
            raise ValueError("entity ledger header is missing required fields")
        for source in reader:
            row_count += 1
            key = (
                source["scenario_id"],
                source["input_sample_id"],
                source["replication_id"],
            )
            cell_key = (key[0], key[1])
            if cell_key not in cells or key[1] not in levels:
                raise ValueError(f"unexpected confirmatory entity key: {key}")
            bucket = accumulators.setdefault(
                key,
                {
                    "arrivals": 0,
                    "security_busy": 0.0,
                    "immigration_busy": 0.0,
                    "security_demand": 0.0,
                    "immigration_demand": 0.0,
                    "exceed": {threshold: 0 for threshold in THRESHOLDS_SECONDS},
                },
            )
            cutoff = 300.0
            security_join = _finite(
                source["security_queue_join_seconds"],
                "security_queue_join_seconds",
            )
            security_start = _finite(
                source["security_start_seconds"],
                "security_start_seconds",
            )
            security_end = _finite(
                source["security_end_seconds"],
                "security_end_seconds",
            )
            immigration_join = _finite(
                source["immigration_queue_join_seconds"],
                "immigration_queue_join_seconds",
            )
            immigration_start = _finite(
                source["immigration_start_seconds"],
                "immigration_start_seconds",
            )
            exit_seconds = _finite(source["exit_seconds"], "exit_seconds")
            security_demand = _finite(
                source["security_service_demand_seconds"],
                "security_service_demand_seconds",
            )
            immigration_demand = _finite(
                source["immigration_primary_service_demand_seconds"],
                "immigration_primary_service_demand_seconds",
            )
            additional_text = source["additional_check_service_demand_seconds"]
            if additional_text:
                immigration_demand += _finite(
                    additional_text,
                    "additional_check_service_demand_seconds",
                )
            total_wait = (
                security_start
                - security_join
                + immigration_start
                - immigration_join
            )
            if total_wait < -1e-9:
                raise ValueError("entity ledger contains negative queue wait")
            bucket["arrivals"] = int(bucket["arrivals"]) + 1
            bucket["security_busy"] = float(
                bucket["security_busy"]
            ) + interval_overlap(security_start, security_end, 0.0, cutoff)
            bucket["immigration_busy"] = float(
                bucket["immigration_busy"]
            ) + interval_overlap(immigration_start, exit_seconds, 0.0, cutoff)
            bucket["security_demand"] = float(
                bucket["security_demand"]
            ) + security_demand
            bucket["immigration_demand"] = float(
                bucket["immigration_demand"]
            ) + immigration_demand
            exceed = bucket["exceed"]
            assert isinstance(exceed, dict)
            for threshold in THRESHOLDS_SECONDS:
                if total_wait > threshold:
                    exceed[threshold] = int(exceed[threshold]) + 1

    if row_count != 253756:
        raise ValueError(
            f"confirmatory entity ledger must have 253756 rows, found {row_count}"
        )
    if len(accumulators) != 600:
        raise ValueError(
            f"confirmatory diagnostics require 600 runs, found {len(accumulators)}"
        )

    rows: list[dict[str, object]] = []
    for key in sorted(
        accumulators,
        key=lambda value: (value[1], value[0], int(value[2])),
    ):
        scenario_id, input_sample_id, replication_id = key
        bucket = accumulators[key]
        arrivals = int(bucket["arrivals"])
        if arrivals <= 0:
            raise ValueError(f"run has no travellers: {key}")
        security_capacity, immigration_capacity = cells[
            (scenario_id, input_sample_id)
        ]
        level_id, arrival_rate = levels[input_sample_id]
        mean_security_demand = float(bucket["security_demand"]) / arrivals
        mean_immigration_demand = (
            float(bucket["immigration_demand"]) / arrivals
        )
        exceed = bucket["exceed"]
        assert isinstance(exceed, dict)
        rows.append(
            {
                "schema_version": "1.0",
                "study_id": study_id,
                "analysis_role": "POST_HOC_SUPPORTING_LOAD_DIAGNOSTIC",
                "scenario_id": scenario_id,
                "arrival_level_id": level_id,
                "input_sample_id": input_sample_id,
                "replication_id": replication_id,
                "arrival_rate_per_second": arrival_rate,
                "arrivals": arrivals,
                "security_capacity": security_capacity,
                "immigration_capacity": immigration_capacity,
                "security_nominal_offered_load": (
                    arrival_rate
                    * mean_security_demand
                    / security_capacity
                ),
                "immigration_nominal_offered_load": (
                    arrival_rate
                    * mean_immigration_demand
                    / immigration_capacity
                ),
                "security_arrival_window_utilization": (
                    float(bucket["security_busy"])
                    / (security_capacity * 300.0)
                ),
                "immigration_arrival_window_utilization": (
                    float(bucket["immigration_busy"])
                    / (immigration_capacity * 300.0)
                ),
                "total_queue_wait_exceed_15_rate": (
                    int(exceed[15.0]) / arrivals
                ),
                "total_queue_wait_exceed_30_rate": (
                    int(exceed[30.0]) / arrivals
                ),
                "total_queue_wait_exceed_60_rate": (
                    int(exceed[60.0]) / arrivals
                ),
            }
        )
    return rows, row_count


def summarise_diagnostics(
    rows: Sequence[Mapping[str, object]],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Return replication-level estimates and paired reference/joint contrasts."""

    grouped: dict[tuple[str, str], list[Mapping[str, object]]] = defaultdict(
        list
    )
    for row in rows:
        grouped[(str(row["scenario_id"]), str(row["input_sample_id"]))].append(
            row
        )
    if any(len(group) != 50 for group in grouped.values()):
        raise ValueError("every regime diagnostic cell must have 50 replications")

    estimates: list[dict[str, object]] = []
    for (scenario_id, input_sample_id), group in sorted(grouped.items()):
        level_id = str(group[0]["arrival_level_id"])
        for metric in REGIME_METRICS:
            summary = one_sample_summary(
                [float(row[metric]) for row in group],
                ci_level=0.95,
            )
            estimates.append(
                {
                    "schema_version": "1.0",
                    "study_id": group[0]["study_id"],
                    "analysis_role": "POST_HOC_SUPPORTING_LOAD_DIAGNOSTIC",
                    "scenario_id": scenario_id,
                    "arrival_level_id": level_id,
                    "input_sample_id": input_sample_id,
                    "metric": metric,
                    "n_replications": summary["n"],
                    "mean": summary["mean"],
                    "standard_deviation": summary["standard_deviation"],
                    "standard_error": summary["standard_error"],
                    "ci_level": 0.95,
                    "ci_low": summary["ci_low"],
                    "ci_high": summary["ci_high"],
                }
            )

    contrast_metrics = (
        "total_queue_wait_exceed_15_rate",
        "total_queue_wait_exceed_30_rate",
        "total_queue_wait_exceed_60_rate",
    )
    contrasts: list[dict[str, object]] = []
    input_sample_ids = sorted({str(row["input_sample_id"]) for row in rows})
    for input_sample_id in input_sample_ids:
        reference = grouped[(REFERENCE_SCENARIO_ID, input_sample_id)]
        joint = grouped[(JOINT_SCENARIO_ID, input_sample_id)]
        level_id = str(reference[0]["arrival_level_id"])
        for metric in contrast_metrics:
            comparison = paired_difference(
                {
                    str(row["replication_id"]): float(row[metric])
                    for row in reference
                },
                {
                    str(row["replication_id"]): float(row[metric])
                    for row in joint
                },
                ci_level=0.95,
            )
            contrasts.append(
                {
                    "schema_version": "1.0",
                    "study_id": reference[0]["study_id"],
                    "analysis_role": "POST_HOC_SUPPORTING_LOAD_DIAGNOSTIC",
                    "arrival_level_id": level_id,
                    "input_sample_id": input_sample_id,
                    "metric": metric,
                    "difference_direction": "REFERENCE_MINUS_JOINT",
                    "comparison_method": "PAIRED_STUDENT_T_AFTER_CRN_PASS",
                    "n_pairs": comparison["n_scenario"],
                    "difference_mean_percentage_points": (
                        100.0 * float(comparison["difference_mean"])
                    ),
                    "ci_level": 0.95,
                    "ci_low_percentage_points": (
                        100.0 * float(comparison["ci_low"])
                    ),
                    "ci_high_percentage_points": (
                        100.0 * float(comparison["ci_high"])
                    ),
                }
            )
    return estimates, contrasts


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--entity-log", type=Path, default=DEFAULT_ENTITY_LOG)
    parser.add_argument("--design", type=Path, default=DEFAULT_DESIGN)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--audit-manifest",
        type=Path,
        default=DEFAULT_AUDIT_MANIFEST,
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    entity_log = args.entity_log.resolve()
    design_path = args.design.resolve()
    audit = json.loads(args.audit_manifest.read_text(encoding="utf-8"))
    expected_hash = audit["source_entity_log"]["sha256"]
    actual_hash = _sha256(entity_log)
    if actual_hash != expected_hash:
        raise ValueError("entity ledger hash does not match the compact audit")
    design = json.loads(design_path.read_text(encoding="utf-8"))
    replication_rows, row_count = build_replication_diagnostics(
        entity_log,
        design,
    )
    estimates, contrasts = summarise_diagnostics(replication_rows)

    output_dir = args.output_dir.resolve()
    replication_path = output_dir / "regime_diagnostics_by_replication.csv"
    estimates_path = output_dir / "regime_estimates.csv"
    contrasts_path = output_dir / "regime_reference_joint_contrasts.csv"
    manifest_path = output_dir / "regime_diagnostics_manifest.json"
    _write_csv(replication_path, replication_rows, REPLICATION_FIELDS)
    _write_csv(estimates_path, estimates, ESTIMATE_FIELDS)
    _write_csv(contrasts_path, contrasts, CONTRAST_FIELDS)
    manifest = {
        "schema_version": "1.0",
        "analysis": "TASK3_POST_HOC_LOAD_REGIME_DIAGNOSTICS_V1",
        "study_id": design["study_id"],
        "status": "PASS",
        "analysis_role": "POST_HOC_SUPPORTING_LOAD_DIAGNOSTIC",
        "replication_row_count": len(replication_rows),
        "estimate_row_count": len(estimates),
        "contrast_row_count": len(contrasts),
        "thresholds_seconds": list(THRESHOLDS_SECONDS),
        "threshold_semantics": (
            "Illustrative model-scale diagnostics; not ICA service standards "
            "and not prospectively registered confirmatory endpoints."
        ),
        "source_entity_log": {
            "path": portable_path(entity_log),
            "tracked": False,
            "row_count": row_count,
            "sha256": actual_hash,
        },
        "outputs": {
            portable_path(replication_path): _sha256(replication_path),
            portable_path(estimates_path): _sha256(estimates_path),
            portable_path(contrasts_path): _sha256(contrasts_path),
        },
        "claim_boundary": (
            "Post-hoc supporting diagnostics conditional on the frozen "
            "assumption sandbox; not a service-level agreement, site forecast, "
            "or staffing recommendation."
        ),
    }
    _write_json(manifest_path, manifest)
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
