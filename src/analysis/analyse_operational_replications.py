"""Summarise replication-level KPIs and scenario-minus-reference differences.

The statistical sample is the set of replication-level KPI rows.  Traveller
rows are never pooled and treated as independent replications.  Paired
Student-t differences are enabled only after an explicit traveller-level CRN
alignment report passes; otherwise the script uses an independent Welch
interval.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from scipy.stats import t as student_t

from src.analysis.validate_operational_contract import (
    REFERENCE_SCENARIO_ID,
)
from src.analysis.validate_operational_results import (
    DEFAULT_RESULTS_DIR,
    DEFAULT_SCHEMA_REGISTRY,
    load_result_schemas,
    read_csv,
    validate_operational_results,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "results" / "analysis" / "operational"
DEFAULT_ALIGNMENT_REPORT = (
    PROJECT_ROOT
    / "results"
    / "intermediate"
    / "operational_results"
    / "crn_alignment.json"
)
ANALYSIS_SCHEMA_VERSION = "1.0"
ESTIMAND = "MEAN_OF_REPLICATION_LEVEL_METRIC"

METRICS = (
    "total_queue_wait_p95_seconds",
    "total_queue_wait_mean_seconds",
    "security_wait_p95_seconds",
    "immigration_wait_p95_seconds",
    "total_queue_wait_exceed_600_rate",
    "total_queue_wait_exceed_900_rate",
    "total_queue_wait_exceed_1200_rate",
    "security_utilization",
    "immigration_utilization",
    "cutoff_backlog_fraction",
    "cohort_clear_time_after_cutoff_seconds",
)


def _finite_values(
    rows: Iterable[Mapping[str, str]], field: str
) -> list[float]:
    values: list[float] = []
    for row in rows:
        value = float(row[field])
        if not math.isfinite(value):
            raise ValueError(f"{field} contains a non-finite value")
        values.append(value)
    return values


def one_sample_summary(
    values: Sequence[float], *, ci_level: float = 0.95
) -> dict[str, float | int]:
    """Return a two-sided Student-t interval for a replication-level mean."""

    if len(values) < 2:
        raise ValueError("at least two replications are required for a t interval")
    if not 0 < ci_level < 1:
        raise ValueError("ci_level must be between 0 and 1")
    mean = statistics.fmean(values)
    standard_deviation = statistics.stdev(values)
    standard_error = standard_deviation / math.sqrt(len(values))
    critical = float(
        student_t.ppf(0.5 + ci_level / 2, df=len(values) - 1)
    )
    half_width = critical * standard_error
    return {
        "n": len(values),
        "mean": mean,
        "standard_deviation": standard_deviation,
        "standard_error": standard_error,
        "degrees_of_freedom": float(len(values) - 1),
        "ci_low": mean - half_width,
        "ci_high": mean + half_width,
    }


def independent_difference(
    scenario_values: Sequence[float],
    reference_values: Sequence[float],
    *,
    ci_level: float = 0.95,
) -> dict[str, float | int]:
    """Welch interval for scenario minus reference."""

    scenario = one_sample_summary(scenario_values, ci_level=ci_level)
    reference = one_sample_summary(reference_values, ci_level=ci_level)
    n_s = int(scenario["n"])
    n_r = int(reference["n"])
    var_s = float(scenario["standard_deviation"]) ** 2
    var_r = float(reference["standard_deviation"]) ** 2
    component_s = var_s / n_s
    component_r = var_r / n_r
    standard_error = math.sqrt(component_s + component_r)
    denominator = (
        component_s**2 / (n_s - 1) + component_r**2 / (n_r - 1)
    )
    if denominator == 0:
        degrees_of_freedom = float(n_s + n_r - 2)
    else:
        degrees_of_freedom = (component_s + component_r) ** 2 / denominator
    difference = float(scenario["mean"]) - float(reference["mean"])
    critical = float(
        student_t.ppf(0.5 + ci_level / 2, df=degrees_of_freedom)
    )
    half_width = critical * standard_error
    return {
        "n_scenario": n_s,
        "n_reference": n_r,
        "difference_mean": difference,
        "standard_error": standard_error,
        "degrees_of_freedom": degrees_of_freedom,
        "ci_low": difference - half_width,
        "ci_high": difference + half_width,
    }


def paired_difference(
    scenario_by_replication: Mapping[str, float],
    reference_by_replication: Mapping[str, float],
    *,
    ci_level: float = 0.95,
) -> dict[str, float | int]:
    """Paired interval after an external traveller-level alignment gate."""

    if set(scenario_by_replication) != set(reference_by_replication):
        raise ValueError("paired comparison requires identical replication IDs")
    keys = sorted(scenario_by_replication, key=lambda value: int(value))
    differences = [
        scenario_by_replication[key] - reference_by_replication[key]
        for key in keys
    ]
    summary = one_sample_summary(differences, ci_level=ci_level)
    return {
        "n_scenario": len(keys),
        "n_reference": len(keys),
        "difference_mean": summary["mean"],
        "standard_error": summary["standard_error"],
        "degrees_of_freedom": summary["degrees_of_freedom"],
        "ci_low": summary["ci_low"],
        "ci_high": summary["ci_high"],
    }


def alignment_report_passes(report: object) -> bool:
    """Require explicit traveller/draw alignment, not a generic PASS string."""

    return (
        isinstance(report, Mapping)
        and report.get("status") == "PASS"
        and report.get("traveller_level_alignment_pass") is True
        and report.get("branch_invariant_draws_pass") is True
    )


def analyse_replication_rows(
    rows: Sequence[Mapping[str, str]],
    *,
    reference_scenario_id: str = REFERENCE_SCENARIO_ID,
    ci_level: float = 0.95,
    alignment_verified: bool = False,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Build scenario estimates and controlled difference intervals."""

    grouped: dict[
        tuple[str, str], list[Mapping[str, str]]
    ] = defaultdict(list)
    for row in rows:
        grouped[(row["scenario_id"], row["input_sample_id"])].append(row)
    if not grouped:
        raise ValueError("replication KPI table is empty")

    estimates: list[dict[str, object]] = []
    for (scenario_id, input_sample_id), group in sorted(grouped.items()):
        replication_ids = [row["replication_id"] for row in group]
        if len(replication_ids) != len(set(replication_ids)):
            raise ValueError(
                f"{scenario_id}/{input_sample_id} has duplicate replications"
            )
        for metric in METRICS:
            summary = one_sample_summary(
                _finite_values(group, metric), ci_level=ci_level
            )
            estimates.append(
                {
                    "schema_version": ANALYSIS_SCHEMA_VERSION,
                    "scenario_id": scenario_id,
                    "input_sample_id": input_sample_id,
                    "metric": metric,
                    "estimand": ESTIMAND,
                    "n_replications": summary["n"],
                    "mean": summary["mean"],
                    "standard_deviation": summary["standard_deviation"],
                    "standard_error": summary["standard_error"],
                    "ci_level": ci_level,
                    "ci_low": summary["ci_low"],
                    "ci_high": summary["ci_high"],
                    "analysis_status": "COMPLETE",
                }
            )

    reference_groups = {
        sample_id: group
        for (scenario_id, sample_id), group in grouped.items()
        if scenario_id == reference_scenario_id
    }
    if not reference_groups:
        raise ValueError(f"missing reference scenario {reference_scenario_id}")
    only_reference_sample = (
        next(iter(reference_groups)) if len(reference_groups) == 1 else None
    )

    contrasts: list[dict[str, object]] = []
    for (scenario_id, scenario_sample_id), scenario_group in sorted(
        grouped.items()
    ):
        if scenario_id == reference_scenario_id:
            continue
        reference_sample_id = (
            scenario_sample_id
            if scenario_sample_id in reference_groups
            else only_reference_sample
        )
        if reference_sample_id is None:
            raise ValueError(
                f"{scenario_id}/{scenario_sample_id} has no matched reference "
                "input sample"
            )
        reference_group = reference_groups[reference_sample_id]
        can_pair = (
            alignment_verified
            and scenario_sample_id == reference_sample_id
            and {
                row["replication_id"] for row in scenario_group
            }
            == {row["replication_id"] for row in reference_group}
        )
        for metric in METRICS:
            if can_pair:
                comparison = paired_difference(
                    {
                        row["replication_id"]: float(row[metric])
                        for row in scenario_group
                    },
                    {
                        row["replication_id"]: float(row[metric])
                        for row in reference_group
                    },
                    ci_level=ci_level,
                )
                method = "PAIRED_STUDENT_T"
                alignment_status = "PASS"
            else:
                comparison = independent_difference(
                    _finite_values(scenario_group, metric),
                    _finite_values(reference_group, metric),
                    ci_level=ci_level,
                )
                method = "INDEPENDENT_WELCH_T"
                alignment_status = (
                    "NOT_APPLICABLE_DIFFERENT_INPUT_SAMPLE"
                    if scenario_sample_id != reference_sample_id
                    else "NOT_VERIFIED"
                )
            contrasts.append(
                {
                    "schema_version": ANALYSIS_SCHEMA_VERSION,
                    "scenario_id": scenario_id,
                    "reference_scenario_id": reference_scenario_id,
                    "scenario_input_sample_id": scenario_sample_id,
                    "reference_input_sample_id": reference_sample_id,
                    "metric": metric,
                    "difference_direction": "SCENARIO_MINUS_REFERENCE",
                    "comparison_method": method,
                    "alignment_status": alignment_status,
                    **comparison,
                    "ci_level": ci_level,
                    "analysis_status": "COMPLETE",
                }
            )
    return estimates, contrasts


