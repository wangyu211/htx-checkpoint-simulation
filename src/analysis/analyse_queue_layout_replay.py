"""Replay one immutable traveller ledger under pooled and separate queues.

This module is a deliberately bounded *mechanism counterfactual*.  It does not
change demand, service requirements, stage order, capacity, or the population
of travellers.  For each AnyLogic replication it:

1. reconstructs the registered pooled-FCFS mechanism from the entity ledger;
2. requires every replayed start/completion timestamp to match AnyLogic;
3. replays the same travellers through counter-specific shortest-queue lanes;
4. proves that the immutable traveller inputs are identical across layouts;
5. only then forms paired replication-level intervals.

The replay is serial: replayed Security completions are the Immigration
arrivals.  Separate queues are joined once, at stage arrival, and travellers
never jockey.  Every lane choice and counter event is logged.  No default real
output directory is provided, so importing or testing this module cannot create
an apparent result.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import statistics
from collections import defaultdict
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from src.analysis.analyse_operational_replications import paired_difference
from src.analysis.export_queue_layout_replay_source import (
    audit_curated_package,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DESIGN = PROJECT_ROOT / "config" / "queue_layout_replay_study.json"
DEFAULT_CURATED_SOURCE_DIR = (
    PROJECT_ROOT / "data" / "derived" / "queue_layout_replay_source"
)
DEFAULT_ENTITY_LEDGER = DEFAULT_CURATED_SOURCE_DIR / "entity_ledger.csv"
DEFAULT_REPLICATION_KPIS = DEFAULT_CURATED_SOURCE_DIR / "registered_p95.csv"
DEFAULT_SOURCE_MANIFEST = DEFAULT_CURATED_SOURCE_DIR / "manifest.json"
DEFAULT_LOCAL_EVENT_LOG = (
    PROJECT_ROOT
    / "results"
    / "intermediate"
    / "queue_layout_replay"
    / "replay_events.public_source_lf.csv"
)

POOLED = "POOLED_FCFS"
SEPARATE = "SEPARATE_JSQ_NO_JOCKEYING"
SECURITY = "SECURITY"
IMMIGRATION = "IMMIGRATION"
STAGES = (SECURITY, IMMIGRATION)
LAYOUTS = (POOLED, SEPARATE)

ANALYSIS_SCHEMA_VERSION = "1.0"
ANALYSIS_ID = "TASK3_QUEUE_LAYOUT_REPLAY_ANALYSIS_V1"
REPLAY_EPSILON = 1e-12

REPLICATION_METRICS = (
    "total_queue_wait_p95_seconds",
    "peak_security_waiting_queue",
    "peak_immigration_waiting_queue",
    "peak_total_waiting_queue",
    "peak_security_lane_waiting_queue",
    "peak_immigration_lane_waiting_queue",
    "security_fragmentation_seconds",
    "immigration_fragmentation_seconds",
    "total_fragmentation_seconds",
    "security_fragmentation_fraction",
    "immigration_fragmentation_fraction",
    "total_fragmentation_fraction",
)

CROSS_SCALE_METRICS = tuple(
    metric
    for metric in REPLICATION_METRICS
    if metric
    not in {
        "security_fragmentation_seconds",
        "immigration_fragmentation_seconds",
        "total_fragmentation_seconds",
    }
)

EVENT_FIELDS = (
    "schema_version",
    "study_id",
    "scenario_id",
    "input_sample_id",
    "replication_id",
    "study_cell_id",
    "layout_id",
    "stage",
    "traveller_id",
    "stage_arrival_seconds",
    "service_demand_seconds",
    "counter_id",
    "service_start_seconds",
    "service_end_seconds",
    "queue_wait_seconds",
    "lane_length_snapshot",
    "minimum_lane_length",
    "tie_candidate_counter_ids",
    "tie_candidate_count",
    "lane_tie_u",
    "tie_index",
    "routing_rule",
    "jockeying_permitted",
)

METRIC_FIELDS = (
    "schema_version",
    "study_id",
    "scenario_id",
    "input_sample_id",
    "replication_id",
    "study_cell_id",
    "layout_id",
    "traveller_count",
    "security_observation_span_seconds",
    "immigration_observation_span_seconds",
    "total_stage_observation_span_seconds",
    *REPLICATION_METRICS,
    "immutable_input_sha256",
    "pooled_replay_status",
    "crn_status",
)

CONTRAST_FIELDS = (
    "schema_version",
    "study_id",
    "study_cell_id",
    "metric",
    "difference_direction",
    "comparison_method",
    "pooled_replay_status",
    "replay_validation_scope",
    "crn_status",
    "n_scenario",
    "n_reference",
    "difference_mean",
    "standard_error",
    "degrees_of_freedom",
    "ci_level",
    "ci_low",
    "ci_high",
    "analysis_status",
)

CROSS_SCALE_FIELDS = (
    "schema_version",
    "study_id",
    "metric",
    "reference_study_cell_id",
    "illustrative_study_cell_id",
    "reference_separate_minus_pooled_mean",
    "illustrative_separate_minus_pooled_mean",
    "illustrative_minus_reference_layout_effect_mean",
    "paired_standard_error",
    "paired_degrees_of_freedom",
    "ci_level",
    "ci_low",
    "ci_high",
    "analysis_status",
    "claim_boundary",
)


def _finite_float(value: object, field: str) -> float:
    if value is None or (isinstance(value, str) and not value.strip()):
        raise ValueError(f"{field} must not be blank")
    try:
        result = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field} must be numeric") from error
    if not math.isfinite(result):
        raise ValueError(f"{field} must be finite")
    return result


def _nonnegative_float(value: object, field: str) -> float:
    result = _finite_float(value, field)
    if result < 0:
        raise ValueError(f"{field} must be nonnegative")
    return result


def _required_text(row: Mapping[str, object], field: str) -> str:
    value = str(row.get(field, "")).strip()
    if not value:
        raise ValueError(f"{field} must not be blank")
    return value


def _boolean(value: object, field: str) -> bool:
    normalized = str(value).strip().lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise ValueError(f"{field} must be true or false")


def _canonical_float(value: float) -> str:
    """Stable, lossless-enough text for cross-layout input hashing."""

    return format(value, ".17g")


@dataclass(frozen=True)
class TravellerInput:
    traveller_id: str
    arrival_seconds: float
    security_service_demand_seconds: float
    immigration_primary_service_demand_seconds: float
    additional_check_flag: bool
    additional_check_service_demand_seconds: float
    lane_tie_u: float
    logged_security_join_seconds: float
    logged_security_start_seconds: float
    logged_security_end_seconds: float
    logged_immigration_join_seconds: float
    logged_immigration_start_seconds: float
    logged_exit_seconds: float

    @property
    def immigration_service_demand_seconds(self) -> float:
        return (
            self.immigration_primary_service_demand_seconds
            + self.additional_check_service_demand_seconds
        )

    def immutable_tuple(self) -> tuple[str, ...]:
        return (
            self.traveller_id,
            _canonical_float(self.arrival_seconds),
            _canonical_float(self.security_service_demand_seconds),
            _canonical_float(
                self.immigration_primary_service_demand_seconds
            ),
            "true" if self.additional_check_flag else "false",
            _canonical_float(
                self.additional_check_service_demand_seconds
            ),
            _canonical_float(self.lane_tie_u),
        )


@dataclass(frozen=True)
class StageArrival:
    traveller_id: str
    arrival_seconds: float
    service_demand_seconds: float
    lane_tie_u: float


@dataclass(frozen=True)
class ServiceEvent:
    layout_id: str
    stage: str
    traveller_id: str
    arrival_seconds: float
    service_demand_seconds: float
    counter_index: int
    start_seconds: float
    end_seconds: float
    lane_lengths: tuple[int, ...]
    minimum_lane_length: int
    tie_candidates: tuple[int, ...]
    lane_tie_u: float | None
    tie_index: int | None
    routing_rule: str

    @property
    def counter_id(self) -> str:
        return f"{self.stage}_{self.counter_index + 1:03d}"

    @property
    def queue_wait_seconds(self) -> float:
        return self.start_seconds - self.arrival_seconds


@dataclass(frozen=True)
class LayoutReplay:
    layout_id: str
    security_events: tuple[ServiceEvent, ...]
    immigration_events: tuple[ServiceEvent, ...]
    immutable_input_sha256: str

    @property
    def events(self) -> tuple[ServiceEvent, ...]:
        return self.security_events + self.immigration_events


def load_design(path: Path = DEFAULT_DESIGN) -> dict[str, object]:
    design = json.loads(path.read_text(encoding="utf-8"))
    validate_design(design)
    return design


def validate_design(design: Mapping[str, object]) -> None:
    """Reject design drift in the frozen reference-scale replay contract."""

    if design.get("schema_version") != "1.0":
        raise ValueError("queue-layout design schema_version must be 1.0")
    if design.get("design_status") != "FROZEN_PRE_ANALYSIS":
        raise ValueError("queue-layout design must be FROZEN_PRE_ANALYSIS")
    if design.get("claim_ceiling") != (
        "CONDITIONAL_TWO_CELL_QUEUE_LAYOUT_COUNTERFACTUAL_ONLY"
    ):
        raise ValueError("queue-layout claim ceiling must cover both cells")

    source = design.get("source_ledger")
    if not isinstance(source, Mapping):
        raise ValueError("source_ledger must be an object")
    expected_source = {
        "model_version": "TASK3_OPERATIONAL_POOLED_V1",
        "scenario_id": "REFERENCE_ASSUMPTION_SANDBOX_V1",
        "input_sample_id": "LOCAL_WINDOW_HPP_BASE",
        "security_capacity": 36,
        "immigration_capacity": 21,
        "arrival_cutoff_seconds": 300.0,
        "drain_rule": "FULL_DRAIN",
    }
    for field, expected in expected_source.items():
        if source.get(field) != expected:
            raise ValueError(
                f"frozen source_ledger.{field} must be {expected!r}"
            )
    replication_ids = source.get("replication_ids")
    if replication_ids != {"first": 1, "last": 50, "count": 50}:
        raise ValueError("reference-scale study must contain replications 1..50")
    public_source = design.get("public_curated_source")
    expected_public_source = {
        "dataset_id": "QUEUE_LAYOUT_REPLAY_CURATED_SYNTHETIC_LEDGER_V1",
        "entity_ledger": (
            "data/derived/queue_layout_replay_source/entity_ledger.csv"
        ),
        "registered_p95": (
            "data/derived/queue_layout_replay_source/registered_p95.csv"
        ),
        "manifest": "data/derived/queue_layout_replay_source/manifest.json",
        "classification": "SYNTHETIC_ANYLOGIC_EVENT_LEDGER",
        "contains_video_person_data": False,
        "contains_real_person_identifiers": False,
    }
    if not isinstance(public_source, Mapping):
        raise ValueError("public_curated_source must be an object")
    for field, expected in expected_public_source.items():
        if public_source.get(field) != expected:
            raise ValueError(
                f"public_curated_source.{field} must be {expected!r}"
            )
    cells = design.get("study_cells")
    if not isinstance(cells, list) or len(cells) != 2:
        raise ValueError("queue-layout design must contain exactly two cells")
    cell_by_id = {
        str(cell.get("study_cell_id")): cell
        for cell in cells
        if isinstance(cell, Mapping)
    }
    reference_cell = cell_by_id.get("REFERENCE_SCALE")
    small_cell = cell_by_id.get("ILLUSTRATIVE_NORMALIZED_SMALL_SCALE")
    if not isinstance(reference_cell, Mapping) or not isinstance(
        small_cell, Mapping
    ):
        raise ValueError("both frozen queue-layout study cells are required")
    expected_reference_cell = {
        "arrival_time_scale": 1.0,
        "arrival_cutoff_seconds": 300.0,
        "security_capacity": 36,
        "immigration_capacity": 21,
    }
    expected_small_cell = {
        "arrival_time_scale": 5.0,
        "arrival_cutoff_seconds": 1500.0,
        "security_capacity": 6,
        "immigration_capacity": 4,
        "execution_prerequisite": (
            "REFERENCE_SCALE_POOLED_REPLAY_GATE_PASS"
        ),
        "claim_status": (
            "TRANSPARENT_ASSUMPTION_MECHANISM_ONLY_NOT_SITE_VALIDATED"
        ),
    }
    for field, expected in expected_reference_cell.items():
        if reference_cell.get(field) != expected:
            raise ValueError(
                f"REFERENCE_SCALE.{field} must be {expected!r}"
            )
    for field, expected in expected_small_cell.items():
        if small_cell.get(field) != expected:
            raise ValueError(
                "ILLUSTRATIVE_NORMALIZED_SMALL_SCALE."
                f"{field} must be {expected!r}"
            )

    layouts = design.get("layouts")
    if not isinstance(layouts, Mapping):
        raise ValueError("layouts must be an object")
    separate = layouts.get("separate_jsq")
    if not isinstance(separate, Mapping):
        raise ValueError("layouts.separate_jsq must be an object")
    required_rules = {
        "layout_id": SEPARATE,
        "assignment_epoch": "STAGE_ARRIVAL_ONLY",
        "assignment_rule": "SHORTEST_NUMBER_IN_LANE",
        "tie_draw_field": "lane_tie_u",
        "jockeying": "PROHIBITED",
    }
    for field, expected in required_rules.items():
        if separate.get(field) != expected:
            raise ValueError(f"separate_jsq.{field} must be {expected!r}")

    serial = design.get("serial_process")
    if not isinstance(serial, Mapping) or serial.get(
        "immigration_arrival_definition"
    ) != "REPLAYED_SECURITY_COMPLETION":
        raise ValueError("Immigration must receive replayed Security completions")

    gates = design.get("validation_gates")
    if not isinstance(gates, Mapping):
        raise ValueError("validation_gates must be an object")
    paired = gates.get("paired_inference")
    if not isinstance(paired, Mapping) or paired.get(
        "failure_action"
    ) != "DO_NOT_COMPUTE_OR_WRITE_PAIRED_CONTRASTS":
        raise ValueError("paired inference must fail closed")


def parse_traveller_rows(
    rows: Iterable[Mapping[str, object]],
) -> list[TravellerInput]:
    """Parse and chronology-check one replication's entity ledger."""

    travellers: list[TravellerInput] = []
    seen: set[str] = set()
    for line, row in enumerate(rows, start=2):
        traveller_id = _required_text(row, "traveller_id")
        if traveller_id in seen:
            raise ValueError(f"duplicate traveller_id {traveller_id!r}")
        seen.add(traveller_id)

        arrival = _nonnegative_float(row.get("arrival_seconds"), "arrival_seconds")
        security_demand = _nonnegative_float(
            row.get("security_service_demand_seconds"),
            "security_service_demand_seconds",
        )
        primary = _nonnegative_float(
            row.get("immigration_primary_service_demand_seconds"),
            "immigration_primary_service_demand_seconds",
        )
        additional_flag = _boolean(
            row.get("additional_check_flag"), "additional_check_flag"
        )
        additional_raw = row.get("additional_check_service_demand_seconds")
        if additional_flag:
            additional = _nonnegative_float(
                additional_raw, "additional_check_service_demand_seconds"
            )
        else:
            if additional_raw is not None and str(additional_raw).strip():
                additional = _nonnegative_float(
                    additional_raw,
                    "additional_check_service_demand_seconds",
                )
                if additional > REPLAY_EPSILON:
                    raise ValueError(
                        f"line {line}: unselected additional check has "
                        "positive service demand"
                    )
            additional = 0.0

        lane_tie_u = _finite_float(row.get("lane_tie_u"), "lane_tie_u")
        if not 0.0 <= lane_tie_u <= 1.0:
            raise ValueError("lane_tie_u must be in [0, 1]")

        logged_security_join = _finite_float(
            row.get("security_queue_join_seconds"),
            "security_queue_join_seconds",
        )
        logged_security_start = _finite_float(
            row.get("security_start_seconds"), "security_start_seconds"
        )
        logged_security_end = _finite_float(
            row.get("security_end_seconds"), "security_end_seconds"
        )
        logged_immigration_join = _finite_float(
            row.get("immigration_queue_join_seconds"),
            "immigration_queue_join_seconds",
        )
        logged_immigration_start = _finite_float(
            row.get("immigration_start_seconds"),
            "immigration_start_seconds",
        )
        logged_exit = _finite_float(row.get("exit_seconds"), "exit_seconds")
        if not (
            arrival
            <= logged_security_join
            <= logged_security_start
            <= logged_security_end
            <= logged_immigration_join + REPLAY_EPSILON
            and logged_immigration_join
            <= logged_immigration_start
            <= logged_exit
        ):
            raise ValueError(
                f"line {line}: illegal serial event chronology for "
                f"{traveller_id}"
            )
        if abs(logged_security_end - logged_immigration_join) > 1e-6:
            raise ValueError(
                f"line {line}: Security completion must equal Immigration join"
            )
        if abs(arrival - logged_security_join) > 1e-6:
            raise ValueError(
                f"line {line}: arrival must equal Security queue join"
            )

        travellers.append(
            TravellerInput(
                traveller_id=traveller_id,
                arrival_seconds=arrival,
                security_service_demand_seconds=security_demand,
                immigration_primary_service_demand_seconds=primary,
                additional_check_flag=additional_flag,
                additional_check_service_demand_seconds=additional,
                lane_tie_u=lane_tie_u,
                logged_security_join_seconds=logged_security_join,
                logged_security_start_seconds=logged_security_start,
                logged_security_end_seconds=logged_security_end,
                logged_immigration_join_seconds=logged_immigration_join,
                logged_immigration_start_seconds=logged_immigration_start,
                logged_exit_seconds=logged_exit,
            )
        )
    if not travellers:
        raise ValueError("entity ledger replication is empty")
    travellers.sort(key=lambda item: (item.arrival_seconds, item.traveller_id))
    return travellers


