"""Create large, non-generative event-review panels for owner sign-off.

The output uses only decoded source-video pixels plus deterministic crop,
resize, line, bounding-box, centroid, and text overlays. It deliberately does
not sharpen, interpolate with AI, or synthesize missing detail.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

import cv2
import numpy as np


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def bounded_origin(center: float, size: int, lower: int, upper: int) -> int:
    """Return a crop origin that keeps ``size`` pixels inside [lower, upper)."""
    if size > upper - lower:
        raise ValueError("Crop size exceeds the available image interval")
    return min(max(int(round(center - size / 2)), lower), upper - size)


def nearest_observation(
    observations: list[dict[str, str]],
    frame_index: int,
    maximum_gap: int,
) -> dict[str, str] | None:
    if not observations:
        return None
    observation = min(
        observations,
        key=lambda item: abs(int(item["frame_index"]) - frame_index),
    )
    if abs(int(observation["frame_index"]) - frame_index) > maximum_gap:
        return None
    return observation


def render_panel(
    frame: np.ndarray,
    observation: dict[str, str] | None,
    crop: tuple[int, int, int, int],
    line_x: int,
    label: str,
    scale: int,
) -> np.ndarray:
    x1, y1, x2, y2 = crop
    panel = frame[y1:y2, x1:x2].copy()
    local_line_x = line_x - x1
    cv2.line(
        panel,
        (local_line_x, 0),
        (local_line_x, panel.shape[0] - 1),
        (0, 255, 255),
        3,
    )

    if observation is not None:
        bx1 = int(round(float(observation["x1"]))) - x1
        by1 = int(round(float(observation["y1"]))) - y1
        bx2 = int(round(float(observation["x2"]))) - x1
        by2 = int(round(float(observation["y2"]))) - y1
        cx = int(round(float(observation["centroid_x"]))) - x1
        cy = int(round(float(observation["centroid_y"]))) - y1
        cv2.rectangle(panel, (bx1, by1), (bx2, by2), (30, 255, 30), 4)
        cv2.circle(panel, (cx, cy), 8, (0, 0, 255), thickness=-1)

    panel = cv2.resize(
        panel,
        (panel.shape[1] * scale, panel.shape[0] * scale),
        interpolation=cv2.INTER_NEAREST,
    )
    label_height = 58
    labelled = np.zeros(
        (panel.shape[0] + label_height, panel.shape[1], 3),
        dtype=np.uint8,
    )
    labelled[label_height:, :] = panel
    cv2.putText(
        labelled,
        label,
        (16, 39),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.9,
        (255, 255, 255),
        2,
        cv2.LINE_AA,
    )
    return labelled


def render_event(
    capture: cv2.VideoCapture,
    event: dict[str, str],
    observations: list[dict[str, str]],
    frame_count: int,
    fps: float,
    line_x: int,
    roi_y_max: int,
    crop_width: int,
    crop_height: int,
    frame_step: int,
    scale: int,
) -> np.ndarray:
    event_frame = int(event["frame_index"])
    center_y = float(event["centroid_y"])
    frame_width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    roi_y_max = min(roi_y_max, frame_height)
    x1 = bounded_origin(line_x, crop_width, 0, frame_width)
    y1 = bounded_origin(center_y, crop_height, 0, roi_y_max)
    crop = (x1, y1, x1 + crop_width, y1 + crop_height)

    panels: list[np.ndarray] = []
    for multiplier in (-2, -1, 0, 1, 2):
        offset = multiplier * frame_step
        frame_index = min(max(event_frame + offset, 0), frame_count - 1)
        capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
        ok, frame = capture.read()
        if not ok:
            raise RuntimeError(f"Could not decode frame {frame_index}")
        pts = float(capture.get(cv2.CAP_PROP_POS_MSEC)) / 1000.0
        relative_seconds = offset / fps
        observation = nearest_observation(
            observations,
            frame_index=frame_index,
            maximum_gap=3,
        )
        panels.append(
            render_panel(
                frame=frame,
                observation=observation,
                crop=crop,
                line_x=line_x,
                label=(
                    f"{relative_seconds:+.2f} s from candidate | "
                    f"video t={pts:.2f} s | frame={frame_index}"
                ),
                scale=scale,
            )
        )

    body = np.vstack(panels)
    title_height = 88
    output = np.zeros(
        (body.shape[0] + title_height, body.shape[1], 3),
        dtype=np.uint8,
    )
    output[title_height:, :] = body
    title = (
        f"E{event['event_id']} | track {event['track_id']} | "
        f"candidate direction: {event['direction']} | "
        f"candidate t={float(event['time_seconds']):.3f} s"
    )
    cv2.putText(
        output,
        title,
        (16, 42),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.82,
        (255, 255, 255),
        2,
        cv2.LINE_AA,
    )
    cv2.putText(
        output,
        "Green box = target track | red dot = centroid | yellow = count line",
        (16, 72),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.62,
        (190, 190, 190),
        1,
        cv2.LINE_AA,
    )
    return output


def run(args: argparse.Namespace) -> None:
    events = read_rows(args.ledger.resolve())
    selected_ids = {
        int(value.strip())
        for value in args.event_ids.split(",")
        if value.strip()
    }
    events = [
        event for event in events if int(event["event_id"]) in selected_ids
    ]
    if len(events) != len(selected_ids):
        found = {int(event["event_id"]) for event in events}
        raise ValueError(f"Missing event IDs: {sorted(selected_ids - found)}")

    observations_by_track: dict[int, list[dict[str, str]]] = {}
    for observation in read_rows(args.observations.resolve()):
        observations_by_track.setdefault(
            int(observation["track_id"]),
            [],
        ).append(observation)

    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    capture = cv2.VideoCapture(str(args.video.resolve()))
    if not capture.isOpened():
        raise RuntimeError(f"Could not open video: {args.video}")
    frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = float(capture.get(cv2.CAP_PROP_FPS))
    if frame_count <= 0 or fps <= 0:
        raise RuntimeError("Video frame count and FPS must be positive")

    for event in events:
        event_id = int(event["event_id"])
        image = render_event(
            capture=capture,
            event=event,
            observations=observations_by_track.get(int(event["track_id"]), []),
            frame_count=frame_count,
            fps=fps,
            line_x=args.line_x,
            roi_y_max=args.roi_y_max,
            crop_width=args.crop_width,
            crop_height=args.crop_height,
            frame_step=args.frame_step,
            scale=args.scale,
        )
        output_path = output_dir / f"event_{event_id:03d}_zoom.png"
        if not cv2.imwrite(str(output_path), image):
            raise RuntimeError(f"Could not write {output_path}")
        print(output_path)
    capture.release()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", required=True, type=Path)
    parser.add_argument("--ledger", required=True, type=Path)
    parser.add_argument("--observations", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--event-ids", required=True)
    parser.add_argument("--line-x", type=int, default=640)
    parser.add_argument("--roi-y-max", type=int, default=310)
    parser.add_argument("--crop-width", type=int, default=320)
    parser.add_argument("--crop-height", type=int, default=240)
    parser.add_argument("--frame-step", type=int, default=6)
    parser.add_argument("--scale", type=int, default=3)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    for name in ("crop_width", "crop_height", "frame_step", "scale"):
        if getattr(args, name) < 1:
            raise ValueError(f"--{name.replace('_', '-')} must be positive")
    run(args)


if __name__ == "__main__":
    main()
