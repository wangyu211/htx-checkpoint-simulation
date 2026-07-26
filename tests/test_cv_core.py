"""Offline regression tests for the Task 1 CV counting core."""

from __future__ import annotations

import math
import unittest
from unittest.mock import patch

import numpy as np

from src.cv.audit_crossings import (
    Track,
    detect_in_tiles,
    filter_roi,
    parse_roi,
    parse_tiles,
    resolve_time_seconds,
    side_of_line,
    update_crossing,
)
from src.cv.recount_lines import recount
from src.cv.yolox_onnx import Detection, decode_outputs, nms


def make_track(x_coordinate: float, y_coordinate: float = 20.0) -> Track:
    half_size = 2.0
    return Track(
        track_id=7,
        box=np.array(
            [
                x_coordinate - half_size,
                y_coordinate - half_size,
                x_coordinate + half_size,
                y_coordinate + half_size,
            ],
            dtype=np.float32,
        ),
        score=0.81234567,
    )


def move_track(track: Track, x_coordinate: float, y_coordinate: float = 20.0) -> None:
    half_size = 2.0
    track.box = np.array(
        [
            x_coordinate - half_size,
            y_coordinate - half_size,
            x_coordinate + half_size,
            y_coordinate + half_size,
        ],
        dtype=np.float32,
    )


def observation(
    frame_index: int,
    x_coordinate: float,
    *,
    track_id: int = 7,
    time_seconds: float | None = None,
) -> dict[str, str]:
    if time_seconds is None:
        time_seconds = frame_index / 30.0
    return {
        "frame_index": str(frame_index),
        "time_seconds": str(time_seconds),
        "track_id": str(track_id),
        "centroid_x": str(x_coordinate),
        "centroid_y": "20.0",
        "confidence": "0.81234567",
    }


class TimestampTests(unittest.TestCase):
    def test_valid_pts_is_used_instead_of_frame_rate_approximation(self) -> None:
        self.assertEqual(resolve_time_seconds(1.234567, 90, 30.0), 1.234567)
        self.assertEqual(resolve_time_seconds(0.0, 90, 30.0), 0.0)

    def test_invalid_pts_falls_back_to_frame_index_over_fps(self) -> None:
        self.assertAlmostEqual(resolve_time_seconds(math.nan, 3, 30.0), 0.1)
        self.assertAlmostEqual(resolve_time_seconds(math.inf, 15, 25.0), 0.6)
        self.assertAlmostEqual(resolve_time_seconds(-1.0, 15, 25.0), 0.6)

    def test_fallback_rejects_invalid_fps(self) -> None:
        with self.assertRaisesRegex(ValueError, "positive finite FPS"):
            resolve_time_seconds(math.nan, 3, 0.0)


