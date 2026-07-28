"""Validate Task 3 operational CSV outputs against the frozen result schemas."""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
from collections import defaultdict
from pathlib import Path
from typing import Mapping, Sequence

from src.analysis.validate_operational_contract import (
    DEFAULT_SCENARIOS,
    PROJECT_ROOT,
    SCENARIO_COLUMNS,
    scenario_config_sha256,
)


DEFAULT_SCHEMA_REGISTRY = (
    PROJECT_ROOT / "config" / "result_schema_registry.csv"
)
DEFAULT_RESULTS_DIR = PROJECT_ROOT / "results" / "raw" / "operational"
DEFAULT_REPORT = (
    PROJECT_ROOT
    / "results"
    / "intermediate"
    / "operational_results"
    / "validation.json"
)
RESULT_FILES = {
    "run_manifest": "run_manifest.csv",
    "entity_log": "entity_log.csv",
    "replication_kpis": "replication_kpis.csv",
}
SCHEMA_REGISTRY_COLUMNS = (
    "table_name",
    "ordinal",
    "field_name",
    "data_type",
    "nullable",
    "unit",
    "description",
)
RUN_KEY = ("scenario_id", "input_sample_id", "replication_id")
HEX64 = re.compile(r"^[0-9a-f]{64}$")


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    if not path.is_file():
        raise FileNotFoundError(path)
    with path.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames is None:
            raise ValueError(f"{path}: missing header")
        return list(reader.fieldnames), list(reader)


def load_result_schemas(
    path: Path = DEFAULT_SCHEMA_REGISTRY,
) -> dict[str, list[dict[str, str]]]:
    """Load the ordered, machine-readable CSV output schemas."""

    fieldnames, rows = read_csv(path)
    if tuple(fieldnames) != SCHEMA_REGISTRY_COLUMNS:
        raise ValueError(f"{path}: invalid schema-registry header")
    by_table: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        by_table[row["table_name"]].append(row)
    for table, fields in by_table.items():
        fields.sort(key=lambda row: int(row["ordinal"]))
        ordinals = [int(row["ordinal"]) for row in fields]
        if ordinals != list(range(1, len(fields) + 1)):
            raise ValueError(f"{path}: {table} ordinals are not contiguous")
        names = [row["field_name"] for row in fields]
        if len(names) != len(set(names)):
            raise ValueError(f"{path}: {table} has duplicate fields")
    return dict(by_table)


def _parse_bool(raw: str) -> bool:
    if raw.lower() == "true":
        return True
    if raw.lower() == "false":
        return False
    raise ValueError


def _parse_number(raw: str) -> float:
    value = float(raw)
    if not math.isfinite(value):
        raise ValueError
    return value


def _validate_table(
    path: Path,
    table_name: str,
    fields: Sequence[Mapping[str, str]],
    errors: list[str],
) -> list[dict[str, str]]:
    try:
        actual_fields, rows = read_csv(path)
    except (FileNotFoundError, ValueError) as exc:
        errors.append(str(exc))
        return []
    expected = [field["field_name"] for field in fields]
    if actual_fields != expected:
        errors.append(
            f"{path.name}: schema mismatch; expected {expected}, "
            f"found {actual_fields}"
        )
        return rows

    for line, row in enumerate(rows, start=2):
        for field in fields:
            name = field["field_name"]
            raw = (row.get(name) or "").strip()
            nullable = field["nullable"] == "true"
            if not raw:
                if not nullable:
                    errors.append(
                        f"{path.name}:{line}:{name}: null is not allowed"
                    )
                continue
            data_type = field["data_type"]
            try:
                if data_type == "integer":
                    int(raw)
                elif data_type == "number":
                    _parse_number(raw)
                elif data_type == "boolean":
                    _parse_bool(raw)
                elif data_type != "string":
                    errors.append(
                        f"{path.name}:{line}:{name}: unknown type {data_type}"
                    )
            except ValueError:
                errors.append(
                    f"{path.name}:{line}:{name}: invalid {data_type} {raw!r}"
                )
    return rows


def _key(row: Mapping[str, str]) -> tuple[str, str, str]:
    return tuple((row.get(field) or "").strip() for field in RUN_KEY)  # type: ignore[return-value]