def immutable_input_sha256(travellers: Sequence[TravellerInput]) -> str:
    canonical_rows = [
        "\x1f".join(traveller.immutable_tuple())
        for traveller in sorted(travellers, key=lambda item: item.traveller_id)
    ]
    payload = ("\n".join(canonical_rows) + "\n").encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _ordered_arrivals(
    arrivals: Iterable[StageArrival],
) -> list[StageArrival]:
    ordered = sorted(
        arrivals, key=lambda item: (item.arrival_seconds, item.traveller_id)
    )
    ids = [item.traveller_id for item in ordered]
    if len(ids) != len(set(ids)):
        raise ValueError("stage arrivals contain duplicate traveller IDs")
    return ordered


def replay_pooled_stage(
    arrivals: Iterable[StageArrival],
    *,
    capacity: int,
    stage: str,
) -> tuple[ServiceEvent, ...]:
    """Exact deterministic FCFS replay for one common queue."""

    if stage not in STAGES:
        raise ValueError(f"unsupported stage {stage!r}")
    if capacity < 1:
        raise ValueError("capacity must be positive")
    available = [0.0] * capacity
    events: list[ServiceEvent] = []
    for item in _ordered_arrivals(arrivals):
        earliest = min(available)
        candidates = tuple(
            index
            for index, timestamp in enumerate(available)
            if abs(timestamp - earliest) <= REPLAY_EPSILON
        )
        counter = candidates[0]
        start = max(item.arrival_seconds, available[counter])
        end = start + item.service_demand_seconds
        common_waiting = sum(
            event.arrival_seconds <= item.arrival_seconds < event.start_seconds
            for event in events
        )
        available[counter] = end
        events.append(
            ServiceEvent(
                layout_id=POOLED,
                stage=stage,
                traveller_id=item.traveller_id,
                arrival_seconds=item.arrival_seconds,
                service_demand_seconds=item.service_demand_seconds,
                counter_index=counter,
                start_seconds=start,
                end_seconds=end,
                lane_lengths=(common_waiting,),
                minimum_lane_length=common_waiting,
                tie_candidates=candidates,
                lane_tie_u=None,
                tie_index=None,
                routing_rule="FCFS_EARLIEST_AVAILABLE_THEN_LOWEST_COUNTER_ID",
            )
        )
    return tuple(events)