class CrossingStateTests(unittest.TestCase):
    def call_update(
        self,
        track: Track,
        frame_index: int,
        x_coordinate: float,
        *,
        time_seconds: float | None = None,
        minimum_displacement: float = 24.0,
    ) -> dict[str, object] | None:
        move_track(track, x_coordinate)
        if time_seconds is None:
            time_seconds = frame_index / 30.0
        return update_crossing(
            track,
            frame_index,
            time_seconds,
            line_x=50,
            line_margin=5,
            side_confirm_frames=3,
            minimum_crossing_displacement=minimum_displacement,
        )

    def test_deadband_boundaries_and_sides(self) -> None:
        self.assertEqual(side_of_line(44.999, 50, 5), -1)
        self.assertEqual(side_of_line(45.0, 50, 5), 0)
        self.assertEqual(side_of_line(50.0, 50, 5), 0)
        self.assertEqual(side_of_line(55.0, 50, 5), 0)
        self.assertEqual(side_of_line(55.001, 50, 5), 1)

    def test_crossing_requires_mature_sides_and_emits_pts(self) -> None:
        track = make_track(35)
        positions = [35, 36, 34, 47, 50, 54, 66, 68, 70]
        events = [
            self.call_update(
                track,
                frame_index,
                x_coordinate,
                time_seconds=12.3456789 if frame_index == 8 else None,
            )
            for frame_index, x_coordinate in enumerate(positions)
        ]

        self.assertTrue(all(event is None for event in events[:-1]))
        self.assertEqual(
            events[-1],
            {
                "track_id": 7,
                "frame_index": 8,
                "time_seconds": 12.345679,
                "direction": "left_to_right",
                "centroid_x": 70.0,
                "centroid_y": 20.0,
                "confidence": 0.812346,
            },
        )

    def test_deadband_resets_candidate_maturity(self) -> None:
        track = make_track(35)
        for frame_index, x_coordinate in enumerate([35, 36, 50, 34]):
            self.assertIsNone(self.call_update(track, frame_index, x_coordinate))

        self.assertEqual(track.stable_side, 0)
        self.assertEqual(track.candidate_side, -1)
        self.assertEqual(track.candidate_side_frames, 1)

    def test_frame_gap_resets_candidate_maturity(self) -> None:
        track = make_track(35)
        self.assertIsNone(self.call_update(track, 0, 35))
        self.assertIsNone(self.call_update(track, 1, 36))
        self.assertIsNone(self.call_update(track, 3, 34))

        self.assertEqual(track.stable_side, 0)
        self.assertEqual(track.candidate_side_frames, 1)

    def test_minimum_displacement_vetoes_then_allows_event(self) -> None:
        track = make_track(44)
        for frame_index in range(3):
            self.assertIsNone(
                self.call_update(
                    track,
                    frame_index,
                    44,
                    minimum_displacement=20.0,
                )
            )
        for frame_index in range(3, 6):
            self.assertIsNone(
                self.call_update(
                    track,
                    frame_index,
                    56,
                    minimum_displacement=20.0,
                )
            )

        event = self.call_update(
            track,
            6,
            65,
            minimum_displacement=20.0,
        )
        self.assertIsNotNone(event)
        self.assertEqual(event["direction"], "left_to_right")

    def test_track_is_counted_at_most_once(self) -> None:
        track = make_track(30)
        events: list[dict[str, object]] = []
        positions = [30, 31, 32, 68, 69, 70, 32, 31, 30]
        for frame_index, x_coordinate in enumerate(positions):
            event = self.call_update(track, frame_index, x_coordinate)
            if event is not None:
                events.append(event)

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["direction"], "left_to_right")


class OfflineRecountTests(unittest.TestCase):
    def test_recount_sorts_rows_and_preserves_event_timestamp(self) -> None:
        rows = [
            observation(frame, x, time_seconds=9.75 if frame == 6 else None)
            for frame, x in enumerate([70, 69, 68, 50, 32, 31, 30])
        ]
        rows.reverse()

        events = recount(
            rows,
            line_x=50,
            margin=5,
            side_confirm_frames=3,
            minimum_displacement=24.0,
        )

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["direction"], "right_to_left")
        self.assertEqual(events[0]["frame_index"], 6)
        self.assertEqual(events[0]["time_seconds"], 9.75)

    def test_recount_does_not_mature_a_side_across_frame_gap(self) -> None:
        rows = [
            observation(0, 30),
            observation(1, 31),
            observation(3, 32),
            observation(4, 68),
            observation(5, 69),
            observation(6, 70),
        ]

        events = recount(
            rows,
            line_x=50,
            margin=5,
            side_confirm_frames=3,
            minimum_displacement=24.0,
        )
        self.assertEqual(events, [])

    def test_online_and_offline_state_machines_agree(self) -> None:
        positions = [30, 31, 32, 50, 68, 69, 70]
        track = make_track(positions[0])
        online_events = []
        for frame_index, x_coordinate in enumerate(positions):
            event = self.call_online_update(track, frame_index, x_coordinate)
            if event is not None:
                online_events.append(event)

        offline_events = recount(
            [
                observation(
                    frame_index,
                    x_coordinate,
                    time_seconds=frame_index * 0.041,
                )
                for frame_index, x_coordinate in enumerate(positions)
            ],
            line_x=50,
            margin=5,
            side_confirm_frames=3,
            minimum_displacement=24.0,
        )

        self.assertEqual(len(online_events), len(offline_events))
        for online, offline in zip(online_events, offline_events):
            self.assertEqual(online["frame_index"], offline["frame_index"])
            self.assertEqual(online["direction"], offline["direction"])
            self.assertEqual(online["time_seconds"], offline["time_seconds"])

    @staticmethod
    def call_online_update(
        track: Track,
        frame_index: int,
        x_coordinate: float,
    ) -> dict[str, object] | None:
        move_track(track, x_coordinate)
        return update_crossing(
            track,
            frame_index,
            frame_index * 0.041,
            line_x=50,
            line_margin=5,
            side_confirm_frames=3,
            minimum_crossing_displacement=24.0,
        )


