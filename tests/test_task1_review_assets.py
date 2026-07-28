"""Regression tests for count-blind Task 1 review assets."""

from __future__ import annotations

import csv
import hashlib
import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np

from src.cv.make_visual_sweep import (
    even_sized,
    parse_xyxy,
    sha256_file,
    write_enumeration_template,
    write_page,
)


class Task1ReviewAssetTests(unittest.TestCase):
    def test_sha256_file_matches_standard_library(self) -> None:
        content = b"review protocol fixture"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixture.bin"
            path.write_bytes(content)
            observed = sha256_file(path)

        self.assertEqual(observed, hashlib.sha256(content).hexdigest())

    def test_enumeration_template_has_no_count_or_candidate_fields(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "enumeration.csv"
            write_enumeration_template(path)
            with path.open(newline="", encoding="utf-8") as stream:
                reader = csv.DictReader(stream)
                rows = list(reader)
                fields = reader.fieldnames

        self.assertEqual(rows, [])
        self.assertIn("approx_pts_seconds", fields)
        self.assertIn("proposed_direction", fields)
        self.assertNotIn("candidate_id", fields)
        self.assertNotIn("running_total", fields)
        self.assertNotIn("expected_total", fields)

    def test_even_sized_only_pads_odd_dimensions(self) -> None:
        odd = np.zeros((5, 7, 3), dtype=np.uint8)
        even = even_sized(odd)
        self.assertEqual(even.shape, (6, 8, 3))
        np.testing.assert_array_equal(even[:5, :7], odd)

        already_even = np.zeros((6, 8, 3), dtype=np.uint8)
        self.assertEqual(even_sized(already_even).shape, already_even.shape)

    def test_page_writer_preserves_grid_and_pads_missing_tile(self) -> None:
        tile = np.full((10, 20, 3), 127, dtype=np.uint8)
        with tempfile.TemporaryDirectory() as directory:
            pages_dir = Path(directory)
            write_page(
                [tile, tile, tile],
                columns=2,
                rows=2,
                pages_dir=pages_dir,
                page_index=1,
            )
            page = cv2.imread(str(pages_dir / "sweep_page_001.jpg"))

        self.assertIsNotNone(page)
        self.assertEqual(page.shape[:2], (20, 40))

    def test_roi_parser_rejects_invalid_geometry(self) -> None:
        self.assertEqual(parse_xyxy("0,0,1280,310"), (0, 0, 1280, 310))
        for value in ("0,0,1", "4,0,4,10", "0,8,10,2"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    parse_xyxy(value)


if __name__ == "__main__":
    unittest.main()
