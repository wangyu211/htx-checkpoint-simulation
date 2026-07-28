"""Validate the literature-informed Task 3 operational scenario contract.

The contract is intentionally named an assumption sandbox.  Passing this
validator means that scenario inputs are complete, internally consistent, and
traceable.  It does *not* mean that the inputs are calibrated to an HTX site or
that the resulting model has operational validity.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
from typing import Mapping, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SCENARIOS = PROJECT_ROOT / "config" / "operational_scenarios.csv"
DEFAULT_PROVENANCE = PROJECT_ROOT / "config" / "provenance_registry.csv"
DEFAULT_SCENARIO_PROVENANCE = (
    PROJECT_ROOT / "config" / "scenario_provenance.csv"
)
DEFAULT_REPORT = (
    PROJECT_ROOT
    / "results"
    / "intermediate"
    / "operational_contract"
    / "validation.json"
)

REFERENCE_SCENARIO_ID = "REFERENCE_ASSUMPTION_SANDBOX_V1"
CONTRACT = "TASK3_OPERATIONAL_ASSUMPTION_SANDBOX_V1"

SCENARIO_COLUMNS = (
    "schema_version",
    "config_id",
    "scenario_id",
    "scenario_family",
    "description",
    "reference_scenario_id",
    "arrival_mode",
    "arrival_rate_per_second",
    "demand_multiplier",
    "arrival_cutoff_seconds",
    "arrival_guard",
    "drain_rule",
    "security_capacity",
    "security_queue_capacity",
    "security_service_distribution",
    "security_service_p1_seconds",
    "immigration_capacity",
    "immigration_queue_capacity",
    "immigration_service_distribution",
    "immigration_service_p1_seconds",
    "queue_policy",
    "automation_mapping_mode",
    "automation_uptake",
    "automation_multiplier",
    "additional_check_semantics",
    "additional_check_probability_conventional",
    "additional_check_probability_technology",
    "additional_check_service_distribution",
    "additional_check_service_p1_seconds",
    "input_sample_id",
    "pilot_replications",
    "master_seed",
    "crn_alignment_status",
    "input_status",
    "calibration_status",
    "claim_ceiling",
    "notes",
)

PROVENANCE_COLUMNS = (
    "provenance_id",
    "evidence_class",
    "title",
    "organisation_or_authors",
    "publication_date",
    "url",
    "geography",
    "process_boundary",
    "reported_value",
    "reported_unit",
    "permitted_model_use",
    "claim_ceiling",
)

SCENARIO_PROVENANCE_COLUMNS = (
    "scenario_id",
    "parameter_name",
    "parameter_value",
    "unit",
    "provenance_id",
    "mapping_role",
    "notes",
)

EVIDENCE_CLASSES = {
    "MEASURED_LOCAL",
    "OFFICIAL_SG_SCENARIO",
    "EXTERNAL_EMPIRICAL_BENCHMARK",
    "STRUCTURAL_LITERATURE",
    "TRANSPARENT_ASSUMPTION",
    "ILLUSTRATIVE_SCENARIO",
}
MAPPING_ROLES = {
    "DIRECT",
    "DERIVED",
    "TRANSPARENT_ASSUMPTION",
    "STRUCTURAL",
    "CONTEXT_SCENARIO",
    "ILLUSTRATIVE_SCENARIO",
    "EXTERNAL_BOUNDARY",
}
SCENARIO_FAMILIES = {
    "REFERENCE",
    "CAPACITY",
    "DEMAND",
    "SERVICE_CONTEXT",
    "AUTOMATION",
    "RISK",
}

# Only these fields may differ from the reference within each controlled
# comparison family.  This prevents feature bundles from being mislabeled as
# one-factor scenarios.
FAMILY_ALLOWED_DELTAS = {
    "CAPACITY": {"security_capacity", "immigration_capacity"},
    "DEMAND": {"demand_multiplier"},
    "SERVICE_CONTEXT": {"immigration_service_p1_seconds"},
    "AUTOMATION": {
        "automation_mapping_mode",
        "automation_uptake",
        "automation_multiplier",
    },
    "RISK": {
        "additional_check_semantics",
        "additional_check_probability_conventional",
        "additional_check_probability_technology",
        "additional_check_service_distribution",
        "additional_check_service_p1_seconds",
    },
}

DECISION_FIELDS = {
    "arrival_mode",
    "arrival_rate_per_second",
    "demand_multiplier",
    "arrival_cutoff_seconds",
    "arrival_guard",
    "drain_rule",
    "security_capacity",
    "security_queue_capacity",
    "security_service_distribution",
    "security_service_p1_seconds",
    "immigration_capacity",
    "immigration_queue_capacity",
    "immigration_service_distribution",
    "immigration_service_p1_seconds",
    "queue_policy",
    "automation_mapping_mode",
    "automation_uptake",
    "automation_multiplier",
    "additional_check_semantics",
    "additional_check_probability_conventional",
    "additional_check_probability_technology",
    "additional_check_service_distribution",
    "additional_check_service_p1_seconds",
}

REFERENCE_PROVENANCE_FIELDS = {
    "arrival_mode",
    "arrival_rate_per_second",
    "demand_multiplier",
    "arrival_cutoff_seconds",
    "drain_rule",
    "security_capacity",
    "security_queue_capacity",
    "security_service_distribution",
    "security_service_p1_seconds",
    "immigration_capacity",
    "immigration_queue_capacity",
    "immigration_service_distribution",
    "immigration_service_p1_seconds",
    "queue_policy",
    "automation_mapping_mode",
    "automation_uptake",
    "automation_multiplier",
    "additional_check_semantics",
    "additional_check_probability_conventional",
    "additional_check_probability_technology",
    "pilot_replications",
    "master_seed",
}

NAMED_SERVICE_CONTEXTS = {
    "REFERENCE_ASSUMPTION_SANDBOX_V1": 13.0,
    "SERVICE_SG_BUS_QR_10S": 10.0,
    "SERVICE_SG_TRAIN_KIOSK_24S": 24.0,
    "SERVICE_SG_TRAIN_MANUAL_45S": 45.0,
}
NAMED_AUTOMATION_MULTIPLIERS = {
    "AUTO_HTX_TRIAL_U50_M60": 0.6,
    "AUTO_HTX_TRIAL_U100_M60": 0.6,
    "AUTO_ICA_ROLLOUT_U50_M40": 0.4,
    "AUTO_ICA_ROLLOUT_U100_M40": 0.4,
}


def _read_exact_csv(
    path: Path, expected: Sequence[str], errors: list[str]
) -> list[dict[str, str]]:
    if not path.is_file():
        errors.append(f"missing file: {path}")
        return []
    with path.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        actual = tuple(reader.fieldnames or ())
        if actual != tuple(expected):
            errors.append(
                f"{path.name}: schema mismatch; expected {list(expected)}, "
                f"found {list(actual)}"
            )
        return list(reader)


def _text(row: Mapping[str, str], field: str) -> str:
    return (row.get(field) or "").strip()


def canonical_scenario_bytes(row: Mapping[str, str]) -> bytes:
    """Canonical bytes used for the operational ``config_sha256`` lineage."""

    payload = {field: _text(row, field) for field in SCENARIO_COLUMNS}
    return (
        json.dumps(
            payload,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def scenario_config_sha256(row: Mapping[str, str]) -> str:
    """Hash one exact scenario row without depending on CSV quoting."""

    return hashlib.sha256(canonical_scenario_bytes(row)).hexdigest()


def _number(
    row: Mapping[str, str],
    field: str,
    errors: list[str],
    *,
    positive: bool = False,
    nonnegative: bool = False,
) -> float | None:
    raw = _text(row, field)
    try:
        value = float(raw)
    except ValueError:
        errors.append(f"{field} must be a finite number; got {raw!r}")
        return None
    if not math.isfinite(value):
        errors.append(f"{field} must be a finite number; got {raw!r}")
        return None
    if positive and value <= 0:
        errors.append(f"{field} must be positive; got {raw!r}")
    if nonnegative and value < 0:
        errors.append(f"{field} must be non-negative; got {raw!r}")
    return value


def _integer(
    row: Mapping[str, str],
    field: str,
    errors: list[str],
    *,
    positive: bool = False,
) -> int | None:
    raw = _text(row, field)
    try:
        value = int(raw)
    except ValueError:
        errors.append(f"{field} must be an integer; got {raw!r}")
        return None
    if positive and value <= 0:
        errors.append(f"{field} must be positive; got {raw!r}")
    return value


def _probability(
    row: Mapping[str, str], field: str, errors: list[str]
) -> float | None:
    value = _number(row, field, errors)
    if value is not None and not 0 <= value <= 1:
        errors.append(f"{field} must be between 0 and 1; got {value}")
    return value


def _row_errors(row: Mapping[str, str]) -> list[str]:
    errors: list[str] = []
    scenario_id = _text(row, "scenario_id")

    if _text(row, "schema_version") != "1.0":
        errors.append("schema_version must be '1.0'")
    if not _text(row, "config_id").startswith("OP_"):
        errors.append("config_id must start with 'OP_'")
    if not scenario_id:
        errors.append("scenario_id is required")
    if _text(row, "scenario_family") not in SCENARIO_FAMILIES:
        errors.append(
            f"scenario_family must be one of {sorted(SCENARIO_FAMILIES)}"
        )
    if _text(row, "reference_scenario_id") != REFERENCE_SCENARIO_ID:
        errors.append(
            f"reference_scenario_id must be {REFERENCE_SCENARIO_ID!r}"
        )
    if _text(row, "arrival_mode") != "HPP":
        errors.append("arrival_mode must be HPP in operational contract v1")

    rate = _number(row, "arrival_rate_per_second", errors, positive=True)
    multiplier = _number(row, "demand_multiplier", errors, positive=True)
    cutoff = _number(row, "arrival_cutoff_seconds", errors, positive=True)
    guard = _integer(row, "arrival_guard", errors, positive=True)
    if (
        rate is not None
        and multiplier is not None
        and cutoff is not None
        and guard is not None
        and rate * multiplier * cutoff >= guard
    ):
        errors.append(
            "arrival_guard must exceed the expected arrivals over the cutoff"
        )
    if _text(row, "drain_rule") != "FULL_DRAIN":
        errors.append("drain_rule must be FULL_DRAIN")

    for field in (
        "security_capacity",
        "security_queue_capacity",
        "immigration_capacity",
        "immigration_queue_capacity",
        "pilot_replications",
        "master_seed",
    ):
        _integer(row, field, errors, positive=True)
    for stage in ("security", "immigration"):
        if _text(row, f"{stage}_service_distribution") != "FIXED":
            errors.append(
                f"{stage}_service_distribution must be FIXED in v1"
            )
        _number(row, f"{stage}_service_p1_seconds", errors, positive=True)

    if _text(row, "queue_policy") != "pooled":
        errors.append(
            "queue_policy must be pooled in executable v1; a separate lane "
            "bank is an unimplemented v2 extension"
        )

    automation_mode = _text(row, "automation_mapping_mode")
    uptake = _probability(row, "automation_uptake", errors)
    automation_multiplier = _number(
        row, "automation_multiplier", errors, positive=True
    )
    if automation_mode == "DISABLED":
        if uptake != 0 or automation_multiplier != 1:
            errors.append(
                "DISABLED automation requires uptake=0 and multiplier=1"
            )
    elif automation_mode == "MULTIPLIER":
        if uptake is not None and uptake <= 0:
            errors.append("MULTIPLIER automation requires positive uptake")
        if (
            automation_multiplier is not None
            and not 0 < automation_multiplier < 1
        ):
            errors.append(
                "MULTIPLIER automation requires a multiplier between 0 and 1"
            )
    else:
        errors.append(
            "automation_mapping_mode must be DISABLED or MULTIPLIER"
        )

    check_semantics = _text(row, "additional_check_semantics")
    check_p_conventional = _probability(
        row, "additional_check_probability_conventional", errors
    )
    check_p_technology = _probability(
        row, "additional_check_probability_technology", errors
    )
    check_distribution = _text(
        row, "additional_check_service_distribution"
    )
    check_seconds = _text(row, "additional_check_service_p1_seconds")
    if check_semantics == "NONE":
        if check_p_conventional != 0 or check_p_technology != 0:
            errors.append("NONE additional-check semantics requires zero rates")
        if check_distribution != "UNSET" or check_seconds:
            errors.append(
                "NONE additional-check semantics requires UNSET and blank "
                "service demand"
            )
    elif check_semantics == "COUNTER_HELD_RISK_REFERRAL_PROXY":
        if check_p_conventional == 0 and check_p_technology == 0:
            errors.append("risk proxy requires a positive branch probability")
        if check_distribution != "FIXED":
            errors.append("risk proxy requires FIXED service in v1")
        _number(
            row,
            "additional_check_service_p1_seconds",
            errors,
            positive=True,
        )
    else:
        errors.append(
            "additional_check_semantics must be NONE or "
            "COUNTER_HELD_RISK_REFERRAL_PROXY"
        )

    for field, expected in (
        ("crn_alignment_status", "NOT_TESTED"),
        ("input_status", "READY_ASSUMPTION_SANDBOX"),
        ("calibration_status", "NOT_CALIBRATED"),
        ("claim_ceiling", "COMPARATIVE_WHAT_IF_ONLY"),
    ):
        if _text(row, field) != expected:
            errors.append(f"{field} must be {expected!r}")

    narrative = " ".join(
        _text(row, field) for field in ("description", "notes")
    ).lower()
    if "calibrated baseline" in narrative or "calibrated htx" in narrative:
        errors.append("scenario narrative exceeds the non-calibration boundary")

    if scenario_id in NAMED_SERVICE_CONTEXTS:
        actual = _number(
            row, "immigration_service_p1_seconds", errors, positive=True
        )
        expected = NAMED_SERVICE_CONTEXTS[scenario_id]
        if actual is not None and not math.isclose(actual, expected):
            errors.append(
                f"{scenario_id} must preserve its named {expected:g}-second "
                "context"
            )
    if scenario_id in NAMED_AUTOMATION_MULTIPLIERS:
        actual = _number(row, "automation_multiplier", errors, positive=True)
        expected = NAMED_AUTOMATION_MULTIPLIERS[scenario_id]
        if actual is not None and not math.isclose(actual, expected):
            errors.append(
                f"{scenario_id} must preserve multiplier {expected:g}"
            )

    return errors


def validate_operational_contract(
    scenarios_path: Path = DEFAULT_SCENARIOS,
    provenance_path: Path = DEFAULT_PROVENANCE,
    scenario_provenance_path: Path = DEFAULT_SCENARIO_PROVENANCE,
) -> dict[str, object]:
    """Validate schemas, controlled contrasts, and per-parameter provenance."""

    errors: list[str] = []
    scenarios = _read_exact_csv(
        scenarios_path, SCENARIO_COLUMNS, errors
    )
    provenance = _read_exact_csv(
        provenance_path, PROVENANCE_COLUMNS, errors
    )
    mappings = _read_exact_csv(
        scenario_provenance_path, SCENARIO_PROVENANCE_COLUMNS, errors
    )

    scenario_by_id = {
        _text(row, "scenario_id"): row for row in scenarios
    }
    config_ids = [_text(row, "config_id") for row in scenarios]
    scenario_ids = [_text(row, "scenario_id") for row in scenarios]
    if len(config_ids) != len(set(config_ids)):
        errors.append("operational_scenarios.csv: duplicate config_id")
    if len(scenario_ids) != len(set(scenario_ids)):
        errors.append("operational_scenarios.csv: duplicate scenario_id")
    if REFERENCE_SCENARIO_ID not in scenario_by_id:
        errors.append(f"missing reference scenario {REFERENCE_SCENARIO_ID}")

    row_reports: list[dict[str, object]] = []
    for line, row in enumerate(scenarios, start=2):
        row_errors = _row_errors(row)
        row_reports.append(
            {
                "scenario_id": _text(row, "scenario_id"),
                "config_sha256": scenario_config_sha256(row),
                "status": "PASS" if not row_errors else "FAIL",
                "errors": row_errors,
            }
        )
        errors.extend(
            f"operational_scenarios.csv:{line} "
            f"({_text(row, 'scenario_id')}): {message}"
            for message in row_errors
        )

    reference = scenario_by_id.get(REFERENCE_SCENARIO_ID)
    if reference is not None:
        if _text(reference, "scenario_family") != "REFERENCE":
            errors.append("reference scenario_family must be REFERENCE")
        rate = _number(
            reference, "arrival_rate_per_second", errors, positive=True
        )
        security_seconds = _number(
            reference, "security_service_p1_seconds", errors, positive=True
        )
        immigration_seconds = _number(
            reference,
            "immigration_service_p1_seconds",
            errors,
            positive=True,
        )
        if (
            rate is not None
            and security_seconds is not None
            and immigration_seconds is not None
        ):
            expected_security = math.ceil(rate * security_seconds / 0.85)
            expected_immigration = math.ceil(
                rate * immigration_seconds / 0.85
            )
            if int(reference["security_capacity"]) != expected_security:
                errors.append(
                    "reference security_capacity does not match the declared "
                    "85-percent offered-load rule"
                )
            if int(reference["immigration_capacity"]) != expected_immigration:
                errors.append(
                    "reference immigration_capacity does not match the "
                    "declared 85-percent offered-load rule"
                )

        for row in scenarios:
            scenario_id = _text(row, "scenario_id")
            family = _text(row, "scenario_family")
            if scenario_id == REFERENCE_SCENARIO_ID:
                continue
            changed = {
                field
                for field in DECISION_FIELDS
                if _text(row, field) != _text(reference, field)
            }
            allowed = FAMILY_ALLOWED_DELTAS.get(family, set())
            unexpected = sorted(changed - allowed)
            if unexpected:
                errors.append(
                    f"{scenario_id}: {family} scenario changes fields outside "
                    f"its controlled contrast: {unexpected}"
                )
            if not changed:
                errors.append(
                    f"{scenario_id}: scenario does not differ from reference"
                )

    provenance_ids = [_text(row, "provenance_id") for row in provenance]
    provenance_by_id = {
        _text(row, "provenance_id"): row for row in provenance
    }
    if len(provenance_ids) != len(set(provenance_ids)):
        errors.append("provenance_registry.csv: duplicate provenance_id")
    for line, row in enumerate(provenance, start=2):
        evidence_class = _text(row, "evidence_class")
        if evidence_class not in EVIDENCE_CLASSES:
            errors.append(
                f"provenance_registry.csv:{line}: invalid evidence_class "
                f"{evidence_class!r}"
            )
        if evidence_class in {
            "OFFICIAL_SG_SCENARIO",
            "EXTERNAL_EMPIRICAL_BENCHMARK",
            "STRUCTURAL_LITERATURE",
        } and not _text(row, "url"):
            errors.append(
                f"provenance_registry.csv:{line}: published source needs URL"
            )
        if "calibrat" in evidence_class.lower():
            errors.append(
                f"provenance_registry.csv:{line}: calibration evidence class "
                "is prohibited"
            )

    mapping_keys: set[tuple[str, str]] = set()
    mapped_fields: dict[str, set[str]] = {}
    for line, mapping in enumerate(mappings, start=2):
        scenario_id = _text(mapping, "scenario_id")
        parameter = _text(mapping, "parameter_name")
        key = (scenario_id, parameter)
        if key in mapping_keys:
            errors.append(
                f"scenario_provenance.csv:{line}: duplicate mapping {key}"
            )
        mapping_keys.add(key)
        mapped_fields.setdefault(scenario_id, set()).add(parameter)

        scenario = scenario_by_id.get(scenario_id)
        if scenario is None:
            errors.append(
                f"scenario_provenance.csv:{line}: unknown scenario_id "
                f"{scenario_id!r}"
            )
        elif parameter not in SCENARIO_COLUMNS:
            errors.append(
                f"scenario_provenance.csv:{line}: unknown parameter "
                f"{parameter!r}"
            )
        elif _text(mapping, "parameter_value") != _text(scenario, parameter):
            errors.append(
                f"scenario_provenance.csv:{line}: value does not match "
                f"{scenario_id}.{parameter}"
            )

        provenance_id = _text(mapping, "provenance_id")
        if provenance_id not in provenance_by_id:
            errors.append(
                f"scenario_provenance.csv:{line}: unknown provenance_id "
                f"{provenance_id!r}"
            )
        if _text(mapping, "mapping_role") not in MAPPING_ROLES:
            errors.append(
                f"scenario_provenance.csv:{line}: invalid mapping_role"
            )

    reference_mapped = mapped_fields.get(REFERENCE_SCENARIO_ID, set())
    missing_reference = sorted(
        REFERENCE_PROVENANCE_FIELDS - reference_mapped
    )
    if missing_reference:
        errors.append(
            "reference scenario is missing provenance for "
            f"{missing_reference}"
        )

    if reference is not None:
        for row in scenarios:
            scenario_id = _text(row, "scenario_id")
            if scenario_id == REFERENCE_SCENARIO_ID:
                continue
            changed = {
                field
                for field in DECISION_FIELDS
                if _text(row, field) != _text(reference, field)
            }
            unmapped = sorted(changed - mapped_fields.get(scenario_id, set()))
            if unmapped:
                errors.append(
                    f"{scenario_id}: changed fields lack direct provenance "
                    f"mappings: {unmapped}"
                )

    return {
        "contract": CONTRACT,
        "status": "PASS" if not errors else "FAIL",
        "reference_scenario_id": REFERENCE_SCENARIO_ID,
        "scenario_count": len(scenarios),
        "provenance_source_count": len(provenance),
        "scenario_parameter_mapping_count": len(mappings),
        "rows": row_reports,
        "claim_boundary": (
            "Executable, traceable assumption scenarios; not calibrated HTX "
            "inputs or an operational forecast."
        ),
        "errors": errors,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenarios", type=Path, default=DEFAULT_SCENARIOS)
    parser.add_argument("--provenance", type=Path, default=DEFAULT_PROVENANCE)
    parser.add_argument(
        "--scenario-provenance",
        type=Path,
        default=DEFAULT_SCENARIO_PROVENANCE,
    )
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    report = validate_operational_contract(
        args.scenarios.resolve(),
        args.provenance.resolve(),
        args.scenario_provenance.resolve(),
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
