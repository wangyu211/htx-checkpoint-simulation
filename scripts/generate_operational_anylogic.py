"""Generate the split AnyLogic fragments for the Task 3 operational model.

The empty OperationalTraveller, OperationalCheckpointModel, and
OperationalInteractive objects must first be created in the AnyLogic GUI.  The
GUI owns their class/experiment IDs.  This script fills only those new objects
and leaves the verified gate, HPP, and deterministic-oracle objects untouched.
"""

from __future__ import annotations

import csv
import html
import json
import re
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.analysis.validate_operational_contract import (  # noqa: E402
    SCENARIO_COLUMNS,
    scenario_config_sha256,
    validate_operational_contract,
)
from src.analysis.confirmatory_design import (  # noqa: E402
    DEFAULT_DESIGN as CONFIRMATORY_DESIGN,
    DEFAULT_SEED_MANIFEST as CONFIRMATORY_SEED_MANIFEST,
    build_confirmatory_scenario_rows,
    load_confirmatory_seed_rows,
    validate_confirmatory_design,
)

ALP = REPO / "simulation" / "anylogic" / "HTXCheckpointSimulation" / "_alp"
AGENTS = ALP / "Agents"
CHECKPOINT = AGENTS / "CheckpointModel"
OP_MODEL = AGENTS / "OperationalCheckpointModel"
OP_TRAVELLER = AGENTS / "OperationalTraveller"
EXPERIMENTS = ALP / "Experiments.xml"
SCENARIOS = REPO / "config" / "operational_scenarios.csv"
SINGLE_ALP = (
    REPO
    / "simulation"
    / "anylogic"
    / "HTXCheckpointSimulationCLI"
    / "HTXCheckpointSimulationCLI.alp"
)

PILOT_EXPERIMENT_NAME = "OperationalPilot"
PILOT_OUTPUT_COLLECTION = "anylogic_operational_batch"
INTERACTIVE_OUTPUT_COLLECTION = "anylogic_operational"
CONFIRMATORY_EXPERIMENT_NAME = "CapacityRobustnessConfirmatory"
CONFIRMATORY_OUTPUT_COLLECTION = "confirmatory_capacity"
CONFIRMATORY_EXPERIMENT_ID = "1785162900001"
CONFIRMATORY_TIMER_ID = "1785162900002"
INTERACTIVE_PARAMETER_NAMES = (
    "demand_multiplier",
    "security_capacity",
    "immigration_capacity",
    "automation_uptake",
    "automation_multiplier",
)

MODEL_BLOCK_POSITIONS = {
    "travellerSource": (90, 280, -18, -24),
    "securityService": (300, 270, -26, -24),
    "securityResources": (310, 350, -34, -24),
    "immigrationService": (580, 270, -34, -24),
    "immigrationResources": (590, 350, -40, -24),
    "checkpointSink": (850, 280, -10, -24),
}

MODEL_VARIABLE_POSITIONS = {
    "admitted": (70, 455),
    "completed": (830, 455),
    "arrivals_closed": (70, 490),
    "rejected_or_dropped_count": (830, 490),
    "technology_count": (560, 525),
    "additional_check_count": (560, 560),
    "security_queue_count": (245, 455),
    "security_in_service_count": (245, 490),
    "immigration_queue_count": (525, 455),
    "immigration_in_service_count": (525, 490),
    "max_security_queue": (245, 525),
    "max_immigration_queue": (700, 560),
    "run_status": (830, 525),
}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.replace("\r\n", "\n"), encoding="utf-8")


def _class_id(path: Path) -> str:
    match = re.search(r"<ActiveObjectClass>\s*<Id>(\d+)</Id>", _read(path))
    if not match:
        raise RuntimeError(f"Cannot read class ID from {path}")
    return match.group(1)


def _generic_parameter_id(path: Path) -> str:
    match = re.search(
        r"<GenericParameter>\s*<Id>(\d+)</Id>",
        _read(path),
    )
    if not match:
        raise RuntimeError(f"Cannot read generic parameter ID from {path}")
    return match.group(1)


def _load_scenarios() -> tuple[list[str], list[dict[str, str]]]:
    validation = validate_operational_contract()
    if validation["status"] != "PASS":
        raise RuntimeError(
            "Operational scenario contract failed: "
            + "; ".join(str(error) for error in validation["errors"])
        )
    with SCENARIOS.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        fieldnames = list(reader.fieldnames or ())
        rows = [
            {
                key: (value or "").strip()
                for key, value in row.items()
            }
            for row in reader
        ]
    if fieldnames != list(SCENARIO_COLUMNS):
        raise RuntimeError("Operational scenario CSV header is not canonical")
    if len(rows) != 15:
        raise RuntimeError(
            f"OperationalPilot requires exactly 15 scenarios, found {len(rows)}"
        )
    if any(row.get("pilot_replications") != "10" for row in rows):
        raise RuntimeError(
            "OperationalPilot requires exactly 10 replications per scenario"
        )
    scenario_ids = [row.get("scenario_id", "") for row in rows]
    if len(scenario_ids) != len(set(scenario_ids)):
        raise RuntimeError("Operational scenario IDs must be unique")
    return fieldnames, rows


def _load_confirmatory_inputs() -> tuple[
    list[dict[str, str]], list[dict[str, str]], dict[str, object]
]:
    validation = validate_confirmatory_design(
        CONFIRMATORY_DESIGN,
        CONFIRMATORY_SEED_MANIFEST,
    )
    if validation["status"] != "PASS":
        raise RuntimeError(
            "Confirmatory design failed: "
            + "; ".join(str(error) for error in validation["errors"])
        )
    rows = build_confirmatory_scenario_rows(CONFIRMATORY_DESIGN, SCENARIOS)
    seed_rows = load_confirmatory_seed_rows(CONFIRMATORY_SEED_MANIFEST)
    if len(rows) != 12 or len(seed_rows) != 150:
        raise RuntimeError(
            "CapacityRobustnessConfirmatory requires 12 cells and 150 seed groups"
        )
    return rows, seed_rows, validation


def _ensure_split_references(
    path: Path,
    *,
    events: bool,
    embedded_objects: bool,
) -> None:
    text = _read(path)
    references: list[str] = []
    if '<Variables xmlns:al="http://anylogic.com"/>' not in text:
        references.append('\t<Variables xmlns:al="http://anylogic.com"/>')
    if events and '<Events xmlns:al="http://anylogic.com"/>' not in text:
        references.append('\t<Events xmlns:al="http://anylogic.com"/>')
    if references:
        match = re.search(r"\t<ConnectionsId>.*?</ConnectionsId>", text)
        if not match:
            raise RuntimeError(f"Cannot place split references in {path}")
        text = (
            text[: match.end()]
            + "\n"
            + "\n".join(references)
            + text[match.end() :]
        )
    if (
        embedded_objects
        and '<EmbeddedObjects xmlns:al="http://anylogic.com"/>' not in text
    ):
        marker = "\t<Presentation>"
        if marker not in text:
            raise RuntimeError(f"Cannot place EmbeddedObjects reference in {path}")
        text = text.replace(
            marker,
            '\t<EmbeddedObjects xmlns:al="http://anylogic.com"/>\n'
            + marker,
            1,
        )
    _write(path, text)


def _plain_variable(
    *,
    item_id: int,
    name: str,
    value_type: str,
    initial: str,
    x: int,
    y: int,
    visible: bool = True,
) -> str:
    flag = "true" if visible else "false"
    return f"""\
\t<Variable Class="PlainVariable">
\t\t<Id>{item_id}</Id>
\t\t<Name><![CDATA[{name}]]></Name>
\t\t<X>{x}</X>
\t\t<Y>{y}</Y>
\t\t<Label><X>10</X><Y>0</Y></Label>
\t\t<PublicFlag>false</PublicFlag>
\t\t<PresentationFlag>{flag}</PresentationFlag>
\t\t<ShowLabel>{flag}</ShowLabel>
\t\t<Properties SaveInSnapshot="true"
              Constant="false"
              AccessType="public"
              StaticVariable="false">
\t\t\t<Type><![CDATA[{value_type}]]></Type>
\t\t\t<InitialValue Class="CodeValue">
\t\t\t\t<Code><![CDATA[{initial}]]></Code>
\t\t\t</InitialValue>
\t\t</Properties>
\t</Variable>"""


def _parameter(
    *,
    item_id: int,
    name: str,
    value_type: str,
    default: str,
    x: int,
    y: int,
) -> str:
    return f"""\
\t<Variable Class="Parameter">
\t\t<Id>{item_id}</Id>
\t\t<Name><![CDATA[{name}]]></Name>
\t\t<X>{x}</X>
\t\t<Y>{y}</Y>
\t\t<Label><X>10</X><Y>0</Y></Label>
\t\t<PublicFlag>false</PublicFlag>
\t\t<PresentationFlag>false</PresentationFlag>
\t\t<ShowLabel>false</ShowLabel>
\t\t<Properties SaveInSnapshot="true" ModificatorType="STATIC">
\t\t\t<Type><![CDATA[{value_type}]]></Type>
\t\t\t<UnitType>NONE</UnitType>
\t\t\t<SdArray>false</SdArray>
\t\t\t<DefaultValue Class="CodeValue">
\t\t\t\t<Code><![CDATA[{default}]]></Code>
\t\t\t</DefaultValue>
\t\t\t<ParameterEditor>
\t\t\t\t<Id>{item_id + 1}</Id>
\t\t\t\t<EditorContolType>TEXT_BOX</EditorContolType>
\t\t\t\t<MinSliderValue>0</MinSliderValue>
\t\t\t\t<MaxSliderValue>5000</MaxSliderValue>
\t\t\t\t<DelimeterType>NO_DELIMETER</DelimeterType>
\t\t\t</ParameterEditor>
\t\t</Properties>
\t</Variable>"""


