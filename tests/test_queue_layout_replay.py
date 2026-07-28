from __future__ import annotations

import copy
import unittest

from src.analysis.analyse_queue_layout_replay import (
    IMMIGRATION,
    POOLED,
    SECURITY,
    SEPARATE,
    StageArrival,
    build_cross_scale_summary,
    build_paired_contrasts,
    fragmentation_seconds,
    load_design,
    nearest_rank_p95,
    parse_traveller_rows,
    replay_layout,
    replay_one_replication,
    replay_pooled_stage,
    replay_separate_stage,
    scale_traveller_arrivals,
    validate_design,
    validate_layout_crn,
    validate_pooled_replay,
)


def row(
    *,
    traveller_id: str,
    arrival: float,
    security_demand: float,
    immigration_primary_demand: float,
    lane_tie_u: float,
    security_start: float,
    security_end: float,
    immigration_start: float,
    exit_seconds: float,
    additional: float = 0.0,
) -> dict[str, str]:
    additional_flag = additional > 0
    return {
        "traveller_id": traveller_id,
        "arrival_seconds": str(arrival),
        "security_service_demand_seconds": str(security_demand),
        "immigration_primary_service_demand_seconds": str(
            immigration_primary_demand
        ),
        "additional_check_flag": str(additional_flag).lower(),
        "additional_check_service_demand_seconds": (
            str(additional) if additional_flag else ""
        ),
        "lane_tie_u": str(lane_tie_u),
        "security_queue_join_seconds": str(arrival),
        "security_start_seconds": str(security_start),
        "security_end_seconds": str(security_end),
        "immigration_queue_join_seconds": str(security_end),
        "immigration_start_seconds": str(immigration_start),
        "exit_seconds": str(exit_seconds),
    }


SYNTHETIC_LEDGER = [
    row(
        traveller_id="T001",
        arrival=0,
        security_demand=2,
        immigration_primary_demand=3,
        lane_tie_u=0.1,
        security_start=0,
        security_end=2,
        immigration_start=2,
        exit_seconds=5,
    ),
    row(
        traveller_id="T002",
        arrival=1,
        security_demand=2,
        immigration_primary_demand=1,
        lane_tie_u=0.9,
        security_start=2,
        security_end=4,
        immigration_start=5,
        exit_seconds=6,
    ),
]


class FrozenDesignTests(unittest.TestCase):
    def test_repository_design_is_frozen_reference_scale(self) -> None:
        design = load_design()
        source = design["source_ledger"]

        self.assertEqual(source["security_capacity"], 36)
        self.assertEqual(source["immigration_capacity"], 21)
        self.assertEqual(
            source["replication_ids"],
            {"first": 1, "last": 50, "count": 50},
        )
        self.assertEqual(
            design["metrics"]["p95_quantile_definition"],
            "NEAREST_RANK_INDEX_CEIL_0.95N_MINUS_1",
        )
        self.assertTrue(
            design["scale_boundary"]["reference_scale_first"]
        )
        cells = {
            cell["study_cell_id"]: cell for cell in design["study_cells"]
        }
        self.assertEqual(
            cells["ILLUSTRATIVE_NORMALIZED_SMALL_SCALE"][
                "arrival_time_scale"
            ],
            5.0,
        )
        self.assertEqual(
            cells["ILLUSTRATIVE_NORMALIZED_SMALL_SCALE"][
                "security_capacity"
            ],
            6,
        )
        self.assertEqual(
            cells["ILLUSTRATIVE_NORMALIZED_SMALL_SCALE"][
                "immigration_capacity"
            ],
            4,
        )

    def test_drift_to_jockeying_is_rejected(self) -> None:
        design = copy.deepcopy(load_design())
        design["layouts"]["separate_jsq"]["jockeying"] = "ALLOWED"

        with self.assertRaisesRegex(ValueError, "jockeying"):
            validate_design(design)


