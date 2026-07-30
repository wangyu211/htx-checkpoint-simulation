from __future__ import annotations

import csv
import json
import re
import unittest
import xml.etree.ElementTree as ET
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path

from src.analysis.confirmatory_design import (
    build_confirmatory_scenario_rows,
    load_confirmatory_seed_rows,
)
from src.analysis.capacity_availability_design import (
    load_capacity_availability_scenario_rows,
    load_capacity_availability_seed_rows,
)
from src.analysis.capacity_response_surface_design import (
    load_response_surface_scenario_rows,
    load_response_surface_seed_rows,
)
from src.analysis.peak_duration_sensitivity_design import (
    load_peak_duration_scenario_rows,
    load_peak_duration_seed_rows,
)
from src.analysis.service_variability_design import (
    MODEL_VERSION as SERVICE_VARIABILITY_MODEL_VERSION,
    load_service_variability_scenario_rows,
    load_service_variability_seed_rows,
    service_scenario_config_sha256,
)
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
SPLIT_ALPX = MODEL_ROOT / "HTXCheckpointSimulation.alpx"
ALP_ROOT = MODEL_ROOT / "_alp"
EXPERIMENTS = ALP_ROOT / "Experiments.xml"
OP_MODEL = ALP_ROOT / "Agents" / "OperationalCheckpointModel"
OP_TRAVELLER = ALP_ROOT / "Agents" / "OperationalTraveller"
OP_MODEL_AOC = OP_MODEL / "AOC.OperationalCheckpointModel.xml"
OP_MODEL_ADDITIONAL_CLASS = OP_MODEL / "Code" / "AdditionalClass.java"
OP_MODEL_ADDITIONAL_CLASS_CODE = (
    OP_MODEL / "Code" / "AdditionalClassCode.java"
)
OP_MODEL_VARIABLES = OP_MODEL / "Variables.xml"
OP_EMBEDDED = OP_MODEL / "EmbeddedObjects.xml"
OP_CONNECTORS = OP_MODEL / "Connectors.xml"
OP_EVENTS = OP_MODEL / "Code" / "Events.xml"
OP_EVENT_CODE = OP_MODEL / "Code" / "Events.java"
OP_TRAVELLER_AOC = OP_TRAVELLER / "AOC.OperationalTraveller.xml"
OP_TRAVELLER_VARIABLES = OP_TRAVELLER / "Variables.xml"
SINGLE_ALP = (
    PROJECT_ROOT
    / "simulation"
    / "anylogic"
    / "HTXCheckpointSimulationCLI"
    / "HTXCheckpointSimulationCLI.alp"
)
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


def _confirmatory_experiment() -> ET.Element:
    experiments = ET.parse(EXPERIMENTS).getroot()
    matches = [
        item
        for item in experiments.findall("ParamVariationExperiment")
        if item.findtext("Name") == "CapacityRobustnessConfirmatory"
    ]
    if len(matches) != 1:
        raise AssertionError(
            "Expected one CapacityRobustnessConfirmatory experiment, "
            f"got {len(matches)}"
        )
    return matches[0]


def _availability_experiment() -> ET.Element:
    experiments = ET.parse(EXPERIMENTS).getroot()
    matches = [
        item
        for item in experiments.findall("ParamVariationExperiment")
        if item.findtext("Name") == "CapacityAvailabilityStress"
    ]
    if len(matches) != 1:
        raise AssertionError(
            "Expected one CapacityAvailabilityStress experiment, "
            f"got {len(matches)}"
        )
    return matches[0]


def _response_surface_experiment() -> ET.Element:
    experiments = ET.parse(EXPERIMENTS).getroot()
    matches = [
        item
        for item in experiments.findall("ParamVariationExperiment")
        if item.findtext("Name") == "CapacityResponseSurfaceExploratory"
    ]
    if len(matches) != 1:
        raise AssertionError(
            "Expected one CapacityResponseSurfaceExploratory experiment, "
            f"got {len(matches)}"
        )
    return matches[0]


def _named_parameter_variation_experiment(name: str) -> ET.Element:
    experiments = ET.parse(EXPERIMENTS).getroot()
    matches = [
        item
        for item in experiments.findall("ParamVariationExperiment")
        if item.findtext("Name") == name
    ]
    if len(matches) != 1:
        raise AssertionError(
            f"Expected one {name} experiment, got {len(matches)}"
        )
    return matches[0]


def _operational_parameter_metadata(
) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    root = ET.parse(OP_MODEL_VARIABLES).getroot()
    parameters = [
        item
        for item in root.findall("Variable")
        if item.attrib.get("Class") == "Parameter"
    ]
    return (
        {
            item.findtext("Name", "").strip(): item.findtext(
                "Id", ""
            ).strip()
            for item in parameters
        },
        {
            item.findtext("Name", "").strip(): item.findtext(
                "Properties/Type", ""
            ).strip()
            for item in parameters
        },
        {
            item.findtext("Name", "").strip(): item.findtext(
                "Properties/DefaultValue/Code", ""
            ).strip()
            for item in parameters
        },
    )


def _experiment_parameter_values(
    experiment: ET.Element,
) -> tuple[dict[str, str], set[str]]:
    freeform = {
        item.findtext("Id", "").strip(): item.findtext(
            "Expression/Code", ""
        ).strip()
        for item in experiment.findall("FreeformParamValue")
    }
    fixed = {
        item.findtext("Id", "").strip()
        for item in experiment.findall("RangeVariationParamValue")
        if item.findtext("Type") == "FIXED"
    }
    return freeform, fixed


