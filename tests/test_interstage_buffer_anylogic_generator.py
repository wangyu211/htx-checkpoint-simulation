from __future__ import annotations

import json
import re
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from src.analysis.analyse_interstage_buffer import REQUIRED_FIELDS
from src.analysis.interstage_buffer_design import (
    BLOCKING_POLICY,
    BUFFER_LEVELS,
    MODEL_VERSION,
    STUDY_ID,
    load_interstage_buffer_scenario_rows,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODEL_ROOT = (
    PROJECT_ROOT
    / "simulation"
    / "anylogic"
    / "HTXCheckpointSimulation"
)
ALP_ROOT = MODEL_ROOT / "_alp"
SPILLBACK_MODEL = ALP_ROOT / "Agents" / "SpillbackCheckpointModel"
SPILLBACK_AOC = SPILLBACK_MODEL / "AOC.SpillbackCheckpointModel.xml"
SPILLBACK_VARIABLES = SPILLBACK_MODEL / "Variables.xml"
SPILLBACK_EMBEDDED = SPILLBACK_MODEL / "EmbeddedObjects.xml"
SPILLBACK_CONNECTORS = SPILLBACK_MODEL / "Connectors.xml"
SPILLBACK_EVENTS = SPILLBACK_MODEL / "Code" / "Events.xml"
SPILLBACK_EVENT_CODE = SPILLBACK_MODEL / "Code" / "Events.java"
SPILLBACK_ADDITIONAL_CLASS = (
    SPILLBACK_MODEL / "Code" / "AdditionalClass.java"
)
SPILLBACK_ADDITIONAL_CLASS_CODE = (
    SPILLBACK_MODEL / "Code" / "AdditionalClassCode.java"
)
EXPERIMENTS = ALP_ROOT / "Experiments.xml"
SINGLE_ALP = (
    PROJECT_ROOT
    / "simulation"
    / "anylogic"
    / "HTXCheckpointSimulationCLI"
    / "HTXCheckpointSimulationCLI.alp"
)

EXPERIMENT_NAME = "InterstageBufferSpillbackSensitivity"
OUTPUT_COLLECTION_ID = "interstage_buffer"


def _named_child(
    root: ET.Element,
    tag: str,
    name: str,
) -> ET.Element:
    matches = [
        item
        for item in root.findall(tag)
        if item.findtext("Name", "").strip() == name
    ]
    if len(matches) != 1:
        raise AssertionError(
            f"Expected one {tag} named {name}, found {len(matches)}"
        )
    return matches[0]


def _variables(
    root: ET.Element,
    variable_class: str,
) -> dict[str, ET.Element]:
    return {
        item.findtext("Name", "").strip(): item
        for item in root.findall("Variable")
        if item.attrib.get("Class") == variable_class
    }


def _default_value(variable: ET.Element) -> str:
    return variable.findtext(
        "Properties/DefaultValue/Code",
        "",
    ).strip()


def _embedded_objects(root: ET.Element) -> dict[str, ET.Element]:
    return {
        item.findtext("Name", "").strip(): item
        for item in root.findall("EmbeddedObject")
    }


def _embedded_class(item: ET.Element) -> str:
    return item.findtext("ActiveObjectClass/ClassName", "").strip()


def _parameter_code(item: ET.Element, name: str) -> str:
    matches = [
        parameter
        for parameter in item.findall("Parameters/Parameter")
        if parameter.findtext("Name", "").strip() == name
    ]
    if len(matches) != 1:
        raise AssertionError(
            f"{item.findtext('Name')}: expected one parameter {name}, "
            f"found {len(matches)}"
        )
    return matches[0].findtext("Value/Code", "").strip()


def _connector_edges(root: ET.Element) -> list[tuple[str, str]]:
    return [
        (
            item.findtext(
                "SourceEmbeddedObjectReference/ItemName",
                "",
            ).strip(),
            item.findtext(
                "TargetEmbeddedObjectReference/ItemName",
                "",
            ).strip(),
        )
        for item in root.findall("Connector")
    ]


def _freeform_parameter_expressions(
    experiment: ET.Element,
) -> dict[str, str]:
    return {
        item.findtext("Id", "").strip(): item.findtext(
            "Expression/Code",
            "",
        ).strip()
        for item in experiment.findall("FreeformParamValue")
    }


def _fixed_parameter_ids(experiment: ET.Element) -> set[str]:
    return {
        item.findtext("Id", "").strip()
        for item in experiment.findall("RangeVariationParamValue")
        if item.findtext("Type", "").strip() == "FIXED"
    }


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


def _java_csv_header(code: str, collection_name: str) -> list[str]:
    marker = f"{collection_name}.add("
    start = code.find(marker)
    if start < 0:
        raise AssertionError(f"Missing {collection_name}.add(...) header")
    start += len(marker)
    end = code.find(");", start)
    if end < 0:
        raise AssertionError(
            f"Unterminated {collection_name}.add(...) header"
        )
    string_literals = re.findall(
        r'"(?:\\.|[^"\\])*"',
        code[start:end],
    )
    if not string_literals:
        raise AssertionError(
            f"{collection_name}.add(...) contains no string literals"
        )
    return "".join(json.loads(value) for value in string_literals).split(",")


def _single_file_class(root: ET.Element, name: str) -> ET.Element:
    classes = root.find("Model/ActiveObjectClasses")
    if classes is None:
        raise AssertionError("single-file model has no ActiveObjectClasses")
    return _named_child(
        classes,
        "ActiveObjectClass",
        name,
    )


def _experiment(root: ET.Element, *, single_file: bool) -> ET.Element:
    experiments = (
        root.find("Model/Experiments")
        if single_file
        else root
    )
    if experiments is None:
        raise AssertionError("Experiments root is missing")
    return _named_child(
        experiments,
        "ParamVariationExperiment",
        EXPERIMENT_NAME,
    )


def _parameter_defaults(root: ET.Element) -> dict[str, str]:
    return {
        name: _default_value(item)
        for name, item in _variables(root, "Parameter").items()
    }


class InterstageBufferAnyLogicGeneratorTests(unittest.TestCase):
    def test_generator_materialises_complete_spillback_split_fragments(
        self,
    ) -> None:
        expected = {
            SPILLBACK_AOC,
            SPILLBACK_VARIABLES,
            SPILLBACK_EMBEDDED,
            SPILLBACK_CONNECTORS,
            SPILLBACK_EVENTS,
            SPILLBACK_EVENT_CODE,
            SPILLBACK_ADDITIONAL_CLASS,
            SPILLBACK_ADDITIONAL_CLASS_CODE,
        }
        missing = sorted(str(path) for path in expected if not path.is_file())
        self.assertEqual(
            missing,
            [],
            "generate_operational_anylogic.py must materialise every "
            "SpillbackCheckpointModel split fragment",
        )

        aoc = ET.parse(SPILLBACK_AOC).getroot()
        self.assertEqual(aoc.findtext("Name"), "SpillbackCheckpointModel")
        self.assertIsNotNone(aoc.find("Variables"))
        self.assertIsNotNone(aoc.find("Events"))
        self.assertIsNotNone(aoc.find("EmbeddedObjects"))

        parameters = _variables(
            ET.parse(SPILLBACK_VARIABLES).getroot(),
            "Parameter",
        )
        self.assertTrue(
            {
                "study_id",
                "interstage_buffer_capacity",
                "interstage_blocking_policy",
            }.issubset(parameters)
        )
        self.assertEqual(
            _default_value(parameters["study_id"]),
            json.dumps(STUDY_ID),
        )
        self.assertEqual(
            _default_value(parameters["interstage_buffer_capacity"]),
            "5000",
        )
        self.assertEqual(
            _default_value(parameters["interstage_blocking_policy"]),
            json.dumps(BLOCKING_POLICY),
        )

        additional_code = SPILLBACK_ADDITIONAL_CLASS_CODE.read_text(
            encoding="utf-8"
        )
        self.assertIn("INTERSTAGE_SPILLBACK_AUDIT_BEGIN", additional_code)
        self.assertIn("sha256CanonicalRows", additional_code)

    def test_spillback_flow_implements_explicit_blocking_after_service(
        self,
    ) -> None:
        embedded_root = ET.parse(SPILLBACK_EMBEDDED).getroot()
        embedded = _embedded_objects(embedded_root)
        expected_classes = {
            "travellerSource": "Source",
            "securityResources": "ResourcePool",
            "securitySeize": "Seize",
            "securityDelay": "Delay",
            "interstageSpace": "ResourcePool",
            "interstageSpaceSeize": "Seize",
            "securityRelease": "Release",
            "immigrationResources": "ResourcePool",
            "immigrationSeize": "Seize",
            "interstageSpaceRelease": "Release",
            "immigrationDelay": "Delay",
            "immigrationRelease": "Release",
            "checkpointSink": "Sink",
        }
        self.assertEqual(
            {name: _embedded_class(embedded[name]) for name in expected_classes},
            expected_classes,
        )

        self.assertEqual(
            _parameter_code(embedded["interstageSpace"], "capacity"),
            "interstage_buffer_capacity",
        )
        resource_bindings = {
            "securitySeize": "securityResources",
            "interstageSpaceSeize": "interstageSpace",
            "securityRelease": "securityResources",
            "immigrationSeize": "immigrationResources",
            "interstageSpaceRelease": "interstageSpace",
            "immigrationRelease": "immigrationResources",
        }
        for block_name, pool_name in resource_bindings.items():
            with self.subTest(block=block_name):
                self.assertEqual(
                    _parameter_code(embedded[block_name], "resourcePool"),
                    pool_name,
                )

        # The ordering is the BAS contract: Security cannot release its server
        # before a finite-space token is seized, and that token is retained
        # until an Immigration server is seized.
        self.assertEqual(
            _connector_edges(ET.parse(SPILLBACK_CONNECTORS).getroot()),
            [
                ("travellerSource", "securitySeize"),
                ("securitySeize", "securityDelay"),
                ("securityDelay", "interstageSpaceSeize"),
                ("interstageSpaceSeize", "securityRelease"),
                ("securityRelease", "immigrationSeize"),
                ("immigrationSeize", "interstageSpaceRelease"),
                ("interstageSpaceRelease", "immigrationDelay"),
                ("immigrationDelay", "immigrationRelease"),
                ("immigrationRelease", "checkpointSink"),
            ],
        )

        space_seize_code = (
            _parameter_code(embedded["interstageSpaceSeize"], "onEnter")
            + "\n"
            + _parameter_code(embedded["interstageSpaceSeize"], "onSeizeUnit")
        )
        self.assertIn(
            "interstage_occupied_count >= interstage_buffer_capacity",
            space_seize_code,
        )
        self.assertIn("security_blocked_count++", space_seize_code)
        self.assertIn("interstage_occupied_count++", space_seize_code)
        self.assertIn(
            "interstage occupancy exceeded declared capacity",
            space_seize_code,
        )
        space_release_code = _parameter_code(
            embedded["interstageSpaceRelease"],
            "onEnter",
        )
        self.assertIn("interstage_occupied_count--", space_release_code)
        self.assertIn(
            "interstage occupancy underflow before release",
            space_release_code,
        )

    def test_interstage_experiment_targets_spillback_class_and_exact_batch(
        self,
    ) -> None:
        spillback_id = ET.parse(SPILLBACK_AOC).getroot().findtext("Id")
        experiment = _experiment(
            ET.parse(EXPERIMENTS).getroot(),
            single_file=False,
        )
        rows = load_interstage_buffer_scenario_rows()

        self.assertEqual(len(rows), 8)
        self.assertEqual(
            experiment.attrib.get("ActiveObjectClassId"),
            spillback_id,
        )
        self.assertEqual(experiment.findtext("NumberOfRuns"), "8")
        self.assertEqual(
            experiment.findtext("AllowParallelEvaluations"),
            "false",
        )
        self.assertEqual(
            experiment.findtext("UseFreeformParameters"),
            "true",
        )
        for field in (
            "ReplicationPerIteration",
            "MinimumReplication",
            "MaximumReplication",
        ):
            self.assertEqual(
                experiment.findtext(f"ReplicationsProperties/{field}"),
                "50",
            )

        parameter_root = ET.parse(SPILLBACK_VARIABLES).getroot()
        parameters = _variables(parameter_root, "Parameter")
        parameter_ids = {
            name: item.findtext("Id", "").strip()
            for name, item in parameters.items()
        }
        freeform = _freeform_parameter_expressions(experiment)
        self.assertEqual(set(freeform), set(parameter_ids.values()))
        self.assertEqual(
            _fixed_parameter_ids(experiment),
            set(parameter_ids.values()),
        )

        capacities = _indexed_values(
            freeform[parameter_ids["interstage_buffer_capacity"]],
            len(rows),
        )
        self.assertEqual(
            capacities,
            [row["interstage_buffer_capacity"] for row in rows],
        )
        self.assertEqual(
            capacities,
            [
                str(level)
                for level in (*BUFFER_LEVELS, *BUFFER_LEVELS)
            ],
        )
        self.assertEqual(
            _indexed_values(
                freeform[parameter_ids["study_id"]],
                len(rows),
            ),
            [json.dumps(STUDY_ID)] * len(rows),
        )
        self.assertEqual(
            _indexed_values(
                freeform[parameter_ids["model_version"]],
                len(rows),
            ),
            [json.dumps(MODEL_VERSION)] * len(rows),
        )
        self.assertEqual(
            _indexed_values(
                freeform[parameter_ids["interstage_blocking_policy"]],
                len(rows),
            ),
            [json.dumps(BLOCKING_POLICY)] * len(rows),
        )

        before = experiment.findtext("BeforeSimulationRunCode", "")
        self.assertIn(
            f'"{OUTPUT_COLLECTION_ID}".equals'
            "( root.output_collection_id )",
            before,
        )
        self.assertIn(
            "InterstageBufferSpillbackSensitivity replication must be 1..50",
            before,
        )
        self.assertIn("getCurrentReplication()", before)

    def test_interstage_kpi_export_matches_analysis_contract(
        self,
    ) -> None:
        experiment = _experiment(
            ET.parse(EXPERIMENTS).getroot(),
            single_file=False,
        )
        after = experiment.findtext("AfterSimulationRunCode", "")
        kpi_fields = _java_csv_header(after, "kpis")

        self.assertEqual(len(kpi_fields), len(set(kpi_fields)))
        missing = sorted(set(REQUIRED_FIELDS) - set(kpi_fields))
        self.assertEqual(
            missing,
            [],
            "replication_kpis.csv must expose every field required by "
            "analyse_interstage_buffer.py",
        )
        for field in (
            "study_id",
            "input_draws_sha256",
            "normalized_event_payload_sha256",
            "interstage_buffer_peak_occupancy",
            "interstage_buffer_full_time_fraction",
            "time_weighted_mean_interstage_buffer_occupancy",
            "interstage_block_time_mean_seconds",
            "interstage_block_time_p95_seconds",
            "security_blocked_resource_seconds",
            "security_blocked_resource_fraction",
            "security_blocked_share_of_occupied",
            "total_wait_including_interstage_mean_seconds",
            "total_wait_including_interstage_p95_seconds",
        ):
            with self.subTest(field=field):
                self.assertIn(field, kpi_fields)

        entity_fields = _java_csv_header(after, "entities")
        self.assertTrue(
            {
                "security_processing_end_seconds",
                "interstage_block_start_seconds",
                "interstage_admitted_seconds",
                "interstage_block_seconds",
            }.issubset(entity_fields)
        )
        self.assertIn('resolve( "replication_kpis.csv" )', after)
        self.assertIn("sha256CanonicalRows", after)

    def test_normalized_replay_digest_excludes_runtime_resource_ids(
        self,
    ) -> None:
        embedded = SPILLBACK_EMBEDDED.read_text(encoding="utf-8")
        start = embedded.index("normalized_event_rows.add(")
        end = embedded.index(
            "if ( arrivals_closed && completed == admitted )",
            start,
        )
        normalized_payload = embedded[start:end]

        self.assertNotIn(
            "security_resource_id",
            normalized_payload,
        )
        self.assertNotIn(
            "immigration_resource_id",
            normalized_payload,
        )
        self.assertIn(
            "security_resource_id",
            embedded[:start],
            "runtime resource IDs should remain in the full entity audit log",
        )
        self.assertIn(
            "immigration_resource_id",
            embedded[:start],
            "runtime resource IDs should remain in the full entity audit log",
        )

    def test_single_file_contains_the_same_spillback_model_and_experiment(
        self,
    ) -> None:
        split_aoc = ET.parse(SPILLBACK_AOC).getroot()
        split_variables = ET.parse(SPILLBACK_VARIABLES).getroot()
        split_embedded = ET.parse(SPILLBACK_EMBEDDED).getroot()
        split_connectors = ET.parse(SPILLBACK_CONNECTORS).getroot()
        split_experiment = _experiment(
            ET.parse(EXPERIMENTS).getroot(),
            single_file=False,
        )

        single_root = ET.parse(SINGLE_ALP).getroot()
        single_model = _single_file_class(
            single_root,
            "SpillbackCheckpointModel",
        )
        single_experiment = _experiment(
            single_root,
            single_file=True,
        )

        self.assertEqual(
            single_model.findtext("Id"),
            split_aoc.findtext("Id"),
        )
        single_variables = single_model.find("Variables")
        single_embedded = single_model.find("EmbeddedObjects")
        single_connectors = single_model.find("Connectors")
        self.assertIsNotNone(single_variables)
        self.assertIsNotNone(single_embedded)
        self.assertIsNotNone(single_connectors)
        self.assertEqual(
            _parameter_defaults(single_variables),
            _parameter_defaults(split_variables),
        )
        self.assertEqual(
            {
                name: _embedded_class(item)
                for name, item in _embedded_objects(
                    single_embedded
                ).items()
            },
            {
                name: _embedded_class(item)
                for name, item in _embedded_objects(split_embedded).items()
            },
        )
        self.assertEqual(
            _connector_edges(single_connectors),
            _connector_edges(split_connectors),
        )

        self.assertEqual(
            single_experiment.attrib.get("ActiveObjectClassId"),
            split_experiment.attrib.get("ActiveObjectClassId"),
        )
        for field in (
            "NumberOfRuns",
            "AllowParallelEvaluations",
            "UseFreeformParameters",
        ):
            with self.subTest(field=field):
                self.assertEqual(
                    single_experiment.findtext(field),
                    split_experiment.findtext(field),
                )
        for field in (
            "BeforeSimulationRunCode",
            "AfterSimulationRunCode",
        ):
            with self.subTest(field=field):
                # Inlining the split Experiments element adds one XML
                # indentation level to every physical line.  Compare the
                # generated Java semantics rather than that harmless wrapper
                # indentation.
                single_code = re.sub(
                    r"\s+",
                    " ",
                    single_experiment.findtext(field, ""),
                ).strip()
                split_code = re.sub(
                    r"\s+",
                    " ",
                    split_experiment.findtext(field, ""),
                ).strip()
                self.assertEqual(single_code, split_code)
        for field in (
            "ReplicationPerIteration",
            "MinimumReplication",
            "MaximumReplication",
        ):
            self.assertEqual(
                single_experiment.findtext(
                    f"ReplicationsProperties/{field}"
                ),
                split_experiment.findtext(
                    f"ReplicationsProperties/{field}"
                ),
            )


if __name__ == "__main__":
    unittest.main()
