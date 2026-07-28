"""Stage and validate the GUI animation-speed invariance evidence.

The experiment is executed three times in the AnyLogic GUI.  The model-time
outputs, not real elapsed time, are the estimand.  ``stage`` copies one newly
finished run into an immutable mode-specific directory and binds it to a
mode-labelled UI screenshot.  ``validate`` fails closed unless all three
captures exist, were staged in the registered order from distinct exports,
and have exactly equal ordered fields in the manifest, entity/event ledger,
and replication KPI table.

Capture metadata, filesystem paths/timestamps, wall-clock duration, and the UI
screenshot are provenance rather than simulation outputs.  They are validated
but deliberately excluded from the core numerical equality comparison.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from src.analysis.validate_operational_results import (
    DEFAULT_SCHEMA_REGISTRY,
    RESULT_FILES,
    load_result_schemas,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROTOCOL = (
    PROJECT_ROOT / "config" / "animation_speed_invariance_protocol.json"
)
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
HEX40 = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
CAPTURE_METADATA_FILE = "capture_metadata.json"
UI_EVIDENCE_FILE = "ui_finished.png"
TABLE_BY_FILE = {filename: table for table, filename in RESULT_FILES.items()}
EXPECTED_TABLES = ("run_manifest", "entity_log", "replication_kpis")
CAPTURE_METADATA_REQUIRED = (
    "schema_version",
    "contract_id",
    "evidence_id",
    "experiment_name",
    "run_mode",
    "directory_name",
    "execution_mode",
    "real_time_scale",
    "animation_condition",
    "operator_role_alias",
    "model_git_commit",
    "capture_utc",
    "finished_confirmed",
    "source_run_directory",
    "source_file_mtime_ns",
    "core_file_sha256",
    "ui_evidence_sha256",
)


class ProtocolError(ValueError):
    """Raised when the frozen protocol is malformed."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _portable(path: Path) -> str:
    try:
        return path.resolve().relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _read_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return value


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def load_protocol(path: Path = DEFAULT_PROTOCOL) -> dict[str, Any]:
    protocol = _read_json(path)
    errors: list[str] = []
    expected_scalar = {
        "schema_version": "1.0",
        "contract_id": "TASK3_ANIMATION_SPEED_INVARIANCE_V1",
        "current_evidence_state": "IMPLEMENTED_NOT_EXECUTED",
        "experiment_name": "OperationalInteractive",
        "model_version": "TASK3_OPERATIONAL_POOLED_V1",
    }
    for field, expected in expected_scalar.items():
        if protocol.get(field) != expected:
            errors.append(f"{field}: expected {expected!r}")

    evidence_id = protocol.get("evidence_id")
    if not isinstance(evidence_id, str) or not evidence_id:
        errors.append("evidence_id: expected a non-empty string")

    required_files = protocol.get("required_core_files")
    if required_files != [RESULT_FILES[table] for table in EXPECTED_TABLES]:
        errors.append("required_core_files: unexpected table/file contract")

    expected_identity = protocol.get("expected_run_identity")
    expected_identity_fields = (
        "schema_version",
        "config_id",
        "config_sha256",
        "model_version",
        "scenario_id",
        "scenario_family",
        "reference_scenario_id",
        "input_sample_id",
        "replication_id",
        "master_seed",
        "arrival_seed",
        "service_seed",
        "routing_seed",
        "tie_seed",
        "start_state",
        "arrival_mode",
        "arrival_cutoff_seconds",
        "drain_rule",
        "engine_name",
        "engine_version",
        "calibration_status",
        "claim_ceiling",
        "crn_alignment_status",
        "run_status",
    )
    if not isinstance(expected_identity, dict):
        errors.append("expected_run_identity: expected object")
    elif tuple(expected_identity) != expected_identity_fields:
        errors.append("expected_run_identity: fields or order are not frozen")
    elif not HEX64.fullmatch(
        str(expected_identity.get("config_sha256") or "")
    ):
        errors.append("expected_run_identity.config_sha256 must be 64 hex")

    modes = protocol.get("required_run_order")
    expected_modes = (
        (
            "GUI_1X",
            "01_gui_1x",
            "REAL_TIME_SCALE",
            1,
            "PRESENTATION_RENDERED",
        ),
        (
            "GUI_10X",
            "02_gui_10x",
            "REAL_TIME_SCALE",
            10,
            "PRESENTATION_RENDERED",
        ),
        (
            "GUI_VIRTUAL_TIME",
            "03_gui_virtual_time",
            "VIRTUAL_TIME",
            None,
            "ANIMATION_NOT_REQUIRED_BY_EXECUTION_MODE",
        ),
    )
    if not isinstance(modes, list) or len(modes) != len(expected_modes):
        errors.append("required_run_order: expected exactly three modes")
    else:
        for position, (mode, expected) in enumerate(
            zip(modes, expected_modes, strict=True), start=1
        ):
            if not isinstance(mode, dict):
                errors.append(f"required_run_order[{position}]: expected object")
                continue
            actual = (
                mode.get("run_mode"),
                mode.get("directory_name"),
                mode.get("execution_mode"),
                mode.get("real_time_scale"),
                mode.get("animation_condition"),
            )
            if actual != expected:
                errors.append(
                    f"required_run_order[{position}]: expected {expected!r}"
                )

    comparison = protocol.get("core_comparison")
    if not isinstance(comparison, dict):
        errors.append("core_comparison: expected object")
    else:
        if comparison.get("reference_run_mode") != "GUI_1X":
            errors.append("core_comparison.reference_run_mode must be GUI_1X")
        if comparison.get("comparison_semantics") != (
            "EXACT_ORDERED_FIELD_EQUALITY"
        ):
            errors.append("core_comparison.comparison_semantics is not frozen")
        if comparison.get("compared_tables") != list(EXPECTED_TABLES):
            errors.append("core_comparison.compared_tables is not frozen")

    for path_field in (
        "source_run_directory",
        "evidence_root",
        "validation_report",
    ):
        value = protocol.get(path_field)
        if not isinstance(value, str) or not value:
            errors.append(f"{path_field}: expected a non-empty relative path")
        elif Path(value).is_absolute() or ".." in Path(value).parts:
            errors.append(f"{path_field}: must be a project-relative path")

    if errors:
        raise ProtocolError("; ".join(errors))
    return protocol