def _tie_index(tie_u: float, candidate_count: int) -> int:
    if candidate_count < 1:
        raise ValueError("tie candidate set must not be empty")
    # lane_tie_u is specified on [0, 1], so the clamp handles the rare exact 1.
    return min(int(math.floor(tie_u * candidate_count)), candidate_count - 1)


def replay_separate_stage(
    arrivals: Iterable[StageArrival],
    *,
    capacity: int,
    stage: str,
) -> tuple[ServiceEvent, ...]:
    """Replay one queue per counter with join-shortest-once routing."""

    if stage not in STAGES:
        raise ValueError(f"unsupported stage {stage!r}")
    if capacity < 1:
        raise ValueError("capacity must be positive")
    available = [0.0] * capacity
    lane_events: list[list[ServiceEvent]] = [[] for _ in range(capacity)]
    events: list[ServiceEvent] = []

    for item in _ordered_arrivals(arrivals):
        # Number already in each line, including at most one in service.
        # Completed customers have departed before an arrival at the same time.
        lane_lengths = tuple(
            sum(
                previous.end_seconds > item.arrival_seconds
                for previous in lane
            )
            for lane in lane_events
        )
        minimum = min(lane_lengths)
        candidates = tuple(
            index
            for index, lane_length in enumerate(lane_lengths)
            if lane_length == minimum
        )
        tie_index = _tie_index(item.lane_tie_u, len(candidates))
        counter = candidates[tie_index]
        start = max(item.arrival_seconds, available[counter])
        end = start + item.service_demand_seconds
        event = ServiceEvent(
            layout_id=SEPARATE,
            stage=stage,
            traveller_id=item.traveller_id,
            arrival_seconds=item.arrival_seconds,
            service_demand_seconds=item.service_demand_seconds,
            counter_index=counter,
            start_seconds=start,
            end_seconds=end,
            lane_lengths=lane_lengths,
            minimum_lane_length=minimum,
            tie_candidates=candidates,
            lane_tie_u=item.lane_tie_u,
            tie_index=tie_index,
            routing_rule="SHORTEST_NUMBER_IN_LANE_AT_ARRIVAL",
        )
        lane_events[counter].append(event)
        events.append(event)
        available[counter] = end
    return tuple(events)


def replay_layout(
    travellers: Sequence[TravellerInput],
    *,
    layout_id: str,
    security_capacity: int,
    immigration_capacity: int,
) -> LayoutReplay:
    """Replay both serial stages under exactly one queue layout."""

    security_arrivals = [
        StageArrival(
            traveller_id=item.traveller_id,
            arrival_seconds=item.arrival_seconds,
            service_demand_seconds=item.security_service_demand_seconds,
            lane_tie_u=item.lane_tie_u,
        )
        for item in travellers
    ]
    stage_replayer = (
        replay_pooled_stage if layout_id == POOLED else replay_separate_stage
    )
    if layout_id not in LAYOUTS:
        raise ValueError(f"unsupported layout {layout_id!r}")
    security_events = stage_replayer(
        security_arrivals, capacity=security_capacity, stage=SECURITY
    )
    security_by_id = {event.traveller_id: event for event in security_events}

    immigration_arrivals = [
        StageArrival(
            traveller_id=item.traveller_id,
            arrival_seconds=security_by_id[item.traveller_id].end_seconds,
            service_demand_seconds=item.immigration_service_demand_seconds,
            lane_tie_u=item.lane_tie_u,
        )
        for item in travellers
    ]
    immigration_events = stage_replayer(
        immigration_arrivals,
        capacity=immigration_capacity,
        stage=IMMIGRATION,
    )
    return LayoutReplay(
        layout_id=layout_id,
        security_events=security_events,
        immigration_events=immigration_events,
        immutable_input_sha256=immutable_input_sha256(travellers),
    )