class StageReplayTests(unittest.TestCase):
    def test_pooled_fcfs_is_work_conserving_and_deterministic(self) -> None:
        events = replay_pooled_stage(
            [
                StageArrival("T1", 0, 4, 0.1),
                StageArrival("T2", 0, 2, 0.2),
                StageArrival("T3", 1, 1, 0.3),
            ],
            capacity=2,
            stage=SECURITY,
        )

        by_id = {event.traveller_id: event for event in events}
        self.assertEqual(by_id["T1"].counter_index, 0)
        self.assertEqual(by_id["T2"].counter_index, 1)
        self.assertEqual(by_id["T3"].start_seconds, 2)
        self.assertEqual(by_id["T3"].counter_index, 1)

    def test_separate_shortest_lane_logs_tie_and_never_jockeys(self) -> None:
        events = replay_separate_stage(
            [
                StageArrival("T1", 0, 10, 0.0),
                StageArrival("T2", 0, 2, 0.99),
                StageArrival("T3", 1, 1, 0.0),
            ],
            capacity=2,
            stage=SECURITY,
        )
        by_id = {event.traveller_id: event for event in events}

        self.assertEqual(by_id["T1"].tie_candidates, (0, 1))
        self.assertEqual(by_id["T1"].tie_index, 0)
        self.assertEqual(by_id["T1"].counter_index, 0)
        self.assertEqual(by_id["T2"].lane_lengths, (1, 0))
        self.assertEqual(by_id["T2"].counter_index, 1)
        self.assertEqual(by_id["T3"].lane_lengths, (1, 1))
        self.assertEqual(by_id["T3"].counter_index, 0)
        self.assertEqual(by_id["T3"].start_seconds, 10)
        self.assertEqual(
            by_id["T3"].routing_rule,
            "SHORTEST_NUMBER_IN_LANE_AT_ARRIVAL",
        )

    def test_fragmentation_integrates_idle_while_other_lane_waits(self) -> None:
        events = replay_separate_stage(
            [
                StageArrival("T1", 0, 10, 0.0),
                StageArrival("T2", 0, 2, 0.99),
                StageArrival("T3", 1, 1, 0.0),
            ],
            capacity=2,
            stage=SECURITY,
        )

        # Lane 2 is idle on [2, 10) while T3 remains in lane 1.
        self.assertAlmostEqual(fragmentation_seconds(events, capacity=2), 8)

    def test_pooled_fragmentation_is_zero_by_mechanism(self) -> None:
        events = replay_pooled_stage(
            [
                StageArrival("T1", 0, 10, 0.0),
                StageArrival("T2", 0, 2, 0.99),
                StageArrival("T3", 1, 1, 0.0),
            ],
            capacity=2,
            stage=SECURITY,
        )

        self.assertEqual(fragmentation_seconds(events, capacity=2), 0)


class SerialReplayAndGateTests(unittest.TestCase):
    def test_security_completion_is_replayed_immigration_arrival(self) -> None:
        travellers = parse_traveller_rows(SYNTHETIC_LEDGER)
        replay = replay_layout(
            travellers,
            layout_id=SEPARATE,
            security_capacity=1,
            immigration_capacity=1,
        )
        security = {
            event.traveller_id: event for event in replay.security_events
        }
        immigration = {
            event.traveller_id: event for event in replay.immigration_events
        }

        for traveller_id in security:
            self.assertEqual(
                immigration[traveller_id].arrival_seconds,
                security[traveller_id].end_seconds,
            )
        self.assertEqual(
            immigration["T001"].service_demand_seconds,
            3,
        )

    def test_selected_additional_work_is_part_of_counter_hold(self) -> None:
        rows = [
            row(
                traveller_id="T001",
                arrival=0,
                security_demand=1,
                immigration_primary_demand=2,
                additional=4,
                lane_tie_u=0.5,
                security_start=0,
                security_end=1,
                immigration_start=1,
                exit_seconds=7,
            )
        ]

        traveller = parse_traveller_rows(rows)[0]
        self.assertEqual(traveller.immigration_service_demand_seconds, 6)
        self.assertEqual(
            traveller.immigration_primary_service_demand_seconds, 2
        )
        self.assertTrue(traveller.additional_check_flag)
        self.assertEqual(
            traveller.additional_check_service_demand_seconds, 4
        )

    def test_small_scale_changes_arrivals_only(self) -> None:
        source = parse_traveller_rows(SYNTHETIC_LEDGER)
        scaled = scale_traveller_arrivals(source, arrival_time_scale=5)

        for original, transformed in zip(source, scaled):
            self.assertEqual(
                transformed.arrival_seconds, original.arrival_seconds * 5
            )
            self.assertEqual(
                transformed.security_service_demand_seconds,
                original.security_service_demand_seconds,
            )
            self.assertEqual(
                transformed.immigration_primary_service_demand_seconds,
                original.immigration_primary_service_demand_seconds,
            )
            self.assertEqual(
                transformed.additional_check_flag,
                original.additional_check_flag,
            )
            self.assertEqual(
                transformed.additional_check_service_demand_seconds,
                original.additional_check_service_demand_seconds,
            )
            self.assertEqual(transformed.lane_tie_u, original.lane_tie_u)

    def test_exact_pooled_timestamps_and_registered_p95_pass(self) -> None:
        result = replay_one_replication(
            SYNTHETIC_LEDGER,
            security_capacity=1,
            immigration_capacity=1,
            tolerance_seconds=1e-9,
            logged_total_queue_wait_p95_seconds=2.0,
        )

        self.assertEqual(result["pooled_gate"]["status"], "PASS")
        self.assertEqual(
            result["pooled_gate"]["replication_kpi_comparison_count"], 1
        )
        self.assertEqual(
            result["pooled_metrics"]["total_queue_wait_p95_seconds"], 2
        )
        self.assertEqual(result["crn_gate"]["status"], "PASS")

    def test_pooled_gate_fails_on_logged_timestamp_drift(self) -> None:
        travellers = parse_traveller_rows(SYNTHETIC_LEDGER)
        replay = replay_layout(
            travellers,
            layout_id=POOLED,
            security_capacity=1,
            immigration_capacity=1,
        )
        drifted = list(SYNTHETIC_LEDGER)
        drifted[1] = {**drifted[1], "immigration_start_seconds": "5.25"}
        drifted_travellers = parse_traveller_rows(drifted)

        report = validate_pooled_replay(
            drifted_travellers,
            replay,
            tolerance_seconds=1e-6,
            logged_total_queue_wait_p95_seconds=2,
        )

        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(report["mismatch_count"], 2)
        self.assertEqual(
            {item["field"] for item in report["mismatches"]},
            {
                "immigration_start_seconds",
                "derived_immigration_wait_seconds",
            },
        )

    def test_pooled_gate_fails_on_registered_p95_drift(self) -> None:
        travellers = parse_traveller_rows(SYNTHETIC_LEDGER)
        replay = replay_layout(
            travellers,
            layout_id=POOLED,
            security_capacity=1,
            immigration_capacity=1,
        )

        report = validate_pooled_replay(
            travellers,
            replay,
            tolerance_seconds=1e-6,
            logged_total_queue_wait_p95_seconds=2.25,
        )

        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(
            report["mismatches"][0]["field"],
            "replication_kpis.total_queue_wait_p95_seconds",
        )

    def test_crn_hash_detects_changed_service_demand(self) -> None:
        travellers = parse_traveller_rows(SYNTHETIC_LEDGER)
        pooled = replay_layout(
            travellers,
            layout_id=POOLED,
            security_capacity=1,
            immigration_capacity=1,
        )
        separate = replay_layout(
            travellers,
            layout_id=SEPARATE,
            security_capacity=1,
            immigration_capacity=1,
        )
        corrupted = copy.copy(separate)
        object.__setattr__(corrupted, "immutable_input_sha256", "0" * 64)

        report = validate_layout_crn(travellers, pooled, corrupted)

        self.assertEqual(report["status"], "FAIL")
        self.assertFalse(report["separate_input_hash_matches_source"])