def _mode_by_name(
    protocol: Mapping[str, Any], run_mode: str
) -> dict[str, Any]:
    for mode in protocol["required_run_order"]:
        if mode["run_mode"] == run_mode:
            return dict(mode)
    raise ValueError(
        f"unknown run mode {run_mode!r}; expected "
        + ", ".join(
            str(mode["run_mode"]) for mode in protocol["required_run_order"]
        )
    )


def _parse_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames is None:
            raise ValueError(f"{path}: missing CSV header")
        return list(reader.fieldnames), list(reader)


def _validate_csv(
    path: Path,
    table_name: str,
    schemas: Mapping[str, Sequence[Mapping[str, str]]],
    errors: list[str],
) -> tuple[list[str], list[dict[str, str]]]:
    try:
        fields, rows = _parse_csv(path)
    except (FileNotFoundError, OSError, UnicodeError, ValueError) as exc:
        errors.append(str(exc))
        return [], []

    expected = [field["field_name"] for field in schemas[table_name]]
    if fields != expected:
        errors.append(
            f"{path}: schema mismatch; expected {expected}, found {fields}"
        )
        return fields, rows

    for line, row in enumerate(rows, start=2):
        for field in schemas[table_name]:
            name = field["field_name"]
            raw = row.get(name)
            if raw is None:
                errors.append(f"{path}:{line}:{name}: missing value")
                continue
            if raw == "":
                if field["nullable"] != "true":
                    errors.append(f"{path}:{line}:{name}: null is not allowed")
                continue
            try:
                data_type = field["data_type"]
                if data_type == "integer":
                    int(raw)
                elif data_type == "number":
                    if not math.isfinite(float(raw)):
                        raise ValueError
                elif data_type == "boolean":
                    if raw not in {"true", "false"}:
                        raise ValueError
                elif data_type != "string":
                    errors.append(
                        f"{path}:{line}:{name}: unsupported type {data_type}"
                    )
            except ValueError:
                errors.append(
                    f"{path}:{line}:{name}: invalid "
                    f"{field['data_type']} {raw!r}"
                )
    return fields, rows


