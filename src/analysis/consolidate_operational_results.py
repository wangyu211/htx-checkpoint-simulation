"""Consolidate immutable per-run AnyLogic outputs into analysis-ready tables."""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from typing import Mapping, Sequence

from src.analysis.validate_operational_contract import PROJECT_ROOT
from src.analysis.validate_operational_results import (
    DEFAULT_SCHEMA_REGISTRY,
    RESULT_FILES,
    RUN_KEY,
    load_result_schemas,
    read_csv,
    validate_operational_results,
)


DEFAULT_SOURCE_ROOT = (
    PROJECT_ROOT / "results" / "raw" / "anylogic_operational_batch"
)
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "results" / "raw" / "operational"
REPLICATION_DIRECTORY = re.compile(r"^replication_(\d{3,})$")


def _key(row: Mapping[str, str]) -> tuple[str, str, int]:
    return (
        row["scenario_id"],
        row["input_sample_id"],
        int(row["replication_id"]),
    )


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


def consolidate_operational_results(
    source_root: Path = DEFAULT_SOURCE_ROOT,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    *,
    schema_registry_path: Path = DEFAULT_SCHEMA_REGISTRY,
) -> dict[str, object]:
    """Merge one-row-per-leaf outputs without weakening run lineage."""

    schemas = load_result_schemas(schema_registry_path)
    fields = {
        table: [item["field_name"] for item in schemas[table]]
        for table in RESULT_FILES
    }
    manifests: list[dict[str, str]] = []
    entities: list[dict[str, str]] = []
    kpis: list[dict[str, str]] = []
    seen: set[tuple[str, str, int]] = set()
    leaves = sorted(source_root.rglob(RESULT_FILES["run_manifest"]))
    if not leaves:
        raise FileNotFoundError(
            f"No {RESULT_FILES['run_manifest']} files under {source_root}"
        )

    for manifest_path in leaves:
        leaf = manifest_path.parent
        leaf_manifests = _read_exact(
            manifest_path,
            fields["run_manifest"],
        )
        leaf_entities = _read_exact(
            leaf / RESULT_FILES["entity_log"],
            fields["entity_log"],
        )
        leaf_kpis = _read_exact(
            leaf / RESULT_FILES["replication_kpis"],
            fields["replication_kpis"],
        )
        if len(leaf_manifests) != 1 or len(leaf_kpis) != 1:
            raise ValueError(
                f"{leaf}: expected exactly one manifest row and one KPI row"
            )
        manifest = leaf_manifests[0]
        key = _key(manifest)
        if key in seen:
            raise ValueError(f"{leaf}: duplicate run key {key}")
        seen.add(key)
        if _key(leaf_kpis[0]) != key:
            raise ValueError(f"{leaf}: manifest and KPI run keys differ")
        if any(_key(row) != key for row in leaf_entities):
            raise ValueError(f"{leaf}: entity row has a different run key")

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
        manifests.append(manifest)
        entities.extend(leaf_entities)
        kpis.append(leaf_kpis[0])

    manifests.sort(key=_key)
    kpis.sort(key=_key)
    entities.sort(
        key=lambda row: (
            *_key(row),
            row["traveller_id"],
        )
    )
    _write_exact(
        output_dir / RESULT_FILES["run_manifest"],
        fields["run_manifest"],
        manifests,
    )
    _write_exact(
        output_dir / RESULT_FILES["entity_log"],
        fields["entity_log"],
        entities,
    )
    _write_exact(
        output_dir / RESULT_FILES["replication_kpis"],
        fields["replication_kpis"],
        kpis,
    )
    report = {
        "contract": "TASK3_OPERATIONAL_CONSOLIDATION_V1",
        "status": "PASS",
        "source_root": str(source_root),
        "output_dir": str(output_dir),
        "run_count": len(manifests),
        "entity_count": len(entities),
        "claim_boundary": (
            "Mechanical consolidation only; validation and statistical "
            "analysis remain separate gates."
        ),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "consolidation_manifest.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=DEFAULT_SOURCE_ROOT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--schema-registry",
        type=Path,
        default=DEFAULT_SCHEMA_REGISTRY,
    )
    parser.add_argument(
        "--allow-partial",
        action="store_true",
        help="Allow consolidation of an intentionally incomplete pilot batch.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        report = consolidate_operational_results(
            args.source_root.resolve(),
            args.output_dir.resolve(),
            schema_registry_path=args.schema_registry.resolve(),
        )
        validation = validate_operational_results(
            args.output_dir.resolve(),
            schema_registry_path=args.schema_registry.resolve(),
            require_pilot_coverage=not args.allow_partial,
        )
    except (FileNotFoundError, KeyError, ValueError) as exc:
        print(
            json.dumps(
                {
                    "contract": "TASK3_OPERATIONAL_CONSOLIDATION_V1",
                    "status": "FAIL",
                    "errors": [str(exc)],
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 1
    report["validation_status"] = validation["status"]
    report["validation_errors"] = validation["errors"]
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if validation["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
