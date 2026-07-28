"""Validate exogenous-draw alignment before enabling paired CRN analysis.

A shared seed is necessary but not sufficient.  PASS requires exact expected
run coverage, prescribed stream seeds, identical traveller IDs within every
pairing group, and equality of all recorded branch-invariant exogenous draws.
Downstream queue and service timestamps are deliberately allowed to differ.
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

from src.analysis.confirmatory_design import DEFAULT_DESIGN, DEFAULT_SEED_MANIFEST


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RESULTS_DIR = PROJECT_ROOT / "results" / "raw" / "confirmatory_capacity"
DEFAULT_REPORT = (
    PROJECT_ROOT
    / "results"
    / "intermediate"
    / "confirmatory_capacity"
    / "crn_alignment.json"
)
RUN_MANIFEST = "run_manifest.csv"
ENTITY_LOG = "entity_log.csv"

STREAM_SEED_FIELDS = (
    "arrival_seed",
    "service_seed",
    "routing_seed",
    "tie_seed",
)
DRAW_FIELDS = (
    "arrival_seconds",
    "security_service_demand_seconds",
    "immigration_conventional_service_demand_seconds",
    "automation_u",
    "additional_check_u",
    "lane_tie_u",
)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _key_digest(keys: Sequence[tuple[str, str, str]]) -> str:
    payload = json.dumps(
        [list(key) for key in sorted(keys)],
        ensure_ascii=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _run_key(row: Mapping[str, str]) -> tuple[str, str, str]:
    return (
        row.get("scenario_id", ""),
        row.get("input_sample_id", ""),
        row.get("replication_id", ""),
    )


def _same_numeric(left: str, right: str, tolerance: float) -> bool:
    try:
        left_number = float(left)
        right_number = float(right)
    except ValueError:
        return left == right
    return (
        math.isfinite(left_number)
        and math.isfinite(right_number)
        and math.isclose(
            left_number,
            right_number,
            rel_tol=tolerance,
            abs_tol=tolerance,
        )
    )


def validate_crn_alignment(
    results_dir: Path = DEFAULT_RESULTS_DIR,
    seed_manifest_path: Path = DEFAULT_SEED_MANIFEST,
    *,
    design_path: Path = DEFAULT_DESIGN,
    numeric_tolerance: float = 1e-9,
) -> dict[str, object]:
    """Return an explicit alignment report consumable by the analysis gate."""

    errors: list[str] = []
    run_manifest_path = results_dir / RUN_MANIFEST
    entity_log_path = results_dir / ENTITY_LOG
    artifact_hashes = {
        "design_sha256": _sha256(design_path),
        "seed_manifest_sha256": _sha256(seed_manifest_path),
        "run_manifest_sha256": _sha256(run_manifest_path),
        "entity_log_sha256": _sha256(entity_log_path),
    }
    try:
        design = json.loads(design_path.read_text(encoding="utf-8"))
        seed_rows = _read_csv(seed_manifest_path)
        run_rows = _read_csv(run_manifest_path)
        entity_rows = _read_csv(entity_log_path)
    except (FileNotFoundError, json.JSONDecodeError, KeyError, ValueError) as exc:
        return {
            "status": "FAIL",
            "validation": "CONFIRMATORY_CAPACITY_CRN_ALIGNMENT_V1",
            "study_id": None,
            "coverage_pass": False,
            "seed_alignment_pass": False,
            "traveller_level_alignment_pass": False,
            "branch_invariant_draws_pass": False,
            "artifact_hashes": artifact_hashes,
            "expected_run_key_sha256": None,
            "actual_run_key_sha256": None,
            "errors": [str(exc)],
        }
    study_id = str(design.get("study_id", ""))
    seed_studies = {row.get("study_id", "") for row in seed_rows}
    if seed_studies != {study_id}:
        errors.append("seed manifest study_id does not match frozen design")

    expected_runs: dict[tuple[str, str, str], dict[str, str]] = {}
    group_scenarios: dict[str, list[str]] = {}
    group_input: dict[str, tuple[str, str]] = {}
    for line, seed_row in enumerate(seed_rows, start=2):
        group_id = seed_row["pairing_group_id"]
        scenarios = [
            value for value in seed_row["scenario_ids"].split("|") if value
        ]
        if len(scenarios) < 2:
            errors.append(
                f"seed manifest line {line}: pairing group needs at least two scenarios"
            )
        group_scenarios[group_id] = scenarios
        group_input[group_id] = (
            seed_row["input_sample_id"],
            seed_row["replication_id"],
        )
        for scenario_id in scenarios:
            key = (
                scenario_id,
                seed_row["input_sample_id"],
                seed_row["replication_id"],
            )
            if key in expected_runs:
                errors.append(f"seed manifest line {line}: duplicate expected run {key}")
            expected_runs[key] = seed_row

    actual_runs: dict[tuple[str, str, str], dict[str, str]] = {}
    for line, run in enumerate(run_rows, start=2):
        key = _run_key(run)
        if key in actual_runs:
            errors.append(f"{RUN_MANIFEST}:{line}: duplicate run key {key}")
        actual_runs[key] = run
    missing_runs = sorted(set(expected_runs) - set(actual_runs))
    unexpected_runs = sorted(set(actual_runs) - set(expected_runs))
    for key in missing_runs:
        errors.append(f"missing expected run {key}")
    for key in unexpected_runs:
        errors.append(f"unexpected run {key}")

    seed_errors: list[str] = []
    for key in sorted(set(expected_runs) & set(actual_runs)):
        expected = expected_runs[key]
        actual = actual_runs[key]
        if actual.get("run_status") != "COMPLETE":
            seed_errors.append(f"{key}: run_status must be COMPLETE")
        if actual.get("master_seed") != expected.get("master_seed"):
            seed_errors.append(f"{key}: master_seed mismatch")
        for field in STREAM_SEED_FIELDS:
            if actual.get(field) != expected.get(field):
                seed_errors.append(f"{key}: {field} mismatch")
    errors.extend(seed_errors)

    entities_by_run: dict[
        tuple[str, str, str], dict[str, dict[str, str]]
    ] = defaultdict(dict)
    entity_errors: list[str] = []
    for line, entity in enumerate(entity_rows, start=2):
        key = _run_key(entity)
        if key not in expected_runs:
            entity_errors.append(f"{ENTITY_LOG}:{line}: unexpected run key {key}")
            continue
        traveller_id = entity.get("traveller_id", "")
        if not traveller_id:
            entity_errors.append(f"{ENTITY_LOG}:{line}: empty traveller_id")
            continue
        if traveller_id in entities_by_run[key]:
            entity_errors.append(
                f"{ENTITY_LOG}:{line}: duplicate traveller_id {traveller_id}"
            )
        entities_by_run[key][traveller_id] = entity
    errors.extend(entity_errors)

    traveller_errors: list[str] = []
    draw_errors: list[str] = []
    compared_travellers = 0
    compared_values = 0
    for group_id, scenarios in group_scenarios.items():
        input_sample_id, replication_id = group_input[group_id]
        if not scenarios:
            continue
        reference_key = (scenarios[0], input_sample_id, replication_id)
        if reference_key not in actual_runs:
            continue
        reference_entities = entities_by_run.get(reference_key, {})
        if not reference_entities:
            traveller_errors.append(f"{group_id}: reference run has no entities")
            continue
        reference_ids = set(reference_entities)
        for scenario_id in scenarios[1:]:
            comparison_key = (scenario_id, input_sample_id, replication_id)
            if comparison_key not in actual_runs:
                continue
            comparison_entities = entities_by_run.get(comparison_key, {})
            comparison_ids = set(comparison_entities)
            missing_ids = sorted(reference_ids - comparison_ids)
            extra_ids = sorted(comparison_ids - reference_ids)
            if missing_ids or extra_ids:
                traveller_errors.append(
                    f"{group_id}:{scenario_id}: traveller IDs differ "
                    f"(missing={len(missing_ids)}, extra={len(extra_ids)})"
                )
                continue
            compared_travellers += len(reference_ids)
            for traveller_id in sorted(reference_ids):
                reference = reference_entities[traveller_id]
                comparison = comparison_entities[traveller_id]
                for field in DRAW_FIELDS:
                    compared_values += 1
                    if not _same_numeric(
                        reference.get(field, ""),
                        comparison.get(field, ""),
                        numeric_tolerance,
                    ):
                        draw_errors.append(
                            f"{group_id}:{scenario_id}:{traveller_id}: "
                            f"{field} differs"
                        )
    errors.extend(traveller_errors)
    errors.extend(draw_errors)

    coverage_pass = not missing_runs and not unexpected_runs
    seed_alignment_pass = coverage_pass and not seed_errors
    traveller_level_alignment_pass = (
        coverage_pass and not entity_errors and not traveller_errors
    )
    branch_invariant_draws_pass = (
        traveller_level_alignment_pass
        and compared_values > 0
        and not draw_errors
    )
    status = (
        "PASS"
        if seed_alignment_pass
        and traveller_level_alignment_pass
        and branch_invariant_draws_pass
        and not errors
        else "FAIL"
    )
    return {
        "status": status,
        "validation": "CONFIRMATORY_CAPACITY_CRN_ALIGNMENT_V1",
        "study_id": study_id,
        "coverage_pass": coverage_pass,
        "seed_alignment_pass": seed_alignment_pass,
        "traveller_level_alignment_pass": traveller_level_alignment_pass,
        "branch_invariant_draws_pass": branch_invariant_draws_pass,
        "expected_run_count": len(expected_runs),
        "actual_run_count": len(actual_runs),
        "pairing_group_count": len(group_scenarios),
        "entity_row_count": len(entity_rows),
        "compared_traveller_pairs": compared_travellers,
        "compared_draw_values": compared_values,
        "numeric_tolerance": numeric_tolerance,
        "draw_fields": list(DRAW_FIELDS),
        "artifact_hashes": artifact_hashes,
        "expected_run_key_sha256": _key_digest(list(expected_runs)),
        "actual_run_key_sha256": _key_digest(list(actual_runs)),
        "errors": errors,
        "claim_rule": (
            "Paired CRN analysis is permitted only when status, seed alignment, "
            "traveller-level alignment, and branch-invariant draws all PASS."
        ),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate confirmatory traveller-level CRN alignment"
    )
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS_DIR)
    parser.add_argument(
        "--seed-manifest", type=Path, default=DEFAULT_SEED_MANIFEST
    )
    parser.add_argument("--design", type=Path, default=DEFAULT_DESIGN)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--numeric-tolerance", type=float, default=1e-9)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = validate_crn_alignment(
        args.results_dir,
        args.seed_manifest,
        design_path=args.design,
        numeric_tolerance=args.numeric_tolerance,
    )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.report.with_suffix(args.report.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(report, indent=2, sort_keys=True) + "\n")
    temporary.replace(args.report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