def _validate_one_run(
    run_dir: Path,
    mode: Mapping[str, Any],
    protocol: Mapping[str, Any],
    schemas: Mapping[str, Sequence[Mapping[str, str]]],
) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    tables: dict[str, Any] = {}
    for filename in protocol["required_core_files"]:
        table = TABLE_BY_FILE[filename]
        fields, rows = _validate_csv(
            run_dir / filename, table, schemas, errors
        )
        tables[table] = {
            "filename": filename,
            "fields": fields,
            "rows": rows,
            "row_count": len(rows),
            "sha256": (
                _sha256(run_dir / filename)
                if (run_dir / filename).is_file()
                else None
            ),
        }

    if len(tables["run_manifest"]["rows"]) != 1:
        errors.append(f"{run_dir}: run_manifest must have exactly one row")
    if len(tables["replication_kpis"]["rows"]) != 1:
        errors.append(f"{run_dir}: replication_kpis must have exactly one row")
    if not tables["entity_log"]["rows"]:
        errors.append(f"{run_dir}: entity_log must contain at least one row")

    manifest_row = (
        tables["run_manifest"]["rows"][0]
        if len(tables["run_manifest"]["rows"]) == 1
        else {}
    )
    kpi_row = (
        tables["replication_kpis"]["rows"][0]
        if len(tables["replication_kpis"]["rows"]) == 1
        else {}
    )
    for field, expected in protocol["expected_run_identity"].items():
        if manifest_row.get(field) != expected:
            errors.append(
                f"{run_dir / RESULT_FILES['run_manifest']}:{field}: "
                f"expected {expected!r}, found {manifest_row.get(field)!r}"
            )

    shared_lineage = (
        "schema_version",
        "config_id",
        "config_sha256",
        "model_version",
        "scenario_id",
        "input_sample_id",
        "replication_id",
    )
    for field in shared_lineage:
        manifest_value = manifest_row.get(field)
        if kpi_row and kpi_row.get(field) != manifest_value:
            errors.append(
                f"{run_dir}: replication_kpis.{field} differs from manifest"
            )
        for line, row in enumerate(
            tables["entity_log"]["rows"], start=2
        ):
            if row.get(field) != manifest_value:
                errors.append(
                    f"{run_dir / RESULT_FILES['entity_log']}:{line}:{field}: "
                    "differs from manifest"
                )

    if manifest_row and kpi_row:
        for field in ("arrival_cutoff_seconds", "drain_end_seconds"):
            if kpi_row.get(field) != manifest_row.get(field):
                errors.append(
                    f"{run_dir}: replication_kpis.{field} differs from manifest"
                )
        try:
            expected_count = int(kpi_row["arrivals"])
            completed_count = int(kpi_row["completed_after_drain"])
        except (KeyError, ValueError):
            pass
        else:
            if len(tables["entity_log"]["rows"]) != expected_count:
                errors.append(
                    f"{run_dir}: entity row count differs from arrivals"
                )
            if completed_count != expected_count:
                errors.append(
                    f"{run_dir}: completed_after_drain differs from arrivals"
                )

    traveller_ids = [
        row.get("traveller_id") for row in tables["entity_log"]["rows"]
    ]
    if len(set(traveller_ids)) != len(traveller_ids):
        errors.append(f"{run_dir}: duplicate traveller_id in entity_log")

    metadata_path = run_dir / CAPTURE_METADATA_FILE
    try:
        metadata = _read_json(metadata_path)
    except (FileNotFoundError, OSError, UnicodeError, ValueError) as exc:
        errors.append(str(exc))
        metadata = {}
    missing = [
        field for field in CAPTURE_METADATA_REQUIRED if field not in metadata
    ]
    if missing:
        errors.append(f"{metadata_path}: missing fields {missing}")

    expected_metadata = {
        "schema_version": protocol["schema_version"],
        "contract_id": protocol["contract_id"],
        "evidence_id": protocol["evidence_id"],
        "experiment_name": protocol["experiment_name"],
        "run_mode": mode["run_mode"],
        "directory_name": mode["directory_name"],
        "execution_mode": mode["execution_mode"],
        "real_time_scale": mode["real_time_scale"],
        "animation_condition": mode["animation_condition"],
        "finished_confirmed": True,
    }
    for field, expected in expected_metadata.items():
        if metadata.get(field) != expected:
            errors.append(
                f"{metadata_path}:{field}: expected {expected!r}, "
                f"found {metadata.get(field)!r}"
            )
    if not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9_.-]{1,63}",
        str(metadata.get("operator_role_alias") or ""),
    ):
        errors.append(
            f"{metadata_path}: operator_role_alias must be a role alias"
        )
    if not HEX40.fullmatch(str(metadata.get("model_git_commit") or "")):
        errors.append(f"{metadata_path}: model_git_commit must be 40 hex")
    try:
        captured = datetime.fromisoformat(
            str(metadata.get("capture_utc") or "").replace("Z", "+00:00")
        )
        if captured.tzinfo is None:
            raise ValueError
    except ValueError:
        errors.append(f"{metadata_path}: capture_utc must include a timezone")

    expected_hashes = {
        filename: tables[TABLE_BY_FILE[filename]]["sha256"]
        for filename in protocol["required_core_files"]
    }
    if metadata.get("core_file_sha256") != expected_hashes:
        errors.append(f"{metadata_path}: core_file_sha256 mismatch")

    mtimes = metadata.get("source_file_mtime_ns")
    if not isinstance(mtimes, dict):
        errors.append(f"{metadata_path}: source_file_mtime_ns must be object")
        mtimes = {}
    elif set(mtimes) != set(protocol["required_core_files"]):
        errors.append(f"{metadata_path}: source_file_mtime_ns keys mismatch")
    elif any(not isinstance(value, int) or value <= 0 for value in mtimes.values()):
        errors.append(
            f"{metadata_path}: source_file_mtime_ns values must be positive integers"
        )

    screenshot = run_dir / UI_EVIDENCE_FILE
    if not screenshot.is_file():
        errors.append(f"{screenshot}: missing UI evidence")
    else:
        with screenshot.open("rb") as stream:
            if stream.read(len(PNG_SIGNATURE)) != PNG_SIGNATURE:
                errors.append(f"{screenshot}: not a PNG file")
        actual_ui_hash = _sha256(screenshot)
        if not HEX64.fullmatch(str(metadata.get("ui_evidence_sha256") or "")):
            errors.append(f"{metadata_path}: invalid ui_evidence_sha256")
        elif metadata.get("ui_evidence_sha256") != actual_ui_hash:
            errors.append(f"{metadata_path}: ui_evidence_sha256 mismatch")

    for table in EXPECTED_TABLES:
        rows = tables[table]["rows"]
        for row_number, row in enumerate(rows, start=2):
            label = f"{run_dir / tables[table]['filename']}:{row_number}"
            if row.get("model_version") != protocol["model_version"]:
                errors.append(f"{label}: model_version mismatch")
            if row.get("run_status") != "COMPLETE" and table != "entity_log":
                errors.append(f"{label}: run_status must be COMPLETE")
    if kpi_row:
        if kpi_row.get("conservation_pass") != "true":
            errors.append(
                f"{run_dir / RESULT_FILES['replication_kpis']}: "
                "conservation_pass must be true"
            )
        if kpi_row.get("rejected_or_dropped_count") != "0":
            errors.append(
                f"{run_dir / RESULT_FILES['replication_kpis']}: "
                "rejected_or_dropped_count must be zero"
            )

    return {
        "run_mode": mode["run_mode"],
        "directory_name": mode["directory_name"],
        "run_dir": _portable(run_dir),
        "metadata": metadata,
        "tables": tables,
    }, errors


