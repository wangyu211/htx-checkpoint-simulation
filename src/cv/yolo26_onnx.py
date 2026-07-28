"""Dependency-light adapter for an end-to-end Ultralytics YOLO26 ONNX model.

YOLO26 uses a centred RGB letterbox and emits NMS-free rows in the form
``[x1, y1, x2, y2, confidence, class_id]``.  The model weights remain governed
by Ultralytics' own licence; this adapter only defines the local inference
contract used by the assessment pipeline.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort

from .yolox_onnx import Detection


def preprocess_yolo26(
    image: np.ndarray,
    input_size: tuple[int, int],
) -> tuple[np.ndarray, float, tuple[int, int]]:
    """Apply the centred Ultralytics letterbox and return CHW RGB float input."""
    if image.ndim != 3 or image.shape[2] != 3:
        raise ValueError("YOLO26 expects a BGR image with three channels")

    input_height, input_width = input_size
    image_height, image_width = image.shape[:2]
    ratio = min(input_height / image_height, input_width / image_width)
    resized_width = int(round(image_width * ratio))
    resized_height = int(round(image_height * ratio))

    horizontal_padding = (input_width - resized_width) / 2.0
    vertical_padding = (input_height - resized_height) / 2.0
    left = int(round(horizontal_padding - 0.1))
    right = int(round(horizontal_padding + 0.1))
    top = int(round(vertical_padding - 0.1))
    bottom = int(round(vertical_padding + 0.1))

    if (resized_width, resized_height) != (image_width, image_height):
        resized = cv2.resize(
            image,
            (resized_width, resized_height),
            interpolation=cv2.INTER_LINEAR,
        )
    else:
        resized = image
    letterboxed = cv2.copyMakeBorder(
        resized,
        top,
        bottom,
        left,
        right,
        cv2.BORDER_CONSTANT,
        value=(114, 114, 114),
    )
    if letterboxed.shape[:2] != input_size:
        raise RuntimeError(
            f"Letterbox produced {letterboxed.shape[:2]}, expected {input_size}"
        )

    tensor = letterboxed[:, :, ::-1].transpose((2, 0, 1))
    tensor = np.ascontiguousarray(tensor, dtype=np.float32) / 255.0
    return tensor, ratio, (left, top)


def decode_end_to_end(
    raw: np.ndarray,
    *,
    ratio: float,
    padding: tuple[int, int],
    original_shape: tuple[int, int],
    confidence_threshold: float,
    person_class_id: int,
) -> list[Detection]:
    """Decode YOLO26's end-to-end ``(1, 300, 6)`` output."""
    if raw.ndim != 3 or raw.shape[0] != 1 or raw.shape[2] != 6:
        raise ValueError(
            "Expected end-to-end YOLO26 output shaped (1, N, 6), "
            f"received {raw.shape}. Export the model with end-to-end output."
        )
    rows = raw[0]
    if rows.size == 0:
        return []

    finite_mask = np.all(np.isfinite(rows), axis=1)
    class_mask = np.rint(rows[:, 5]).astype(np.int64) == person_class_id
    score_mask = rows[:, 4] >= confidence_threshold
    selected = rows[finite_mask & class_mask & score_mask]
    if selected.size == 0:
        return []

    left, top = padding
    boxes = selected[:, :4].astype(np.float32, copy=True)
    boxes[:, [0, 2]] = (boxes[:, [0, 2]] - left) / ratio
    boxes[:, [1, 3]] = (boxes[:, [1, 3]] - top) / ratio
    image_height, image_width = original_shape
    boxes[:, [0, 2]] = np.clip(boxes[:, [0, 2]], 0.0, float(image_width))
    boxes[:, [1, 3]] = np.clip(boxes[:, [1, 3]], 0.0, float(image_height))
    geometry_mask = (boxes[:, 2] > boxes[:, 0]) & (boxes[:, 3] > boxes[:, 1])

    return [
        Detection(
            xyxy=box,
            score=float(row[4]),
            class_id=person_class_id,
        )
        for row, box, valid in zip(selected, boxes, geometry_mask)
        if bool(valid)
    ]


class Yolo26Onnx:
    """Run a fixed-shape, end-to-end YOLO26 ONNX detector on CPU."""

    def __init__(
        self,
        model_path: Path,
        confidence_threshold: float = 0.15,
        person_class_id: int = 0,
    ) -> None:
        self.session = ort.InferenceSession(
            str(model_path),
            providers=["CPUExecutionProvider"],
        )
        input_info = self.session.get_inputs()[0]
        self.input_name = input_info.name
        shape = input_info.shape
        if len(shape) != 4 or not isinstance(shape[2], int) or not isinstance(shape[3], int):
            raise ValueError(f"Unsupported dynamic or non-NCHW input shape: {shape}")
        self.input_size = (shape[2], shape[3])
        self.output_names = [output.name for output in self.session.get_outputs()]
        output_shape = self.session.get_outputs()[0].shape
        if (
            len(output_shape) != 3
            or output_shape[0] != 1
            or output_shape[2] != 6
        ):
            raise ValueError(
                "Expected end-to-end YOLO26 ONNX output shaped (1, N, 6), "
                f"received {output_shape}"
            )
        self.confidence_threshold = confidence_threshold
        self.person_class_id = person_class_id

    def predict(self, frame: np.ndarray) -> list[Detection]:
        tensor, ratio, padding = preprocess_yolo26(frame, self.input_size)
        raw = self.session.run(
            self.output_names,
            {self.input_name: tensor[None, :, :, :]},
        )[0]
        return decode_end_to_end(
            raw,
            ratio=ratio,
            padding=padding,
            original_shape=frame.shape[:2],
            confidence_threshold=self.confidence_threshold,
            person_class_id=self.person_class_id,
        )