def _assert_full_parameter_mapping(
    test: unittest.TestCase,
    *,
    experiment: ET.Element,
    rows: list[dict[str, str]],
    seed_rows: list[dict[str, str]],
    output_collection_id: str,
    config_hash: Callable[[dict[str, str]], str],
    model_version: str | None = None,
) -> None:
    parameter_ids, parameter_types, parameter_defaults = (
        _operational_parameter_metadata()
    )
    freeform, fixed = _experiment_parameter_values(experiment)
    test.assertEqual(len(parameter_ids), 44)
    test.assertEqual(set(freeform), set(parameter_ids.values()))
    test.assertEqual(fixed, set(parameter_ids.values()))
    test.assertTrue(all(freeform.values()))

    first_seed_by_input = {
        row["input_sample_id"]: row
        for row in seed_rows
        if row["replication_id"] == "1"
    }
    for name in parameter_ids:
        actual = _indexed_values(
            freeform[parameter_ids[name]],
            len(rows),
        )
        expected: list[str] = []
        for row in rows:
            if name == "output_collection_id":
                value = json.dumps(output_collection_id)
            elif name == "config_sha256":
                value = json.dumps(config_hash(row))
            elif name in {
                "arrival_seed",
                "service_seed",
                "routing_seed",
                "tie_seed",
            }:
                seed = first_seed_by_input[row["input_sample_id"]]
                value = f"{seed[name]}L"
            elif name == "replication_id":
                value = "0"
            elif name == "model_version":
                value = (
                    json.dumps(model_version)
                    if model_version is not None
                    else parameter_defaults[name]
                )
            elif name == "start_state" or name not in row:
                value = parameter_defaults[name]
            else:
                value = _java_test_literal(
                    parameter_types[name],
                    row[name],
                )
            expected.append(value)
        with test.subTest(
            experiment=experiment.findtext("Name"),
            parameter=name,
        ):
            test.assertEqual(actual, expected)


def _assert_exact_serial_batch(
    test: unittest.TestCase,
    *,
    experiment: ET.Element,
    experiment_id: str,
    number_of_cells: int,
    replications_per_cell: int,
    timer_name: str,
    timer_id: str,
) -> None:
    test.assertEqual(
        experiment.attrib["ActiveObjectClassId"],
        ET.parse(OP_MODEL_AOC).getroot().findtext("Id"),
    )
    test.assertEqual(experiment.findtext("Id"), experiment_id)
    test.assertEqual(
        experiment.findtext("AllowParallelEvaluations"),
        "false",
    )
    test.assertEqual(experiment.findtext("UseFreeformParameters"), "true")
    test.assertEqual(
        experiment.findtext("NumberOfRuns"),
        str(number_of_cells),
    )
    test.assertEqual(
        experiment.findtext("ModelTimeProperties/StopOption"),
        "Never",
    )
    replications = experiment.find("ReplicationsProperties")
    test.assertIsNotNone(replications)
    assert replications is not None
    test.assertEqual(replications.findtext("UseReplication"), "true")
    test.assertEqual(
        replications.findtext("FixedReplicationsNumber"),
        "true",
    )
    for field in (
        "ReplicationPerIteration",
        "MinimumReplication",
        "MaximumReplication",
    ):
        test.assertEqual(
            replications.findtext(field),
            str(replications_per_cell),
        )
    test.assertEqual(replications.findtext("ConfidenceLevel"), "LEVEL_95")

    timers = [
        item
        for item in experiment.findall("Variables/Variable")
        if item.findtext("Name") == timer_name
    ]
    test.assertEqual(len(timers), 1)
    timer = timers[0]
    test.assertEqual(timer.findtext("Id"), timer_id)
    test.assertEqual(timer.findtext("PresentationFlag"), "false")
    test.assertEqual(timer.findtext("ShowLabel"), "false")
    properties = timer.find("Properties")
    test.assertIsNotNone(properties)
    assert properties is not None
    test.assertEqual(properties.attrib.get("AccessType"), "private")
    test.assertEqual(properties.attrib.get("SaveInSnapshot"), "false")
    test.assertEqual(properties.findtext("Type"), "javax.swing.Timer")
    timer_code = properties.findtext("InitialValue/Code", "")
    experiment_name = experiment.findtext("Name", "")
    test.assertEqual(
        timer_code.count(f"{experiment_name}.this.run();"),
        1,
    )
    test.assertEqual(timer_code.count("setRepeats(false);"), 1)


def _physical_line_break(path: Path) -> bytes:
    raw = path.read_bytes()
    first_lf = raw.find(b"\n")
    if first_lf < 0:
        raise AssertionError(f"{path}: no line break found")
    return (
        b"\r\n"
        if first_lf > 0 and raw[first_lf - 1 : first_lf + 1] == b"\r\n"
        else b"\n"
    )