def _write_rows(
    path: Path, rows: Sequence[Mapping[str, object]], fieldnames: Sequence[str]
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--schema-registry", type=Path, default=DEFAULT_SCHEMA_REGISTRY
    )
    parser.add_argument(
        "--reference-scenario-id", default=REFERENCE_SCENARIO_ID
    )
    parser.add_argument("--ci-level", type=float, default=0.95)
    parser.add_argument(
        "--alignment-report",
        type=Path,
        default=DEFAULT_ALIGNMENT_REPORT,
        help=(
            "Optional CRN alignment JSON. Paired analysis is used only when "
            "the report explicitly passes traveller and draw alignment."
        ),
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    validation = validate_operational_results(
        args.results_dir.resolve(),
        schema_registry_path=args.schema_registry.resolve(),
        require_pilot_coverage=True,
    )
    if validation["status"] != "PASS":
        print(json.dumps(validation, indent=2, sort_keys=True))
        return 1

    alignment: object = {}
    if args.alignment_report.is_file():
        alignment = json.loads(args.alignment_report.read_text(encoding="utf-8"))
    alignment_verified = alignment_report_passes(alignment)

    _, rows = read_csv(args.results_dir / "replication_kpis.csv")
    estimates, contrasts = analyse_replication_rows(
        rows,
        reference_scenario_id=args.reference_scenario_id,
        ci_level=args.ci_level,
        alignment_verified=alignment_verified,
    )
    schemas = load_result_schemas(args.schema_registry.resolve())
    estimates_path = args.output_dir / "scenario_estimates.csv"
    contrasts_path = args.output_dir / "scenario_contrasts.csv"
    _write_rows(
        estimates_path,
        estimates,
        [row["field_name"] for row in schemas["scenario_estimates"]],
    )
    _write_rows(
        contrasts_path,
        contrasts,
        [row["field_name"] for row in schemas["scenario_contrasts"]],
    )
    report = {
        "analysis": "TASK3_REPLICATION_KPI_AND_CI_V1",
        "status": "PASS",
        "reference_scenario_id": args.reference_scenario_id,
        "ci_level": args.ci_level,
        "primary_estimand": (
            "mean of replication-level total_queue_wait_p95_seconds"
        ),
        "alignment_verified": alignment_verified,
        "default_unverified_comparison": "INDEPENDENT_WELCH_T",
        "estimate_rows": len(estimates),
        "contrast_rows": len(contrasts),
        "outputs": [str(estimates_path), str(contrasts_path)],
        "claim_boundary": (
            "Monte Carlo uncertainty conditional on the assumption scenarios; "
            "not input uncertainty or operational calibration."
        ),
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "analysis_manifest.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
