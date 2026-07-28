from __future__ import annotations

import unittest
import xml.etree.ElementTree as ET

from scripts.generate_operational_anylogic import (
    RESPONSE_SURFACE_EXPERIMENT_ID,
    RESPONSE_SURFACE_EXPERIMENT_NAME,
    RESPONSE_SURFACE_OUTPUT_COLLECTION,
    RESPONSE_SURFACE_TIMER_ID,
    _load_response_surface_inputs,
    _response_surface_experiment_xml,
    _upsert_response_surface_experiment,
)


class CapacityResponseSurfaceAnyLogicTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.rows, cls.seeds, cls.validation = (
            _load_response_surface_inputs()
        )
        cls.xml_text = _response_surface_experiment_xml(
            "12345",
            RESPONSE_SURFACE_EXPERIMENT_ID,
            RESPONSE_SURFACE_TIMER_ID,
            cls.rows,
            cls.seeds,
        )
        cls.root = ET.fromstring(cls.xml_text)

    def test_experiment_is_serial_self_contained_54_by_50(self) -> None:
        self.assertEqual(self.validation["status"], "PASS")
        self.assertEqual(self.root.findtext("Name"), RESPONSE_SURFACE_EXPERIMENT_NAME)
        self.assertEqual(self.root.findtext("AllowParallelEvaluations"), "false")
        self.assertEqual(self.root.findtext("NumberOfRuns"), "54")
        replications = self.root.find("ReplicationsProperties")
        self.assertIsNotNone(replications)
        self.assertEqual(replications.findtext("UseReplication"), "true")
        self.assertEqual(
            replications.findtext("ReplicationPerIteration"),
            "50",
        )
        self.assertEqual(replications.findtext("MinimumReplication"), "50")
        self.assertEqual(replications.findtext("MaximumReplication"), "50")

    def test_before_run_has_every_cell_and_base_seed_group(self) -> None:
        before = self.root.findtext("BeforeSimulationRunCode") or ""
        self.assertIn(RESPONSE_SURFACE_EXPERIMENT_NAME, before)
        self.assertIn(RESPONSE_SURFACE_OUTPUT_COLLECTION, before)
        self.assertEqual(before.count('expectedConfigId = "OP_RESPONSE_'), 54)
        self.assertEqual(before.count("seedGroupMatched = true;"), 50)
        self.assertIn(
            "CapacityResponseSurfaceExploratory replication must be 1..50",
            before,
        )

    def test_autostart_calls_only_the_response_surface(self) -> None:
        variables = self.root.find("Variables")
        self.assertIsNotNone(variables)
        timer = variables.find("Variable")
        self.assertIsNotNone(timer)
        self.assertEqual(
            timer.findtext("Name"),
            "response_surface_auto_start_timer",
        )
        code = timer.findtext("./Properties/InitialValue/Code") or ""
        self.assertEqual(
            code.count("CapacityResponseSurfaceExploratory.this.run();"),
            1,
        )

    def test_upsert_adds_exactly_one_experiment(self) -> None:
        document = "<Experiments>\n</Experiments>"
        updated = _upsert_response_surface_experiment(
            document,
            "12345",
            self.rows,
            self.seeds,
        )
        self.assertEqual(
            updated.count(
                "<Name><![CDATA[CapacityResponseSurfaceExploratory]]></Name>"
            ),
            1,
        )
        self.assertEqual(
            updated.count(f"<Id>{RESPONSE_SURFACE_EXPERIMENT_ID}</Id>"),
            1,
        )
        self.assertEqual(
            updated.count(f"<Id>{RESPONSE_SURFACE_TIMER_ID}</Id>"),
            1,
        )


if __name__ == "__main__":
    unittest.main()