def _event_action(event_id: str) -> str:
    """Extract code with the same raw marker contract as AnyLogic 8.9."""

    line_break = _physical_line_break(SPLIT_ALPX)
    raw = OP_EVENT_CODE.read_bytes()
    start = (
        f"/*ALCODESTART::{event_id}*/".encode("utf-8") + line_break
    )
    end = line_break + b"/*ALCODEEND*/"
    if raw.count(start) != 1 or raw.count(end) != 1:
        raise AssertionError(
            "Operational cutoff must have one loader-compatible "
            "code-marker pair"
        )
    return raw.split(start, 1)[1].split(end, 1)[0].decode("utf-8")


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
        self.assertEqual(defaults["security_service_cv"], "0.0")
        self.assertEqual(defaults["immigration_service_cv"], "0.0")

    def test_random_streams_are_reseeded_without_forward_field_references(
        self,
    ) -> None:
        variables = _variables(OP_MODEL_VARIABLES, "PlainVariable")
        self.assertEqual(variables["routing_rng"], "null")
        self.assertEqual(variables["tie_rng"], "null")
        self.assertEqual(variables["security_service_rng"], "null")
        self.assertEqual(variables["immigration_service_rng"], "null")
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

        service_code = OP_MODEL_ADDITIONAL_CLASS_CODE.read_text(
            encoding="utf-8"
        )
        self.assertIn(
            "service_seed ^ 0x13579BDF2468ACE1L",
            service_code,
        )
        self.assertIn(
            "service_seed ^ 0x2468ACE113579BDFL",
            service_code,
        )
        self.assertEqual(
            service_code.count("new java.util.Random("),
            2,
            "Security and Immigration need exactly two independently "
            "derived stage-local service streams",
        )
        self.assertIn("nextExplicitStandardNormal", service_code)
        self.assertIn("Math.sqrt( -2.0 * Math.log( u1 ) )", service_code)
        self.assertIn(
            "Math.log(\n\t\t1.0 + coefficientOfVariation "
            "* coefficientOfVariation",
            service_code,
        )
        self.assertIn(
            "-0.5 * sigmaSquared + sigma * latentZ",
            service_code,
        )
        fixed_return = service_code.index("return meanSeconds;")
        latent_draw = service_code.index(
            "double latentZ = nextExplicitStandardNormal( rng );"
        )
        self.assertLess(
            fixed_return,
            latent_draw,
            "The fixed-service arm must not consume a latent service draw",
        )
        self.assertIn(
            "security_service_distribution,\n"
            "\tsecurity_service_p1_seconds,\n"
            "\tsecurity_service_cv,\n"
            "\tsecurity_service_rng",
            source,
        )
        self.assertIn(
            "immigration_service_distribution,\n"
            "\timmigration_service_p1_seconds,\n"
            "\timmigration_service_cv,\n"
            "\timmigration_service_rng",
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
        self.assertIn(
            "travellerSource.arrival.reset();",
            action,
        )
        self.assertIn("travellerSource.reschedule.reset();", action)
        self.assertIn("arrivals_closed = true;", action)
        self.assertIn("admitted_at_cutoff = admitted;", action)
        self.assertIn("if ( completed == admitted )", action)
        self.assertEqual(
            _physical_line_break(OP_EVENT_CODE),
            _physical_line_break(SPLIT_ALPX),
            "AnyLogic silently drops ALCODE actions when the sidecar and "
            "parent ALPX use different physical line endings",
        )

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
            "security_processing_end",
            "interstage_block_start",
            "interstage_admitted",
            "interstage_block_seconds",
            "interstage_waiting_flag",
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

    def test_experiment_is_fail_fast_and_exposes_only_effective_controls(
        self,
    ) -> None:
        experiment = _operational_experiment()
        self.assertEqual(experiment.findtext("BypassInitialScreen"), "false")
        self.assertEqual(
            experiment.findtext("ModelTimeProperties/StopOption"),
            "Never",
        )
        self.assertEqual(
            experiment.findtext("PresentationProperties/ExecutionMode"),
            "realTimeScaled",
        )
        self.assertEqual(
            experiment.findtext("PresentationProperties/RealTimeScale"),
            "5.0",
        )
        before = experiment.findtext("BeforeSimulationRunCode", "")
        after = experiment.findtext("AfterSimulationRunCode", "")
        for fragment in (
            "v1 implements pooled FCFS only",
            "claim-boundary fields were weakened",
            "arrival_guard must exceed expected arrivals",
            "COUNTER_HELD_RISK_REFERRAL_PROXY",
            "five exposed exploratory inputs",
            "OP_INTERACTIVE_AD_HOC_V1",
            "INTERACTIVE_EXPLORATORY",
            "INTERACTIVE_D%03d_SEC%03d_IMM%03d_U%03d_M%03d",
            "demand_multiplier must be between 0.5 and 2.0",
            "interactive capacities must be integers between 1 and 200",
            "automation_uptake must be between 0 and 1",
        ):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, before)
        self.assertNotIn(
            "OperationalInteractive is locked to the canonical reference row",
            before,
        )
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
            {
                "demand_multiplier",
                "security_capacity",
                "immigration_capacity",
                "automation_uptake",
                "automation_multiplier",
            },
        )
        self.assertNotIn("queue_policy", exposed)
        presentation_text = " ".join(
            text.findtext("Text", "")
            for text in experiment.findall("Presentation/Text")
        )
        self.assertIn("ad-hoc exploratory", presentation_text)
        self.assertIn("Pooled FCFS is the only implemented", presentation_text)

    def test_operational_presentation_has_clear_zones_and_live_state(
        self,
    ) -> None:
        model = ET.parse(OP_MODEL_AOC).getroot()
        rectangles = {
            item.findtext("Name", ""): item
            for item in model.findall("Presentation/Rectangle")
        }
        self.assertTrue(
            {
                "arrival_zone",
                "security_zone",
                "immigration_zone",
                "exit_zone",
                "live_kpi_panel",
            }.issubset(rectangles),
        )
        token_names = {
            name
            for name in rectangles
            if re.fullmatch(
                r"(security|immigration)_(queue|service)_token_\d{2}",
                name,
            )
        }
        self.assertEqual(len(token_names), 100)
        for name in token_names:
            token = rectangles[name]
            self.assertIn(
                "presentation_animation_enabled",
                token.findtext("VisibleCode", ""),
            )
            self.assertEqual(token.findtext("Width"), "10")
            self.assertEqual(token.findtext("Height"), "10")
        labels = {
            item.findtext("Name", ""): item.findtext("Text", "")
            for item in model.findall("Presentation/Text")
        }
        for name in (
            "view_title",
            "view_subtitle",
            "arrival_zone_title",
            "security_zone_title",
            "immigration_zone_title",
            "exit_zone_title",
            "live_kpi_title",
            "control_note",
            "input_note",
            "animation_scope_note",
        ):
            with self.subTest(label=name):
                self.assertIn(name, labels)
        self.assertIn("pooled FCFS only", labels["view_subtitle"])
        self.assertIn("Queue policy is not exposed", labels["input_note"])
        self.assertNotIn("\\n", labels["control_note"])
        self.assertIn("state tokens", labels["animation_scope_note"])

        variables_root = ET.parse(OP_MODEL_VARIABLES).getroot()
        visible = {
            item.findtext("Name", "")
            for item in variables_root.findall("Variable")
            if (
                item.attrib.get("Class") == "PlainVariable"
                and item.findtext("PresentationFlag") == "true"
            )
        }
        self.assertTrue(
            {
                "admitted",
                "completed",
                "security_queue_count",
                "security_in_service_count",
                "immigration_queue_count",
                "immigration_in_service_count",
                "technology_count",
                "additional_check_count",
                "run_status",
            }.issubset(visible)
        )
        self.assertNotIn("security_queue_at_cutoff", visible)
        self.assertNotIn("immigration_queue_at_cutoff", visible)
        cutoff_event = ET.parse(OP_EVENTS).getroot().find("Event")
        self.assertIsNotNone(cutoff_event)
        assert cutoff_event is not None
        self.assertEqual(cutoff_event.findtext("PresentationFlag"), "false")

    def test_presentation_animation_is_state_driven_and_interactive_only(
        self,
    ) -> None:
        traveller = ET.parse(OP_TRAVELLER_AOC).getroot()
        markers = [
            item
            for item in traveller.findall("Presentation/Rectangle")
            if item.findtext("Name") == "traveller_marker"
        ]
        self.assertEqual(len(markers), 1)
        marker = markers[0]
        self.assertEqual(marker.findtext("X"), "-5")
        self.assertEqual(marker.findtext("Y"), "-5")
        self.assertEqual(marker.findtext("Width"), "10")
        self.assertEqual(marker.findtext("Height"), "10")
        self.assertEqual(marker.findtext("PublicFlag"), "true")
        self.assertEqual(marker.findtext("DrawMode"), "SHAPE_DRAW_2D3D")

        variables_root = ET.parse(OP_MODEL_VARIABLES).getroot()
        animation_variables = [
            item
            for item in variables_root.findall("Variable")
            if item.findtext("Name") == "presentation_animation_enabled"
        ]
        self.assertEqual(len(animation_variables), 1)
        animation_variable = animation_variables[0]
        self.assertEqual(animation_variable.attrib.get("Class"), "PlainVariable")
        self.assertEqual(
            animation_variable.findtext("Properties/InitialValue/Code"),
            "false",
        )
        self.assertEqual(
            animation_variable.findtext("PresentationFlag"),
            "false",
        )

        model = ET.parse(OP_MODEL_AOC).getroot()
        self.assertIsNotNone(model.find("AdditionalClassCode"))
        self.assertEqual(model.findtext("AdditionalClassCode", ""), "")
        self.assertTrue(OP_MODEL_ADDITIONAL_CLASS.is_file())
        self.assertTrue(OP_MODEL_ADDITIONAL_CLASS_CODE.is_file())
        animation_code = OP_MODEL_ADDITIONAL_CLASS_CODE.read_text(
            encoding="utf-8"
        )
        self.assertEqual(
            OP_MODEL_ADDITIONAL_CLASS.read_text(encoding="utf-8"),
            animation_code,
        )
        for fragment in (
            "PRESENTATION_ONLY_BEGIN",
            "refreshPresentationAnimation",
            "securityService.queueGet",
            "securityService.delayGet",
            "immigrationService.queueGet",
            "immigrationService.delayGet",
            "jumpTo",
        ):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, animation_code)
        self.assertNotRegex(
            animation_code,
            r"\b(random|uniform|normal|exponential|moveTo|delay)\s*\(",
        )

        blocks = _embedded()
        self.assertIn("operationalTravellers", blocks)
        population = blocks["operationalTravellers"]
        self.assertEqual(
            population.findtext("ActiveObjectClass/ClassName"),
            "OperationalTraveller",
        )
        self.assertEqual(population.findtext("InitializationType"), "EMPTY")
        self.assertEqual(population.findtext("InEnvironment"), "true")
        presentation_id = population.findtext("PresentationId")
        self.assertTrue(presentation_id)
        mounted_presentations = [
            item
            for item in model.findall(
                "Presentation/EmbeddedObjectPresentation"
            )
            if item.findtext("Id") == presentation_id
        ]
        self.assertEqual(len(mounted_presentations), 1)
        self.assertEqual(
            mounted_presentations[0].findtext("DrawingMode"),
            "AGENT_CURRENT_POSITION",
        )
        source_parameters = _parameters(blocks["travellerSource"])
        self.assertEqual(
            source_parameters["addToCustomPopulation"][0],
            "true",
        )
        self.assertEqual(
            source_parameters["population"][0],
            "operationalTravellers",
        )

        experiments = ET.parse(EXPERIMENTS).getroot()
        interactive_before = _operational_experiment().findtext(
            "BeforeSimulationRunCode", ""
        )
        self.assertIn(
            "root.presentation_animation_enabled = true;",
            interactive_before,
        )
        for experiment_name in (
            "OperationalPilot",
            "CapacityRobustnessConfirmatory",
            "CapacityAvailabilityStress",
            "CapacityResponseSurfaceExploratory",
            "ServiceVariabilitySensitivity",
            "PeakDurationSensitivity",
        ):
            experiment = next(
                item
                for item in experiments.findall("ParamVariationExperiment")
                if item.findtext("Name") == experiment_name
            )
            before = experiment.findtext("BeforeSimulationRunCode", "")
            self.assertIn(
                "root.presentation_animation_enabled = false;",
                before,
            )
            self.assertNotIn(
                "root.presentation_animation_enabled = true;",
                before,
            )

        for block_name in (
            "travellerSource",
            "securityService",
            "immigrationService",
            "checkpointSink",
        ):
            action_code = " ".join(
                code
                for code, _ in _parameters(blocks[block_name]).values()
            )
            with self.subTest(block=block_name):
                self.assertIn(
                    "presentation_animation_enabled",
                    action_code,
                )
                self.assertIn("jumpTo", action_code)

        after = _operational_experiment().findtext(
            "AfterSimulationRunCode", ""
        )
        self.assertNotIn("presentation_animation", after)

    def test_split_and_single_file_share_the_animation_contract(self) -> None:
        single_root = ET.parse(SINGLE_ALP).getroot()
        single_classes = {
            item.findtext("Name", ""): item
            for item in single_root.findall(".//ActiveObjectClass")
        }
        self.assertIn("OperationalTraveller", single_classes)
        self.assertIn("OperationalCheckpointModel", single_classes)

        split_traveller = ET.parse(OP_TRAVELLER_AOC).getroot()
        split_marker = next(
            item
            for item in split_traveller.findall("Presentation/Rectangle")
            if item.findtext("Name") == "traveller_marker"
        )
        single_marker = next(
            item
            for item in single_classes["OperationalTraveller"].findall(
                "Presentation/Rectangle"
            )
            if item.findtext("Name") == "traveller_marker"
        )
        for field in (
            "Id",
            "X",
            "Y",
            "Width",
            "Height",
            "FillColor",
            "PublicFlag",
        ):
            with self.subTest(field=field):
                self.assertEqual(
                    single_marker.findtext(field),
                    split_marker.findtext(field),
                )

        split_code = OP_MODEL_ADDITIONAL_CLASS_CODE.read_text(
            encoding="utf-8"
        )
        single_code = single_classes["OperationalCheckpointModel"].findtext(
            "AdditionalClassCode", ""
        )
        normalize_java = lambda code: "\n".join(
            line.strip() for line in code.strip().splitlines()
        )
        self.assertEqual(
            normalize_java(single_code),
            normalize_java(split_code),
        )
        split_event = ET.parse(OP_EVENTS).getroot().find("Event")
        self.assertIsNotNone(split_event)
        assert split_event is not None
        single_event = next(
            item
            for item in single_classes[
                "OperationalCheckpointModel"
            ].findall("Events/Event")
            if item.findtext("Name") == "arrivalCutoff"
        )
        self.assertEqual(
            normalize_java(single_event.findtext("Action", "")),
            normalize_java(_event_action(split_event.findtext("Id", ""))),
        )

        split_before = _operational_experiment().findtext(
            "BeforeSimulationRunCode", ""
        )
        single_interactive = next(
            item
            for item in single_root.findall(".//SimulationExperiment")
            if item.findtext("Name") == "OperationalInteractive"
        )
        self.assertEqual(
            normalize_java(
                single_interactive.findtext("BeforeSimulationRunCode", "")
            ),
            normalize_java(split_before),
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
        self.assertEqual(len(parameter_ids), 44)
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
                elif name in {
                    "model_version",
                    "start_state",
                    "security_service_cv",
                    "immigration_service_cv",
                }:
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

    def test_confirmatory_experiment_is_exact_serial_12_by_50_batch(
        self,
    ) -> None:
        experiment = _confirmatory_experiment()
        rows = build_confirmatory_scenario_rows()
        seed_rows = load_confirmatory_seed_rows()
        self.assertEqual(
            experiment.attrib["ActiveObjectClassId"],
            ET.parse(OP_MODEL_AOC).getroot().findtext("Id"),
        )
        self.assertEqual(experiment.findtext("Id"), "1785162900001")
        self.assertEqual(
            experiment.findtext("AllowParallelEvaluations"),
            "false",
        )
        self.assertEqual(experiment.findtext("UseFreeformParameters"), "true")
        self.assertEqual(experiment.findtext("NumberOfRuns"), "12")
        self.assertEqual(
            experiment.findtext("ModelTimeProperties/StopOption"),
            "Never",
        )
        replications = experiment.find("ReplicationsProperties")
        self.assertIsNotNone(replications)
        assert replications is not None
        self.assertEqual(replications.findtext("UseReplication"), "true")
        self.assertEqual(
            replications.findtext("FixedReplicationsNumber"),
            "true",
        )
        for field in (
            "ReplicationPerIteration",
            "MinimumReplication",
            "MaximumReplication",
        ):
            self.assertEqual(replications.findtext(field), "50")

        parameter_root = ET.parse(OP_MODEL_VARIABLES).getroot()
        parameter_ids = {
            item.findtext("Name", "").strip(): item.findtext("Id", "").strip()
            for item in parameter_root.findall("Variable")
            if item.attrib.get("Class") == "Parameter"
        }
        freeform = {
            item.findtext("Id", "").strip(): item.findtext(
                "Expression/Code", ""
            ).strip()
            for item in experiment.findall("FreeformParamValue")
        }
        fixed = {
            item.findtext("Id", "").strip()
            for item in experiment.findall("RangeVariationParamValue")
            if item.findtext("Type") == "FIXED"
        }
        self.assertEqual(set(freeform), set(parameter_ids.values()))
        self.assertEqual(fixed, set(parameter_ids.values()))
        for name in (
            "scenario_id",
            "input_sample_id",
            "config_id",
            "config_sha256",
            "arrival_rate_per_second",
            "security_capacity",
            "immigration_capacity",
        ):
            values = _indexed_values(
                freeform[parameter_ids[name]],
                len(rows),
            )
            if name == "config_sha256":
                expected = [
                    json.dumps(scenario_config_sha256(row)) for row in rows
                ]
            else:
                parameter_type = next(
                    item.findtext("Properties/Type", "").strip()
                    for item in parameter_root.findall("Variable")
                    if item.findtext("Name", "").strip() == name
                )
                expected = [
                    _java_test_literal(parameter_type, row[name])
                    for row in rows
                ]
            with self.subTest(confirmatory_parameter=name):
                self.assertEqual(values, expected)

        self.assertEqual(
            freeform[parameter_ids["output_collection_id"]],
            '"confirmatory_capacity"',
        )
        self.assertEqual(
            freeform[parameter_ids["crn_alignment_status"]],
            '"PENDING_VALIDATION"',
        )
        first_seed_by_sample = {
            row["input_sample_id"]: row
            for row in seed_rows
            if row["replication_id"] == "1"
        }
        for name in (
            "arrival_seed",
            "service_seed",
            "routing_seed",
            "tie_seed",
        ):
            actual = _indexed_values(
                freeform[parameter_ids[name]],
                len(rows),
            )
            expected = [
                f"{first_seed_by_sample[row['input_sample_id']][name]}L"
                for row in rows
            ]
            with self.subTest(confirmatory_seed_parameter=name):
                self.assertEqual(actual, expected)

        before = experiment.findtext("BeforeSimulationRunCode", "")
        self.assertIn(
            "CapacityRobustnessConfirmatory received an unknown "
            "scenario/input cell",
            before,
        )
        self.assertIn(
            "CapacityRobustnessConfirmatory replication must be 1..50",
            before,
        )
        self.assertEqual(before.count("seedGroupMatched = true;"), 150)
        for seed_row in seed_rows:
            with self.subTest(
                seed_group=seed_row["pairing_group_id"],
            ):
                self.assertIn(
                    f"root.arrival_seed = {seed_row['arrival_seed']}L;",
                    before,
                )
                self.assertIn(
                    f"root.tie_seed = {seed_row['tie_seed']}L;",
                    before,
                )

        timers = [
            item
            for item in experiment.findall("Variables/Variable")
            if item.findtext("Name") == "confirmatory_auto_start_timer"
        ]
        self.assertEqual(len(timers), 1)
        timer = timers[0]
        self.assertEqual(timer.findtext("PresentationFlag"), "false")
        self.assertEqual(timer.findtext("ShowLabel"), "false")
        self.assertEqual(
            timer.findtext("Properties/Type"),
            "javax.swing.Timer",
        )
        timer_code = timer.findtext("Properties/InitialValue/Code", "")
        self.assertEqual(
            timer_code.count("CapacityRobustnessConfirmatory.this.run();"),
            1,
        )
        self.assertEqual(timer_code.count("setRepeats(false);"), 1)

    def test_availability_experiment_is_exact_serial_12_by_50_batch(
        self,
    ) -> None:
        experiment = _availability_experiment()
        rows = load_capacity_availability_scenario_rows()
        seed_rows = load_capacity_availability_seed_rows()
        self.assertEqual(
            experiment.attrib["ActiveObjectClassId"],
            ET.parse(OP_MODEL_AOC).getroot().findtext("Id"),
        )
        self.assertEqual(experiment.findtext("Id"), "1785162950001")
        self.assertEqual(
            experiment.findtext("AllowParallelEvaluations"),
            "false",
        )
        self.assertEqual(experiment.findtext("UseFreeformParameters"), "true")
        self.assertEqual(experiment.findtext("NumberOfRuns"), "12")
        replications = experiment.find("ReplicationsProperties")
        self.assertIsNotNone(replications)
        assert replications is not None
        for field in (
            "ReplicationPerIteration",
            "MinimumReplication",
            "MaximumReplication",
        ):
            self.assertEqual(replications.findtext(field), "50")

        parameter_root = ET.parse(OP_MODEL_VARIABLES).getroot()
        parameter_ids = {
            item.findtext("Name", "").strip(): item.findtext("Id", "").strip()
            for item in parameter_root.findall("Variable")
            if item.attrib.get("Class") == "Parameter"
        }
        freeform = {
            item.findtext("Id", "").strip(): item.findtext(
                "Expression/Code", ""
            ).strip()
            for item in experiment.findall("FreeformParamValue")
        }
        self.assertEqual(
            freeform[parameter_ids["output_collection_id"]],
            '"capacity_availability"',
        )
        for name in (
            "scenario_id",
            "input_sample_id",
            "config_id",
            "config_sha256",
            "arrival_rate_per_second",
            "security_capacity",
            "immigration_capacity",
        ):
            values = _indexed_values(
                freeform[parameter_ids[name]],
                len(rows),
            )
            if name == "config_sha256":
                expected = [
                    json.dumps(scenario_config_sha256(row)) for row in rows
                ]
            else:
                parameter_type = next(
                    item.findtext("Properties/Type", "").strip()
                    for item in parameter_root.findall("Variable")
                    if item.findtext("Name", "").strip() == name
                )
                expected = [
                    _java_test_literal(parameter_type, row[name])
                    for row in rows
                ]
            with self.subTest(availability_parameter=name):
                self.assertEqual(values, expected)

        first_seed_by_sample = {
            row["input_sample_id"]: row
            for row in seed_rows
            if row["replication_id"] == "1"
        }
        for name in (
            "arrival_seed",
            "service_seed",
            "routing_seed",
            "tie_seed",
        ):
            actual = _indexed_values(
                freeform[parameter_ids[name]],
                len(rows),
            )
            expected = [
                f"{first_seed_by_sample[row['input_sample_id']][name]}L"
                for row in rows
            ]
            with self.subTest(availability_seed_parameter=name):
                self.assertEqual(actual, expected)

        before = experiment.findtext("BeforeSimulationRunCode", "")
        self.assertIn(
            "CapacityAvailabilityStress received an unknown "
            "scenario/input cell",
            before,
        )
        self.assertEqual(before.count("seedGroupMatched = true;"), 150)
        timers = [
            item
            for item in experiment.findall("Variables/Variable")
            if item.findtext("Name") == "availability_auto_start_timer"
        ]
        self.assertEqual(len(timers), 1)
        timer_code = timers[0].findtext(
            "Properties/InitialValue/Code",
            "",
        )
        self.assertEqual(
            timer_code.count("CapacityAvailabilityStress.this.run();"),
            1,
        )
        self.assertEqual(timer_code.count("setRepeats(false);"), 1)

    def test_response_surface_is_exact_serial_54_by_50_batch(self) -> None:
        experiment = _response_surface_experiment()
        rows = load_response_surface_scenario_rows()
        seed_rows = load_response_surface_seed_rows()
        self.assertEqual(len(rows), 54)
        self.assertEqual(len(seed_rows), 50)
        self.assertEqual(
            experiment.attrib["ActiveObjectClassId"],
            ET.parse(OP_MODEL_AOC).getroot().findtext("Id"),
        )
        self.assertEqual(experiment.findtext("Id"), "1785162960001")
        self.assertEqual(
            experiment.findtext("AllowParallelEvaluations"),
            "false",
        )
        self.assertEqual(experiment.findtext("UseFreeformParameters"), "true")
        self.assertEqual(experiment.findtext("NumberOfRuns"), "54")
        self.assertEqual(
            experiment.findtext("ModelTimeProperties/StopOption"),
            "Never",
        )

        replications = experiment.find("ReplicationsProperties")
        self.assertIsNotNone(replications)
        assert replications is not None
        self.assertEqual(replications.findtext("UseReplication"), "true")
        self.assertEqual(
            replications.findtext("FixedReplicationsNumber"),
            "true",
        )
        for field in (
            "ReplicationPerIteration",
            "MinimumReplication",
            "MaximumReplication",
        ):
            self.assertEqual(replications.findtext(field), "50")
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
        freeform = {
            item.findtext("Id", "").strip(): item.findtext(
                "Expression/Code", ""
            ).strip()
            for item in experiment.findall("FreeformParamValue")
        }
        fixed = {
            item.findtext("Id", "").strip()
            for item in experiment.findall("RangeVariationParamValue")
            if item.findtext("Type") == "FIXED"
        }
        self.assertEqual(set(freeform), set(parameter_ids.values()))
        self.assertEqual(fixed, set(parameter_ids.values()))
        self.assertEqual(
            freeform[parameter_ids["output_collection_id"]],
            '"capacity_response_surface"',
        )
        self.assertEqual(
            freeform[parameter_ids["crn_alignment_status"]],
            '"PENDING_VALIDATION"',
        )

        for name in (
            "scenario_id",
            "input_sample_id",
            "config_id",
            "config_sha256",
            "arrival_rate_per_second",
            "security_capacity",
            "immigration_capacity",
        ):
            actual = _indexed_values(
                freeform[parameter_ids[name]],
                len(rows),
            )
            if name == "config_sha256":
                expected = [
                    json.dumps(scenario_config_sha256(row)) for row in rows
                ]
            else:
                expected = [
                    _java_test_literal(parameter_types[name], row[name])
                    for row in rows
                ]
            with self.subTest(response_surface_parameter=name):
                self.assertEqual(actual, expected)

        first_seed = next(
            row for row in seed_rows if row["replication_id"] == "1"
        )
        for name in (
            "arrival_seed",
            "service_seed",
            "routing_seed",
            "tie_seed",
        ):
            actual = _indexed_values(
                freeform[parameter_ids[name]],
                len(rows),
            )
            expected = [f"{first_seed[name]}L"] * len(rows)
            with self.subTest(response_surface_seed_parameter=name):
                self.assertEqual(actual, expected)

        before = experiment.findtext("BeforeSimulationRunCode", "")
        self.assertIn(
            "CapacityResponseSurfaceExploratory received an unknown "
            "scenario/input cell",
            before,
        )
        self.assertIn(
            "CapacityResponseSurfaceExploratory replication must be 1..50",
            before,
        )
        self.assertEqual(
            before.count('expectedConfigId = "OP_RESPONSE_'),
            54,
        )
        self.assertEqual(before.count("seedGroupMatched = true;"), 50)
        for seed_row in seed_rows:
            with self.subTest(
                response_surface_seed_group=seed_row["pairing_group_id"],
            ):
                self.assertIn(
                    f"root.arrival_seed = {seed_row['arrival_seed']}L;",
                    before,
                )
                self.assertIn(
                    f"root.tie_seed = {seed_row['tie_seed']}L;",
                    before,
                )

        after = experiment.findtext("AfterSimulationRunCode", "")
        self.assertIn("root.output_collection_id", after)
        timers = [
            item
            for item in experiment.findall("Variables/Variable")
            if item.findtext("Name") == "response_surface_auto_start_timer"
        ]
        self.assertEqual(len(timers), 1)
        timer = timers[0]
        self.assertEqual(timer.findtext("Id"), "1785162960002")
        self.assertEqual(timer.findtext("PresentationFlag"), "false")
        self.assertEqual(timer.findtext("ShowLabel"), "false")
        self.assertEqual(
            timer.findtext("Properties/Type"),
            "javax.swing.Timer",
        )
        timer_code = timer.findtext(
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

    def test_registered_v1_batches_remain_fixed_service_with_zero_cv(
        self,
    ) -> None:
        parameter_ids, _, _ = _operational_parameter_metadata()
        self.assertEqual(len(parameter_ids), 44)
        for experiment_name in (
            "OperationalPilot",
            "CapacityRobustnessConfirmatory",
            "CapacityAvailabilityStress",
            "CapacityResponseSurfaceExploratory",
            "PeakDurationSensitivity",
        ):
            experiment = _named_parameter_variation_experiment(
                experiment_name
            )
            freeform, fixed = _experiment_parameter_values(experiment)
            self.assertEqual(set(freeform), set(parameter_ids.values()))
            self.assertEqual(fixed, set(parameter_ids.values()))
            for parameter_name, expected in (
                ("model_version", '"TASK3_OPERATIONAL_POOLED_V1"'),
                ("security_service_distribution", '"FIXED"'),
                ("immigration_service_distribution", '"FIXED"'),
                ("security_service_cv", "0.0"),
                ("immigration_service_cv", "0.0"),
            ):
                values = _indexed_values(
                    freeform[parameter_ids[parameter_name]],
                    int(experiment.findtext("NumberOfRuns", "0")),
                )
                with self.subTest(
                    experiment=experiment_name,
                    parameter=parameter_name,
                ):
                    self.assertEqual(values, [expected] * len(values))

            before = experiment.findtext("BeforeSimulationRunCode", "")
            self.assertIn(
                '"TASK3_OPERATIONAL_POOLED_V1".equals( root.model_version )',
                before,
            )
            self.assertIn(
                "TASK3_OPERATIONAL_POOLED_V1 is frozen to FIXED "
                "service and CV=0",
                before,
            )

    def test_service_variability_is_exact_serial_9_by_50_batch(
        self,
    ) -> None:
        experiment = _named_parameter_variation_experiment(
            "ServiceVariabilitySensitivity"
        )
        rows = load_service_variability_scenario_rows()
        seed_rows = load_service_variability_seed_rows()
        self.assertEqual(len(rows), 9)
        self.assertEqual(len(seed_rows), 50)
        self.assertEqual(
            {
                (row["security_service_cv"], row["immigration_service_cv"])
                for row in rows
            },
            {
                (security_cv, immigration_cv)
                for security_cv in ("0", "0.5", "1")
                for immigration_cv in ("0", "0.5", "1")
            },
        )
        _assert_exact_serial_batch(
            self,
            experiment=experiment,
            experiment_id="1785162970001",
            number_of_cells=9,
            replications_per_cell=50,
            timer_name="service_variability_auto_start_timer",
            timer_id="1785162970002",
        )
        _assert_full_parameter_mapping(
            self,
            experiment=experiment,
            rows=rows,
            seed_rows=seed_rows,
            output_collection_id="service_variability",
            config_hash=service_scenario_config_sha256,
            model_version=SERVICE_VARIABILITY_MODEL_VERSION,
        )

        before = experiment.findtext("BeforeSimulationRunCode", "")
        for fragment in (
            f'"{SERVICE_VARIABILITY_MODEL_VERSION}".equals'
            "( root.model_version )",
            '"service_variability".equals( root.output_collection_id )',
            "ServiceVariabilitySensitivity received an unknown "
            "scenario/input cell",
            "ServiceVariabilitySensitivity replication must be 1..50",
            "root.security_service_rng = null;",
            "root.immigration_service_rng = null;",
            "getEngine().getDefaultRandomGenerator().setSeed"
            "( root.arrival_seed );",
        ):
            with self.subTest(before_fragment=fragment):
                self.assertIn(fragment, before)
        self.assertEqual(
            before.count('expectedConfigId = "OP_SERVICE_VARIABILITY_'),
            9,
        )
        self.assertEqual(before.count("seedGroupMatched = true;"), 50)
        for row in rows:
            with self.subTest(service_cell=row["scenario_id"]):
                self.assertIn(f'"{row["scenario_id"]}"', before)
                self.assertIn(
                    f'"{service_scenario_config_sha256(row)}"',
                    before,
                )
        for seed_row in seed_rows:
            with self.subTest(service_seed=seed_row["replication_id"]):
                for seed_name in (
                    "arrival_seed",
                    "service_seed",
                    "routing_seed",
                    "tie_seed",
                ):
                    self.assertIn(
                        f"root.{seed_name} = "
                        f"{seed_row[seed_name]}L;",
                        before,
                    )

    def test_peak_duration_is_exact_serial_20_by_50_batch(self) -> None:
        experiment = _named_parameter_variation_experiment(
            "PeakDurationSensitivity"
        )
        rows = load_peak_duration_scenario_rows()
        seed_rows = load_peak_duration_seed_rows()
        self.assertEqual(len(rows), 20)
        self.assertEqual(len(seed_rows), 50)
        self.assertEqual(
            {
                (
                    int(row["security_capacity"]),
                    int(row["immigration_capacity"]),
                )
                for row in rows
            },
            {(36, 21), (30, 18), (29, 17), (28, 16)},
        )
        self.assertEqual(
            {int(row["arrival_cutoff_seconds"]) for row in rows},
            {300, 900, 1800, 3600, 7200},
        )
        self.assertEqual(
            {
                int(row["arrival_cutoff_seconds"]): int(
                    row["arrival_guard"]
                )
                for row in rows
            },
            {
                300: 5000,
                900: 5000,
                1800: 5000,
                3600: 5712,
                7200: 10914,
            },
        )
        _assert_exact_serial_batch(
            self,
            experiment=experiment,
            experiment_id="1785162980001",
            number_of_cells=20,
            replications_per_cell=50,
            timer_name="peak_duration_auto_start_timer",
            timer_id="1785162980002",
        )
        _assert_full_parameter_mapping(
            self,
            experiment=experiment,
            rows=rows,
            seed_rows=seed_rows,
            output_collection_id="peak_duration_sensitivity",
            config_hash=scenario_config_sha256,
        )

        parameter_ids, _, _ = _operational_parameter_metadata()
        freeform, _ = _experiment_parameter_values(experiment)
        self.assertEqual(
            _indexed_values(
                freeform[parameter_ids["input_sample_id"]],
                len(rows),
            ),
            ['"LOCAL_WINDOW_HPP_BASE_STATIONARY_EXTENSION"']
            * len(rows),
        )
        before = experiment.findtext("BeforeSimulationRunCode", "")
        for fragment in (
            '"peak_duration_sensitivity".equals'
            "( root.output_collection_id )",
            "PeakDurationSensitivity received an unknown "
            "scenario/input cell",
            "PeakDurationSensitivity replication must be 1..50",
            "getEngine().getDefaultRandomGenerator().setSeed"
            "( root.arrival_seed );",
        ):
            with self.subTest(before_fragment=fragment):
                self.assertIn(fragment, before)
        self.assertEqual(
            before.count('expectedConfigId = "OP_PEAK_DURATION_BASE_'),
            20,
        )
        self.assertEqual(before.count("seedGroupMatched = true;"), 50)
        self.assertNotIn("CapacityRobustnessConfirmatory", before)
        for row in rows:
            with self.subTest(duration_cell=row["scenario_id"]):
                self.assertIn(f'"{row["scenario_id"]}"', before)
                self.assertIn(
                    f'"{scenario_config_sha256(row)}"',
                    before,
                )
        for seed_row in seed_rows:
            with self.subTest(duration_seed=seed_row["replication_id"]):
                for seed_name in (
                    "arrival_seed",
                    "service_seed",
                    "routing_seed",
                    "tie_seed",
                ):
                    self.assertIn(
                        f"root.{seed_name} = "
                        f"{seed_row[seed_name]}L;",
                        before,
                    )

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
        block_positions = {
            name: (
                int(item.findtext("X", "0")),
                int(item.findtext("Y", "0")),
            )
            for name, item in _embedded().items()
        }
        self.assertEqual(block_positions["travellerSource"], (90, 280))
        self.assertEqual(block_positions["securityService"], (300, 270))
        self.assertEqual(block_positions["securityResources"], (310, 390))
        self.assertEqual(block_positions["immigrationService"], (580, 270))
        self.assertEqual(block_positions["immigrationResources"], (590, 390))
        self.assertEqual(block_positions["checkpointSink"], (850, 280))
        connector_points = [
            [
                (
                    int(point.findtext("X", "0")),
                    int(point.findtext("Y", "0")),
                )
                for point in connector.findall("Points/Point")
            ]
            for connector in connectors
        ]
        self.assertEqual(
            connector_points,
            [
                [(120, 290), (300, 290)],
                [(360, 290), (580, 290)],
                [(640, 290), (850, 290)],
            ],
        )


if __name__ == "__main__":
    unittest.main()
