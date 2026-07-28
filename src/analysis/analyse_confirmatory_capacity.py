"""Fail-closed analysis for the frozen capacity robustness study."""

from __future__ import annotations

import argparse
import csv
import hashlib
import itertools
import json
import math
from pathlib import Path
from typing import Mapping, Sequence

from src.analysis.analyse_operational_replications import (
    METRICS,
    analyse_replication_rows,
    independent_difference,
    paired_difference,
    portable_path,
)
from src.analysis.confirmatory_design import (
    CAPACITY_SCENARIO_IDS,
    DEFAULT_DESIGN,
    DEFAULT_SEED_MANIFEST,
)
from src.analysis.validate_crn_alignment import (
    validate_crn_alignment,
)
from src.analysis.validate_operational_contract import REFERENCE_SCENARIO_ID
from src.analysis.validate_operational_results import (
    DEFAULT_SCHEMA_REGISTRY,
    load_result_schemas,
    read_csv,
    validate_operational_results,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RESULTS_DIR = (
    PROJECT_ROOT / "results" / "raw" / "confirmatory_capacity_consolidated"
)
DEFAULT_OUTPUT_DIR = (
    PROJECT_ROOT / "results" / "analysis" / "confirmatory_capacity"
)
DEFAULT_INTERMEDIATE_DIR = (
    PROJECT_ROOT / "results" / "intermediate" / "confirmatory_capacity"
)
PRIMARY_METRIC = "total_queue_wait_p95_seconds"

RANKING_FIELDS = (
    "schema_version",
    "study_id",
    "arrival_level_id",
    "input_sample_id",
    "point_estimate_rank",
    "scenario_id",
    "mean_seconds",
    "ci_low_seconds",
    "ci_high_seconds",
    "base_rate_rank",
    "rank_delta_from_base",
    "point_order_matches_base",
)
PAIRWISE_FIELDS = (
    "schema_version",
    "study_id",
    "arrival_level_id",
    "input_sample_id",
    "scenario_a",
    "scenario_b",
    "difference_direction",
    "comparison_method",
    "alignment_status",
    "difference_mean_seconds",
    "ci_low_seconds",
    "ci_high_seconds",
    "direction_status",
)


def _sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
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
    rows: Sequence[Mapping[str, object]],
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


def confirmatory_alignment_report_passes(
    report: object,
    *,
    study_id: str,
    design_path: Path,
    seed_manifest_path: Path,
    results_dir: Path,
) -> bool:
    """Reject incomplete, stale, foreign, or partially passing CRN reports."""

    if not isinstance(report, Mapping):
        return False
    expected_hashes = {
        "design_sha256": _sha256(design_path),
        "seed_manifest_sha256": _sha256(seed_manifest_path),
        "run_manifest_sha256": _sha256(results_dir / "run_manifest.csv"),
        "entity_log_sha256": _sha256(results_dir / "entity_log.csv"),
    }
    return (
        report.get("status") == "PASS"
        and report.get("validation")
        == "CONFIRMATORY_CAPACITY_CRN_ALIGNMENT_V1"
        and report.get("study_id") == study_id
        and report.get("coverage_pass") is True
        and report.get("seed_alignment_pass") is True
        and report.get("traveller_level_alignment_pass") is True
        and report.get("branch_invariant_draws_pass") is True
        and report.get("errors") == []
        and report.get("artifact_hashes") == expected_hashes
        and report.get("expected_run_key_sha256")
        == report.get("actual_run_key_sha256")
    )


def _direction_status(low: float, high: float) -> str:
    if high < 0:
        return "A_LOWER_RESOLVED"
    if low > 0:
        return "A_HIGHER_RESOLVED"
    return "UNRESOLVED"


def build_confirmatory_analysis(
    kpi_rows: Sequence[Mapping[str, str]],
    design: Mapping[str, object],
    *,
    alignment_verified: bool,
) -> dict[str, object]:
    """Build primary, ranking, and within-rate pairwise evidence."""

    study_id = str(design["study_id"])
    levels = {
        str(level["input_sample_id"]): str(level["level_id"])
        for level in design["arrival_rate_uncertainty"]["levels"]  # type: ignore[index]
    }
    grouped: dict[tuple[str, str], list[Mapping[str, str]]] = {}
    for key, group in itertools.groupby(
        sorted(
            kpi_rows,
            key=lambda row: (
                row["scenario_id"],
                row["input_sample_id"],
                int(row["replication_id"]),
            ),
        ),
        key=lambda row: (row["scenario_id"], row["input_sample_id"]),
    ):
        grouped[key] = list(group)
    expected_cells = {
        (scenario_id, input_sample_id)
        for input_sample_id in levels
        for scenario_id in CAPACITY_SCENARIO_IDS
    }
    if set(grouped) != expected_cells:
        missing = sorted(expected_cells - set(grouped))
        extra = sorted(set(grouped) - expected_cells)
        raise ValueError(
            f"confirmatory analysis cell mismatch; missing={missing}, extra={extra}"
        )
    if any(len(group) != 50 for group in grouped.values()):
        raise ValueError("every confirmatory analysis cell must contain 50 rows")

    estimates, contrasts = analyse_replication_rows(
        kpi_rows,
        reference_scenario_id=REFERENCE_SCENARIO_ID,
        ci_level=float(design["primary_analysis"]["confidence_level"]),  # type: ignore[index]
        alignment_verified=alignment_verified,
    )
    primary_spec = design["primary_analysis"]  # type: ignore[index]
    primary_level_id = str(primary_spec["input_level_id"])
    primary_input = next(
        input_sample_id
        for input_sample_id, level_id in levels.items()
        if level_id == primary_level_id
    )
    primary = next(
        row
        for row in contrasts
        if row["scenario_id"] == primary_spec["scenario_id"]
        and row["scenario_input_sample_id"] == primary_input
        and row["metric"] == PRIMARY_METRIC
    )
    achieved_half_width = (
        float(primary["ci_high"]) - float(primary["ci_low"])
    ) / 2.0
    target_half_width = float(
        design["precision_plan"]["target_two_sided_ci_half_width_seconds"]  # type: ignore[index]
    )
    primary_result = {
        "schema_version": "1.0",
        "study_id": study_id,
        "scenario_id": primary["scenario_id"],
        "reference_scenario_id": primary["reference_scenario_id"],
        "input_sample_id": primary_input,
        "metric": PRIMARY_METRIC,
        "comparison_method": primary["comparison_method"],
        "alignment_status": primary["alignment_status"],
        "n_scenario": primary["n_scenario"],
        "n_reference": primary["n_reference"],
        "difference_mean_seconds": primary["difference_mean"],
        "standard_error_seconds": primary["standard_error"],
        "degrees_of_freedom": primary["degrees_of_freedom"],
        "ci_level": primary["ci_level"],
        "ci_low_seconds": primary["ci_low"],
        "ci_high_seconds": primary["ci_high"],
        "achieved_half_width_seconds": achieved_half_width,
        "target_half_width_seconds": target_half_width,
        "precision_target_met": achieved_half_width <= target_half_width,
        "analysis_status": "COMPLETE",
        "claim_ceiling": design["claim_ceiling"],
    }

    estimate_lookup = {
        (str(row["scenario_id"]), str(row["input_sample_id"])): row
        for row in estimates
        if row["metric"] == PRIMARY_METRIC
    }
    rank_by_input: dict[str, dict[str, int]] = {}
    signatures: dict[str, list[str]] = {}
    tie_groups: dict[str, list[list[str]]] = {}
    for input_sample_id in levels:
        order = sorted(
            CAPACITY_SCENARIO_IDS,
            key=lambda scenario_id: (
                float(estimate_lookup[(scenario_id, input_sample_id)]["mean"]),
                scenario_id,
            ),
        )
        level_id = levels[input_sample_id]
        signatures[level_id] = order
        level_groups: list[list[str]] = []
        level_ranks: dict[str, int] = {}
        previous_mean: float | None = None
        for position, scenario_id in enumerate(order, start=1):
            mean = float(
                estimate_lookup[(scenario_id, input_sample_id)]["mean"]
            )
            if previous_mean is None or not math.isclose(
                mean,
                previous_mean,
                rel_tol=0.0,
                abs_tol=1e-12,
            ):
                level_groups.append([scenario_id])
                current_rank = position
            else:
                level_groups[-1].append(scenario_id)
            level_ranks[scenario_id] = current_rank
            previous_mean = mean
        tie_groups[level_id] = level_groups
        rank_by_input[input_sample_id] = level_ranks
    base_ranks = rank_by_input[primary_input]
    base_tie_groups = tie_groups[primary_level_id]
    ranking_rows: list[dict[str, object]] = []
    for input_sample_id, level_id in sorted(
        levels.items(), key=lambda item: item[1]
    ):
        same_order = tie_groups[level_id] == base_tie_groups
        for scenario_id in signatures[level_id]:
            estimate = estimate_lookup[(scenario_id, input_sample_id)]
            rank = rank_by_input[input_sample_id][scenario_id]
            ranking_rows.append(
                {
                    "schema_version": "1.0",
                    "study_id": study_id,
                    "arrival_level_id": level_id,
                    "input_sample_id": input_sample_id,
                    "point_estimate_rank": rank,
                    "scenario_id": scenario_id,
                    "mean_seconds": estimate["mean"],
                    "ci_low_seconds": estimate["ci_low"],
                    "ci_high_seconds": estimate["ci_high"],
                    "base_rate_rank": base_ranks[scenario_id],
                    "rank_delta_from_base": rank - base_ranks[scenario_id],
                    "point_order_matches_base": same_order,
                }
            )

    pairwise_rows: list[dict[str, object]] = []
    pair_statuses: dict[tuple[str, str], list[str]] = {}
    pair_signs: dict[tuple[str, str], list[int]] = {}
    for input_sample_id, level_id in levels.items():
        for scenario_a, scenario_b in itertools.combinations(
            CAPACITY_SCENARIO_IDS,
            2,
        ):
            rows_a = grouped[(scenario_a, input_sample_id)]
            rows_b = grouped[(scenario_b, input_sample_id)]
            if alignment_verified:
                comparison = paired_difference(
                    {
                        row["replication_id"]: float(row[PRIMARY_METRIC])
                        for row in rows_a
                    },
                    {
                        row["replication_id"]: float(row[PRIMARY_METRIC])
                        for row in rows_b
                    },
                )
                method = "PAIRED_STUDENT_T"
                alignment_status = "PASS"
            else:
                comparison = independent_difference(
                    [float(row[PRIMARY_METRIC]) for row in rows_a],
                    [float(row[PRIMARY_METRIC]) for row in rows_b],
                )
                method = "INDEPENDENT_WELCH_T"
                alignment_status = "NOT_VERIFIED"
            low = float(comparison["ci_low"])
            high = float(comparison["ci_high"])
            difference = float(comparison["difference_mean"])
            status = _direction_status(low, high)
            pair = (scenario_a, scenario_b)
            pair_statuses.setdefault(pair, []).append(status)
            pair_signs.setdefault(pair, []).append(
                -1 if difference < 0 else 1 if difference > 0 else 0
            )
            pairwise_rows.append(
                {
                    "schema_version": "1.0",
                    "study_id": study_id,
                    "arrival_level_id": level_id,
                    "input_sample_id": input_sample_id,
                    "scenario_a": scenario_a,
                    "scenario_b": scenario_b,
                    "difference_direction": "A_MINUS_B",
                    "comparison_method": method,
                    "alignment_status": alignment_status,
                    "difference_mean_seconds": difference,
                    "ci_low_seconds": low,
                    "ci_high_seconds": high,
                    "direction_status": status,
                }
            )

    point_direction_stable = all(
        len(set(signs)) == 1 for signs in pair_signs.values()
    )
    resolved_direction_stable = all(
        len({status for status in statuses if status != "UNRESOLVED"}) <= 1
        for statuses in pair_statuses.values()
    )
    stability = {
        "schema_version": "1.0",
        "study_id": study_id,
        "metric": PRIMARY_METRIC,
        "analysis_role": "SUPPORTING_POINT_ESTIMATE_RANKING",
        "rank_signature_by_level": signatures,
        "tie_groups_by_level": tie_groups,
        "point_order_stable_across_rates": (
            len(
                {
                    tuple(tuple(group) for group in groups)
                    for groups in tie_groups.values()
                }
            )
            == 1
        ),
        "pairwise_point_direction_stable_across_rates": point_direction_stable,
        "resolved_direction_stable_across_rates": resolved_direction_stable,
        "any_unresolved_pairwise_interval": any(
            status == "UNRESOLVED"
            for statuses in pair_statuses.values()
            for status in statuses
        ),
        "claim_boundary": (
            "Ranking is descriptive and rate-specific; ties and unresolved "
            "intervals preclude statistically resolved option dominance."
        ),
    }
    return {
        "estimates": estimates,
        "contrasts": contrasts,
        "primary": primary_result,
        "rankings": ranking_rows,
        "pairwise": pairwise_rows,
        "stability": stability,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--intermediate-dir",
        type=Path,
        default=DEFAULT_INTERMEDIATE_DIR,
    )
    parser.add_argument("--design", type=Path, default=DEFAULT_DESIGN)
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
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    design = json.loads(args.design.read_text(encoding="utf-8"))
    validation = validate_operational_results(
        args.results_dir.resolve(),
        schema_registry_path=args.schema_registry.resolve(),
        require_confirmatory_coverage=True,
        confirmatory_design_path=args.design.resolve(),
        confirmatory_seed_manifest_path=args.seed_manifest.resolve(),
    )
    validation_path = args.intermediate_dir / "validation.json"
    _write_json(validation_path, validation)
    if validation["status"] != "PASS":
        print(json.dumps(validation, indent=2, sort_keys=True))
        return 1

    alignment = validate_crn_alignment(
        args.results_dir.resolve(),
        args.seed_manifest.resolve(),
        design_path=args.design.resolve(),
    )
    alignment_path = args.intermediate_dir / "crn_alignment.json"
    _write_json(alignment_path, alignment)
    alignment_verified = confirmatory_alignment_report_passes(
        alignment,
        study_id=str(design["study_id"]),
        design_path=args.design.resolve(),
        seed_manifest_path=args.seed_manifest.resolve(),
        results_dir=args.results_dir.resolve(),
    )
    _, kpi_rows = read_csv(args.results_dir / "replication_kpis.csv")
    analysis = build_confirmatory_analysis(
        kpi_rows,
        design,
        alignment_verified=alignment_verified,
    )
    schemas = load_result_schemas(args.schema_registry.resolve())
    output_dir = args.output_dir
    packaged_validation_path = output_dir / "validation.json"
    packaged_alignment_path = output_dir / "crn_alignment.json"
    packaged_validation = dict(validation)
    packaged_validation["results_dir"] = portable_path(args.results_dir)
    _write_json(packaged_validation_path, packaged_validation)
    _write_json(packaged_alignment_path, alignment)
    estimates_path = output_dir / "scenario_estimates.csv"
    contrasts_path = output_dir / "scenario_contrasts.csv"
    primary_path = output_dir / "primary_result.json"
    rankings_path = output_dir / "rate_rankings.csv"
    pairwise_path = output_dir / "within_rate_pairwise_contrasts.csv"
    stability_path = output_dir / "ranking_stability.json"
    _write_csv(
        estimates_path,
        analysis["estimates"],  # type: ignore[arg-type]
        [row["field_name"] for row in schemas["scenario_estimates"]],
    )
    _write_csv(
        contrasts_path,
        analysis["contrasts"],  # type: ignore[arg-type]
        [row["field_name"] for row in schemas["scenario_contrasts"]],
    )
    _write_json(primary_path, analysis["primary"])  # type: ignore[arg-type]
    _write_csv(
        rankings_path,
        analysis["rankings"],  # type: ignore[arg-type]
        RANKING_FIELDS,
    )
    _write_csv(
        pairwise_path,
        analysis["pairwise"],  # type: ignore[arg-type]
        PAIRWISE_FIELDS,
    )
    _write_json(stability_path, analysis["stability"])  # type: ignore[arg-type]

    report = {
        "schema_version": "1.0",
        "analysis": "TASK3_CAPACITY_CONFIRMATORY_ANALYSIS_V1",
        "study_id": design["study_id"],
        "status": "PASS",
        "validation_status": validation["status"],
        "crn_alignment_status": alignment["status"],
        "comparison_method": (
            "PAIRED_STUDENT_T"
            if alignment_verified
            else "INDEPENDENT_WELCH_T"
        ),
        "welch_fallback_reason": (
            None
            if alignment_verified
            else "CRN alignment gate did not produce a current complete PASS"
        ),
        "primary": analysis["primary"],
        "ranking_stability": analysis["stability"],
        "outputs": [
            portable_path(path)
            for path in (
                estimates_path,
                contrasts_path,
                primary_path,
                rankings_path,
                pairwise_path,
                stability_path,
                packaged_validation_path,
                packaged_alignment_path,
            )
        ],
        "artifact_hashes": {
            "design_sha256": _sha256(args.design.resolve()),
            "seed_manifest_sha256": _sha256(args.seed_manifest.resolve()),
            "run_manifest_sha256": _sha256(
                args.results_dir.resolve() / "run_manifest.csv"
            ),
            "entity_log_sha256": _sha256(
                args.results_dir.resolve() / "entity_log.csv"
            ),
            "replication_kpis_sha256": _sha256(
                args.results_dir.resolve() / "replication_kpis.csv"
            ),
        },
        "claim_boundary": design["claim_ceiling"],
    }
    manifest_path = output_dir / "analysis_manifest.json"
    _write_json(manifest_path, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