def validate_pooled_replay(
    travellers: Sequence[TravellerInput],
    replay: LayoutReplay,
    *,
    tolerance_seconds: float,
    logged_total_queue_wait_p95_seconds: float | None = None,
) -> dict[str, object]:
    """Compare pooled replay to all corresponding AnyLogic timestamps."""

    if replay.layout_id != POOLED:
        raise ValueError("pooled replay validation requires POOLED_FCFS")
    if tolerance_seconds < 0 or not math.isfinite(tolerance_seconds):
        raise ValueError("tolerance_seconds must be finite and nonnegative")

    security = {event.traveller_id: event for event in replay.security_events}
    immigration = {
        event.traveller_id: event for event in replay.immigration_events
    }
    comparisons: list[tuple[str, str, float, float]] = []
    for item in travellers:
        sec = security[item.traveller_id]
        imm = immigration[item.traveller_id]
        comparisons.extend(
            [
                (
                    item.traveller_id,
                    "security_queue_join_seconds",
                    sec.arrival_seconds,
                    item.logged_security_join_seconds,
                ),
                (
                    item.traveller_id,
                    "security_start_seconds",
                    sec.start_seconds,
                    item.logged_security_start_seconds,
                ),
                (
                    item.traveller_id,
                    "security_end_seconds",
                    sec.end_seconds,
                    item.logged_security_end_seconds,
                ),
                (
                    item.traveller_id,
                    "immigration_queue_join_seconds",
                    imm.arrival_seconds,
                    item.logged_immigration_join_seconds,
                ),
                (
                    item.traveller_id,
                    "immigration_start_seconds",
                    imm.start_seconds,
                    item.logged_immigration_start_seconds,
                ),
                (
                    item.traveller_id,
                    "exit_seconds",
                    imm.end_seconds,
                    item.logged_exit_seconds,
                ),
                (
                    item.traveller_id,
                    "derived_security_wait_seconds",
                    sec.queue_wait_seconds,
                    (
                        item.logged_security_start_seconds
                        - item.logged_security_join_seconds
                    ),
                ),
                (
                    item.traveller_id,
                    "derived_immigration_wait_seconds",
                    imm.queue_wait_seconds,
                    (
                        item.logged_immigration_start_seconds
                        - item.logged_immigration_join_seconds
                    ),
                ),
            ]
        )

    mismatches = []
    max_error = 0.0
    for traveller_id, field, replayed, logged in comparisons:
        error = abs(replayed - logged)
        max_error = max(max_error, error)
        if error > tolerance_seconds:
            mismatches.append(
                {
                    "traveller_id": traveller_id,
                    "field": field,
                    "replayed_seconds": replayed,
                    "logged_seconds": logged,
                    "absolute_error_seconds": error,
                }
            )
    replayed_total_wait_p95 = nearest_rank_p95(
        [
            security[item.traveller_id].queue_wait_seconds
            + immigration[item.traveller_id].queue_wait_seconds
            for item in travellers
        ]
    )
    kpi_comparison_count = 0
    if logged_total_queue_wait_p95_seconds is not None:
        logged_p95 = _nonnegative_float(
            logged_total_queue_wait_p95_seconds,
            "replication_kpis.total_queue_wait_p95_seconds",
        )
        kpi_comparison_count = 1
        error = abs(replayed_total_wait_p95 - logged_p95)
        max_error = max(max_error, error)
        if error > tolerance_seconds:
            mismatches.append(
                {
                    "traveller_id": "",
                    "field": (
                        "replication_kpis.total_queue_wait_p95_seconds"
                    ),
                    "replayed_seconds": replayed_total_wait_p95,
                    "logged_seconds": logged_p95,
                    "absolute_error_seconds": error,
                }
            )
    return {
        "gate_id": "POOLED_REPLAY_GATE_V1",
        "status": "PASS" if not mismatches else "FAIL",
        "tolerance_seconds": tolerance_seconds,
        "traveller_count": len(travellers),
        "timestamp_comparison_count": len(comparisons),
        "replication_kpi_comparison_count": kpi_comparison_count,
        "replayed_total_queue_wait_p95_seconds": replayed_total_wait_p95,
        "mismatch_count": len(mismatches),
        "maximum_absolute_error_seconds": max_error,
        "mismatches": mismatches,
        "claim_boundary": (
            "PASS establishes timestamp-level equivalence for this replay "
            "input only; it is not site validation."
        ),
    }


def validate_layout_crn(
    travellers: Sequence[TravellerInput],
    pooled: LayoutReplay,
    separate: LayoutReplay,
) -> dict[str, object]:
    """Prove identical traveller population and immutable inputs."""

    source_ids = {item.traveller_id for item in travellers}
    pooled_ids = {event.traveller_id for event in pooled.security_events}
    separate_ids = {event.traveller_id for event in separate.security_events}
    source_hash = immutable_input_sha256(travellers)
    checks = {
        "traveller_sets_identical": (
            source_ids == pooled_ids == separate_ids
        ),
        "pooled_input_hash_matches_source": (
            pooled.immutable_input_sha256 == source_hash
        ),
        "separate_input_hash_matches_source": (
            separate.immutable_input_sha256 == source_hash
        ),
        "security_to_immigration_conservation": (
            {event.traveller_id for event in pooled.immigration_events}
            == source_ids
            and {event.traveller_id for event in separate.immigration_events}
            == source_ids
        ),
    }
    return {
        "gate_id": "QUEUE_LAYOUT_CRN_GATE_V1",
        "status": "PASS" if all(checks.values()) else "FAIL",
        **checks,
        "traveller_count": len(travellers),
        "immutable_input_sha256": source_hash,
        "immutable_fields": [
            "traveller_id",
            "arrival_seconds",
            "security_service_demand_seconds",
            "immigration_primary_service_demand_seconds",
            "additional_check_flag",
            "additional_check_service_demand_seconds",
            "lane_tie_u",
        ],
    }


def nearest_rank_quantile(
    values: Sequence[float], probability: float
) -> float:
    """Return the registered nearest-rank empirical quantile.

    The zero-based index is ``ceil(probability * n) - 1``.  This is the same
    rule used by the AnyLogic KPI writer, so replay validation and the layout
    contrast target the registered within-replication P95 definition.
    """
    if not values:
        raise ValueError("quantile requires at least one value")
    if not 0 < probability <= 1:
        raise ValueError("probability must be in (0, 1]")
    ordered = sorted(_finite_float(value, "quantile value") for value in values)
    index = max(0, math.ceil(probability * len(ordered)) - 1)
    return ordered[index]


def nearest_rank_p95(values: Sequence[float]) -> float:
    return nearest_rank_quantile(values, 0.95)


def _peak_waiting(
    event_groups: Sequence[Sequence[ServiceEvent]],
) -> tuple[int, tuple[int, ...]]:
    """Peak total waiting and peak waiting in each assigned lane."""

    if not event_groups:
        return 0, ()
    lane_count = max(
        (event.counter_index for group in event_groups for event in group),
        default=-1,
    ) + 1
    deltas: dict[float, list[tuple[int, int]]] = defaultdict(list)
    for group in event_groups:
        for event in group:
            if event.start_seconds <= event.arrival_seconds:
                continue
            deltas[event.arrival_seconds].append((event.counter_index, 1))
            deltas[event.start_seconds].append((event.counter_index, -1))
    current = [0] * lane_count
    peak_by_lane = [0] * lane_count
    peak_total = 0
    for timestamp in sorted(deltas):
        # Half-open intervals: waiting ends are applied before new waits start.
        for counter, delta in sorted(
            deltas[timestamp], key=lambda item: item[1]
        ):
            current[counter] += delta
            if current[counter] < 0:
                raise AssertionError("waiting sweep became negative")
        peak_total = max(peak_total, sum(current))
        for counter, count in enumerate(current):
            peak_by_lane[counter] = max(peak_by_lane[counter], count)
    return peak_total, tuple(peak_by_lane)


def fragmentation_seconds(
    events: Sequence[ServiceEvent], *, capacity: int
) -> float:
    """Integrate avoidable lane fragmentation for counter-specific queues."""

    if capacity < 1:
        raise ValueError("capacity must be positive")
    if not events:
        return 0.0
    if any(event.layout_id == POOLED for event in events):
        # A common FCFS queue has no lane-specific fragmentation by definition.
        return 0.0

    # At each time, deltas are (kind, counter, amount).  Duration is integrated
    # before applying all co-timed deltas, so point ordering cannot add measure.
    deltas: dict[float, list[tuple[str, int, int]]] = defaultdict(list)
    for event in events:
        deltas[event.start_seconds].append(("busy", event.counter_index, 1))
        deltas[event.end_seconds].append(("busy", event.counter_index, -1))
        if event.start_seconds > event.arrival_seconds:
            deltas[event.arrival_seconds].append(
                ("waiting", event.counter_index, 1)
            )
            deltas[event.start_seconds].append(
                ("waiting", event.counter_index, -1)
            )

    busy = [0] * capacity
    waiting = [0] * capacity
    previous = min(deltas)
    fragmented = 0.0
    for timestamp in sorted(deltas):
        duration = timestamp - previous
        if duration < -REPLAY_EPSILON:
            raise AssertionError("event sweep is not ordered")
        predicate = any(
            busy[idle_counter] == 0
            and any(
                waiting[queued_counter] > 0
                for queued_counter in range(capacity)
                if queued_counter != idle_counter
            )
            for idle_counter in range(capacity)
        )
        if predicate:
            fragmented += max(0.0, duration)
        for kind, counter, amount in sorted(
            deltas[timestamp], key=lambda item: item[2]
        ):
            target = busy if kind == "busy" else waiting
            target[counter] += amount
            if target[counter] < 0:
                raise AssertionError(f"{kind} sweep became negative")
            if kind == "busy" and target[counter] > 1:
                raise AssertionError("counter serves more than one traveller")
        previous = timestamp
    return fragmented


