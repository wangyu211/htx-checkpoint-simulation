"""Fail-closed public-release checks for the HTX assessment repository."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CANONICAL_DECK = "slides/HTX_Task4_Operational_Insights.pptx"
REQUIRED_TRACKED = {
    "README.md",
    "LICENSING.md",
    "THIRD_PARTY_NOTICES.md",
    "config/confirmatory_capacity_study.json",
    "config/confirmatory_seed_manifest.csv",
    "data/derived/task1_final_aggregate.csv",
    "docs/task1_measurement.md",
    "docs/task2_system_design.md",
    "docs/task3_results.md",
    "docs/task3_confirmatory_design.md",
    "results/analysis/operational/audit_manifest.json",
    "results/analysis/operational/replication_kpis.csv",
    "results/analysis/operational/run_manifest.csv",
    "results/analysis/operational/validation.json",
    "results/analysis/confirmatory_capacity/README.md",
    "results/analysis/confirmatory_capacity/analysis_manifest.json",
    "results/analysis/confirmatory_capacity/audit_manifest.json",
    "results/analysis/confirmatory_capacity/crn_alignment.json",
    "results/analysis/confirmatory_capacity/primary_result.json",
    "results/analysis/confirmatory_capacity/ranking_stability.json",
    "results/analysis/confirmatory_capacity/rate_rankings.csv",
    "results/analysis/confirmatory_capacity/replication_kpis.csv",
    "results/analysis/confirmatory_capacity/run_manifest.csv",
    "results/analysis/confirmatory_capacity/scenario_contrasts.csv",
    "results/analysis/confirmatory_capacity/scenario_estimates.csv",
    "results/analysis/confirmatory_capacity/validation.json",
    "results/analysis/confirmatory_capacity/within_rate_pairwise_contrasts.csv",
    CANONICAL_DECK,
}
TEXT_SUFFIXES = {".csv", ".json", ".md", ".ps1", ".py", ".txt"}
MARKDOWN_LINK = re.compile(r"!?\[[^\]]*]\(([^)]+)\)")
WINDOWS_USER_PATH = re.compile(r"[A-Za-z]:[\\/]+Users[\\/]+[^\\/]+", re.I)


def git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def tracked_files() -> set[str]:
    result = git("ls-files")
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "git ls-files failed")
    return {
        line.strip().replace("\\", "/")
        for line in result.stdout.splitlines()
        if line.strip()
    }


def local_link_target(source: Path, raw_target: str) -> Path | None:
    target = raw_target.strip().strip("<>")
    if not target or target.startswith("#"):
        return None
    if re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", target):
        return None
    target = unquote(target.split("#", 1)[0].split("?", 1)[0])
    if not target:
        return None
    return (source.parent / Path(target)).resolve()


def check_markdown_links(
    tracked: set[str],
) -> tuple[list[str], int]:
    errors: list[str] = []
    checked = 0
    for relative in sorted(tracked):
        if not relative.lower().endswith(".md"):
            continue
        source = PROJECT_ROOT / relative
        text = source.read_text(encoding="utf-8")
        for raw_target in MARKDOWN_LINK.findall(text):
            target = local_link_target(source, raw_target)
            if target is None:
                continue
            checked += 1
            try:
                target_relative = target.relative_to(PROJECT_ROOT).as_posix()
            except ValueError:
                errors.append(f"{relative}: link escapes repository: {raw_target}")
                continue
            if not target.exists():
                errors.append(f"{relative}: missing link target: {raw_target}")
            elif target.is_file() and target_relative not in tracked:
                errors.append(
                    f"{relative}: linked file is not tracked: {target_relative}"
                )
    return errors, checked


def check_user_paths(tracked: set[str]) -> list[str]:
    errors: list[str] = []
    for relative in sorted(tracked):
        path = PROJECT_ROOT / relative
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        match = WINDOWS_USER_PATH.search(text)
        if match:
            errors.append(
                f"{relative}: contains a machine-specific user path: "
                f"{match.group(0)}"
            )
    return errors


def validate_compact_audit() -> list[str]:
    errors: list[str] = []
    manifest_path = (
        PROJECT_ROOT / "results" / "analysis" / "operational" / "audit_manifest.json"
    )
    validation_path = (
        PROJECT_ROOT / "results" / "analysis" / "operational" / "validation.json"
    )
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        validation = json.loads(validation_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        return [f"compact audit package is unreadable: {exc}"]
    if manifest.get("status") != "PASS":
        errors.append("operational audit manifest status is not PASS")
    if validation.get("status") != "PASS" or validation.get("errors"):
        errors.append("tracked operational validation report is not a clean PASS")
    if validation.get("run_count") != 150:
        errors.append("tracked operational validation report must record 150 runs")
    if validation.get("entity_count") != 61218:
        errors.append(
            "tracked operational validation report must record 61,218 entities"
        )
    return errors


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_confirmatory_audit() -> list[str]:
    errors: list[str] = []
    root = PROJECT_ROOT / "results" / "analysis" / "confirmatory_capacity"
    try:
        audit = json.loads(
            (root / "audit_manifest.json").read_text(encoding="utf-8")
        )
        validation = json.loads(
            (root / "validation.json").read_text(encoding="utf-8")
        )
        alignment = json.loads(
            (root / "crn_alignment.json").read_text(encoding="utf-8")
        )
        primary = json.loads(
            (root / "primary_result.json").read_text(encoding="utf-8")
        )
        analysis_manifest = json.loads(
            (root / "analysis_manifest.json").read_text(encoding="utf-8")
        )
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        return [f"confirmatory compact audit package is unreadable: {exc}"]

    if audit.get("status") != "PASS":
        errors.append("confirmatory audit manifest status is not PASS")
    if audit.get("run_count") != 600 or audit.get("entity_count") != 253756:
        errors.append(
            "confirmatory audit manifest must record 600 runs and 253,756 entities"
        )
    if audit.get("pairing_group_count") != 150:
        errors.append(
            "confirmatory audit manifest must record 150 CRN pairing groups"
        )
    if audit.get("comparison_method") != "PAIRED_STUDENT_T":
        errors.append(
            "confirmatory audit manifest must record the validated paired method"
        )

    if (
        validation.get("status") != "PASS"
        or validation.get("errors")
        or validation.get("run_count") != 600
        or validation.get("entity_count") != 253756
    ):
        errors.append("confirmatory validation report is not a clean 600-run PASS")

    output_inventory = analysis_manifest.get("outputs")
    if not isinstance(output_inventory, list):
        errors.append("confirmatory analysis manifest has no output inventory")
    else:
        expected_prefix = "results/analysis/confirmatory_capacity/"
        for relative in output_inventory:
            if not isinstance(relative, str) or not relative.startswith(
                expected_prefix
            ):
                errors.append(
                    "confirmatory analysis output is not self-contained: "
                    f"{relative}"
                )
                continue
            if not (PROJECT_ROOT / relative).is_file():
                errors.append(
                    f"confirmatory analysis output is missing: {relative}"
                )

    required_alignment = {
        "coverage_pass": True,
        "seed_alignment_pass": True,
        "traveller_level_alignment_pass": True,
        "branch_invariant_draws_pass": True,
    }
    if alignment.get("status") != "PASS" or alignment.get("errors"):
        errors.append("confirmatory CRN report is not a clean PASS")
    for field, expected in required_alignment.items():
        if alignment.get(field) is not expected:
            errors.append(f"confirmatory CRN report field {field} is not true")

    if (
        primary.get("analysis_status") != "COMPLETE"
        or primary.get("comparison_method") != "PAIRED_STUDENT_T"
        or primary.get("alignment_status") != "PASS"
        or primary.get("precision_target_met") is not True
        or primary.get("n_scenario") != 50
        or primary.get("n_reference") != 50
    ):
        errors.append("confirmatory primary result failed its execution contract")
    half_width = primary.get("achieved_half_width_seconds")
    target = primary.get("target_half_width_seconds")
    if not isinstance(half_width, (int, float)) or not isinstance(
        target, (int, float)
    ):
        errors.append("confirmatory primary precision values are missing")
    elif half_width > target:
        errors.append("confirmatory primary interval missed its frozen target")
    ci_low = primary.get("ci_low_seconds")
    ci_high = primary.get("ci_high_seconds")
    if (
        not isinstance(ci_low, (int, float))
        or not isinstance(ci_high, (int, float))
        or not (ci_low < ci_high < 0)
    ):
        errors.append(
            "confirmatory primary interval must resolve a negative joint-minus-reference difference"
        )

    tracked_hashes = audit.get("tracked_artifacts")
    if not isinstance(tracked_hashes, dict):
        errors.append("confirmatory audit manifest has no tracked-artifact hashes")
    else:
        for name, expected in tracked_hashes.items():
            path = root / str(name)
            if not path.is_file():
                errors.append(f"confirmatory audit artifact is missing: {name}")
            elif sha256(path) != expected:
                errors.append(f"confirmatory audit artifact hash mismatch: {name}")

    entity_evidence = audit.get("source_entity_log")
    if (
        not isinstance(entity_evidence, dict)
        or entity_evidence.get("tracked") is not False
        or entity_evidence.get("row_count") != 253756
        or entity_evidence.get("sha256")
        != "7fea0ee6215f277b1ef48cd9d2dab18ea1b761158b66a037fbd9012f644b2657"
    ):
        errors.append("confirmatory entity-log hash evidence is incomplete")
    return errors


def run_tests() -> list[str]:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "unittest",
            "discover",
            "-s",
            "tests",
            "-v",
        ],
        cwd=PROJECT_ROOT,
        check=False,
        text=True,
        encoding="utf-8",
    )
    if result.returncode:
        return ["test suite failed"]
    return []


def precheck(*, require_clean: bool, execute_tests: bool) -> dict[str, object]:
    errors: list[str] = []
    tracked = tracked_files()

    missing_required = sorted(REQUIRED_TRACKED - tracked)
    errors.extend(f"required file is not tracked: {path}" for path in missing_required)

    decks = sorted(path for path in tracked if path.lower().endswith(".pptx"))
    if decks != [CANONICAL_DECK]:
        errors.append(
            "exactly one tracked PPTX is required at "
            f"{CANONICAL_DECK}; found {decks}"
        )

    restricted_inputs = sorted(
        path
        for path in tracked
        if path.startswith("data/raw/") and path != "data/raw/README.md"
    )
    errors.extend(
        f"restricted raw input must not be tracked: {path}"
        for path in restricted_inputs
    )

    oversized = sorted(
        path
        for path in tracked
        if (PROJECT_ROOT / path).is_file()
        and (PROJECT_ROOT / path).stat().st_size >= 95_000_000
    )
    errors.extend(f"tracked file is at least 95 MB: {path}" for path in oversized)

    link_errors, link_count = check_markdown_links(tracked)
    errors.extend(link_errors)
    errors.extend(check_user_paths(tracked))
    errors.extend(validate_compact_audit())
    errors.extend(validate_confirmatory_audit())

    if require_clean:
        status = git("status", "--porcelain")
        if status.returncode or status.stdout.strip():
            errors.append("git worktree/index is not clean")

    if execute_tests:
        errors.extend(run_tests())

    return {
        "status": "PASS" if not errors else "FAIL",
        "tracked_file_count": len(tracked),
        "markdown_local_links_checked": link_count,
        "require_clean": require_clean,
        "tests_executed": execute_tests,
        "errors": errors,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--require-clean",
        action="store_true",
        help="Fail when the Git index or worktree contains changes.",
    )
    parser.add_argument(
        "--run-tests",
        action="store_true",
        help="Run the complete unittest suite as part of the gate.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    report = precheck(
        require_clean=args.require_clean,
        execute_tests=args.run_tests,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
