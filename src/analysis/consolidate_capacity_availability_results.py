"""Build the immutable Part 2 capacity-availability analysis dataset.

Part 2 reuses only the Reference arm from the completed Part 1 confirmatory
study and combines it with newly executed reduced-capacity arms.  This module
keeps that reuse auditable:

* all three Part 1 source tables must match the hashes recorded in the compact
  confirmatory audit manifest before any rows are selected;
* the Reference and reduced-capacity run-key sets must exactly match the
  registered scenario x input-sample x replication design;
* manifest, KPI and entity rows must preserve run and configuration lineage;
* output is written only after every validation gate passes, and never into a
  Part 1 source or analysis directory.

The public function accepts explicit expected scenario, sample and replication
sets so unit tests (and any later registered design) do not need 750 fixtures.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from src.analysis.validate_operational_contract import PROJECT_ROOT
from src.analysis.validate_operational_results import (
    DEFAULT_SCHEMA_REGISTRY,
    RESULT_FILES,
    load_result_schemas,
    read_csv,
)


CONTRACT = "TASK3_CAPACITY_AVAILABILITY_CONSOLIDATION_V1"
REFERENCE_SCENARIO_ID = "REFERENCE_ASSUMPTION_SANDBOX_V1"
REDUCTION_SCENARIO_IDS = (
    "CAPACITY_AVAIL_SECURITY_MINUS_4",
    "CAPACITY_AVAIL_IMMIGRATION_MINUS_3",
    "CAPACITY_AVAIL_JOINT_MINUS_4_MINUS_3",
    "CAPACITY_AVAIL_SEVERE_JOINT_30_17",
)
INPUT_SAMPLE_IDS = (
    "LOCAL_WINDOW_HPP_EXACT95_LOW",
    "LOCAL_WINDOW_HPP_BASE",
    "LOCAL_WINDOW_HPP_EXACT95_HIGH",
)
REPLICATION_IDS = tuple(range(1, 51))

DEFAULT_REFERENCE_SOURCE_DIR = (
    PROJECT_ROOT / "results" / "raw" / "confirmatory_capacity_consolidated"
)
DEFAULT_REFERENCE_AUDIT_MANIFEST = (
    PROJECT_ROOT
    / "results"
    / "analysis"
    / "confirmatory_capacity"
    / "audit_manifest.json"
)
DEFAULT_REDUCTION_SOURCE_ROOT = (
    PROJECT_ROOT / "results" / "raw" / "capacity_availability"
)
DEFAULT_OUTPUT_DIR = (
    PROJECT_ROOT / "results" / "raw" / "capacity_availability_consolidated"
)
PART1_PROTECTED_DIRS = (
    PROJECT_ROOT / "results" / "raw" / "confirmatory_capacity",
    DEFAULT_REFERENCE_SOURCE_DIR,
    DEFAULT_REFERENCE_AUDIT_MANIFEST.parent,
)
REPLICATION_DIRECTORY = re.compile(r"^replication_(\d{3,})$")
CRN_SEED_FIELDS = (
    "master_seed",
    "arrival_seed",
    "service_seed",
    "routing_seed",
    "tie_seed",
)

RunKey = tuple[str, str, int]


def _run_key(row: Mapping[str, str]) -> RunKey:
    try:
        replication_id = int(row["replication_id"])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("row has an invalid replication_id") from error
    return (
        row["scenario_id"],
        row["input_sample_id"],
        replication_id,
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_exact(
    path: Path,
    expected_fields: Sequence[str],
) -> list[dict[str, str]]:
    actual_fields, rows = read_csv(path)
    if actual_fields != list(expected_fields):
        raise ValueError(
            f"{path}: schema mismatch; expected {list(expected_fields)}, "
            f"found {actual_fields}"
        )
    return rows


def _write_exact(
    path: Path,
    fields: Sequence[str],
    rows: Sequence[Mapping[str, str]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=list(fields),
            extrasaction="raise",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def _normalise_design_axis(
    values: Sequence[str] | Sequence[int],
    label: str,
) -> tuple[str, ...] | tuple[int, ...]:
    normalised = tuple(values)
    if not normalised:
        raise ValueError(f"{label} must not be empty")
    if len(set(normalised)) != len(normalised):
        raise ValueError(f"{label} contains duplicates")
    if label == "replication_ids":
        if any(
            isinstance(value, bool)
            or not isinstance(value, int)
            or value <= 0
            for value in normalised
        ):
            raise ValueError("replication_ids must be positive integers")
    elif any(not isinstance(value, str) or not value for value in normalised):
        raise ValueError(f"{label} must contain non-empty strings")
    return normalised


def _expected_keys(
    scenario_ids: Sequence[str],
    input_sample_ids: Sequence[str],
    replication_ids: Sequence[int],
) -> set[RunKey]:
    return {
        (scenario_id, input_sample_id, replication_id)
        for scenario_id in scenario_ids
        for input_sample_id in input_sample_ids
        for replication_id in replication_ids
    }


def _format_keys(keys: Iterable[RunKey], limit: int = 5) -> str:
    ordered = sorted(keys)
    displayed = ", ".join(repr(key) for key in ordered[:limit])
    if len(ordered) > limit:
        displayed += f", ... ({len(ordered)} total)"
    return displayed


def _require_exact_keys(
    actual: set[RunKey],
    expected: set[RunKey],
    label: str,
) -> None:
    unexpected = actual - expected
    missing = expected - actual
    if unexpected:
        raise ValueError(
            f"{label}: unexpected run keys: {_format_keys(unexpected)}"
        )
    if missing:
        raise ValueError(f"{label}: missing run keys: {_format_keys(missing)}")


def _unique_rows_by_run_key(
    rows: Sequence[Mapping[str, str]],
    label: str,
) -> dict[RunKey, Mapping[str, str]]:
    indexed: dict[RunKey, Mapping[str, str]] = {}
    for row in rows:
        key = _run_key(row)
        if key in indexed:
            raise ValueError(f"{label}: duplicate run key {key}")
        indexed[key] = row
    return indexed


def _validate_entity_rows(
    entity_rows: Sequence[Mapping[str, str]],
    manifests: Mapping[RunKey, Mapping[str, str]],
    label: str,
) -> None:
    seen_entities: set[tuple[str, str, int, str]] = set()
    lineage_fields = ("config_id", "config_sha256", "model_version")
    for row in entity_rows:
        key = _run_key(row)
        manifest = manifests.get(key)
        if manifest is None:
            raise ValueError(
                f"{label}: entity row has no matching run manifest for {key}"
            )
        traveller_id = row["traveller_id"]
        entity_key = (*key, traveller_id)
        if entity_key in seen_entities:
            raise ValueError(f"{label}: duplicate entity key {entity_key}")
        seen_entities.add(entity_key)
        for field in lineage_fields:
            if row[field] != manifest[field]:
                raise ValueError(
                    f"{label}: entity {entity_key} has {field}={row[field]!r}; "
                    f"manifest has {manifest[field]!r}"
                )


def _validate_kpi_rows(
    kpi_rows: Sequence[Mapping[str, str]],
    manifests: Mapping[RunKey, Mapping[str, str]],
    label: str,
) -> dict[RunKey, Mapping[str, str]]:
    indexed = _unique_rows_by_run_key(kpi_rows, label)
    if set(indexed) != set(manifests):
        unexpected = set(indexed) - set(manifests)
        missing = set(manifests) - set(indexed)
        details: list[str] = []
        if unexpected:
            details.append(f"unexpected={_format_keys(unexpected)}")
        if missing:
            details.append(f"missing={_format_keys(missing)}")
        raise ValueError(
            f"{label}: KPI and manifest run keys differ; {'; '.join(details)}"
        )
    lineage_fields = ("config_id", "config_sha256", "model_version")
    for key, row in indexed.items():
        manifest = manifests[key]
        for field in lineage_fields:
            if row[field] != manifest[field]:
                raise ValueError(
                    f"{label}: KPI {key} has {field}={row[field]!r}; "
                    f"manifest has {manifest[field]!r}"
                )
    return indexed


def _validate_cross_scenario_seed_lineage(
    manifests: Mapping[RunKey, Mapping[str, str]],
    *,
    reference_scenario_id: str,
    reduction_scenario_ids: Sequence[str],
    input_sample_ids: Sequence[str],
    replication_ids: Sequence[int],
) -> None:
    """Require exact exogenous-stream reuse for every registered pairing."""

    for input_sample_id in input_sample_ids:
        for replication_id in replication_ids:
            reference_key = (
                reference_scenario_id,
                input_sample_id,
                replication_id,
            )
            reference = manifests[reference_key]
            reference_seeds = tuple(
                reference[field] for field in CRN_SEED_FIELDS
            )
            for scenario_id in reduction_scenario_ids:
                scenario_key = (
                    scenario_id,
                    input_sample_id,
                    replication_id,
                )
                scenario_seeds = tuple(
                    manifests[scenario_key][field]
                    for field in CRN_SEED_FIELDS
                )
                if scenario_seeds != reference_seeds:
                    raise ValueError(
                        "Cross-scenario seed lineage mismatch for "
                        f"{scenario_key}; expected {dict(zip(CRN_SEED_FIELDS, reference_seeds))}, "
                        f"found {dict(zip(CRN_SEED_FIELDS, scenario_seeds))}"
                    )


def _audited_reference_hashes(
    audit_manifest_path: Path,
) -> tuple[dict[str, str], dict[str, object]]:
    if not audit_manifest_path.is_file():
        raise FileNotFoundError(
            f"Reference audit manifest not found: {audit_manifest_path}"
        )
    try:
        audit = json.loads(audit_manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(
            f"{audit_manifest_path}: invalid JSON audit manifest"
        ) from error
    if audit.get("status") != "PASS":
        raise ValueError(
            f"{audit_manifest_path}: Part 1 audit status is not PASS"
        )
    try:
        hashes = {
            RESULT_FILES["run_manifest"]: str(
                audit["tracked_artifacts"][RESULT_FILES["run_manifest"]]
            ).lower(),
            RESULT_FILES["replication_kpis"]: str(
                audit["tracked_artifacts"][RESULT_FILES["replication_kpis"]]
            ).lower(),
            RESULT_FILES["entity_log"]: str(
                audit["source_entity_log"]["sha256"]
            ).lower(),
        }
    except (KeyError, TypeError) as error:
        raise ValueError(
            f"{audit_manifest_path}: missing audited source hashes"
        ) from error
    if any(not re.fullmatch(r"[0-9a-f]{64}", value) for value in hashes.values()):
        raise ValueError(
            f"{audit_manifest_path}: audited source hash is not SHA-256"
        )
    return hashes, audit


def _load_reference_rows(
    reference_source_dir: Path,
    audit_manifest_path: Path,
    fields: Mapping[str, Sequence[str]],
    *,
    reference_scenario_id: str,
    expected_keys: set[RunKey],
) -> tuple[
    dict[str, list[dict[str, str]]],
    dict[str, object],
]:
    audited_hashes, audit = _audited_reference_hashes(audit_manifest_path)
    rows_by_table: dict[str, list[dict[str, str]]] = {}
    source_table_metadata: dict[str, object] = {}

    for table, filename in RESULT_FILES.items():
        path = reference_source_dir / filename
        if not path.is_file():
            raise FileNotFoundError(f"Reference source file not found: {path}")
        actual_hash = _sha256(path)
        expected_hash = audited_hashes[filename]
        if actual_hash != expected_hash:
            raise ValueError(
                f"{path}: SHA-256 mismatch; expected {expected_hash}, "
                f"found {actual_hash}"
            )
        rows = _read_exact(path, fields[table])
        rows_by_table[table] = rows
        source_table_metadata[filename] = {
            "path": str(path),
            "sha256": actual_hash,
            "source_row_count": len(rows),
        }

    try:
        audited_run_count = int(audit["run_count"])
        audited_entity_count = int(audit["source_entity_log"]["row_count"])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(
            f"{audit_manifest_path}: missing audited source row counts"
        ) from error
    if len(rows_by_table["run_manifest"]) != audited_run_count:
        raise ValueError(
            "Reference run-manifest row count does not match audit manifest"
        )
    if len(rows_by_table["replication_kpis"]) != audited_run_count:
        raise ValueError(
            "Reference KPI row count does not match audit manifest"
        )
    if len(rows_by_table["entity_log"]) != audited_entity_count:
        raise ValueError(
            "Reference entity row count does not match audit manifest"
        )

    all_manifests = _unique_rows_by_run_key(
        rows_by_table["run_manifest"], "Reference source run manifest"
    )
    _validate_kpi_rows(
        rows_by_table["replication_kpis"],
        all_manifests,
        "Reference source KPIs",
    )
    _validate_entity_rows(
        rows_by_table["entity_log"],
        all_manifests,
        "Reference source entities",
    )

    selected = {
        table: [
            row
            for row in rows
            if row["scenario_id"] == reference_scenario_id
        ]
        for table, rows in rows_by_table.items()
    }
    selected_manifests = _unique_rows_by_run_key(
        selected["run_manifest"], "Selected Reference run manifest"
    )
    _require_exact_keys(
        set(selected_manifests),
        expected_keys,
        "Selected Reference coverage",
    )
    _validate_kpi_rows(
        selected["replication_kpis"],
        selected_manifests,
        "Selected Reference KPIs",
    )
    _validate_entity_rows(
        selected["entity_log"],
        selected_manifests,
        "Selected Reference entities",
    )
    for table, filename in RESULT_FILES.items():
        source_table_metadata[filename]["selected_row_count"] = len(
            selected[table]
        )

    metadata = {
        "audit_manifest": {
            "path": str(audit_manifest_path),
            "sha256": _sha256(audit_manifest_path),
            "status": audit["status"],
        },
        "source_dir": str(reference_source_dir),
        "hash_verification_status": "PASS",
        "tables": source_table_metadata,
    }
    return selected, metadata


def _tree_digest(entries: Sequence[tuple[str, str]]) -> str:
    """Hash a canonical list of relative-path and file-hash pairs."""

    digest = hashlib.sha256()
    for relative_path, file_hash in sorted(entries):
        digest.update(relative_path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(file_hash.encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def _load_reduction_rows(
    source_root: Path,
    fields: Mapping[str, Sequence[str]],
    *,
    expected_keys: set[RunKey],
) -> tuple[
    dict[str, list[dict[str, str]]],
    dict[str, object],
]:
    leaves = sorted(source_root.rglob(RESULT_FILES["run_manifest"]))
    if not leaves:
        raise FileNotFoundError(
            f"No {RESULT_FILES['run_manifest']} files under {source_root}"
        )

    rows_by_table: dict[str, list[dict[str, str]]] = {
        table: [] for table in RESULT_FILES
    }
    source_hash_entries: dict[str, list[tuple[str, str]]] = {
        table: [] for table in RESULT_FILES
    }
    source_bytes = {table: 0 for table in RESULT_FILES}
    manifests: dict[RunKey, Mapping[str, str]] = {}

    for manifest_path in leaves:
        leaf = manifest_path.parent
        leaf_rows: dict[str, list[dict[str, str]]] = {}
        for table, filename in RESULT_FILES.items():
            path = leaf / filename
            if not path.is_file():
                raise FileNotFoundError(f"Reduction source file not found: {path}")
            leaf_rows[table] = _read_exact(path, fields[table])
            relative_path = path.relative_to(source_root).as_posix()
            source_hash_entries[table].append(
                (relative_path, _sha256(path))
            )
            source_bytes[table] += path.stat().st_size

        if (
            len(leaf_rows["run_manifest"]) != 1
            or len(leaf_rows["replication_kpis"]) != 1
        ):
            raise ValueError(
                f"{leaf}: expected exactly one manifest row and one KPI row"
            )
        manifest = leaf_rows["run_manifest"][0]
        key = _run_key(manifest)
        if key not in expected_keys:
            raise ValueError(f"Reduction source: unexpected run key {key}")
        if key in manifests:
            raise ValueError(f"Reduction source: duplicate run key {key}")

        replication_match = REPLICATION_DIRECTORY.fullmatch(leaf.name)
        if (
            leaf.parent.name != key[1]
            or leaf.parent.parent.name != key[0]
            or replication_match is None
            or int(replication_match.group(1)) != key[2]
        ):
            raise ValueError(
                f"{leaf}: directory lineage does not match CSV run key {key}"
            )
        manifests[key] = manifest

        kpi = leaf_rows["replication_kpis"][0]
        if _run_key(kpi) != key:
            raise ValueError(f"{leaf}: manifest and KPI run keys differ")
        for field in ("config_id", "config_sha256", "model_version"):
            if kpi[field] != manifest[field]:
                raise ValueError(
                    f"{leaf}: KPI {field} does not match run manifest"
                )
        _validate_entity_rows(
            leaf_rows["entity_log"],
            {key: manifest},
            str(leaf),
        )
        for table in RESULT_FILES:
            rows_by_table[table].extend(leaf_rows[table])

    _require_exact_keys(
        set(manifests),
        expected_keys,
        "Reduction source coverage",
    )
    _validate_kpi_rows(
        rows_by_table["replication_kpis"],
        manifests,
        "Reduction source KPIs",
    )
    _validate_entity_rows(
        rows_by_table["entity_log"],
        manifests,
        "Reduction source entities",
    )

    table_metadata: dict[str, object] = {}
    for table, filename in RESULT_FILES.items():
        table_metadata[filename] = {
            "file_count": len(source_hash_entries[table]),
            "row_count": len(rows_by_table[table]),
            "byte_count": source_bytes[table],
            "tree_sha256": _tree_digest(source_hash_entries[table]),
        }
    metadata = {
        "source_root": str(source_root),
        "leaf_count": len(leaves),
        "tree_digest_definition": (
            "SHA256 over sorted UTF-8 relative_path + NUL + lowercase "
            "file_sha256 + LF records"
        ),
        "tables": table_metadata,
    }
    return rows_by_table, metadata


def _protect_part1_outputs(
    output_dir: Path,
    reference_source_dir: Path,
    audit_manifest_path: Path,
) -> None:
    resolved_output = output_dir.resolve()
    protected = {
        path.resolve()
        for path in (
            *PART1_PROTECTED_DIRS,
            reference_source_dir,
            audit_manifest_path.parent,
        )
    }
    for protected_dir in protected:
        if (
            resolved_output == protected_dir
            or protected_dir in resolved_output.parents
            or resolved_output in protected_dir.parents
        ):
            raise ValueError(
                f"Refusing Part 2 output that overlaps a Part 1 directory: "
                f"{resolved_output}"
            )


def consolidate_capacity_availability_results(
    reduction_source_root: Path = DEFAULT_REDUCTION_SOURCE_ROOT,
    reference_source_dir: Path = DEFAULT_REFERENCE_SOURCE_DIR,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    *,
    audit_manifest_path: Path = DEFAULT_REFERENCE_AUDIT_MANIFEST,
    schema_registry_path: Path = DEFAULT_SCHEMA_REGISTRY,
    reference_scenario_id: str = REFERENCE_SCENARIO_ID,
    reduction_scenario_ids: Sequence[str] = REDUCTION_SCENARIO_IDS,
    input_sample_ids: Sequence[str] = INPUT_SAMPLE_IDS,
    replication_ids: Sequence[int] = REPLICATION_IDS,
) -> dict[str, object]:
    """Verify, select, consolidate and merge the registered Part 2 dataset."""

    reduction_scenarios = _normalise_design_axis(
        reduction_scenario_ids, "reduction_scenario_ids"
    )
    samples = _normalise_design_axis(input_sample_ids, "input_sample_ids")
    replications = _normalise_design_axis(replication_ids, "replication_ids")
    if not isinstance(reference_scenario_id, str) or not reference_scenario_id:
        raise ValueError("reference_scenario_id must be a non-empty string")
    if reference_scenario_id in reduction_scenarios:
        raise ValueError(
            "reference_scenario_id must not appear in reduction_scenario_ids"
        )

    reduction_source_root = reduction_source_root.resolve()
    reference_source_dir = reference_source_dir.resolve()
    output_dir = output_dir.resolve()
    audit_manifest_path = audit_manifest_path.resolve()
    schema_registry_path = schema_registry_path.resolve()
    _protect_part1_outputs(
        output_dir, reference_source_dir, audit_manifest_path
    )

    schemas = load_result_schemas(schema_registry_path)
    fields = {
        table: [item["field_name"] for item in schemas[table]]
        for table in RESULT_FILES
    }
    reference_keys = _expected_keys(
        (reference_scenario_id,), samples, replications
    )
    reduction_keys = _expected_keys(
        reduction_scenarios, samples, replications
    )
    combined_keys = reference_keys | reduction_keys

    reference_rows, reference_metadata = _load_reference_rows(
        reference_source_dir,
        audit_manifest_path,
        fields,
        reference_scenario_id=reference_scenario_id,
        expected_keys=reference_keys,
    )
    reduction_rows, reduction_metadata = _load_reduction_rows(
        reduction_source_root,
        fields,
        expected_keys=reduction_keys,
    )

    merged: dict[str, list[dict[str, str]]] = {}
    for table in RESULT_FILES:
        merged[table] = [
            *reference_rows[table],
            *reduction_rows[table],
        ]
    merged_manifests = _unique_rows_by_run_key(
        merged["run_manifest"], "Merged run manifest"
    )
    _require_exact_keys(
        set(merged_manifests),
        combined_keys,
        "Merged Part 2 coverage",
    )
    _validate_kpi_rows(
        merged["replication_kpis"],
        merged_manifests,
        "Merged Part 2 KPIs",
    )
    _validate_entity_rows(
        merged["entity_log"],
        merged_manifests,
        "Merged Part 2 entities",
    )
    _validate_cross_scenario_seed_lineage(
        merged_manifests,
        reference_scenario_id=reference_scenario_id,
        reduction_scenario_ids=reduction_scenarios,
        input_sample_ids=samples,
        replication_ids=replications,
    )

    merged["run_manifest"].sort(key=_run_key)
    merged["replication_kpis"].sort(key=_run_key)
    merged["entity_log"].sort(
        key=lambda row: (*_run_key(row), row["traveller_id"])
    )

    # No output mutation occurs until every source, coverage and lineage gate
    # above has succeeded.
    for table, filename in RESULT_FILES.items():
        _write_exact(output_dir / filename, fields[table], merged[table])

    output_metadata: dict[str, object] = {}
    for table, filename in RESULT_FILES.items():
        path = output_dir / filename
        output_metadata[filename] = {
            "path": str(path),
            "row_count": len(merged[table]),
            "sha256": _sha256(path),
        }

    report: dict[str, object] = {
        "contract": CONTRACT,
        "status": "PASS",
        "output_dir": str(output_dir),
        "coverage": {
            "reference_scenario_id": reference_scenario_id,
            "reduction_scenario_ids": list(reduction_scenarios),
            "input_sample_ids": list(samples),
            "replication_ids": list(replications),
            "scenario_count": 1 + len(reduction_scenarios),
            "input_sample_count": len(samples),
            "replications_per_cell": len(replications),
            "reference_run_count": len(reference_keys),
            "new_reduction_run_count": len(reduction_keys),
            "analysis_run_count": len(combined_keys),
            "coverage_status": "PASS",
        },
        "sources": {
            "immutable_part1_reference": reference_metadata,
            "part2_reduced_capacity": reduction_metadata,
        },
        "outputs": output_metadata,
        "lineage_status": "PASS",
        "cross_scenario_seed_lineage_status": "PASS",
        "claim_boundary": (
            "Mechanical Part 2 merge of audited Part 1 Reference runs and "
            "registered reduced-capacity runs; no staffing recommendation or "
            "calibrated-site claim."
        ),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "consolidation_manifest.json"
    temporary = manifest_path.with_suffix(manifest_path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(manifest_path)
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--reduction-source-root",
        type=Path,
        default=DEFAULT_REDUCTION_SOURCE_ROOT,
    )
    parser.add_argument(
        "--reference-source-dir",
        type=Path,
        default=DEFAULT_REFERENCE_SOURCE_DIR,
    )
    parser.add_argument(
        "--reference-audit-manifest",
        type=Path,
        default=DEFAULT_REFERENCE_AUDIT_MANIFEST,
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--schema-registry",
        type=Path,
        default=DEFAULT_SCHEMA_REGISTRY,
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        report = consolidate_capacity_availability_results(
            args.reduction_source_root,
            args.reference_source_dir,
            args.output_dir,
            audit_manifest_path=args.reference_audit_manifest,
            schema_registry_path=args.schema_registry,
        )
    except (FileNotFoundError, KeyError, ValueError) as error:
        print(
            json.dumps(
                {
                    "contract": CONTRACT,
                    "status": "FAIL",
                    "errors": [str(error)],
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 1
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