def _variables_xml(
    plain: list[tuple[str, str, str, bool]],
    parameters: list[tuple[str, str, str]],
    *,
    plain_base: int,
    parameter_base: int,
    plain_positions: dict[str, tuple[int, int]] | None = None,
) -> str:
    blocks: list[str] = ['<?xml version="1.0" encoding="UTF-8"?>', "<Variables>"]
    for index, (name, value_type, initial, visible) in enumerate(plain):
        default_position = (
            40 + 260 * ((index // 12) % 4),
            160 + 30 * (index % 12),
        )
        x, y = (plain_positions or {}).get(name, default_position)
        blocks.append(
            _plain_variable(
                item_id=plain_base + 10 * index,
                name=name,
                value_type=value_type,
                initial=initial,
                x=x,
                y=y,
                visible=visible,
            )
        )
    for index, (name, value_type, default) in enumerate(parameters):
        blocks.append(
            _parameter(
                item_id=parameter_base + 10 * index,
                name=name,
                value_type=value_type,
                default=default,
                x=40 + 260 * ((index // 12) % 4),
                y=540 + 30 * (index % 12),
            )
        )
    blocks.append("</Variables>")
    return "\n".join(blocks) + "\n"


TRAVELLER_VARIABLES = [
    ("traveller_id", "String", '""', True),
    ("input_sample_id", "String", '""', True),
    ("replication_id", "int", "0", True),
    ("arrival", "double", "Double.NaN", True),
    ("security_service_demand", "double", "Double.NaN", True),
    (
        "immigration_conventional_service_demand",
        "double",
        "Double.NaN",
        True,
    ),
    ("automation_u", "double", "Double.NaN", True),
    ("additional_check_u", "double", "Double.NaN", True),
    ("lane_tie_u", "double", "Double.NaN", True),
    ("security_queue_join", "double", "Double.NaN", True),
    ("security_start", "double", "Double.NaN", True),
    ("security_end", "double", "Double.NaN", True),
    ("immigration_queue_join", "double", "Double.NaN", True),
    ("immigration_lane_id", "String", '""', True),
    ("immigration_start", "double", "Double.NaN", True),
    ("technology_flag", "boolean", "false", True),
    (
        "immigration_primary_service_demand",
        "double",
        "Double.NaN",
        True,
    ),
    ("immigration_primary_end", "double", "Double.NaN", True),
    ("additional_check_flag", "boolean", "false", True),
    ("additional_check_service_demand", "double", "0.0", True),
    ("additional_check_end", "double", "Double.NaN", True),
    ("exit", "double", "Double.NaN", True),
    ("security_resource_id", "String", '""', True),
    ("immigration_resource_id", "String", '""', True),
]


MODEL_VARIABLES = [
    ("admitted", "int", "0", True),
    ("completed", "int", "0", True),
    ("admitted_at_cutoff", "int", "0", False),
    ("completed_at_cutoff", "int", "0", False),
    ("arrivals_closed", "boolean", "false", True),
    ("guard_hit", "boolean", "false", False),
    ("rejected_or_dropped_count", "int", "0", True),
    ("technology_count", "int", "0", True),
    ("additional_check_count", "int", "0", True),
    ("security_queue_count", "int", "0", True),
    ("security_in_service_count", "int", "0", True),
    ("immigration_queue_count", "int", "0", True),
    ("immigration_in_service_count", "int", "0", True),
    ("security_queue_at_cutoff", "int", "0", False),
    ("security_in_service_at_cutoff", "int", "0", False),
    ("immigration_queue_at_cutoff", "int", "0", False),
    ("immigration_in_service_at_cutoff", "int", "0", False),
    ("max_security_queue", "int", "0", True),
    ("max_immigration_queue", "int", "0", True),
    ("last_arrival_time", "double", "Double.NEGATIVE_INFINITY", False),
    ("last_exit", "double", "Double.NaN", False),
    ("security_busy_seconds", "double", "0.0", False),
    ("immigration_busy_seconds", "double", "0.0", False),
    ("exceed_600_count", "int", "0", False),
    ("exceed_900_count", "int", "0", False),
    ("exceed_1200_count", "int", "0", False),
    ("run_status", "String", '"RUNNING"', True),
    (
        "security_waits",
        "java.util.ArrayList<Double>",
        "new java.util.ArrayList<Double>()",
        False,
    ),
    (
        "immigration_waits",
        "java.util.ArrayList<Double>",
        "new java.util.ArrayList<Double>()",
        False,
    ),
    (
        "total_queue_waits",
        "java.util.ArrayList<Double>",
        "new java.util.ArrayList<Double>()",
        False,
    ),
    (
        "system_times",
        "java.util.ArrayList<Double>",
        "new java.util.ArrayList<Double>()",
        False,
    ),
    (
        "entity_log_rows",
        "java.util.ArrayList<String>",
        "new java.util.ArrayList<String>()",
        False,
    ),
    (
        "routing_rng",
        "java.util.Random",
        "null",
        False,
    ),
    (
        "tie_rng",
        "java.util.Random",
        "null",
        False,
    ),
]


MODEL_PARAMETERS = [
    ("schema_version", "String", '"1.0"'),
    ("model_version", "String", '"TASK3_OPERATIONAL_POOLED_V1"'),
    ("output_collection_id", "String", '"anylogic_operational"'),
    ("config_id", "String", '"OP_REFERENCE_ASSUMPTION_SANDBOX_V1"'),
    (
        "config_sha256",
        "String",
        '"166e6c918cff63041b08f31ff5c17fbea49008b8cdd3047b1082b326faae3460"',
    ),
    ("scenario_id", "String", '"REFERENCE_ASSUMPTION_SANDBOX_V1"'),
    ("scenario_family", "String", '"REFERENCE"'),
    (
        "reference_scenario_id",
        "String",
        '"REFERENCE_ASSUMPTION_SANDBOX_V1"',
    ),
    ("input_sample_id", "String", '"LOCAL_WINDOW_HPP_BASE"'),
    ("replication_id", "int", "0"),
    ("start_state", "String", '"EMPTY_AND_IDLE"'),
    ("calibration_status", "String", '"NOT_CALIBRATED"'),
    ("claim_ceiling", "String", '"COMPARATIVE_WHAT_IF_ONLY"'),
    ("crn_alignment_status", "String", '"NOT_TESTED"'),
    ("arrival_mode", "String", '"HPP"'),
    ("arrival_rate_per_second", "double", "1.364213"),
    ("demand_multiplier", "double", "1.0"),
    ("arrival_cutoff_seconds", "double", "300.0"),
    ("arrival_guard", "int", "5000"),
    ("drain_rule", "String", '"FULL_DRAIN"'),
    ("security_capacity", "int", "36"),
    ("security_queue_capacity", "int", "5000"),
    ("security_service_distribution", "String", '"FIXED"'),
    ("security_service_p1_seconds", "double", "21.818181818"),
    ("immigration_capacity", "int", "21"),
    ("immigration_queue_capacity", "int", "5000"),
    ("immigration_service_distribution", "String", '"FIXED"'),
    ("immigration_service_p1_seconds", "double", "13.0"),
    ("queue_policy", "String", '"pooled"'),
    ("automation_mapping_mode", "String", '"DISABLED"'),
    ("automation_uptake", "double", "0.0"),
    ("automation_multiplier", "double", "1.0"),
    ("additional_check_semantics", "String", '"NONE"'),
    ("additional_check_probability_conventional", "double", "0.0"),
    ("additional_check_probability_technology", "double", "0.0"),
    ("additional_check_service_distribution", "String", '"UNSET"'),
    ("additional_check_service_p1_seconds", "double", "0.0"),
    ("master_seed", "long", "2026072800L"),
    ("arrival_seed", "long", "2026072801L"),
    ("service_seed", "long", "2026072802L"),
    ("routing_seed", "long", "2026072803L"),
    ("tie_seed", "long", "2026072804L"),
]


SOURCE_ON_EXIT = """\
if ( admitted + 1 >= arrival_guard ) {
\tguard_hit = true;
\ttravellerSource.set_rate( 0.0, PER_SECOND );
\tthrow new IllegalStateException( "arrival_guard reached before cutoff: " + arrival_guard );
}
double arrivalTime = time();
if ( arrivalTime < 0.0 || arrivalTime >= arrival_cutoff_seconds ) {
\tthrow new IllegalStateException( "HPP arrival outside [0, cutoff): " + arrivalTime );
}
if ( arrivalTime <= last_arrival_time ) {
\tthrow new IllegalStateException( "arrival times are not strictly increasing" );
}
OperationalTraveller traveller = (OperationalTraveller) agent;
int sequence = ++admitted;
last_arrival_time = arrivalTime;
traveller.traveller_id = String.format(
\tjava.util.Locale.ROOT,
\t"%s_R%03d_T%05d",
\tinput_sample_id,
\treplication_id,
\tsequence
);
traveller.input_sample_id = input_sample_id;
traveller.replication_id = replication_id;
traveller.arrival = arrivalTime;
traveller.security_service_demand = security_service_p1_seconds;
traveller.immigration_conventional_service_demand = immigration_service_p1_seconds;
if ( routing_rng == null ) routing_rng = new java.util.Random( routing_seed );
if ( tie_rng == null ) tie_rng = new java.util.Random( tie_seed );
traveller.automation_u = routing_rng.nextDouble();
traveller.technology_flag =
\t"MULTIPLIER".equals( automation_mapping_mode )
\t&& traveller.automation_u < automation_uptake;
traveller.immigration_primary_service_demand =
\ttraveller.immigration_conventional_service_demand
\t* ( traveller.technology_flag ? automation_multiplier : 1.0 );
if ( traveller.technology_flag ) technology_count++;
traveller.additional_check_u = routing_rng.nextDouble();
double additionalProbability = traveller.technology_flag
\t? additional_check_probability_technology
\t: additional_check_probability_conventional;
traveller.additional_check_flag =
\t"COUNTER_HELD_RISK_REFERRAL_PROXY".equals( additional_check_semantics )
\t&& traveller.additional_check_u < additionalProbability;
traveller.additional_check_service_demand =
\ttraveller.additional_check_flag ? additional_check_service_p1_seconds : 0.0;
if ( traveller.additional_check_flag ) additional_check_count++;
traveller.lane_tie_u = tie_rng.nextDouble();"""


SECURITY_ENTER = """\
if ( security_queue_count >= security_queue_capacity ) {
\trejected_or_dropped_count++;
\tthrow new IllegalStateException( "Security queue capacity reached" );
}
OperationalTraveller traveller = (OperationalTraveller) agent;
traveller.security_queue_join = time();
security_queue_count++;
max_security_queue = Math.max( max_security_queue, security_queue_count );"""


SECURITY_DELAY_ENTER = """\
OperationalTraveller traveller = (OperationalTraveller) agent;
security_queue_count--;
security_in_service_count++;
traveller.security_start = time();"""


SECURITY_EXIT = """\
OperationalTraveller traveller = (OperationalTraveller) agent;
security_in_service_count--;
traveller.security_end = time();
security_busy_seconds += traveller.security_service_demand;"""


IMMIGRATION_ENTER = """\
if ( immigration_queue_count >= immigration_queue_capacity ) {
\trejected_or_dropped_count++;
\tthrow new IllegalStateException( "Immigration queue capacity reached" );
}
OperationalTraveller traveller = (OperationalTraveller) agent;
traveller.immigration_queue_join = time();
traveller.immigration_lane_id = "IMMIGRATION_POOLED";
immigration_queue_count++;
max_immigration_queue = Math.max( max_immigration_queue, immigration_queue_count );"""


IMMIGRATION_DELAY_ENTER = """\
OperationalTraveller traveller = (OperationalTraveller) agent;
immigration_queue_count--;
immigration_in_service_count++;
traveller.immigration_start = time();
traveller.immigration_primary_end =
\ttraveller.immigration_start + traveller.immigration_primary_service_demand;"""


IMMIGRATION_EXIT = """\
OperationalTraveller traveller = (OperationalTraveller) agent;
immigration_in_service_count--;
if ( traveller.additional_check_flag ) traveller.additional_check_end = time();
immigration_busy_seconds +=
\ttraveller.immigration_primary_service_demand
\t+ traveller.additional_check_service_demand;"""


SINK_ENTER = """\
OperationalTraveller traveller = (OperationalTraveller) agent;
traveller.exit = time();
completed++;
last_exit = traveller.exit;
double securityWait = traveller.security_start - traveller.security_queue_join;
double immigrationWait = traveller.immigration_start - traveller.immigration_queue_join;
double totalQueueWait = securityWait + immigrationWait;
double systemTime = traveller.exit - traveller.arrival;
security_waits.add( securityWait );
immigration_waits.add( immigrationWait );
total_queue_waits.add( totalQueueWait );
system_times.add( systemTime );
if ( totalQueueWait > 600.0 ) exceed_600_count++;
if ( totalQueueWait > 900.0 ) exceed_900_count++;
if ( totalQueueWait > 1200.0 ) exceed_1200_count++;
entity_log_rows.add(
\tString.join(
\t\t",",
\t\tnew String[] {
\t\t\tschema_version,
\t\t\tconfig_id,
\t\t\tconfig_sha256,
\t\t\tmodel_version,
\t\t\tscenario_id,
\t\t\ttraveller.input_sample_id,
\t\t\tInteger.toString( traveller.replication_id ),
\t\t\ttraveller.traveller_id,
\t\t\tString.format( java.util.Locale.ROOT, "%.9f", traveller.arrival ),
\t\t\tString.format( java.util.Locale.ROOT, "%.9f", traveller.security_service_demand ),
\t\t\tString.format( java.util.Locale.ROOT, "%.9f", traveller.immigration_conventional_service_demand ),
\t\t\tString.format( java.util.Locale.ROOT, "%.9f", traveller.automation_u ),
\t\t\tString.format( java.util.Locale.ROOT, "%.9f", traveller.additional_check_u ),
\t\t\tString.format( java.util.Locale.ROOT, "%.9f", traveller.lane_tie_u ),
\t\t\tString.format( java.util.Locale.ROOT, "%.9f", traveller.security_queue_join ),
\t\t\tString.format( java.util.Locale.ROOT, "%.9f", traveller.security_start ),
\t\t\tString.format( java.util.Locale.ROOT, "%.9f", traveller.security_end ),
\t\t\tString.format( java.util.Locale.ROOT, "%.9f", traveller.immigration_queue_join ),
\t\t\ttraveller.immigration_lane_id,
\t\t\tString.format( java.util.Locale.ROOT, "%.9f", traveller.immigration_start ),
\t\t\tBoolean.toString( traveller.technology_flag ),
\t\t\tString.format( java.util.Locale.ROOT, "%.9f", traveller.immigration_primary_service_demand ),
\t\t\tString.format( java.util.Locale.ROOT, "%.9f", traveller.immigration_primary_end ),
\t\t\tBoolean.toString( traveller.additional_check_flag ),
\t\t\ttraveller.additional_check_flag
\t\t\t\t? String.format( java.util.Locale.ROOT, "%.9f", traveller.additional_check_service_demand )
\t\t\t\t: "",
\t\t\ttraveller.additional_check_flag
\t\t\t\t? String.format( java.util.Locale.ROOT, "%.9f", traveller.additional_check_end )
\t\t\t\t: "",
\t\t\tString.format( java.util.Locale.ROOT, "%.9f", traveller.exit ),
\t\t\ttraveller.security_resource_id,
\t\t\ttraveller.immigration_resource_id
\t\t}
\t)
);
if ( arrivals_closed && completed == admitted ) {
\trun_status = "COMPLETE";
\tfinishSimulation();
}"""


CUTOFF_ACTION = """\
travellerSource.set_rate( 0.0, PER_SECOND );
arrivals_closed = true;
admitted_at_cutoff = admitted;
completed_at_cutoff = completed;
security_queue_at_cutoff = security_queue_count;
security_in_service_at_cutoff = security_in_service_count;
immigration_queue_at_cutoff = immigration_queue_count;
immigration_in_service_at_cutoff = immigration_in_service_count;
if ( completed == admitted ) {
\trun_status = "COMPLETE";
\tfinishSimulation();
}"""


def _presentation_rectangle(
    *,
    item_id: int,
    name: str,
    x: int,
    y: int,
    width: int,
    height: int,
    line_color: int,
    fill_color: int,
) -> str:
    return f"""\
\t\t<Rectangle>
\t\t\t<Id>{item_id}</Id>
\t\t\t<Name><![CDATA[{name}]]></Name>
\t\t\t<ExcludeFromBuild>false</ExcludeFromBuild>
\t\t\t<X>{x}</X><Y>{y}</Y>
\t\t\t<Label><X>10</X><Y>10</Y></Label>
\t\t\t<PublicFlag>false</PublicFlag>
\t\t\t<PresentationFlag>true</PresentationFlag>
\t\t\t<ShowLabel>false</ShowLabel>
\t\t\t<AsObject>true</AsObject>
\t\t\t<EmbeddedIcon>false</EmbeddedIcon>
\t\t\t<LineWidth>2</LineWidth>
\t\t\t<LineColor>{line_color}</LineColor>
\t\t\t<LineStyle>SOLID</LineStyle>
\t\t\t<Width>{width}</Width>
\t\t\t<Height>{height}</Height>
\t\t\t<Rotation>0.0</Rotation>
\t\t\t<FillColor>{fill_color}</FillColor>
\t\t</Rectangle>"""


def _presentation_text(
    *,
    item_id: int,
    name: str,
    text: str,
    x: int,
    y: int,
    size: int,
    color: int = -15788246,
    style: int = 0,
) -> str:
    return f"""\
\t\t<Text>
\t\t\t<Id>{item_id}</Id>
\t\t\t<Name><![CDATA[{name}]]></Name>
\t\t\t<X>{x}</X><Y>{y}</Y>
\t\t\t<Label><X>10</X><Y>0</Y></Label>
\t\t\t<PublicFlag>false</PublicFlag>
\t\t\t<PresentationFlag>true</PresentationFlag>
\t\t\t<ShowLabel>false</ShowLabel>
\t\t\t<DrawMode>SHAPE_DRAW_2D3D</DrawMode>
\t\t\t<EmbeddedIcon>false</EmbeddedIcon>
\t\t\t<Z>0</Z><Rotation>0.0</Rotation><Color>{color}</Color>
\t\t\t<Text><![CDATA[{text}]]></Text>
\t\t\t<Font><Name><![CDATA[SansSerif]]></Name><Size>{size}</Size><Style>{style}</Style></Font>
\t\t\t<Alignment>LEFT</Alignment>
\t\t</Text>"""


def _decorate_model_aoc(text: str) -> str:
    level_match = re.search(
        r"\t<Presentation>\s*(<Level>.*?</Level>).*?\t</Presentation>",
        text,
        re.DOTALL,
    )
    if not level_match:
        raise RuntimeError("OperationalCheckpointModel presentation is missing")
    level = level_match.group(1)
    rectangles = [
        _presentation_rectangle(
            item_id=1785218000001,
            name="arrival_zone",
            x=35,
            y=190,
            width=145,
            height=205,
            line_color=-14334997,
            fill_color=-1050881,
        ),
        _presentation_rectangle(
            item_id=1785218000011,
            name="security_zone",
            x=210,
            y=190,
            width=250,
            height=205,
            line_color=-15293622,
            fill_color=-983564,
        ),
        _presentation_rectangle(
            item_id=1785218000021,
            name="immigration_zone",
            x=490,
            y=190,
            width=250,
            height=205,
            line_color=-1419252,
            fill_color=-2067,
        ),
        _presentation_rectangle(
            item_id=1785218000031,
            name="exit_zone",
            x=770,
            y=190,
            width=165,
            height=205,
            line_color=-10193781,
            fill_color=-460036,
        ),
        _presentation_rectangle(
            item_id=1785218000041,
            name="live_kpi_panel",
            x=35,
            y=425,
            width=900,
            height=165,
            line_color=-10193781,
            fill_color=-328966,
        ),
    ]
    labels = [
        _presentation_text(
            item_id=1785218000101,
            name="view_title",
            text="HTX CHECKPOINT — OPERATIONAL ASSUMPTION SANDBOX",
            x=35,
            y=35,
            size=24,
            style=1,
        ),
        _presentation_text(
            item_id=1785218000111,
            name="view_subtitle",
            text="Traveller-level DES | finite resources | pooled FCFS only | not calibrated",
            x=35,
            y=72,
            size=14,
            color=-10193781,
        ),
        _presentation_text(
            item_id=1785218000121,
            name="arrival_zone_title",
            text="1  ARRIVAL",
            x=55,
            y=215,
            size=17,
            color=-14334997,
            style=1,
        ),
        _presentation_text(
            item_id=1785218000131,
            name="security_zone_title",
            text="2  SECURITY",
            x=230,
            y=215,
            size=17,
            color=-15293622,
            style=1,
        ),
        _presentation_text(
            item_id=1785218000141,
            name="immigration_zone_title",
            text="3  IMMIGRATION",
            x=510,
            y=215,
            size=17,
            color=-1419252,
            style=1,
        ),
        _presentation_text(
            item_id=1785218000151,
            name="exit_zone_title",
            text="4  EXIT",
            x=790,
            y=215,
            size=17,
            color=-10193781,
            style=1,
        ),
        _presentation_text(
            item_id=1785218000161,
            name="security_zone_note",
            text="Queue + service\\nfinite lane capacity",
            x=230,
            y=310,
            size=12,
            color=-10193781,
        ),
        _presentation_text(
            item_id=1785218000171,
            name="immigration_zone_note",
            text="Pooled queue + service\\nautomation mixture",
            x=510,
            y=310,
            size=12,
            color=-10193781,
        ),
        _presentation_text(
            item_id=1785218000181,
            name="live_kpi_title",
            text="LIVE STATE — values below update during the simulation",
            x=55,
            y=440,
            size=15,
            color=-10193781,
            style=1,
        ),
        _presentation_text(
            item_id=1785218000191,
            name="control_note",
            text=(
                "Use the built-in Run / Pause / Stop controls. Stop and reopen "
                "OperationalInteractive to reset structural inputs.\\n"
                "Editable inputs: demand multiplier, Security/Immigration "
                "capacity, automation uptake and multiplier. Queue policy is "
                "not exposed because v1 implements pooled FCFS only."
            ),
            x=55,
            y=105,
            size=12,
            color=-10193781,
        ),
    ]
    replacement = (
        "\t<Presentation>\n\t"
        + level
        + "\n"
        + "\n".join(rectangles)
        + "\n"
        + "\n".join(labels)
        + "\n\t</Presentation>"
    )
    result = text[: level_match.start()] + replacement + text[level_match.end() :]
    result = re.sub(
        r"<SceneBackgroundColor>.*?</SceneBackgroundColor>",
        "<SceneBackgroundColor>-328966</SceneBackgroundColor>",
        result,
        count=1,
    )
    return result


def _replace_embedded_position(
    block: str,
    *,
    x: int,
    y: int,
    label_x: int,
    label_y: int,
) -> str:
    block, count = re.subn(r"<X>-?\d+</X>", f"<X>{x}</X>", block, count=1)
    if count != 1:
        raise RuntimeError("Embedded object X coordinate is missing")
    block, count = re.subn(r"<Y>-?\d+</Y>", f"<Y>{y}</Y>", block, count=1)
    if count != 1:
        raise RuntimeError("Embedded object Y coordinate is missing")
    block, count = re.subn(
        r"<Label>\s*<X>-?\d+</X>\s*<Y>-?\d+</Y>\s*</Label>",
        f"<Label><X>{label_x}</X><Y>{label_y}</Y></Label>",
        block,
        count=1,
    )
    if count != 1:
        raise RuntimeError("Embedded object label coordinates are missing")
    return block


def _parameter_fragment(name: str, value_class: str | None, code: str = "", unit: str = "") -> str:
    if value_class is None:
        return f"""\
\t\t\t<Parameter>
\t\t\t\t<Name><![CDATA[{name}]]></Name>
\t\t\t</Parameter>"""
    unit_value = "PER_SECOND" if unit == "RateUnits" else "SECOND"
    unit_line = (
        f'\n\t\t\t\t\t<Unit Class="{unit}">{unit_value}</Unit>'
        if unit
        else ""
    )
    return f"""\
\t\t\t<Parameter>
\t\t\t\t<Name><![CDATA[{name}]]></Name>
\t\t\t\t<Value Class="{value_class}">
\t\t\t\t\t<Code><![CDATA[{code}]]></Code>{unit_line}
\t\t\t\t</Value>
\t\t\t</Parameter>"""


def _replace_parameter(block: str, name: str, replacement: str) -> str:
    pattern = re.compile(
        r"\t\t\t<Parameter>\s*"
        + rf"<Name><!\[CDATA\[{re.escape(name)}\]\]></Name>"
        + r".*?\t\t\t</Parameter>",
        re.DOTALL,
    )
    result, count = pattern.subn(replacement, block, count=1)
    if count != 1:
        raise RuntimeError(f"Expected one {name!r} parameter in block")
    return result


def _transform_embedded_objects(op_traveller_generic_id: str) -> str:
    text = _read(CHECKPOINT / "EmbeddedObjects.xml")
    for old, new in {
        "178508802": "178516312",
        "CheckpointTraveller": "OperationalTraveller",
        "1785088400006": op_traveller_generic_id,
    }.items():
        text = text.replace(old, new)

    chunks = text.split("\n\t<EmbeddedObject>")
    transformed = [chunks[0]]
    for raw in chunks[1:]:
        block = "\n\t<EmbeddedObject>" + raw
        name_match = re.search(r"<Name><!\[CDATA\[(.*?)\]\]></Name>", block)
        name = name_match.group(1) if name_match else ""
        if name in MODEL_BLOCK_POSITIONS:
            x, y, label_x, label_y = MODEL_BLOCK_POSITIONS[name]
            block = _replace_embedded_position(
                block,
                x=x,
                y=y,
                label_x=label_x,
                label_y=label_y,
            )
        if name == "travellerSource":
            block = _replace_parameter(
                block,
                "arrivalType",
                _parameter_fragment("arrivalType", "CodeValue", "self.RATE"),
            )
            block = _replace_parameter(
                block, "interarrivalTime", _parameter_fragment("interarrivalTime", None)
            )
            block = _replace_parameter(
                block, "firstArrivalMode", _parameter_fragment("firstArrivalMode", None)
            )
            block = _replace_parameter(
                block, "firstArrivalTime", _parameter_fragment("firstArrivalTime", None)
            )
            block = _replace_parameter(
                block,
                "limitArrivals",
                _parameter_fragment("limitArrivals", "CodeValue", "false"),
            )
            block = _replace_parameter(
                block, "maxArrivals", _parameter_fragment("maxArrivals", None)
            )
            block = _replace_parameter(
                block,
                "onExit",
                _parameter_fragment("onExit", "CodeValue", SOURCE_ON_EXIT),
            )
            block = _replace_parameter(
                block,
                "rate",
                _parameter_fragment(
                    "rate",
                    "CodeUnitValue",
                    "arrival_rate_per_second * demand_multiplier",
                    "RateUnits",
                ),
            )
        elif name == "securityService":
            block = _replace_parameter(
                block,
                "delayTime",
                _parameter_fragment(
                    "delayTime",
                    "CodeUnitValue",
                    "((OperationalTraveller) agent).security_service_demand",
                    "TimeUnits",
                ),
            )
            block = _replace_parameter(
                block, "onEnter", _parameter_fragment("onEnter", "CodeValue", SECURITY_ENTER)
            )
            block = _replace_parameter(
                block,
                "onSeizeUnit",
                _parameter_fragment(
                    "onSeizeUnit",
                    "CodeValue",
                    '((OperationalTraveller) agent).security_resource_id = "SECURITY_" + Integer.toString( unit.getId() );',
                ),
            )
            block = _replace_parameter(
                block,
                "onEnterDelay",
                _parameter_fragment("onEnterDelay", "CodeValue", SECURITY_DELAY_ENTER),
            )
            block = _replace_parameter(
                block, "onAtExit", _parameter_fragment("onAtExit", "CodeValue", SECURITY_EXIT)
            )
        elif name == "immigrationService":
            block = _replace_parameter(
                block,
                "delayTime",
                _parameter_fragment(
                    "delayTime",
                    "CodeUnitValue",
                    "((OperationalTraveller) agent).immigration_primary_service_demand\n+ ((OperationalTraveller) agent).additional_check_service_demand",
                    "TimeUnits",
                ),
            )
            block = _replace_parameter(
                block,
                "onEnter",
                _parameter_fragment("onEnter", "CodeValue", IMMIGRATION_ENTER),
            )
            block = _replace_parameter(
                block,
                "onSeizeUnit",
                _parameter_fragment(
                    "onSeizeUnit",
                    "CodeValue",
                    '((OperationalTraveller) agent).immigration_resource_id = "IMMIGRATION_" + Integer.toString( unit.getId() );',
                ),
            )
            block = _replace_parameter(
                block,
                "onEnterDelay",
                _parameter_fragment("onEnterDelay", "CodeValue", IMMIGRATION_DELAY_ENTER),
            )
            block = _replace_parameter(
                block,
                "onAtExit",
                _parameter_fragment("onAtExit", "CodeValue", IMMIGRATION_EXIT),
            )
        elif name == "checkpointSink":
            block = _replace_parameter(
                block, "onEnter", _parameter_fragment("onEnter", "CodeValue", SINK_ENTER)
            )
        transformed.append(block)
    return "".join(transformed)


def _transform_connectors() -> str:
    text = _read(CHECKPOINT / "Connectors.xml")
    text = text.replace("178508803", "178516313")
    text = text.replace("CheckpointModel", "OperationalCheckpointModel")
    point_map = {
        "sourceToSecurity": ((120, 290), (300, 290)),
        "securityToImmigration": ((360, 290), (580, 290)),
        "immigrationToSink": ((640, 290), (850, 290)),
    }
    chunks = text.split("\n\t<Connector>")
    transformed = [chunks[0]]
    for raw in chunks[1:]:
        block = "\n\t<Connector>" + raw
        name_match = re.search(r"<Name><!\[CDATA\[(.*?)\]\]></Name>", block)
        name = name_match.group(1) if name_match else ""
        if name in point_map:
            start, end = point_map[name]
            points = f"""\
\t\t<Points>
\t\t\t<Point><X>{start[0]}</X><Y>{start[1]}</Y></Point>
\t\t\t<Point><X>{end[0]}</X><Y>{end[1]}</Y></Point>
\t\t</Points>"""
            block, count = re.subn(
                r"\t\t<Points>.*?\t\t</Points>",
                points,
                block,
                count=1,
                flags=re.DOTALL,
            )
            if count != 1:
                raise RuntimeError(f"Connector {name} points are missing")
        transformed.append(block)
    return "".join(transformed)


COMMON_BEFORE_RUN = """\
if ( !"1.0".equals( root.schema_version ) )
\tthrow new IllegalArgumentException( "schema_version must be 1.0" );
if ( !root.config_sha256.matches( "[0-9a-f]{64}" ) )
\tthrow new IllegalArgumentException( "config_sha256 must be 64 lowercase hex characters" );
if ( !root.output_collection_id.matches( "[a-z0-9_]+" ) )
\tthrow new IllegalArgumentException( "output_collection_id is unsafe" );
if ( !"HPP".equals( root.arrival_mode ) )
\tthrow new IllegalArgumentException( "arrival_mode must be HPP" );
if ( !( root.arrival_rate_per_second > 0.0 ) || !( root.demand_multiplier > 0.0 ) )
\tthrow new IllegalArgumentException( "arrival rate and demand multiplier must be positive" );
if ( !( root.arrival_cutoff_seconds > 0.0 ) || root.arrival_guard <= 1 )
\tthrow new IllegalArgumentException( "arrival cutoff and guard are invalid" );
if ( root.arrival_rate_per_second * root.demand_multiplier * root.arrival_cutoff_seconds >= root.arrival_guard )
\tthrow new IllegalArgumentException( "arrival_guard must exceed expected arrivals" );
if ( !"FULL_DRAIN".equals( root.drain_rule ) )
\tthrow new IllegalArgumentException( "drain_rule must be FULL_DRAIN" );
if ( root.security_capacity <= 0 || root.immigration_capacity <= 0 )
\tthrow new IllegalArgumentException( "resource capacities must be positive" );
if ( root.security_queue_capacity <= 0 || root.immigration_queue_capacity <= 0 )
\tthrow new IllegalArgumentException( "queue capacities must be positive" );
if ( !"FIXED".equals( root.security_service_distribution )
\t|| !"FIXED".equals( root.immigration_service_distribution ) )
\tthrow new IllegalArgumentException( "v1 supports FIXED primary service only" );
if ( !( root.security_service_p1_seconds > 0.0 )
\t|| !( root.immigration_service_p1_seconds > 0.0 ) )
\tthrow new IllegalArgumentException( "primary service demands must be positive" );
if ( !"pooled".equals( root.queue_policy ) )
\tthrow new IllegalArgumentException( "v1 implements pooled FCFS only" );
if ( "DISABLED".equals( root.automation_mapping_mode ) ) {
\tif ( root.automation_uptake != 0.0 || root.automation_multiplier != 1.0 )
\t\tthrow new IllegalArgumentException( "DISABLED automation requires uptake=0 and multiplier=1" );
} else if ( "MULTIPLIER".equals( root.automation_mapping_mode ) ) {
\tif ( !( root.automation_uptake > 0.0 && root.automation_uptake <= 1.0 )
\t\t|| !( root.automation_multiplier > 0.0 && root.automation_multiplier < 1.0 ) )
\t\tthrow new IllegalArgumentException( "automation inputs are outside their domains" );
} else {
\tthrow new IllegalArgumentException( "unknown automation_mapping_mode" );
}
if ( "NONE".equals( root.additional_check_semantics ) ) {
\tif ( root.additional_check_probability_conventional != 0.0
\t\t|| root.additional_check_probability_technology != 0.0
\t\t|| !"UNSET".equals( root.additional_check_service_distribution )
\t\t|| root.additional_check_service_p1_seconds != 0.0 )
\t\tthrow new IllegalArgumentException( "NONE additional-check contract violated" );
} else if ( "COUNTER_HELD_RISK_REFERRAL_PROXY".equals( root.additional_check_semantics ) ) {
\tif ( !"FIXED".equals( root.additional_check_service_distribution )
\t\t|| root.additional_check_probability_conventional < 0.0
\t\t|| root.additional_check_probability_conventional > 1.0
\t\t|| root.additional_check_probability_technology < 0.0
\t\t|| root.additional_check_probability_technology > 1.0
\t\t|| !( root.additional_check_service_p1_seconds > 0.0 ) )
\t\tthrow new IllegalArgumentException( "risk-proxy inputs are invalid" );
} else {
\tthrow new IllegalArgumentException( "unknown additional_check_semantics" );
}
if ( !"EMPTY_AND_IDLE".equals( root.start_state )
\t|| !"NOT_CALIBRATED".equals( root.calibration_status )
\t|| !"COMPARATIVE_WHAT_IF_ONLY".equals( root.claim_ceiling )
\t|| !( "NOT_TESTED".equals( root.crn_alignment_status )
\t\t|| "PENDING_VALIDATION".equals( root.crn_alignment_status ) ) )
\tthrow new IllegalArgumentException( "claim-boundary fields were weakened" );
"""


INTERACTIVE_SETUP = """\
if ( root.demand_multiplier < 0.5 || root.demand_multiplier > 2.0 )
\tthrow new IllegalArgumentException(
\t\t"demand_multiplier must be between 0.5 and 2.0"
\t);
if ( root.security_capacity < 1 || root.security_capacity > 200
\t|| root.immigration_capacity < 1 || root.immigration_capacity > 200 )
\tthrow new IllegalArgumentException(
\t\t"interactive capacities must be integers between 1 and 200"
\t);
if ( root.automation_uptake < 0.0 || root.automation_uptake > 1.0 )
\tthrow new IllegalArgumentException(
\t\t"automation_uptake must be between 0 and 1"
\t);
if ( root.automation_uptake == 0.0 ) {
\troot.automation_mapping_mode = "DISABLED";
\troot.automation_multiplier = 1.0;
} else {
\tif ( !( root.automation_multiplier > 0.0
\t\t&& root.automation_multiplier < 1.0 ) )
\t\tthrow new IllegalArgumentException(
\t\t\t"automation_multiplier must be between 0 and 1 when uptake is positive"
\t\t);
\troot.automation_mapping_mode = "MULTIPLIER";
}
root.output_collection_id = "anylogic_operational";
root.config_id = "OP_INTERACTIVE_AD_HOC_V1";
root.scenario_family = "INTERACTIVE_EXPLORATORY";
root.reference_scenario_id = "REFERENCE_ASSUMPTION_SANDBOX_V1";
root.input_sample_id = "LOCAL_WINDOW_HPP_BASE";
root.replication_id = 0;
root.scenario_id = String.format(
\tjava.util.Locale.ROOT,
\t"INTERACTIVE_D%03d_SEC%03d_IMM%03d_U%03d_M%03d",
\t(int) Math.round( 100.0 * root.demand_multiplier ),
\troot.security_capacity,
\troot.immigration_capacity,
\t(int) Math.round( 100.0 * root.automation_uptake ),
\t(int) Math.round( 100.0 * root.automation_multiplier )
);
String interactiveCanonical = String.format(
\tjava.util.Locale.ROOT,
\t"model=TASK3_OPERATIONAL_POOLED_V1|queue=pooled|"
\t+ "demand=%.9f|security_capacity=%d|immigration_capacity=%d|"
\t+ "automation_mode=%s|automation_uptake=%.9f|"
\t+ "automation_multiplier=%.9f",
\troot.demand_multiplier,
\troot.security_capacity,
\troot.immigration_capacity,
\troot.automation_mapping_mode,
\troot.automation_uptake,
\troot.automation_multiplier
);
try {
\tjava.security.MessageDigest digest =
\t\tjava.security.MessageDigest.getInstance( "SHA-256" );
\tbyte[] hash = digest.digest(
\t\tinteractiveCanonical.getBytes( java.nio.charset.StandardCharsets.UTF_8 )
\t);
\tStringBuilder hexadecimal = new StringBuilder();
\tfor ( byte value : hash )
\t\thexadecimal.append(
\t\t\tString.format( java.util.Locale.ROOT, "%02x", value & 0xff )
\t\t);
\troot.config_sha256 = hexadecimal.toString();
} catch ( java.security.NoSuchAlgorithmException exception ) {
\tthrow new RuntimeException( "SHA-256 is unavailable", exception );
}
"""


INTERACTIVE_BEFORE_RUN = INTERACTIVE_SETUP + COMMON_BEFORE_RUN + """\
if ( !"TASK3_OPERATIONAL_POOLED_V1".equals( root.model_version )
\t|| root.arrival_rate_per_second != 1.364213
\t|| root.arrival_cutoff_seconds != 300.0
\t|| root.arrival_guard != 5000
\t|| root.security_queue_capacity != 5000
\t|| root.security_service_p1_seconds != 21.818181818
\t|| root.immigration_queue_capacity != 5000
\t|| root.immigration_service_p1_seconds != 13.0
\t|| !"pooled".equals( root.queue_policy )
\t|| !"NONE".equals( root.additional_check_semantics )
\t|| root.additional_check_probability_conventional != 0.0
\t|| root.additional_check_probability_technology != 0.0
\t|| !"UNSET".equals( root.additional_check_service_distribution )
\t|| root.additional_check_service_p1_seconds != 0.0
\t|| root.master_seed != 2026072800L
\t|| root.arrival_seed != 2026072801L
\t|| root.service_seed != 2026072802L
\t|| root.routing_seed != 2026072803L
\t|| root.tie_seed != 2026072804L )
\tthrow new IllegalArgumentException(
\t\t"OperationalInteractive permits only the five exposed exploratory inputs; "
\t\t+ "all other mechanism and lineage fields must remain fixed"
\t);
getEngine().getDefaultRandomGenerator().setSeed( root.arrival_seed );"""


def _pilot_before_run(
    rows: list[dict[str, str]],
) -> str:
    guards: list[str] = []
    for index, row in enumerate(rows):
        keyword = "if" if index == 0 else "else if"
        scenario_id = json.dumps(row["scenario_id"])
        config_id = json.dumps(row["config_id"])
        config_hash = json.dumps(scenario_config_sha256(row))
        guards.append(
            f"""{keyword} ( {scenario_id}.equals( root.scenario_id ) ) {{
\texpectedConfigId = {config_id};
\texpectedConfigHash = {config_hash};
\tscenarioSeedIndex = {index};
}}"""
        )
    scenario_guard = "\n".join(guards)
    return COMMON_BEFORE_RUN + f"""\
if ( !"TASK3_OPERATIONAL_POOLED_V1".equals( root.model_version ) )
\tthrow new IllegalArgumentException( "OperationalPilot model_version mismatch" );
if ( !"{PILOT_OUTPUT_COLLECTION}".equals( root.output_collection_id ) )
\tthrow new IllegalArgumentException( "OperationalPilot output collection mismatch" );
String expectedConfigId = null;
String expectedConfigHash = null;
int scenarioSeedIndex = -1;
{scenario_guard}
if ( expectedConfigId == null || expectedConfigHash == null
\t|| scenarioSeedIndex < 0 )
\tthrow new IllegalArgumentException( "OperationalPilot received an unknown scenario_id" );
if ( !expectedConfigId.equals( root.config_id )
\t|| !expectedConfigHash.equals( root.config_sha256 ) )
\tthrow new IllegalArgumentException(
\t\t"OperationalPilot scenario lineage mismatch for " + root.scenario_id
\t);
int replication = getCurrentReplication();
if ( replication < 1 || replication > 10 )
\tthrow new IllegalArgumentException( "OperationalPilot replication must be 1..10" );
root.replication_id = replication;
long streamBase =
\troot.master_seed
\t+ 100000L * (long) scenarioSeedIndex
\t+ 100L * (long) replication;
root.arrival_seed = streamBase + 1L;
root.service_seed = streamBase + 2L;
root.routing_seed = streamBase + 3L;
root.tie_seed = streamBase + 4L;
getEngine().getDefaultRandomGenerator().setSeed( root.arrival_seed );"""


def _confirmatory_before_run(
    rows: list[dict[str, str]],
    seed_rows: list[dict[str, str]],
) -> str:
    cell_guards: list[str] = []
    for index, row in enumerate(rows):
        keyword = "if" if index == 0 else "else if"
        scenario_id = json.dumps(row["scenario_id"])
        input_sample_id = json.dumps(row["input_sample_id"])
        config_id = json.dumps(row["config_id"])
        config_hash = json.dumps(scenario_config_sha256(row))
        cell_guards.append(
            f"""{keyword} ( {scenario_id}.equals( root.scenario_id )
\t&& {input_sample_id}.equals( root.input_sample_id ) ) {{
\texpectedConfigId = {config_id};
\texpectedConfigHash = {config_hash};
}}"""
        )

    seed_guards: list[str] = []
    for index, seed in enumerate(seed_rows):
        keyword = "if" if index == 0 else "else if"
        input_sample_id = json.dumps(seed["input_sample_id"])
        replication_id = int(seed["replication_id"])
        seed_guards.append(
            f"""{keyword} ( {input_sample_id}.equals( root.input_sample_id )
\t&& replication == {replication_id} ) {{
\troot.arrival_seed = {int(seed["arrival_seed"])}L;
\troot.service_seed = {int(seed["service_seed"])}L;
\troot.routing_seed = {int(seed["routing_seed"])}L;
\troot.tie_seed = {int(seed["tie_seed"])}L;
\tseedGroupMatched = true;
}}"""
        )

    masters = {int(row["master_seed"]) for row in seed_rows}
    if len(masters) != 1:
        raise RuntimeError("confirmatory seed manifest has multiple master seeds")
    master_seed = next(iter(masters))
    return COMMON_BEFORE_RUN + f"""\
if ( !"TASK3_OPERATIONAL_POOLED_V1".equals( root.model_version ) )
\tthrow new IllegalArgumentException(
\t\t"CapacityRobustnessConfirmatory model_version mismatch"
\t);
if ( !"{CONFIRMATORY_OUTPUT_COLLECTION}".equals( root.output_collection_id ) )
\tthrow new IllegalArgumentException(
\t\t"CapacityRobustnessConfirmatory output collection mismatch"
\t);
if ( root.master_seed != {master_seed}L )
\tthrow new IllegalArgumentException(
\t\t"CapacityRobustnessConfirmatory master seed mismatch"
\t);
String expectedConfigId = null;
String expectedConfigHash = null;
{chr(10).join(cell_guards)}
if ( expectedConfigId == null || expectedConfigHash == null )
\tthrow new IllegalArgumentException(
\t\t"CapacityRobustnessConfirmatory received an unknown scenario/input cell"
\t);
if ( !expectedConfigId.equals( root.config_id )
\t|| !expectedConfigHash.equals( root.config_sha256 ) )
\tthrow new IllegalArgumentException(
\t\t"CapacityRobustnessConfirmatory lineage mismatch for "
\t\t+ root.scenario_id + "/" + root.input_sample_id
\t);
int replication = getCurrentReplication();
if ( replication < 1 || replication > 50 )
\tthrow new IllegalArgumentException(
\t\t"CapacityRobustnessConfirmatory replication must be 1..50"
\t);
root.replication_id = replication;
boolean seedGroupMatched = false;
{chr(10).join(seed_guards)}
if ( !seedGroupMatched )
\tthrow new IllegalArgumentException(
\t\t"CapacityRobustnessConfirmatory seed group is not frozen"
\t);
getEngine().getDefaultRandomGenerator().setSeed( root.arrival_seed );"""


AFTER_RUN = """\
if ( !"COMPLETE".equals( root.run_status ) )
\tthrow new IllegalStateException( "operational run did not reach COMPLETE" );
if ( root.guard_hit || root.rejected_or_dropped_count != 0 )
\tthrow new IllegalStateException( "guard, rejection, or drop detected" );
if ( root.admitted != root.completed )
\tthrow new IllegalStateException( "full-drain conservation failed" );
if ( root.security_queue_count != 0 || root.security_in_service_count != 0
\t|| root.immigration_queue_count != 0 || root.immigration_in_service_count != 0 )
\tthrow new IllegalStateException( "non-zero WIP after drain" );
int wipAtCutoff =
\troot.security_queue_at_cutoff + root.security_in_service_at_cutoff
\t+ root.immigration_queue_at_cutoff + root.immigration_in_service_at_cutoff;
boolean conservationPass =
\troot.admitted_at_cutoff == root.completed_at_cutoff + wipAtCutoff;
if ( !conservationPass )
\tthrow new IllegalStateException( "cutoff conservation failed" );

java.util.ArrayList<Double> securitySorted =
\tnew java.util.ArrayList<Double>( root.security_waits );
java.util.ArrayList<Double> immigrationSorted =
\tnew java.util.ArrayList<Double>( root.immigration_waits );
java.util.ArrayList<Double> totalSorted =
\tnew java.util.ArrayList<Double>( root.total_queue_waits );
java.util.ArrayList<Double> systemSorted =
\tnew java.util.ArrayList<Double>( root.system_times );
java.util.Collections.sort( securitySorted );
java.util.Collections.sort( immigrationSorted );
java.util.Collections.sort( totalSorted );
java.util.Collections.sort( systemSorted );
double securitySum = 0.0, immigrationSum = 0.0, totalSum = 0.0, systemSum = 0.0;
for ( double value : securitySorted ) securitySum += value;
for ( double value : immigrationSorted ) immigrationSum += value;
for ( double value : totalSorted ) totalSum += value;
for ( double value : systemSorted ) systemSum += value;
int n = root.completed;
if ( n <= 0 ) throw new IllegalStateException( "operational run generated no travellers" );
int p95Index = Math.max( 0, (int) Math.ceil( 0.95 * n ) - 1 );
double drainEnd = Math.max( root.arrival_cutoff_seconds, root.last_exit );
int cutoffBacklog = root.admitted_at_cutoff - root.completed_at_cutoff;
double securityUtilization =
\troot.security_busy_seconds / ( root.security_capacity * drainEnd );
double immigrationUtilization =
\troot.immigration_busy_seconds / ( root.immigration_capacity * drainEnd );
java.util.function.DoubleFunction<String> number = value ->
\tString.format( java.util.Locale.ROOT, "%.9f", value );

java.io.File probe = new java.io.File(
\tSystem.getProperty( "htx.repo.root", System.getProperty( "user.dir" ) )
).getAbsoluteFile();
while ( probe != null
\t&& !new java.io.File( probe, "config/operational_scenarios.csv" ).isFile() ) {
\tprobe = probe.getParentFile();
}
if ( probe == null )
\tthrow new IllegalStateException( "Cannot locate repository root" );
java.nio.file.Path runDirectory = new java.io.File(
\tprobe,
\tString.format(
\t\tjava.util.Locale.ROOT,
\t\t"results/raw/%s/%s/%s/replication_%03d",
\t\troot.output_collection_id,
\t\troot.scenario_id,
\t\troot.input_sample_id,
\t\troot.replication_id
\t)
).toPath();
try {
\tjava.nio.file.Files.createDirectories( runDirectory );
\tjava.util.ArrayList<String> manifest = new java.util.ArrayList<String>();
\tmanifest.add(
\t\t"schema_version,config_id,config_sha256,model_version,scenario_id,"
\t\t+ "scenario_family,reference_scenario_id,input_sample_id,replication_id,"
\t\t+ "master_seed,arrival_seed,service_seed,routing_seed,tie_seed,start_state,"
\t\t+ "arrival_mode,arrival_cutoff_seconds,drain_end_seconds,drain_rule,"
\t\t+ "engine_name,engine_version,calibration_status,claim_ceiling,"
\t\t+ "crn_alignment_status,run_status"
\t);
\tmanifest.add( String.join( ",", new String[] {
\t\troot.schema_version, root.config_id, root.config_sha256, root.model_version,
\t\troot.scenario_id, root.scenario_family, root.reference_scenario_id,
\t\troot.input_sample_id, Integer.toString( root.replication_id ),
\t\tLong.toString( root.master_seed ), Long.toString( root.arrival_seed ),
\t\tLong.toString( root.service_seed ), Long.toString( root.routing_seed ),
\t\tLong.toString( root.tie_seed ), root.start_state, root.arrival_mode,
\t\tnumber.apply( root.arrival_cutoff_seconds ), number.apply( drainEnd ),
\t\troot.drain_rule, "AnyLogic", "8.9.9.202607020720",
\t\troot.calibration_status, root.claim_ceiling, root.crn_alignment_status,
\t\troot.run_status
\t} ) );
\tjava.util.ArrayList<String> entities = new java.util.ArrayList<String>();
\tentities.add(
\t\t"schema_version,config_id,config_sha256,model_version,scenario_id,"
\t\t+ "input_sample_id,replication_id,traveller_id,arrival_seconds,"
\t\t+ "security_service_demand_seconds,"
\t\t+ "immigration_conventional_service_demand_seconds,automation_u,"
\t\t+ "additional_check_u,lane_tie_u,security_queue_join_seconds,"
\t\t+ "security_start_seconds,security_end_seconds,"
\t\t+ "immigration_queue_join_seconds,immigration_lane_id,"
\t\t+ "immigration_start_seconds,technology_flag,"
\t\t+ "immigration_primary_service_demand_seconds,"
\t\t+ "immigration_primary_end_seconds,additional_check_flag,"
\t\t+ "additional_check_service_demand_seconds,"
\t\t+ "additional_check_end_seconds,exit_seconds,security_resource_id,"
\t\t+ "immigration_resource_id"
\t);
\tentities.addAll( root.entity_log_rows );
\tjava.util.ArrayList<String> kpis = new java.util.ArrayList<String>();
\tkpis.add(
\t\t"schema_version,config_id,config_sha256,model_version,scenario_id,"
\t\t+ "input_sample_id,replication_id,arrival_cutoff_seconds,"
\t\t+ "drain_end_seconds,arrivals,completed_at_cutoff,"
\t\t+ "security_queue_at_cutoff,security_in_service_at_cutoff,"
\t\t+ "immigration_queue_at_cutoff,immigration_in_service_at_cutoff,"
\t\t+ "wip_at_cutoff,completed_after_drain,rejected_or_dropped_count,"
\t\t+ "technology_count,additional_check_count,"
\t\t+ "security_wait_mean_seconds,security_wait_p95_seconds,"
\t\t+ "immigration_wait_mean_seconds,immigration_wait_p95_seconds,"
\t\t+ "total_queue_wait_mean_seconds,total_queue_wait_p95_seconds,"
\t\t+ "total_queue_wait_exceed_600_rate,total_queue_wait_exceed_900_rate,"
\t\t+ "total_queue_wait_exceed_1200_rate,system_time_mean_seconds,"
\t\t+ "system_time_p95_seconds,security_utilization,immigration_utilization,"
\t\t+ "cutoff_backlog,cutoff_backlog_fraction,"
\t\t+ "cohort_clear_time_after_cutoff_seconds,conservation_pass,run_status"
\t);
\tkpis.add( String.join( ",", new String[] {
\t\troot.schema_version, root.config_id, root.config_sha256, root.model_version,
\t\troot.scenario_id, root.input_sample_id, Integer.toString( root.replication_id ),
\t\tnumber.apply( root.arrival_cutoff_seconds ), number.apply( drainEnd ),
\t\tInteger.toString( root.admitted ), Integer.toString( root.completed_at_cutoff ),
\t\tInteger.toString( root.security_queue_at_cutoff ),
\t\tInteger.toString( root.security_in_service_at_cutoff ),
\t\tInteger.toString( root.immigration_queue_at_cutoff ),
\t\tInteger.toString( root.immigration_in_service_at_cutoff ),
\t\tInteger.toString( wipAtCutoff ), Integer.toString( root.completed ),
\t\tInteger.toString( root.rejected_or_dropped_count ),
\t\tInteger.toString( root.technology_count ),
\t\tInteger.toString( root.additional_check_count ),
\t\tnumber.apply( securitySum / n ), number.apply( securitySorted.get( p95Index ) ),
\t\tnumber.apply( immigrationSum / n ), number.apply( immigrationSorted.get( p95Index ) ),
\t\tnumber.apply( totalSum / n ), number.apply( totalSorted.get( p95Index ) ),
\t\tnumber.apply( (double) root.exceed_600_count / n ),
\t\tnumber.apply( (double) root.exceed_900_count / n ),
\t\tnumber.apply( (double) root.exceed_1200_count / n ),
\t\tnumber.apply( systemSum / n ), number.apply( systemSorted.get( p95Index ) ),
\t\tnumber.apply( securityUtilization ), number.apply( immigrationUtilization ),
\t\tInteger.toString( cutoffBacklog ),
\t\tnumber.apply( root.admitted_at_cutoff > 0
\t\t\t? (double) cutoffBacklog / root.admitted_at_cutoff : 0.0 ),
\t\tnumber.apply( Math.max( 0.0, drainEnd - root.arrival_cutoff_seconds ) ),
\t\tBoolean.toString( conservationPass ), root.run_status
\t} ) );
\tjava.nio.file.Files.write(
\t\trunDirectory.resolve( "run_manifest.csv" ), manifest,
\t\tjava.nio.charset.StandardCharsets.UTF_8
\t);
\tjava.nio.file.Files.write(
\t\trunDirectory.resolve( "entity_log.csv" ), entities,
\t\tjava.nio.charset.StandardCharsets.UTF_8
\t);
\tjava.nio.file.Files.write(
\t\trunDirectory.resolve( "replication_kpis.csv" ), kpis,
\t\tjava.nio.charset.StandardCharsets.UTF_8
\t);
} catch ( java.io.IOException exception ) {
\tthrow new RuntimeException( "Operational CSV export failed", exception );
}"""


def _experiment_xml(model_id: str, experiment_id: str, text_id: str) -> str:
    before = html.escape(INTERACTIVE_BEFORE_RUN, quote=False)
    after = html.escape(AFTER_RUN, quote=False)
    params = "\n".join(
        f"\t\t\t<Parameter><ParameterName>{name}</ParameterName></Parameter>"
        for name in INTERACTIVE_PARAMETER_NAMES
    )
    return f"""\
\t<SimulationExperiment ActiveObjectClassId="{model_id}">
\t\t<Id>{experiment_id}</Id>
\t\t<Name><![CDATA[OperationalInteractive]]></Name>
\t\t<CommandLineArguments/>
\t\t<MaximumMemory>512</MaximumMemory>
\t\t<RandomNumberGenerationType>fixedSeed</RandomNumberGenerationType>
\t\t<CustomGeneratorCode>new Random()</CustomGeneratorCode>
\t\t<BeforeSimulationRunCode>{before}</BeforeSimulationRunCode>
\t\t<AfterSimulationRunCode>{after}</AfterSimulationRunCode>
\t\t<SeedValue>2026072801</SeedValue>
\t\t<SelectionModeForSimultaneousEvents>LIFO</SelectionModeForSimultaneousEvents>
\t\t<VmArgs/>
\t\t<LoadRootFromSnapshot>false</LoadRootFromSnapshot>
\t\t<Presentation>
\t\t\t<Text>
\t\t\t\t<Id>{text_id}</Id>
\t\t\t\t<Name><![CDATA[text]]></Name>
\t\t\t\t<X>40</X><Y>25</Y>
\t\t\t\t<Label><X>10</X><Y>0</Y></Label>
\t\t\t\t<PublicFlag>true</PublicFlag>
\t\t\t\t<PresentationFlag>true</PresentationFlag>
\t\t\t\t<ShowLabel>false</ShowLabel>
\t\t\t\t<DrawMode>SHAPE_DRAW_2D3D</DrawMode>
\t\t\t\t<EmbeddedIcon>false</EmbeddedIcon>
\t\t\t\t<Z>0</Z><Rotation>0.0</Rotation><Color>-12490271</Color>
\t\t\t\t<Text><![CDATA[OperationalInteractive — editable exploratory run]]></Text>
\t\t\t\t<Font><Name><![CDATA[SansSerif]]></Name><Size>22</Size><Style>0</Style></Font>
\t\t\t\t<Alignment>LEFT</Alignment>
\t\t\t</Text>
\t\t\t<Text>
\t\t\t\t<Id>1785218100001</Id>
\t\t\t\t<Name><![CDATA[editable_parameters_note]]></Name>
\t\t\t\t<X>40</X><Y>65</Y>
\t\t\t\t<Label><X>10</X><Y>0</Y></Label>
\t\t\t\t<PublicFlag>false</PublicFlag>
\t\t\t\t<PresentationFlag>true</PresentationFlag>
\t\t\t\t<ShowLabel>false</ShowLabel>
\t\t\t\t<DrawMode>SHAPE_DRAW_2D3D</DrawMode>
\t\t\t\t<EmbeddedIcon>false</EmbeddedIcon>
\t\t\t\t<Z>0</Z><Rotation>0.0</Rotation><Color>-10193781</Color>
\t\t\t\t<Text><![CDATA[Edit only the five fields shown below before Run: demand multiplier, Security capacity, Immigration capacity, automation uptake, and automation multiplier.]]></Text>
\t\t\t\t<Font><Name><![CDATA[SansSerif]]></Name><Size>13</Size><Style>0</Style></Font>
\t\t\t\t<Alignment>LEFT</Alignment>
\t\t\t</Text>
\t\t\t<Text>
\t\t\t\t<Id>1785218100011</Id>
\t\t\t\t<Name><![CDATA[automation_control_note]]></Name>
\t\t\t\t<X>40</X><Y>92</Y>
\t\t\t\t<Label><X>10</X><Y>0</Y></Label>
\t\t\t\t<PublicFlag>false</PublicFlag>
\t\t\t\t<PresentationFlag>true</PresentationFlag>
\t\t\t\t<ShowLabel>false</ShowLabel>
\t\t\t\t<DrawMode>SHAPE_DRAW_2D3D</DrawMode>
\t\t\t\t<EmbeddedIcon>false</EmbeddedIcon>
\t\t\t\t<Z>0</Z><Rotation>0.0</Rotation><Color>-10193781</Color>
\t\t\t\t<Text><![CDATA[Automation: uptake = 0 disables the mixture; uptake > 0 requires a multiplier strictly between 0 and 1. Pooled FCFS is the only implemented queue policy.]]></Text>
\t\t\t\t<Font><Name><![CDATA[SansSerif]]></Name><Size>12</Size><Style>0</Style></Font>
\t\t\t\t<Alignment>LEFT</Alignment>
\t\t\t</Text>
\t\t\t<Text>
\t\t\t\t<Id>1785218100021</Id>
\t\t\t\t<Name><![CDATA[run_control_note]]></Name>
\t\t\t\t<X>40</X><Y>118</Y>
\t\t\t\t<Label><X>10</X><Y>0</Y></Label>
\t\t\t\t<PublicFlag>false</PublicFlag>
\t\t\t\t<PresentationFlag>true</PresentationFlag>
\t\t\t\t<ShowLabel>false</ShowLabel>
\t\t\t\t<DrawMode>SHAPE_DRAW_2D3D</DrawMode>
\t\t\t\t<EmbeddedIcon>false</EmbeddedIcon>
\t\t\t\t<Z>0</Z><Rotation>0.0</Rotation><Color>-10193781</Color>
\t\t\t\t<Text><![CDATA[After Run, use AnyLogic's built-in Pause / Resume / Stop controls. Stop and reopen this experiment to reset structural inputs. Outputs are labelled ad-hoc exploratory and not calibrated.]]></Text>
\t\t\t\t<Font><Name><![CDATA[SansSerif]]></Name><Size>12</Size><Style>0</Style></Font>
\t\t\t\t<Alignment>LEFT</Alignment>
\t\t\t</Text>
\t\t</Presentation>
\t\t<Parameters>
{params}
\t\t</Parameters>
\t\t<PresentationProperties>
\t\t\t<EnableZoomAndPanning>true</EnableZoomAndPanning>
\t\t\t<ExecutionMode>virtualTime</ExecutionMode>
\t\t\t<Title>HTXCheckpointSimulation : OperationalInteractive (exploratory)</Title>
\t\t\t<EnableDeveloperPanel>true</EnableDeveloperPanel>
\t\t\t<ShowDeveloperPanelOnStart>false</ShowDeveloperPanelOnStart>
\t\t\t<RealTimeScale>1.0</RealTimeScale>
\t\t</PresentationProperties>
\t\t<ModelTimeProperties>
\t\t\t<StopOption>Never</StopOption>
\t\t\t<InitialDate>1785024000000</InitialDate>
\t\t\t<InitialTime>0.0</InitialTime>
\t\t\t<FinalDate>1787702400000</FinalDate>
\t\t\t<FinalTime>300.0</FinalTime>
\t\t</ModelTimeProperties>
\t\t<BypassInitialScreen>false</BypassInitialScreen>
\t</SimulationExperiment>"""


def _java_literal(value_type: str, raw_value: str) -> str:
    value = raw_value.strip()
    if value_type == "String":
        return json.dumps(value)
    if value_type == "int":
        return str(int(value))
    if value_type == "long":
        return f"{int(value)}L"
    if value_type == "double":
        if value == "":
            return "0.0"
        float(value)
        if "." not in value and "e" not in value.lower():
            value += ".0"
        return value
    raise RuntimeError(f"Unsupported pilot parameter type: {value_type}")


def _indexed_expression(values: list[str]) -> str:
    if not values:
        raise RuntimeError("Cannot generate an empty pilot expression")
    if len(set(values)) == 1:
        return values[0]
    parts = [
        f"index == {index} ? {value}"
        for index, value in enumerate(values[:-1])
    ]
    return "\n\t: ".join(parts + [values[-1]])


def _pilot_parameter_expressions(
    rows: list[dict[str, str]],
) -> dict[str, str]:
    defaults = {
        name: default
        for name, _, default in MODEL_PARAMETERS
    }
    seed_offsets = {
        "arrival_seed": 1,
        "service_seed": 2,
        "routing_seed": 3,
        "tie_seed": 4,
    }
    expressions: dict[str, str] = {}
    for name, value_type, _ in MODEL_PARAMETERS:
        values: list[str] = []
        for row in rows:
            if name == "output_collection_id":
                raw = PILOT_OUTPUT_COLLECTION
                value = _java_literal(value_type, raw)
            elif name == "config_sha256":
                value = _java_literal(
                    value_type,
                    scenario_config_sha256(row),
                )
            elif name in seed_offsets:
                value = _java_literal(
                    value_type,
                    str(int(row["master_seed"]) + seed_offsets[name]),
                )
            elif name == "replication_id":
                value = "0"
            elif name in {"model_version", "start_state"}:
                value = defaults[name]
            elif name in row:
                value = _java_literal(value_type, row[name])
            else:
                raise RuntimeError(
                    f"No OperationalPilot mapping for parameter {name}"
                )
            values.append(value)
        expressions[name] = _indexed_expression(values)
    return expressions


def _confirmatory_parameter_expressions(
    rows: list[dict[str, str]],
    seed_rows: list[dict[str, str]],
) -> dict[str, str]:
    defaults = {
        name: default
        for name, _, default in MODEL_PARAMETERS
    }
    first_seed_by_input = {
        row["input_sample_id"]: row
        for row in seed_rows
        if row["replication_id"] == "1"
    }
    expressions: dict[str, str] = {}
    for name, value_type, _ in MODEL_PARAMETERS:
        values: list[str] = []
        for row in rows:
            if name == "output_collection_id":
                value = _java_literal(
                    value_type,
                    CONFIRMATORY_OUTPUT_COLLECTION,
                )
            elif name == "config_sha256":
                value = _java_literal(
                    value_type,
                    scenario_config_sha256(row),
                )
            elif name in {
                "arrival_seed",
                "service_seed",
                "routing_seed",
                "tie_seed",
            }:
                seed = first_seed_by_input.get(row["input_sample_id"])
                if seed is None:
                    raise RuntimeError(
                        "confirmatory input sample has no replication-1 seed"
                    )
                value = _java_literal(value_type, seed[name])
            elif name == "replication_id":
                value = "0"
            elif name in {"model_version", "start_state"}:
                value = defaults[name]
            elif name in row:
                value = _java_literal(value_type, row[name])
            else:
                raise RuntimeError(
                    "No CapacityRobustnessConfirmatory mapping for "
                    f"parameter {name}"
                )
            values.append(value)
        expressions[name] = _indexed_expression(values)
    return expressions


def _pilot_experiment_xml(
    model_id: str,
    experiment_id: str,
    timer_id: str,
    rows: list[dict[str, str]],
) -> str:
    before = html.escape(_pilot_before_run(rows), quote=False)
    after = html.escape(AFTER_RUN, quote=False)
    expressions = _pilot_parameter_expressions(rows)
    freeform_values: list[str] = []
    range_values: list[str] = []
    for index, (name, _, _) in enumerate(MODEL_PARAMETERS):
        parameter_id = 1785163110001 + 10 * index
        expression = expressions[name]
        freeform_values.append(
            f"""\t\t<FreeformParamValue>
\t\t\t<Id>{parameter_id}</Id>
\t\t\t<Expression Class="CodeValue">
\t\t\t\t<Code><![CDATA[{expression}]]></Code>
\t\t\t</Expression>
\t\t</FreeformParamValue>"""
        )
        range_values.append(
            f"""\t\t<RangeVariationParamValue>
\t\t\t<Id>{parameter_id}</Id>
\t\t\t<Type><![CDATA[FIXED]]></Type>
\t\t</RangeVariationParamValue>"""
        )
    freeform = "\n".join(freeform_values)
    ranges = "\n".join(range_values)
    return f"""\
\t<ParamVariationExperiment ActiveObjectClassId="{model_id}">
\t\t<Id>{experiment_id}</Id>
\t\t<Name><![CDATA[{PILOT_EXPERIMENT_NAME}]]></Name>
\t\t<CommandLineArguments/>
\t\t<MaximumMemory>512</MaximumMemory>
\t\t<RandomNumberGenerationType>fixedSeed</RandomNumberGenerationType>
\t\t<CustomGeneratorCode>new Random()</CustomGeneratorCode>
\t\t<BeforeSimulationRunCode>{before}</BeforeSimulationRunCode>
\t\t<AfterSimulationRunCode>{after}</AfterSimulationRunCode>
\t\t<SeedValue>1</SeedValue>
\t\t<SelectionModeForSimultaneousEvents>LIFO</SelectionModeForSimultaneousEvents>
\t\t<VmArgs/>
\t\t<LoadRootFromSnapshot>false</LoadRootFromSnapshot>
\t\t<Variables>
\t\t\t<Variable Class="PlainVariable">
\t\t\t\t<Id>{timer_id}</Id>
\t\t\t\t<Name><![CDATA[operational_pilot_auto_start_timer]]></Name>
\t\t\t\t<X>40</X><Y>120</Y>
\t\t\t\t<Label><X>10</X><Y>0</Y></Label>
\t\t\t\t<PublicFlag>false</PublicFlag>
\t\t\t\t<PresentationFlag>false</PresentationFlag>
\t\t\t\t<ShowLabel>false</ShowLabel>
\t\t\t\t<Properties SaveInSnapshot="false"
                Constant="false"
                AccessType="private"
                StaticVariable="false">
\t\t\t\t\t<Type><![CDATA[javax.swing.Timer]]></Type>
\t\t\t\t\t<InitialValue Class="CodeValue">
\t\t\t\t\t\t<Code><![CDATA[new javax.swing.Timer(300, event -> {{ ((javax.swing.Timer) event.getSource()).stop(); OperationalPilot.this.run(); }}) {{{{ setRepeats(false); start(); }}}}]]></Code>
\t\t\t\t\t</InitialValue>
\t\t\t\t</Properties>
\t\t\t</Variable>
\t\t</Variables>
\t\t<AllowParallelEvaluations>false</AllowParallelEvaluations>
\t\t<UseFreeformParameters>true</UseFreeformParameters>
\t\t<NumberOfRuns>{len(rows)}</NumberOfRuns>
{freeform}
{ranges}
\t\t<ModelTimeProperties>
\t\t\t<StopOption>Never</StopOption>
\t\t\t<InitialDate>1785024000000</InitialDate>
\t\t\t<InitialTime>0.0</InitialTime>
\t\t\t<FinalDate>1787702400000</FinalDate>
\t\t\t<FinalTime>300.0</FinalTime>
\t\t</ModelTimeProperties>
\t\t<PresentationProperties>
\t\t\t<EnableZoomAndPanning>true</EnableZoomAndPanning>
\t\t\t<Title>HTXCheckpointSimulation : OperationalPilot</Title>
\t\t\t<EnableDeveloperPanel>true</EnableDeveloperPanel>
\t\t\t<ShowDeveloperPanelOnStart>false</ShowDeveloperPanelOnStart>
\t\t</PresentationProperties>
\t\t<ReplicationsProperties>
\t\t\t<UseReplication>true</UseReplication>
\t\t\t<FixedReplicationsNumber>true</FixedReplicationsNumber>
\t\t\t<ReplicationPerIteration>10</ReplicationPerIteration>
\t\t\t<MinimumReplication>10</MinimumReplication>
\t\t\t<MaximumReplication>10</MaximumReplication>
\t\t\t<ConfidenceLevel>LEVEL_95</ConfidenceLevel>
\t\t\t<ErrorPercent>0.05</ErrorPercent>
\t\t\t<ExpressionForConfidenceComputation>0</ExpressionForConfidenceComputation>
\t\t</ReplicationsProperties>
\t</ParamVariationExperiment>"""


def _confirmatory_experiment_xml(
    model_id: str,
    experiment_id: str,
    timer_id: str,
    rows: list[dict[str, str]],
    seed_rows: list[dict[str, str]],
) -> str:
    before = html.escape(
        _confirmatory_before_run(rows, seed_rows),
        quote=False,
    )
    after = html.escape(AFTER_RUN, quote=False)
    expressions = _confirmatory_parameter_expressions(rows, seed_rows)
    freeform_values: list[str] = []
    range_values: list[str] = []
    for index, (name, _, _) in enumerate(MODEL_PARAMETERS):
        parameter_id = 1785163110001 + 10 * index
        expression = expressions[name]
        freeform_values.append(
            f"""\t\t<FreeformParamValue>
\t\t\t<Id>{parameter_id}</Id>
\t\t\t<Expression Class="CodeValue">
\t\t\t\t<Code><![CDATA[{expression}]]></Code>
\t\t\t</Expression>
\t\t</FreeformParamValue>"""
        )
        range_values.append(
            f"""\t\t<RangeVariationParamValue>
\t\t\t<Id>{parameter_id}</Id>
\t\t\t<Type><![CDATA[FIXED]]></Type>
\t\t</RangeVariationParamValue>"""
        )
    freeform = "\n".join(freeform_values)
    ranges = "\n".join(range_values)
    return f"""\
\t<ParamVariationExperiment ActiveObjectClassId="{model_id}">
\t\t<Id>{experiment_id}</Id>
\t\t<Name><![CDATA[{CONFIRMATORY_EXPERIMENT_NAME}]]></Name>
\t\t<CommandLineArguments/>
\t\t<MaximumMemory>512</MaximumMemory>
\t\t<RandomNumberGenerationType>fixedSeed</RandomNumberGenerationType>
\t\t<CustomGeneratorCode>new Random()</CustomGeneratorCode>
\t\t<BeforeSimulationRunCode>{before}</BeforeSimulationRunCode>
\t\t<AfterSimulationRunCode>{after}</AfterSimulationRunCode>
\t\t<SeedValue>1</SeedValue>
\t\t<SelectionModeForSimultaneousEvents>LIFO</SelectionModeForSimultaneousEvents>
\t\t<VmArgs/>
\t\t<LoadRootFromSnapshot>false</LoadRootFromSnapshot>
\t\t<Variables>
\t\t\t<Variable Class="PlainVariable">
\t\t\t\t<Id>{timer_id}</Id>
\t\t\t\t<Name><![CDATA[confirmatory_auto_start_timer]]></Name>
\t\t\t\t<X>40</X><Y>120</Y>
\t\t\t\t<Label><X>10</X><Y>0</Y></Label>
\t\t\t\t<PublicFlag>false</PublicFlag>
\t\t\t\t<PresentationFlag>false</PresentationFlag>
\t\t\t\t<ShowLabel>false</ShowLabel>
\t\t\t\t<Properties SaveInSnapshot="false"
                Constant="false"
                AccessType="private"
                StaticVariable="false">
\t\t\t\t\t<Type><![CDATA[javax.swing.Timer]]></Type>
\t\t\t\t\t<InitialValue Class="CodeValue">
\t\t\t\t\t\t<Code><![CDATA[new javax.swing.Timer(300, event -> {{ ((javax.swing.Timer) event.getSource()).stop(); CapacityRobustnessConfirmatory.this.run(); }}) {{{{ setRepeats(false); start(); }}}}]]></Code>
\t\t\t\t\t</InitialValue>
\t\t\t\t</Properties>
\t\t\t</Variable>
\t\t</Variables>
\t\t<AllowParallelEvaluations>false</AllowParallelEvaluations>
\t\t<UseFreeformParameters>true</UseFreeformParameters>
\t\t<NumberOfRuns>{len(rows)}</NumberOfRuns>
{freeform}
{ranges}
\t\t<ModelTimeProperties>
\t\t\t<StopOption>Never</StopOption>
\t\t\t<InitialDate>1785024000000</InitialDate>
\t\t\t<InitialTime>0.0</InitialTime>
\t\t\t<FinalDate>1787702400000</FinalDate>
\t\t\t<FinalTime>300.0</FinalTime>
\t\t</ModelTimeProperties>
\t\t<PresentationProperties>
\t\t\t<EnableZoomAndPanning>true</EnableZoomAndPanning>
\t\t\t<Title>HTXCheckpointSimulation : CapacityRobustnessConfirmatory</Title>
\t\t\t<EnableDeveloperPanel>true</EnableDeveloperPanel>
\t\t\t<ShowDeveloperPanelOnStart>false</ShowDeveloperPanelOnStart>
\t\t</PresentationProperties>
\t\t<ReplicationsProperties>
\t\t\t<UseReplication>true</UseReplication>
\t\t\t<FixedReplicationsNumber>true</FixedReplicationsNumber>
\t\t\t<ReplicationPerIteration>50</ReplicationPerIteration>
\t\t\t<MinimumReplication>50</MinimumReplication>
\t\t\t<MaximumReplication>50</MaximumReplication>
\t\t\t<ConfidenceLevel>LEVEL_95</ConfidenceLevel>
\t\t\t<ErrorPercent>0.05</ErrorPercent>
\t\t\t<ExpressionForConfidenceComputation>0</ExpressionForConfidenceComputation>
\t\t</ReplicationsProperties>
\t</ParamVariationExperiment>"""


def _replace_operational_experiment(text: str, model_id: str) -> str:
    pattern = re.compile(
        rf"\t<SimulationExperiment ActiveObjectClassId=\"{model_id}\">.*?"
        r"\t</SimulationExperiment>",
        re.DOTALL,
    )
    match = pattern.search(text)
    if not match:
        raise RuntimeError("OperationalInteractive experiment block not found")
    old = match.group(0)
    experiment_id = re.search(r"<Id>(\d+)</Id>", old).group(1)
    text_id_match = re.search(r"<Presentation>.*?<Id>(\d+)</Id>", old, re.DOTALL)
    text_id = text_id_match.group(1) if text_id_match else "1785162602459"
    return text[: match.start()] + _experiment_xml(
        model_id, experiment_id, text_id
    ) + text[match.end() :]


def _replace_operational_pilot_experiment(
    text: str,
    model_id: str,
    rows: list[dict[str, str]],
) -> str:
    pattern = re.compile(
        rf"\t<ParamVariationExperiment ActiveObjectClassId=\"{model_id}\">.*?"
        r"\t</ParamVariationExperiment>",
        re.DOTALL,
    )
    matches = [
        match
        for match in pattern.finditer(text)
        if (
            re.search(r"<Name><!\[CDATA\[(.*?)\]\]></Name>", match.group(0))
            and re.search(
                r"<Name><!\[CDATA\[(.*?)\]\]></Name>",
                match.group(0),
            ).group(1)
            == PILOT_EXPERIMENT_NAME
        )
    ]
    if len(matches) != 1:
        raise RuntimeError(
            f"Expected one {PILOT_EXPERIMENT_NAME} experiment, "
            f"found {len(matches)}"
        )
    match = matches[0]
    old = match.group(0)
    experiment_id_match = re.search(r"<Id>(\d+)</Id>", old)
    if not experiment_id_match:
        raise RuntimeError("OperationalPilot experiment ID is missing")
    experiment_id = experiment_id_match.group(1)
    timer_match = re.search(
        r"<Variable Class=\"PlainVariable\">\s*"
        r"<Id>(\d+)</Id>\s*"
        r"<Name><!\[CDATA\[operational_pilot_auto_start_timer\]\]></Name>",
        old,
    )
    timer_id = (
        timer_match.group(1)
        if timer_match
        else str(int(experiment_id) + 2)
    )
    replacement = _pilot_experiment_xml(
        model_id,
        experiment_id,
        timer_id,
        rows,
    )
    return text[: match.start()] + replacement + text[match.end() :]


def _upsert_confirmatory_experiment(
    text: str,
    model_id: str,
    rows: list[dict[str, str]],
    seed_rows: list[dict[str, str]],
) -> str:
    pattern = re.compile(
        rf"\t<ParamVariationExperiment ActiveObjectClassId=\"{model_id}\">.*?"
        r"\t</ParamVariationExperiment>",
        re.DOTALL,
    )
    matches = [
        match
        for match in pattern.finditer(text)
        if (
            re.search(r"<Name><!\[CDATA\[(.*?)\]\]></Name>", match.group(0))
            and re.search(
                r"<Name><!\[CDATA\[(.*?)\]\]></Name>",
                match.group(0),
            ).group(1)
            == CONFIRMATORY_EXPERIMENT_NAME
        )
    ]
    if len(matches) > 1:
        raise RuntimeError(
            f"Expected at most one {CONFIRMATORY_EXPERIMENT_NAME}; "
            f"found {len(matches)}"
        )
    if matches:
        match = matches[0]
        old = match.group(0)
        experiment_match = re.search(r"<Id>(\d+)</Id>", old)
        timer_match = re.search(
            r"<Variable Class=\"PlainVariable\">\s*"
            r"<Id>(\d+)</Id>\s*"
            r"<Name><!\[CDATA\[confirmatory_auto_start_timer\]\]></Name>",
            old,
        )
        if not experiment_match:
            raise RuntimeError("confirmatory experiment ID is missing")
        experiment_id = experiment_match.group(1)
        timer_id = (
            timer_match.group(1)
            if timer_match
            else str(int(experiment_id) + 1)
        )
        replacement = _confirmatory_experiment_xml(
            model_id,
            experiment_id,
            timer_id,
            rows,
            seed_rows,
        )
        return text[: match.start()] + replacement + text[match.end() :]

    for item_id in (CONFIRMATORY_EXPERIMENT_ID, CONFIRMATORY_TIMER_ID):
        if re.search(rf"<Id>{item_id}</Id>", text):
            raise RuntimeError(f"confirmatory insertion ID {item_id} is in use")
    marker = "</Experiments>"
    if text.count(marker) != 1:
        raise RuntimeError("split experiment root is not canonical")
    block = _confirmatory_experiment_xml(
        model_id,
        CONFIRMATORY_EXPERIMENT_ID,
        CONFIRMATORY_TIMER_ID,
        rows,
        seed_rows,
    )
    return text.replace(marker, block + "\n" + marker, 1)


def _xml_root_without_declaration(path: Path) -> str:
    return re.sub(
        r"\A<\?xml[^>]*\?>\s*",
        "",
        _read(path),
        count=1,
    ).strip()


def _balanced_element_span(text: str, tag: str, start: int) -> tuple[int, int]:
    token_pattern = re.compile(
        rf"<{re.escape(tag)}(?:\s[^>]*)?>|</{re.escape(tag)}>"
    )
    depth = 0
    for token in token_pattern.finditer(text, start):
        if token.start() < start:
            continue
        if token.group(0).startswith(f"</{tag}"):
            depth -= 1
            if depth == 0:
                return start, token.end()
        elif not token.group(0).endswith("/>"):
            depth += 1
    raise RuntimeError(f"Cannot find balanced {tag} element")


def _named_top_level_span(
    text: str,
    *,
    tag: str,
    name: str,
) -> tuple[int, int]:
    for match in re.finditer(rf"<{re.escape(tag)}(?:\s[^>]*)?>", text):
        start, end = _balanced_element_span(text, tag, match.start())
        opening_region = text[start : min(end, start + 800)]
        nested_start = opening_region.find(f"<{tag}", len(match.group(0)))
        direct_region = (
            opening_region
            if nested_start < 0
            else opening_region[:nested_start]
        )
        if f"<Name><![CDATA[{name}]]></Name>" in direct_region:
            return start, end
    raise RuntimeError(f"Cannot locate {tag} named {name}")


def _indent_xml(block: str, prefix: str) -> str:
    return "\n".join(
        prefix + line if line else line
        for line in block.splitlines()
    )


def _inline_operational_model() -> str:
    model = _xml_root_without_declaration(
        OP_MODEL / "AOC.OperationalCheckpointModel.xml"
    )
    variables = _xml_root_without_declaration(OP_MODEL / "Variables.xml")
    connectors = _xml_root_without_declaration(OP_MODEL / "Connectors.xml")
    events = _xml_root_without_declaration(OP_MODEL / "Code" / "Events.xml")
    embedded = _xml_root_without_declaration(OP_MODEL / "EmbeddedObjects.xml")
    events, count = re.subn(
        r"<Action(?:\s[^>]*)?/>",
        f"<Action><![CDATA[{CUTOFF_ACTION}]]></Action>",
        events,
        count=1,
    )
    if count != 1:
        raise RuntimeError("Operational cutoff action placeholder is missing")
    replacements = {
        '<Variables xmlns:al="http://anylogic.com"/>': (
            variables + "\n" + connectors
        ),
        '<Events xmlns:al="http://anylogic.com"/>': events,
        '<EmbeddedObjects xmlns:al="http://anylogic.com"/>': embedded,
    }
    for marker, replacement in replacements.items():
        if model.count(marker) != 1:
            raise RuntimeError(f"Expected one split marker {marker}")
        model = model.replace(marker, replacement, 1)
    return model


def _sync_single_file(
    *,
    model_id: str,
) -> None:
    if not SINGLE_ALP.is_file():
        raise RuntimeError(f"Single-file launcher is missing: {SINGLE_ALP}")
    text = _read(SINGLE_ALP)
    class_start, class_end = _named_top_level_span(
        text,
        tag="ActiveObjectClass",
        name="OperationalCheckpointModel",
    )
    line_start = text.rfind("\n", 0, class_start) + 1
    if text[line_start:class_start].strip():
        raise RuntimeError(
            "OperationalCheckpointModel must begin on its own XML line"
        )
    class_start = line_start
    inline_model = _indent_xml(_inline_operational_model(), "\t\t")
    text = text[:class_start] + inline_model + text[class_end:]

    experiment_match = re.search(r"<Experiments>", text)
    if not experiment_match:
        raise RuntimeError("single-file launcher has no Experiments block")
    experiment_start, experiment_end = _balanced_element_span(
        text,
        "Experiments",
        experiment_match.start(),
    )
    experiment_line_start = text.rfind("\n", 0, experiment_start) + 1
    prefix = text[experiment_line_start:experiment_start]
    if not prefix or prefix.strip():
        raise RuntimeError("single-file Experiments must begin on its own line")
    inline_experiments = _indent_xml(
        _xml_root_without_declaration(EXPERIMENTS),
        prefix,
    )
    text = (
        text[:experiment_line_start]
        + inline_experiments
        + text[experiment_end:]
    )
    _write(SINGLE_ALP, text)


def generate() -> None:
    _, scenario_rows = _load_scenarios()
    confirmatory_rows, confirmatory_seed_rows, confirmatory_validation = (
        _load_confirmatory_inputs()
    )
    traveller_aoc = OP_TRAVELLER / "AOC.OperationalTraveller.xml"
    model_aoc = OP_MODEL / "AOC.OperationalCheckpointModel.xml"
    if not traveller_aoc.is_file() or not model_aoc.is_file():
        raise RuntimeError(
            "Create OperationalTraveller and OperationalCheckpointModel in "
            "the AnyLogic GUI before running this generator"
        )
    op_traveller_id = _class_id(traveller_aoc)
    op_traveller_generic_id = _generic_parameter_id(traveller_aoc)
    op_model_id = _class_id(model_aoc)
    _ensure_split_references(
        traveller_aoc,
        events=False,
        embedded_objects=False,
    )
    _ensure_split_references(
        model_aoc,
        events=True,
        embedded_objects=True,
    )
    _write(model_aoc, _decorate_model_aoc(_read(model_aoc)))

    _write(
        OP_TRAVELLER / "Variables.xml",
        _variables_xml(
            TRAVELLER_VARIABLES,
            [],
            plain_base=1785163200001,
            parameter_base=1785163210001,
        ),
    )
    _write(
        OP_MODEL / "Variables.xml",
        _variables_xml(
            MODEL_VARIABLES,
            MODEL_PARAMETERS,
            plain_base=1785163100001,
            parameter_base=1785163110001,
            plain_positions=MODEL_VARIABLE_POSITIONS,
        ),
    )
    _write(
        OP_MODEL / "EmbeddedObjects.xml",
        _transform_embedded_objects(op_traveller_generic_id),
    )

    _write(OP_MODEL / "Connectors.xml", _transform_connectors())

    event_xml = _read(CHECKPOINT / "Code" / "Events.xml")
    for old, new in {
        "178509109": "178516314",
    }.items():
        event_xml = event_xml.replace(old, new)
    _write(OP_MODEL / "Code" / "Events.xml", event_xml)
    event_java = f"""\
void arrivalCutoff()
{{/*ALCODESTART::1785163143775*/
{CUTOFF_ACTION}
/*ALCODEEND*/}}
"""
    _write(OP_MODEL / "Code" / "Events.java", event_java)

    experiment_text = _replace_operational_experiment(_read(EXPERIMENTS), op_model_id)
    experiment_text = _replace_operational_pilot_experiment(
        experiment_text,
        op_model_id,
        scenario_rows,
    )
    experiment_text = _upsert_confirmatory_experiment(
        experiment_text,
        op_model_id,
        confirmatory_rows,
        confirmatory_seed_rows,
    )
    _write(EXPERIMENTS, experiment_text)
    _sync_single_file(model_id=op_model_id)

    print(f"OperationalTraveller class ID: {op_traveller_id}")
    print(f"OperationalCheckpointModel class ID: {op_model_id}")
    print(
        f"OperationalPilot: {len(scenario_rows)} scenarios x "
        "10 replications (serial)"
    )
    print(
        "CapacityRobustnessConfirmatory: "
        f"{len(confirmatory_rows)} cells x 50 replications "
        f"({confirmatory_validation['total_run_cap']} capped runs, serial)"
    )
    print("Generated operational AnyLogic split fragments and single-file launcher")


if __name__ == "__main__":
    generate()
