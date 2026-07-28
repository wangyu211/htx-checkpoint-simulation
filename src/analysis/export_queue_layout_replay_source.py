"""Export the minimum public synthetic ledger for queue-layout replay.

The confirmatory AnyLogic batch writes a wide local ledger.  Queue-layout
replay needs only simulated entity identifiers, immutable service inputs, and
the pooled event timestamps used by the exact replay gate.  This exporter
allowlists those fields, rejects unexpected replication coverage, and writes a
small public package with byte-level hashes and an explicit privacy audit.

The package contains synthetic AnyLogic events only.  It is not derived from
video tracks and contains no appearance, biometric, or real-person identity
data.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Mapping, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DESIGN = PROJECT_ROOT / "config" / "queue_layout_replay_study.json"
DEFAULT_LOCAL_ENTITY_LEDGER = (
    PROJECT_ROOT
    / "results"
    / "raw"
    / "confirmatory_capacity_consolidated"
    / "entity_log.csv"
)
DEFAULT_LOCAL_REPLICATION_KPIS = (
    PROJECT_ROOT
    / "results"
    / "analysis"
    / "confirmatory_capacity"
    / "replication_kpis.csv"
)
DEFAULT_OUTPUT_DIR = (
    PROJECT_ROOT / "data" / "derived" / "queue_layout_replay_source"
)

DATASET_ID = "QUEUE_LAYOUT_REPLAY_CURATED_SYNTHETIC_LEDGER_V1"
SCHEMA_VERSION = "1.0"

ENTITY_FIELDS = (
    "replication_id",
    "traveller_id",
    "arrival_seconds",
    "security_service_demand_seconds",
    "immigration_primary_service_demand_seconds",
    "additional_check_flag",
    "additional_check_service_demand_seconds",
    "lane_tie_u",
    "security_queue_join_seconds",
    "security_start_seconds",
    "security_end_seconds",
    "immigration_queue_join_seconds",
    "immigration_start_seconds",
    "exit_seconds",
)

KPI_FIELDS = (
    "replication_id",
    "total_queue_wait_p95_seconds",
    "run_status",
)

SOURCE_METADATA_FIELDS = (
    "model_version",
    "config_id",
    "config_sha256",
    "scenario_id",
    "input_sample_id",
)

PROHIBITED_PUBLIC_FIELDS = frozenset(
    {
        "appearance",
        "biometric",
        "face_crop",
        "identity_embedding",
        "reid_embedding",
        "person_name",
        "email",
        "source_video_path",
        "security_resource_id",
        "immigration_resource_id",
        "immigration_lane_id",
        "automation_u",
        "additional_check_u",
    }
)

SIMULATED_TRAVELLER_ID = re.compile(
    r"^LOCAL_WINDOW_HPP_BASE_R(?P<replication>\d{3})_T\d{5}$"
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError(f"{path} has no header")
        return list(reader.fieldnames), list(reader)


def _write_csv(
    path: Path,
    rows: Sequence[Mapping[str, object]],
    fields: Sequence[str],
) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fields,
            extrasaction="raise",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def _write_json(path: Path, payload: Mapping[str, object]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(payload, indent=2, sort_keys=True))
        handle.write("\n")


def _required_columns(
    actual: Sequence[str],
    required: Sequence[str],
    *,
    table: str,
) -> None:
    missing = sorted(set(required) - set(actual))
    if missing:
        raise ValueError(f"{table} is missing required columns: {missing}")


def _source_filter(
    rows: Sequence[Mapping[str, str]],
    source: Mapping[str, object],
) -> list[dict[str, str]]:
    selected = [
        dict(row)
        for row in rows
        if row.get("scenario_id") == str(source["scenario_id"])
        and row.get("input_sample_id") == str(source["input_sample_id"])
    ]
    if not selected:
        raise ValueError("local source has no frozen reference rows")
    return selected


def _validate_source_rows(
    entity_rows: Sequence[Mapping[str, str]],
    kpi_rows: Sequence[Mapping[str, str]],
    source: Mapping[str, object],
) -> None:
    first = int(source["replication_ids"]["first"])
    last = int(source["replication_ids"]["last"])
    expected = set(range(first, last + 1))
    actual_entity = {int(row["replication_id"]) for row in entity_rows}
    actual_kpi = {int(row["replication_id"]) for row in kpi_rows}
    if actual_entity != expected:
        raise ValueError("entity ledger replication coverage is not 1..50")
    if actual_kpi != expected or len(kpi_rows) != len(expected):
        raise ValueError("registered P95 table must contain one row per run")

    metadata_fields = (
        "model_version",
        "config_id",
        "config_sha256",
        "scenario_id",
        "input_sample_id",
    )
    for field in metadata_fields:
        expected_value = str(source[field])
        if any(row.get(field) != expected_value for row in entity_rows):
            raise ValueError(f"entity ledger {field} differs from design")
        if any(row.get(field) != expected_value for row in kpi_rows):
            raise ValueError(f"registered P95 {field} differs from design")
    if any(row.get("run_status") != str(source["run_status"]) for row in kpi_rows):
        raise ValueError("registered P95 includes a non-complete run")

    identifiers: set[str] = set()
    for row in entity_rows:
        traveller_id = row["traveller_id"]
        match = SIMULATED_TRAVELLER_ID.fullmatch(traveller_id)
        if match is None:
            raise ValueError(
                f"traveller_id is not a synthetic model identifier: {traveller_id}"
            )
        if int(match.group("replication")) != int(row["replication_id"]):
            raise ValueError("traveller_id replication prefix is inconsistent")
        if traveller_id in identifiers:
            raise ValueError(f"duplicate synthetic traveller_id: {traveller_id}")
        identifiers.add(traveller_id)


def audit_curated_package(
    *,
    entity_path: Path,
    kpi_path: Path,
    manifest_path: Path,
) -> dict[str, object]:
    """Validate a public package without consulting the ignored raw ledger."""

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("dataset_id") != DATASET_ID:
        raise ValueError("curated source dataset_id is not frozen")
    if manifest.get("status") != "PASS":
        raise ValueError("curated source manifest status is not PASS")
    privacy = manifest.get("privacy_audit")
    if not isinstance(privacy, Mapping):
        raise ValueError("curated source manifest has no privacy audit")
    required_privacy = {
        "contains_video_person_data": False,
        "contains_appearance_or_biometric_data": False,
        "contains_real_person_identifiers": False,
        "traveller_ids_are_simulated_entity_ids": True,
        "status": "PASS",
    }
    for field, expected in required_privacy.items():
        if privacy.get(field) != expected:
            raise ValueError(f"privacy audit {field} must be {expected!r}")

    entity_fields, entity_rows = _read_csv(entity_path)
    kpi_fields, kpi_rows = _read_csv(kpi_path)
    if entity_fields != list(ENTITY_FIELDS):
        raise ValueError("curated entity ledger does not match the allowlist")
    if kpi_fields != list(KPI_FIELDS):
        raise ValueError("curated registered P95 does not match the allowlist")
    leaked = (set(entity_fields) | set(kpi_fields)) & PROHIBITED_PUBLIC_FIELDS
    if leaked:
        raise ValueError(f"prohibited public fields detected: {sorted(leaked)}")

    identifiers: set[str] = set()
    entity_replications: set[int] = set()
    for row in entity_rows:
        replication_id = int(row["replication_id"])
        traveller_id = row["traveller_id"]
        match = SIMULATED_TRAVELLER_ID.fullmatch(traveller_id)
        if match is None:
            raise ValueError(
                "curated traveller_id is not a synthetic model identifier"
            )
        if int(match.group("replication")) != replication_id:
            raise ValueError(
                "curated traveller_id replication prefix is inconsistent"
            )
        if traveller_id in identifiers:
            raise ValueError("curated traveller_id is duplicated")
        identifiers.add(traveller_id)
        entity_replications.add(replication_id)
    kpi_replications = {int(row["replication_id"]) for row in kpi_rows}
    if entity_replications != kpi_replications:
        raise ValueError("curated entity and P95 replication sets differ")

    provenance = manifest.get("provenance")
    if not isinstance(provenance, Mapping):
        raise ValueError("curated source manifest provenance is missing")
    expected_replications = set(
        range(
            int(provenance["replication_first"]),
            int(provenance["replication_last"]) + 1,
        )
    )
    if entity_replications != expected_replications:
        raise ValueError("curated replication coverage differs from manifest")
    if len(entity_replications) != int(provenance["replication_count"]):
        raise ValueError("curated replication count differs from manifest")

    files = manifest.get("files")
    if not isinstance(files, Mapping):
        raise ValueError("curated source manifest files block is missing")
    expected_files = {
        "entity_ledger.csv": (entity_path, len(entity_rows)),
        "registered_p95.csv": (kpi_path, len(kpi_rows)),
    }
    for name, (path, row_count) in expected_files.items():
        evidence = files.get(name)
        if not isinstance(evidence, Mapping):
            raise ValueError(f"manifest evidence missing for {name}")
        if evidence.get("row_count") != row_count:
            raise ValueError(f"manifest row count mismatch for {name}")
        if evidence.get("sha256") != _sha256(path):
            raise ValueError(f"manifest hash mismatch for {name}")
    return manifest


def export_curated_source(
    *,
    entity_source_path: Path,
    kpi_source_path: Path,
    output_dir: Path,
    design_path: Path = DEFAULT_DESIGN,
) -> dict[str, object]:
    design = json.loads(design_path.read_text(encoding="utf-8"))
    source = design.get("source_ledger")
    if not isinstance(source, Mapping):
        raise ValueError("design source_ledger is missing")

    entity_fields, all_entity_rows = _read_csv(entity_source_path)
    kpi_fields, all_kpi_rows = _read_csv(kpi_source_path)
    _required_columns(
        entity_fields,
        (*SOURCE_METADATA_FIELDS, *ENTITY_FIELDS),
        table="entity ledger",
    )
    _required_columns(
        kpi_fields,
        (*SOURCE_METADATA_FIELDS, *KPI_FIELDS),
        table="replication KPIs",
    )
    entity_rows = _source_filter(all_entity_rows, source)
    kpi_rows = _source_filter(all_kpi_rows, source)
    _validate_source_rows(entity_rows, kpi_rows, source)

    entity_rows.sort(
        key=lambda row: (
            int(row["replication_id"]),
            float(row["arrival_seconds"]),
            row["traveller_id"],
        )
    )
    kpi_rows.sort(key=lambda row: int(row["replication_id"]))
    curated_entities = [
        {field: row.get(field, "") for field in ENTITY_FIELDS}
        for row in entity_rows
    ]
    curated_kpis = [
        {field: row.get(field, "") for field in KPI_FIELDS}
        for row in kpi_rows
    ]

    output_dir.mkdir(parents=True, exist_ok=False)
    entity_path = output_dir / "entity_ledger.csv"
    kpi_path = output_dir / "registered_p95.csv"
    manifest_path = output_dir / "manifest.json"
    _write_csv(entity_path, curated_entities, ENTITY_FIELDS)
    _write_csv(kpi_path, curated_kpis, KPI_FIELDS)

    counts = Counter(int(row["replication_id"]) for row in entity_rows)
    manifest: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "dataset_id": DATASET_ID,
        "status": "PASS",
        "classification": "SYNTHETIC_ANYLOGIC_EVENT_LEDGER",
        "purpose": (
            "Minimum public source needed to reproduce the exact-gated "
            "pooled-versus-separate queue-layout replay."
        ),
        "provenance": {
            "generator": "OperationalCheckpointModel",
            "model_version": source["model_version"],
            "config_id": source["config_id"],
            "config_sha256": source["config_sha256"],
            "scenario_id": source["scenario_id"],
            "input_sample_id": source["input_sample_id"],
            "replication_first": min(counts),
            "replication_last": max(counts),
            "replication_count": len(counts),
            "raw_entity_source_sha256": _sha256(entity_source_path),
            "raw_kpi_source_sha256": _sha256(kpi_source_path),
            "selection": (
                "scenario_id and input_sample_id frozen in "
                "config/queue_layout_replay_study.json"
            ),
        },
        "field_allowlists": {
            "entity_ledger.csv": list(ENTITY_FIELDS),
            "registered_p95.csv": list(KPI_FIELDS),
        },
        "privacy_audit": {
            "status": "PASS",
            "contains_video_person_data": False,
            "contains_appearance_or_biometric_data": False,
            "contains_real_person_identifiers": False,
            "traveller_ids_are_simulated_entity_ids": True,
            "traveller_id_pattern": SIMULATED_TRAVELLER_ID.pattern,
            "removed_wide_ledger_fields": sorted(
                (set(entity_fields) | set(kpi_fields))
                - set(ENTITY_FIELDS)
                - set(KPI_FIELDS)
            ),
            "field_allowlist_enforced": True,
        },
        "files": {
            "entity_ledger.csv": {
                "row_count": len(curated_entities),
                "replication_count": len(counts),
                "minimum_rows_per_replication": min(counts.values()),
                "maximum_rows_per_replication": max(counts.values()),
                "bytes": entity_path.stat().st_size,
                "sha256": _sha256(entity_path),
            },
            "registered_p95.csv": {
                "row_count": len(curated_kpis),
                "replication_count": len(curated_kpis),
                "bytes": kpi_path.stat().st_size,
                "sha256": _sha256(kpi_path),
            },
        },
        "claim_boundary": (
            "These are simulated traveller events from the registered "
            "AnyLogic assumption sandbox. They are not observations of "
            "people in the supplied video and do not validate a site policy."
        ),
    }
    _write_json(manifest_path, manifest)
    audit_curated_package(
        entity_path=entity_path,
        kpi_path=kpi_path,
        manifest_path=manifest_path,
    )
    return manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Export the public minimum synthetic queue replay source."
    )
    parser.add_argument(
        "--entity-source",
        type=Path,
        default=DEFAULT_LOCAL_ENTITY_LEDGER,
        help="Local wide AnyLogic entity ledger (ignored by Git).",
    )
    parser.add_argument(
        "--kpi-source",
        type=Path,
        default=DEFAULT_LOCAL_REPLICATION_KPIS,
        help="Local AnyLogic replication KPI table.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="New public curated-source directory.",
    )
    parser.add_argument(
        "--design",
        type=Path,
        default=DEFAULT_DESIGN,
        help="Frozen queue-layout replay design.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    manifest = export_curated_source(
        entity_source_path=args.entity_source,
        kpi_source_path=args.kpi_source,
        output_dir=args.output_dir,
        design_path=args.design,
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
