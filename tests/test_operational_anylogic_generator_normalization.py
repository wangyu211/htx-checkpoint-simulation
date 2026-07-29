import unittest
from pathlib import Path

from scripts.generate_operational_anylogic import (
    CANONICAL_EXPERIMENT_ORDER,
    CANONICAL_EXPERIMENT_TAGS,
    _balanced_element_span,
    _canonicalize_cli_markup_line_suffixes,
    _canonicalize_experiment_order,
    _named_top_level_span,
    _strip_operational_traveller_container_links,
)


REPO = Path(__file__).resolve().parents[1]
SPLIT_ROOT = (
    REPO
    / "simulation"
    / "anylogic"
    / "HTXCheckpointSimulation"
    / "_alp"
)
SINGLE_ALP = (
    REPO
    / "simulation"
    / "anylogic"
    / "HTXCheckpointSimulationCLI"
    / "HTXCheckpointSimulationCLI.alp"
)


def _experiment_block(name: str, item_id: int) -> str:
    tag = CANONICAL_EXPERIMENT_TAGS[name]
    return (
        f"<{tag} ActiveObjectClassId=\"123\">\n"
        f"\t\t<Id>{item_id}</Id>\n"
        f"\t\t<Name><![CDATA[{name}]]></Name>\n"
        "\t\t<BeforeSimulationRunCode><![CDATA["
        "if (a < b && c > d) keepFormatting();"
        "]]></BeforeSimulationRunCode>\n"
        f"\t</{tag}>"
    )


def _experiment_document(names: tuple[str, ...]) -> str:
    blocks = [
        _experiment_block(
            name,
            1000 + CANONICAL_EXPERIMENT_ORDER.index(name),
        )
        for name in names
    ]
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<Experiments>\n\t"
        + "\n\t".join(blocks)
        + "\n</Experiments>\n"
    )


def _known_container_links() -> str:
    return """\
\t<ContainerLinks>
\t\t<ContainerLink>
\t\t\t<Id>999</Id>
\t\t\t<Name><![CDATA[operationalCheckpointModel]]></Name>
\t\t\t<X>50</X>
\t\t\t<Y>-100</Y>
\t\t\t<ActiveObjectClass>
\t\t\t\t<PackageName>htx.checkpoint</PackageName>
\t\t\t\t<ClassName>OperationalCheckpointModel</ClassName>
\t\t\t</ActiveObjectClass>
\t\t</ContainerLink>
\t</ContainerLinks>
"""


class OperationalAnyLogicGeneratorNormalizationTests(unittest.TestCase):
    def test_known_gui_container_link_is_removed_without_other_changes(self):
        before = "<ActiveObjectClass>\n\t<AgentLinks/>\n"
        after = "\t<Presentation/>\n</ActiveObjectClass>\n"
        document = before + _known_container_links() + after

        self.assertEqual(
            _strip_operational_traveller_container_links(document),
            before + after,
        )

    def test_unknown_gui_container_link_fails_closed(self):
        document = _known_container_links().replace(
            "OperationalCheckpointModel",
            "AuthoredContainer",
        )

        with self.assertRaisesRegex(RuntimeError, "unexpected"):
            _strip_operational_traveller_container_links(document)

    def test_duplicate_container_links_fail_closed(self):
        document = _known_container_links() + _known_container_links()

        with self.assertRaisesRegex(RuntimeError, "at most one"):
            _strip_operational_traveller_container_links(document)

    def test_experiment_blocks_are_reordered_without_reformatting(self):
        reverse_order = tuple(reversed(CANONICAL_EXPERIMENT_ORDER))
        shuffled = _experiment_document(reverse_order)
        expected = _experiment_document(CANONICAL_EXPERIMENT_ORDER)

        self.assertEqual(_canonicalize_experiment_order(shuffled), expected)

    def test_missing_experiment_fails_closed(self):
        document = _experiment_document(CANONICAL_EXPERIMENT_ORDER[:-1])

        with self.assertRaisesRegex(RuntimeError, "missing top-level"):
            _canonicalize_experiment_order(document)

    def test_duplicate_experiment_fails_closed(self):
        document = _experiment_document(
            CANONICAL_EXPERIMENT_ORDER
            + (CANONICAL_EXPERIMENT_ORDER[0],)
        )

        with self.assertRaisesRegex(RuntimeError, "duplicate top-level"):
            _canonicalize_experiment_order(document)

    def test_unexpected_experiment_fails_closed(self):
        document = _experiment_document(CANONICAL_EXPERIMENT_ORDER).replace(
            "<![CDATA[PeakDurationSensitivity]]>",
            "<![CDATA[UnregisteredExperiment]]>",
            1,
        )

        with self.assertRaisesRegex(RuntimeError, "unexpected top-level"):
            _canonicalize_experiment_order(document)

    def test_cli_markup_suffix_cleanup_does_not_touch_cdata_body(self):
        document = (
            "<AnyLogicWorkspace>   \n"
            "\t<Type><![CDATA[int]]></Type>        \n"
            "\t<Code><![CDATA[\n"
            "<comparison >   \n"
            "javaCall();    \n"
            "]]></Code>\n"
            "\t<Inputs>\t\t\n"
            "</AnyLogicWorkspace>"
        )
        expected = (
            "<AnyLogicWorkspace>   \n"
            "\t<Type><![CDATA[int]]></Type>\n"
            "\t<Code><![CDATA[\n"
            "<comparison >   \n"
            "javaCall();    \n"
            "]]></Code>\n"
            "\t<Inputs>\n"
            "</AnyLogicWorkspace>\n"
        )

        self.assertEqual(
            _canonicalize_cli_markup_line_suffixes(document),
            expected,
        )

    def test_repository_split_and_single_file_are_canonical(self):
        split_experiments = (
            SPLIT_ROOT / "Experiments.xml"
        ).read_text(encoding="utf-8")
        self.assertEqual(
            _canonicalize_experiment_order(split_experiments),
            split_experiments,
        )
        split_traveller = (
            SPLIT_ROOT
            / "Agents"
            / "OperationalTraveller"
            / "AOC.OperationalTraveller.xml"
        ).read_text(encoding="utf-8")
        self.assertNotIn("<ContainerLinks>", split_traveller)

        single = SINGLE_ALP.read_text(encoding="utf-8")
        experiment_open = single.index("<Experiments>")
        experiment_start, experiment_end = _balanced_element_span(
            single,
            "Experiments",
            experiment_open,
        )
        inline_experiments = single[experiment_start:experiment_end]
        self.assertEqual(
            _canonicalize_experiment_order(inline_experiments),
            inline_experiments,
        )
        traveller_start, traveller_end = _named_top_level_span(
            single,
            tag="ActiveObjectClass",
            name="OperationalTraveller",
        )
        self.assertNotIn(
            "<ContainerLinks>",
            single[traveller_start:traveller_end],
        )


if __name__ == "__main__":
    unittest.main()