def _first_differences(
    reference: Mapping[str, Any],
    candidate: Mapping[str, Any],
    limit: int = 20,
) -> list[dict[str, Any]]:
    differences: list[dict[str, Any]] = []
    ref_fields = reference["fields"]
    cand_fields = candidate["fields"]
    if ref_fields != cand_fields:
        differences.append(
            {
                "kind": "HEADER",
                "reference": ref_fields,
                "candidate": cand_fields,
            }
        )
        return differences
    ref_rows = reference["rows"]
    cand_rows = candidate["rows"]
    if len(ref_rows) != len(cand_rows):
        differences.append(
            {
                "kind": "ROW_COUNT",
                "reference": len(ref_rows),
                "candidate": len(cand_rows),
            }
        )
    for row_index, (ref_row, cand_row) in enumerate(
        zip(ref_rows, cand_rows), start=2
    ):
        for field in ref_fields:
            if ref_row.get(field) != cand_row.get(field):
                differences.append(
                    {
                        "kind": "FIELD",
                        "csv_line": row_index,
                        "field": field,
                        "reference": ref_row.get(field),
                        "candidate": cand_row.get(field),
                    }
                )
                if len(differences) >= limit:
                    return differences
    return differences


def validate_evidence(
    protocol_path: Path = DEFAULT_PROTOCOL,
    evidence_root: Path | None = None,
) -> dict[str, Any]:
    try:
        protocol = load_protocol(protocol_path)
    except (FileNotFoundError, OSError, UnicodeError, ValueError) as exc:
        return {
            "schema_version": "1.0",
            "contract_id": "TASK3_ANIMATION_SPEED_INVARIANCE_V1",
            "status": "FAIL",
            "evidence_state": "IMPLEMENTED_NOT_EXECUTED",
            "errors": [str(exc)],
        }

    root = (
        evidence_root.resolve()
        if evidence_root is not None
        else (PROJECT_ROOT / protocol["evidence_root"]).resolve()
    )
    schemas = load_result_schemas(DEFAULT_SCHEMA_REGISTRY)
    captures: list[dict[str, Any]] = []
    errors: list[str] = []
    missing_modes: list[str] = []
    for mode in protocol["required_run_order"]:
        run_dir = root / mode["directory_name"]
        if not run_dir.is_dir():
            missing_modes.append(mode["run_mode"])
            continue
        capture, run_errors = _validate_one_run(
            run_dir, mode, protocol, schemas
        )
        captures.append(capture)
        errors.extend(run_errors)

    if missing_modes:
        return {
            "schema_version": protocol["schema_version"],
            "contract_id": protocol["contract_id"],
            "evidence_id": protocol["evidence_id"],
            "status": "NOT_EXECUTED",
            "evidence_state": "IMPLEMENTED_NOT_EXECUTED",
            "evidence_root": _portable(root),
            "required_run_modes": [
                mode["run_mode"] for mode in protocol["required_run_order"]
            ],
            "captured_run_modes": [
                capture["run_mode"] for capture in captures
            ],
            "missing_run_modes": missing_modes,
            "errors": errors,
            "claim_boundary": protocol["claim_boundary"],
        }

    metadata_commits = {
        str(capture["metadata"].get("model_git_commit") or "")
        for capture in captures
    }
    if len(metadata_commits) != 1:
        errors.append("capture metadata uses different model_git_commit values")
    metadata_source_dirs = {
        str(capture["metadata"].get("source_run_directory") or "")
        for capture in captures
    }
    if metadata_source_dirs != {protocol["source_run_directory"]}:
        errors.append("capture metadata source_run_directory mismatch")

    ui_hashes = [
        str(capture["metadata"].get("ui_evidence_sha256") or "")
        for capture in captures
    ]
    if len(set(ui_hashes)) != len(ui_hashes):
        errors.append(
            "UI evidence hashes must be distinct; a screenshot appears reused"
        )

    source_mtime_vectors: list[tuple[int, ...]] = []
    for capture in captures:
        raw = capture["metadata"].get("source_file_mtime_ns")
        if isinstance(raw, dict):
            try:
                vector = tuple(
                    int(raw[filename])
                    for filename in protocol["required_core_files"]
                )
            except (KeyError, TypeError, ValueError):
                continue
            source_mtime_vectors.append(vector)
    if len(source_mtime_vectors) == len(captures):
        for index in range(1, len(source_mtime_vectors)):
            earlier = source_mtime_vectors[index - 1]
            later = source_mtime_vectors[index]
            if not all(new > old for old, new in zip(earlier, later)):
                errors.append(
                    "source CSV modification times are not strictly increasing "
                    f"from capture {index} to {index + 1}; a GUI rerun is not "
                    "independently evidenced"
                )

    reference = captures[0]
    comparisons: list[dict[str, Any]] = []
    for candidate in captures[1:]:
        table_reports: list[dict[str, Any]] = []
        for table in EXPECTED_TABLES:
            differences = _first_differences(
                reference["tables"][table],
                candidate["tables"][table],
            )
            if differences:
                errors.append(
                    f"{candidate['run_mode']} differs from GUI_1X in {table}"
                )
            table_reports.append(
                {
                    "table": table,
                    "reference_row_count": reference["tables"][table][
                        "row_count"
                    ],
                    "candidate_row_count": candidate["tables"][table][
                        "row_count"
                    ],
                    "reference_sha256": reference["tables"][table]["sha256"],
                    "candidate_sha256": candidate["tables"][table]["sha256"],
                    "exact_ordered_field_equality": not differences,
                    "first_differences": differences,
                }
            )
        comparisons.append(
            {
                "reference_run_mode": reference["run_mode"],
                "candidate_run_mode": candidate["run_mode"],
                "tables": table_reports,
                "status": (
                    "PASS"
                    if all(
                        table["exact_ordered_field_equality"]
                        for table in table_reports
                    )
                    else "FAIL"
                ),
            }
        )

    status = "PASS" if not errors else "FAIL"
    return {
        "schema_version": protocol["schema_version"],
        "contract_id": protocol["contract_id"],
        "evidence_id": protocol["evidence_id"],
        "status": status,
        "evidence_state": (
            "EVIDENCE_ACCEPTED"
            if status == "PASS"
            else "EXECUTED_VALIDATION_FAILED"
        ),
        "evidence_root": _portable(root),
        "comparison_semantics": "EXACT_ORDERED_FIELD_EQUALITY",
        "core_tables": list(EXPECTED_TABLES),
        "excluded_from_core_equality": protocol["core_comparison"][
            "excluded_from_core_equality"
        ],
        "captures": [
            {
                "run_mode": capture["run_mode"],
                "directory_name": capture["directory_name"],
                "model_git_commit": capture["metadata"].get(
                    "model_git_commit"
                ),
                "capture_utc": capture["metadata"].get("capture_utc"),
                "core_file_sha256": capture["metadata"].get(
                    "core_file_sha256"
                ),
                "ui_evidence_sha256": capture["metadata"].get(
                    "ui_evidence_sha256"
                ),
            }
            for capture in captures
        ],
        "comparisons": comparisons,
        "errors": errors,
        "claim_boundary": protocol["claim_boundary"],
    }


