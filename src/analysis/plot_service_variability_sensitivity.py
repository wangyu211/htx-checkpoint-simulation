"""Render audited figures for the accepted service-variability sensitivity.

The script reads only compact, validated analysis outputs. It does not
re-estimate metrics or confidence intervals from raw AnyLogic ledgers.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Mapping, Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.cm import ScalarMappable
from matplotlib.colors import Normalize
from matplotlib.patches import Rectangle


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ANALYSIS_DIR = (
    PROJECT_ROOT / "results" / "analysis" / "service_variability"
)
DEFAULT_OUTPUT_DIR = DEFAULT_ANALYSIS_DIR / "figures"

CV_LEVELS = (0.0, 0.5, 1.0)
NAVY = "#0B1F3A"
BLUE = "#2563EB"
ORANGE = "#EA580C"
GREEN = "#16A34A"
GREY = "#64748B"
LIGHT_GREY = "#CBD5E1"
PALE_BLUE = "#EFF6FF"

QUEUE_METRIC = "total_queue_wait_p95_seconds"
TAIL_METRICS = (
    ("total_queue_wait_p95_seconds", "Queue-wait P95"),
    ("system_time_p95_seconds", "System-time P95"),
    (
        "cohort_clear_time_after_cutoff_seconds",
        "Post-cutoff clearance",
    ),
)
TREATMENTS = (
    (1.0, 0.0, "Security CV 1"),
    (0.0, 1.0, "Immigration CV 1"),
    (1.0, 1.0, "Both CV 1"),
)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _read_json(path: Path) -> dict[str, object]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain one JSON object")
    return payload


def _require_pass(analysis_dir: Path) -> None:
    required = {
        "validation.json": "status",
        "crn_alignment.json": "status",
        "cross_batch_reproducibility.json": "status",
    }
    for filename, field in required.items():
        payload = _read_json(analysis_dir / filename)
        if payload.get(field) != "PASS":
            raise ValueError(f"{filename} must report PASS before plotting")
    validation = _read_json(analysis_dir / "validation.json")
    if (
        int(validation.get("actual_run_count", -1)) != 450
        or int(validation.get("scenario_count", -1)) != 9
        or int(validation.get("replications_per_cell", -1)) != 50
    ):
        raise ValueError("validated service-variability coverage drifted")


def _number(row: Mapping[str, str], field: str) -> float:
    value = float(row[field])
    if not np.isfinite(value):
        raise ValueError(f"{field} must be finite")
    return value


def _matching_row(
    rows: Sequence[Mapping[str, str]],
    *,
    security_cv: float,
    immigration_cv: float,
    metric: str,
) -> Mapping[str, str]:
    matches = [
        row
        for row in rows
        if _number(row, "security_service_cv") == security_cv
        and _number(row, "immigration_service_cv") == immigration_cv
        and row["metric"] == metric
    ]
    if len(matches) != 1:
        raise ValueError(
            "expected one row for "
            f"Security CV={security_cv}, Immigration CV={immigration_cv}, "
            f"metric={metric}; found {len(matches)}"
        )
    return matches[0]


def _style_axis(axis: plt.Axes) -> None:
    axis.spines["top"].set_visible(False)
    axis.spines["right"].set_visible(False)
    axis.spines["left"].set_color(LIGHT_GREY)
    axis.spines["bottom"].set_color(LIGHT_GREY)
    axis.tick_params(colors=GREY)
    axis.set_axisbelow(True)


def _save_figure(fig: plt.Figure, output_dir: Path, stem: str) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for suffix in ("png", "svg"):
        path = output_dir / f"{stem}.{suffix}"
        fig.savefig(
            path,
            dpi=240,
            bbox_inches="tight",
            facecolor="white",
            metadata={"Date": None},
        )
        if suffix == "svg":
            text = path.read_text(encoding="utf-8")
            with path.open(
                "w",
                encoding="utf-8",
                newline="\n",
            ) as stream:
                stream.write(
                    "\n".join(
                        line.rstrip() for line in text.splitlines()
                    )
                    + "\n"
                )


def render_queue_sensitivity(
    analysis_dir: Path,
    output_dir: Path,
) -> None:
    heatmap_rows = _read_csv(analysis_dir / "heatmap.csv")
    contrast_rows = _read_csv(
        analysis_dir / "paired_contrasts_vs_reference.csv"
    )
    interaction_rows = _read_csv(
        analysis_dir / "factorial_interactions.csv"
    )

    matrix = np.empty((3, 3), dtype=float)
    for row_index, security_cv in enumerate(CV_LEVELS):
        for column_index, immigration_cv in enumerate(CV_LEVELS):
            row = _matching_row(
                heatmap_rows,
                security_cv=security_cv,
                immigration_cv=immigration_cv,
                metric=QUEUE_METRIC,
            )
            matrix[row_index, column_index] = _number(row, "mean")

    fig, axes = plt.subplots(1, 2, figsize=(12.8, 5.2))
    heat_axis, forest_axis = axes
    colour_map = plt.get_cmap("Blues")
    normalizer = Normalize(vmin=0.0, vmax=7.0)
    for row_index in range(3):
        for column_index in range(3):
            heat_axis.add_patch(
                Rectangle(
                    (column_index - 0.5, row_index - 0.5),
                    1.0,
                    1.0,
                    facecolor=colour_map(
                        normalizer(matrix[row_index, column_index])
                    ),
                    edgecolor="none",
                )
            )
            heat_axis.text(
                column_index,
                row_index,
                f"{matrix[row_index, column_index]:.1f}s",
                ha="center",
                va="center",
                color=NAVY if matrix[row_index, column_index] < 4.7 else "white",
                fontweight="bold",
            )
    heat_axis.add_patch(
        Rectangle(
            (-0.5, -0.5),
            1,
            1,
            fill=False,
            edgecolor=GREEN,
            linewidth=2.5,
        )
    )
    heat_axis.set_xticks(range(3), [str(value) for value in CV_LEVELS])
    heat_axis.set_yticks(range(3), [str(value) for value in CV_LEVELS])
    heat_axis.set_xlim(-0.5, 2.5)
    heat_axis.set_ylim(-0.5, 2.5)
    heat_axis.set_aspect("auto")
    heat_axis.set_xlabel("Immigration service CV assumption", color=NAVY)
    heat_axis.set_ylabel("Security service CV assumption", color=NAVY)
    heat_axis.set_title(
        "A  Queue-wait P95 across the 3 x 3 grid\n"
        "Mean service held fixed; values are means across 50 replications",
        loc="left",
        color=NAVY,
        fontweight="bold",
    )
    heat_axis.tick_params(colors=GREY)
    colour_scale = ScalarMappable(norm=normalizer, cmap=colour_map)
    colour_scale.set_array([])
    colorbar = fig.colorbar(
        colour_scale,
        ax=heat_axis,
        fraction=0.046,
        pad=0.04,
    )
    if colorbar.solids is not None:
        colorbar.solids.set_rasterized(False)
    colorbar.set_label("Mean replication-level P95 wait (s)", color=NAVY)
    colorbar.ax.tick_params(colors=GREY)

    forest_rows: list[tuple[str, float, float, float, str, str]] = []
    for security_cv, immigration_cv, label in TREATMENTS:
        row = _matching_row(
            contrast_rows,
            security_cv=security_cv,
            immigration_cv=immigration_cv,
            metric=QUEUE_METRIC,
        )
        forest_rows.append(
            (
                label,
                _number(row, "difference_mean"),
                _number(row, "ci_low"),
                _number(row, "ci_high"),
                BLUE,
                "o",
            )
        )
    interaction = _matching_row(
        interaction_rows,
        security_cv=1.0,
        immigration_cv=1.0,
        metric=QUEUE_METRIC,
    )
    forest_rows.append(
        (
            "CV 1 x CV 1 interaction",
            _number(interaction, "interaction_mean"),
            _number(interaction, "ci_low"),
            _number(interaction, "ci_high"),
            ORANGE,
            "s",
        )
    )

    y_positions = np.arange(len(forest_rows))[::-1]
    for y_position, (
        label,
        estimate,
        low,
        high,
        color,
        marker,
    ) in zip(y_positions, forest_rows):
        forest_axis.errorbar(
            estimate,
            y_position,
            xerr=np.array([[estimate - low], [high - estimate]]),
            color=color,
            marker=marker,
            markersize=7,
            capsize=4,
            linewidth=2,
        )
        forest_axis.text(
            high + 0.08,
            y_position,
            f"{estimate:+.2f}s [{low:+.2f}, {high:+.2f}]",
            va="center",
            color=NAVY,
            fontsize=9,
        )
    forest_axis.axvline(0.0, color=GREY, linewidth=1.1)
    forest_axis.set_yticks(
        y_positions,
        [row[0] for row in forest_rows],
    )
    forest_axis.set_xlabel(
        "Paired difference vs CV 0/0 (seconds)",
        color=NAVY,
    )
    forest_axis.set_title(
        "B  Which stage transmits variability into queueing?\n"
        "Paired Student-t 95% CIs, n = 50",
        loc="left",
        color=NAVY,
        fontweight="bold",
    )
    forest_axis.grid(axis="x", color=LIGHT_GREY, linewidth=0.7, alpha=0.65)
    forest_axis.set_xlim(-0.9, 3.35)
    _style_axis(forest_axis)

    fig.suptitle(
        "Immigration-side variability drives queue sensitivity at the 36/21 "
        "reference assumption",
        x=0.06,
        ha="left",
        color=NAVY,
        fontsize=15,
        fontweight="bold",
    )
    fig.text(
        0.06,
        0.005,
        "Exploratory assumption sensitivity: lognormal CV levels are not "
        "measured; 36/21 is a model reference, not an observed roster. "
        "Not calibrated and not a staffing recommendation.",
        color=GREY,
        fontsize=8.5,
    )
    fig.tight_layout(rect=(0.04, 0.06, 0.99, 0.92))
    _save_figure(fig, output_dir, "service_variability_queue_sensitivity")
    plt.close(fig)


def render_tail_contrasts(
    analysis_dir: Path,
    output_dir: Path,
) -> None:
    contrast_rows = _read_csv(
        analysis_dir / "paired_contrasts_vs_reference.csv"
    )
    fig, axes = plt.subplots(1, 3, figsize=(13.2, 4.9))
    colors = (BLUE, ORANGE, GREEN)
    for axis, (metric, title) in zip(axes, TAIL_METRICS):
        y_positions = np.arange(len(TREATMENTS))[::-1]
        for y_position, (
            (security_cv, immigration_cv, label),
            color,
        ) in zip(y_positions, zip(TREATMENTS, colors)):
            row = _matching_row(
                contrast_rows,
                security_cv=security_cv,
                immigration_cv=immigration_cv,
                metric=metric,
            )
            estimate = _number(row, "difference_mean")
            low = _number(row, "ci_low")
            high = _number(row, "ci_high")
            axis.errorbar(
                estimate,
                y_position,
                xerr=np.array([[estimate - low], [high - estimate]]),
                color=color,
                marker="o",
                markersize=7,
                capsize=4,
                linewidth=2,
            )
            axis.text(
                high + max(0.08, 0.025 * max(high, 1.0)),
                y_position,
                f"{estimate:+.1f}",
                va="center",
                color=NAVY,
                fontsize=9,
                fontweight="bold",
            )
        axis.axvline(0.0, color=GREY, linewidth=1.1)
        axis.set_yticks(
            y_positions,
            [label for _, _, label in TREATMENTS],
        )
        axis.set_xlabel("Paired difference vs CV 0/0 (s)", color=NAVY)
        axis.set_title(title, loc="left", color=NAVY, fontweight="bold")
        axis.grid(axis="x", color=LIGHT_GREY, linewidth=0.7, alpha=0.65)
        _style_axis(axis)

    fig.suptitle(
        "Fixed service time masks traveller-tail and recovery risk",
        x=0.055,
        ha="left",
        color=NAVY,
        fontsize=15,
        fontweight="bold",
    )
    fig.text(
        0.055,
        0.875,
        "Mean-preserving lognormal service CV assumptions; paired Student-t "
        "95% CIs across 50 common-random-number replications",
        color=GREY,
        fontsize=9.5,
    )
    fig.text(
        0.055,
        0.005,
        "The tested CVs are transparent assumptions, not measured HTX "
        "distributions. Results are conditional on HPP demand, pooled FCFS, "
        "36/21 reference capacity, empty start and full drain.",
        color=GREY,
        fontsize=8.5,
    )
    fig.tight_layout(rect=(0.04, 0.06, 0.99, 0.84))
    _save_figure(fig, output_dir, "service_variability_tail_contrasts")
    plt.close(fig)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--analysis-dir",
        type=Path,
        default=DEFAULT_ANALYSIS_DIR,
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    analysis_dir = args.analysis_dir.resolve()
    output_dir = args.output_dir.resolve()
    _require_pass(analysis_dir)
    render_queue_sensitivity(analysis_dir, output_dir)
    render_tail_contrasts(analysis_dir, output_dir)
    print(
        json.dumps(
            {
                "status": "PASS",
                "analysis_dir": str(analysis_dir),
                "output_dir": str(output_dir),
                "figures": [
                    "service_variability_queue_sensitivity.png",
                    "service_variability_queue_sensitivity.svg",
                    "service_variability_tail_contrasts.png",
                    "service_variability_tail_contrasts.svg",
                ],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
