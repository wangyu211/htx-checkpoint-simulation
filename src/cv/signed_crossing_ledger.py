"""Fail-closed tooling for the Task 1 human-signed crossing ledger.

The registered review protocol is the authority for fields, decision values,
reason codes, geometry, and source identity.  This module never detects,
reconciles, accepts, or rejects a crossing.  It only validates already-human-
reviewed artifacts, writes a detached hash sign-off, and exports accepted
arrival events without shifting their source presentation timestamps.

The detached hashes provide artifact integrity.  They are not a cryptographic
identity signature.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import re
from datetime import datetime
from pathlib import Path
from typing import Mapping, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROTOCOL = PROJECT_ROOT / "config" / "task1_event_review_protocol.json"

LEDGER_SCHEMA_VERSION = "TASK1_SIGNED_CROSSING_LEDGER_V1"
SIGNOFF_SCHEMA_VERSION = "TASK1_CROSSING_SIGNOFF_V1"
TRACE_SCHEMA_VERSION = "TASK1_OBSERVED_ARRIVAL_TRACE_V1"

TRACE_FIELDS = (
    "schema_version",
    "ledger_version",
    "arrival_index",
    "source_event_id",
    "time_resolution",
    "arrival_seconds",
    "time_lower_seconds",
    "time_upper_seconds",
)
TRACE_MANIFEST_FIELDS = {
    "schema_version",
    "artifact_type",
    "source_ledger_sha256",
    "source_signoff_sha256",
    "ledger_version",
    "arrival_direction",
    "event_count",
    "interval_censored_event_count",
    "source_duration_seconds",
    "clock_basis",
    "trace_sha256",
    "claim_ceiling",
    "stationarity_claim",
    "privacy_classification",
}

SIGNOFF_REQUEST_FIELDS = {
    "schema_version",
    "ledger_version",
    "reviewer_id",
    "signed_at_utc",
    "attestation",
}

STATIONARITY_CLAIM = "NOT_ESTABLISHED_FROM_SHORT_CLIP"
PRIVACY_CLASSIFICATION = "NON_PIXEL_NON_PII_ROLE_ALIASES_ONLY"
SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
REVIEWER_ALIAS = re.compile(r"^[A-Z][A-Z0-9_]{2,63}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
UTC_TIMESTAMP = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T"
    r"[0-9]{2}:[0-9]{2}:[0-9]{2}Z$"
)


def canonical_json_bytes(value: object) -> bytes:
    """Return canonical UTF-8 JSON for deterministic generated artifacts."""

    return (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def canonical_csv_bytes(
    rows: Sequence[Mapping[str, object]],
    fields: Sequence[str],
) -> bytes:
    """Return a deterministic UTF-8 CSV with LF line terminators."""

    stream = io.StringIO(newline="")
    writer = csv.DictWriter(
        stream,
        fieldnames=list(fields),
        extrasaction="raise",
        lineterminator="\n",
    )
    writer.writeheader()
    for row in rows:
        writer.writerow({field: row.get(field, "") for field in fields})
    return stream.getvalue().encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_protocol(path: Path = DEFAULT_PROTOCOL) -> dict[str, object]:
    """Load and minimally validate the registered machine-readable protocol."""

    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("review protocol must be a JSON object")
    required = {
        "protocol_id",
        "source_video",
        "measurement_geometry",
        "decisions",
        "reason_codes",
        "signoff_requirements",
        "public_ledger_contract",
        "review_item_contract",
        "detached_signoff_contract",
    }
    missing = sorted(required - set(value))
    if missing:
        raise ValueError(f"review protocol is missing fields: {missing}")
    requirements = value["signoff_requirements"]
    if not isinstance(requirements, Mapping):
        raise ValueError("signoff_requirements must be an object")
    if requirements.get("expected_total_for_validation") is not None:
        raise ValueError(
            "registered protocol must not define an expected event total"
        )
    return value


def _contract_fields(
    protocol: Mapping[str, object],
    section: str,
    key: str = "fields_in_order",
) -> tuple[str, ...]:
    contract = protocol.get(section)
    if not isinstance(contract, Mapping):
        raise ValueError(f"{section} must be an object")
    fields = contract.get(key)
    if not isinstance(fields, list) or not fields:
        raise ValueError(f"{section}.{key} must be a non-empty list")
    names = tuple(str(value) for value in fields)
    if len(names) != len(set(names)):
        raise ValueError(f"{section}.{key} contains duplicate fields")
    return names


def _read_csv(path: Path) -> tuple[tuple[str, ...], list[dict[str, str]]]:
    with path.open("r", newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        return tuple(reader.fieldnames or ()), list(reader)


def _finite(
    value: object,
    field: str,
    errors: list[str],
    *,
    minimum: float | None = None,
) -> float | None:
    if isinstance(value, bool):
        errors.append(f"{field} must be finite")
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        errors.append(f"{field} must be finite")
        return None
    if not math.isfinite(numeric):
        errors.append(f"{field} must be finite")
        return None
    if minimum is not None and numeric < minimum:
        errors.append(f"{field} must be at least {minimum}")
        return None
    return numeric


def _blank(value: object) -> bool:
    return str(value or "").strip() == ""


def _integer(
    value: object,
    field: str,
    errors: list[str],
    *,
    minimum: int = 0,
) -> int | None:
    text = str(value or "").strip()
    try:
        numeric = int(text)
    except ValueError:
        errors.append(f"{field} must be an integer")
        return None
    if str(numeric) != text or numeric < minimum:
        errors.append(f"{field} must be an integer >= {minimum}")
        return None
    return numeric


def _portable_id(value: object, field: str, errors: list[str]) -> str | None:
    text = str(value or "")
    if not SAFE_ID.fullmatch(text):
        errors.append(f"{field} must be a portable opaque token")
        return None
    return text


def _reviewer_alias(
    value: object,
    field: str,
    errors: list[str],
) -> str | None:
    text = str(value or "")
    if not REVIEWER_ALIAS.fullmatch(text):
        errors.append(
            f"{field} must be a non-PII uppercase role alias such as "
            "PROJECT_OWNER"
        )
        return None
    return text


def _utc_timestamp(
    value: object,
    field: str,
    errors: list[str],
) -> str | None:
    text = str(value or "")
    if not UTC_TIMESTAMP.fullmatch(text):
        errors.append(f"{field} must be UTC YYYY-MM-DDTHH:MM:SSZ")
        return None
    try:
        datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        errors.append(f"{field} must be a real UTC timestamp")
        return None
    return text


def _sha256(value: object, field: str, errors: list[str]) -> str | None:
    text = str(value or "")
    if not SHA256.fullmatch(text):
        errors.append(f"{field} must be 64 lowercase hex characters")
        return None
    return text


def _roi_text(protocol: Mapping[str, object]) -> str:
    geometry = protocol["measurement_geometry"]
    if not isinstance(geometry, Mapping):
        raise ValueError("measurement_geometry must be an object")
    roi = geometry.get("roi_xyxy")
    if not isinstance(roi, list) or len(roi) != 4:
        raise ValueError("measurement_geometry.roi_xyxy must contain four values")
    values = [int(value) for value in roi]
    if values[0] < 0 or values[1] < 0 or values[0] >= values[2] or values[1] >= values[3]:
        raise ValueError("measurement_geometry.roi_xyxy is invalid")
    return ",".join(str(value) for value in values)


def _protocol_duration(protocol: Mapping[str, object]) -> float:
    source = protocol["source_video"]
    if not isinstance(source, Mapping):
        raise ValueError("source_video must be an object")
    value = float(source["nominal_duration_seconds"])
    if not math.isfinite(value) or value <= 0:
        raise ValueError("source_video.nominal_duration_seconds is invalid")
    return value


def _protocol_source_hash(protocol: Mapping[str, object]) -> str:
    source = protocol["source_video"]
    if not isinstance(source, Mapping):
        raise ValueError("source_video must be an object")
    value = str(source.get("sha256") or "")
    if not SHA256.fullmatch(value):
        raise ValueError("source_video.sha256 is invalid")
    return value


def _protocol_line_x(protocol: Mapping[str, object]) -> int:
    geometry = protocol["measurement_geometry"]
    if not isinstance(geometry, Mapping):
        raise ValueError("measurement_geometry must be an object")
    return int(geometry["line_x"])


def _allowed_values(
    protocol: Mapping[str, object],
    section: str,
    field: str,
) -> set[str]:
    contract = protocol[section]
    if not isinstance(contract, Mapping):
        raise ValueError(f"{section} must be an object")
    raw = contract.get(field)
    if not isinstance(raw, list):
        raise ValueError(f"{section}.{field} must be a list")
    return {str(value) for value in raw}


def _reason_codes(
    protocol: Mapping[str, object],
) -> dict[str, set[str]]:
    raw = protocol["reason_codes"]
    if not isinstance(raw, Mapping):
        raise ValueError("reason_codes must be an object")
    return {
        str(decision): {str(code) for code in codes}
        for decision, codes in raw.items()
        if isinstance(codes, list)
    }


def _mapping_for_direction(
    protocol: Mapping[str, object],
    direction: str,
) -> str | None:
    geometry = protocol["measurement_geometry"]
    if not isinstance(geometry, Mapping):
        return None
    mapping = geometry.get("operational_stream_mapping")
    if not isinstance(mapping, Mapping):
        return None
    value = mapping.get(direction)
    return str(value) if value is not None else None


def validate_review_items(
    rows: Sequence[Mapping[str, object]],
    protocol: Mapping[str, object],
    *,
    fields: Sequence[str] | None = None,
) -> dict[str, object]:
    """Validate complete review history without exposing or checking a total."""

    errors: list[str] = []
    expected_fields = _contract_fields(protocol, "review_item_contract")
    if fields is not None and tuple(fields) != expected_fields:
        errors.append(
            f"review-item header must be exactly {list(expected_fields)}; "
            f"got {list(fields)}"
        )
    if not rows:
        errors.append("review-item history must contain at least one row")

    decisions = {str(value) for value in protocol["decisions"]}  # type: ignore[index]
    reasons = _reason_codes(protocol)
    directions = set(
        str(value)
        for value in protocol["measurement_geometry"]["image_directions"]  # type: ignore[index]
    )
    item_ids: set[str] = set()
    accepted_packets: set[str] = set()
    accepted_count = 0
    uncertain_count = 0

    for position, row in enumerate(rows, start=2):
        prefix = f"review-item line {position}"
        unknown = sorted(set(row) - set(expected_fields))
        missing = sorted(set(expected_fields) - set(row))
        if unknown:
            errors.append(f"{prefix}: unknown fields: {unknown}")
        if missing:
            errors.append(f"{prefix}: missing fields: {missing}")

        item_id = _portable_id(row.get("review_item_id"), f"{prefix}: review_item_id", errors)
        if item_id is not None:
            if item_id in item_ids:
                errors.append(f"{prefix}: duplicate review_item_id {item_id!r}")
            item_ids.add(item_id)
        _portable_id(
            row.get("enumeration_pass_id"),
            f"{prefix}: enumeration_pass_id",
            errors,
        )

        approx_pts = _finite(
            row.get("approx_pts_seconds"),
            f"{prefix}: approx_pts_seconds",
            errors,
            minimum=0,
        )
        if approx_pts is not None and approx_pts >= _protocol_duration(protocol):
            errors.append(f"{prefix}: approx_pts_seconds must be inside the clip")
        direction = str(row.get("proposed_direction") or "")
        if direction not in directions:
            errors.append(f"{prefix}: proposed_direction is invalid")
        roi = protocol["measurement_geometry"]["roi_xyxy"]  # type: ignore[index]
        crossing_y = _finite(
            row.get("approx_crossing_y_px"),
            f"{prefix}: approx_crossing_y_px",
            errors,
            minimum=float(roi[1]),
        )
        if crossing_y is not None and crossing_y > float(roi[3]):
            errors.append(f"{prefix}: approx_crossing_y_px is outside the ROI")

        packet_id = _portable_id(
            row.get("evidence_packet_id"),
            f"{prefix}: evidence_packet_id",
            errors,
        )
        decision = str(row.get("final_decision") or "")
        if decision not in decisions:
            errors.append(
                f"{prefix}: final_decision must be one of {sorted(decisions)}"
            )
        reason = str(row.get("reason_code") or "")
        if decision in reasons and reason not in reasons[decision]:
            errors.append(
                f"{prefix}: reason_code {reason!r} is invalid for {decision}"
            )
        duplicate_of = str(row.get("duplicate_of_event_id") or "")
        if decision == "REJECT" and reason == "DUPLICATE_FRAGMENT":
            _portable_id(
                duplicate_of,
                f"{prefix}: duplicate_of_event_id",
                errors,
            )
        elif duplicate_of:
            errors.append(
                f"{prefix}: duplicate_of_event_id is only allowed for "
                "DUPLICATE_FRAGMENT"
            )
        _reviewer_alias(
            row.get("reviewer_id"),
            f"{prefix}: reviewer_id",
            errors,
        )
        _utc_timestamp(
            row.get("reviewed_at_utc"),
            f"{prefix}: reviewed_at_utc",
            errors,
        )

        if decision == "ACCEPT":
            accepted_count += 1
            if packet_id is not None:
                if packet_id in accepted_packets:
                    errors.append(
                        f"{prefix}: accepted evidence_packet_id is duplicated"
                    )
                accepted_packets.add(packet_id)
        elif decision == "UNCERTAIN":
            uncertain_count += 1

    complete = not errors
    return {
        "contract": str(protocol["protocol_id"]),
        "status": "PASS" if complete else "FAIL",
        "review_item_count": len(rows),
        # The registered protocol hides totals until every row is resolved.
        "accepted_review_item_count": accepted_count if complete else None,
        "uncertain_count": uncertain_count if complete else None,
        "accepted_evidence_packet_ids": (
            sorted(accepted_packets) if complete else []
        ),
        "errors": errors,
    }


def validate_accepted_ledger(
    rows: Sequence[Mapping[str, object]],
    protocol: Mapping[str, object],
    *,
    fields: Sequence[str] | None = None,
) -> dict[str, object]:
    """Validate accepted event rows exactly against the registered contract."""

    errors: list[str] = []
    expected_fields = _contract_fields(protocol, "public_ledger_contract")
    if fields is not None and tuple(fields) != expected_fields:
        errors.append(
            f"ledger header must be exactly {list(expected_fields)}; "
            f"got {list(fields)}"
        )
    if not rows:
        errors.append("accepted event ledger must contain at least one row")

    contract = protocol["public_ledger_contract"]
    if not isinstance(contract, Mapping):
        raise ValueError("public_ledger_contract must be an object")
    time_values = _allowed_values(
        protocol,
        "public_ledger_contract",
        "time_resolution_values",
    )
    continuity_values = _allowed_values(
        protocol,
        "public_ledger_contract",
        "continuity_class_values",
    )
    boundary_values = _allowed_values(
        protocol,
        "public_ledger_contract",
        "boundary_flag_values",
    )
    accept_reasons = _reason_codes(protocol).get("ACCEPT", set())
    directions = set(
        str(value)
        for value in protocol["measurement_geometry"]["image_directions"]  # type: ignore[index]
    )
    source_hash = _protocol_source_hash(protocol)
    duration = _protocol_duration(protocol)
    line_x_expected = _protocol_line_x(protocol)
    roi_expected = _roi_text(protocol)
    frame_count = int(protocol["source_video"]["decoded_frame_count"])  # type: ignore[index]

    event_ids: set[str] = set()
    packet_ids: set[str] = set()
    ledger_versions: set[str] = set()
    reviewer_ids: set[str] = set()
    lower_order = -math.inf
    counts = {direction: 0 for direction in sorted(directions)}
    interval_count = 0

    reason_structure = {
        "CLEAR_CONTINUOUS_CROSSING": ("CLEAR_CONTINUOUS", "NONE"),
        "OCCLUDED_CONTINUITY_RESOLVED": ("OCCLUDED_RESOLVED", "NONE"),
        "ROI_BOUNDARY_PARTIAL_BUT_CLEAR": (
            "ROI_BOUNDARY_PARTIAL_RESOLVED",
            "ROI_BOUNDARY_PARTIAL",
        ),
    }

    for position, row in enumerate(rows, start=2):
        prefix = f"ledger line {position}"
        unknown = sorted(set(row) - set(expected_fields))
        missing = sorted(set(expected_fields) - set(row))
        if unknown:
            errors.append(f"{prefix}: unknown fields: {unknown}")
        if missing:
            errors.append(f"{prefix}: missing fields: {missing}")

        if row.get("schema_version") != LEDGER_SCHEMA_VERSION:
            errors.append(
                f"{prefix}: schema_version must be {LEDGER_SCHEMA_VERSION}"
            )
        ledger_version = _portable_id(
            row.get("ledger_version"),
            f"{prefix}: ledger_version",
            errors,
        )
        if ledger_version is not None:
            ledger_versions.add(ledger_version)
        event_id = _portable_id(row.get("event_id"), f"{prefix}: event_id", errors)
        if event_id is not None:
            if event_id in event_ids:
                errors.append(f"{prefix}: duplicate event_id {event_id!r}")
            event_ids.add(event_id)
        if row.get("source_video_sha256") != source_hash:
            errors.append(f"{prefix}: source_video_sha256 is not the registered source")

        resolution = str(row.get("time_resolution") or "")
        if resolution not in time_values:
            errors.append(f"{prefix}: time_resolution is invalid")
        lower = _finite(
            row.get("time_lower_seconds"),
            f"{prefix}: time_lower_seconds",
            errors,
            minimum=0,
        )
        upper = _finite(
            row.get("time_upper_seconds"),
            f"{prefix}: time_upper_seconds",
            errors,
            minimum=0,
        )
        if lower is not None:
            if lower < lower_order:
                errors.append(
                    f"{prefix}: ledger rows must be ordered by lower event time"
                )
            lower_order = lower
        if upper is not None and upper >= duration:
            errors.append(f"{prefix}: time_upper_seconds must be inside the clip")

        if resolution == "EXACT_FRAME":
            frame_index = _integer(
                row.get("frame_index"),
                f"{prefix}: frame_index",
                errors,
            )
            pts = _finite(
                row.get("pts_seconds"),
                f"{prefix}: pts_seconds",
                errors,
                minimum=0,
            )
            if frame_index is not None and frame_index >= frame_count:
                errors.append(f"{prefix}: frame_index is outside decoded frames")
            if pts is not None and pts >= duration:
                errors.append(f"{prefix}: pts_seconds must be inside the clip")
            if (
                pts is not None
                and lower is not None
                and upper is not None
                and not (pts == lower == upper)
            ):
                errors.append(
                    f"{prefix}: exact-frame bounds must equal pts_seconds"
                )
        elif resolution == "INTERVAL_CENSORED":
            interval_count += 1
            if not _blank(row.get("frame_index")) or not _blank(
                row.get("pts_seconds")
            ):
                errors.append(
                    f"{prefix}: interval-censored frame_index and pts_seconds "
                    "must be blank"
                )
            if lower is not None and upper is not None and not lower < upper:
                errors.append(
                    f"{prefix}: interval-censored bounds must satisfy lower < upper"
                )

        direction = str(row.get("image_direction") or "")
        if direction not in directions:
            errors.append(f"{prefix}: image_direction is invalid")
        else:
            counts[direction] += 1
            expected_mapping = _mapping_for_direction(protocol, direction)
            if row.get("operational_stream_mapping") != expected_mapping:
                errors.append(
                    f"{prefix}: operational_stream_mapping does not match "
                    "the registered direction mapping"
                )

        roi_values = protocol["measurement_geometry"]["roi_xyxy"]  # type: ignore[index]
        crossing_y = _finite(
            row.get("crossing_y_px"),
            f"{prefix}: crossing_y_px",
            errors,
            minimum=float(roi_values[1]),
        )
        if crossing_y is not None and crossing_y > float(roi_values[3]):
            errors.append(f"{prefix}: crossing_y_px is outside the ROI")
        line_x = _integer(row.get("line_x"), f"{prefix}: line_x", errors)
        if line_x is not None and line_x != line_x_expected:
            errors.append(f"{prefix}: line_x does not match the protocol")
        if row.get("roi_xyxy") != roi_expected:
            errors.append(f"{prefix}: roi_xyxy does not match the protocol")

        continuity = str(row.get("continuity_class") or "")
        if continuity not in continuity_values:
            errors.append(f"{prefix}: continuity_class is invalid")
        boundary = str(row.get("boundary_flags") or "")
        if boundary not in boundary_values:
            errors.append(f"{prefix}: boundary_flags is invalid")
        packet_id = _portable_id(
            row.get("evidence_packet_id"),
            f"{prefix}: evidence_packet_id",
            errors,
        )
        if packet_id is not None:
            if packet_id in packet_ids:
                errors.append(f"{prefix}: duplicate evidence_packet_id")
            packet_ids.add(packet_id)
        if row.get("decision") != contract.get("decision_value"):
            errors.append(f"{prefix}: accepted ledger decision must be ACCEPT")
        reason = str(row.get("decision_reason_code") or "")
        if reason not in accept_reasons:
            errors.append(f"{prefix}: decision_reason_code is not an ACCEPT code")
        if reason in reason_structure:
            expected_continuity, expected_boundary = reason_structure[reason]
            if continuity != expected_continuity:
                errors.append(
                    f"{prefix}: continuity_class is inconsistent with reason"
                )
            if boundary != expected_boundary:
                errors.append(
                    f"{prefix}: boundary_flags is inconsistent with reason"
                )

        reviewer = _reviewer_alias(
            row.get("reviewer_id"),
            f"{prefix}: reviewer_id",
            errors,
        )
        if reviewer is not None:
            reviewer_ids.add(reviewer)
        _utc_timestamp(
            row.get("reviewed_at_utc"),
            f"{prefix}: reviewed_at_utc",
            errors,
        )

    if len(ledger_versions) > 1:
        errors.append("all ledger rows must use one ledger_version")
    return {
        "contract": LEDGER_SCHEMA_VERSION,
        "status": "PASS" if not errors else "FAIL",
        "ledger_row_count": len(rows),
        "ledger_version": (
            next(iter(ledger_versions)) if len(ledger_versions) == 1 else None
        ),
        "accepted_counts_by_direction": counts,
        "interval_censored_count": interval_count,
        "evidence_packet_ids": sorted(packet_ids),
        "reviewer_ids": sorted(reviewer_ids),
        "errors": errors,
    }


def validate_signoff_request(
    request: object,
    protocol: Mapping[str, object],
) -> dict[str, object]:
    """Validate the explicit human sign-off request; no count is an input."""

    errors: list[str] = []
    if not isinstance(request, Mapping):
        return {
            "contract": SIGNOFF_SCHEMA_VERSION,
            "status": "FAIL",
            "errors": ["sign-off request must be a JSON object"],
        }
    unknown = sorted(set(request) - SIGNOFF_REQUEST_FIELDS)
    missing = sorted(SIGNOFF_REQUEST_FIELDS - set(request))
    if unknown:
        errors.append(f"unknown sign-off request fields: {unknown}")
    if missing:
        errors.append(f"missing sign-off request fields: {missing}")
    if request.get("schema_version") != SIGNOFF_SCHEMA_VERSION:
        errors.append(f"schema_version must be {SIGNOFF_SCHEMA_VERSION}")
    _portable_id(request.get("ledger_version"), "ledger_version", errors)
    _reviewer_alias(request.get("reviewer_id"), "reviewer_id", errors)
    _utc_timestamp(request.get("signed_at_utc"), "signed_at_utc", errors)
    detached = protocol["detached_signoff_contract"]
    if not isinstance(detached, Mapping):
        raise ValueError("detached_signoff_contract must be an object")
    if request.get("attestation") != detached.get("attestation"):
        errors.append("attestation must exactly match the registered protocol")
    return {
        "contract": SIGNOFF_SCHEMA_VERSION,
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
    }


def _validate_cross_artifact_links(
    ledger_rows: Sequence[Mapping[str, object]],
    ledger_report: Mapping[str, object],
    review_rows: Sequence[Mapping[str, object]],
    review_report: Mapping[str, object],
    request: Mapping[str, object],
) -> list[str]:
    errors: list[str] = []
    ledger_packets = set(ledger_report["evidence_packet_ids"])  # type: ignore[arg-type]
    accepted_packets = set(
        review_report["accepted_evidence_packet_ids"]  # type: ignore[arg-type]
    )
    if ledger_packets != accepted_packets:
        errors.append(
            "accepted review items and accepted ledger rows must have the same "
            "evidence_packet_id set"
        )
    if ledger_report.get("ledger_row_count") != review_report.get(
        "accepted_review_item_count"
    ):
        errors.append(
            "accepted review-item count does not match accepted ledger rows"
        )
    if ledger_report.get("ledger_version") != request.get("ledger_version"):
        errors.append("ledger_version does not match the sign-off request")
    reviewers = set(ledger_report["reviewer_ids"])  # type: ignore[arg-type]
    if reviewers != {request.get("reviewer_id")}:
        errors.append("accepted ledger reviewer_id does not match sign-off request")

    event_ids = {str(row.get("event_id") or "") for row in ledger_rows}
    for position, row in enumerate(review_rows, start=2):
        if (
            row.get("final_decision") == "REJECT"
            and row.get("reason_code") == "DUPLICATE_FRAGMENT"
            and row.get("duplicate_of_event_id") not in event_ids
        ):
            errors.append(
                f"review-item line {position}: duplicate_of_event_id does not "
                "reference an accepted event"
            )
    return errors


def create_signoff_package(
    ledger_draft_csv: Path,
    review_items_csv: Path,
    evidence_manifest: Path,
    request_json: Path,
    ledger_output: Path,
    signoff_output: Path,
    *,
    protocol_path: Path = DEFAULT_PROTOCOL,
    overwrite: bool = False,
) -> dict[str, object]:
    """Finalize reviewed artifacts without creating or changing any decision."""

    if not overwrite:
        existing = [
            path for path in (ledger_output, signoff_output) if path.exists()
        ]
        if existing:
            raise FileExistsError(
                "refusing to overwrite signed-review history: "
                + ", ".join(str(path) for path in existing)
            )

    protocol = load_protocol(protocol_path)
    ledger_fields, ledger_rows = _read_csv(ledger_draft_csv)
    review_fields, review_rows = _read_csv(review_items_csv)
    request = json.loads(request_json.read_text(encoding="utf-8"))
    if not isinstance(request, Mapping):
        raise ValueError("sign-off request must be a JSON object")

    ledger_report = validate_accepted_ledger(
        ledger_rows,
        protocol,
        fields=ledger_fields,
    )
    review_report = validate_review_items(
        review_rows,
        protocol,
        fields=review_fields,
    )
    request_report = validate_signoff_request(request, protocol)
    errors = [
        *(str(error) for error in ledger_report["errors"]),  # type: ignore[index]
        *(str(error) for error in review_report["errors"]),  # type: ignore[index]
        *(str(error) for error in request_report["errors"]),  # type: ignore[index]
    ]
    if (
        ledger_report["status"] == "PASS"
        and review_report["status"] == "PASS"
        and request_report["status"] == "PASS"
    ):
        errors.extend(
            _validate_cross_artifact_links(
                ledger_rows,
                ledger_report,
                review_rows,
                review_report,
                request,
            )
        )
    if errors:
        raise ValueError(
            "review cannot be signed off:\n- " + "\n- ".join(errors)
        )
    if not evidence_manifest.is_file():
        raise FileNotFoundError(
            f"evidence manifest does not exist: {evidence_manifest}"
        )

    canonical_ledger = canonical_csv_bytes(ledger_rows, ledger_fields)
    canonical_reviews = canonical_csv_bytes(review_rows, review_fields)
    detached = protocol["detached_signoff_contract"]
    if not isinstance(detached, Mapping):
        raise ValueError("detached_signoff_contract must be an object")
    signoff = {
        "schema_version": SIGNOFF_SCHEMA_VERSION,
        "ledger_version": request["ledger_version"],
        "protocol_sha256": sha256_file(protocol_path),
        "source_video_sha256": _protocol_source_hash(protocol),
        "review_items_sha256": sha256_bytes(canonical_reviews),
        "signed_event_ledger_sha256": sha256_bytes(canonical_ledger),
        "evidence_manifest_sha256": sha256_file(evidence_manifest),
        "accepted_counts_by_direction": (
            ledger_report["accepted_counts_by_direction"]
        ),
        "uncertain_count": review_report["uncertain_count"],
        "reviewer_id": request["reviewer_id"],
        "signed_at_utc": request["signed_at_utc"],
        "attestation": request["attestation"],
    }
    expected_signoff_fields = set(
        _contract_fields(
            protocol,
            "detached_signoff_contract",
            key="fields",
        )
    )
    if set(signoff) != expected_signoff_fields:
        raise ValueError(
            "generated sign-off fields differ from registered contract"
        )

    ledger_output.parent.mkdir(parents=True, exist_ok=True)
    signoff_output.parent.mkdir(parents=True, exist_ok=True)
    ledger_output.write_bytes(canonical_ledger)
    signoff_output.write_bytes(canonical_json_bytes(signoff))
    return validate_signed_package(
        ledger_output,
        review_items_csv,
        evidence_manifest,
        signoff_output,
        protocol_path=protocol_path,
    )


def validate_signed_package(
    ledger_path: Path,
    review_items_path: Path,
    evidence_manifest_path: Path,
    signoff_path: Path,
    *,
    protocol_path: Path = DEFAULT_PROTOCOL,
) -> dict[str, object]:
    """Validate every detached sign-off hash and cross-artifact relationship."""

    errors: list[str] = []
    protocol = load_protocol(protocol_path)
    ledger_fields, ledger_rows = _read_csv(ledger_path)
    review_fields, review_rows = _read_csv(review_items_path)
    try:
        signoff = json.loads(signoff_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return {
            "contract": SIGNOFF_SCHEMA_VERSION,
            "status": "FAIL",
            "errors": [f"detached sign-off is unreadable: {exc}"],
        }
    if not isinstance(signoff, Mapping):
        return {
            "contract": SIGNOFF_SCHEMA_VERSION,
            "status": "FAIL",
            "errors": ["detached sign-off must be a JSON object"],
        }

    expected_fields = set(
        _contract_fields(
            protocol,
            "detached_signoff_contract",
            key="fields",
        )
    )
    unknown = sorted(set(signoff) - expected_fields)
    missing = sorted(expected_fields - set(signoff))
    if unknown:
        errors.append(f"unknown detached sign-off fields: {unknown}")
    if missing:
        errors.append(f"missing detached sign-off fields: {missing}")

    ledger_report = validate_accepted_ledger(
        ledger_rows,
        protocol,
        fields=ledger_fields,
    )
    review_report = validate_review_items(
        review_rows,
        protocol,
        fields=review_fields,
    )
    errors.extend(str(error) for error in ledger_report["errors"])  # type: ignore[index]
    errors.extend(str(error) for error in review_report["errors"])  # type: ignore[index]
    request = {
        "schema_version": signoff.get("schema_version"),
        "ledger_version": signoff.get("ledger_version"),
        "reviewer_id": signoff.get("reviewer_id"),
        "signed_at_utc": signoff.get("signed_at_utc"),
        "attestation": signoff.get("attestation"),
    }
    request_report = validate_signoff_request(request, protocol)
    errors.extend(str(error) for error in request_report["errors"])  # type: ignore[index]
    if (
        ledger_report["status"] == "PASS"
        and review_report["status"] == "PASS"
        and request_report["status"] == "PASS"
    ):
        errors.extend(
            _validate_cross_artifact_links(
                ledger_rows,
                ledger_report,
                review_rows,
                review_report,
                request,
            )
        )

    canonical_ledger = canonical_csv_bytes(ledger_rows, ledger_fields)
    canonical_reviews = canonical_csv_bytes(review_rows, review_fields)
    expected_links = {
        "protocol_sha256": sha256_file(protocol_path),
        "source_video_sha256": _protocol_source_hash(protocol),
        "review_items_sha256": sha256_bytes(canonical_reviews),
        "signed_event_ledger_sha256": sha256_bytes(canonical_ledger),
        "accepted_counts_by_direction": (
            ledger_report["accepted_counts_by_direction"]
        ),
        "uncertain_count": review_report["uncertain_count"],
    }
    if evidence_manifest_path.is_file():
        expected_links["evidence_manifest_sha256"] = sha256_file(
            evidence_manifest_path
        )
    else:
        errors.append("evidence manifest is missing")
    for field, expected in expected_links.items():
        if signoff.get(field) != expected:
            errors.append(f"{field} does not match the signed artifacts")

    return {
        "contract": SIGNOFF_SCHEMA_VERSION,
        "status": "PASS" if not errors else "FAIL",
        "ledger_row_count": len(ledger_rows),
        "accepted_counts_by_direction": (
            ledger_report["accepted_counts_by_direction"]
        ),
        "uncertain_count": review_report["uncertain_count"],
        "errors": errors,
    }


def export_arrival_trace(
    ledger_path: Path,
    review_items_path: Path,
    evidence_manifest_path: Path,
    signoff_path: Path,
    trace_output: Path,
    trace_manifest_output: Path | None = None,
    *,
    protocol_path: Path = DEFAULT_PROTOCOL,
    overwrite: bool = False,
) -> dict[str, object]:
    """Export accepted arrival events while preserving exact/interval timing."""

    package_report = validate_signed_package(
        ledger_path,
        review_items_path,
        evidence_manifest_path,
        signoff_path,
        protocol_path=protocol_path,
    )
    if package_report["status"] != "PASS":
        raise ValueError(
            "cannot export an invalid signed package:\n- "
            + "\n- ".join(
                str(error) for error in package_report["errors"]  # type: ignore[index]
            )
        )
    if trace_manifest_output is None:
        trace_manifest_output = trace_output.with_suffix(
            trace_output.suffix + ".manifest.json"
        )
    if not overwrite:
        existing = [
            path
            for path in (trace_output, trace_manifest_output)
            if path.exists()
        ]
        if existing:
            raise FileExistsError(
                "refusing to overwrite observed-trace history: "
                + ", ".join(str(path) for path in existing)
            )

    protocol = load_protocol(protocol_path)
    _, ledger_rows = _read_csv(ledger_path)
    signoff = json.loads(signoff_path.read_text(encoding="utf-8"))
    arrival_direction = next(
        direction
        for direction in protocol["measurement_geometry"]["image_directions"]  # type: ignore[index]
        if _mapping_for_direction(protocol, str(direction)) == "arrival"
    )
    arrival_rows = [
        row
        for row in ledger_rows
        if row["image_direction"] == arrival_direction
    ]
    trace_rows: list[dict[str, object]] = []
    interval_count = 0
    for index, row in enumerate(arrival_rows, start=1):
        if row["time_resolution"] == "EXACT_FRAME":
            arrival_seconds = row["pts_seconds"]
        else:
            arrival_seconds = ""
            interval_count += 1
        trace_rows.append(
            {
                "schema_version": TRACE_SCHEMA_VERSION,
                "ledger_version": row["ledger_version"],
                "arrival_index": index,
                "source_event_id": row["event_id"],
                "time_resolution": row["time_resolution"],
                "arrival_seconds": arrival_seconds,
                "time_lower_seconds": row["time_lower_seconds"],
                "time_upper_seconds": row["time_upper_seconds"],
            }
        )
    trace_bytes = canonical_csv_bytes(trace_rows, TRACE_FIELDS)
    trace_manifest = {
        "schema_version": TRACE_SCHEMA_VERSION,
        "artifact_type": "FINITE_OBSERVED_ARRIVAL_TRACE",
        "source_ledger_sha256": signoff["signed_event_ledger_sha256"],
        "source_signoff_sha256": sha256_file(signoff_path),
        "ledger_version": signoff["ledger_version"],
        "arrival_direction": arrival_direction,
        "event_count": len(trace_rows),
        "interval_censored_event_count": interval_count,
        "source_duration_seconds": _protocol_duration(protocol),
        "clock_basis": "SOURCE_VIDEO_PRESENTATION_TIME_SECONDS",
        "trace_sha256": sha256_bytes(trace_bytes),
        "claim_ceiling": "FINITE_CLIP_TRACE_REPLAY_ONLY",
        "stationarity_claim": STATIONARITY_CLAIM,
        "privacy_classification": PRIVACY_CLASSIFICATION,
    }
    trace_output.parent.mkdir(parents=True, exist_ok=True)
    trace_manifest_output.parent.mkdir(parents=True, exist_ok=True)
    trace_output.write_bytes(trace_bytes)
    trace_manifest_output.write_bytes(canonical_json_bytes(trace_manifest))
    return validate_arrival_trace(trace_output, trace_manifest_output)


def validate_arrival_trace(
    trace_path: Path,
    trace_manifest_path: Path,
) -> dict[str, object]:
    """Validate finite observed trace ordering, timing, and integrity links."""

    errors: list[str] = []
    fields, rows = _read_csv(trace_path)
    if fields != TRACE_FIELDS:
        errors.append(
            f"trace header must be exactly {list(TRACE_FIELDS)}; "
            f"got {list(fields)}"
        )
    try:
        manifest = json.loads(trace_manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return {
            "contract": TRACE_SCHEMA_VERSION,
            "status": "FAIL",
            "errors": [f"trace manifest is unreadable: {exc}"],
        }
    if not isinstance(manifest, Mapping):
        return {
            "contract": TRACE_SCHEMA_VERSION,
            "status": "FAIL",
            "errors": ["trace manifest must be a JSON object"],
        }
    unknown = sorted(set(manifest) - TRACE_MANIFEST_FIELDS)
    missing = sorted(TRACE_MANIFEST_FIELDS - set(manifest))
    if unknown:
        errors.append(f"unknown trace manifest fields: {unknown}")
    if missing:
        errors.append(f"missing trace manifest fields: {missing}")
    expected_literals = {
        "schema_version": TRACE_SCHEMA_VERSION,
        "artifact_type": "FINITE_OBSERVED_ARRIVAL_TRACE",
        "clock_basis": "SOURCE_VIDEO_PRESENTATION_TIME_SECONDS",
        "claim_ceiling": "FINITE_CLIP_TRACE_REPLAY_ONLY",
        "stationarity_claim": STATIONARITY_CLAIM,
        "privacy_classification": PRIVACY_CLASSIFICATION,
    }
    for field, value in expected_literals.items():
        if manifest.get(field) != value:
            errors.append(f"{field} must be {value}")
    for field in ("source_ledger_sha256", "source_signoff_sha256"):
        _sha256(manifest.get(field), field, errors)

    previous_lower = -math.inf
    interval_count = 0
    event_ids: set[str] = set()
    ledger_versions: set[str] = set()
    for index, row in enumerate(rows, start=1):
        prefix = f"trace row {index}"
        if row.get("schema_version") != TRACE_SCHEMA_VERSION:
            errors.append(f"{prefix}: schema_version is invalid")
        version = _portable_id(
            row.get("ledger_version"),
            f"{prefix}: ledger_version",
            errors,
        )
        if version is not None:
            ledger_versions.add(version)
        if row.get("arrival_index") != str(index):
            errors.append(f"{prefix}: arrival_index must be {index}")
        event_id = _portable_id(
            row.get("source_event_id"),
            f"{prefix}: source_event_id",
            errors,
        )
        if event_id is not None:
            if event_id in event_ids:
                errors.append(f"{prefix}: source_event_id is duplicated")
            event_ids.add(event_id)
        lower = _finite(
            row.get("time_lower_seconds"),
            f"{prefix}: time_lower_seconds",
            errors,
            minimum=0,
        )
        upper = _finite(
            row.get("time_upper_seconds"),
            f"{prefix}: time_upper_seconds",
            errors,
            minimum=0,
        )
        if lower is not None:
            if lower < previous_lower:
                errors.append("trace must be ordered by time_lower_seconds")
            previous_lower = lower
        resolution = row.get("time_resolution")
        if resolution == "EXACT_FRAME":
            arrival = _finite(
                row.get("arrival_seconds"),
                f"{prefix}: arrival_seconds",
                errors,
                minimum=0,
            )
            if (
                arrival is not None
                and lower is not None
                and upper is not None
                and not (arrival == lower == upper)
            ):
                errors.append(f"{prefix}: exact bounds must equal arrival_seconds")
        elif resolution == "INTERVAL_CENSORED":
            interval_count += 1
            if not _blank(row.get("arrival_seconds")):
                errors.append(
                    f"{prefix}: interval-censored arrival_seconds must be blank"
                )
            if lower is not None and upper is not None and not lower < upper:
                errors.append(
                    f"{prefix}: interval-censored bounds must satisfy lower < upper"
                )
        else:
            errors.append(f"{prefix}: time_resolution is invalid")

    if len(ledger_versions) > 1:
        errors.append("all trace rows must use one ledger_version")
    if ledger_versions and manifest.get("ledger_version") not in ledger_versions:
        errors.append("trace ledger_version does not match manifest")
    if manifest.get("event_count") != len(rows):
        errors.append("event_count does not match the trace")
    if manifest.get("interval_censored_event_count") != interval_count:
        errors.append("interval_censored_event_count does not match the trace")
    if manifest.get("trace_sha256") != sha256_file(trace_path):
        errors.append("trace_sha256 does not match the trace bytes")
    return {
        "contract": TRACE_SCHEMA_VERSION,
        "status": "PASS" if not errors else "FAIL",
        "event_count": len(rows),
        "interval_censored_event_count": interval_count,
        "errors": errors,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    signoff = subparsers.add_parser(
        "signoff",
        help="Finalize already-reviewed events and write a detached hash sign-off.",
    )
    signoff.add_argument("--ledger-draft", required=True, type=Path)
    signoff.add_argument("--review-items", required=True, type=Path)
    signoff.add_argument("--evidence-manifest", required=True, type=Path)
    signoff.add_argument("--request-json", required=True, type=Path)
    signoff.add_argument("--ledger-out", required=True, type=Path)
    signoff.add_argument("--signoff-out", required=True, type=Path)
    signoff.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    signoff.add_argument("--overwrite", action="store_true")

    validate = subparsers.add_parser(
        "validate",
        help="Validate all signed artifacts and detached hashes.",
    )
    validate.add_argument("--ledger", required=True, type=Path)
    validate.add_argument("--review-items", required=True, type=Path)
    validate.add_argument("--evidence-manifest", required=True, type=Path)
    validate.add_argument("--signoff", required=True, type=Path)
    validate.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)

    export = subparsers.add_parser(
        "export-trace",
        help="Export accepted arrivals with exact or interval-censored timing.",
    )
    export.add_argument("--ledger", required=True, type=Path)
    export.add_argument("--review-items", required=True, type=Path)
    export.add_argument("--evidence-manifest", required=True, type=Path)
    export.add_argument("--signoff", required=True, type=Path)
    export.add_argument("--trace-out", required=True, type=Path)
    export.add_argument("--trace-manifest-out", type=Path)
    export.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    export.add_argument("--overwrite", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    try:
        if args.command == "signoff":
            report = create_signoff_package(
                args.ledger_draft,
                args.review_items,
                args.evidence_manifest,
                args.request_json,
                args.ledger_out,
                args.signoff_out,
                protocol_path=args.protocol,
                overwrite=args.overwrite,
            )
        elif args.command == "validate":
            report = validate_signed_package(
                args.ledger,
                args.review_items,
                args.evidence_manifest,
                args.signoff,
                protocol_path=args.protocol,
            )
        else:
            report = export_arrival_trace(
                args.ledger,
                args.review_items,
                args.evidence_manifest,
                args.signoff,
                args.trace_out,
                args.trace_manifest_out,
                protocol_path=args.protocol,
                overwrite=args.overwrite,
            )
    except (
        FileExistsError,
        FileNotFoundError,
        json.JSONDecodeError,
        OSError,
        ValueError,
    ) as exc:
        report = {"status": "FAIL", "errors": [str(exc)]}
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
