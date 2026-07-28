"""Build the reviewer-facing Task 3 operational results dashboard.

The dashboard visualises Monte Carlo uncertainty conditional on the registered
assumption scenarios.  It must not be described as a calibrated HTX forecast.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Mapping, Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402

from src.analysis.validate_operational_contract import (  # noqa: E402
    DEFAULT_SCENARIOS,
    REFERENCE_SCENARIO_ID,
)
from src.analysis.validate_operational_results import (  # noqa: E402
    DEFAULT_RESULTS_DIR,
    validate_operational_results,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ANALYSIS_DIR = (
    PROJECT_ROOT / "results" / "analysis" / "operational"
)
DEFAULT_ESTIMATES = DEFAULT_ANALYSIS_DIR / "scenario_estimates.csv"
DEFAULT_CONTRASTS = DEFAULT_ANALYSIS_DIR / "scenario_contrasts.csv"
DEFAULT_PNG = DEFAULT_ANALYSIS_DIR / "operational_dashboard.png"
DEFAULT_SVG = DEFAULT_ANALYSIS_DIR / "operational_dashboard.svg"
DEFAULT_SUMMARY = DEFAULT_ANALYSIS_DIR / "README.md"

PRIMARY_METRIC = "total_queue_wait_p95_seconds"
CLEAR_METRIC = "cohort_clear_time_after_cutoff_seconds"
SECURITY_UTILIZATION = "security_utilization"
IMMIGRATION_UTILIZATION = "immigration_utilization"
BACKLOG_FRACTION = "cutoff_backlog_fraction"

FAMILY_ORDER = (
    "REFERENCE",
    "CAPACITY",
    "DEMAND",
    "SERVICE_CONTEXT",
    "AUTOMATION",
    "RISK",
)
FAMILY_COLORS = {
    "REFERENCE": "#333333",
    "CAPACITY": "#0072B2",
    "DEMAND": "#E69F00",
    "SERVICE_CONTEXT": "#CC79A7",
    "AUTOMATION": "#009E73",
    "RISK": "#D55E00",
}
FAMILY_LABELS = {
    "REFERENCE": "Reference",
    "CAPACITY": "Capacity",
    "DEMAND": "Demand",
    "SERVICE_CONTEXT": "Service context",
    "AUTOMATION": "Automation",
    "RISK": "Risk boundary",
}
SCENARIO_LABELS = {
    "REFERENCE_ASSUMPTION_SANDBOX_V1": "Reference sandbox",
    "CAPACITY_SECURITY_PLUS_4": "Security +4",
    "CAPACITY_IMMIGRATION_PLUS_3": "Immigration +3",
    "CAPACITY_BOTH_PLUS": "Both capacities +",
    "DEMAND_LOW_080": "Demand ×0.8",
    "DEMAND_HIGH_120": "Demand ×1.2",
    "SERVICE_SG_BUS_QR_10S": "SG QR context · 10 s",
    "SERVICE_SG_TRAIN_KIOSK_24S": "SG kiosk context · 24 s",
    "SERVICE_SG_TRAIN_MANUAL_45S": "SG manual context · 45 s",
    "AUTO_HTX_TRIAL_U50_M60": "HTX trial · 50% ×0.6",
    "AUTO_HTX_TRIAL_U100_M60": "HTX trial · 100% ×0.6",
    "AUTO_ICA_ROLLOUT_U50_M40": "ICA context · 50% ×0.4",
    "AUTO_ICA_ROLLOUT_U100_M40": "ICA context · 100% ×0.4",
    "RISK_EXTERNAL_P02_D900": "Risk bound · 2%, +900 s",
    "RISK_EXTERNAL_P02_D7200": "Risk bound · 2%, +7200 s",
}


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def _indexed_metric(
    rows: Sequence[Mapping[str, str]],
    metric: str,
) -> dict[str, Mapping[str, str]]:
    selected = {
        row["scenario_id"]: row
        for row in rows
        if row["metric"] == metric
    }
    if len(selected) != 15:
        raise ValueError(
            f"{metric}: expected 15 scenario estimates, found {len(selected)}"
        )
    return selected


def _float(row: Mapping[str, str], field: str) -> float:
    return float(row[field])


def _friendly_seconds(value: float) -> str:
    if value >= 3600:
        return f"{value / 3600:.1f} h"
    if value >= 120:
        return f"{value / 60:.1f} min"
    return f"{value:.1f} s"


def _plot_interval_panel(
    axis: plt.Axes,
    scenarios: Sequence[Mapping[str, str]],
    metric_rows: Mapping[str, Mapping[str, str]],
    *,
    title: str,
    xlabel: str,
) -> None:
    means = [
        _float(metric_rows[row["scenario_id"]], "mean")
        for row in scenarios
    ]
    lows = [
        _float(metric_rows[row["scenario_id"]], "ci_low")
        for row in scenarios
    ]
    highs = [
        _float(metric_rows[row["scenario_id"]], "ci_high")
        for row in scenarios
    ]
    positions = list(range(len(scenarios)))
    for position, scenario, mean, low, high in zip(
        positions,
        scenarios,
        means,
        lows,
        highs,
    ):
        color = FAMILY_COLORS[scenario["scenario_family"]]
        axis.errorbar(
            mean,
            position,
            xerr=[[mean - low], [high - mean]],
            fmt="o",
            color=color,
            ecolor=color,
            elinewidth=1.5,
            capsize=2.5,
            markersize=5.5,
            zorder=3,
        )
        axis.text(
            mean * 1.09,
            position,
            _friendly_seconds(mean),
            va="center",
            ha="left",
            fontsize=7.5,
            color="#252525",
        )
    reference = _float(
        metric_rows[REFERENCE_SCENARIO_ID],
        "mean",
    )
    axis.axvline(
        reference,
        color="#555555",
        linewidth=1,
        linestyle="--",
        alpha=0.65,
        zorder=1,
    )
    axis.set_xscale("log")
    axis.set_xlim(min(lows) * 0.65, max(highs) * 1.8)
    axis.set_title(title, loc="left", fontsize=11, fontweight="bold")
    axis.set_xlabel(xlabel, fontsize=9)
    axis.grid(axis="x", color="#D8D8D8", linewidth=0.7, alpha=0.8)
    axis.tick_params(axis="both", labelsize=8)
    axis.spines[["top", "right", "left"]].set_visible(False)


def build_dashboard(
    *,
    scenarios_path: Path = DEFAULT_SCENARIOS,
    estimates_path: Path = DEFAULT_ESTIMATES,
    contrasts_path: Path = DEFAULT_CONTRASTS,
    output_png: Path = DEFAULT_PNG,
    output_svg: Path = DEFAULT_SVG,
    output_summary: Path = DEFAULT_SUMMARY,
) -> dict[str, object]:
    validation = validate_operational_results(
        DEFAULT_RESULTS_DIR,
        scenarios_path=scenarios_path,
        require_pilot_coverage=True,
    )
    if validation["status"] != "PASS":
        raise ValueError(
            "Operational results failed strict validation: "
            + "; ".join(validation["errors"])
        )

    scenarios = _read_csv(scenarios_path)
    estimates = _read_csv(estimates_path)
    contrasts = _read_csv(contrasts_path)
    if len(scenarios) != 15:
        raise ValueError(f"Expected 15 scenarios, found {len(scenarios)}")
    scenario_ids = [row["scenario_id"] for row in scenarios]
    if set(scenario_ids) != set(SCENARIO_LABELS):
        raise ValueError("Dashboard labels do not cover the scenario registry")
    run_count = int(validation["run_count"])
    entity_count = int(validation["entity_count"])

    primary = _indexed_metric(estimates, PRIMARY_METRIC)
    clear = _indexed_metric(estimates, CLEAR_METRIC)
    security_util = _indexed_metric(estimates, SECURITY_UTILIZATION)
    immigration_util = _indexed_metric(
        estimates,
        IMMIGRATION_UTILIZATION,
    )
    backlog = _indexed_metric(estimates, BACKLOG_FRACTION)

    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "axes.facecolor": "#FFFFFF",
            "figure.facecolor": "#FFFFFF",
            "text.color": "#252525",
            "axes.labelcolor": "#252525",
            "xtick.color": "#4A4A4A",
            "ytick.color": "#252525",
        }
    )
    figure, axes = plt.subplots(
        1,
        3,
        figsize=(18, 10.5),
        sharey=True,
        gridspec_kw={"width_ratios": [1.1, 1.1, 0.9]},
    )
    positions = list(range(len(scenarios)))
    labels = [SCENARIO_LABELS[row["scenario_id"]] for row in scenarios]
    axes[0].set_yticks(positions, labels)
    axes[0].invert_yaxis()
    axes[0].tick_params(axis="y", length=0, labelsize=8.5)

    _plot_interval_panel(
        axes[0],
        scenarios,
        primary,
        title="A · Traveller queue-wait P95",
        xlabel="Mean of replication P95 (seconds, log scale)",
    )
    _plot_interval_panel(
        axes[1],
        scenarios,
        clear,
        title="B · Cohort clear time after cutoff",
        xlabel="Seconds after the 300 s arrival cutoff (log scale)",
    )
    axes[1].tick_params(axis="y", left=False)

    axis = axes[2]
    for position, scenario in zip(positions, scenarios):
        scenario_id = scenario["scenario_id"]
        security = _float(security_util[scenario_id], "mean")
        immigration = _float(immigration_util[scenario_id], "mean")
        color = FAMILY_COLORS[scenario["scenario_family"]]
        axis.plot(
            [security, immigration],
            [position - 0.12, position + 0.12],
            color="#B8B8B8",
            linewidth=1,
            zorder=1,
        )
        axis.scatter(
            security,
            position - 0.12,
            marker="o",
            s=28,
            color=color,
            zorder=3,
        )
        axis.scatter(
            immigration,
            position + 0.12,
            marker="s",
            s=26,
            color=color,
            zorder=3,
        )
    axis.axvline(
        0.85,
        color="#555555",
        linewidth=1,
        linestyle="--",
        alpha=0.65,
    )
    axis.set_xlim(0, 1.02)
    axis.set_title(
        "C · Full-drain resource utilization",
        loc="left",
        fontsize=11,
        fontweight="bold",
    )
    axis.set_xlabel("Utilization over run-to-drain horizon", fontsize=9)
    axis.grid(axis="x", color="#D8D8D8", linewidth=0.7, alpha=0.8)
    axis.tick_params(axis="both", labelsize=8)
    axis.tick_params(axis="y", left=False)
    axis.spines[["top", "right", "left"]].set_visible(False)
    axis.legend(
        handles=[
            Line2D(
                [0],
                [0],
                marker="o",
                color="none",
                markerfacecolor="#555555",
                markeredgecolor="#555555",
                label="Security",
            ),
            Line2D(
                [0],
                [0],
                marker="s",
                color="none",
                markerfacecolor="#555555",
                markeredgecolor="#555555",
                label="Immigration",
            ),
        ],
        loc="lower right",
        frameon=False,
        fontsize=8,
    )

    family_breaks: list[int] = []
    for index in range(1, len(scenarios)):
        if (
            scenarios[index]["scenario_family"]
            != scenarios[index - 1]["scenario_family"]
        ):
            family_breaks.append(index)
    for axis in axes:
        for index in family_breaks:
            axis.axhline(
                index - 0.5,
                color="#E8E8E8",
                linewidth=0.8,
                zorder=0,
            )

    family_handles = [
        Line2D(
            [0],
            [0],
            marker="o",
            color="none",
            markerfacecolor=FAMILY_COLORS[family],
            markeredgecolor=FAMILY_COLORS[family],
            label=FAMILY_LABELS[family],
        )
        for family in FAMILY_ORDER
    ]
    figure.legend(
        handles=family_handles,
        loc="upper center",
        bbox_to_anchor=(0.5, 0.91),
        ncol=6,
        frameon=False,
        fontsize=9,
    )
    reference_primary = _float(primary[REFERENCE_SCENARIO_ID], "mean")
    reference_clear = _float(clear[REFERENCE_SCENARIO_ID], "mean")
    reference_backlog = 100 * _float(
        backlog[REFERENCE_SCENARIO_ID],
        "mean",
    )
    reference_security = 100 * _float(
        security_util[REFERENCE_SCENARIO_ID],
        "mean",
    )
    reference_immigration = 100 * _float(
        immigration_util[REFERENCE_SCENARIO_ID],
        "mean",
    )
    figure.suptitle(
        "Task 3 operational assumption sandbox",
        x=0.03,
        y=0.975,
        ha="left",
        fontsize=18,
        fontweight="bold",
    )
    figure.text(
        0.03,
        0.94,
        (
            f"AnyLogic PLE · {len(scenarios)} scenarios × "
            f"{run_count // len(scenarios)} replications · "
            f"{entity_count:,} entity records · strict validation PASS"
        ),
        ha="left",
        fontsize=10,
        color="#4A4A4A",
    )
    figure.text(
        0.03,
        0.905,
        (
            f"Reference: queue-wait P95 {reference_primary:.1f} s · "
            f"clear after cutoff {reference_clear:.1f} s · "
            f"cutoff backlog {reference_backlog:.1f}% · "
            f"utilization {reference_security:.1f}% Security / "
            f"{reference_immigration:.1f}% Immigration"
        ),
        ha="left",
        fontsize=9.5,
        color="#252525",
    )
    figure.text(
        0.03,
        0.025,
        (
            "Dots are means across 10 replication-level KPIs; bars are 95% "
            "Student-t intervals. Scenario-specific random streams; "
            "unverified contrasts use independent Welch intervals. "
            "Comparative what-if only—not calibrated HTX performance."
        ),
        ha="left",
        fontsize=8.5,
        color="#4A4A4A",
    )
    figure.subplots_adjust(
        left=0.22,
        right=0.985,
        top=0.86,
        bottom=0.09,
        wspace=0.16,
    )
    output_png.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_png, dpi=220, bbox_inches="tight")
    figure.savefig(output_svg, bbox_inches="tight")
    plt.close(figure)

    contrast_primary = {
        row["scenario_id"]: row
        for row in contrasts
        if row["metric"] == PRIMARY_METRIC
    }
    reference = primary[REFERENCE_SCENARIO_ID]
    markdown = [
        "# Task 3 operational results",
        "",
        (
            f"**Status:** {run_count}/{run_count} AnyLogic runs and "
            f"{entity_count:,} entity records "
            "passed strict schema, lineage, seed, conservation, and full-drain "
            "validation."
        ),
        "",
        (
            "**Claim boundary:** Monte Carlo uncertainty conditional on the "
            "registered assumption scenarios. These results are not calibrated "
            "HTX performance, a site forecast, or a staffing recommendation."
        ),
        "",
        "![Operational scenario dashboard](operational_dashboard.png)",
        "",
        "## Reference sandbox",
        "",
        "| Metric | Mean across replications | 95% CI |",
        "|---|---:|---:|",
        (
            f"| Traveller queue-wait P95 | "
            f"{_float(reference, 'mean'):.2f} s | "
            f"{_float(reference, 'ci_low'):.2f}–"
            f"{_float(reference, 'ci_high'):.2f} s |"
        ),
        (
            f"| Clear time after 300 s cutoff | "
            f"{_float(clear[REFERENCE_SCENARIO_ID], 'mean'):.2f} s | "
            f"{_float(clear[REFERENCE_SCENARIO_ID], 'ci_low'):.2f}–"
            f"{_float(clear[REFERENCE_SCENARIO_ID], 'ci_high'):.2f} s |"
        ),
        (
            f"| Cutoff backlog fraction | "
            f"{reference_backlog:.2f}% | "
            f"{100 * _float(backlog[REFERENCE_SCENARIO_ID], 'ci_low'):.2f}–"
            f"{100 * _float(backlog[REFERENCE_SCENARIO_ID], 'ci_high'):.2f}% |"
        ),
        (
            f"| Security utilization | {reference_security:.2f}% | "
            f"{100 * _float(security_util[REFERENCE_SCENARIO_ID], 'ci_low'):.2f}–"
            f"{100 * _float(security_util[REFERENCE_SCENARIO_ID], 'ci_high'):.2f}% |"
        ),
        (
            f"| Immigration utilization | {reference_immigration:.2f}% | "
            f"{100 * _float(immigration_util[REFERENCE_SCENARIO_ID], 'ci_low'):.2f}–"
            f"{100 * _float(immigration_util[REFERENCE_SCENARIO_ID], 'ci_high'):.2f}% |"
        ),
        "",
        "## Primary scenario contrast",
        "",
        (
            "The primary estimand is the mean of the 10 replication-level "
            "traveller queue-wait P95 values. Differences below are "
            "scenario minus reference."
        ),
        "",
        "| Scenario | Difference | 95% CI | Interpretation |",
        "|---|---:|---:|---|",
    ]
    for scenario in scenarios[1:]:
        scenario_id = scenario["scenario_id"]
        row = contrast_primary[scenario_id]
        difference = _float(row, "difference_mean")
        low = _float(row, "ci_low")
        high = _float(row, "ci_high")
        if high < 0:
            interpretation = "Lower under this scenario"
        elif low > 0:
            interpretation = "Higher under this scenario"
        else:
            interpretation = "Direction not resolved at n=10"
        markdown.append(
            f"| {SCENARIO_LABELS[scenario_id]} | {difference:+.2f} s | "
            f"{low:+.2f} to {high:+.2f} s | {interpretation} |"
        )
    markdown.extend(
        [
            "",
            "## Reading the result",
            "",
            (
                "- The reference has little queueing under its own assumptions; "
                "fine-grained capacity or automation rankings are therefore "
                "uncertain with only 10 replications."
            ),
            (
                "- The dominant result is sensitivity to Immigration service "
                "time and demand. The 24 s and 45 s service contexts produce "
                "large queueing and drain-time increases; the 1.2× demand "
                "scenario also materially worsens the primary estimand."
            ),
            (
                "- The risk rows are external boundary stresses. Their long "
                "clear times reflect the deliberately pessimistic "
                "counter-held proxy and must not be presented as ICA practice."
            ),
            (
                "- Separate scenario seeds preserve the independent Welch "
                "analysis. `crn_alignment_status` remains `NOT_TESTED`; no "
                "paired-CRN precision claim is made."
            ),
            "",
            "## Reproduce",
            "",
            "```powershell",
            (
                r".\.venv\Scripts\python.exe -m "
                r"src.analysis.validate_operational_results "
                r"--require-pilot-coverage"
            ),
            (
                r".\.venv\Scripts\python.exe -m "
                r"src.analysis.consolidate_operational_results"
            ),
            (
                r".\.venv\Scripts\python.exe -m "
                r"src.analysis.analyse_operational_replications"
            ),
            (
                r".\.venv\Scripts\python.exe -m "
                r"src.analysis.build_operational_dashboard"
            ),
            "```",
            "",
        ]
    )
    output_summary.write_text(
        "\n".join(markdown),
        encoding="utf-8",
    )
    return {
        "status": "PASS",
        "scenario_count": len(scenarios),
        "replication_count": validation["run_count"],
        "entity_count": validation["entity_count"],
        "outputs": [
            str(output_png),
            str(output_svg),
            str(output_summary),
        ],
        "claim_boundary": (
            "Comparative what-if evidence only; not calibrated HTX performance."
        ),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenarios", type=Path, default=DEFAULT_SCENARIOS)
    parser.add_argument("--estimates", type=Path, default=DEFAULT_ESTIMATES)
    parser.add_argument("--contrasts", type=Path, default=DEFAULT_CONTRASTS)
    parser.add_argument("--output-png", type=Path, default=DEFAULT_PNG)
    parser.add_argument("--output-svg", type=Path, default=DEFAULT_SVG)
    parser.add_argument("--output-summary", type=Path, default=DEFAULT_SUMMARY)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        report = build_dashboard(
            scenarios_path=args.scenarios.resolve(),
            estimates_path=args.estimates.resolve(),
            contrasts_path=args.contrasts.resolve(),
            output_png=args.output_png.resolve(),
            output_svg=args.output_svg.resolve(),
            output_summary=args.output_summary.resolve(),
        )
    except (FileNotFoundError, KeyError, ValueError) as exc:
        print(
            json.dumps(
                {
                    "status": "FAIL",
                    "errors": [str(exc)],
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 1
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
