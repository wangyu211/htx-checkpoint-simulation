"""Generate and validate a reproducible local-window HPP arrival ledger.

The accepted Task 1 aggregate identifies an arrival *rate*, not an exact
arrival count for every simulated window.  This module therefore samples
exponential inter-arrival times until the half-open cutoff ``[0, T)`` instead
of forcing the observed count into each replication.
"""

from __future__ import annotations

import json
import math
import random
from pathlib import Path
from typing import Mapping


SCHEMA_VERSION = "HPP_ARRIVAL_LEDGER_V1"
ARRIVAL_MODEL = "HOMOGENEOUS_POISSON_PROCESS"
ARRIVAL_ASSUMPTION = "LOCAL_WINDOW_HPP_STATIONARY_INDEPENDENT"
RNG_ALGORITHM = "PYTHON_MT19937_INVERSE_EXPONENTIAL_V1"

DEFAULT_RATE_PER_SECOND = 1.364213
DEFAULT_CUTOFF_SECONDS = 24.922788889
DEFAULT_RANDOM_SEED = 2026072710

# The guard is deliberately strict: a valid ledger always contains fewer than
# 50,000 events.  It protects both accidental unit mistakes and PLE workflows.
EVENT_COUNT_LIMIT = 50_000

LEDGER_FIELDS = {
    "schema_version",
    "arrival_model",
    "arrival_assumption",
    "rng_algorithm",
    "rate_per_second",
    "cutoff_seconds",
    "random_seed",
    "event_count",
    "events",
}
EVENT_FIELDS = {"arrival_index", "time_seconds"}


class HPPEventLimitError(RuntimeError):
    """Raised before a generated ledger would reach the event-count limit."""


def _positive_finite(name: str, value: object) -> float:
    if isinstance(value, bool):
        raise TypeError(f"{name} must be a finite positive number")
    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise TypeError(f"{name} must be a finite positive number") from exc
    if not math.isfinite(numeric) or numeric <= 0:
        raise ValueError(f"{name} must be a finite positive number")
    return numeric


