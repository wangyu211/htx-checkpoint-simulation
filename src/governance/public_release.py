"""Fail-closed audit of tracked public-release artifacts.

The audit intentionally treats unclassified raster media as restricted.  A
human must review a non-pixel chart or synthetic screenshot and register its
SHA-256 in ``config/public_release_data_policy.json`` before it can pass.
"""

from __future__ import annotations

import csv
import fnmatch
import hashlib
import json
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


POLICY_RELATIVE_PATH = Path("config/public_release_data_policy.json")


@dataclass(frozen=True)
class Finding:
    code: str
    path: str
    detail: str

    def render(self) -> str:
        return f"{self.code}: {self.path}: {self.detail}"


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_policy(root: Path) -> dict[str, object]:
    path = root / POLICY_RELATIVE_PATH
    policy = json.loads(path.read_text(encoding="utf-8"))
    if policy.get("status") != "ENFORCED":
        raise ValueError("public-release data policy must have status ENFORCED")
    return policy


def _normalise_paths(paths: Iterable[str]) -> list[str]:
    return sorted(
        {
            str(path).strip().replace("\\", "/")
            for path in paths
            if str(path).strip()
        }
    )


def _matches_any_glob(path: str, patterns: Iterable[str]) -> bool:
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)


def _structured_field_names(path: Path) -> set[str]:
    suffix = path.suffix.lower()
    if suffix in {".csv", ".tsv"}:
        delimiter = "\t" if suffix == ".tsv" else ","
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            reader = csv.reader(stream, delimiter=delimiter)
            try:
                return {str(value).strip().lower() for value in next(reader)}
            except StopIteration:
                return set()
    if suffix == ".json":
        document = json.loads(path.read_text(encoding="utf-8"))
        fields: set[str] = set()

        def visit(value: object) -> None:
            if isinstance(value, dict):
                for key, child in value.items():
                    fields.add(str(key).strip().lower())
                    visit(child)
            elif isinstance(value, list):
                for child in value:
                    visit(child)

        visit(document)
        return fields
    return set()


def _audit_public_reviewer_aliases(
    root: Path,
    tracked: list[str],
    policy: dict[str, object],
) -> list[Finding]:
    findings: list[Finding] = []
    task1 = dict(policy["task1_public_artifacts"])
    alias_pattern = re.compile(str(task1["reviewer_alias_pattern"]))
    ledger_globs = list(task1["public_ledger_globs"])
    signoff_globs = list(task1["public_signoff_globs"])
    forbidden = {
        str(field).lower() for field in task1["forbidden_public_ledger_fields"]
    }

    for relative in tracked:
        path = root / relative
        if _matches_any_glob(relative, ledger_globs):
            try:
                with path.open("r", encoding="utf-8-sig", newline="") as stream:
                    rows = list(csv.DictReader(stream))
            except (OSError, UnicodeError, csv.Error) as exc:
                findings.append(
                    Finding("UNREADABLE_PUBLIC_LEDGER", relative, str(exc))
                )
                continue
            fields = {str(field).lower() for field in (rows[0].keys() if rows else [])}
            prohibited = sorted(fields & forbidden)
            if prohibited:
                findings.append(
                    Finding(
                        "PROHIBITED_PUBLIC_LEDGER_FIELDS",
                        relative,
                        ", ".join(prohibited),
                    )
                )
            for index, row in enumerate(rows, start=2):
                alias = str(row.get("reviewer_id", ""))
                if not alias_pattern.fullmatch(alias):
                    findings.append(
                        Finding(
                            "INVALID_REVIEWER_ALIAS",
                            relative,
                            f"row {index} reviewer_id is not a "
                            "project-scoped role alias",
                        )
                    )

        if _matches_any_glob(relative, signoff_globs):
            try:
                document = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                findings.append(
                    Finding("UNREADABLE_PUBLIC_SIGNOFF", relative, str(exc))
                )
                continue
            alias = str(document.get("reviewer_id", ""))
            if not alias_pattern.fullmatch(alias):
                findings.append(
                    Finding(
                        "INVALID_REVIEWER_ALIAS",
                        relative,
                        "reviewer_id is not a project-scoped role alias",
                    )
                )
    return findings


def _audit_archive(
    path: Path,
    relative: str,
    *,
    raster_extensions: set[str],
    restricted_media_extensions: set[str],
    approved_media_hashes: set[str],
    restricted_hashes: dict[str, str],
) -> list[Finding]:
    findings: list[Finding] = []
    try:
        with zipfile.ZipFile(path) as archive:
            for member in archive.infolist():
                if member.is_dir():
                    continue
                suffix = Path(member.filename).suffix.lower()
                if suffix not in raster_extensions | restricted_media_extensions:
                    continue
                content = archive.read(member)
                digest = sha256_bytes(content)
                member_path = f"{relative}!/{member.filename}"
                if digest in restricted_hashes:
                    findings.append(
                        Finding(
                            "RESTRICTED_CONTENT_HASH",
                            member_path,
                            restricted_hashes[digest],
                        )
                    )
                elif suffix in restricted_media_extensions:
                    findings.append(
                        Finding(
                            "EMBEDDED_AUDIO_VIDEO",
                            member_path,
                            f"embedded {suffix} media is restricted",
                        )
                    )
                elif digest not in approved_media_hashes:
                    findings.append(
                        Finding(
                            "UNCLASSIFIED_EMBEDDED_RASTER",
                            member_path,
                            f"SHA-256 {digest} has no reviewed "
                            "non-pixel classification",
                        )
                    )
    except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
        findings.append(Finding("UNREADABLE_ARCHIVE", relative, str(exc)))
    return findings


