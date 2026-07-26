"""Extract deterministic video metadata, sampled frames, and a contact sheet."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import cv2
import numpy as np


def sha256(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def fourcc_text(value: int) -> str:
    return "".join(chr((value >> (8 * index)) & 0xFF) for index in range(4))


def labelled_thumbnail(
    frame: np.ndarray,
    label: str,
    width: int = 320,
    height: int = 180,
) -> np.ndarray:
    resized = cv2.resize(frame, (width, height), interpolation=cv2.INTER_AREA)
    overlay = resized.copy()
    cv2.rectangle(overlay, (0, 0), (width, 28), (0, 0, 0), thickness=-1)
    cv2.addWeighted(overlay, 0.65, resized, 0.35, 0, resized)
    cv2.putText(
        resized,
        label,
        (8, 20),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.52,
        (255, 255, 255),
        1,
        cv2.LINE_AA,
    )
    return resized


def parse_roi(text: str | None) -> tuple[int, int, int, int] | None:
    if text is None:
        return None
    values = tuple(int(value.strip()) for value in text.split(","))
    if len(values) != 4:
        raise ValueError("--roi must be x1,y1,x2,y2")
    x1, y1, x2, y2 = values
    if x1 >= x2 or y1 >= y2:
        raise ValueError("--roi must have x1<x2 and y1<y2")
    return x1, y1, x2, y2


def extract(
    video_path: Path,
    output_dir: Path,
    sample_count: int,
    roi: tuple[int, int, int, int] | None = None,
    columns: int = 4,
) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    frames_dir = output_dir / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)

    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise RuntimeError(f"OpenCV could not open video: {video_path}")

    frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = float(capture.get(cv2.CAP_PROP_FPS))
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fourcc = fourcc_text(int(capture.get(cv2.CAP_PROP_FOURCC)))
    duration_seconds = frame_count / fps if fps > 0 else None

    if frame_count <= 0 or fps <= 0 or width <= 0 or height <= 0:
        raise RuntimeError("Video metadata is incomplete or invalid.")
    if roi is not None:
        x1, y1, x2, y2 = roi
        if not (0 <= x1 < x2 <= width and 0 <= y1 < y2 <= height):
            raise ValueError(f"ROI {roi} exceeds video dimensions {width}x{height}")

    indices = np.linspace(
        0,
        frame_count - 1,
        num=min(sample_count, frame_count),
        dtype=int,
    )
    thumbnails: list[np.ndarray] = []
    samples: list[dict[str, object]] = []

    for frame_index in indices:
        capture.set(cv2.CAP_PROP_POS_FRAMES, int(frame_index))
        ok, frame = capture.read()
        if not ok:
            raise RuntimeError(f"Could not decode frame {frame_index}.")
        pts_seconds = float(capture.get(cv2.CAP_PROP_POS_MSEC)) / 1000.0
        time_seconds = pts_seconds if math.isfinite(pts_seconds) else frame_index / fps
        displayed_frame = frame
        if roi is not None:
            x1, y1, x2, y2 = roi
            displayed_frame = frame[y1:y2, x1:x2]
        frame_name = f"frame_{frame_index:06d}.jpg"
        frame_path = frames_dir / frame_name
        if not cv2.imwrite(str(frame_path), displayed_frame):
            raise RuntimeError(f"Could not write frame: {frame_path}")
        samples.append(
            {
                "frame_index": int(frame_index),
                "time_seconds": round(time_seconds, 6),
                "file": frame_path.relative_to(output_dir).as_posix(),
            }
        )
        thumbnails.append(
            labelled_thumbnail(
                displayed_frame,
                f"f={frame_index}  t={time_seconds:.2f}s",
            )
        )

    capture.release()

    columns = min(columns, len(thumbnails))
    rows = math.ceil(len(thumbnails) / columns)
    blank = np.zeros_like(thumbnails[0])
    tiles = thumbnails + [blank] * (rows * columns - len(thumbnails))
    contact_sheet = np.vstack(
        [np.hstack(tiles[row * columns : (row + 1) * columns]) for row in range(rows)]
    )
    contact_sheet_path = output_dir / "contact_sheet.jpg"
    if not cv2.imwrite(str(contact_sheet_path), contact_sheet):
        raise RuntimeError(f"Could not write contact sheet: {contact_sheet_path}")

    metadata: dict[str, object] = {
        "schema_version": "1.0",
        "source_file": video_path.name,
        "source_sha256": sha256(video_path),
        "frame_count": frame_count,
        "fps": round(fps, 9),
        "duration_seconds": round(duration_seconds, 9),
        "width_px": width,
        "height_px": height,
        "codec_fourcc": fourcc,
        "sample_count": len(samples),
        "sample_roi_xyxy": list(roi) if roi is not None else None,
        "samples": samples,
    }
    metadata_path = output_dir / "video_metadata.json"
    metadata_path.write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return metadata


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--sample-count", type=int, default=12)
    parser.add_argument("--roi", type=str)
    parser.add_argument("--columns", type=int, default=4)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.sample_count < 1 or args.columns < 1:
        raise ValueError("--sample-count and --columns must be at least 1")
    metadata = extract(
        args.video.resolve(),
        args.output_dir.resolve(),
        args.sample_count,
        parse_roi(args.roi),
        args.columns,
    )
    print(json.dumps(metadata, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
