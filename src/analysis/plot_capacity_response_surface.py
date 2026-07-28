"""Render submission-ready figures from the audited capacity response surface.

The script reads only compact analysis outputs. It never re-estimates metrics
from the raw AnyLogic ledgers, so every plotted value remains traceable to the
validated analysis package.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.ticker import MaxNLocator


SECURITY_CAPACITIES = tuple(range(36, 27, -1))
IMMIGRATION_CAPACITIES = tuple(range(21, 15, -1))
NAVY = "#0B1F3A"
BLUE = "#2563EB"
ORANGE = "#EA580C"
GREEN = "#16A34A"
GREY = "#64748B"
LIGHT_GREY = "#CBD5E1"


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _number(row: dict[str, str], key: str) -> float:
    return float(row[key])


def _save_figure_variants(fig, output_dir: Path, stem: str) -> None:
    """Save PNG/SVG variants and keep generated SVG text diff-clean."""
    for suffix in ("png", "svg"):
        path = output_dir / f"{stem}.{suffix}"
        fig.savefig(
            path,
            dpi=240,
            bbox_inches="tight",
            facecolor="white",
        )
        if suffix == "svg":
            text = path.read_text(encoding="utf-8")
            path.write_text(
                "\n".join(line.rstrip() for line in text.splitlines()) + "\n",
                encoding="utf-8",
            )


def _integer(row: dict[str, str], key: str) -> int:
    return int(row[key])


def _index_by_capacity(
    rows: list[dict[str, str]],
    capacity_field: str,
) -> dict[int, dict[str, str]]:
    indexed = {_integer(row, capacity_field): row for row in rows}
    if len(indexed) != len(rows):
        raise ValueError(f"duplicate capacity in {capacity_field}")
    return indexed


def _style_axis(ax: plt.Axes) -> None:
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color(LIGHT_GREY)
    ax.spines["bottom"].set_color(LIGHT_GREY)
    ax.tick_params(colors=GREY)
    ax.grid(axis="y", color=LIGHT_GREY, linewidth=0.7, alpha=0.65)
    ax.set_axisbelow(True)


def render_curves(analysis_dir: Path, output_dir: Path) -> None:
    security_rows = _read_csv(analysis_dir / "security_only_slice.csv")
    immigration_rows = _read_csv(analysis_dir / "immigration_only_slice.csv")
    ideal_rows = _read_csv(analysis_dir / "ideal_case_comparator.csv")

    security_index = _index_by_capacity(security_rows, "security_capacity")
    immigration_index = _index_by_capacity(
        immigration_rows,
        "immigration_capacity",
    )
    ideal_index = {
        (
            _integer(row, "security_capacity"),
            _integer(row, "immigration_capacity"),
        ): row
        for row in ideal_rows
    }

    if set(security_index) != set(SECURITY_CAPACITIES):
        raise ValueError("security-only slice does not contain the frozen grid")
    if set(immigration_index) != set(IMMIGRATION_CAPACITIES):
        raise ValueError("immigration-only slice does not contain the frozen grid")

    fig, axes = plt.subplots(1, 2, figsize=(12.8, 5.2), sharey=True)
    panels = (
        (
            axes[0],
            SECURITY_CAPACITIES,
            security_index,
            lambda capacity: ideal_index[(capacity, 21)],
            "Security capacity",
            "Immigration fixed at 21",
            29.7647,
        ),
        (
            axes[1],
            IMMIGRATION_CAPACITIES,
            immigration_index,
            lambda capacity: ideal_index[(36, capacity)],
            "Immigration capacity",
            "Security fixed at 36",
            17.7348,
        ),
    )

    for (
        ax,
        capacities,
        stochastic_index,
        ideal_lookup,
        title,
        subtitle,
        offered_workload,
    ) in panels:
        x = np.asarray(capacities, dtype=float)
        mean = np.asarray(
            [_number(stochastic_index[capacity], "mean") for capacity in capacities]
        )
        low = np.asarray(
            [_number(stochastic_index[capacity], "ci_low") for capacity in capacities]
        )
        high = np.asarray(
            [_number(stochastic_index[capacity], "ci_high") for capacity in capacities]
        )
        ideal = np.asarray(
            [
                _number(ideal_lookup(capacity), "ideal_total_queue_wait_p95_seconds")
                for capacity in capacities
            ]
        )

        ax.errorbar(
            x,
            mean,
            yerr=np.vstack((mean - low, high - mean)),
            color=BLUE,
            marker="o",
            markersize=5,
            linewidth=2.2,
            capsize=3,
            label="AnyLogic HPP · 95% CI",
            zorder=3,
        )
        ax.plot(
            x,
            ideal,
            color=ORANGE,
            marker="s",
            markersize=4,
            linewidth=2,
            linestyle=(0, (5, 3)),
            label="Deterministic ideal",
            zorder=2,
        )
        ax.fill_between(
            x,
            ideal,
            mean,
            color=BLUE,
            alpha=0.08,
            label="Variability + congestion penalty",
            zorder=1,
        )
        ax.axvline(
            offered_workload,
            color=GREY,
            linewidth=1.2,
            linestyle=(0, (3, 3)),
        )
        ax.text(
            offered_workload,
            39.0,
            r"$\rho \approx 1$",
            color=GREY,
            ha="center",
            va="top",
        )
        ax.set_title(f"{title}\n{subtitle}", loc="left", color=NAVY, fontweight="bold")
        ax.set_xlabel("Available pooled positions", color=NAVY)
        ax.set_xticks(capacities)
        ax.invert_xaxis()
        ax.set_ylim(0, 40)
        ax.yaxis.set_major_locator(MaxNLocator(integer=True, nbins=5))
        _style_axis(ax)

        ax.annotate(
            f"{mean[-1]:.1f}s",
            xy=(x[-1], mean[-1]),
            xytext=(7, 4),
            textcoords="offset points",
            color=BLUE,
            fontweight="bold",
        )
        ax.annotate(
            f"{ideal[-1]:.1f}s ideal",
            xy=(x[-1], ideal[-1]),
            xytext=(7, -14),
            textcoords="offset points",
            color=ORANGE,
        )

    axes[0].set_ylabel("Mean replication-level P95 total wait (seconds)", color=NAVY)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(
        handles,
        labels,
        loc="lower center",
        ncol=3,
        frameon=False,
        bbox_to_anchor=(0.5, 0.02),
    )
    fig.text(
        0.5,
        0.002,
        "Points are simulated integer capacities; connecting lines are visual guides.",
        ha="center",
        color=GREY,
        fontsize=9,
    )
    fig.tight_layout(rect=(0, 0.10, 1, 1))
    _save_figure_variants(fig, output_dir, "capacity_response_curves")
    plt.close(fig)


def render_heatmap(analysis_dir: Path, output_dir: Path) -> None:
    heat_rows = _read_csv(analysis_dir / "heatmap.csv")
    values: dict[tuple[int, int], float] = {}
    for row in heat_rows:
        if row["metric"] != "total_queue_wait_p95_seconds":
            continue
        key = (
            _integer(row, "security_capacity"),
            _integer(row, "immigration_capacity"),
        )
        values[key] = _number(row, "mean")

    expected = {
        (security, immigration)
        for security in SECURITY_CAPACITIES
        for immigration in IMMIGRATION_CAPACITIES
    }
    if set(values) != expected:
        raise ValueError("heatmap does not contain the complete frozen 54-cell grid")

    matrix = np.asarray(
        [
            [values[(security, immigration)] for immigration in IMMIGRATION_CAPACITIES]
            for security in SECURITY_CAPACITIES
        ]
    )

    fig, ax = plt.subplots(figsize=(10.4, 7.0))
    image = ax.imshow(matrix, cmap="YlOrRd", vmin=0, vmax=40, aspect="auto")
    colorbar = fig.colorbar(image, ax=ax, pad=0.025)
    colorbar.set_label("Mean P95 total wait (seconds)", color=NAVY)
    colorbar.ax.tick_params(colors=GREY)

    ax.set_xticks(range(len(IMMIGRATION_CAPACITIES)))
    ax.set_xticklabels(IMMIGRATION_CAPACITIES)
    ax.set_yticks(range(len(SECURITY_CAPACITIES)))
    ax.set_yticklabels(SECURITY_CAPACITIES)
    ax.set_xlabel("Immigration capacity", color=NAVY)
    ax.set_ylabel("Security capacity", color=NAVY)
    fig.suptitle(
        "Capacity response surface · fixed Base demand",
        x=0.075,
        y=0.985,
        ha="left",
        color=NAVY,
        fontweight="bold",
    )
    fig.text(
        0.075,
        0.943,
        "The dominant bottleneck moves between stages; joint delay is not additive.",
        color=GREY,
    )

    for row_index in range(matrix.shape[0]):
        for column_index in range(matrix.shape[1]):
            value = matrix[row_index, column_index]
            text_color = "white" if value >= 24 else NAVY
            ax.text(
                column_index,
                row_index,
                f"{value:.1f}",
                ha="center",
                va="center",
                color=text_color,
                fontweight="bold",
            )

    ax.axvline(3.5, color=NAVY, linewidth=1.4, linestyle=(0, (4, 3)))
    ax.axhline(6.5, color=NAVY, linewidth=1.4, linestyle=(0, (4, 3)))
    ax.add_patch(
        plt.Rectangle(
            (-0.48, -0.48),
            0.96,
            0.96,
            fill=False,
            edgecolor=GREEN,
            linewidth=2.5,
        )
    )
    ax.text(
        -0.43,
        -0.34,
        "REFERENCE",
        color=GREEN,
        ha="left",
        va="top",
        fontsize=8,
        fontweight="bold",
    )
    ax.tick_params(colors=GREY)
    for spine in ax.spines.values():
        spine.set_visible(False)

    fig.text(
        0.5,
        0.018,
        r"Dashed thresholds: Immigration 18→17 and Security 30→29 ($\rho \approx 1$).",
        ha="center",
        color=GREY,
        fontsize=9,
    )
    fig.tight_layout(rect=(0, 0.045, 1, 0.91))
    _save_figure_variants(fig, output_dir, "capacity_response_heatmap")
    plt.close(fig)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--analysis-dir",
        type=Path,
        default=Path("results/analysis/capacity_response_surface"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("results/analysis/capacity_response_surface/figures"),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    analysis_dir = args.analysis_dir.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    render_curves(analysis_dir, output_dir)
    render_heatmap(analysis_dir, output_dir)
    print(output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
