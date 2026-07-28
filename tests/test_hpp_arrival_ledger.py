from __future__ import annotations

import copy
import unittest
from unittest.mock import patch

from src.analysis.hpp_arrival_ledger import (
    ARRIVAL_ASSUMPTION,
    DEFAULT_CUTOFF_SECONDS,
    DEFAULT_RANDOM_SEED,
    DEFAULT_RATE_PER_SECOND,
    EVENT_COUNT_LIMIT,
    HPPEventLimitError,
    canonical_ledger_bytes,
    generate_hpp_ledger,
    validate_hpp_ledger,
)


class HPPArrivalLedgerTests(unittest.TestCase):
    def test_default_contract_uses_the_frozen_local_window_inputs(self) -> None:
        ledger = generate_hpp_ledger()

        self.assertEqual(
            ledger["arrival_assumption"],
            ARRIVAL_ASSUMPTION,
        )
        self.assertEqual(
            ledger["rate_per_second"],
            DEFAULT_RATE_PER_SECOND,
        )
        self.assertEqual(
            ledger["cutoff_seconds"],
            DEFAULT_CUTOFF_SECONDS,
        )
        self.assertEqual(ledger["random_seed"], DEFAULT_RANDOM_SEED)
        self.assertNotIn("max_arrivals", ledger)
        self.assertEqual(ledger["event_count"], len(ledger["events"]))

    def test_arrival_timestamps_are_strictly_inside_half_open_window(
        self,
    ) -> None:
        ledger = generate_hpp_ledger()
        timestamps = [
            event["time_seconds"] for event in ledger["events"]  # type: ignore[index]
        ]

        self.assertTrue(
            all(
                0 <= timestamp < DEFAULT_CUTOFF_SECONDS
                for timestamp in timestamps
            )
        )
        self.assertTrue(
            all(left < right for left, right in zip(timestamps, timestamps[1:]))
        )

    def test_same_seed_is_byte_identical(self) -> None:
        first = canonical_ledger_bytes(generate_hpp_ledger(random_seed=42))
        second = canonical_ledger_bytes(generate_hpp_ledger(random_seed=42))

        self.assertEqual(first, second)

    def test_different_seeds_are_distinct_realizations(self) -> None:
        first = canonical_ledger_bytes(generate_hpp_ledger(random_seed=42))
        second = canonical_ledger_bytes(generate_hpp_ledger(random_seed=43))

        self.assertNotEqual(first, second)

    def test_generated_ledger_passes_structural_and_replay_validation(
        self,
    ) -> None:
        report = validate_hpp_ledger(generate_hpp_ledger())

        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["errors"], [])

    def test_validator_rejects_boundary_and_seed_replay_tampering(self) -> None:
        ledger = copy.deepcopy(generate_hpp_ledger())
        events = ledger["events"]
        self.assertTrue(events)
        events[0]["time_seconds"] = DEFAULT_CUTOFF_SECONDS  # type: ignore[index]

        report = validate_hpp_ledger(ledger)

        self.assertEqual(report["status"], "FAIL")
        self.assertTrue(
            any("outside [0, T)" in error for error in report["errors"])
        )
        self.assertTrue(
            any("seeded replay" in error for error in report["errors"])
        )

    def test_event_guard_is_strictly_below_fifty_thousand(self) -> None:
        self.assertEqual(EVENT_COUNT_LIMIT, 50_000)
        ledger = generate_hpp_ledger()
        self.assertLess(ledger["event_count"], EVENT_COUNT_LIMIT)

        with patch(
            "src.analysis.hpp_arrival_ledger.EVENT_COUNT_LIMIT",
            3,
        ):
            with self.assertRaisesRegex(
                HPPEventLimitError,
                "would reach 50,000 events",
            ):
                generate_hpp_ledger(
                    rate_per_second=1_000_000.0,
                    cutoff_seconds=1.0,
                    random_seed=1,
                )

    def test_invalid_process_parameters_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "rate_per_second"):
            generate_hpp_ledger(rate_per_second=0)
        with self.assertRaisesRegex(ValueError, "cutoff_seconds"):
            generate_hpp_ledger(cutoff_seconds=float("inf"))
        with self.assertRaisesRegex(TypeError, "random_seed"):
            generate_hpp_ledger(random_seed=True)


if __name__ == "__main__":
    unittest.main()
