"""Detect, track, and audit bidirectional pedestrian crossings in a video."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import platform
import sys
import tempfile
from dataclasses import dataclass, field
from importlib.metadata import PackageNotFoundError, version as package_version
from pathlib import Path
from types import SimpleNamespace
from typing import Iterable, Protocol

import cv2
import numpy as np
import onnxruntime as ort
from scipy.optimize import linear_sum_assignment

from .yolox_onnx import Detection, YoloxOnnx, nms


class Detector(Protocol):
    session: ort.InferenceSession

    def predict(self, frame: np.ndarray) -> list[Detection]:
        ...


def sha256(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def write_detection_cache(
    path: Path,
    frames: list[list[Detection]],
    metadata: dict[str, object],
) -> None:
    """Persist exact post-tile-NMS detections for tracker-only replay."""
    offsets = [0]
    boxes: list[np.ndarray] = []
    scores: list[float] = []
    class_ids: list[int] = []
    for detections in frames:
        for detection in detections:
            boxes.append(detection.xyxy.astype(np.float32, copy=False))
            scores.append(detection.score)
            class_ids.append(detection.class_id)
        offsets.append(len(boxes))

    box_array = (
        np.stack(boxes).astype(np.float32, copy=False)
        if boxes
        else np.empty((0, 4), dtype=np.float32)
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as stream:
        np.savez_compressed(
            stream,
            offsets=np.asarray(offsets, dtype=np.int64),
            boxes=box_array,
            scores=np.asarray(scores, dtype=np.float32),
            class_ids=np.asarray(class_ids, dtype=np.int16),
            metadata_json=np.asarray(
                json.dumps(metadata, sort_keys=True, ensure_ascii=False)
            ),
        )


def load_detection_cache(
    path: Path,
) -> tuple[dict[str, object], np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Load a detector cache without allowing pickle-backed objects."""
    with np.load(path, allow_pickle=False) as payload:
        metadata = json.loads(str(payload["metadata_json"].item()))
        offsets = payload["offsets"].astype(np.int64, copy=True)
        boxes = payload["boxes"].astype(np.float32, copy=True)
        scores = payload["scores"].astype(np.float32, copy=True)
        class_ids = payload["class_ids"].astype(np.int16, copy=True)
    if (
        offsets.ndim != 1
        or boxes.ndim != 2
        or boxes.shape[1:] != (4,)
        or scores.ndim != 1
        or class_ids.ndim != 1
        or len(boxes) != len(scores)
        or len(boxes) != len(class_ids)
        or len(offsets) < 1
        or offsets[0] != 0
        or offsets[-1] != len(boxes)
        or np.any(np.diff(offsets) < 0)
    ):
        raise ValueError(f"Malformed detection cache: {path}")
    return metadata, offsets, boxes, scores, class_ids


def detections_for_cached_frame(
    frame_index: int,
    offsets: np.ndarray,
    boxes: np.ndarray,
    scores: np.ndarray,
    class_ids: np.ndarray,
) -> list[Detection]:
    """Reconstruct one frame's immutable detector output."""
    if frame_index < 0 or frame_index + 1 >= len(offsets):
        raise IndexError(f"Frame {frame_index} is not present in detection cache")
    start = int(offsets[frame_index])
    end = int(offsets[frame_index + 1])
    return [
        Detection(
            xyxy=boxes[index].copy(),
            score=float(scores[index]),
            class_id=int(class_ids[index]),
        )
        for index in range(start, end)
    ]