class RoiTileAndNmsTests(unittest.TestCase):
    def test_parse_roi_and_tiles(self) -> None:
        roi = parse_roi(" 0, 1, 20, 30 ")
        self.assertEqual(roi, (0, 1, 20, 30))
        self.assertEqual(parse_tiles(None, roi), [roi])
        self.assertEqual(
            parse_tiles("0,0,10,10; 5,5,15,20; ", roi),
            [(0, 0, 10, 10), (5, 5, 15, 20)],
        )

    def test_parse_roi_and_tiles_reject_invalid_geometry(self) -> None:
        for text in ("0,0,1", "1,0,1,2", "0,3,2,2"):
            with self.subTest(text=text):
                with self.assertRaises(ValueError):
                    parse_roi(text)
        with self.assertRaisesRegex(ValueError, "at least one ROI"):
            parse_tiles(" ; ", (0, 0, 10, 10))

    def test_filter_roi_uses_detection_centroid_and_includes_boundary(self) -> None:
        detections = [
            Detection(np.array([-1, -1, 1, 1], dtype=np.float32), 0.9, 0),
            Detection(np.array([9, 9, 11, 11], dtype=np.float32), 0.8, 0),
            Detection(np.array([10.1, 0, 12.1, 2], dtype=np.float32), 0.7, 0),
        ]
        selected = filter_roi(detections, (0, 0, 10, 10))
        self.assertEqual([item.score for item in selected], [0.9, 0.8])

    def test_nms_keeps_highest_scoring_overlap_and_disjoint_box(self) -> None:
        boxes = np.array(
            [
                [10, 10, 30, 30],
                [11, 11, 31, 31],
                [70, 10, 90, 30],
            ],
            dtype=np.float32,
        )
        scores = np.array([0.9, 0.8, 0.7], dtype=np.float32)
        self.assertEqual(nms(boxes, scores, threshold=0.5), [0, 2])

    def test_tiled_merge_filters_analysis_roi_and_deduplicates_overlap(self) -> None:
        first_tile = [
            Detection(np.array([10, 10, 30, 30], dtype=np.float32), 0.9, 0),
            Detection(np.array([-12, 10, -2, 20], dtype=np.float32), 0.99, 0),
        ]
        second_tile = [
            Detection(np.array([11, 11, 31, 31], dtype=np.float32), 0.8, 0),
            Detection(np.array([70, 10, 90, 30], dtype=np.float32), 0.7, 0),
        ]
        with patch(
            "src.cv.audit_crossings.detect_in_roi",
            side_effect=[first_tile, second_tile],
        ):
            merged = detect_in_tiles(
                detector=object(),
                frame=np.zeros((100, 100, 3), dtype=np.uint8),
                tiles=[(0, 0, 60, 100), (40, 0, 100, 100)],
                analysis_roi=(0, 0, 100, 100),
                merge_nms_threshold=0.5,
            )

        self.assertEqual([item.score for item in merged], [0.9, 0.7])

    def test_decode_outputs_has_expected_grid_and_stride_geometry(self) -> None:
        anchor_count = (32 // 8) ** 2 + (32 // 16) ** 2 + (32 // 32) ** 2
        raw = np.zeros((1, anchor_count, 6), dtype=np.float32)
        decoded = decode_outputs(raw, (32, 32))

        np.testing.assert_array_equal(decoded[0, 0, :4], [0, 0, 8, 8])
        np.testing.assert_array_equal(decoded[0, 1, :4], [8, 0, 8, 8])
        np.testing.assert_array_equal(decoded[0, 16, :4], [0, 0, 16, 16])


if __name__ == "__main__":
    unittest.main()
