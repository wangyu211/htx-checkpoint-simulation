"""Exercise the release gate from a real local Git clone of one revision.

The clone is created by Git, not by copying the source worktree. Consequently,
ignored assessment video, review sheets, model weights, raw simulation output,
virtual environments, and other private working files are not transferred.
No network access, push, publication, or mutation of the source repository is
performed.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_HISTORY_PREFIXES = {
    ".venv/",
    ".venv-bytetrack/",
    "_work/",
    "results/intermediate/",
    "results/raw/",
}
FORBIDDEN_HISTORY_SUFFIXES = {".mov", ".mp4", ".onnx", ".pt", ".pth"}


def git(
    root: Path,
    *args: str,
    timeout_seconds: int = 180,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=timeout_seconds,
    )


def _forbidden_public_path(relative: str) -> bool:
    normalized = relative.replace("\\", "/").lstrip("./").casefold()
    if normalized.startswith("data/raw/") and normalized != "data/raw/readme.md":
        return True
    if any(normalized.startswith(prefix) for prefix in FORBIDDEN_HISTORY_PREFIXES):
        return True
    return Path(normalized).suffix in FORBIDDEN_HISTORY_SUFFIXES


def forbidden_history_paths(source: Path) -> list[str]:
    """Return known private path classes ever named in reachable history."""

    result = git(source, "rev-list", "--objects", "--all")
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "git rev-list failed")
    forbidden: set[str] = set()
    for line in result.stdout.splitlines():
        _, separator, relative = line.partition(" ")
        if separator and _forbidden_public_path(relative):
            forbidden.add(relative.replace("\\", "/"))
    return sorted(forbidden)


def ignored_source_paths(source: Path) -> list[str]:
    """List ignored worktree paths so their non-transfer can be verified."""

    result = git(
        source,
        "ls-files",
        "--others",
        "--ignored",
        "--exclude-standard",
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "git ls-files failed")
    return sorted(
        relative.replace("\\", "/")
        for relative in result.stdout.splitlines()
        if relative.strip()
    )


def source_revision(source: Path, revision: str) -> str:
    result = git(source, "rev-parse", "--verify", f"{revision}^{{commit}}")
    if result.returncode:
        raise RuntimeError(
            result.stderr.strip() or f"cannot resolve revision {revision}"
        )
    return result.stdout.strip()


def source_is_clean(source: Path) -> tuple[bool, list[str]]:
    result = git(source, "status", "--porcelain=v1", "--untracked-files=all")
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "git status failed")
    entries = [line for line in result.stdout.splitlines() if line.strip()]
    return not entries, entries


def create_fresh_clone(
    source: Path,
    destination: Path,
    commit: str,
) -> None:
    """Create an independent local clone and detach it at ``commit``."""

    result = subprocess.run(
        [
            "git",
            "clone",
            "--no-local",
            "--no-hardlinks",
            "--quiet",
            str(source),
            str(destination),
        ],
        cwd=source.parent,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=300,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "git clone failed")
    checkout = git(destination, "checkout", "--detach", "--quiet", commit)
    if checkout.returncode:
        raise RuntimeError(checkout.stderr.strip() or "git checkout failed")


def _parse_precheck_report(stdout: str) -> dict[str, object] | None:
    try:
        value = json.loads(stdout)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def audit_clone(
    *,
    source: Path,
    revision: str,
    require_clean_source: bool,
    run_tests: bool,
    check_generator: bool,
    clone_dir: Path | None = None,
) -> dict[str, object]:
    errors: list[str] = []
    source = source.resolve()
    report: dict[str, object] = {
        "status": "FAIL",
        "source": str(source),
        "revision_requested": revision,
        "source_clean_required": require_clean_source,
        "tests_requested": run_tests,
        "generator_check_requested": check_generator,
        "network_used": False,
        "source_worktree_copied": False,
        "push_or_publication_performed": False,
        "errors": errors,
    }
    if not (source / ".git").exists():
        errors.append(f"source is not a Git worktree: {source}")
        return report

    try:
        commit = source_revision(source, revision)
        report["commit"] = commit
        clean, dirty_entries = source_is_clean(source)
        report["source_clean"] = clean
        report["source_dirty_entry_count"] = len(dirty_entries)
        if require_clean_source and not clean:
            errors.append(
                "source worktree/index is not clean; clean-clone audit would "
                "otherwise omit current changes"
            )

        history_paths = forbidden_history_paths(source)
        report["forbidden_history_paths"] = history_paths
        if history_paths:
            errors.append(
                "reachable Git history names private/restricted paths: "
                + ", ".join(history_paths[:20])
            )

        ignored_paths = ignored_source_paths(source)
        report["ignored_source_path_count"] = len(ignored_paths)
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
        errors.append(str(exc))
        return report

    if errors:
        return report

    temporary: tempfile.TemporaryDirectory[str] | None = None
    if clone_dir is None:
        temporary = tempfile.TemporaryDirectory(prefix="htx-clean-clone-")
        destination = Path(temporary.name) / "repository"
    else:
        destination = clone_dir.resolve()
        if destination.exists() and any(destination.iterdir()):
            errors.append(f"clone destination is not empty: {destination}")
            return report
        destination.parent.mkdir(parents=True, exist_ok=True)

    try:
        create_fresh_clone(source, destination, commit)
        report["clone"] = str(destination)
        missing_exclusion = [
            relative
            for relative in ignored_paths
            if (destination / relative).exists()
        ]
        report["ignored_paths_copied"] = missing_exclusion
        if missing_exclusion:
            errors.append(
                "ignored source paths appeared in the fresh clone: "
                + ", ".join(missing_exclusion[:20])
            )

        command = [
            sys.executable,
            "tools/precheck.py",
            "--require-clean",
        ]
        if run_tests:
            command.append("--run-tests")
        if check_generator:
            command.append("--check-generator")
        result = subprocess.run(
            command,
            cwd=destination,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=900,
        )
        report["precheck_command"] = command[1:]
        report["precheck_exit_code"] = result.returncode
        parsed = _parse_precheck_report(result.stdout)
        if parsed is not None:
            report["precheck"] = parsed
        else:
            report["precheck_stdout_tail"] = result.stdout.splitlines()[-30:]
        if result.stderr.strip():
            report["precheck_stderr_tail"] = result.stderr.splitlines()[-30:]
        if result.returncode:
            errors.append("precheck failed inside the fresh clone")
    except (
        OSError,
        RuntimeError,
        subprocess.TimeoutExpired,
    ) as exc:
        errors.append(str(exc))
    finally:
        if temporary is not None:
            temporary.cleanup()

    report["status"] = "PASS" if not errors else "FAIL"
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=Path,
        default=PROJECT_ROOT,
        help="Source Git worktree (default: this repository).",
    )
    parser.add_argument(
        "--revision",
        default="HEAD",
        help="Committed revision to clone and audit (default: HEAD).",
    )
    parser.add_argument(
        "--allow-dirty-source",
        action="store_true",
        help=(
            "Allow source changes to exist. They are deliberately omitted "
            "from the audited clone, so this is diagnostic-only."
        ),
    )
    parser.add_argument(
        "--skip-tests",
        action="store_true",
        help="Skip the complete unittest suite inside the clone.",
    )
    parser.add_argument(
        "--skip-generator",
        action="store_true",
        help="Skip the tracked-only two-pass generator check inside the clone.",
    )
    parser.add_argument(
        "--clone-dir",
        type=Path,
        help=(
            "Keep the clone at this empty/new directory instead of using and "
            "removing a temporary directory."
        ),
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    report = audit_clone(
        source=args.source,
        revision=args.revision,
        require_clean_source=not args.allow_dirty_source,
        run_tests=not args.skip_tests,
        check_generator=not args.skip_generator,
        clone_dir=args.clone_dir,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