def stage_observation_span_seconds(events: Sequence[ServiceEvent]) -> float:
    """Stage-specific first-arrival through final-completion denominator."""

    if not events:
        return 0.0
    first_arrival = min(event.arrival_seconds for event in events)
    final_completion = max(event.end_seconds for event in events)
    span = final_completion - first_arrival
    if span < -REPLAY_EPSILON:
        raise AssertionError("stage observation span is negative")
    return max(0.0, span)


def _safe_fraction(numerator: float, denominator: float) -> float:
    if denominator == 0:
        if numerator == 0:
            return 0.0
        raise ValueError("positive fragmentation has zero observation span")
    return numerator / denominator


def replication_metrics(
    replay: LayoutReplay,
    *,
    security_capacity: int,
    immigration_capacity: int,
) -> dict[str, float | int | str]:
    security = {event.traveller_id: event for event in replay.security_events}
    immigration = {
        event.traveller_id: event for event in replay.immigration_events
    }
    if set(security) != set(immigration):
        raise ValueError("stage traveller sets differ")
    total_waits = [
        security[traveller_id].queue_wait_seconds
        + immigration[traveller_id].queue_wait_seconds
        for traveller_id in security
    ]
    peak_security, peak_security_lanes = _peak_waiting(
        [replay.security_events]
    )
    peak_immigration, peak_immigration_lanes = _peak_waiting(
        [replay.immigration_events]
    )
    peak_total, _ = _peak_waiting(
        [replay.security_events, replay.immigration_events]
    )
    security_fragmentation = fragmentation_seconds(
        replay.security_events, capacity=security_capacity
    )
    immigration_fragmentation = fragmentation_seconds(
        replay.immigration_events, capacity=immigration_capacity
    )
    security_span = stage_observation_span_seconds(replay.security_events)
    immigration_span = stage_observation_span_seconds(
        replay.immigration_events
    )
    total_stage_span = security_span + immigration_span
    total_fragmentation = (
        security_fragmentation + immigration_fragmentation
    )
    return {
        "traveller_count": len(security),
        "security_observation_span_seconds": security_span,
        "immigration_observation_span_seconds": immigration_span,
        "total_stage_observation_span_seconds": total_stage_span,
        "total_queue_wait_p95_seconds": nearest_rank_p95(total_waits),
        "peak_security_waiting_queue": peak_security,
        "peak_immigration_waiting_queue": peak_immigration,
        "peak_total_waiting_queue": peak_total,
        "peak_security_lane_waiting_queue": max(
            peak_security_lanes, default=0
        ),
        "peak_immigration_lane_waiting_queue": max(
            peak_immigration_lanes, default=0
        ),
        "security_fragmentation_seconds": security_fragmentation,
        "immigration_fragmentation_seconds": immigration_fragmentation,
        "total_fragmentation_seconds": total_fragmentation,
        "security_fragmentation_fraction": _safe_fraction(
            security_fragmentation, security_span
        ),
        "immigration_fragmentation_fraction": _safe_fraction(
            immigration_fragmentation, immigration_span
        ),
        "total_fragmentation_fraction": _safe_fraction(
            total_fragmentation, total_stage_span
        ),
        "immutable_input_sha256": replay.immutable_input_sha256,
    }


def replay_one_replication(
    rows: Iterable[Mapping[str, object]],
    *,
    security_capacity: int,
    immigration_capacity: int,
    tolerance_seconds: float,
    logged_total_queue_wait_p95_seconds: float | None = None,
) -> dict[str, object]:
    """Run both layouts and both validation gates for one replication."""

    travellers = parse_traveller_rows(rows)
    pooled = replay_layout(
        travellers,
        layout_id=POOLED,
        security_capacity=security_capacity,
        immigration_capacity=immigration_capacity,
    )
    separate = replay_layout(
        travellers,
        layout_id=SEPARATE,
        security_capacity=security_capacity,
        immigration_capacity=immigration_capacity,
    )
    pooled_gate = validate_pooled_replay(
        travellers,
        pooled,
        tolerance_seconds=tolerance_seconds,
        logged_total_queue_wait_p95_seconds=(
            logged_total_queue_wait_p95_seconds
        ),
    )
    crn_gate = validate_layout_crn(travellers, pooled, separate)
    return {
        "travellers": travellers,
        "pooled": pooled,
        "separate": separate,
        "pooled_gate": pooled_gate,
        "crn_gate": crn_gate,
        "pooled_metrics": replication_metrics(
            pooled,
            security_capacity=security_capacity,
            immigration_capacity=immigration_capacity,
        ),
        "separate_metrics": replication_metrics(
            separate,
            security_capacity=security_capacity,
            immigration_capacity=immigration_capacity,
        ),
    }


def scale_traveller_arrivals(
    travellers: Sequence[TravellerInput], *, arrival_time_scale: float
) -> list[TravellerInput]:
    """Create the transparent small-scale input without changing work draws."""

    scale = _finite_float(arrival_time_scale, "arrival_time_scale")
    if scale <= 0:
        raise ValueError("arrival_time_scale must be positive")
    return [
        replace(
            traveller,
            arrival_seconds=traveller.arrival_seconds * scale,
        )
        for traveller in travellers
    ]


def replay_mechanism_cell(
    travellers: Sequence[TravellerInput],
    *,
    security_capacity: int,
    immigration_capacity: int,
) -> dict[str, object]:
    """Replay a transformed mechanism-only cell after reference validation."""

    pooled = replay_layout(
        travellers,
        layout_id=POOLED,
        security_capacity=security_capacity,
        immigration_capacity=immigration_capacity,
    )
    separate = replay_layout(
        travellers,
        layout_id=SEPARATE,
        security_capacity=security_capacity,
        immigration_capacity=immigration_capacity,
    )
    crn_gate = validate_layout_crn(travellers, pooled, separate)
    return {
        "travellers": travellers,
        "pooled": pooled,
        "separate": separate,
        "crn_gate": crn_gate,
        "pooled_metrics": replication_metrics(
            pooled,
            security_capacity=security_capacity,
            immigration_capacity=immigration_capacity,
        ),
        "separate_metrics": replication_metrics(
            separate,
            security_capacity=security_capacity,
            immigration_capacity=immigration_capacity,
        ),
    }


def build_paired_contrasts(
    metric_rows: Sequence[Mapping[str, object]],
    *,
    pooled_gate_status: str,
    crn_gate_status: str,
    expected_replication_ids: set[int],
    ci_level: float,
    study_id: str,
    study_cell_id: str = "REFERENCE_SCALE",
    replay_validation_scope: str = "EXACT_ANYLOGIC_REFERENCE",
    reported_pooled_replay_status: str | None = None,
) -> list[dict[str, object]]:
    """Compute paired CIs only after both exactness gates pass."""

    if pooled_gate_status != "PASS" or crn_gate_status != "PASS":
        raise ValueError(
            "paired contrasts are blocked until pooled replay and CRN gates PASS"
        )
    observed = {
        int(row["replication_id"])
        for row in metric_rows
        if row["layout_id"] == POOLED
    }
    if observed != expected_replication_ids:
        raise ValueError(
            "paired contrasts require the exact frozen replication set"
        )

    contrasts: list[dict[str, object]] = []
    for metric in REPLICATION_METRICS:
        pooled_by_replication = {
            str(row["replication_id"]): float(row[metric])
            for row in metric_rows
            if row["layout_id"] == POOLED
        }
        separate_by_replication = {
            str(row["replication_id"]): float(row[metric])
            for row in metric_rows
            if row["layout_id"] == SEPARATE
        }
        comparison = paired_difference(
            separate_by_replication,
            pooled_by_replication,
            ci_level=ci_level,
        )
        contrasts.append(
            {
                "schema_version": ANALYSIS_SCHEMA_VERSION,
                "study_id": study_id,
                "study_cell_id": study_cell_id,
                "metric": metric,
                "difference_direction": "SEPARATE_MINUS_POOLED",
                "comparison_method": "PAIRED_STUDENT_T",
                "pooled_replay_status": (
                    reported_pooled_replay_status or pooled_gate_status
                ),
                "replay_validation_scope": replay_validation_scope,
                "crn_status": crn_gate_status,
                **comparison,
                "ci_level": ci_level,
                "analysis_status": "COMPLETE_CONDITIONAL_COUNTERFACTUAL",
            }
        )
    return contrasts


