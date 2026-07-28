from __future__ import annotations

import csv
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ANYLOGIC_ROOT = PROJECT_ROOT / "simulation" / "anylogic"
ALPX_ROOT = ANYLOGIC_ROOT / "HTXCheckpointSimulation"
ALPX = ALPX_ROOT / "HTXCheckpointSimulation.alpx"
ALP = (
    ANYLOGIC_ROOT
    / "HTXCheckpointSimulationCLI"
    / "HTXCheckpointSimulationCLI.alp"
)
EMBEDDED_OBJECTS = (
    ALPX_ROOT / "_alp" / "Agents" / "Main" / "EmbeddedObjects.xml"
)
CONNECTORS = ALPX_ROOT / "_alp" / "Agents" / "Main" / "Connectors.xml"
EXPERIMENTS = ALPX_ROOT / "_alp" / "Experiments.xml"
CHECKPOINT_MODEL = ALPX_ROOT / "_alp" / "Agents" / "CheckpointModel"
CHECKPOINT_EVENTS = CHECKPOINT_MODEL / "Code" / "Events.xml"
CHECKPOINT_EVENT_CODE = CHECKPOINT_MODEL / "Code" / "Events.java"
CHECKPOINT_EMBEDDED_OBJECTS = CHECKPOINT_MODEL / "EmbeddedObjects.xml"
CHECKPOINT_VARIABLES = CHECKPOINT_MODEL / "Variables.xml"
CHECKPOINT_TRAVELLER_VARIABLES = (
    ALPX_ROOT / "_alp" / "Agents" / "CheckpointTraveller" / "Variables.xml"
)
HPP_MODEL = ALPX_ROOT / "_alp" / "Agents" / "HppArrivalModel"
HPP_AOC = HPP_MODEL / "AOC.HppArrivalModel.xml"
HPP_CONNECTORS = HPP_MODEL / "Connectors.xml"
HPP_EMBEDDED_OBJECTS = HPP_MODEL / "EmbeddedObjects.xml"
HPP_EVENTS = HPP_MODEL / "Code" / "Events.xml"
HPP_EVENT_CODE = HPP_MODEL / "Code" / "Events.java"
HPP_VARIABLES = HPP_MODEL / "Variables.xml"
MODEL_RUN_CONFIGS = PROJECT_ROOT / "config" / "model_run_configs.csv"


def cdata_names(path: Path) -> set[str]:
    root = ET.parse(path).getroot()
    return {
        element.text.strip()
        for element in root.iter("Name")
        if element.text and element.text.strip()
    }


def checkpoint_parameter_defaults() -> dict[str, str]:
    root = ET.parse(CHECKPOINT_VARIABLES).getroot()
    return {
        variable.findtext("Name", "").strip(): variable.findtext(
            "Properties/DefaultValue/Code", ""
        ).strip()
        for variable in root.findall("Variable")
        if variable.attrib.get("Class") == "Parameter"
    }


def single_file_checkpoint_parameter_defaults() -> dict[str, str]:
    root = ET.parse(ALP).getroot()
    checkpoint = next(
        item
        for item in root.findall(".//ActiveObjectClass")
        if item.findtext("Name") == "CheckpointModel"
    )
    return {
        variable.findtext("Name", "").strip(): variable.findtext(
            "Properties/DefaultValue/Code", ""
        ).strip()
        for variable in checkpoint.findall("Variables/Variable")
        if variable.attrib.get("Class") == "Parameter"
    }


def embedded_parameters(name: str) -> dict[str, str]:
    root = ET.parse(CHECKPOINT_EMBEDDED_OBJECTS).getroot()
    embedded = next(
        element
        for element in root.findall("EmbeddedObject")
        if element.findtext("Name") == name
    )
    return {
        parameter.findtext("Name", "").strip(): parameter.findtext(
            "Value/Code", ""
        ).strip()
        for parameter in embedded.findall("Parameters/Parameter")
    }


def hpp_parameter_defaults() -> dict[str, str]:
    root = ET.parse(HPP_VARIABLES).getroot()
    return {
        variable.findtext("Name", "").strip(): variable.findtext(
            "Properties/DefaultValue/Code", ""
        ).strip()
        for variable in root.findall("Variable")
        if variable.attrib.get("Class") == "Parameter"
    }


def hpp_embedded_parameters(name: str) -> dict[str, str]:
    root = ET.parse(HPP_EMBEDDED_OBJECTS).getroot()
    embedded = next(
        element
        for element in root.findall("EmbeddedObject")
        if element.findtext("Name") == name
    )
    return {
        parameter.findtext("Name", "").strip(): parameter.findtext(
            "Value/Code", ""
        ).strip()
        for parameter in embedded.findall("Parameters/Parameter")
    }


