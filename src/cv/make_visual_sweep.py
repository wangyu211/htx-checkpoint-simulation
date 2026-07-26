"""Create sequential, paginated contact sheets for a visual crossing sweep."""

from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path

import cv2
import numpy as np


def parse_xyxy(text: str) -> tuple[int, int, int, int]:
    values = tuple(int(value.strip()) for value in text.split(","))
    if len(values) != 4:
        raise ValueError("--roi must be x1,y1,x2,y2")
    x1, y1, x2, y2 = values
    if x1 >= x2 or y1 >= y2:
        raise ValueError("--roi must have x1<x2 and y1<y2")
    return x1, y1, x2, y2


def labelled_crop(
    frame: np.ndarray,
    frame_index: int,
    pts_seconds: float,
    roi: tuple[int, int, int, int],
    line_x: int,
    scale: float,
) -> np.ndarray:
    x1, y1, x2, y2 = roi
    crop = frame[y1:y2, x1:x2].copy()
    line_local_x = line_x - x1
    if 0 <= line_local_x < crop.shape[1]:
        cv2.line(
            crop,
            (line_local_x, 0),
            (line_local_x, crop.shape[0] - 1),
            (0, 0, 255),
            2,
            cv2.LINE_AA,
        )

    label_height = 30
    tile = np.zeros(
        (crop.shape[0] + label_height, crop.shape[1], 3),
        dtype=np.uint8,
    )
    tile[label_height:] = crop
    cv2.putText(
        tile,
        f"f={frame_index:03d}  PTS={pts_seconds:06.3f}s",
        (7, 21),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.53,
        (255, 255, 255),
        1,
        cv2.LINE_AA,
    )
    cv2.rectangle(
        tile,
        (0, 0),
        (tile.shape[1] - 1, tile.shape[0] - 1),
        (160, 160, 160),
        1,
    )
    if scale != 1.0:
        tile = cv2.resize(
            tile,
            (
                int(round(tile.shape[1] * scale)),
                int(round(tile.shape[0] * scale)),
            ),
            interpolation=cv2.INTER_CUBIC,
        )
    return tile


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--roi", default="480,0,800,310")
    parser.add_argument("--line-x", type=int, default=640)
    parser.add_argument("--sample-fps", type=float, default=10.0)
    parser.add_argument("--columns", type=int, default=5)
    parser.add_argument("--rows", type=int, default=2)
    parser.add_argument("--start-frame", type=int, default=0)
    parser.add_argument("--end-frame", type=int)
    parser.add_argument("--scale", type=float, default=1.0)
    args = parser.parse_args()

    if (
        args.sample_fps <= 0
        or args.columns < 1
        or args.rows < 1
        or args.scale <= 0
    ):
        raise ValueError("Sampling rate and page dimensions must be positive.")

    video_path = args.video.resolve()
    output_dir = args.output_dir.resolve()
    pages_dir = output_dir / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)
    roi = parse_xyxy(args.roi)

    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise RuntimeError(f"Could not open video: {video_path}")

    source_fps = float(capture.get(cv2.CAP_PROP_FPS))
    frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    x1, y1, x2, y2 = roi
    if not (0 <= x1 < x2 <= width and 0 <= y1 < y2 <= height):
        raise ValueError(f"ROI {roi} exceeds {width}x{height}.")
    if not x1 <= args.line_x < x2:
        raise ValueError("--line-x must fall inside the ROI.")
    end_frame = (
        frame_count - 1
        if args.end_frame is None
        else min(args.end_frame, frame_count - 1)
    )
    if not 0 <= args.start_frame <= end_frame:
        raise ValueError("Frame range must satisfy 0 <= start <= end.")

    stride = max(1, int(round(source_fps / args.sample_fps)))
    actual_sample_fps = source_fps / stride
    sampled_tiles: list[np.ndarray] = []
    sampled_rows: list[dict[str, object]] = []
    frame_index = 0
    decoded_count = 0

    while True:
        ok, frame = capture.read()
        if not ok:
            break
        decoded_count += 1
        in_requested_range = args.start_frame <= frame_index <= end_frame
        aligned_sample = (frame_index - args.start_frame) % stride == 0
        if in_requested_range and (aligned_sample or frame_index == end_frame):
            pts_seconds = float(capture.get(cv2.CAP_PROP_POS_MSEC)) / 1000.0
            if not math.isfinite(pts_seconds):
                pts_seconds = frame_index / source_fps
            sampled_tiles.append(
                labelled_crop(
                    frame,
                    frame_index,
                    pts_seconds,
                    roi,
                    args.line_x,
                    args.scale,
                )
            )
            sampled_rows.append(
                {
                    "sample_index": len(sampled_rows) + 1,
                    "frame_index": frame_index,
                    "pts_seconds": f"{pts_seconds:.6f}",
                }
            )
        if frame_index >= end_frame:
            break
        frame_index += 1
    capture.release()

    if not sampled_tiles:
        raise RuntimeError("No frames were decoded.")

    tiles_per_page = args.columns * args.rows
    tile_height, tile_width = sampled_tiles[0].shape[:2]
    blank = np.zeros_like(sampled_tiles[0])
    page_count = math.ceil(len(sampled_tiles) / tiles_per_page)
    for page_index in range(page_count):
        page_tiles = sampled_tiles[
            page_index * tiles_per_page : (page_index + 1) * tiles_per_page
        ]
        page_tiles += [blank] * (tiles_per_page - len(page_tiles))
        page = np.vstack(
            [
                np.hstack(
                    page_tiles[
                        row_index * args.columns : (row_index + 1) * args.columns
                    ]
                )
                for row_index in range(args.rows)
            ]
        )
        page_path = pages_dir / f"sweep_page_{page_index + 1:03d}.jpg"
        if not cv2.imwrite(str(page_path), page, [cv2.IMWRITE_JPEG_QUALITY, 94]):
            raise RuntimeError(f"Could not write {page_path}.")

    with (output_dir / "sample_index.csv").open(
        "w",
        newline="",
        encoding="utf-8",
    ) as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=["sample_index", "frame_index", "pts_seconds"],
        )
        writer.writeheader()
        writer.writerows(sampled_rows)

    manifest = (
        f"source={video_path}\n"
        f"source_fps={source_fps:.9f}\n"
        f"frame_count={frame_count}\n"
        f"decoded_frames={decoded_count}\n"
        f"requested_frame_range={args.start_frame}:{end_frame}\n"
        f"sample_stride_frames={stride}\n"
        f"actual_sample_fps={actual_sample_fps:.9f}\n"
        f"sample_count={len(sampled_tiles)}\n"
        f"first_pts_seconds={sampled_rows[0]['pts_seconds']}\n"
        f"last_pts_seconds={sampled_rows[-1]['pts_seconds']}\n"
        f"roi_xyxy={x1},{y1},{x2},{y2}\n"
        f"line_x={args.line_x}\n"
        f"page_grid={args.columns}x{args.rows}\n"
        f"tile_scale={args.scale}\n"
        f"page_size_px={tile_width * args.columns}x{tile_height * args.rows}\n"
        f"page_count={page_count}\n"
    )
    (output_dir / "manifest.txt").write_text(manifest, encoding="utf-8")
    print(manifest, end="")


if __name__ == "__main__":
    main()