def build_cross_scale_summary(
    metric_rows: Sequence[Mapping[str, object]],
    *,
    expected_replication_ids: set[int],
    ci_level: float,
    study_id: str,
) -> list[dict[str, object]]:
    """Describe how the paired layout effect changes across frozen scales."""

    summary: list[dict[str, object]] = []
    for metric in CROSS_SCALE_METRICS:
        effects: dict[str, dict[str, float]] = {}
        for cell_id in (
            "REFERENCE_SCALE",
            "ILLUSTRATIVE_NORMALIZED_SMALL_SCALE",
        ):
            by_layout = {
                layout_id: {
                    str(row["replication_id"]): float(row[metric])
                    for row in metric_rows
                    if row["study_cell_id"] == cell_id
                    and row["layout_id"] == layout_id
                }
                for layout_id in LAYOUTS
            }
            if (
                {int(key) for key in by_layout[POOLED]}
                != expected_replication_ids
                or set(by_layout[POOLED]) != set(by_layout[SEPARATE])
            ):
                raise ValueError(
                    f"{cell_id} lacks the exact cross-scale replication set"
                )
            effects[cell_id] = {
                key: by_layout[SEPARATE][key] - by_layout[POOLED][key]
                for key in by_layout[POOLED]
            }
        reference = effects["REFERENCE_SCALE"]
        illustrative = effects["ILLUSTRATIVE_NORMALIZED_SMALL_SCALE"]
        comparison = paired_difference(
            illustrative, reference, ci_level=ci_level
        )
        summary.append(
            {
                "schema_version": ANALYSIS_SCHEMA_VERSION,
                "study_id": study_id,
                "metric": metric,
                "reference_study_cell_id": "REFERENCE_SCALE",
                "illustrative_study_cell_id": (
                    "ILLUSTRATIVE_NORMALIZED_SMALL_SCALE"
                ),
                "reference_separate_minus_pooled_mean": statistics.fmean(
                    reference.values()
                ),
                "illustrative_separate_minus_pooled_mean": statistics.fmean(
                    illustrative.values()
                ),
                "illustrative_minus_reference_layout_effect_mean": (
                    comparison["difference_mean"]
                ),
                "paired_standard_error": comparison["standard_error"],
                "paired_degrees_of_freedom": comparison[
                    "degrees_of_freedom"
                ],
                "ci_level": ci_level,
                "ci_low": comparison["ci_low"],
                "ci_high": comparison["ci_high"],
                "analysis_status": "DESCRIPTIVE_CROSS_SCALE_MECHANISM",
                "claim_boundary": (
                    "Illustrative normalized scale is a transparent "
                    "assumption probe, not AnyLogic or site validation."
                ),
            }
        )
    return summary


def _event_row(
    event: ServiceEvent,
    *,
    study_id: str,
    scenario_id: str,
    input_sample_id: str,
    replication_id: int,
    study_cell_id: str,
) -> dict[str, object]:
    return {
        "schema_version": ANALYSIS_SCHEMA_VERSION,
        "study_id": study_id,
        "scenario_id": scenario_id,
        "input_sample_id": input_sample_id,
        "replication_id": replication_id,
        "study_cell_id": study_cell_id,
        "layout_id": event.layout_id,
        "stage": event.stage,
        "traveller_id": event.traveller_id,
        "stage_arrival_seconds": event.arrival_seconds,
        "service_demand_seconds": event.service_demand_seconds,
        "counter_id": event.counter_id,
        "service_start_seconds": event.start_seconds,
        "service_end_seconds": event.end_seconds,
        "queue_wait_seconds": event.queue_wait_seconds,
        "lane_length_snapshot": ";".join(
            f"{index + 1}:{count}"
            for index, count in enumerate(event.lane_lengths)
        ),
        "minimum_lane_length": event.minimum_lane_length,
        "tie_candidate_counter_ids": ";".join(
            f"{event.stage}_{index + 1:03d}"
            for index in event.tie_candidates
        ),
        "tie_candidate_count": len(event.tie_candidates),
        "lane_tie_u": "" if event.lane_tie_u is None else event.lane_tie_u,
        "tie_index": "" if event.tie_index is None else event.tie_index,
        "routing_rule": event.routing_rule,
        "jockeying_permitted": "false",
    }


def _write_csv(
    path: Path,
    rows: Sequence[Mapping[str, object]],
    fieldnames: Sequence[str],
) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fieldnames,
            extrasaction="raise",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def _write_json(path: Path, payload: Mapping[str, object]) -> None:
    """Write repository evidence with stable LF endings on every platform."""

    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(payload, indent=2, sort_keys=True))
        handle.write("\n")


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError(f"{path} has no header")
        return list(reader)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _portable_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return resolved.as_posix()


def counter_event_audit_digest(
    event_rows: Sequence[Mapping[str, object]],
    *,
    event_log_path: Path,
    study_id: str,
) -> dict[str, object]:
    """Compact public evidence for the local-only counter-event ledger."""

    grouped: dict[tuple[str, str, str], dict[str, object]] = {}
    for row in event_rows:
        key = (
            str(row["study_cell_id"]),
            str(row["layout_id"]),
            str(row["stage"]),
        )
        summary = grouped.setdefault(
            key,
            {
                "row_count": 0,
                "positive_wait_count": 0,
                "maximum_wait_seconds": 0.0,
                "counter_ids": set(),
                "replication_ids": set(),
            },
        )
        summary["row_count"] = int(summary["row_count"]) + 1
        wait = float(row["queue_wait_seconds"])
        if wait > 0:
            summary["positive_wait_count"] = (
                int(summary["positive_wait_count"]) + 1
            )
        summary["maximum_wait_seconds"] = max(
            float(summary["maximum_wait_seconds"]), wait
        )
        summary["counter_ids"].add(str(row["counter_id"]))
        summary["replication_ids"].add(int(row["replication_id"]))

    by_cell_layout_stage = {}
    for key, summary in sorted(grouped.items()):
        cell_id, layout_id, stage = key
        by_cell_layout_stage[f"{cell_id}|{layout_id}|{stage}"] = {
            "row_count": summary["row_count"],
            "positive_wait_count": summary["positive_wait_count"],
            "maximum_wait_seconds": summary["maximum_wait_seconds"],
            "counter_count_observed": len(summary["counter_ids"]),
            "replication_count": len(summary["replication_ids"]),
        }
    return {
        "schema_version": ANALYSIS_SCHEMA_VERSION,
        "study_id": study_id,
        "status": "PASS",
        "counter_event_log": _portable_path(event_log_path),
        "counter_event_log_publication_status": "LOCAL_INTERMEDIATE_ONLY",
        "counter_event_log_sha256": _file_sha256(event_log_path),
        "counter_event_row_count": len(event_rows),
        "by_study_cell_layout_stage": by_cell_layout_stage,
        "claim_boundary": (
            "This digest proves the local counter-event artifact identity and "
            "basic coverage; it is not a substitute for the gated replay."
        ),
    }


