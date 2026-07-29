from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from src.analysis.plot_peak_duration_sensitivity import (
    CAPACITY_CELLS,
    DEFAULT_ANALYSIS_DIR,
    DURATION_SECONDS,
    _estimate_grid,
    _growth_grid,
    _require_pass,
    render_queue_sensitivity,
    render_recovery_diagnostics,
)


class PeakDurationSensitivityPlotTests(unittest.TestCase):
    def test_compact_inputs_have_exact_frozen_coverage(self) -> None:
        _require_pass(DEFAULT_ANALYSIS_DIR)
        estimates = _estimate_grid(
            DEFAULT_ANALYSIS_DIR,
            "total_queue_wait_p95_seconds",
        )
        growth = _growth_grid(DEFAULT_ANALYSIS_DIR)

        self.assertEqual(tuple(estimates), CAPACITY_CELLS)
        self.assertEqual(tuple(growth), CAPACITY_CELLS)
        for cell in CAPACITY_CELLS:
            self.assertEqual(
                tuple(
                    int(row["arrival_cutoff_seconds"])
                    for row in estimates[cell]
                ),
                DURATION_SECONDS,
            )
            self.assertEqual(
                tuple(
                    int(row["arrival_cutoff_seconds"])
                    for row in growth[cell]
                ),
                DURATION_SECONDS,
            )

    def test_rendered_figures_are_deterministic_and_vector_safe(self) -> None:
        with tempfile.TemporaryDirectory() as first_directory:
            with tempfile.TemporaryDirectory() as second_directory:
                first = Path(first_directory)
                second = Path(second_directory)
                render_queue_sensitivity(DEFAULT_ANALYSIS_DIR, first)
                render_recovery_diagnostics(DEFAULT_ANALYSIS_DIR, first)
                render_queue_sensitivity(DEFAULT_ANALYSIS_DIR, second)
                render_recovery_diagnostics(DEFAULT_ANALYSIS_DIR, second)

                expected = {
                    "peak_duration_queue_sensitivity.png",
                    "peak_duration_queue_sensitivity.svg",
                    "peak_duration_recovery_diagnostics.png",
                    "peak_duration_recovery_diagnostics.svg",
                }
                self.assertEqual(
                    {path.name for path in first.iterdir()},
                    expected,
                )
                for filename in expected:
                    first_bytes = (first / filename).read_bytes()
                    second_bytes = (second / filename).read_bytes()
                    self.assertGreater(len(first_bytes), 10_000)
                    self.assertEqual(
                        hashlib.sha256(first_bytes).hexdigest(),
                        hashlib.sha256(second_bytes).hexdigest(),
                    )
                    if filename.endswith(".svg"):
                        lowered = first_bytes.lower()
                        self.assertNotIn(b"<image", lowered)
                        self.assertNotIn(b"data:image", lowered)
                        self.assertNotIn(b"\r\n", first_bytes)

    def test_plotting_fails_closed_when_validation_is_not_pass(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for filename in (
                "crn_alignment.json",
                "cross_batch_reproducibility.json",
                "analysis_manifest.json",
            ):
                (root / filename).write_text(
                    json.dumps({"status": "PASS"}),
                    encoding="utf-8",
                )
            (root / "validation.json").write_text(
                json.dumps({"status": "FAIL"}),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                ValueError,
                "validation.json must report PASS",
            ):
                _require_pass(root)


if __name__ == "__main__":
    unittest.main()