def stage_capture(
    *,
    run_mode: str,
    operator_role_alias: str,
    model_git_commit: str,
    ui_evidence: Path,
    protocol_path: Path = DEFAULT_PROTOCOL,
    source_dir: Path | None = None,
    evidence_root: Path | None = None,
    confirm_finished: bool = False,
) -> Path:
    protocol = load_protocol(protocol_path)
    mode = _mode_by_name(protocol, run_mode)
    if not confirm_finished:
        raise ValueError(
            "--confirm-finished is required after the GUI visibly reaches "
            "Finished"
        )
    if not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9_.-]{1,63}", operator_role_alias
    ):
        raise ValueError("operator role alias is invalid")
    if not HEX40.fullmatch(model_git_commit):
        raise ValueError("model git commit must be exactly 40 lowercase hex")
    if not ui_evidence.is_file():
        raise FileNotFoundError(ui_evidence)
    with ui_evidence.open("rb") as stream:
        if stream.read(len(PNG_SIGNATURE)) != PNG_SIGNATURE:
            raise ValueError(f"{ui_evidence}: UI evidence must be a PNG")

    source = (
        source_dir.resolve()
        if source_dir is not None
        else (PROJECT_ROOT / protocol["source_run_directory"]).resolve()
    )
    root = (
        evidence_root.resolve()
        if evidence_root is not None
        else (PROJECT_ROOT / protocol["evidence_root"]).resolve()
    )
    target = root / mode["directory_name"]
    if target.exists():
        raise FileExistsError(
            f"{target} already exists; captures are immutable"
        )

    expected_next = None
    for registered_mode in protocol["required_run_order"]:
        candidate = root / registered_mode["directory_name"]
        if not candidate.exists():
            expected_next = registered_mode["run_mode"]
            break
    if expected_next != run_mode:
        raise ValueError(
            f"registered order requires {expected_next!r}, not {run_mode!r}"
        )

    schemas = load_result_schemas(DEFAULT_SCHEMA_REGISTRY)
    source_errors: list[str] = []
    source_tables: dict[str, list[dict[str, str]]] = {}
    source_mtimes: dict[str, int] = {}
    source_hashes: dict[str, str] = {}
    for filename in protocol["required_core_files"]:
        path = source / filename
        _, rows = _validate_csv(
            path, TABLE_BY_FILE[filename], schemas, source_errors
        )
        source_tables[TABLE_BY_FILE[filename]] = rows
        if path.is_file():
            source_mtimes[filename] = path.stat().st_mtime_ns
            source_hashes[filename] = _sha256(path)
    if source_errors:
        raise ValueError("; ".join(source_errors))
    if len(source_tables["run_manifest"]) != 1:
        raise ValueError("source run_manifest must have exactly one row")
    if len(source_tables["replication_kpis"]) != 1:
        raise ValueError("source replication_kpis must have exactly one row")
    if not source_tables["entity_log"]:
        raise ValueError("source entity_log must not be empty")
    source_manifest = source_tables["run_manifest"][0]
    identity_mismatches = [
        f"{field}: expected {expected!r}, found "
        f"{source_manifest.get(field)!r}"
        for field, expected in protocol["expected_run_identity"].items()
        if source_manifest.get(field) != expected
    ]
    if identity_mismatches:
        raise ValueError(
            "source run is not the canonical interactive identity: "
            + "; ".join(identity_mismatches)
        )
    if source_tables["replication_kpis"][0].get("run_status") != "COMPLETE":
        raise ValueError("source replication_kpis is not COMPLETE")
    if source_tables["replication_kpis"][0].get("conservation_pass") != "true":
        raise ValueError("source conservation_pass is not true")

    previous_metadata: dict[str, Any] | None = None
    for registered_mode in reversed(protocol["required_run_order"]):
        candidate = root / registered_mode["directory_name"]
        if candidate.is_dir():
            previous_metadata = _read_json(candidate / CAPTURE_METADATA_FILE)
            break
    if previous_metadata is not None:
        previous_mtimes = previous_metadata.get("source_file_mtime_ns")
        if not isinstance(previous_mtimes, dict) or not all(
            source_mtimes[filename] > int(previous_mtimes[filename])
            for filename in protocol["required_core_files"]
        ):
            raise ValueError(
                "source CSV modification times have not advanced since the "
                "previous capture; run the GUI experiment again"
            )

    target.mkdir(parents=True, exist_ok=False)
    try:
        for filename in protocol["required_core_files"]:
            shutil.copy2(source / filename, target / filename)
        shutil.copy2(ui_evidence, target / UI_EVIDENCE_FILE)
        metadata = {
            "schema_version": protocol["schema_version"],
            "contract_id": protocol["contract_id"],
            "evidence_id": protocol["evidence_id"],
            "experiment_name": protocol["experiment_name"],
            "run_mode": mode["run_mode"],
            "directory_name": mode["directory_name"],
            "execution_mode": mode["execution_mode"],
            "real_time_scale": mode["real_time_scale"],
            "animation_condition": mode["animation_condition"],
            "operator_role_alias": operator_role_alias,
            "model_git_commit": model_git_commit,
            "capture_utc": datetime.now(timezone.utc)
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z"),
            "finished_confirmed": True,
            "source_run_directory": protocol["source_run_directory"],
            "source_file_mtime_ns": source_mtimes,
            "core_file_sha256": source_hashes,
            "ui_evidence_sha256": _sha256(target / UI_EVIDENCE_FILE),
            "wall_clock_elapsed_seconds": None,
            "wall_clock_excluded_from_model_equality": True,
        }
        _write_json(target / CAPTURE_METADATA_FILE, metadata)
    except Exception:
        shutil.rmtree(target, ignore_errors=True)
        raise
    return target


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Stage or validate animation-speed invariance evidence."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    stage = subparsers.add_parser(
        "stage", help="immutably capture one newly finished GUI run"
    )
    stage.add_argument(
        "--mode",
        required=True,
        choices=("GUI_1X", "GUI_10X", "GUI_VIRTUAL_TIME"),
    )
    stage.add_argument("--operator-role", required=True)
    stage.add_argument("--model-git-commit", required=True)
    stage.add_argument("--ui-evidence", type=Path, required=True)
    stage.add_argument("--confirm-finished", action="store_true")
    stage.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    stage.add_argument("--source-dir", type=Path)
    stage.add_argument("--evidence-root", type=Path)

    validate = subparsers.add_parser(
        "validate", help="compare all registered captures"
    )
    validate.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    validate.add_argument("--evidence-root", type=Path)
    validate.add_argument("--report", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "stage":
        try:
            target = stage_capture(
                run_mode=args.mode,
                operator_role_alias=args.operator_role,
                model_git_commit=args.model_git_commit,
                ui_evidence=args.ui_evidence,
                protocol_path=args.protocol,
                source_dir=args.source_dir,
                evidence_root=args.evidence_root,
                confirm_finished=args.confirm_finished,
            )
        except (FileNotFoundError, OSError, UnicodeError, ValueError) as exc:
            print(f"STAGE FAIL: {exc}", file=sys.stderr)
            return 1
        print(f"STAGED {args.mode}: {_portable(target)}")
        return 0

    report = validate_evidence(args.protocol, args.evidence_root)
    protocol = None
    try:
        protocol = load_protocol(args.protocol)
    except (FileNotFoundError, OSError, UnicodeError, ValueError):
        pass
    report_path = args.report
    if report_path is None and protocol is not None:
        report_path = PROJECT_ROOT / protocol["validation_report"]
    if report_path is not None:
        _write_json(report_path.resolve(), report)
        print(f"REPORT {report_path.resolve()}")
    print(
        f"{report['status']}: {report.get('evidence_state')} "
        f"errors={len(report.get('errors', []))}"
    )
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