def package_queue_layout_replay(
    *,
    entity_log_path: Path,
    replication_kpis_path: Path,
    output_dir: Path,
    design_path: Path = DEFAULT_DESIGN,
    event_log_path: Path = DEFAULT_LOCAL_EVENT_LOG,
    source_manifest_path: Path | None = None,
) -> dict[str, object]:
    """Execute the frozen study and write a fail-closed audit package."""

    design = load_design(design_path)
    source_manifest: dict[str, object] | None = None
    if source_manifest_path is not None:
        source_manifest = audit_curated_package(
            entity_path=entity_log_path,
            kpi_path=replication_kpis_path,
            manifest_path=source_manifest_path,
        )
    source = design["source_ledger"]
    assert isinstance(source, Mapping)
    rows = _read_csv(entity_log_path)
    kpi_rows = _read_csv(replication_kpis_path)

    scenario_id = str(source["scenario_id"])
    input_sample_id = str(source["input_sample_id"])
    if source_manifest is not None:
        provenance = source_manifest.get("provenance")
        if not isinstance(provenance, Mapping):
            raise ValueError("curated source manifest provenance is missing")
        expected_provenance = {
            "model_version": source["model_version"],
            "config_id": source["config_id"],
            "config_sha256": source["config_sha256"],
            "scenario_id": scenario_id,
            "input_sample_id": input_sample_id,
            "replication_first": source["replication_ids"]["first"],
            "replication_last": source["replication_ids"]["last"],
            "replication_count": source["replication_ids"]["count"],
        }
        for field, expected in expected_provenance.items():
            if provenance.get(field) != expected:
                raise ValueError(
                    f"curated source provenance {field} differs from design"
                )
        selected = rows
    else:
        selected = [
            row
            for row in rows
            if row.get("scenario_id") == scenario_id
            and row.get("input_sample_id") == input_sample_id
        ]
    if not selected:
        raise ValueError("source ledger has no rows for the frozen study cell")

    if source_manifest is None:
        metadata_fields = ("model_version", "config_id", "config_sha256")
        for field in metadata_fields:
            expected = str(source[field])
            unexpected = sorted(
                {
                    row.get(field, "")
                    for row in selected
                    if row.get(field) != expected
                }
            )
            if unexpected:
                raise ValueError(
                    "source ledger "
                    f"{field} differs from frozen design: {unexpected}"
                )

    first = int(source["replication_ids"]["first"])
    last = int(source["replication_ids"]["last"])
    expected_replications = set(range(first, last + 1))
    grouped: dict[int, list[dict[str, str]]] = defaultdict(list)
    for row in selected:
        replication_id = int(_required_text(row, "replication_id"))
        grouped[replication_id].append(row)
    if set(grouped) != expected_replications:
        raise ValueError(
            "source ledger does not contain exactly the frozen replications"
        )
    if source_manifest is not None:
        selected_kpis = kpi_rows
    else:
        selected_kpis = [
            row
            for row in kpi_rows
            if row.get("scenario_id") == scenario_id
            and row.get("input_sample_id") == input_sample_id
        ]
    kpi_by_replication: dict[int, dict[str, str]] = {}
    for row in selected_kpis:
        replication_id = int(_required_text(row, "replication_id"))
        if replication_id in kpi_by_replication:
            raise ValueError(
                f"replication_kpis has duplicate replication {replication_id}"
            )
        kpi_by_replication[replication_id] = row
    if set(kpi_by_replication) != expected_replications:
        raise ValueError(
            "replication_kpis does not contain exactly the frozen replications"
        )
    for row in selected_kpis:
        if source_manifest is None:
            if row.get("config_id") != str(source["config_id"]):
                raise ValueError("replication_kpis config_id differs from design")
            if row.get("config_sha256") != str(source["config_sha256"]):
                raise ValueError(
                    "replication_kpis config_sha256 differs from design"
                )
            if row.get("model_version") != str(source["model_version"]):
                raise ValueError(
                    "replication_kpis model_version differs from design"
                )
        if row.get("run_status") != str(source["run_status"]):
            raise ValueError("replication_kpis contains a non-complete run")

    tolerance = float(
        design["validation_gates"]["pooled_replay"][
            "timestamp_absolute_tolerance_seconds"
        ]
    )
    study_id = str(design["study_id"])
    cells = {
        str(cell["study_cell_id"]): cell
        for cell in design["study_cells"]
    }
    reference_cell = cells["REFERENCE_SCALE"]
    small_cell = cells["ILLUSTRATIVE_NORMALIZED_SMALL_SCALE"]

    event_rows: list[dict[str, object]] = []
    metric_rows: list[dict[str, object]] = []
    pooled_reports: dict[str, object] = {}
    reference_crn_reports: dict[str, object] = {}
    parsed_by_replication: dict[int, list[TravellerInput]] = {}
    for replication_id in sorted(grouped):
        result = replay_one_replication(
            grouped[replication_id],
            security_capacity=int(reference_cell["security_capacity"]),
            immigration_capacity=int(reference_cell["immigration_capacity"]),
            tolerance_seconds=tolerance,
            logged_total_queue_wait_p95_seconds=_nonnegative_float(
                kpi_by_replication[replication_id].get(
                    "total_queue_wait_p95_seconds"
                ),
                "replication_kpis.total_queue_wait_p95_seconds",
            ),
        )
        parsed_by_replication[replication_id] = result["travellers"]
        pooled_reports[str(replication_id)] = result["pooled_gate"]
        reference_crn_reports[str(replication_id)] = result["crn_gate"]
        for layout_key in ("pooled", "separate"):
            replay = result[layout_key]
            assert isinstance(replay, LayoutReplay)
            for event in replay.events:
                event_rows.append(
                    _event_row(
                        event,
                        study_id=study_id,
                        scenario_id=scenario_id,
                        input_sample_id=input_sample_id,
                        replication_id=replication_id,
                        study_cell_id="REFERENCE_SCALE",
                    )
                )
            metrics = result[f"{layout_key}_metrics"]
            assert isinstance(metrics, Mapping)
            metric_rows.append(
                {
                    "schema_version": ANALYSIS_SCHEMA_VERSION,
                    "study_id": study_id,
                    "scenario_id": scenario_id,
                    "input_sample_id": input_sample_id,
                    "replication_id": replication_id,
                    "study_cell_id": "REFERENCE_SCALE",
                    "layout_id": replay.layout_id,
                    **metrics,
                    "pooled_replay_status": result["pooled_gate"]["status"],
                    "crn_status": result["crn_gate"]["status"],
                }
            )

    pooled_status = (
        "PASS"
        if all(
            report["status"] == "PASS"
            for report in pooled_reports.values()
        )
        else "FAIL"
    )
    crn_status = (
        "PASS"
        if all(
            report["status"] == "PASS"
            for report in reference_crn_reports.values()
        )
        else "FAIL"
    )
    pooled_validation = {
        "gate_id": "POOLED_REPLAY_GATE_V1",
        "status": pooled_status,
        "study_cell_id": "REFERENCE_SCALE",
        "validation_scope": (
            "EXACT_AGAINST_ANYLOGIC_TIMESTAMPS_AND_REGISTERED_P95"
        ),
        "replication_count": len(pooled_reports),
        "replications": pooled_reports,
    }

    # Fail closed before executing the illustrative cell or creating a
    # directory that could be mistaken for a completed comparative result.
    reference_metric_rows = [
        row
        for row in metric_rows
        if row["study_cell_id"] == "REFERENCE_SCALE"
    ]
    reference_contrasts = build_paired_contrasts(
        reference_metric_rows,
        pooled_gate_status=pooled_status,
        crn_gate_status=crn_status,
        expected_replication_ids=expected_replications,
        ci_level=float(design["inference"]["confidence_level"]),
        study_id=study_id,
        study_cell_id="REFERENCE_SCALE",
        replay_validation_scope=(
            "EXACT_AGAINST_ANYLOGIC_TIMESTAMPS_AND_REGISTERED_P95"
        ),
    )

    small_crn_reports: dict[str, object] = {}
    for replication_id in sorted(parsed_by_replication):
        scaled_travellers = scale_traveller_arrivals(
            parsed_by_replication[replication_id],
            arrival_time_scale=float(small_cell["arrival_time_scale"]),
        )
        result = replay_mechanism_cell(
            scaled_travellers,
            security_capacity=int(small_cell["security_capacity"]),
            immigration_capacity=int(small_cell["immigration_capacity"]),
        )
        small_crn_reports[str(replication_id)] = result["crn_gate"]
        for layout_key in ("pooled", "separate"):
            replay = result[layout_key]
            assert isinstance(replay, LayoutReplay)
            for event in replay.events:
                event_rows.append(
                    _event_row(
                        event,
                        study_id=study_id,
                        scenario_id=scenario_id,
                        input_sample_id=input_sample_id,
                        replication_id=replication_id,
                        study_cell_id=(
                            "ILLUSTRATIVE_NORMALIZED_SMALL_SCALE"
                        ),
                    )
                )
            metrics = result[f"{layout_key}_metrics"]
            assert isinstance(metrics, Mapping)
            metric_rows.append(
                {
                    "schema_version": ANALYSIS_SCHEMA_VERSION,
                    "study_id": study_id,
                    "scenario_id": scenario_id,
                    "input_sample_id": input_sample_id,
                    "replication_id": replication_id,
                    "study_cell_id": (
                        "ILLUSTRATIVE_NORMALIZED_SMALL_SCALE"
                    ),
                    "layout_id": replay.layout_id,
                    **metrics,
                    "pooled_replay_status": (
                        "REFERENCE_GATE_PASS_PREREQUISITE"
                    ),
                    "crn_status": result["crn_gate"]["status"],
                }
            )
    small_crn_status = (
        "PASS"
        if all(
            report["status"] == "PASS"
            for report in small_crn_reports.values()
        )
        else "FAIL"
    )
    small_metric_rows = [
        row
        for row in metric_rows
        if row["study_cell_id"]
        == "ILLUSTRATIVE_NORMALIZED_SMALL_SCALE"
    ]
    small_contrasts = build_paired_contrasts(
        small_metric_rows,
        pooled_gate_status=pooled_status,
        crn_gate_status=small_crn_status,
        expected_replication_ids=expected_replications,
        ci_level=float(design["inference"]["confidence_level"]),
        study_id=study_id,
        study_cell_id="ILLUSTRATIVE_NORMALIZED_SMALL_SCALE",
        replay_validation_scope=(
            "REFERENCE_EXACT_GATE_PASS; TRANSFORMED_MECHANISM_ONLY"
        ),
        reported_pooled_replay_status=(
            "REFERENCE_GATE_PASS_PREREQUISITE"
        ),
    )
    contrasts = reference_contrasts + small_contrasts
    cross_scale_summary = build_cross_scale_summary(
        metric_rows,
        expected_replication_ids=expected_replications,
        ci_level=float(design["inference"]["confidence_level"]),
        study_id=study_id,
    )
    crn_validation = {
        "gate_id": "QUEUE_LAYOUT_CRN_GATE_V1",
        "status": (
            "PASS"
            if crn_status == "PASS" and small_crn_status == "PASS"
            else "FAIL"
        ),
        "study_cells": {
            "REFERENCE_SCALE": {
                "status": crn_status,
                "replication_count": len(reference_crn_reports),
                "replications": reference_crn_reports,
            },
            "ILLUSTRATIVE_NORMALIZED_SMALL_SCALE": {
                "status": small_crn_status,
                "replication_count": len(small_crn_reports),
                "replications": small_crn_reports,
            },
        },
    }

    if event_log_path.exists():
        raise FileExistsError(
            f"local counter-event log already exists: {event_log_path}"
        )
    output_dir.mkdir(parents=True, exist_ok=False)
    event_log_path.parent.mkdir(parents=True, exist_ok=True)
    _write_csv(event_log_path, event_rows, EVENT_FIELDS)
    _write_csv(
        output_dir / "replication_metrics.csv", metric_rows, METRIC_FIELDS
    )
    _write_csv(
        output_dir / "paired_contrasts.csv", contrasts, CONTRAST_FIELDS
    )
    _write_csv(
        output_dir / "cross_scale_mechanism_summary.csv",
        cross_scale_summary,
        CROSS_SCALE_FIELDS,
    )
    _write_json(output_dir / "pooled_replay_validation.json", pooled_validation)
    _write_json(output_dir / "crn_validation.json", crn_validation)
    event_digest = counter_event_audit_digest(
        event_rows,
        event_log_path=event_log_path,
        study_id=study_id,
    )
    _write_json(output_dir / "counter_event_audit_digest.json", event_digest)
    public_artifact_paths = {
        name: output_dir / name
        for name in (
            "replication_metrics.csv",
            "paired_contrasts.csv",
            "cross_scale_mechanism_summary.csv",
            "pooled_replay_validation.json",
            "crn_validation.json",
            "counter_event_audit_digest.json",
        )
    }
    manifest = {
        "schema_version": ANALYSIS_SCHEMA_VERSION,
        "analysis_id": ANALYSIS_ID,
        "study_id": study_id,
        "status": "PASS",
        "claim_ceiling": design["claim_ceiling"],
        "source_entity_log": _portable_path(entity_log_path),
        "source_entity_log_sha256": _file_sha256(entity_log_path),
        "source_replication_kpis": _portable_path(replication_kpis_path),
        "source_replication_kpis_sha256": _file_sha256(
            replication_kpis_path
        ),
        "source_manifest": (
            _portable_path(source_manifest_path)
            if source_manifest_path is not None
            else None
        ),
        "source_manifest_sha256": (
            _file_sha256(source_manifest_path)
            if source_manifest_path is not None
            else None
        ),
        "source_privacy_audit_status": (
            source_manifest["privacy_audit"]["status"]
            if source_manifest is not None
            else "NOT_PROVIDED"
        ),
        "source_classification": (
            source_manifest["classification"]
            if source_manifest is not None
            else "UNSPECIFIED"
        ),
        "design_path": _portable_path(design_path),
        "design_sha256": _file_sha256(design_path),
        "replication_count_per_study_cell": len(expected_replications),
        "study_cell_count": 2,
        "traveller_event_row_count": len(event_rows),
        "counter_event_log": _portable_path(event_log_path),
        "counter_event_log_sha256": event_digest[
            "counter_event_log_sha256"
        ],
        "counter_event_log_publication_status": "LOCAL_INTERMEDIATE_ONLY",
        "metric_row_count": len(metric_rows),
        "paired_contrast_row_count": len(contrasts),
        "cross_scale_summary_row_count": len(cross_scale_summary),
        "pooled_replay_status": pooled_status,
        "reference_crn_status": crn_status,
        "illustrative_crn_status": small_crn_status,
        "difference_direction": "SEPARATE_MINUS_POOLED",
        "scale_boundary": design["scale_boundary"],
        "public_artifact_sha256": {
            name: _file_sha256(path)
            for name, path in public_artifact_paths.items()
        },
        "interpretation": (
            "Two explicitly separated queue-layout mechanism cells: one exact "
            "reference replay and one transparent normalized small-scale "
            "assumption. Neither is a site forecast or policy recommendation."
        ),
    }
    _write_json(output_dir / "analysis_manifest.json", manifest)
    return manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Replay an AnyLogic entity ledger under pooled FCFS and frozen "
            "separate shortest-queue routing."
        )
    )
    parser.add_argument(
        "--entity-log",
        type=Path,
        default=DEFAULT_ENTITY_LEDGER,
        help=(
            "Curated OperationalCheckpointModel entity ledger. Defaults to "
            "the public synthetic source package."
        ),
    )
    parser.add_argument(
        "--replication-kpis",
        type=Path,
        default=DEFAULT_REPLICATION_KPIS,
        help=(
            "Curated registered P95 table; defaults to the public synthetic "
            "source package. The registered P95 is part of the pooled gate."
        ),
    )
    parser.add_argument(
        "--source-manifest",
        type=Path,
        default=DEFAULT_SOURCE_MANIFEST,
        help=(
            "Manifest that hashes and privacy-audits both curated inputs. "
            "Custom inputs must provide their matching manifest."
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="New directory for the validated replay package.",
    )
    parser.add_argument(
        "--event-log-path",
        type=Path,
        default=DEFAULT_LOCAL_EVENT_LOG,
        help=(
            "Local-intermediate path for the full counter-event ledger. "
            "This large file is not part of the public analysis package."
        ),
    )
    parser.add_argument(
        "--design",
        type=Path,
        default=DEFAULT_DESIGN,
        help="Frozen queue-layout replay design JSON.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    manifest = package_queue_layout_replay(
        entity_log_path=args.entity_log,
        replication_kpis_path=args.replication_kpis,
        output_dir=args.output_dir,
        design_path=args.design,
        event_log_path=args.event_log_path,
        source_manifest_path=args.source_manifest,
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