def audit_paths(
    root: Path,
    tracked_paths: Iterable[str],
    *,
    policy: dict[str, object] | None = None,
) -> list[Finding]:
    """Audit an explicit tracked-file inventory.

    ``tracked_paths`` should normally come from ``git ls-files``.  Passing it
    explicitly keeps the core testable and prevents an ignored local artifact
    from being mistaken for a public-release artifact.
    """

    root = root.resolve()
    tracked = _normalise_paths(tracked_paths)
    policy = load_policy(root) if policy is None else policy
    findings: list[Finding] = []

    restricted_prefixes = tuple(
        str(value) for value in policy["restricted_path_prefixes"]
    )
    placeholder_exceptions = {
        str(value) for value in policy["tracked_placeholder_exceptions"]
    }
    restricted_media_extensions = {
        str(value).lower() for value in policy["always_restricted_media_extensions"]
    }
    raster_extensions = {
        str(value).lower() for value in policy["raster_image_extensions"]
    }
    opaque_binary_extensions = {
        str(value).lower()
        for value in policy["opaque_binary_extensions_restricted"]
    }
    archive_extensions = {
        str(value).lower() for value in policy["archive_extensions_to_inspect"]
    }
    restricted_tokens = {
        str(value).lower() for value in policy["restricted_path_tokens"]
    }
    restricted_fields = {
        str(value).lower() for value in policy["restricted_structured_field_tokens"]
    }
    restricted_field_prefixes = tuple(
        str(value).lower()
        for value in policy["restricted_structured_field_prefixes"]
    )
    approved_media_hashes = {
        str(value).lower()
        for value in dict(policy["approved_non_pixel_media_sha256"]).keys()
    }
    restricted_hashes = {
        str(key).lower(): str(value)
        for key, value in dict(policy["restricted_content_sha256"]).items()
    }

    for relative in tracked:
        path = root / relative
        if not path.is_file():
            findings.append(
                Finding("TRACKED_FILE_MISSING", relative, "tracked path is not a file")
            )
            continue

        if (
            relative not in placeholder_exceptions
            and relative.startswith(restricted_prefixes)
        ):
            findings.append(
                Finding(
                    "RESTRICTED_PATH",
                    relative,
                    "path is reserved for local/private artifacts",
                )
            )

        suffix = path.suffix.lower()
        lowered_parts = {
            token
            for part in Path(relative).parts
            for token in re.split(r"[^a-z0-9]+", part.lower())
            if token
        }
        lowered_path = relative.lower()
        if suffix not in {".java", ".md", ".ps1", ".py", ".txt", ".xml"}:
            for token in restricted_tokens:
                if token in lowered_path or token in lowered_parts:
                    findings.append(
                        Finding(
                            "RESTRICTED_PATH_TOKEN",
                            relative,
                            f"path contains restricted token {token!r}",
                        )
                    )
                    break

        digest = sha256_file(path)
        if digest in restricted_hashes:
            findings.append(
                Finding(
                    "RESTRICTED_CONTENT_HASH",
                    relative,
                    restricted_hashes[digest],
                )
            )
        elif suffix in restricted_media_extensions:
            findings.append(
                Finding(
                    "TRACKED_AUDIO_VIDEO",
                    relative,
                    f"tracked {suffix} media is restricted",
                )
            )
        elif suffix in raster_extensions and digest not in approved_media_hashes:
            findings.append(
                Finding(
                    "UNCLASSIFIED_TRACKED_RASTER",
                    relative,
                    f"SHA-256 {digest} has no reviewed non-pixel classification",
                )
            )
        elif suffix in opaque_binary_extensions:
            findings.append(
                Finding(
                    "OPAQUE_BINARY_DATA",
                    relative,
                    f"tracked {suffix} container is restricted; publish a "
                    "reviewed tabular aggregate instead",
                )
            )

        if suffix in archive_extensions:
            findings.extend(
                _audit_archive(
                    path,
                    relative,
                    raster_extensions=raster_extensions,
                    restricted_media_extensions=restricted_media_extensions,
                    approved_media_hashes=approved_media_hashes,
                    restricted_hashes=restricted_hashes,
                )
            )

        if suffix == ".svg":
            try:
                svg_text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeError) as exc:
                findings.append(
                    Finding("UNREADABLE_SVG", relative, str(exc))
                )
            else:
                if digest not in approved_media_hashes and re.search(
                    r"<\s*image\b|data\s*:\s*image/",
                    svg_text,
                    flags=re.IGNORECASE,
                ):
                    findings.append(
                        Finding(
                            "EMBEDDED_RASTER_IN_SVG",
                            relative,
                            "SVG contains an embedded or linked raster image",
                        )
                    )

        if (
            suffix in {".csv", ".json", ".tsv"}
            and relative.startswith(("data/", "results/"))
        ):
            try:
                fields = _structured_field_names(path)
            except (OSError, UnicodeError, csv.Error, json.JSONDecodeError) as exc:
                findings.append(
                    Finding("UNREADABLE_STRUCTURED_DATA", relative, str(exc))
                )
            else:
                prohibited = sorted(
                    field
                    for field in fields
                    if field in restricted_fields
                    or field.startswith(restricted_field_prefixes)
                )
                if prohibited:
                    findings.append(
                        Finding(
                            "RESTRICTED_STRUCTURED_FIELDS",
                            relative,
                            ", ".join(prohibited),
                        )
                    )

    findings.extend(_audit_public_reviewer_aliases(root, tracked, policy))
    return sorted(findings, key=lambda item: (item.path, item.code, item.detail))
