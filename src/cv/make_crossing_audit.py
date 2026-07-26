"""Create frame-level evidence pages for manual crossing-ledger reconciliation."""

from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path

import cv2
import numpy as np


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def label_panel(
    frame: np.ndarray,
    label: str,
    line_x_local: int,
    width: int = 200,
    height: int = 125,
) -> np.ndarray:
    original_height, original_width = frame.shape[:2]
    scale_x = width / original_width
    resized = cv2.resize(frame, (width, height), interpolation=cv2.INTER_AREA)
    line_x_resized = int(round(line_x_local * scale_x))
    cv2.line(
        resized,
        (line_x_resized, 0),
        (line_x_resized, height),
        (0, 255, 255),
        2,
    )
    overlay = resized.copy()
    cv2.rectangle(overlay, (0, 0), (width, 24), (0, 0, 0), thickness=-1)
    cv2.addWeighted(overlay, 0.68, resized, 0.32, 0, resized)
    cv2.putText(
        resized,
        label,
        (5, 17),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.42,
        (255, 255, 255),
        1,
        cv2.LINE_AA,
    )
    return resized


def make_event_strip(
    capture: cv2.VideoCapture,
    row: dict[str, str],
    frame_count: int,
    fps: float,
    line_x: int,
    crop: tuple[int, int, int, int],
    offsets: list[int],
    observations_by_track: dict[int, list[dict[str, str]]],
) -> np.ndarray:
    event_frame = int(row["frame_index"])
    track_id = int(row["track_id"])
    x1, y1, x2, y2 = crop
    panels: list[np.ndarray] = []
    for offset in offsets:
        frame_index = min(max(event_frame + offset, 0), frame_count - 1)
        capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
        ok, frame = capture.read()
        if not ok:
            raise RuntimeError(f"Could not decode frame {frame_index}")
        pts = float(capture.get(cv2.CAP_PROP_POS_MSEC)) / 1000.0
        relative_seconds = offset / fps
        cropped = frame[y1:y2, x1:x2].copy()
        observation = None
        if track_id in observations_by_track:
            candidates = observations_by_track[track_id]
            observation = min(
                candidates,
                key=lambda item: abs(int(item["frame_index"]) - frame_index),
            )
            if abs(int(observation["frame_index"]) - frame_index) > 3:
                observation = None
        if observation is not None:
            bx1 = int(round(float(observation["x1"]))) - x1
            by1 = int(round(float(observation["y1"]))) - y1
            bx2 = int(round(float(observation["x2"]))) - x1
            by2 = int(round(float(observation["y2"]))) - y1
            cx = int(round(float(observation["centroid_x"]))) - x1
            cy = int(round(float(observation["centroid_y"]))) - y1
            cv2.rectangle(cropped, (bx1, by1), (bx2, by2), (50, 255, 50), 3)
            cv2.circle(cropped, (cx, cy), 7, (0, 0, 255), thickness=-1)
        panels.append(
            label_panel(
                cropped,
                f"{relative_seconds:+.2f}s | t={pts:.2f}",
                line_x - x1,
            )
        )
    strip = np.hstack(panels)
    header = np.zeros((35, strip.shape[1], 3), dtype=np.uint8)
    title = (
        f"E{row['event_id']}  track={row['track_id']}  "
        f"{row['direction']}  candidate_t={float(row['time_seconds']):.3f}s"
    )
    cv2.putText(
        header,
        title,
        (7, 24),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55,
        (255, 255, 255),
        1,
        cv2.LINE_AA,
    )
    return np.vstack((header, strip))


def write_template(
    path: Path,
    rows: list[dict[str, str]],
) -> None:
    fields = [
        "event_id",
        "track_id",
        "candidate_direction",
        "candidate_time_seconds",
        "decision",
        "corrected_direction",
        "auditor_notes",
    ]
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "event_id": row["event_id"],
                    "track_id": row["track_id"],
                    "candidate_direction": row["direction"],
                    "candidate_time_seconds": row["time_seconds"],
                    "decision": "REVIEW",
                    "corrected_direction": row["direction"],
                    "auditor_notes": "",
                }
            )


