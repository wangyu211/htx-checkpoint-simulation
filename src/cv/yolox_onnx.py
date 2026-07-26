"""Small, dependency-light YOLOX ONNX inference adapter.

The preprocessing and output decoding follow the Apache-2.0 YOLOX reference
implementation:
https://github.com/Megvii-BaseDetection/YOLOX
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort


@dataclass(frozen=True)
class Detection:
    xyxy: np.ndarray
    score: float
    class_id: int


def preprocess(
    image: np.ndarray,
    input_size: tuple[int, int],
) -> tuple[np.ndarray, float]:
    if image.ndim == 3:
        padded = np.full(
            (input_size[0], input_size[1], 3),
            114,
            dtype=np.uint8,
        )
    else:
        padded = np.full(input_size, 114, dtype=np.uint8)
    ratio = min(input_size[0] / image.shape[0], input_size[1] / image.shape[1])
    resized = cv2.resize(
        image,
        (
            int(image.shape[1] * ratio),
            int(image.shape[0] * ratio),
        ),
        interpolation=cv2.INTER_LINEAR,
    ).astype(np.uint8)
    padded[: resized.shape[0], : resized.shape[1]] = resized
    tensor = padded.transpose((2, 0, 1))
    tensor = np.ascontiguousarray(tensor, dtype=np.float32)
    return tensor, ratio


def decode_outputs(
    outputs: np.ndarray,
    input_size: tuple[int, int],
    include_stride_64: bool = False,
) -> np.ndarray:
    grids: list[np.ndarray] = []
    expanded_strides: list[np.ndarray] = []
    strides = [8, 16, 32]
    if include_stride_64:
        strides.append(64)

    for stride in strides:
        height, width = input_size[0] // stride, input_size[1] // stride
        grid_y, grid_x = np.meshgrid(np.arange(height), np.arange(width), indexing="ij")
        grid = np.stack((grid_x, grid_y), axis=2).reshape(1, -1, 2)
        grids.append(grid)
        expanded_strides.append(
            np.full((*grid.shape[:2], 1), stride, dtype=np.float32)
        )

    grid_array = np.concatenate(grids, axis=1).astype(np.float32)
    stride_array = np.concatenate(expanded_strides, axis=1)
    decoded = outputs.copy()
    decoded[..., :2] = (decoded[..., :2] + grid_array) * stride_array
    decoded[..., 2:4] = np.exp(decoded[..., 2:4]) * stride_array
    return decoded


def nms(boxes: np.ndarray, scores: np.ndarray, threshold: float) -> list[int]:
    x1, y1, x2, y2 = boxes.T
    areas = (x2 - x1 + 1.0) * (y2 - y1 + 1.0)
    order = scores.argsort()[::-1]
    keep: list[int] = []
    while order.size > 0:
        index = int(order[0])
        keep.append(index)
        xx1 = np.maximum(x1[index], x1[order[1:]])
        yy1 = np.maximum(y1[index], y1[order[1:]])
        xx2 = np.minimum(x2[index], x2[order[1:]])
        yy2 = np.minimum(y2[index], y2[order[1:]])
        width = np.maximum(0.0, xx2 - xx1 + 1.0)
        height = np.maximum(0.0, yy2 - yy1 + 1.0)
        intersection = width * height
        overlap = intersection / (areas[index] + areas[order[1:]] - intersection)
        remaining = np.where(overlap <= threshold)[0]
        order = order[remaining + 1]
    return keep


class YoloxOnnx:
    def __init__(
        self,
        model_path: Path,
        confidence_threshold: float = 0.15,
        nms_threshold: float = 0.45,
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
        self.confidence_threshold = confidence_threshold
        self.nms_threshold = nms_threshold
        self.person_class_id = person_class_id

    def predict(self, frame: np.ndarray) -> list[Detection]:
        tensor, ratio = preprocess(frame, self.input_size)
        raw = self.session.run(
            self.output_names,
            {self.input_name: tensor[None, :, :, :]},
        )[0]
        predictions = decode_outputs(raw, self.input_size)[0]

        boxes = predictions[:, :4]
        boxes_xyxy = np.empty_like(boxes)
        boxes_xyxy[:, 0] = boxes[:, 0] - boxes[:, 2] / 2.0
        boxes_xyxy[:, 1] = boxes[:, 1] - boxes[:, 3] / 2.0
        boxes_xyxy[:, 2] = boxes[:, 0] + boxes[:, 2] / 2.0
        boxes_xyxy[:, 3] = boxes[:, 1] + boxes[:, 3] / 2.0
        boxes_xyxy /= ratio

        class_scores = predictions[:, 4:5] * predictions[:, 5:]
        person_scores = class_scores[:, self.person_class_id]
        keep_mask = person_scores >= self.confidence_threshold
        if not np.any(keep_mask):
            return []

        candidate_boxes = boxes_xyxy[keep_mask]
        candidate_scores = person_scores[keep_mask]
        keep_indices = nms(
            candidate_boxes,
            candidate_scores,
            self.nms_threshold,
        )
        return [
            Detection(
                xyxy=candidate_boxes[index].astype(np.float32),
                score=float(candidate_scores[index]),
                class_id=self.person_class_id,
            )
            for index in keep_indices
        ]