def _nonnegative(
    row: Mapping[str, str], fields: Sequence[str], label: str, errors: list[str]
) -> None:
    for field in fields:
        try:
            value = _parse_number(row[field])
        except (KeyError, ValueError):
            continue
        if value < 0:
            errors.append(f"{label}:{field}: must be non-negative")


def validate_operational_pilot_coverage(
    manifests: Sequence[Mapping[str, str]],
    scenario_rows: Sequence[Mapping[str, str]],
) -> list[str]:
    """Require the exact registered Pilot scenario-by-replication key set."""

    errors: list[str] = []
    if len(scenario_rows) != 15:
        errors.append(
            "OperationalPilot contract requires exactly 15 scenarios; "
            f"found {len(scenario_rows)}"
        )
    expected_keys: set[tuple[str, str, str]] = set()
    scenario_index: dict[str, int] = {}
    for index, scenario in enumerate(scenario_rows):
        scenario_id = (scenario.get("scenario_id") or "").strip()
        input_sample_id = (scenario.get("input_sample_id") or "").strip()
        scenario_index[scenario_id] = index
        try:
            replications = int(
                (scenario.get("pilot_replications") or "").strip()
            )
        except ValueError:
            errors.append(
                f"{scenario_id}: pilot_replications is not an integer"
            )
            continue
        if replications != 10:
            errors.append(
                f"{scenario_id}: OperationalPilot requires exactly "
                f"10 replications; found {replications}"
            )
        expected_keys.update(
            (scenario_id, input_sample_id, str(replication))
            for replication in range(1, replications + 1)
        )

    actual_keys = {_key(row) for row in manifests}
    missing = sorted(expected_keys - actual_keys)
    extra = sorted(actual_keys - expected_keys)
    if missing:
        errors.append(
            "OperationalPilot coverage is missing "
            f"{len(missing)} run keys; first={missing[:10]}"
        )
    if extra:
        errors.append(
            "OperationalPilot coverage has "
            f"{len(extra)} unexpected run keys; first={extra[:10]}"
        )

    scenarios = {
        (row.get("scenario_id") or "").strip(): row
        for row in scenario_rows
    }
    for line, manifest in enumerate(manifests, start=2):
        label = f"run_manifest.csv:{line}"
        scenario_id = (manifest.get("scenario_id") or "").strip()
        scenario = scenarios.get(scenario_id)
        if scenario is None:
            continue
        exact_fields = {
            "schema_version": scenario.get("schema_version", ""),
            "config_id": scenario.get("config_id", ""),
            "scenario_family": scenario.get("scenario_family", ""),
            "reference_scenario_id": scenario.get(
                "reference_scenario_id", ""
            ),
            "input_sample_id": scenario.get("input_sample_id", ""),
            "master_seed": scenario.get("master_seed", ""),
            "arrival_mode": scenario.get("arrival_mode", ""),
            "calibration_status": scenario.get("calibration_status", ""),
            "claim_ceiling": scenario.get("claim_ceiling", ""),
            "crn_alignment_status": scenario.get(
                "crn_alignment_status", ""
            ),
        }
        for field, expected in exact_fields.items():
            if (manifest.get(field) or "").strip() != expected.strip():
                errors.append(
                    f"{label}:{field}: does not match operational scenario"
                )
        if manifest.get("model_version") != "TASK3_OPERATIONAL_POOLED_V1":
            errors.append(
                f"{label}:model_version: expected TASK3_OPERATIONAL_POOLED_V1"
            )
        if manifest.get("start_state") != "EMPTY_AND_IDLE":
            errors.append(
                f"{label}:start_state: expected EMPTY_AND_IDLE"
            )
        try:
            if not math.isclose(
                _parse_number(manifest["arrival_cutoff_seconds"]),
                _parse_number(scenario["arrival_cutoff_seconds"]),
                abs_tol=1e-9,
            ):
                errors.append(
                    f"{label}:arrival_cutoff_seconds: does not match scenario"
                )
        except (KeyError, ValueError):
            pass

        try:
            replication = int(manifest["replication_id"])
            master_seed = int(scenario["master_seed"])
            index = scenario_index[scenario_id]
            stream_base = (
                master_seed
                + 100000 * index
                + 100 * replication
            )
            expected_seeds = {
                "arrival_seed": stream_base + 1,
                "service_seed": stream_base + 2,
                "routing_seed": stream_base + 3,
                "tie_seed": stream_base + 4,
            }
            for field, expected in expected_seeds.items():
                if int(manifest[field]) != expected:
                    errors.append(
                        f"{label}:{field}: expected {expected}"
                    )
        except (KeyError, ValueError):
            pass
    return errors