class MetricAndInferenceTests(unittest.TestCase):
    def test_p95_uses_registered_nearest_rank_rule(self) -> None:
        # ceil(0.95 * 20) - 1 = 18, not an interpolated Type-7 value.
        self.assertEqual(nearest_rank_p95(list(range(1, 21))), 19)

    @staticmethod
    def metric_rows(
        cell_id: str = "REFERENCE_SCALE",
    ) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        for replication in (1, 2, 3):
            for layout, offset in ((POOLED, 0.0), (SEPARATE, 2.0)):
                values = {
                    metric: float(replication) + offset
                    for metric in (
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
                }
                rows.append(
                    {
                        "replication_id": replication,
                        "study_cell_id": cell_id,
                        "layout_id": layout,
                        **values,
                    }
                )
        return rows

    def test_paired_intervals_require_both_gates_and_exact_reps(self) -> None:
        contrasts = build_paired_contrasts(
            self.metric_rows(),
            pooled_gate_status="PASS",
            crn_gate_status="PASS",
            expected_replication_ids={1, 2, 3},
            ci_level=0.95,
            study_id="SYNTHETIC",
        )

        self.assertEqual(len(contrasts), 12)
        self.assertTrue(
            all(row["comparison_method"] == "PAIRED_STUDENT_T" for row in contrasts)
        )
        self.assertTrue(
            all(row["difference_mean"] == 2 for row in contrasts)
            )

    def test_failed_replay_gate_blocks_all_contrasts(self) -> None:
        with self.assertRaisesRegex(ValueError, "blocked"):
            build_paired_contrasts(
                self.metric_rows(),
                pooled_gate_status="FAIL",
                crn_gate_status="PASS",
                expected_replication_ids={1, 2, 3},
                ci_level=0.95,
                study_id="SYNTHETIC",
            )

    def test_cross_scale_summary_uses_paired_difference_in_effects(self) -> None:
        reference = self.metric_rows("REFERENCE_SCALE")
        illustrative = self.metric_rows(
            "ILLUSTRATIVE_NORMALIZED_SMALL_SCALE"
        )
        for row in illustrative:
            if row["layout_id"] == SEPARATE:
                for metric in (
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
                ):
                    row[metric] = float(row[metric]) + 3

        summary = build_cross_scale_summary(
            reference + illustrative,
            expected_replication_ids={1, 2, 3},
            ci_level=0.95,
            study_id="SYNTHETIC",
        )

        self.assertEqual(len(summary), 9)
        self.assertTrue(
            all(
                item["illustrative_minus_reference_layout_effect_mean"] == 3
                for item in summary
            )
        )

    def test_missing_replication_blocks_all_contrasts(self) -> None:
        with self.assertRaisesRegex(ValueError, "exact frozen replication"):
            build_paired_contrasts(
                self.metric_rows(),
                pooled_gate_status="PASS",
                crn_gate_status="PASS",
                expected_replication_ids={1, 2, 3, 4},
                ci_level=0.95,
                study_id="SYNTHETIC",
            )


if __name__ == "__main__":
    unittest.main()