def parse_crop(text: str) -> tuple[int, int, int, int]:
    values = tuple(int(value.strip()) for value in text.split(","))
    if len(values) != 4:
        raise ValueError("--crop must be x1,y1,x2,y2")
    x1, y1, x2, y2 = values
    if x1 >= x2 or y1 >= y2:
        raise ValueError("--crop must have x1<x2 and y1<y2")
    return x1, y1, x2, y2


def run(args: argparse.Namespace) -> None:
    rows = read_rows(args.ledger.resolve())
    if args.track_ids:
        selected_track_ids = {
            int(value.strip()) for value in args.track_ids.split(",") if value.strip()
        }
        rows = [
            row for row in rows if int(row["track_id"]) in selected_track_ids
        ]
    if args.line_values:
        selected_lines = {
            int(value.strip()) for value in args.line_values.split(",") if value.strip()
        }
        rows = [
            row
            for row in rows
            if row.get("line_x") and int(row["line_x"]) in selected_lines
        ]
    observations_by_track: dict[int, list[dict[str, str]]] = {}
    if args.observations is not None:
        for observation in read_rows(args.observations.resolve()):
            observations_by_track.setdefault(
                int(observation["track_id"]),
                [],
            ).append(observation)
    output_dir = args.output_dir.resolve()
    strips_dir = output_dir / "event_strips"
    pages_dir = output_dir / "pages"
    strips_dir.mkdir(parents=True, exist_ok=True)
    pages_dir.mkdir(parents=True, exist_ok=True)

    capture = cv2.VideoCapture(str(args.video.resolve()))
    if not capture.isOpened():
        raise RuntimeError(f"Could not open video: {args.video}")
    frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = float(capture.get(cv2.CAP_PROP_FPS))
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    crop = parse_crop(args.crop)
    if not (
        0 <= crop[0] < crop[2] <= width
        and 0 <= crop[1] < crop[3] <= height
    ):
        raise ValueError(f"Crop {crop} exceeds video dimensions {width}x{height}")

    offsets = [
        -args.frame_step * 2,
        -args.frame_step,
        0,
        args.frame_step,
        args.frame_step * 2,
    ]
    strips: list[np.ndarray] = []
    for row in rows:
        event_line_x = (
            int(row["line_x"])
            if row.get("line_x")
            else args.line_x
        )
        if event_line_x is None:
            raise ValueError(
                "Each ledger row needs line_x when --line-x is omitted"
            )
        if not crop[0] <= event_line_x <= crop[2]:
            raise ValueError(f"Line x={event_line_x} falls outside --crop")
        strip = make_event_strip(
            capture,
            row,
            frame_count,
            fps,
            event_line_x,
            crop,
            offsets,
            observations_by_track,
        )
        event_id = int(row["event_id"])
        path = strips_dir / f"event_{event_id:03d}.jpg"
        if not cv2.imwrite(str(path), strip):
            raise RuntimeError(f"Could not write {path}")
        strips.append(strip)
    capture.release()

    for page_index in range(math.ceil(len(strips) / args.events_per_page)):
        start = page_index * args.events_per_page
        page_strips = strips[start : start + args.events_per_page]
        page = np.vstack(page_strips)
        path = pages_dir / f"audit_page_{page_index + 1:02d}.jpg"
        if not cv2.imwrite(str(path), page):
            raise RuntimeError(f"Could not write {path}")

    write_template(output_dir / "manual_audit_template.csv", rows)
    print(
        f"events={len(rows)} pages={math.ceil(len(rows) / args.events_per_page)} "
        f"output={output_dir}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", required=True, type=Path)
    parser.add_argument("--ledger", required=True, type=Path)
    parser.add_argument("--observations", type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--line-x", type=int)
    parser.add_argument(
        "--track-ids",
        help="Optional comma-separated tracker IDs to include.",
    )
    parser.add_argument(
        "--line-values",
        help="Optional comma-separated line_x values to include.",
    )
    parser.add_argument("--crop", default="400,0,880,310")
    parser.add_argument("--frame-step", type=int, default=6)
    parser.add_argument("--events-per-page", type=int, default=6)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.frame_step < 1 or args.events_per_page < 1:
        raise ValueError("--frame-step and --events-per-page must be positive")
    run(args)


if __name__ == "__main__":
    main()