def validate_operational_results(
    results_dir: Path = DEFAULT_RESULTS_DIR,
    *,
    schema_registry_path: Path = DEFAULT_SCHEMA_REGISTRY,
    scenarios_path: Path = DEFAULT_SCENARIOS,
    require_pilot_coverage: bool = False,
) -> dict[str, object]:
    """Validate schemas, lineage, conservation, and entity event order."""

    errors: list[str] = []
    try:
        schemas = load_result_schemas(schema_registry_path)
    except (FileNotFoundError, ValueError) as exc:
        return {
            "contract": "TASK3_OPERATIONAL_RESULTS_V1",
            "status": "FAIL",
            "errors": [str(exc)],
        }

    rows_by_table: dict[str, list[dict[str, str]]] = {}
    for table, filename in RESULT_FILES.items():
        fields = schemas.get(table)
        if not fields:
            errors.append(f"schema registry is missing table {table}")
            continue
        rows_by_table[table] = _validate_table(
            results_dir / filename, table, fields, errors
        )

    try:
        scenario_fields, scenario_rows = read_csv(scenarios_path)
        if (
            require_pilot_coverage
            and tuple(scenario_fields) != SCENARIO_COLUMNS
        ):
            errors.append(
                "operational_scenarios.csv: header does not match the "
                "canonical scenario contract"
            )
    except (FileNotFoundError, ValueError) as exc:
        errors.append(str(exc))
        scenario_rows = []
    scenarios = {row["scenario_id"]: row for row in scenario_rows}

    manifests = rows_by_table.get("run_manifest", [])
    kpis = rows_by_table.get("replication_kpis", [])
    entities = rows_by_table.get("entity_log", [])

    manifest_by_key = {_key(row): row for row in manifests}
    kpi_by_key = {_key(row): row for row in kpis}
    if len(manifest_by_key) != len(manifests):
        errors.append("run_manifest.csv: duplicate run key")
    if len(kpi_by_key) != len(kpis):
        errors.append("replication_kpis.csv: duplicate run key")
    if set(manifest_by_key) != set(kpi_by_key):
        errors.append("manifest and KPI run-key sets do not match")
    if require_pilot_coverage:
        errors.extend(
            validate_operational_pilot_coverage(
                manifests,
                scenario_rows,
            )
        )

    entity_ids: set[tuple[str, str, str, str]] = set()
    entity_count_by_key: dict[tuple[str, str, str], int] = defaultdict(int)
    for line, row in enumerate(entities, start=2):
        key = _key(row)
        entity_key = (*key, row.get("traveller_id", ""))
        if entity_key in entity_ids:
            errors.append(f"entity_log.csv:{line}: duplicate traveller key")
        entity_ids.add(entity_key)
        entity_count_by_key[key] += 1
        manifest = manifest_by_key.get(key)
        if manifest is None:
            errors.append(f"entity_log.csv:{line}: unknown run key {key}")
        else:
            for field in (
                "schema_version",
                "config_id",
                "config_sha256",
                "model_version",
            ):
                if row.get(field) != manifest.get(field):
                    errors.append(
                        f"entity_log.csv:{line}:{field}: does not match "
                        "run_manifest.csv"
                    )

        _nonnegative(
            row,
            (
                "arrival_seconds",
                "security_service_demand_seconds",
                "immigration_conventional_service_demand_seconds",
                "security_queue_join_seconds",
                "security_start_seconds",
                "security_end_seconds",
                "immigration_queue_join_seconds",
                "immigration_start_seconds",
                "immigration_primary_service_demand_seconds",
                "immigration_primary_end_seconds",
                "exit_seconds",
            ),
            f"entity_log.csv:{line}",
            errors,
        )
        try:
            times = [
                _parse_number(row[field])
                for field in (
                    "arrival_seconds",
                    "security_queue_join_seconds",
                    "security_start_seconds",
                    "security_end_seconds",
                    "immigration_queue_join_seconds",
                    "immigration_start_seconds",
                    "immigration_primary_end_seconds",
                    "exit_seconds",
                )
            ]
            if any(later < earlier for earlier, later in zip(times, times[1:])):
                errors.append(
                    f"entity_log.csv:{line}: illegal event timestamp order"
                )
            if manifest is not None and times[0] >= _parse_number(
                manifest["arrival_cutoff_seconds"]
            ):
                errors.append(
                    f"entity_log.csv:{line}: arrival is outside [0, cutoff)"
                )
        except (KeyError, ValueError):
            pass

        for field in ("automation_u", "additional_check_u", "lane_tie_u"):
            try:
                value = _parse_number(row[field])
            except (KeyError, ValueError):
                continue
            if not 0 <= value <= 1:
                errors.append(
                    f"entity_log.csv:{line}:{field}: must be in [0,1]"
                )

        try:
            additional = _parse_bool(row["additional_check_flag"])
        except (KeyError, ValueError):
            additional = False
        demand = (row.get("additional_check_service_demand_seconds") or "").strip()
        end = (row.get("additional_check_end_seconds") or "").strip()
        if additional:
            if not demand or not end:
                errors.append(
                    f"entity_log.csv:{line}: selected additional check needs "
                    "demand and end time"
                )
            else:
                try:
                    primary_end = _parse_number(
                        row["immigration_primary_end_seconds"]
                    )
                    additional_end = _parse_number(end)
                    exit_time = _parse_number(row["exit_seconds"])
                    if additional_end < primary_end or not math.isclose(
                        additional_end, exit_time, abs_tol=1e-9
                    ):
                        errors.append(
                            f"entity_log.csv:{line}: invalid additional-check "
                            "timing"
                        )
                except (KeyError, ValueError):
                    pass
        elif demand or end:
            errors.append(
                f"entity_log.csv:{line}: unselected additional check must "
                "leave nullable fields blank"
            )

    for line, row in enumerate(manifests, start=2):
        scenario = scenarios.get(row.get("scenario_id", ""))
        if scenario is None:
            errors.append(
                f"run_manifest.csv:{line}: unknown scenario_id "
                f"{row.get('scenario_id')!r}"
            )
        elif row.get("config_id") != scenario.get("config_id"):
            errors.append(
                f"run_manifest.csv:{line}: config_id does not match scenario"
            )
        supplied_hash = row.get("config_sha256", "")
        if not HEX64.fullmatch(supplied_hash):
            errors.append(
                f"run_manifest.csv:{line}: config_sha256 must be 64 lowercase "
                "hex characters"
            )
        elif scenario is not None:
            expected_hash = scenario_config_sha256(scenario)
            if supplied_hash != expected_hash:
                errors.append(
                    f"run_manifest.csv:{line}: config_sha256 does not match "
                    "the canonical scenario row"
                )
        for field, expected in (
            ("calibration_status", "NOT_CALIBRATED"),
            ("claim_ceiling", "COMPARATIVE_WHAT_IF_ONLY"),
            ("drain_rule", "FULL_DRAIN"),
            ("run_status", "COMPLETE"),
        ):
            if row.get(field) != expected:
                errors.append(
                    f"run_manifest.csv:{line}:{field}: expected {expected!r}"
                )
        try:
            if _parse_number(row["drain_end_seconds"]) < _parse_number(
                row["arrival_cutoff_seconds"]
            ):
                errors.append(
                    f"run_manifest.csv:{line}: drain ends before cutoff"
                )
        except (KeyError, ValueError):
            pass

    count_fields = (
        "arrivals",
        "completed_at_cutoff",
        "security_queue_at_cutoff",
        "security_in_service_at_cutoff",
        "immigration_queue_at_cutoff",
        "immigration_in_service_at_cutoff",
        "wip_at_cutoff",
        "completed_after_drain",
        "rejected_or_dropped_count",
        "technology_count",
        "additional_check_count",
        "cutoff_backlog",
    )
    metric_fields = (
        "security_wait_mean_seconds",
        "security_wait_p95_seconds",
        "immigration_wait_mean_seconds",
        "immigration_wait_p95_seconds",
        "total_queue_wait_mean_seconds",
        "total_queue_wait_p95_seconds",
        "system_time_mean_seconds",
        "system_time_p95_seconds",
        "cohort_clear_time_after_cutoff_seconds",
    )
    rate_fields = (
        "total_queue_wait_exceed_600_rate",
        "total_queue_wait_exceed_900_rate",
        "total_queue_wait_exceed_1200_rate",
        "security_utilization",
        "immigration_utilization",
        "cutoff_backlog_fraction",
    )
    for line, row in enumerate(kpis, start=2):
        label = f"replication_kpis.csv:{line}"
        manifest = manifest_by_key.get(_key(row))
        if manifest is not None:
            for field in (
                "schema_version",
                "config_id",
                "config_sha256",
                "model_version",
                "arrival_cutoff_seconds",
                "drain_end_seconds",
                "run_status",
            ):
                if row.get(field) != manifest.get(field):
                    errors.append(
                        f"{label}:{field}: does not match run_manifest.csv"
                    )
        _nonnegative(row, (*count_fields, *metric_fields), label, errors)
        for field in rate_fields:
            try:
                value = _parse_number(row[field])
            except (KeyError, ValueError):
                continue
            if not 0 <= value <= 1:
                errors.append(f"{label}:{field}: must be in [0,1]")

        try:
            counts = {field: int(row[field]) for field in count_fields}
            wip_components = (
                counts["security_queue_at_cutoff"]
                + counts["security_in_service_at_cutoff"]
                + counts["immigration_queue_at_cutoff"]
                + counts["immigration_in_service_at_cutoff"]
            )
            if counts["wip_at_cutoff"] != wip_components:
                errors.append(f"{label}: cutoff WIP components do not sum")
            if counts["arrivals"] != (
                counts["completed_at_cutoff"] + counts["wip_at_cutoff"]
            ):
                errors.append(f"{label}: cutoff conservation fails")
            if counts["cutoff_backlog"] != counts["wip_at_cutoff"]:
                errors.append(f"{label}: cutoff backlog differs from WIP")
            if counts["rejected_or_dropped_count"] != 0:
                errors.append(f"{label}: dropped travellers are prohibited")
            if counts["completed_after_drain"] != counts["arrivals"]:
                errors.append(f"{label}: full-drain conservation fails")
            if entity_count_by_key[_key(row)] != counts["arrivals"]:
                errors.append(f"{label}: entity count differs from arrivals")
            expected_fraction = (
                counts["cutoff_backlog"] / counts["arrivals"]
                if counts["arrivals"]
                else 0.0
            )
            if not math.isclose(
                _parse_number(row["cutoff_backlog_fraction"]),
                expected_fraction,
                abs_tol=1e-9,
            ):
                errors.append(f"{label}: cutoff backlog fraction is wrong")
        except (KeyError, ValueError):
            pass
        if row.get("conservation_pass", "").lower() != "true":
            errors.append(f"{label}: conservation_pass must be true")
        if row.get("run_status") != "COMPLETE":
            errors.append(f"{label}: run_status must be COMPLETE")

    return {
        "contract": "TASK3_OPERATIONAL_RESULTS_V1",
        "status": "PASS" if not errors else "FAIL",
        "results_dir": str(results_dir),
        "run_count": len(manifests),
        "pilot_coverage_required": require_pilot_coverage,
        "expected_pilot_run_count": (
            sum(
                int(row.get("pilot_replications", "0"))
                for row in scenario_rows
                if (row.get("pilot_replications") or "").isdigit()
            )
            if require_pilot_coverage
            else None
        ),
        "entity_count": len(entities),
        "claim_boundary": (
            "Schema and software-invariant validation only; not operational "
            "validation or calibration."
        ),
        "errors": errors,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS_DIR)
    parser.add_argument(
        "--schema-registry", type=Path, default=DEFAULT_SCHEMA_REGISTRY
    )
    parser.add_argument("--scenarios", type=Path, default=DEFAULT_SCENARIOS)
    parser.add_argument(
        "--require-pilot-coverage",
        action="store_true",
        help="Require the exact registered scenario x replication key set.",
    )
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    report = validate_operational_results(
        args.results_dir.resolve(),
        schema_registry_path=args.schema_registry.resolve(),
        scenarios_path=args.scenarios.resolve(),
        require_pilot_coverage=args.require_pilot_coverage,
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