def center(box: np.ndarray) -> np.ndarray:
    return np.array(
        [(box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0],
        dtype=np.float32,
    )


def intersection_over_union(first: np.ndarray, second: np.ndarray) -> float:
    x1 = max(float(first[0]), float(second[0]))
    y1 = max(float(first[1]), float(second[1]))
    x2 = min(float(first[2]), float(second[2]))
    y2 = min(float(first[3]), float(second[3]))
    width = max(0.0, x2 - x1)
    height = max(0.0, y2 - y1)
    intersection = width * height
    first_area = max(0.0, float(first[2] - first[0])) * max(
        0.0, float(first[3] - first[1])
    )
    second_area = max(0.0, float(second[2] - second[0])) * max(
        0.0, float(second[3] - second[1])
    )
    union = first_area + second_area - intersection
    return intersection / union if union > 0 else 0.0


@dataclass
class Track:
    track_id: int
    box: np.ndarray
    score: float
    hits: int = 1
    missed: int = 0
    velocity: np.ndarray = field(
        default_factory=lambda: np.zeros(2, dtype=np.float32)
    )
    history: list[tuple[int, float, float, float]] = field(default_factory=list)
    stable_side: int = 0
    stable_side_x: float | None = None
    candidate_side: int = 0
    candidate_side_frames: int = 0
    previous_crossing_frame: int | None = None
    counted: bool = False

    @property
    def centroid(self) -> np.ndarray:
        return center(self.box)

    def predicted_box(self) -> np.ndarray:
        delta = np.array(
            [self.velocity[0], self.velocity[1], self.velocity[0], self.velocity[1]],
            dtype=np.float32,
        )
        return self.box + delta


class MultiObjectTracker:
    """Transparent constant-velocity tracker with Hungarian association."""

    def __init__(
        self,
        max_missed: int = 20,
        min_hits: int = 4,
        max_center_distance: float = 70.0,
        minimum_new_track_score: float = 0.25,
    ) -> None:
        self.max_missed = max_missed
        self.min_hits = min_hits
        self.max_center_distance = max_center_distance
        self.minimum_new_track_score = minimum_new_track_score
        self.tracks: list[Track] = []
        self.next_track_id = 1

    def is_confirmed(self, track: Track) -> bool:
        return track.hits >= self.min_hits

    def _cost(self, track: Track, detection: Detection) -> float:
        predicted = track.predicted_box()
        overlap = intersection_over_union(predicted, detection.xyxy)
        distance = float(np.linalg.norm(center(predicted) - center(detection.xyxy)))
        if distance > self.max_center_distance and overlap < 0.01:
            return 1_000_000.0
        normalized_distance = min(distance / self.max_center_distance, 2.0)
        return 0.65 * (1.0 - overlap) + 0.35 * normalized_distance

    def update(
        self,
        detections: list[Detection],
        frame_index: int,
        time_seconds: float,
    ) -> list[Track]:
        matched_tracks: set[int] = set()
        matched_detections: set[int] = set()

        if self.tracks and detections:
            costs = np.array(
                [
                    [self._cost(track, detection) for detection in detections]
                    for track in self.tracks
                ],
                dtype=np.float64,
            )
            row_indices, column_indices = linear_sum_assignment(costs)
            for row, column in zip(row_indices, column_indices):
                if costs[row, column] >= 1_000_000.0:
                    continue
                track = self.tracks[int(row)]
                detection = detections[int(column)]
                old_center = track.centroid
                new_center = center(detection.xyxy)
                observed_velocity = new_center - old_center
                track.velocity = 0.65 * track.velocity + 0.35 * observed_velocity
                track.box = detection.xyxy.copy()
                track.score = detection.score
                track.hits += 1
                track.missed = 0
                matched_tracks.add(int(row))
                matched_detections.add(int(column))

        for index, track in enumerate(self.tracks):
            if index not in matched_tracks:
                track.box = track.predicted_box()
                track.missed += 1
            point = track.centroid
            track.history.append(
                (frame_index, time_seconds, float(point[0]), float(point[1]))
            )

        self.tracks = [
            track for track in self.tracks if track.missed <= self.max_missed
        ]

        for index, detection in enumerate(detections):
            if (
                index not in matched_detections
                and detection.score >= self.minimum_new_track_score
            ):
                point = center(detection.xyxy)
                track = Track(
                    track_id=self.next_track_id,
                    box=detection.xyxy.copy(),
                    score=detection.score,
                    history=[
                        (
                            frame_index,
                            time_seconds,
                            float(point[0]),
                            float(point[1]),
                        )
                    ],
                )
                self.next_track_id += 1
                self.tracks.append(track)

        return list(self.tracks)


class ByteTrackAdapter:
    """Adapter around Supervision's MIT-licensed ByteTrack implementation."""

    def __init__(
        self,
        frame_rate: float,
        track_activation_threshold: float = 0.15,
        lost_track_buffer: int = 30,
        minimum_matching_threshold: float = 0.8,
        minimum_consecutive_frames: int = 3,
    ) -> None:
        cache_dir = Path(tempfile.gettempdir()) / "htx-matplotlib-cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        os.environ.setdefault("MPLCONFIGDIR", str(cache_dir))
        try:
            import supervision as sv
        except ImportError as exc:
            raise RuntimeError(
                "ByteTrack is an optional sensitivity check. Create a separate "
                ".venv-bytetrack and install requirements-bytetrack.txt; do not "
                "mix opencv-python with the base environment's "
                "opencv-python-headless package."
            ) from exc

        self.sv = sv
        self.tracker = sv.ByteTrack(
            track_activation_threshold=track_activation_threshold,
            lost_track_buffer=lost_track_buffer,
            minimum_matching_threshold=minimum_matching_threshold,
            frame_rate=max(1, int(round(frame_rate))),
            minimum_consecutive_frames=minimum_consecutive_frames,
        )
        self.track_states: dict[int, Track] = {}
        self.tracks: list[Track] = []

    def is_confirmed(self, track: Track) -> bool:
        return True

    def update(
        self,
        detections: list[Detection],
        frame_index: int,
        time_seconds: float,
    ) -> list[Track]:
        if detections:
            xyxy = np.stack([detection.xyxy for detection in detections])
            confidence = np.array(
                [detection.score for detection in detections],
                dtype=np.float32,
            )
            class_id = np.zeros(len(detections), dtype=int)
        else:
            xyxy = np.empty((0, 4), dtype=np.float32)
            confidence = np.empty((0,), dtype=np.float32)
            class_id = np.empty((0,), dtype=int)

        tracked = self.tracker.update_with_detections(
            self.sv.Detections(
                xyxy=xyxy,
                confidence=confidence,
                class_id=class_id,
            )
        )
        active: list[Track] = []
        if tracked.tracker_id is None:
            self.tracks = active
            return active

        for box, score, tracker_id in zip(
            tracked.xyxy,
            tracked.confidence,
            tracked.tracker_id,
        ):
            track_id = int(tracker_id)
            point = center(box)
            if track_id in self.track_states:
                track = self.track_states[track_id]
                track.velocity = point - track.centroid
                track.box = box.astype(np.float32)
                track.score = float(score)
                track.hits += 1
                track.missed = 0
                track.history.append(
                    (
                        frame_index,
                        time_seconds,
                        float(point[0]),
                        float(point[1]),
                    )
                )
            else:
                track = Track(
                    track_id=track_id,
                    box=box.astype(np.float32),
                    score=float(score),
                    history=[
                        (
                            frame_index,
                            time_seconds,
                            float(point[0]),
                            float(point[1]),
                        )
                    ],
                )
                self.track_states[track_id] = track
            active.append(track)

        self.tracks = active
        return active


class UltralyticsTrackerAdapter:
    """Adapter for Ultralytics ByteTrack and BoT-SORT tracker backends.

    The adapter consumes the same already-merged detections as the transparent
    Hungarian tracker. Ultralytics remains an optional, AGPL-3.0 experimental
    dependency and is imported only when this backend is selected. This is not
    the repository's private-deployment baseline; see LICENSING.md.
    """

    def __init__(
        self,
        backend: str,
        track_high_threshold: float = 0.10,
        track_low_threshold: float = 0.05,
        new_track_threshold: float = 0.12,
        lost_track_buffer: int = 20,
        matching_threshold: float = 0.8,
        gmc_method: str = "sparseOptFlow",
        min_hits: int = 4,
        frame_rate: float = 30.0,
    ) -> None:
        try:
            from ultralytics.engine.results import Boxes
            from ultralytics.trackers.bot_sort import BOTSORT
            from ultralytics.trackers.byte_tracker import BYTETracker
        except ImportError as exc:
            raise RuntimeError(
                "Ultralytics ByteTrack/BoT-SORT is an optional YOLO26 "
                "sensitivity check. Run it from the isolated experimental "
                "environment containing ultralytics."
            ) from exc

        if backend not in {"bytetrack", "botsort"}:
            raise ValueError(f"Unsupported Ultralytics tracker backend: {backend}")
        self.Boxes = Boxes
        tracker_args = SimpleNamespace(
            tracker_type=backend,
            track_high_thresh=track_high_threshold,
            track_low_thresh=track_low_threshold,
            new_track_thresh=new_track_threshold,
            track_buffer=lost_track_buffer,
            match_thresh=matching_threshold,
            fuse_score=True,
            gmc_method=gmc_method,
            proximity_thresh=0.5,
            appearance_thresh=0.8,
            with_reid=False,
            model="auto",
            device="cpu",
        )
        tracker_class = BYTETracker if backend == "bytetrack" else BOTSORT
        self.tracker = tracker_class(
            tracker_args,
            frame_rate=max(1, int(round(frame_rate))),
        )
        self.backend = backend
        self.min_hits = min_hits
        self.track_states: dict[int, Track] = {}
        self.tracks: list[Track] = []

    def is_confirmed(self, track: Track) -> bool:
        return track.hits >= self.min_hits

    def update(
        self,
        detections: list[Detection],
        frame_index: int,
        time_seconds: float,
        frame: np.ndarray | None = None,
    ) -> list[Track]:
        if frame is None:
            raise ValueError("Ultralytics trackers require the current frame")
        if detections:
            rows = np.array(
                [
                    [
                        *detection.xyxy.tolist(),
                        detection.score,
                        detection.class_id,
                    ]
                    for detection in detections
                ],
                dtype=np.float32,
            )
        else:
            rows = np.empty((0, 6), dtype=np.float32)
        results = self.Boxes(rows, frame.shape[:2])
        tracked_rows = self.tracker.update(results, img=frame)

        active: list[Track] = []
        for row in tracked_rows:
            box = np.asarray(row[:4], dtype=np.float32)
            track_id = int(round(float(row[4])))
            score = float(row[5])
            point = center(box)
            if track_id in self.track_states:
                track = self.track_states[track_id]
                track.velocity = point - track.centroid
                track.box = box
                track.score = score
                track.hits += 1
                track.missed = 0
                track.history.append(
                    (
                        frame_index,
                        time_seconds,
                        float(point[0]),
                        float(point[1]),
                    )
                )
            else:
                track = Track(
                    track_id=track_id,
                    box=box,
                    score=score,
                    history=[
                        (
                            frame_index,
                            time_seconds,
                            float(point[0]),
                            float(point[1]),
                        )
                    ],
                )
                self.track_states[track_id] = track
            active.append(track)

        self.tracks = active
        return active


def filter_roi(
    detections: Iterable[Detection],
    roi: tuple[int, int, int, int],
) -> list[Detection]:
    x1, y1, x2, y2 = roi
    selected: list[Detection] = []
    for detection in detections:
        cx, cy = center(detection.xyxy)
        if x1 <= cx <= x2 and y1 <= cy <= y2:
            selected.append(detection)
    return selected


def detect_in_roi(
    detector: Detector,
    frame: np.ndarray,
    roi: tuple[int, int, int, int],
) -> list[Detection]:
    """Run inference on a crop so small overhead pedestrians retain resolution."""
    x1, y1, x2, y2 = roi
    cropped = frame[y1:y2, x1:x2]
    translated: list[Detection] = []
    offset = np.array([x1, y1, x1, y1], dtype=np.float32)
    for detection in detector.predict(cropped):
        translated.append(
            Detection(
                xyxy=detection.xyxy + offset,
                score=detection.score,
                class_id=detection.class_id,
            )
        )
    return filter_roi(translated, roi)


def detect_in_tiles(
    detector: Detector,
    frame: np.ndarray,
    tiles: list[tuple[int, int, int, int]],
    analysis_roi: tuple[int, int, int, int],
    merge_nms_threshold: float = 0.5,
) -> list[Detection]:
    detections: list[Detection] = []
    for tile in tiles:
        detections.extend(detect_in_roi(detector, frame, tile))
    detections = filter_roi(detections, analysis_roi)
    if not detections:
        return []
    boxes = np.stack([detection.xyxy for detection in detections])
    scores = np.array([detection.score for detection in detections], dtype=np.float32)
    keep = nms(boxes, scores, merge_nms_threshold)
    return [detections[index] for index in keep]


def side_of_line(x_coordinate: float, line_x: int, margin: int) -> int:
    if x_coordinate < line_x - margin:
        return -1
    if x_coordinate > line_x + margin:
        return 1
    return 0


def resolve_time_seconds(
    pts_seconds: float,
    frame_index: int,
    fps: float,
) -> float:
    """Prefer a valid presentation timestamp, with frame-rate fallback."""
    if math.isfinite(pts_seconds) and pts_seconds >= 0.0:
        return pts_seconds
    if not math.isfinite(fps) or fps <= 0.0:
        raise ValueError("A positive finite FPS is required when PTS is unavailable")
    return frame_index / fps


def update_crossing(
    track: Track,
    frame_index: int,
    time_seconds: float,
    line_x: int,
    line_margin: int,
    side_confirm_frames: int,
    minimum_crossing_displacement: float,
) -> dict[str, object] | None:
    if (
        track.previous_crossing_frame is not None
        and frame_index != track.previous_crossing_frame + 1
    ):
        track.candidate_side = 0
        track.candidate_side_frames = 0
    track.previous_crossing_frame = frame_index

    current_side = side_of_line(float(track.centroid[0]), line_x, line_margin)
    if current_side == 0:
        track.candidate_side = 0
        track.candidate_side_frames = 0
        return None
    if current_side == track.candidate_side:
        track.candidate_side_frames += 1
    else:
        track.candidate_side = current_side
        track.candidate_side_frames = 1
    if track.candidate_side_frames < side_confirm_frames:
        return None
    if track.stable_side == 0:
        track.stable_side = current_side
        track.stable_side_x = float(track.centroid[0])
        return None
    if track.counted or current_side == track.stable_side:
        return None
    if track.stable_side_x is None or (
        abs(float(track.centroid[0]) - track.stable_side_x)
        < minimum_crossing_displacement
    ):
        return None

    direction = "left_to_right" if track.stable_side == -1 else "right_to_left"
    track.counted = True
    track.stable_side = current_side
    track.stable_side_x = float(track.centroid[0])
    return {
        "track_id": track.track_id,
        "frame_index": frame_index,
        "time_seconds": round(time_seconds, 6),
        "direction": direction,
        "centroid_x": round(float(track.centroid[0]), 3),
        "centroid_y": round(float(track.centroid[1]), 3),
        "confidence": round(track.score, 6),
    }


def draw_frame(
    frame: np.ndarray,
    tracks: Iterable[Track],
    tracker: MultiObjectTracker | ByteTrackAdapter | UltralyticsTrackerAdapter,
    roi: tuple[int, int, int, int],
    line_x: int,
    counts: dict[str, int],
) -> np.ndarray:
    annotated = frame.copy()
    x1, y1, x2, y2 = roi
    cv2.rectangle(annotated, (x1, y1), (x2, y2), (255, 180, 0), 2)
    cv2.line(annotated, (line_x, y1), (line_x, y2), (0, 255, 255), 2)

    for track in tracks:
        if not tracker.is_confirmed(track):
            continue
        bx1, by1, bx2, by2 = (int(round(value)) for value in track.box)
        color = (65, 220, 65) if track.missed == 0 else (120, 120, 120)
        cv2.rectangle(annotated, (bx1, by1), (bx2, by2), color, 2)
        cv2.putText(
            annotated,
            f"ID {track.track_id} {track.score:.2f}",
            (bx1, max(16, by1 - 5)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.48,
            color,
            1,
            cv2.LINE_AA,
        )

    cv2.rectangle(annotated, (8, 8), (390, 72), (0, 0, 0), thickness=-1)
    cv2.putText(
        annotated,
        f"L->R: {counts['left_to_right']}   R->L: {counts['right_to_left']}",
        (18, 36),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (255, 255, 255),
        2,
        cv2.LINE_AA,
    )
    cv2.putText(
        annotated,
        "ROI excludes lower-half glass reflection",
        (18, 61),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.48,
        (255, 220, 80),
        1,
        cv2.LINE_AA,
    )
    return annotated


def parse_roi(text: str) -> tuple[int, int, int, int]:
    values = tuple(int(value.strip()) for value in text.split(","))
    if len(values) != 4:
        raise ValueError("--roi must be x1,y1,x2,y2")
    x1, y1, x2, y2 = values
    if x1 >= x2 or y1 >= y2:
        raise ValueError("--roi must have x1<x2 and y1<y2")
    return x1, y1, x2, y2


def parse_tiles(
    text: str | None,
    fallback_roi: tuple[int, int, int, int],
) -> list[tuple[int, int, int, int]]:
    if text is None:
        return [fallback_roi]
    tiles = [parse_roi(part.strip()) for part in text.split(";") if part.strip()]
    if not tiles:
        raise ValueError("--inference-tiles must contain at least one ROI")
    return tiles


def write_csv(path: Path, rows: list[dict[str, object]], fields: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def run(args: argparse.Namespace) -> dict[str, object]:
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    video_path = args.video.resolve()
    model_path = args.model.resolve()
    source_sha256 = sha256(video_path)
    model_sha256 = sha256(model_path)
    if args.detector == "yolo26":
        from .yolo26_onnx import Yolo26Onnx

        detector: Detector = Yolo26Onnx(
            model_path,
            confidence_threshold=args.confidence_threshold,
        )
    else:
        detector = YoloxOnnx(
            model_path,
            confidence_threshold=args.confidence_threshold,
            nms_threshold=args.nms_threshold,
        )
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise RuntimeError(f"Could not open video: {video_path}")
    frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = float(capture.get(cv2.CAP_PROP_FPS))
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    if args.tracker == "bytetrack":
        tracker: (
            MultiObjectTracker
            | ByteTrackAdapter
            | UltralyticsTrackerAdapter
        ) = ByteTrackAdapter(
            frame_rate=fps,
            track_activation_threshold=args.track_activation_threshold,
            lost_track_buffer=args.max_missed,
            minimum_matching_threshold=args.minimum_matching_threshold,
            minimum_consecutive_frames=args.min_hits,
        )
    elif args.tracker in {"ultralytics_bytetrack", "botsort"}:
        tracker = UltralyticsTrackerAdapter(
            backend=(
                "bytetrack"
                if args.tracker == "ultralytics_bytetrack"
                else "botsort"
            ),
            track_high_threshold=args.track_activation_threshold,
            track_low_threshold=args.confidence_threshold,
            new_track_threshold=args.new_track_threshold,
            lost_track_buffer=args.max_missed,
            matching_threshold=args.minimum_matching_threshold,
            gmc_method=args.botsort_gmc_method,
            min_hits=args.min_hits,
            frame_rate=fps,
        )
    else:
        tracker = MultiObjectTracker(
            max_missed=args.max_missed,
            min_hits=args.min_hits,
            max_center_distance=args.max_center_distance,
            minimum_new_track_score=args.new_track_threshold,
        )
    roi = parse_roi(args.roi)
    if not (0 <= roi[0] < roi[2] <= width and 0 <= roi[1] < roi[3] <= height):
        raise ValueError(f"ROI {roi} exceeds video dimensions {width}x{height}")
    if not roi[0] <= args.line_x <= roi[2]:
        raise ValueError("--line-x must fall inside the ROI")
    tiles = parse_tiles(args.inference_tiles, roi)
    for tile in tiles:
        if not (
            0 <= tile[0] < tile[2] <= width
            and 0 <= tile[1] < tile[3] <= height
        ):
            raise ValueError(f"Inference tile {tile} exceeds {width}x{height}")

    cache_metadata = {
        "schema_version": "1.0",
        "source_sha256": source_sha256,
        "model_sha256": model_sha256,
        "detector": args.detector,
        "frame_count": frame_count,
        "roi_xyxy": list(roi),
        "inference_tiles_xyxy": [list(tile) for tile in tiles],
        "confidence_threshold": args.confidence_threshold,
        "cross_tile_nms_threshold": 0.5,
    }
    cached_payload: (
        tuple[dict[str, object], np.ndarray, np.ndarray, np.ndarray, np.ndarray]
        | None
    ) = None
    detection_cache_in = (
        args.detection_cache_in.resolve()
        if args.detection_cache_in is not None
        else None
    )
    detection_cache_out = (
        args.detection_cache_out.resolve()
        if args.detection_cache_out is not None
        else None
    )
    if detection_cache_in is not None:
        cached_payload = load_detection_cache(detection_cache_in)
        actual_metadata = cached_payload[0]
        for key, expected_value in cache_metadata.items():
            if actual_metadata.get(key) != expected_value:
                raise ValueError(
                    f"Detection cache mismatch for {key}: "
                    f"{actual_metadata.get(key)!r} != {expected_value!r}"
                )
    detections_to_cache: list[list[Detection]] = []

    annotated_path = output_dir / "annotated_crossings.mp4"
    writer = cv2.VideoWriter(
        str(annotated_path),
        cv2.VideoWriter_fourcc(*"mp4v"),
        fps,
        (width, height),
    )
    if not writer.isOpened():
        raise RuntimeError(f"Could not create annotated video: {annotated_path}")

    crossings: list[dict[str, object]] = []
    observations: list[dict[str, object]] = []
    counts = {"left_to_right": 0, "right_to_left": 0}
    frame_index = 0

    while True:
        ok, frame = capture.read()
        if not ok:
            break
        if args.max_frames and frame_index >= args.max_frames:
            break
        pts_seconds = float(capture.get(cv2.CAP_PROP_POS_MSEC)) / 1000.0
        time_seconds = resolve_time_seconds(pts_seconds, frame_index, fps)
        if cached_payload is None:
            detections = detect_in_tiles(detector, frame, tiles, roi)
        else:
            _, offsets, boxes, scores, class_ids = cached_payload
            detections = detections_for_cached_frame(
                frame_index,
                offsets,
                boxes,
                scores,
                class_ids,
            )
        if detection_cache_out is not None:
            detections_to_cache.append(detections)
        if isinstance(tracker, UltralyticsTrackerAdapter):
            tracks = tracker.update(
                detections,
                frame_index,
                time_seconds,
                frame=frame,
            )
        else:
            tracks = tracker.update(detections, frame_index, time_seconds)

        for track in tracks:
            if not tracker.is_confirmed(track) or track.missed > 0:
                continue
            point = track.centroid
            observations.append(
                {
                    "frame_index": frame_index,
                    "time_seconds": round(time_seconds, 6),
                    "track_id": track.track_id,
                    "centroid_x": round(float(point[0]), 3),
                    "centroid_y": round(float(point[1]), 3),
                    "x1": round(float(track.box[0]), 3),
                    "y1": round(float(track.box[1]), 3),
                    "x2": round(float(track.box[2]), 3),
                    "y2": round(float(track.box[3]), 3),
                    "confidence": round(track.score, 6),
                }
            )
            event = update_crossing(
                track,
                frame_index,
                time_seconds,
                args.line_x,
                args.line_margin,
                args.side_confirm_frames,
                args.minimum_crossing_displacement,
            )
            if event is not None:
                counts[str(event["direction"])] += 1
                event["event_id"] = len(crossings) + 1
                crossings.append(event)

        writer.write(
            draw_frame(
                frame,
                tracks,
                tracker,
                roi,
                args.line_x,
                counts,
            )
        )
        frame_index += 1
        if frame_index % 100 == 0:
            print(
                f"processed={frame_index}/{frame_count} "
                f"L->R={counts['left_to_right']} R->L={counts['right_to_left']}",
                flush=True,
            )

    capture.release()
    writer.release()
    duration_seconds = frame_index / fps
    if detection_cache_out is not None:
        output_cache_metadata = dict(cache_metadata)
        output_cache_metadata["frames_cached"] = len(detections_to_cache)
        write_detection_cache(
            detection_cache_out,
            detections_to_cache,
            output_cache_metadata,
        )

    crossing_fields = [
        "event_id",
        "track_id",
        "frame_index",
        "time_seconds",
        "direction",
        "centroid_x",
        "centroid_y",
        "confidence",
    ]
    observation_fields = [
        "frame_index",
        "time_seconds",
        "track_id",
        "centroid_x",
        "centroid_y",
        "x1",
        "y1",
        "x2",
        "y2",
        "confidence",
    ]
    write_csv(output_dir / "crossing_ledger.csv", crossings, crossing_fields)
    write_csv(output_dir / "track_observations.csv", observations, observation_fields)

    if args.tracker == "hungarian":
        tracker_config: dict[str, object] = {
            "backend": "constant_velocity_hungarian",
            "max_center_distance_px": args.max_center_distance,
            "minimum_new_track_score": args.new_track_threshold,
            "max_missed_frames": args.max_missed,
            "minimum_detector_matches": args.min_hits,
        }
    elif args.tracker == "bytetrack":
        try:
            supervision_version: str | None = package_version("supervision")
        except PackageNotFoundError:
            supervision_version = None
        tracker_config = {
            "backend": "supervision_bytetrack",
            "supervision_version": supervision_version,
            "track_activation_threshold": args.track_activation_threshold,
            "minimum_matching_threshold": args.minimum_matching_threshold,
            "lost_track_buffer": args.max_missed,
            "minimum_consecutive_frames": args.min_hits,
        }
    else:
        try:
            ultralytics_version: str | None = package_version("ultralytics")
        except PackageNotFoundError:
            ultralytics_version = None
        tracker_config = {
            "backend": (
                "ultralytics_bytetrack"
                if args.tracker == "ultralytics_bytetrack"
                else "ultralytics_botsort"
            ),
            "ultralytics_version": ultralytics_version,
            "track_high_threshold": args.track_activation_threshold,
            "track_low_threshold": args.confidence_threshold,
            "new_track_threshold": args.new_track_threshold,
            "track_buffer": args.max_missed,
            "matching_threshold": args.minimum_matching_threshold,
            "fuse_score": True,
            "gmc_method": (
                args.botsort_gmc_method if args.tracker == "botsort" else None
            ),
            "with_reid": False if args.tracker == "botsort" else None,
            "external_min_output_hits": args.min_hits,
            "external_min_output_hits_note": (
                "Counts emitted tracker observations, not raw detector matches."
            ),
        }

    summary: dict[str, object] = {
        "schema_version": "1.0",
        "source_file": video_path.name,
        "source_sha256": source_sha256,
        "model_file": args.model.name,
        "model_sha256": model_sha256,
        "detector": args.detector,
        "runtime": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "opencv": cv2.__version__,
            "numpy": np.__version__,
            "onnxruntime": ort.__version__,
            "onnx_execution_providers": detector.session.get_providers(),
            "command": [str(value) for value in sys.argv],
        },
        "detection_cache": {
            "input_file": (
                detection_cache_in.name
                if detection_cache_in is not None
                else None
            ),
            "input_sha256": (
                sha256(detection_cache_in)
                if detection_cache_in is not None
                else None
            ),
            "output_file": (
                detection_cache_out.name
                if detection_cache_out is not None
                else None
            ),
            "output_sha256": (
                sha256(detection_cache_out)
                if detection_cache_out is not None
                else None
            ),
        },
        "frames_processed": frame_index,
        "fps": round(fps, 9),
        "duration_seconds": round(duration_seconds, 9),
        "roi_xyxy": list(roi),
        "inference_tiles_xyxy": [list(tile) for tile in tiles],
        "cross_tile_nms_threshold": 0.5,
        "count_line_x": args.line_x,
        "count_line_margin_px": args.line_margin,
        "side_confirm_frames": args.side_confirm_frames,
        "minimum_crossing_displacement_px": args.minimum_crossing_displacement,
        "confidence_threshold": args.confidence_threshold,
        "tracker": args.tracker,
        "tracker_config": tracker_config,
        "counts": counts,
        "crossing_rate_per_second": {
            direction: round(count / duration_seconds, 6)
            for direction, count in counts.items()
        },
        "total_crossing_rate_per_second": round(
            sum(counts.values()) / duration_seconds,
            6,
        ),
        "confirmed_observation_rows": len(observations),
        "note": (
            "Automated output is a candidate ledger. Manual frame-level audit is "
            "required before parameters are frozen for simulation."
        ),
    }
    (output_dir / "run_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", required=True, type=Path)
    parser.add_argument("--model", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument(
        "--detection-cache-in",
        type=Path,
        help="Replay exact post-tile-NMS detections from an NPZ cache.",
    )
    parser.add_argument(
        "--detection-cache-out",
        type=Path,
        help="Write exact post-tile-NMS detections to an NPZ cache.",
    )
    parser.add_argument(
        "--detector",
        choices=("yolox", "yolo26"),
        default="yolox",
        help=(
            "ONNX detector family. Defaults to the reproducible YOLOX baseline; "
            "YOLO26 models carry the Ultralytics licence boundary."
        ),
    )
    parser.add_argument("--roi", default="0,0,1280,310")
    parser.add_argument(
        "--inference-tiles",
        default="0,0,720,310;560,0,1280,310",
        help="Semicolon-separated x1,y1,x2,y2 inference tiles.",
    )
    parser.add_argument("--line-x", type=int, default=640)
    parser.add_argument("--line-margin", type=int, default=12)
    parser.add_argument("--side-confirm-frames", type=int, default=3)
    parser.add_argument("--minimum-crossing-displacement", type=float, default=24.0)
    parser.add_argument("--confidence-threshold", type=float, default=0.05)
    parser.add_argument(
        "--tracker",
        choices=(
            "bytetrack",
            "hungarian",
            "ultralytics_bytetrack",
            "botsort",
        ),
        default="hungarian",
        help=(
            "Tracker backend. ultralytics_bytetrack and botsort use the "
            "AGPL-3.0 Ultralytics implementation; see LICENSING.md."
        ),
    )
    parser.add_argument("--track-activation-threshold", type=float, default=0.10)
    parser.add_argument("--minimum-matching-threshold", type=float, default=0.8)
    parser.add_argument(
        "--botsort-gmc-method",
        choices=("sparseOptFlow", "orb", "sift", "ecc", "none"),
        default="sparseOptFlow",
    )
    parser.add_argument("--new-track-threshold", type=float, default=0.12)
    parser.add_argument("--nms-threshold", type=float, default=0.45)
    parser.add_argument("--min-hits", type=int, default=4)
    parser.add_argument("--max-missed", type=int, default=20)
    parser.add_argument("--max-center-distance", type=float, default=70.0)
    parser.add_argument("--max-frames", type=int, default=0)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if (
        args.detection_cache_in is not None
        and args.detection_cache_out is not None
    ):
        raise ValueError(
            "--detection-cache-in and --detection-cache-out are mutually exclusive"
        )
    if not 0.0 < args.confidence_threshold <= 1.0:
        raise ValueError("--confidence-threshold must be in (0, 1]")
    if (
        args.tracker == "hungarian"
        and args.new_track_threshold < args.confidence_threshold
    ):
        raise ValueError("--new-track-threshold cannot be below detection threshold")
    if (
        args.min_hits < 1
        or args.max_missed < 0
        or args.line_margin < 0
        or args.side_confirm_frames < 1
        or args.minimum_crossing_displacement < 0
    ):
        raise ValueError("Tracker and line parameters must be non-negative")
    summary = run(args)
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
