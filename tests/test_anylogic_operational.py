from __future__ import annotations

import csv
import json
import re
import unittest
import xml.etree.ElementTree as ET
from decimal import Decimal
from pathlib import Path

from src.analysis.validate_operational_contract import (
    scenario_config_sha256,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODEL_ROOT = (
    PROJECT_ROOT
    / "simulation"
    / "anylogic"
    / "HTXCheckpointSimulation"
)
ALP_ROOT = MODEL_ROOT / "_alp"
EXPERIMENTS = ALP_ROOT / "Experiments.xml"
OP_MODEL = ALP_ROOT / "Agents" / "OperationalCheckpointModel"
OP_TRAVELLER = ALP_ROOT / "Agents" / "OperationalTraveller"
OP_MODEL_AOC = OP_MODEL / "AOC.OperationalCheckpointModel.xml"
OP_MODEL_VARIABLES = OP_MODEL / "Variables.xml"
OP_EMBEDDED = OP_MODEL / "EmbeddedObjects.xml"
OP_CONNECTORS = OP_MODEL / "Connectors.xml"
OP_EVENTS = OP_MODEL / "Code" / "Events.xml"
OP_EVENT_CODE = OP_MODEL / "Code" / "Events.java"
OP_TRAVELLER_AOC = OP_TRAVELLER / "AOC.OperationalTraveller.xml"
OP_TRAVELLER_VARIABLES = OP_TRAVELLER / "Variables.xml"
SCENARIOS = PROJECT_ROOT / "config" / "operational_scenarios.csv"
SCHEMAS = PROJECT_ROOT / "config" / "result_schema_registry.csv"


def _variables(path: Path, variable_class: str) -> dict[str, str]:
    root = ET.parse(path).getroot()
    value_path = (
        "Properties/DefaultValue/Code"
        if variable_class == "Parameter"
        else "Properties/InitialValue/Code"
    )
    return {
        variable.findtext("Name", "").strip(): variable.findtext(
            value_path, ""
        ).strip()
        for variable in root.findall("Variable")
        if variable.attrib.get("Class") == variable_class
    }


def _embedded() -> dict[str, ET.Element]:
    return {
        item.findtext("Name", "").strip(): item
        for item in ET.parse(OP_EMBEDDED).getroot().findall("EmbeddedObject")
    }


def _parameters(item: ET.Element) -> dict[str, tuple[str, str]]:
    return {
        parameter.findtext("Name", "").strip(): (
            parameter.findtext("Value/Code", "").strip(),
            parameter.findtext("Value/Unit", "").strip(),
        )
        for parameter in item.findall("Parameters/Parameter")
    }


def _operational_experiment() -> ET.Element:
    experiments = ET.parse(EXPERIMENTS).getroot()
    matches = [
        item
        for item in experiments.findall("SimulationExperiment")
        if item.findtext("Name") == "OperationalInteractive"
    ]
    if len(matches) != 1:
        raise AssertionError(
            f"Expected one OperationalInteractive experiment, got {len(matches)}"
        )
    return matches[0]


def _operational_pilot() -> ET.Element:
    experiments = ET.parse(EXPERIMENTS).getroot()
    matches = [
        item
        for item in experiments.findall("ParamVariationExperiment")
        if item.findtext("Name") == "OperationalPilot"
    ]
    if len(matches) != 1:
        raise AssertionError(
            f"Expected one OperationalPilot experiment, got {len(matches)}"
        )
    return matches[0]


def _event_action(event_id: str) -> str:
    raw = OP_EVENT_CODE.read_text(encoding="utf-8")
    start = f"/*ALCODESTART::{event_id}*/"
    if raw.count(start) != 1 or raw.count("/*ALCODEEND*/") != 1:
        raise AssertionError("Operational cutoff must have one code-marker pair")
    return raw.split(start, 1)[1].split("/*ALCODEEND*/", 1)[0]


def _schema_fields(table_name: str) -> list[str]:
    with SCHEMAS.open(encoding="utf-8", newline="") as stream:
        rows = [
            row
            for row in csv.DictReader(stream)
            if row["table_name"] == table_name
        ]
    rows.sort(key=lambda row: int(row["ordinal"]))
    return [row["field_name"] for row in rows]


def _java_header(after_code: str, variable_name: str) -> list[str]:
    marker = f"{variable_name}.add("
    start = after_code.index(marker) + len(marker)
    end = after_code.index(");", start)
    literals = re.findall(r'"((?:\\.|[^"\\])*)"', after_code[start:end])
    header = "".join(bytes(value, "utf-8").decode("unicode_escape") for value in literals)
    return header.split(",")


def _indexed_values(expression: str, count: int) -> list[str]:
    parts = expression.split("\n\t: ")
    if len(parts) == 1:
        return [expression] * count
    if len(parts) != count:
        raise AssertionError(
            f"Expected {count} indexed values, found {len(parts)}"
        )
    values: list[str] = []
    for index, part in enumerate(parts[:-1]):
        prefix = f"index == {index} ? "
        if not part.startswith(prefix):
            raise AssertionError(
                f"Malformed indexed expression at {index}: {part}"
            )
        values.append(part[len(prefix) :])
    values.append(parts[-1])
    return values


def _java_test_literal(value_type: str, raw: str) -> str:
    value = raw.strip()
    if value_type == "String":
        return json.dumps(value)
    if value_type == "int":
        return str(int(value))
    if value_type == "long":
        return f"{int(value)}L"
    if value_type == "double":
        if value == "":
            return "0.0"
        if "." not in value and "e" not in value.lower():
            value += ".0"
        return value
    raise AssertionError(value_type)


class AnyLogicOperationalModelTests(unittest.TestCase):
    def test_operational_classes_are_independent_gui_owned_objects(self) -> None:
        model_aoc = ET.parse(OP_MODEL_AOC).getroot()
        traveller_aoc = ET.parse(OP_TRAVELLER_AOC).getroot()
        self.assertEqual(model_aoc.findtext("Name"), "OperationalCheckpointModel")
        self.assertEqual(model_aoc.findtext("Id"), "1785162520364")
        self.assertIsNotNone(model_aoc.find("Variables"))
        self.assertIsNotNone(model_aoc.find("Events"))
        self.assertIsNotNone(model_aoc.find("EmbeddedObjects"))
        self.assertEqual(traveller_aoc.findtext("Name"), "OperationalTraveller")
        self.assertEqual(traveller_aoc.findtext("Id"), "1785162453950")
        self.assertIsNotNone(traveller_aoc.find("Variables"))
        experiment = _operational_experiment()
        self.assertEqual(
            experiment.attrib["ActiveObjectClassId"],
            model_aoc.findtext("Id"),
        )

    def test_reference_defaults_match_the_executable_scenario_contract(self) -> None:
        with SCENARIOS.open(encoding="utf-8", newline="") as stream:
            reference = next(
                row
                for row in csv.DictReader(stream)
                if row["scenario_id"] == "REFERENCE_ASSUMPTION_SANDBOX_V1"
            )
        defaults = _variables(OP_MODEL_VARIABLES, "Parameter")
        direct_mapping = (
            "schema_version",
            "config_id",
            "scenario_id",
            "scenario_family",
            "reference_scenario_id",
            "input_sample_id",
            "calibration_status",
            "claim_ceiling",
            "crn_alignment_status",
            "arrival_mode",
            "arrival_rate_per_second",
            "demand_multiplier",
            "arrival_guard",
            "drain_rule",
            "security_capacity",
            "security_queue_capacity",
            "security_service_distribution",
            "security_service_p1_seconds",
            "immigration_capacity",
            "immigration_queue_capacity",
            "immigration_service_distribution",
            "immigration_service_p1_seconds",
            "queue_policy",
            "automation_mapping_mode",
            "automation_uptake",
            "automation_multiplier",
            "additional_check_semantics",
            "additional_check_probability_conventional",
            "additional_check_probability_technology",
            "additional_check_service_distribution",
        )
        string_fields = {
            name
            for name in direct_mapping
            if name
            in {
                "schema_version",
                "config_id",
                "scenario_id",
                "scenario_family",
                "reference_scenario_id",
                "input_sample_id",
                "start_state",
                "calibration_status",
                "claim_ceiling",
                "crn_alignment_status",
                "arrival_mode",
                "drain_rule",
                "security_service_distribution",
                "immigration_service_distribution",
                "queue_policy",
                "automation_mapping_mode",
                "additional_check_semantics",
                "additional_check_service_distribution",
            }
        }
        for name in direct_mapping:
            expected = reference[name]
            if name in string_fields:
                expected = f'"{expected}"'
            with self.subTest(name=name):
                if name in string_fields:
                    self.assertEqual(defaults[name], expected)
                else:
                    self.assertEqual(Decimal(defaults[name]), Decimal(expected))
        self.assertEqual(defaults["arrival_cutoff_seconds"], "300.0")
        self.assertEqual(defaults["additional_check_service_p1_seconds"], "0.0")
        self.assertEqual(defaults["start_state"], '"EMPTY_AND_IDLE"')
        self.assertEqual(
            defaults["output_collection_id"],
            '"anylogic_operational"',
        )
        self.assertEqual(defaults["config_sha256"], (
            '"166e6c918cff63041b08f31ff5c17fbea49008b8cdd3047b1082b326faae3460"'
        ))
        self.assertEqual(defaults["master_seed"], "2026072800L")
        self.assertEqual(defaults["arrival_seed"], "2026072801L")
        self.assertEqual(defaults["service_seed"], "2026072802L")
        self.assertEqual(defaults["routing_seed"], "2026072803L")
        self.assertEqual(defaults["tie_seed"], "2026072804L")

    def test_random_streams_are_reseeded_without_forward_field_references(
        self,
    ) -> None:
        variables = _variables(OP_MODEL_VARIABLES, "PlainVariable")
        self.assertEqual(variables["routing_rng"], "null")
        self.assertEqual(variables["tie_rng"], "null")
        before = _operational_experiment().findtext(
            "BeforeSimulationRunCode", ""
        )
        self.assertNotIn("root.routing_rng", before)
        self.assertNotIn("root.tie_rng", before)
        self.assertIn(
            "getEngine().getDefaultRandomGenerator().setSeed( root.arrival_seed );",
            before,
        )
        source = _parameters(_embedded()["travellerSource"])["onExit"][0]
        self.assertIn(
            "routing_rng = new java.util.Random( routing_seed )",
            source,
        )
        self.assertIn(
            "tie_rng = new java.util.Random( tie_seed )",
            source,
        )

    def test_hpp_source_cutoff_and_full_drain_are_explicit(self) -> None:
        blocks = _embedded()
        source = _parameters(blocks["travellerSource"])
        self.assertEqual(source["arrivalType"][0], "self.RATE")
        self.assertEqual(
            source["rate"],
            ("arrival_rate_per_second * demand_multiplier", "PER_SECOND"),
        )
        self.assertEqual(source["limitArrivals"][0], "false")
        self.assertIn("arrivalTime >= arrival_cutoff_seconds", source["onExit"][0])
        self.assertEqual(source["maxArrivals"][0], "")
        self.assertEqual(
            blocks["travellerSource"].findtext(
                ".//EntityEmbeddedObject/GenericParameterSubstitute/"
                "GenericParameterSubstituteReference/ItemName"
            ),
            ET.parse(OP_TRAVELLER_AOC).getroot().findtext(
                "GenericParameter/Id"
            ),
        )

        event = ET.parse(OP_EVENTS).getroot().find("Event")
        self.assertIsNotNone(event)
        assert event is not None
        self.assertEqual(event.findtext("Name"), "arrivalCutoff")
        self.assertEqual(
            event.findtext("Properties/Timeout/Code"),
            "arrival_cutoff_seconds",
        )
        self.assertEqual(
            event.findtext("Properties/OccurrenceTime/Code"),
            "arrival_cutoff_seconds",
        )
        action = _event_action(event.findtext("Id", ""))
        self.assertIn("travellerSource.set_rate( 0.0, PER_SECOND );", action)
        self.assertIn("arrivals_closed = true;", action)
        self.assertIn("admitted_at_cutoff = admitted;", action)
        self.assertIn("if ( completed == admitted )", action)

        sink = _parameters(blocks["checkpointSink"])["onEnter"][0]
        self.assertIn("if ( arrivals_closed && completed == admitted )", sink)
        self.assertIn('run_status = "COMPLETE";', sink)
        self.assertIn("finishSimulation();", sink)

    def test_v1_is_pooled_fcfs_and_additional_work_holds_the_counter(
        self,
    ) -> None:
        blocks = _embedded()
        classes = [
            item.findtext("ActiveObjectClass/ClassName")
            for item in blocks.values()
        ]
        self.assertEqual(classes.count("ResourcePool"), 2)
        self.assertEqual(classes.count("Service"), 2)
        self.assertNotIn("SelectOutput", classes)
        self.assertNotIn("Queue", classes)

        security_resource = _parameters(blocks["securityResources"])
        immigration_resource = _parameters(blocks["immigrationResources"])
        security_service = _parameters(blocks["securityService"])
        immigration_service = _parameters(blocks["immigrationService"])
        self.assertEqual(security_resource["capacity"][0], "security_capacity")
        self.assertEqual(
            immigration_resource["capacity"][0], "immigration_capacity"
        )
        self.assertEqual(
            security_service["queueCapacity"][0], "security_queue_capacity"
        )
        self.assertEqual(
            immigration_service["queueCapacity"][0],
            "immigration_queue_capacity",
        )
        self.assertEqual(
            security_service["delayTime"],
            (
                "((OperationalTraveller) agent).security_service_demand",
                "SECOND",
            ),
        )
        immigration_delay = immigration_service["delayTime"][0]
        self.assertIn("immigration_primary_service_demand", immigration_delay)
        self.assertIn("additional_check_service_demand", immigration_delay)
        self.assertEqual(immigration_service["delayTime"][1], "SECOND")
        self.assertIn(
            'immigration_lane_id = "IMMIGRATION_POOLED"',
            immigration_service["onEnter"][0],
        )

    def test_traveller_contains_the_complete_event_lineage(self) -> None:
        variables = _variables(OP_TRAVELLER_VARIABLES, "PlainVariable")
        expected = {
            "traveller_id",
            "input_sample_id",
            "replication_id",
            "arrival",
            "security_service_demand",
            "immigration_conventional_service_demand",
            "automation_u",
            "additional_check_u",
            "lane_tie_u",
            "security_queue_join",
            "security_start",
            "security_end",
            "immigration_queue_join",
            "immigration_lane_id",
            "immigration_start",
            "technology_flag",
            "immigration_primary_service_demand",
            "immigration_primary_end",
            "additional_check_flag",
            "additional_check_service_demand",
            "additional_check_end",
            "exit",
            "security_resource_id",
            "immigration_resource_id",
        }
        self.assertEqual(set(variables), expected)
        for name in (
            "arrival",
            "security_service_demand",
            "immigration_conventional_service_demand",
            "automation_u",
            "additional_check_u",
            "lane_tie_u",
        ):
            with self.subTest(name=name):
                self.assertEqual(variables[name], "Double.NaN")

    def test_experiment_is_fail_fast_and_exposes_every_parameter(self) -> None:
        experiment = _operational_experiment()
        self.assertEqual(experiment.findtext("BypassInitialScreen"), "false")
        self.assertEqual(
            experiment.findtext("ModelTimeProperties/StopOption"),
            "Never",
        )
        before = experiment.findtext("BeforeSimulationRunCode", "")
        after = experiment.findtext("AfterSimulationRunCode", "")
        for fragment in (
            "v1 implements pooled FCFS only",
            "claim-boundary fields were weakened",
            "arrival_guard must exceed expected arrivals",
            "COUNTER_HELD_RISK_REFERRAL_PROXY",
            "OperationalInteractive is locked to the canonical reference row",
            "166e6c918cff63041b08f31ff5c17fbea49008b8cdd3047b1082b326faae3460",
        ):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, before)
        for fragment in (
            "full-drain conservation failed",
            "cutoff conservation failed",
            "operational run did not reach COMPLETE",
            "run_manifest.csv",
            "entity_log.csv",
            "replication_kpis.csv",
        ):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, after)
        exposed = {
            parameter.findtext("ParameterName")
            for parameter in experiment.findall("Parameters/Parameter")
        }
        self.assertEqual(
            exposed,
            set(_variables(OP_MODEL_VARIABLES, "Parameter")),
        )

    def test_operational_pilot_is_exact_serial_15_by_10_batch(self) -> None:
        pilot = _operational_pilot()
        self.assertEqual(
            pilot.attrib["ActiveObjectClassId"],
            ET.parse(OP_MODEL_AOC).getroot().findtext("Id"),
        )
        self.assertEqual(pilot.findtext("Id"), "1785196300833")
        self.assertEqual(pilot.findtext("AllowParallelEvaluations"), "false")
        self.assertEqual(pilot.findtext("UseFreeformParameters"), "true")
        self.assertEqual(pilot.findtext("NumberOfRuns"), "15")
        self.assertEqual(
            pilot.findtext("ModelTimeProperties/StopOption"),
            "Never",
        )
        replications = pilot.find("ReplicationsProperties")
        self.assertIsNotNone(replications)
        assert replications is not None
        self.assertEqual(replications.findtext("UseReplication"), "true")
        self.assertEqual(
            replications.findtext("FixedReplicationsNumber"),
            "true",
        )
        self.assertEqual(
            replications.findtext("ReplicationPerIteration"),
            "10",
        )
        self.assertEqual(replications.findtext("ConfidenceLevel"), "LEVEL_95")

        parameter_root = ET.parse(OP_MODEL_VARIABLES).getroot()
        parameter_ids = {
            item.findtext("Name", "").strip(): item.findtext("Id", "").strip()
            for item in parameter_root.findall("Variable")
            if item.attrib.get("Class") == "Parameter"
        }
        parameter_types = {
            item.findtext("Name", "").strip(): item.findtext(
                "Properties/Type", ""
            ).strip()
            for item in parameter_root.findall("Variable")
            if item.attrib.get("Class") == "Parameter"
        }
        parameter_defaults = {
            item.findtext("Name", "").strip(): item.findtext(
                "Properties/DefaultValue/Code", ""
            ).strip()
            for item in parameter_root.findall("Variable")
            if item.attrib.get("Class") == "Parameter"
        }
        freeform = {
            item.findtext("Id", "").strip(): item.findtext(
                "Expression/Code", ""
            ).strip()
            for item in pilot.findall("FreeformParamValue")
        }
        fixed = {
            item.findtext("Id", "").strip()
            for item in pilot.findall("RangeVariationParamValue")
            if item.findtext("Type") == "FIXED"
        }
        self.assertEqual(len(parameter_ids), 42)
        self.assertEqual(set(freeform), set(parameter_ids.values()))
        self.assertEqual(fixed, set(parameter_ids.values()))
        self.assertTrue(all(freeform.values()))

        with SCENARIOS.open(encoding="utf-8", newline="") as stream:
            scenarios = list(csv.DictReader(stream))
        self.assertEqual(len(scenarios), 15)
        for field in ("scenario_id", "config_id"):
            expression = freeform[parameter_ids[field]]
            for row in scenarios:
                with self.subTest(field=field, value=row[field]):
                    self.assertIn(f'"{row[field]}"', expression)
        hash_expression = freeform[parameter_ids["config_sha256"]]
        for row in scenarios:
            with self.subTest(hash_scenario=row["scenario_id"]):
                self.assertIn(
                    f'"{scenario_config_sha256(row)}"',
                    hash_expression,
                )
        self.assertEqual(
            freeform[parameter_ids["output_collection_id"]],
            '"anylogic_operational_batch"',
        )
        self.assertEqual(
            freeform[parameter_ids["additional_check_service_p1_seconds"]]
            .splitlines()[0],
            "index == 0 ? 0.0",
        )
        seed_offsets = {
            "arrival_seed": 1,
            "service_seed": 2,
            "routing_seed": 3,
            "tie_seed": 4,
        }
        for name in parameter_ids:
            actual_values = _indexed_values(
                freeform[parameter_ids[name]],
                len(scenarios),
            )
            expected_values: list[str] = []
            for row in scenarios:
                if name == "output_collection_id":
                    expected = '"anylogic_operational_batch"'
                elif name == "config_sha256":
                    expected = json.dumps(scenario_config_sha256(row))
                elif name in seed_offsets:
                    expected = (
                        f"{int(row['master_seed']) + seed_offsets[name]}L"
                    )
                elif name == "replication_id":
                    expected = "0"
                elif name in {"model_version", "start_state"}:
                    expected = parameter_defaults[name]
                else:
                    expected = _java_test_literal(
                        parameter_types[name],
                        row[name],
                    )
                expected_values.append(expected)
            with self.subTest(parameter_mapping=name):
                self.assertEqual(actual_values, expected_values)

        before = pilot.findtext("BeforeSimulationRunCode", "")
        for fragment in (
            "getCurrentReplication()",
            "scenarioSeedIndex",
            "100000L * (long) scenarioSeedIndex",
            "100L * (long) replication",
            "root.arrival_seed = streamBase + 1L",
            "root.tie_seed = streamBase + 4L",
            "OperationalPilot scenario lineage mismatch",
            "anylogic_operational_batch",
        ):
            with self.subTest(before_fragment=fragment):
                self.assertIn(fragment, before)
        self.assertNotIn(
            "OperationalInteractive is locked to the canonical reference row",
            before,
        )
        after = pilot.findtext("AfterSimulationRunCode", "")
        self.assertIn("root.output_collection_id", after)
        timer = pilot.findtext(
            "Variables/Variable/Properties/InitialValue/Code",
            "",
        )
        self.assertIn("OperationalPilot.this.run()", timer)

    def test_export_headers_match_the_registered_contract_exactly(self) -> None:
        after = _operational_experiment().findtext(
            "AfterSimulationRunCode", ""
        )
        for table_name, variable_name in (
            ("run_manifest", "manifest"),
            ("entity_log", "entities"),
            ("replication_kpis", "kpis"),
        ):
            with self.subTest(table_name=table_name):
                self.assertEqual(
                    _java_header(after, variable_name),
                    _schema_fields(table_name),
                )

    def test_generated_object_ids_are_unique_and_connector_chain_is_exact(
        self,
    ) -> None:
        paths = [
            OP_MODEL_AOC,
            OP_MODEL_VARIABLES,
            OP_EMBEDDED,
            OP_CONNECTORS,
            OP_EVENTS,
            OP_TRAVELLER_AOC,
            OP_TRAVELLER_VARIABLES,
        ]
        ids: list[str] = []
        for path in paths:
            ids.extend(
                element.text.strip()
                for element in ET.parse(path).getroot().iter("Id")
                if element.text
            )
        experiment = _operational_experiment()
        ids.extend(
            element.text.strip()
            for element in experiment.iter("Id")
            if element.text
        )
        self.assertEqual(len(ids), len(set(ids)))

        connectors = ET.parse(OP_CONNECTORS).getroot().findall("Connector")
        self.assertEqual(len(connectors), 3)
        pairs = [
            (
                connector.findtext(
                    "TargetEmbeddedObjectReference/ItemName"
                ),
                connector.findtext(
                    "SourceEmbeddedObjectReference/ItemName"
                ),
            )
            for connector in connectors
        ]
        self.assertEqual(
            pairs,
            [
                ("securityService", "travellerSource"),
                ("immigrationService", "securityService"),
                ("checkpointSink", "immigrationService"),
            ],
        )


if __name__ == "__main__":
    unittest.main()
