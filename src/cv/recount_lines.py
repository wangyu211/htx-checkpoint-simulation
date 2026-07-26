"""Recount crossings from one track ledger across several line positions."""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class CrossingState:
    stable_side: int = 0
    stable_side_x: float | None = None
    candidate_side: int = 0
    candidate_frames: int = 0
    previous_frame: int | None = None
    counted: bool = False


def side_of_line(x_coordinate: float, line_x: int, margin: int) -> int:
    if x_coordinate < line_x - margin:
        return -1
    if x_coordinate > line_x + margin:
        return 1
    return 0


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def recount(
    rows: list[dict[str, str]],
    line_x: int,
    margin: int,
    side_confirm_frames: int,
    minimum_displacement: float,
) -> list[dict[str, object]]:
    states: dict[int, CrossingState] = {}
    events: list[dict[str, object]] = []
    ordered_rows = sorted(
        rows,
        key=lambda row: (int(row["frame_index"]), int(row["track_id"])),
    )
    for row in ordered_rows:
        track_id = int(row["track_id"])
        frame_index = int(row["frame_index"])
        x_coordinate = float(row["centroid_x"])
        state = states.setdefault(track_id, CrossingState())
        current_side = side_of_line(x_coordinate, line_x, margin)

        if state.previous_frame is not None and frame_index != state.previous_frame + 1:
            state.candidate_side = 0
            state.candidate_frames = 0
        state.previous_frame = frame_index

        if current_side == 0:
            state.candidate_side = 0
            state.candidate_frames = 0
            continue
        if current_side == state.candidate_side:
            state.candidate_frames += 1
        else:
            state.candidate_side = current_side
            state.candidate_frames = 1
        if state.candidate_frames < side_confirm_frames:
            continue
        if state.stable_side == 0:
            state.stable_side = current_side
            state.stable_side_x = x_coordinate
            continue
        if state.counted or current_side == state.stable_side:
            continue
        if (
            state.stable_side_x is None
            or abs(x_coordinate - state.stable_side_x) < minimum_displacement
        ):
            continue

        direction = "left_to_right" if state.stable_side == -1 else "right_to_left"
        state.counted = True
        state.stable_side = current_side
        state.stable_side_x = x_coordinate
        events.append(
            {
                "line_x": line_x,
                "event_id": len(events) + 1,
                "track_id": track_id,
                "frame_index": frame_index,
                "time_seconds": float(row["time_seconds"]),
                "direction": direction,
                "centroid_x": x_coordinate,
                "centroid_y": float(row["centroid_y"]),
                "confidence": float(row["confidence"]),
            }
        )
    return events


def run(args: argparse.Namespace) -> None:
    rows = read_rows(args.observations.resolve())
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    lines = [int(value.strip()) for value in args.lines.split(",") if value.strip()]
    if not lines:
        raise ValueError("--lines must contain at least one x-coordinate")

    all_events: list[dict[str, object]] = []
    summaries: list[dict[str, object]] = []
    for line_x in lines:
        events = recount(
            rows,
            line_x,
            args.line_margin,
            args.side_confirm_frames,
            args.minimum_crossing_displacement,
        )
        all_events.extend(events)
        left_to_right = sum(
            event["direction"] == "left_to_right" for event in events
        )
        right_to_left = sum(
            event["direction"] == "right_to_left" for event in events
        )
        summaries.append(
            {
                "line_x": line_x,
                "left_to_right": left_to_right,
                "right_to_left": right_to_left,
                "total": left_to_right + right_to_left,
            }
        )

    event_fields = [
        "line_x",
        "event_id",
        "track_id",
        "frame_index",
        "time_seconds",
        "direction",
        "centroid_x",
        "centroid_y",
        "confidence",
    ]
    with (output_dir / "line_sensitivity_events.csv").open(
        "w",
        newline="",
        encoding="utf-8",
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=event_fields)
        writer.writeheader()
        writer.writerows(all_events)

    summary_fields = ["line_x", "left_to_right", "right_to_left", "total"]
    with (output_dir / "line_sensitivity_summary.csv").open(
        "w",
        newline="",
        encoding="utf-8",
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=summary_fields)
        writer.writeheader()
        writer.writerows(summaries)

    print(json.dumps(summaries, indent=2))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--observations", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--lines", default="620,640,660")
    parser.add_argument("--line-margin", type=int, default=12)
    parser.add_argument("--side-confirm-frames", type=int, default=3)
    parser.add_argument("--minimum-crossing-displacement", type=float, default=24.0)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if (
        args.line_margin < 0
        or args.side_confirm_frames < 1
        or args.minimum_crossing_displacement < 0
    ):
        raise ValueError("Crossing thresholds must be non-negative")
    run(args)


if __name__ == "__main__":
    main()
