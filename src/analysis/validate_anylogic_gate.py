"""Validate the AnyLogic 2-input-sample by 3-replication smoke gate.

The gate is intentionally synthetic. It verifies experiment orchestration,
seed lineage, event ordering, and output schemas before the assessment's
unfrozen operational inputs are introduced. When ``--reference-dir`` is
supplied, it also checks byte identity against that same-contract reference.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = PROJECT_ROOT / "config" / "anylogic_gate_manifest.csv"
DEFAULT_RESULTS_DIR = PROJECT_ROOT / "results" / "raw" / "anylogic_gate"
DEFAULT_REPORT = (
    PROJECT_ROOT
    / "results"
    / "intermediate"
    / "anylogic_gate"
    / "gate_validation.json"
)

RUN_KEY = ("scenario_id", "input_sample_id", "replication_id")
COMMON_LINEAGE = (
    "schema_version",
    "scenario_id",
    "input_sample_id",
    "replication_id",
    "stream_seed_ids",
)

RUN_MANIFEST_COLUMNS = (
    "schema_version",
    "config_hash",
    "model_version",
    "scenario_id",
    "input_sample_id",
    "replication_id",
    "stream_seed_ids",
    "start_state",
    "arrival_cutoff",
    "drain_end",
    "engine_version",
)

ENTITY_COLUMNS = (
    *COMMON_LINEAGE,
    "traveller_id",
    "arrival",
    "security_queue_join",
    "security_start",
    "security_end",
    "immigration_queue_join",
    "immigration_lane",
    "immigration_start",
    "immigration_primary_end",
    "additional_check_flag",
    "additional_check_end",
    "technology_flag",
    "exit",
    "security_resource_id",
    "immigration_resource_id",
    "service_demand",
)

SUMMARY_COLUMNS = (
    *COMMON_LINEAGE,
    "arrivals",
    "completed_at_cutoff",
    "wip_at_cutoff",
    "completed_after_drain",
    "security_wait_mean",
    "security_wait_p95",
    "total_wait_mean",
    "total_wait_p95",
    "cutoff_backlog",
    "cohort_clear_time",
)


@dataclass(frozen=True)
class ExpectedRun:
    schema_version: str
    scenario_id: str
    input_sample_id: str
    input_sample_index: int
    replication_id: int
    run_seed: int
    gate_arrival_scale: float
    gate_entity_count: int

    @property
    def key(self) -> tuple[str, str, str]:
        return (
            self.scenario_id,
            self.input_sample_id,
            str(self.replication_id),
        )

    @property
    def stream_seed_ids(self) -> str:
        return f"default_rng:{self.run_seed}"


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    if not path.is_file():
        raise FileNotFoundError(path)
    with path.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames is None:
            raise ValueError(f"{path}: missing header")
        return reader.fieldnames, list(reader)


def require_columns(
    path: Path,
    fieldnames: Sequence[str],
    required: Sequence[str],
    errors: list[str],
) -> None:
    missing = [name for name in required if name not in fieldnames]
    if missing:
        errors.append(f"{path.name}: missing columns {missing}")


def row_key(row: dict[str, str]) -> tuple[str, str, str]:
    return tuple(row.get(name, "") for name in RUN_KEY)  # type: ignore[return-value]


def parse_int(value: str, label: str, errors: list[str]) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        errors.append(f"{label}: expected integer, got {value!r}")
        return None


def parse_float(value: str, label: str, errors: list[str]) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        errors.append(f"{label}: expected finite number, got {value!r}")
        return None
    if not math.isfinite(result):
        errors.append(f"{label}: expected finite number, got {value!r}")
        return None
    return result


def duplicate_header_rows(
    fieldnames: Sequence[str], rows: Iterable[dict[str, str]]
) -> int:
    first = fieldnames[0]
    return sum(row.get(first) == first for row in rows)


def load_expected_runs(path: Path) -> list[ExpectedRun]:
    fieldnames, rows = read_csv(path)
    required = (
        "schema_version",
        "scenario_id",
        "input_sample_id",
        "input_sample_index",
        "replication_id",
        "run_seed",
        "gate_arrival_scale",
        "gate_entity_count",
    )
    missing = [name for name in required if name not in fieldnames]
    if missing:
        raise ValueError(f"{path}: missing columns {missing}")

    expected: list[ExpectedRun] = []
    for line_number, row in enumerate(rows, start=2):
        try:
            expected.append(
                ExpectedRun(
                    schema_version=row["schema_version"],
                    scenario_id=row["scenario_id"],
                    input_sample_id=row["input_sample_id"],
                    input_sample_index=int(row["input_sample_index"]),
                    replication_id=int(row["replication_id"]),
                    run_seed=int(row["run_seed"]),
                    gate_arrival_scale=float(row["gate_arrival_scale"]),
                    gate_entity_count=int(row["gate_entity_count"]),
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"{path}:{line_number}: invalid row: {exc}") from exc
    return expected


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_gate(
    manifest_path: Path,
    results_dir: Path,
    reference_dir: Path | None = None,
) -> dict[str, object]:
    errors: list[str] = []
    expected = load_expected_runs(manifest_path)
    expected_by_key = {run.key: run for run in expected}

    if len(expected) != 6:
        errors.append(f"gate manifest: expected 6 rows, found {len(expected)}")
    if len(expected_by_key) != len(expected):
        errors.append("gate manifest: duplicate composite run keys")
    if sorted(Counter(run.input_sample_id for run in expected).values()) != [3, 3]:
        errors.append("gate manifest: expected two input samples with three runs each")

    paths = {
        "run_manifest": results_dir / "run_manifest.csv",
        "entity_log": results_dir / "entity_log.csv",
        "run_summary": results_dir / "run_summary.csv",
    }
    loaded: dict[str, tuple[list[str], list[dict[str, str]]]] = {}
    schemas = {
        "run_manifest": RUN_MANIFEST_COLUMNS,
        "entity_log": ENTITY_COLUMNS,
        "run_summary": SUMMARY_COLUMNS,
    }
    for name, path in paths.items():
        try:
            fieldnames, rows = read_csv(path)
        except (FileNotFoundError, ValueError) as exc:
            errors.append(str(exc))
            continue
        loaded[name] = (fieldnames, rows)
        require_columns(path, fieldnames, schemas[name], errors)
        repeats = duplicate_header_rows(fieldnames, rows)
        if repeats:
            errors.append(f"{path.name}: contains {repeats} duplicate header row(s)")

    if len(loaded) == 3:
        run_rows = loaded["run_manifest"][1]
        entity_rows = loaded["entity_log"][1]
        summary_rows = loaded["run_summary"][1]

        if len(run_rows) != 6:
            errors.append(f"run_manifest.csv: expected 6 rows, found {len(run_rows)}")
        if len(summary_rows) != 6:
            errors.append(f"run_summary.csv: expected 6 rows, found {len(summary_rows)}")
        expected_entities = sum(run.gate_entity_count for run in expected)
        if len(entity_rows) != expected_entities:
            errors.append(
                f"entity_log.csv: expected {expected_entities} rows, "
                f"found {len(entity_rows)}"
            )

        for filename, rows in (
            ("run_manifest.csv", run_rows),
            ("run_summary.csv", summary_rows),
        ):
            keys = [row_key(row) for row in rows]
            if len(keys) != len(set(keys)):
                errors.append(f"{filename}: duplicate composite run keys")
            extra = sorted(set(keys) - set(expected_by_key))
            missing = sorted(set(expected_by_key) - set(keys))
            if extra:
                errors.append(f"{filename}: unexpected run keys {extra}")
            if missing:
                errors.append(f"{filename}: missing run keys {missing}")
            for row in rows:
                key = row_key(row)
                expected_run = expected_by_key.get(key)
                if expected_run is None:
                    continue
                if row.get("schema_version") != expected_run.schema_version:
                    errors.append(f"{filename} {key}: schema_version mismatch")
                if row.get("stream_seed_ids") != expected_run.stream_seed_ids:
                    errors.append(
                        f"{filename} {key}: expected seed lineage "
                        f"{expected_run.stream_seed_ids!r}, got "
                        f"{row.get('stream_seed_ids')!r}"
                    )

        entity_keys = [
            (*row_key(row), row.get("traveller_id", "")) for row in entity_rows
        ]
        if len(entity_keys) != len(set(entity_keys)):
            errors.append("entity_log.csv: duplicate traveller keys")

        entities_by_run: dict[
            tuple[str, str, str], list[dict[str, str]]
        ] = defaultdict(list)
        fingerprints: dict[tuple[str, str, str], str] = {}
        for row_number, row in enumerate(entity_rows, start=2):
            key = row_key(row)
            expected_run = expected_by_key.get(key)
            if expected_run is None:
                errors.append(f"entity_log.csv:{row_number}: unexpected run key {key}")
                continue
            entities_by_run[key].append(row)
            if row.get("schema_version") != expected_run.schema_version:
                errors.append(
                    f"entity_log.csv:{row_number}: schema_version mismatch"
                )
            if row.get("stream_seed_ids") != expected_run.stream_seed_ids:
                errors.append(
                    f"entity_log.csv:{row_number}: seed lineage mismatch"
                )

            ordered_fields = (
                "arrival",
                "security_queue_join",
                "security_start",
                "security_end",
                "exit",
            )
            values = [
                parse_float(
                    row.get(field, ""),
                    f"entity_log.csv:{row_number}:{field}",
                    errors,
                )
                for field in ordered_fields
            ]
            if all(value is not None for value in values):
                numeric = [value for value in values if value is not None]
                if any(right + 1e-12 < left for left, right in zip(numeric, numeric[1:])):
                    errors.append(
                        f"entity_log.csv:{row_number}: illegal event ordering"
                    )

            demand = parse_float(
                row.get("service_demand", ""),
                f"entity_log.csv:{row_number}:service_demand",
                errors,
            )
            if demand is not None and demand <= 0:
                errors.append(
                    f"entity_log.csv:{row_number}: service_demand must be positive"
                )

        for key, expected_run in expected_by_key.items():
            rows = entities_by_run.get(key, [])
            if len(rows) != expected_run.gate_entity_count:
                errors.append(
                    f"entity_log.csv {key}: expected "
                    f"{expected_run.gate_entity_count} travellers, found {len(rows)}"
                )
            fingerprint_payload = "\n".join(
                ",".join(
                    row.get(field, "")
                    for field in (
                        "traveller_id",
                        "arrival",
                        "security_start",
                        "service_demand",
                        "exit",
                    )
                )
                for row in sorted(rows, key=lambda item: item.get("traveller_id", ""))
            )
            fingerprints[key] = hashlib.sha256(
                fingerprint_payload.encode("utf-8")
            ).hexdigest()

        for input_sample_id in sorted(
            {run.input_sample_id for run in expected}
        ):
            values = {
                fingerprints[run.key]
                for run in expected
                if run.input_sample_id == input_sample_id
                and run.key in fingerprints
            }
            if len(values) != 3:
                errors.append(
                    f"{input_sample_id}: replications do not have three "
                    "distinct stochastic fingerprints"
                )

        summary_by_key = {row_key(row): row for row in summary_rows}
        for key, expected_run in expected_by_key.items():
            row = summary_by_key.get(key)
            if row is None:
                continue
            for field in (
                "arrivals",
                "completed_after_drain",
            ):
                value = parse_int(
                    row.get(field, ""),
                    f"run_summary.csv {key}:{field}",
                    errors,
                )
                if value is not None and value != expected_run.gate_entity_count:
                    errors.append(
                        f"run_summary.csv {key}:{field}: expected "
                        f"{expected_run.gate_entity_count}, found {value}"
                    )

    reproducibility: dict[str, object] = {
        "reference_supplied": reference_dir is not None,
        "byte_identical": None,
        "files": {},
    }
    if reference_dir is not None:
        byte_identical = True
        hashes: dict[str, dict[str, str]] = {}
        for name, path in paths.items():
            reference = reference_dir / path.name
            if not path.is_file() or not reference.is_file():
                errors.append(
                    f"reproducibility: missing {path.name} in current or reference"
                )
                byte_identical = False
                continue
            current_hash = file_sha256(path)
            reference_hash = file_sha256(reference)
            hashes[name] = {
                "current_sha256": current_hash,
                "reference_sha256": reference_hash,
            }
            if current_hash != reference_hash:
                byte_identical = False
                errors.append(
                    f"reproducibility: {path.name} is not byte-identical"
                )
        reproducibility = {
            "reference_supplied": True,
            "byte_identical": byte_identical,
            "files": hashes,
        }

    return {
        "gate": "ANYLOGIC_2_INPUT_X_3_REPLICATION",
        "status": "PASS" if not errors else "FAIL",
        "pairing_status": "NOT_APPLICABLE_SINGLE_SCENARIO",
        "manifest": str(manifest_path),
        "results_dir": str(results_dir),
        "expected_runs": len(expected),
        "expected_entities": sum(run.gate_entity_count for run in expected),
        "reproducibility": reproducibility,
        "errors": errors,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS_DIR)
    parser.add_argument(
        "--reference-dir",
        type=Path,
        help=(
            "Optional same-contract reference directory for byte-identical "
            "comparison."
        ),
    )
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    report = validate_gate(
        manifest_path=args.manifest.resolve(),
        results_dir=args.results_dir.resolve(),
        reference_dir=(
            args.reference_dir.resolve() if args.reference_dir is not None else None
        ),
    )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
