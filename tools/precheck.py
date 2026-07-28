"""Fail-closed public-release checks for the HTX assessment repository."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
import zipfile
from pathlib import Path
from pathlib import PurePosixPath
from urllib.parse import unquote


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CANONICAL_DECK = "slides/HTX_Task4_Operational_Insights.pptx"
REQUIRED_TRACKED = {
    "README.md",
    "LICENSING.md",
    "THIRD_PARTY_NOTICES.md",
    "config/confirmatory_capacity_study.json",
    "config/confirmatory_seed_manifest.csv",
    "config/public_release_data_policy.json",
    "data/derived/task1_final_aggregate.csv",
    "docs/privacy_and_data_governance.md",
    "docs/task1_measurement.md",
    "docs/task2_system_design.md",
    "docs/task3_results.md",
    "docs/task3_confirmatory_design.md",
    "docs/release_readiness_audit.md",
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
    "results/analysis/confirmatory_capacity/regime_diagnostics_by_replication.csv",
    "results/analysis/confirmatory_capacity/regime_diagnostics_manifest.json",
    "results/analysis/confirmatory_capacity/regime_estimates.csv",
    "results/analysis/confirmatory_capacity/regime_reference_joint_contrasts.csv",
    "results/analysis/confirmatory_capacity/replication_kpis.csv",
    "results/analysis/confirmatory_capacity/run_manifest.csv",
    "results/analysis/confirmatory_capacity/scenario_contrasts.csv",
    "results/analysis/confirmatory_capacity/scenario_estimates.csv",
    "results/analysis/confirmatory_capacity/validation.json",
    "results/analysis/confirmatory_capacity/within_rate_pairwise_contrasts.csv",
    "tools/audit_public_release_data.py",
    "tools/clean_clone_audit.py",
    CANONICAL_DECK,
}
TEXT_SUFFIXES = {".csv", ".json", ".md", ".ps1", ".py", ".txt"}
MARKDOWN_LINK = re.compile(r"!?\[[^\]]*]\(([^)]+)\)")
WINDOWS_USER_PATH = re.compile(r"[A-Za-z]:[\\/]+Users[\\/]+[^\\/]+", re.I)
WINDOWS_ABSOLUTE_PATH = re.compile(
    r"(?<![A-Za-z0-9+.\-])"
    r"(?:"
    r"(?:file:/+)?[A-Za-z]:[\\/]"
    r"|"
    r"\\\\[A-Za-z0-9_.\-]+\\[A-Za-z0-9$_.\-]+"
    r")",
    re.I,
)
OFFICE_ARCHIVE_SUFFIXES = {".docx", ".pptx", ".xlsx"}
ARCHIVE_TEXT_SUFFIXES = {
    ".csv",
    ".json",
    ".rels",
    ".txt",
    ".xml",
}
WINDOWS_RESERVED_NAMES = {
    "aux",
    "clock$",
    "con",
    "nul",
    "prn",
    *(f"com{index}" for index in range(1, 10)),
    *(f"lpt{index}" for index in range(1, 10)),
}
README_REQUIRED_COMMANDS = {
    "primary environment creation": "python -m venv .venv",
    "primary dependency installation": (
        r".\.venv\Scripts\python.exe -m pip install -r requirements.txt"
    ),
    "fallback environment creation": "python -m venv .venv-bytetrack",
    "fallback dependency installation": (
        r".\.venv-bytetrack\Scripts\python.exe -m pip install "
        "-r requirements-bytetrack.txt"
    ),
    "complete test suite": (
        r".\.venv\Scripts\python.exe -m unittest discover -s tests -v"
    ),
    "release precheck": (
        r".\.venv\Scripts\python.exe tools\precheck.py --run-tests"
    ),
    "AnyLogic source generator": (
        r".\.venv\Scripts\python.exe "
        r"scripts\generate_operational_anylogic.py"
    ),
}
README_COMMAND_FILES = {
    "README.md",
    "requirements.txt",
    "requirements-common.txt",
    "requirements-bytetrack.txt",
    "scripts/download_yolox_s.ps1",
    "scripts/generate_operational_anylogic.py",
    "simulation/anylogic/HTXCheckpointSimulation/"
    "HTXCheckpointSimulation.alpx",
    "simulation/anylogic/HTXCheckpointSimulationCLI/"
    "HTXCheckpointSimulationCLI.alp",
    "tests",
    "tools/precheck.py",
}
DOCUMENTED_STDLIB_MODULES = {"pip", "unittest", "venv"}
PRIVATE_TRACKED_PREFIXES = {
    ".venv/",
    ".venv-bytetrack/",
    "_work/",
    "results/intermediate/",
    "results/raw/",
}
PRIVATE_TRACKED_SUFFIXES = {".mov", ".mp4", ".onnx", ".pt", ".pth"}
GENERATOR_RELATIVE_PATH = "scripts/generate_operational_anylogic.py"


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
            if "\\" in raw_target and not re.match(
                r"^[A-Za-z][A-Za-z0-9+.-]*:", raw_target.strip()
            ):
                errors.append(
                    f"{relative}: local Markdown link uses a non-portable "
                    f"backslash: {raw_target}"
                )
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


def check_portable_tracked_names(tracked: set[str]) -> list[str]:
    """Reject names that do not survive ordinary Windows/Linux checkouts."""

    errors: list[str] = []
    casefolded: dict[str, str] = {}
    normalized: dict[str, str] = {}
    for relative in sorted(tracked):
        if "\\" in relative:
            errors.append(
                f"tracked path uses a backslash instead of '/': {relative}"
            )
            continue
        pure = PurePosixPath(relative)
        if pure.is_absolute() or ".." in pure.parts:
            errors.append(f"tracked path is not repository-relative: {relative}")
        if len(relative.encode("utf-8")) > 240:
            errors.append(
                f"tracked path exceeds the conservative 240-byte limit: {relative}"
            )
        for component in pure.parts:
            if component in {"", ".", ".."}:
                errors.append(
                    f"tracked path has an unsafe component {component!r}: {relative}"
                )
                continue
            if component.endswith((" ", ".")):
                errors.append(
                    f"tracked path has a Windows-unsafe trailing character: "
                    f"{relative}"
                )
            if ":" in component or any(ord(char) < 32 for char in component):
                errors.append(
                    f"tracked path has a Windows-unsafe character: {relative}"
                )
            basename = component.split(".", 1)[0].casefold()
            if basename in WINDOWS_RESERVED_NAMES:
                errors.append(
                    f"tracked path uses a Windows-reserved name: {relative}"
                )

        folded = relative.casefold()
        prior = casefolded.setdefault(folded, relative)
        if prior != relative:
            errors.append(
                "tracked paths collide on a case-insensitive filesystem: "
                f"{prior} <> {relative}"
            )

        portable = unicodedata.normalize("NFC", relative).casefold()
        prior = normalized.setdefault(portable, relative)
        if prior != relative and prior.casefold() != folded:
            errors.append(
                "tracked paths collide after Unicode normalization: "
                f"{prior} <> {relative}"
            )
    return errors


def _decode_for_path_scan(data: bytes) -> list[str]:
    candidates: list[str] = []
    try:
        candidates.append(data.decode("utf-8"))
    except UnicodeDecodeError:
        pass
    if b"\x00" in data:
        for encoding in ("utf-16-le", "utf-16-be"):
            try:
                candidates.append(data.decode(encoding))
            except UnicodeDecodeError:
                continue
    return candidates


def _absolute_windows_path_hits(data: bytes) -> list[str]:
    hits: list[str] = []
    for text in _decode_for_path_scan(data):
        for match in WINDOWS_ABSOLUTE_PATH.finditer(text):
            line_start = text.rfind("\n", 0, match.start()) + 1
            line_end = text.find("\n", match.start())
            if line_end < 0:
                line_end = len(text)
            excerpt = text[line_start:line_end].strip()
            excerpt = excerpt[:240]
            if excerpt not in hits:
                hits.append(excerpt)
    return hits


def check_absolute_windows_paths(
    tracked: set[str],
    *,
    root: Path = PROJECT_ROOT,
) -> tuple[list[str], int]:
    """Scan tracked files, including Office ZIP members, for local paths."""

    errors: list[str] = []
    scanned = 0
    for relative in sorted(tracked):
        path = root / relative
        if not path.is_file():
            continue
        scanned += 1
        try:
            data = path.read_bytes()
        except OSError as exc:
            errors.append(f"{relative}: cannot scan for local paths: {exc}")
            continue
        for excerpt in _absolute_windows_path_hits(data):
            errors.append(
                f"{relative}: contains a forbidden absolute Windows path: "
                f"{excerpt}"
            )

        if path.suffix.lower() not in OFFICE_ARCHIVE_SUFFIXES:
            continue
        try:
            with zipfile.ZipFile(path) as archive:
                for member in archive.infolist():
                    if (
                        member.is_dir()
                        or Path(member.filename).suffix.lower()
                        not in ARCHIVE_TEXT_SUFFIXES
                    ):
                        continue
                    member_data = archive.read(member)
                    for excerpt in _absolute_windows_path_hits(member_data):
                        errors.append(
                            f"{relative}!{member.filename}: contains a "
                            f"forbidden absolute Windows path: {excerpt}"
                        )
        except (OSError, zipfile.BadZipFile) as exc:
            errors.append(f"{relative}: cannot inspect Office archive: {exc}")
    return errors, scanned


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


def _powershell_blocks(markdown: str) -> list[str]:
    blocks: list[str] = []
    inside = False
    language = ""
    current: list[str] = []
    for line in markdown.splitlines():
        fence = re.match(r"^```\s*([A-Za-z0-9_-]*)\s*$", line)
        if fence:
            if inside:
                if language.casefold() in {"powershell", "pwsh"}:
                    blocks.append("\n".join(current))
                inside = False
                language = ""
                current = []
            else:
                inside = True
                language = fence.group(1)
            continue
        if inside:
            current.append(line)
    return blocks


def _repo_relative_command_path(raw: str) -> str:
    value = raw.strip().strip("\"'").rstrip("`")
    value = value.replace("$PWD\\", "").replace("${PWD}\\", "")
    value = value.replace("$PWD/", "").replace("${PWD}/", "")
    while value.startswith(".\\") or value.startswith("./"):
        value = value[2:]
    return value.replace("\\", "/")


def _module_source(module: str) -> tuple[str, str]:
    base = module.replace(".", "/")
    return f"{base}.py", f"{base}/__init__.py"


def check_readme_command_contract(
    tracked: set[str],
    *,
    root: Path = PROJECT_ROOT,
) -> tuple[list[str], int]:
    """Validate exact release commands and their repository-owned inputs."""

    errors: list[str] = []
    readme_path = root / "README.md"
    try:
        readme = readme_path.read_text(encoding="utf-8")
    except OSError as exc:
        return [f"README command contract is unreadable: {exc}"], 0

    for label, command in README_REQUIRED_COMMANDS.items():
        count = len(
            re.findall(
                re.escape(command) + r"(?![A-Za-z0-9_.-])",
                readme,
            )
        )
        if count != 1:
            errors.append(
                f"README must contain the exact {label} command once; "
                f"found {count}: {command}"
            )

    for relative in sorted(README_COMMAND_FILES):
        target = root / relative
        if not target.exists():
            errors.append(
                f"README command dependency does not exist: {relative}"
            )
        elif target.is_file() and relative not in tracked:
            errors.append(
                f"README command dependency is not tracked: {relative}"
            )
        elif target.is_dir() and not any(
            path == relative or path.startswith(f"{relative}/")
            for path in tracked
        ):
            errors.append(
                f"README command directory has no tracked files: {relative}"
            )

    blocks = _powershell_blocks(readme)
    checked = 0
    for block in blocks:
        for module in re.findall(r"(?:^|\s)-m\s+([A-Za-z_][A-Za-z0-9_.]*)", block):
            checked += 1
            if module in DOCUMENTED_STDLIB_MODULES:
                continue
            candidates = _module_source(module)
            if not any(candidate in tracked for candidate in candidates):
                errors.append(
                    "README invokes a module with no tracked source: "
                    f"{module} ({candidates[0]} or {candidates[1]})"
                )

        for raw in re.findall(
            r"(?:^|\s)-File\s+(\"[^\"]+\.ps1\"|'[^']+\.ps1'|[^\s`]+\.ps1)",
            block,
            flags=re.I,
        ):
            checked += 1
            relative = _repo_relative_command_path(raw)
            if relative not in tracked:
                errors.append(
                    f"README invokes an untracked PowerShell script: {relative}"
                )

        for raw in re.findall(
            r"(?:python(?:\.exe)?|python3)\s+"
            r"(?!-(?:m|c)\b)(\"[^\"]+\.py\"|'[^']+\.py'|[^\s`]+\.py)",
            block,
            flags=re.I,
        ):
            checked += 1
            relative = _repo_relative_command_path(raw)
            if relative not in tracked:
                errors.append(
                    f"README invokes an untracked Python script: {relative}"
                )

        for raw in re.findall(
            r"(?:^|\s)-r\s+(\"[^\"]+\"|'[^']+'|[^\s`]+)",
            block,
            flags=re.I,
        ):
            checked += 1
            relative = _repo_relative_command_path(raw)
            if relative.lower().endswith((".alp", ".alpx", ".txt")):
                if relative not in tracked:
                    errors.append(
                        f"README references an untracked command input: {relative}"
                    )
    return errors, checked


def _read_requirement_file(
    relative: str,
    *,
    root: Path,
    tracked: set[str],
    seen: set[str],
    errors: list[str],
) -> dict[str, str]:
    if relative in seen:
        return {}
    seen.add(relative)
    path = root / relative
    if relative not in tracked or not path.is_file():
        errors.append(f"requirements include is missing or untracked: {relative}")
        return {}

    packages: dict[str, str] = {}
    for number, raw_line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        include = re.fullmatch(r"-r\s+(.+)", line, flags=re.I)
        if include:
            child = _repo_relative_command_path(include.group(1))
            if WINDOWS_ABSOLUTE_PATH.search(include.group(1)):
                errors.append(
                    f"{relative}:{number}: requirements include is absolute"
                )
                continue
            child_packages = _read_requirement_file(
                child,
                root=root,
                tracked=tracked,
                seen=seen,
                errors=errors,
            )
            for name, version in child_packages.items():
                prior = packages.get(name)
                if prior is not None and prior != version:
                    errors.append(
                        f"{relative}:{number}: conflicting included pins for "
                        f"{name}: {prior} versus {version}"
                    )
                packages[name] = version
            continue
        match = re.fullmatch(
            r"([A-Za-z0-9_.-]+(?:\[[A-Za-z0-9_,.-]+\])?)==([^\s;]+)",
            line,
        )
        if not match:
            errors.append(
                f"{relative}:{number}: dependency is not an exact == pin: {line}"
            )
            continue
        name = match.group(1).split("[", 1)[0].replace("_", "-").casefold()
        version = match.group(2)
        prior = packages.get(name)
        if prior is not None and prior != version:
            errors.append(
                f"{relative}:{number}: conflicting pins for {name}: "
                f"{prior} versus {version}"
            )
        packages[name] = version
    return packages


def check_requirements_contract(
    tracked: set[str],
    *,
    root: Path = PROJECT_ROOT,
) -> tuple[list[str], int]:
    errors: list[str] = []
    primary = _read_requirement_file(
        "requirements.txt",
        root=root,
        tracked=tracked,
        seen=set(),
        errors=errors,
    )
    fallback = _read_requirement_file(
        "requirements-bytetrack.txt",
        root=root,
        tracked=tracked,
        seen=set(),
        errors=errors,
    )
    if "opencv-python-headless" not in primary:
        errors.append("primary requirements must pin opencv-python-headless")
    if "opencv-python" in primary:
        errors.append("primary requirements must not install opencv-python")
    if "opencv-python" not in fallback:
        errors.append("ByteTrack requirements must pin opencv-python")
    if "opencv-python-headless" in fallback:
        errors.append(
            "ByteTrack requirements must not install opencv-python-headless"
        )
    return errors, len(primary) + len(fallback)


def check_private_tracked_paths(tracked: set[str]) -> list[str]:
    errors: list[str] = []
    for relative in sorted(tracked):
        lowered = relative.casefold()
        if lowered.startswith("data/raw/") and lowered != "data/raw/readme.md":
            errors.append(f"restricted raw input must not be tracked: {relative}")
        if any(lowered.startswith(prefix) for prefix in PRIVATE_TRACKED_PREFIXES):
            errors.append(f"private/generated working path is tracked: {relative}")
        if Path(lowered).suffix in PRIVATE_TRACKED_SUFFIXES:
            errors.append(f"private or redistributable binary is tracked: {relative}")
    return errors


def check_privacy_boundary(tracked: set[str]) -> list[str]:
    """Delegate content/privacy policy to the dedicated governance scanner."""

    project_root_text = str(PROJECT_ROOT)
    if project_root_text not in sys.path:
        sys.path.insert(0, project_root_text)
    try:
        from src.governance.public_release import audit_paths
    except (ImportError, ModuleNotFoundError) as exc:
        return [f"privacy boundary: governance scanner is unavailable: {exc}"]
    return [
        f"privacy boundary: {finding.render()}"
        for finding in audit_paths(PROJECT_ROOT, tracked)
    ]


def validate_compact_audit() -> list[str]:
    errors: list[str] = []
    root = PROJECT_ROOT / "results" / "analysis" / "operational"
    manifest_path = (
        root / "audit_manifest.json"
    )
    validation_path = (
        root / "validation.json"
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
    for key in ("run_manifest", "replication_kpis"):
        entry = manifest.get(key)
        if not isinstance(entry, dict) or entry.get("tracked") is not True:
            errors.append(f"operational audit {key} must be tracked")
            continue
        raw_path = entry.get("path")
        expected_hash = entry.get("sha256")
        if not isinstance(raw_path, str) or not raw_path:
            errors.append(f"operational audit {key} has no portable path")
            continue
        artifact = (PROJECT_ROOT / raw_path).resolve()
        try:
            artifact.relative_to(PROJECT_ROOT.resolve())
        except ValueError:
            errors.append(f"operational audit {key} escapes the repository")
            continue
        if not artifact.is_file():
            errors.append(f"operational audit {key} artifact is missing")
        elif not isinstance(expected_hash, str) or sha256(artifact) != expected_hash:
            errors.append(f"operational audit {key} hash mismatch")
        expected_rows = 150
        if entry.get("row_count") != expected_rows:
            errors.append(
                f"operational audit {key} must record {expected_rows} rows"
            )
    entity_entry = manifest.get("entity_log")
    if not isinstance(entity_entry, dict):
        errors.append("operational audit entity_log disclosure is missing")
    else:
        if entity_entry.get("tracked") is not False:
            errors.append("operational entity ledger must be disclosed as untracked")
        if entity_entry.get("row_count") != 61218:
            errors.append("operational entity ledger must record 61,218 rows")
        entity_hash = entity_entry.get("sha256")
        if not isinstance(entity_hash, str) or not re.fullmatch(
            r"[0-9a-f]{64}", entity_hash
        ):
            errors.append("operational entity ledger SHA-256 is invalid")
    return errors


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _copy_tracked_snapshot(
    tracked: set[str],
    *,
    source_root: Path,
    destination_root: Path,
) -> None:
    for relative in sorted(tracked):
        source = source_root / relative
        destination = destination_root / relative
        if not source.is_file() and not source.is_symlink():
            raise FileNotFoundError(f"tracked source is missing: {relative}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        if source.is_symlink():
            target = os.readlink(source)
            try:
                destination.symlink_to(target)
            except OSError as exc:
                raise RuntimeError(
                    f"cannot reproduce tracked symlink {relative}: {exc}"
                ) from exc
        else:
            shutil.copy2(source, destination)


def _snapshot_hashes(root: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if (
            "__pycache__" in relative.parts
            or ".pytest_cache" in relative.parts
            or path.suffix.casefold() in {".pyc", ".pyo"}
        ):
            continue
        hashes[relative.as_posix()] = sha256(path)
    return hashes


def _manifest_changes(
    before: dict[str, str],
    after: dict[str, str],
) -> list[str]:
    return sorted(
        relative
        for relative in before.keys() | after.keys()
        if before.get(relative) != after.get(relative)
    )


def check_generator_determinism(
    tracked: set[str],
    *,
    root: Path = PROJECT_ROOT,
    generator_relative: str = GENERATOR_RELATIVE_PATH,
    timeout_seconds: int = 180,
) -> tuple[list[str], dict[str, object]]:
    """Run the generator twice in a tracked-only temporary snapshot.

    The first comparison proves that committed/generated artifacts are current.
    The second comparison proves byte-level idempotence. Ignored video, review
    material, raw outputs, model weights, and virtual environments are never
    copied into the snapshot.
    """

    errors: list[str] = []
    details: dict[str, object] = {
        "generator": generator_relative,
        "tracked_only_snapshot": True,
        "source_synchronized": False,
        "second_run_byte_identical": False,
    }
    if generator_relative not in tracked:
        return [
            f"deterministic generator is not tracked: {generator_relative}"
        ], details

    with tempfile.TemporaryDirectory(prefix="htx-generator-audit-") as raw:
        snapshot = Path(raw) / "repository"
        snapshot.mkdir()
        try:
            _copy_tracked_snapshot(
                tracked,
                source_root=root,
                destination_root=snapshot,
            )
        except (OSError, RuntimeError) as exc:
            return [f"cannot create tracked-only generator snapshot: {exc}"], details

        before = _snapshot_hashes(snapshot)
        manifests: list[dict[str, str]] = []
        for pass_number in (1, 2):
            try:
                result = subprocess.run(
                    [sys.executable, generator_relative],
                    cwd=snapshot,
                    check=False,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    timeout=timeout_seconds,
                )
            except subprocess.TimeoutExpired:
                errors.append(
                    f"generator pass {pass_number} exceeded "
                    f"{timeout_seconds} seconds"
                )
                return errors, details
            if result.returncode:
                tail = "\n".join(
                    (result.stderr or result.stdout).splitlines()[-12:]
                )
                errors.append(
                    f"generator pass {pass_number} failed with exit "
                    f"{result.returncode}: {tail}"
                )
                return errors, details
            manifests.append(_snapshot_hashes(snapshot))

        first_changes = _manifest_changes(before, manifests[0])
        second_changes = _manifest_changes(manifests[0], manifests[1])
        details["first_run_changes"] = first_changes
        details["second_run_changes"] = second_changes
        details["source_synchronized"] = not first_changes
        details["second_run_byte_identical"] = not second_changes
        if first_changes:
            errors.append(
                "generator output is not synchronized with tracked source: "
                + ", ".join(first_changes[:20])
            )
        if second_changes:
            errors.append(
                "generator is not byte-idempotent on its second pass: "
                + ", ".join(second_changes[:20])
            )
    return errors, details


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
        regime_manifest = json.loads(
            (root / "regime_diagnostics_manifest.json").read_text(
                encoding="utf-8"
            )
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

    if (
        regime_manifest.get("status") != "PASS"
        or regime_manifest.get("analysis_role")
        != "POST_HOC_SUPPORTING_LOAD_DIAGNOSTIC"
        or regime_manifest.get("replication_row_count") != 600
        or regime_manifest.get("estimate_row_count") != 84
        or regime_manifest.get("contrast_row_count") != 9
        or regime_manifest.get("thresholds_seconds") != [15.0, 30.0, 60.0]
    ):
        errors.append("post-hoc load-regime diagnostic contract is incomplete")
    regime_entity = regime_manifest.get("source_entity_log")
    if (
        not isinstance(regime_entity, dict)
        or regime_entity.get("row_count") != 253756
        or regime_entity.get("sha256")
        != "7fea0ee6215f277b1ef48cd9d2dab18ea1b761158b66a037fbd9012f644b2657"
    ):
        errors.append("post-hoc load-regime source evidence is incomplete")
    regime_outputs = regime_manifest.get("outputs")
    if not isinstance(regime_outputs, dict):
        errors.append("post-hoc load-regime output inventory is missing")
    else:
        for relative, expected in regime_outputs.items():
            path = PROJECT_ROOT / str(relative)
            if not path.is_file():
                errors.append(
                    f"post-hoc load-regime artifact is missing: {relative}"
                )
            elif sha256(path) != expected:
                errors.append(
                    f"post-hoc load-regime artifact hash mismatch: {relative}"
                )

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


def precheck(
    *,
    require_clean: bool,
    execute_tests: bool,
    check_generator: bool = False,
) -> dict[str, object]:
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

    oversized = sorted(
        path
        for path in tracked
        if (PROJECT_ROOT / path).is_file()
        and (PROJECT_ROOT / path).stat().st_size >= 95_000_000
    )
    errors.extend(f"tracked file is at least 95 MB: {path}" for path in oversized)

    link_errors, link_count = check_markdown_links(tracked)
    command_errors, command_reference_count = check_readme_command_contract(
        tracked
    )
    requirement_errors, requirement_pin_count = check_requirements_contract(
        tracked
    )
    absolute_path_errors, absolute_path_scan_count = (
        check_absolute_windows_paths(tracked)
    )
    errors.extend(link_errors)
    errors.extend(check_portable_tracked_names(tracked))
    errors.extend(check_private_tracked_paths(tracked))
    errors.extend(check_privacy_boundary(tracked))
    errors.extend(absolute_path_errors)
    errors.extend(command_errors)
    errors.extend(requirement_errors)
    errors.extend(validate_compact_audit())
    errors.extend(validate_confirmatory_audit())

    if require_clean:
        status = git("status", "--porcelain")
        if status.returncode or status.stdout.strip():
            errors.append("git worktree/index is not clean")

    if execute_tests:
        errors.extend(run_tests())

    generator_details: dict[str, object] | None = None
    if check_generator:
        generator_errors, generator_details = check_generator_determinism(
            tracked
        )
        errors.extend(generator_errors)

    return {
        "status": "PASS" if not errors else "FAIL",
        "tracked_file_count": len(tracked),
        "tracked_artifacts_scanned_for_absolute_paths": (
            absolute_path_scan_count
        ),
        "markdown_local_links_checked": link_count,
        "readme_command_references_checked": command_reference_count,
        "resolved_requirement_pin_count": requirement_pin_count,
        "require_clean": require_clean,
        "tests_executed": execute_tests,
        "generator_checked": check_generator,
        "generator": generator_details,
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
    parser.add_argument(
        "--check-generator",
        action="store_true",
        help=(
            "Run the AnyLogic source generator twice in a temporary "
            "tracked-only snapshot; require synchronized, byte-idempotent "
            "output."
        ),
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    report = precheck(
        require_clean=args.require_clean,
        execute_tests=args.run_tests,
        check_generator=args.check_generator,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