def split_event_action_code(path: Path, event_id: str) -> str:
    alp_raw = ALPX.read_bytes()
    first_lf = alp_raw.find(b"\n")
    if first_lf < 0:
        raise AssertionError(f"{ALPX}: no line break found")
    line_break = (
        b"\r\n"
        if first_lf > 0 and alp_raw[first_lf - 1 : first_lf + 1] == b"\r\n"
        else b"\n"
    )

    raw = path.read_bytes()
    if line_break == b"\r\n":
        has_mismatched_line_break = b"\n" in raw.replace(b"\r\n", b"")
    else:
        has_mismatched_line_break = b"\r\n" in raw
    if has_mismatched_line_break:
        raise AssertionError(
            f"{path}: line endings must match the parent ALPX"
        )

    start_marker = (
        f"/*ALCODESTART::{event_id}*/".encode("utf-8") + line_break
    )
    end_marker = line_break + b"/*ALCODEEND*/"
    if raw.count(start_marker) != 1 or raw.count(end_marker) != 1:
        raise AssertionError(
            f"{path}: expected exactly one AnyLogic code-marker pair"
        )
    return raw.split(start_marker, 1)[1].split(end_marker, 1)[0].decode(
        "utf-8"
    )


class AnyLogicProjectTests(unittest.TestCase):
    def assert_gate_autostart_adapter(self, path: Path) -> None:
        root = ET.parse(path).getroot()
        gate_experiments = [
            experiment
            for experiment in root.findall(".//ParamVariationExperiment")
            if experiment.findtext("Name") == "GatePV2x3"
        ]
        self.assertEqual(len(gate_experiments), 1)

        timer_variables = [
            variable
            for variable in gate_experiments[0].findall("Variables/Variable")
            if variable.findtext("Name") == "gate_auto_start_timer"
        ]
        self.assertEqual(len(timer_variables), 1)
        timer = timer_variables[0]

        self.assertEqual(timer.findtext("PresentationFlag"), "false")
        self.assertEqual(timer.findtext("ShowLabel"), "false")

        properties = timer.find("Properties")
        self.assertIsNotNone(properties)
        assert properties is not None
        self.assertEqual(properties.attrib["AccessType"], "private")
        self.assertEqual(properties.attrib["SaveInSnapshot"], "false")
        self.assertEqual(properties.findtext("Type"), "javax.swing.Timer")

        code = properties.findtext("InitialValue/Code")
        self.assertIsNotNone(code)
        assert code is not None
        expected_fragments = (
            "new javax.swing.Timer(",
            "((javax.swing.Timer) event.getSource()).stop();",
            "setRepeats(false);",
            "start();",
            "GatePV2x3.this.run();",
        )
        for fragment in expected_fragments:
            with self.subTest(path=path, fragment=fragment):
                self.assertEqual(code.count(fragment), 1)

    def test_every_split_model_fragment_is_well_formed_xml(self) -> None:
        paths = [ALPX, *sorted((ALPX_ROOT / "_alp").rglob("*.xml"))]
        self.assertGreaterEqual(len(paths), 8)
        for path in paths:
            with self.subTest(path=path.relative_to(PROJECT_ROOT)):
                ET.parse(path)

    def test_native_gate_flow_and_connectors_are_present(self) -> None:
        self.assertTrue(
            {"source", "queue", "delay", "sink"}.issubset(
                cdata_names(EMBEDDED_OBJECTS)
            )
        )
        connectors = ET.parse(CONNECTORS).getroot().findall("Connector")
        self.assertEqual(len(connectors), 3)

    def test_parameter_variation_contract_is_serial_and_seeded(self) -> None:
        text = EXPERIMENTS.read_text(encoding="utf-8")
        self.assertIn("<![CDATA[GatePV2x3]]>", text)
        self.assertIn("<AllowParallelEvaluations>false</AllowParallelEvaluations>", text)
        self.assertIn("<NumberOfRuns>2</NumberOfRuns>", text)
        self.assertIn("<UseReplication>true</UseReplication>", text)
        self.assertIn("<ReplicationPerIteration>3</ReplicationPerIteration>", text)
        self.assertIn("getEngine().getDefaultRandomGenerator().setSeed( seed )", text)
        self.assertIn("config/anylogic_gate_manifest.csv", text)

    def test_gate_parameter_variation_has_one_private_one_shot_autostart_adapter(
        self,
    ) -> None:
        self.assert_gate_autostart_adapter(EXPERIMENTS)

    def test_single_file_copy_contains_the_gate_autostart_adapter(self) -> None:
        self.assert_gate_autostart_adapter(ALP)

    def test_single_file_copy_contains_the_operational_pilot(self) -> None:
        root = ET.parse(ALP).getroot()
        experiments = [
            experiment
            for experiment in root.findall(".//ParamVariationExperiment")
            if experiment.findtext("Name") == "OperationalPilot"
        ]
        self.assertEqual(len(experiments), 1)
        pilot = experiments[0]

        self.assertEqual(pilot.attrib["ActiveObjectClassId"], "1785162520364")
        self.assertEqual(pilot.findtext("AllowParallelEvaluations"), "false")
        self.assertEqual(pilot.findtext("UseFreeformParameters"), "true")
        self.assertEqual(pilot.findtext("NumberOfRuns"), "15")
        self.assertEqual(
            pilot.findtext("ModelTimeProperties/StopOption"),
            "Never",
        )
        self.assertEqual(
            pilot.findtext("ReplicationsProperties/UseReplication"),
            "true",
        )
        self.assertEqual(
            pilot.findtext(
                "ReplicationsProperties/ReplicationPerIteration"
            ),
            "10",
        )

        before = pilot.findtext("BeforeSimulationRunCode", "")
        after = pilot.findtext("AfterSimulationRunCode", "")
        self.assertIn("anylogic_operational_batch", before)
        self.assertIn("replication < 1 || replication > 10", before)
        self.assertIn("full-drain conservation failed", after)
        self.assertIn('runDirectory.resolve( "entity_log.csv" )', after)

        timers = [
            variable
            for variable in pilot.findall("Variables/Variable")
            if variable.findtext("Name")
            == "operational_pilot_auto_start_timer"
        ]
        self.assertEqual(len(timers), 1)
        timer_code = timers[0].findtext("Properties/InitialValue/Code", "")
        self.assertEqual(timer_code.count("OperationalPilot.this.run();"), 1)
        self.assertEqual(timer_code.count("setRepeats(false);"), 1)

    def test_split_and_single_file_contain_one_identical_confirmatory_contract(
        self,
    ) -> None:
        split_root = ET.parse(EXPERIMENTS).getroot()
        single_root = ET.parse(ALP).getroot()

        def find_confirmatory(root: ET.Element) -> ET.Element:
            matches = [
                experiment
                for experiment in root.findall(".//ParamVariationExperiment")
                if experiment.findtext("Name")
                == "CapacityRobustnessConfirmatory"
            ]
            self.assertEqual(len(matches), 1)
            return matches[0]

        split = find_confirmatory(split_root)
        single = find_confirmatory(single_root)
        for experiment in (split, single):
            self.assertEqual(
                experiment.attrib["ActiveObjectClassId"],
                "1785162520364",
            )
            self.assertEqual(
                experiment.findtext("AllowParallelEvaluations"),
                "false",
            )
            self.assertEqual(experiment.findtext("NumberOfRuns"), "12")
            self.assertEqual(
                experiment.findtext(
                    "ReplicationsProperties/ReplicationPerIteration"
                ),
                "50",
            )
            self.assertEqual(
                experiment.findtext(
                    "ReplicationsProperties/MinimumReplication"
                ),
                "50",
            )
            self.assertEqual(
                experiment.findtext(
                    "ReplicationsProperties/MaximumReplication"
                ),
                "50",
            )
            self.assertEqual(
                experiment.findtext("ModelTimeProperties/StopOption"),
                "Never",
            )
            before = experiment.findtext("BeforeSimulationRunCode", "")
            self.assertIn('"confirmatory_capacity"', before)
            self.assertIn("PENDING_VALIDATION", before)
            timers = [
                variable
                for variable in experiment.findall("Variables/Variable")
                if variable.findtext("Name")
                == "confirmatory_auto_start_timer"
            ]
            self.assertEqual(len(timers), 1)
            timer_code = timers[0].findtext(
                "Properties/InitialValue/Code",
                "",
            )
            self.assertEqual(
                timer_code.count(
                    "CapacityRobustnessConfirmatory.this.run();"
                ),
                1,
            )

        def semantic_signature(
            element: ET.Element,
        ) -> tuple[
            str,
            tuple[tuple[str, str], ...],
            str,
            tuple[object, ...],
        ]:
            text = " ".join((element.text or "").split())
            return (
                element.tag,
                tuple(sorted(element.attrib.items())),
                text,
                tuple(semantic_signature(child) for child in element),
            )

        self.assertEqual(
            semantic_signature(split),
            semantic_signature(single),
        )

    def test_split_and_single_file_contain_availability_stress_contract(
        self,
    ) -> None:
        split_root = ET.parse(EXPERIMENTS).getroot()
        single_root = ET.parse(ALP).getroot()

        def find_availability(root: ET.Element) -> ET.Element:
            matches = [
                experiment
                for experiment in root.findall(".//ParamVariationExperiment")
                if experiment.findtext("Name")
                == "CapacityAvailabilityStress"
            ]
            self.assertEqual(len(matches), 1)
            return matches[0]

        split = find_availability(split_root)
        single = find_availability(single_root)
        for experiment in (split, single):
            self.assertEqual(
                experiment.attrib["ActiveObjectClassId"],
                "1785162520364",
            )
            self.assertEqual(experiment.findtext("Id"), "1785162950001")
            self.assertEqual(
                experiment.findtext("AllowParallelEvaluations"),
                "false",
            )
            self.assertEqual(experiment.findtext("NumberOfRuns"), "12")
            for field in (
                "ReplicationPerIteration",
                "MinimumReplication",
                "MaximumReplication",
            ):
                self.assertEqual(
                    experiment.findtext(
                        f"ReplicationsProperties/{field}"
                    ),
                    "50",
                )
            before = experiment.findtext("BeforeSimulationRunCode", "")
            self.assertIn('"capacity_availability"', before)
            self.assertIn("PENDING_VALIDATION", before)
            timers = [
                variable
                for variable in experiment.findall("Variables/Variable")
                if variable.findtext("Name")
                == "availability_auto_start_timer"
            ]
            self.assertEqual(len(timers), 1)
            timer_code = timers[0].findtext(
                "Properties/InitialValue/Code",
                "",
            )
            self.assertEqual(
                timer_code.count(
                    "CapacityAvailabilityStress.this.run();"
                ),
                1,
            )

        def semantic_signature(
            element: ET.Element,
        ) -> tuple[
            str,
            tuple[tuple[str, str], ...],
            str,
            tuple[object, ...],
        ]:
            text = " ".join((element.text or "").split())
            return (
                element.tag,
                tuple(sorted(element.attrib.items())),
                text,
                tuple(semantic_signature(child) for child in element),
            )

        self.assertEqual(
            semantic_signature(split),
            semantic_signature(single),
        )

    def test_split_and_single_file_contain_response_surface_contract(
        self,
    ) -> None:
        split_root = ET.parse(EXPERIMENTS).getroot()
        single_root = ET.parse(ALP).getroot()

        def find_response_surface(root: ET.Element) -> ET.Element:
            matches = [
                experiment
                for experiment in root.findall(".//ParamVariationExperiment")
                if experiment.findtext("Name")
                == "CapacityResponseSurfaceExploratory"
            ]
            self.assertEqual(len(matches), 1)
            return matches[0]

        split = find_response_surface(split_root)
        single = find_response_surface(single_root)
        for root, experiment in (
            (split_root, split),
            (single_root, single),
        ):
            self.assertEqual(
                experiment.attrib["ActiveObjectClassId"],
                "1785162520364",
            )
            self.assertEqual(experiment.findtext("Id"), "1785162960001")
            self.assertEqual(
                experiment.findtext("AllowParallelEvaluations"),
                "false",
            )
            self.assertEqual(experiment.findtext("UseFreeformParameters"), "true")
            self.assertEqual(experiment.findtext("NumberOfRuns"), "54")
            for field in (
                "ReplicationPerIteration",
                "MinimumReplication",
                "MaximumReplication",
            ):
                self.assertEqual(
                    experiment.findtext(
                        f"ReplicationsProperties/{field}"
                    ),
                    "50",
                )
            before = experiment.findtext("BeforeSimulationRunCode", "")
            self.assertIn('"capacity_response_surface"', before)
            self.assertIn("PENDING_VALIDATION", before)
            self.assertEqual(
                before.count('expectedConfigId = "OP_RESPONSE_'),
                54,
            )
            self.assertEqual(before.count("seedGroupMatched = true;"), 50)

            timers = [
                variable
                for variable in experiment.findall("Variables/Variable")
                if variable.findtext("Name")
                == "response_surface_auto_start_timer"
            ]
            self.assertEqual(len(timers), 1)
            self.assertEqual(timers[0].findtext("Id"), "1785162960002")
            timer_code = timers[0].findtext(
                "Properties/InitialValue/Code",
                "",
            )
            self.assertEqual(
                timer_code.count(
                    "CapacityResponseSurfaceExploratory.this.run();"
                ),
                1,
            )
            self.assertEqual(timer_code.count("setRepeats(false);"), 1)

            top_level_ids = [
                item.findtext("Id", "").strip()
                for tag in (
                    "SimulationExperiment",
                    "ParamVariationExperiment",
                )
                for item in root.findall(f".//{tag}")
            ]
            timer_ids = [
                item.findtext("Id", "").strip()
                for experiment_item in root.findall(
                    ".//ParamVariationExperiment"
                )
                for item in experiment_item.findall("Variables/Variable")
            ]
            object_ids = [item for item in top_level_ids + timer_ids if item]
            self.assertEqual(
                len(object_ids),
                len(set(object_ids)),
                "Top-level experiment and private timer IDs must be unique",
            )

        def semantic_signature(
            element: ET.Element,
        ) -> tuple[
            str,
            tuple[tuple[str, str], ...],
            str,
            tuple[object, ...],
        ]:
            text = " ".join((element.text or "").split())
            return (
                element.tag,
                tuple(sorted(element.attrib.items())),
                text,
                tuple(semantic_signature(child) for child in element),
            )

        self.assertEqual(
            semantic_signature(split),
            semantic_signature(single),
        )

    def test_two_stage_cutoff_uses_the_explicit_parameter_and_conserves_flow(
        self,
    ) -> None:
        event = ET.parse(CHECKPOINT_EVENTS).getroot().find("Event")
        self.assertIsNotNone(event)
        assert event is not None
        self.assertEqual(event.findtext("Name"), "arrivalCutoff")

        properties = event.find("Properties")
        self.assertIsNotNone(properties)
        assert properties is not None
        self.assertEqual(properties.attrib["TriggerType"], "timeout")
        self.assertEqual(properties.attrib["Mode"], "occuresOnce")
        self.assertEqual(
            properties.findtext("Timeout/Code"),
            "arrival_cutoff_seconds",
        )
        self.assertEqual(properties.findtext("Timeout/Unit"), "SECOND")
        self.assertEqual(properties.findtext("OccurrenceAtTime"), "true")
        self.assertEqual(
            properties.findtext("OccurrenceTime/Code"),
            "arrival_cutoff_seconds",
        )
        self.assertEqual(properties.findtext("OccurrenceTime/Unit"), "SECOND")

        self.assertIsNotNone(event.find("Action"))
        self.assertEqual(event.findtext("Action", ""), "")
        event_id = event.findtext("Id", "")
        code = split_event_action_code(CHECKPOINT_EVENT_CODE, event_id)
        self.assertEqual(
            code.count("travellerSource.arrival.reset();"),
            1,
        )
        self.assertEqual(
            code.count("travellerSource.reschedule.reset();"),
            1,
        )
        self.assertIn("arrivals_closed = true;", code)
        self.assertIn("completed_at_cutoff = completed;", code)
        self.assertIn("security_queue_at_cutoff = security_queue_count;", code)
        self.assertIn(
            "immigration_in_service_at_cutoff = immigration_in_service_count;",
            code,
        )

    def test_two_stage_oracle_parameters_reconstruct_the_exact_arrivals(
        self,
    ) -> None:
        defaults = checkpoint_parameter_defaults()
        parameters = embedded_parameters("travellerSource")

        self.assertEqual(
            parameters["firstArrivalTime"],
            "oracle_first_arrival_seconds",
        )
        self.assertEqual(parameters["maxArrivals"], "max_arrivals")
        self.assertEqual(
            parameters["interarrivalTime"],
            "admitted < oracle_interval_switch_after "
            "? oracle_early_interarrival_seconds "
            ": oracle_late_interarrival_seconds",
        )

        first = float(defaults["oracle_first_arrival_seconds"])
        early = float(defaults["oracle_early_interarrival_seconds"])
        late = float(defaults["oracle_late_interarrival_seconds"])
        switch_after = int(defaults["oracle_interval_switch_after"])
        maximum = int(defaults["max_arrivals"])
        arrivals = [first]
        for admitted in range(maximum - 1):
            interval = early if admitted < switch_after else late
            arrivals.append(arrivals[-1] + interval)
        self.assertEqual(arrivals, [0.0, 0.5, 1.0, 1.5, 2.5, 3.5])

    def test_two_stage_parameter_defaults_match_the_ready_contract(self) -> None:
        defaults = checkpoint_parameter_defaults()
        with MODEL_RUN_CONFIGS.open(encoding="utf-8", newline="") as stream:
            oracle = next(
                row
                for row in csv.DictReader(stream)
                if row["config_id"] == "VERIFY_TWO_STAGE_A"
            )

        expected_defaults = {
            "config_id": '"VERIFY_TWO_STAGE_A"',
            "scenario_id": '"VERIFY_2STAGE_C1"',
            "input_sample_id": '"DETERMINISTIC_LEDGER_A"',
            "replication_id": "1",
            "arrival_fixture_id": '"two_stage_six_person_fixture"',
            "max_arrivals": oracle["max_arrivals"],
            "arrival_cutoff_seconds": oracle["arrival_cutoff_seconds"],
            "security_capacity": oracle["security_capacity"],
            "immigration_capacity": oracle["immigration_capacity"],
            "security_queue_capacity": oracle["security_queue_capacity"],
            "immigration_queue_capacity": oracle[
                "immigration_queue_capacity"
            ],
            "security_service_p1_seconds": oracle[
                "security_service_p1_seconds"
            ],
            "immigration_service_p1_seconds": oracle[
                "immigration_service_p1_seconds"
            ],
            "oracle_first_arrival_seconds": "0.0",
            "oracle_early_interarrival_seconds": "0.5",
            "oracle_late_interarrival_seconds": "1.0",
            "oracle_interval_switch_after": "3",
        }
        self.assertEqual(defaults, expected_defaults)

    def test_hpp_arrival_harness_is_demand_only_source_to_sink(self) -> None:
        aoc = ET.parse(HPP_AOC).getroot()
        self.assertEqual(aoc.findtext("Name"), "HppArrivalModel")
        self.assertEqual(aoc.findtext("Id"), "1785093000001")

        embedded = ET.parse(HPP_EMBEDDED_OBJECTS).getroot().findall(
            "EmbeddedObject"
        )
        self.assertEqual(
            [item.findtext("Name") for item in embedded],
            ["travellerSource", "arrivalSink"],
        )
        self.assertEqual(
            [
                item.findtext("ActiveObjectClass/ClassName")
                for item in embedded
            ],
            ["Source", "Sink"],
        )
        text = HPP_EMBEDDED_OBJECTS.read_text(encoding="utf-8")
        for forbidden in ("<ClassName>Queue</ClassName>", "<ClassName>Delay</ClassName>",
                          "<ClassName>Service</ClassName>",
                          "<ClassName>ResourcePool</ClassName>"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, text)

        connectors = ET.parse(HPP_CONNECTORS).getroot().findall("Connector")
        self.assertEqual(len(connectors), 1)
        self.assertEqual(
            connectors[0].findtext(
                "SourceEmbeddedObjectReference/ItemName"
            ),
            "arrivalSink",
        )
        self.assertEqual(
            connectors[0].findtext(
                "TargetEmbeddedObjectReference/ItemName"
            ),
            "travellerSource",
        )

    def test_hpp_arrival_harness_matches_the_demand_contract(self) -> None:
        with MODEL_RUN_CONFIGS.open(encoding="utf-8", newline="") as stream:
            baseline = next(
                row
                for row in csv.DictReader(stream)
                if row["config_id"] == "BASELINE_LOCAL_WINDOW_HPP"
            )
        defaults = hpp_parameter_defaults()
        self.assertEqual(
            defaults,
            {
                "source_config_id": '"BASELINE_LOCAL_WINDOW_HPP"',
                "arrival_evidence_id": '"task1_final_aggregate"',
                "arrival_assumption": (
                    '"LOCAL_WINDOW_HPP_STATIONARY_INDEPENDENT"'
                ),
                "arrival_rate_per_second": baseline[
                    "arrival_rate_per_second"
                ],
                "arrival_cutoff_seconds": baseline[
                    "arrival_cutoff_seconds"
                ],
                "arrival_seed": f'{baseline["random_seed"]}L',
                "input_sample_id": '"HPP_SYNTHETIC_A"',
                "ple_max_generated_guard": "49000",
            },
        )
        expected = float(defaults["arrival_rate_per_second"]) * float(
            defaults["arrival_cutoff_seconds"]
        )
        self.assertAlmostEqual(expected, 34.0, delta=1e-5)
        self.assertNotIn("max_arrivals", defaults)

    def test_hpp_source_uses_rate_mode_and_a_real_cutoff(self) -> None:
        parameters = hpp_embedded_parameters("travellerSource")
        self.assertEqual(parameters["arrivalType"], "self.RATE")
        self.assertEqual(parameters["rate"], "arrival_rate_per_second")
        self.assertEqual(parameters["limitArrivals"], "false")
        self.assertNotIn("34", parameters["onExit"])

        source_root = ET.parse(HPP_EMBEDDED_OBJECTS).getroot()
        source = next(
            item
            for item in source_root.findall("EmbeddedObject")
            if item.findtext("Name") == "travellerSource"
        )
        rate = next(
            item
            for item in source.findall("Parameters/Parameter")
            if item.findtext("Name") == "rate"
        )
        self.assertEqual(rate.findtext("Value/Unit"), "PER_SECOND")

        event = ET.parse(HPP_EVENTS).getroot().find("Event")
        self.assertIsNotNone(event)
        assert event is not None
        self.assertEqual(event.findtext("Name"), "arrivalCutoff")
        self.assertEqual(
            event.findtext("Properties/Timeout/Code"),
            "arrival_cutoff_seconds",
        )
        self.assertIsNotNone(event.find("Action"))
        self.assertEqual(event.findtext("Action", ""), "")
        event_code = split_event_action_code(
            HPP_EVENT_CODE,
            event.findtext("Id", ""),
        )
        self.assertEqual(
            event_code.count(
                "travellerSource.set_rate( 0.0, PER_SECOND );"
            ),
            1,
        )
        self.assertIn("finishSimulation();", event_code)

    def test_hpp_experiment_is_explicitly_arrival_only_and_guarded(self) -> None:
        experiments = ET.parse(EXPERIMENTS).getroot()
        experiment = next(
            item
            for item in experiments.findall("SimulationExperiment")
            if item.findtext("Name") == "HppArrivalVerification"
        )
        self.assertEqual(
            experiment.attrib["ActiveObjectClassId"],
            "1785093000001",
        )
        self.assertEqual(experiment.findtext("BypassInitialScreen"), "true")
        before = experiment.findtext("BeforeSimulationRunCode", "")
        after = experiment.findtext("AfterSimulationRunCode", "")
        for fragment in (
            "LOCAL_WINDOW_HPP_STATIONARY_INDEPENDENT",
            "expectedCount + 10.0 * Math.sqrt( expectedCount )",
            "getDefaultRandomGenerator().setSeed( root.arrival_seed )",
        ):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, before)
        for fragment in (
            "DEMAND_MECHANISM_VERIFICATION",
            "ARRIVAL_ONLY",
            "arrival_ledger.csv",
            "root.travellerSource.count()",
            "arrivalTime >= root.arrival_cutoff_seconds",
        ):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, after)

    def test_two_stage_resources_and_services_reference_parameters(
        self,
    ) -> None:
        self.assertEqual(
            embedded_parameters("securityResources")["capacity"],
            "security_capacity",
        )
        self.assertEqual(
            embedded_parameters("immigrationResources")["capacity"],
            "immigration_capacity",
        )
        self.assertEqual(
            embedded_parameters("securityService")["queueCapacity"],
            "security_queue_capacity",
        )
        self.assertEqual(
            embedded_parameters("immigrationService")["queueCapacity"],
            "immigration_queue_capacity",
        )

        source_code = embedded_parameters("travellerSource")["onExit"]
        for name in (
            "security_service_p1_seconds",
            "immigration_service_p1_seconds",
            "input_sample_id",
            "replication_id",
        ):
            with self.subTest(name=name):
                self.assertIn(name, source_code)

    def test_traveller_has_no_hidden_service_time_defaults(self) -> None:
        split_root = ET.parse(CHECKPOINT_TRAVELLER_VARIABLES).getroot()
        split_initials = {
            variable.findtext("Name"): variable.findtext(
                "Properties/InitialValue/Code"
            )
            for variable in split_root.findall("Variable")
        }
        single_root = ET.parse(ALP).getroot()
        traveller = next(
            item
            for item in single_root.findall(".//ActiveObjectClass")
            if item.findtext("Name") == "CheckpointTraveller"
        )
        single_initials = {
            variable.findtext("Name"): variable.findtext(
                "Properties/InitialValue/Code"
            )
            for variable in traveller.findall("Variables/Variable")
        }
        for name in (
            "security_service_demand",
            "immigration_service_demand",
        ):
            with self.subTest(name=name):
                self.assertEqual(split_initials[name], "Double.NaN")
                self.assertEqual(single_initials[name], "Double.NaN")

    def test_two_stage_experiment_exposes_every_oracle_parameter(self) -> None:
        experiments = ET.parse(EXPERIMENTS).getroot()
        experiment = next(
            item
            for item in experiments.findall("SimulationExperiment")
            if item.findtext("Name") == "TwoStageDeterministic"
        )
        exposed = {
            parameter.findtext("ParameterName")
            for parameter in experiment.findall("Parameters/Parameter")
        }
        self.assertEqual(exposed, set(checkpoint_parameter_defaults()))

    def test_single_file_launch_copy_is_parseable_and_portable(self) -> None:
        root = ET.parse(ALP).getroot()
        text = ALP.read_text(encoding="utf-8")
        self.assertEqual(root.findtext("Model/Name"), "HTXCheckpointSimulationCLI")
        self.assertNotIn("splitVersion", root.attrib)
        self.assertIn("GatePV2x3", cdata_names(ALP))
        self.assertTrue(
            {"source", "queue", "delay", "sink"}.issubset(cdata_names(ALP))
        )
        self.assertNotIn(r"C:\Users", text)
        self.assertIn("config/anylogic_gate_manifest.csv", text)

    def test_single_file_copy_contains_the_two_stage_oracle(self) -> None:
        root = ET.parse(ALP).getroot()
        text = ALP.read_text(encoding="utf-8")
        names = cdata_names(ALP)
        for name in (
            "CheckpointModel",
            "CheckpointTraveller",
            "TwoStageDeterministic",
            "arrivalCutoff",
        ):
            self.assertIn(name, names)
        self.assertEqual(
            single_file_checkpoint_parameter_defaults(),
            checkpoint_parameter_defaults(),
        )
        checkpoint = next(
            item
            for item in root.findall("Model/ActiveObjectClasses/ActiveObjectClass")
            if item.findtext("Name") == "CheckpointModel"
        )
        traveller_source = next(
            item
            for item in checkpoint.findall("EmbeddedObjects/EmbeddedObject")
            if item.findtext("Name") == "travellerSource"
        )
        interarrival = next(
            item
            for item in traveller_source.findall("Parameters/Parameter")
            if item.findtext("Name") == "interarrivalTime"
        )
        self.assertEqual(
            " ".join(interarrival.findtext("Value/Code", "").split()),
            "admitted < oracle_interval_switch_after "
            "? oracle_early_interarrival_seconds "
            ": oracle_late_interarrival_seconds",
        )
        cutoff = next(
            item
            for item in checkpoint.findall("Events/Event")
            if item.findtext("Name") == "arrivalCutoff"
        )
        self.assertEqual(
            cutoff.findtext("Properties/Timeout/Code"),
            "arrival_cutoff_seconds",
        )
        self.assertEqual(
            cutoff.findtext("Properties/OccurrenceTime/Code"),
            "arrival_cutoff_seconds",
        )
        action = cutoff.findtext("Action", "")
        self.assertEqual(action.count("travellerSource.arrival.reset();"), 1)
        self.assertEqual(action.count("travellerSource.reschedule.reset();"), 1)
        for name in (
            "security_capacity",
            "immigration_capacity",
            "security_queue_capacity",
            "immigration_queue_capacity",
            "security_service_p1_seconds",
            "immigration_service_p1_seconds",
        ):
            with self.subTest(name=name):
                self.assertGreaterEqual(text.count(name), 3)
        self.assertIn("arrivals_closed = true;", text)
        self.assertIn("Cannot write two-stage verification outputs", text)

    def test_single_file_copy_contains_the_hpp_arrival_harness(self) -> None:
        root = ET.parse(ALP).getroot()
        names = cdata_names(ALP)
        self.assertIn("HppArrivalModel", names)
        self.assertIn("HppArrivalVerification", names)

        hpp = next(
            item
            for item in root.findall("Model/ActiveObjectClasses/ActiveObjectClass")
            if item.findtext("Name") == "HppArrivalModel"
        )
        cutoff = next(
            item
            for item in hpp.findall("Events/Event")
            if item.findtext("Name") == "arrivalCutoff"
        )
        self.assertEqual(
            cutoff.findtext("Properties/Timeout/Code"),
            "arrival_cutoff_seconds",
        )
        action = cutoff.findtext("Action", "")
        self.assertIn("travellerSource.set_rate( 0.0, PER_SECOND );", action)
        self.assertIn("finishSimulation();", action)

        experiment = next(
            item
            for item in root.findall("Model/Experiments/SimulationExperiment")
            if item.findtext("Name") == "HppArrivalVerification"
        )
        self.assertIn(
            '"ARRIVAL_ONLY"',
            experiment.findtext("AfterSimulationRunCode", ""),
        )


if __name__ == "__main__":
    unittest.main()
