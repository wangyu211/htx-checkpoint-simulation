from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.analysis.build_operational_dashboard import (
    _friendly_seconds,
    build_dashboard,
)


class OperationalDashboardTests(unittest.TestCase):
    def test_friendly_seconds_uses_operationally_readable_units(self) -> None:
        self.assertEqual(_friendly_seconds(35.3), "35.3 s")
        self.assertEqual(_friendly_seconds(218.8), "3.6 min")
        self.assertEqual(_friendly_seconds(7214.2), "2.0 h")

    def test_dashboard_build_requires_and_reports_full_pilot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            png = root / "dashboard.png"
            svg = root / "dashboard.svg"
            summary = root / "README.md"

            report = build_dashboard(
                output_png=png,
                output_svg=svg,
                output_summary=summary,
            )

            self.assertEqual(report["status"], "PASS")
            self.assertEqual(report["scenario_count"], 15)
            self.assertEqual(report["replication_count"], 150)
            self.assertEqual(report["entity_count"], 61218)
            self.assertGreater(png.stat().st_size, 10_000)
            self.assertGreater(svg.stat().st_size, 10_000)
            text = summary.read_text(encoding="utf-8")
            self.assertIn("150/150 AnyLogic runs", text)
            self.assertIn("61,218 entity records", text)
            self.assertIn("--require-pilot-coverage", text)
            self.assertIn("not calibrated HTX performance", text)


if __name__ == "__main__":
    unittest.main()