def _integer_seed(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError("random_seed must be an integer")
    if not 0 <= value <= 2**63 - 1:
        raise ValueError("random_seed must be between 0 and 2^63 - 1")
    return value


def generate_hpp_ledger(
    *,
    rate_per_second: float = DEFAULT_RATE_PER_SECOND,
    cutoff_seconds: float = DEFAULT_CUTOFF_SECONDS,
    random_seed: int = DEFAULT_RANDOM_SEED,
) -> dict[str, object]:
    """Sample one seeded HPP realization on the half-open window ``[0, T)``.

    ``event_count`` is an output of the random realization.  There is
    intentionally no ``max_arrivals`` input and no forced count of 34.
    """

    rate = _positive_finite("rate_per_second", rate_per_second)
    cutoff = _positive_finite("cutoff_seconds", cutoff_seconds)
    seed = _integer_seed(random_seed)

    rng = random.Random(seed)
    events: list[dict[str, object]] = []
    arrival_time = 0.0

    while True:
        # random() is in [0, 1).  Resampling its possible zero value keeps the
        # inverse-transform inter-arrival strictly positive.
        uniform = rng.random()
        while uniform == 0.0:
            uniform = rng.random()
        interarrival = -math.log1p(-uniform) / rate
        arrival_time += interarrival

        if arrival_time >= cutoff:
            break
        if len(events) >= EVENT_COUNT_LIMIT - 1:
            raise HPPEventLimitError(
                "generated ledger would reach 50,000 events; "
                "check the arrival-rate and time units"
            )

        events.append(
            {
                "arrival_index": len(events) + 1,
                "time_seconds": arrival_time,
            }
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "arrival_model": ARRIVAL_MODEL,
        "arrival_assumption": ARRIVAL_ASSUMPTION,
        "rng_algorithm": RNG_ALGORITHM,
        "rate_per_second": rate,
        "cutoff_seconds": cutoff,
        "random_seed": seed,
        "event_count": len(events),
        "events": events,
    }


def canonical_ledger_bytes(ledger: Mapping[str, object]) -> bytes:
    """Return the canonical UTF-8 JSON representation used for replay checks."""

    return (
        json.dumps(
            ledger,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def write_hpp_ledger(path: Path, ledger: Mapping[str, object]) -> None:
    """Write a ledger without changing its canonical byte representation."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_ledger_bytes(ledger))


def validate_hpp_ledger(ledger: object) -> dict[str, object]:
    """Validate structure, bounds, seed lineage, and exact seeded replay."""

    errors: list[str] = []
    if not isinstance(ledger, Mapping):
        return {
            "contract": SCHEMA_VERSION,
            "status": "FAIL",
            "realized_event_count": None,
            "errors": ["ledger must be a JSON object"],
        }

    unknown_fields = sorted(set(ledger) - LEDGER_FIELDS)
    missing_fields = sorted(LEDGER_FIELDS - set(ledger))
    if unknown_fields:
        errors.append(f"unknown ledger fields: {unknown_fields}")
    if missing_fields:
        errors.append(f"missing ledger fields: {missing_fields}")

    expected_literals = {
        "schema_version": SCHEMA_VERSION,
        "arrival_model": ARRIVAL_MODEL,
        "arrival_assumption": ARRIVAL_ASSUMPTION,
        "rng_algorithm": RNG_ALGORITHM,
    }
    for field, expected in expected_literals.items():
        if ledger.get(field) != expected:
            errors.append(f"{field} must be {expected!r}")

    rate: float | None = None
    cutoff: float | None = None
    seed: int | None = None
    try:
        rate = _positive_finite(
            "rate_per_second", ledger.get("rate_per_second")
        )
    except (TypeError, ValueError) as exc:
        errors.append(str(exc))
    try:
        cutoff = _positive_finite(
            "cutoff_seconds", ledger.get("cutoff_seconds")
        )
    except (TypeError, ValueError) as exc:
        errors.append(str(exc))
    try:
        seed = _integer_seed(ledger.get("random_seed"))
    except (TypeError, ValueError) as exc:
        errors.append(str(exc))

    raw_events = ledger.get("events")
    events: list[object]
    if isinstance(raw_events, list):
        events = raw_events
    else:
        events = []
        errors.append("events must be a list")

    if len(events) >= EVENT_COUNT_LIMIT:
        errors.append("event_count must be strictly less than 50,000")

    declared_count = ledger.get("event_count")
    if (
        isinstance(declared_count, bool)
        or not isinstance(declared_count, int)
        or declared_count < 0
    ):
        errors.append("event_count must be a non-negative integer")
    elif declared_count != len(events):
        errors.append(
            f"event_count={declared_count} but events contains {len(events)} rows"
        )

    previous_time = -math.inf
    for position, event in enumerate(events, start=1):
        if not isinstance(event, Mapping):
            errors.append(f"events[{position - 1}] must be an object")
            continue
        extra = sorted(set(event) - EVENT_FIELDS)
        missing = sorted(EVENT_FIELDS - set(event))
        if extra:
            errors.append(
                f"events[{position - 1}] has unknown fields: {extra}"
            )
        if missing:
            errors.append(
                f"events[{position - 1}] is missing fields: {missing}"
            )

        if event.get("arrival_index") != position:
            errors.append(
                f"events[{position - 1}].arrival_index must be {position}"
            )

        raw_time = event.get("time_seconds")
        if isinstance(raw_time, bool):
            errors.append(
                f"events[{position - 1}].time_seconds must be finite"
            )
            continue
        try:
            event_time = float(raw_time)
        except (TypeError, ValueError):
            errors.append(
                f"events[{position - 1}].time_seconds must be finite"
            )
            continue
        if not math.isfinite(event_time):
            errors.append(
                f"events[{position - 1}].time_seconds must be finite"
            )
            continue
        if event_time <= previous_time:
            errors.append("arrival timestamps must be strictly increasing")
        if event_time < 0 or (cutoff is not None and event_time >= cutoff):
            errors.append(
                f"events[{position - 1}].time_seconds is outside [0, T)"
            )
        previous_time = event_time

    if rate is not None and cutoff is not None and seed is not None:
        try:
            expected = generate_hpp_ledger(
                rate_per_second=rate,
                cutoff_seconds=cutoff,
                random_seed=seed,
            )
            if canonical_ledger_bytes(ledger) != canonical_ledger_bytes(expected):
                errors.append(
                    "ledger is not byte-identical to its declared seeded replay"
                )
        except HPPEventLimitError as exc:
            errors.append(str(exc))
        except (TypeError, ValueError) as exc:
            errors.append(str(exc))

    return {
        "contract": SCHEMA_VERSION,
        "status": "PASS" if not errors else "FAIL",
        "realized_event_count": len(events),
        "errors": errors,
    }
