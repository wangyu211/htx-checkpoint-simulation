"""Render audited peak-duration sensitivity figures.

The plotting layer reads only compact, validated analysis outputs. It does
not re-estimate metrics from the raw AnyLogic ledgers, and it fails closed
unless validation, CRN alignment, and cross-batch reproducibility all pass.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Mapping, Sequence

import matplotlib

matplotlib.use("Agg")
matplotlib.rcParams["svg.hashsalt"] = "htx-peak-duration-sensitivity-v1"
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Rectangle


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ANALYSIS_DIR = (
    PROJECT_ROOT / "results" / "analysis" / "peak_duration_sensitivity"
)
DEFAULT_OUTPUT_DIR = DEFAULT_ANALYSIS_DIR / "figures"

DURATION_SECONDS = (300, 900, 1800, 3600, 7200)
DURATION_MINUTES = tuple(value / 60 for value in DURATION_SECONDS)
CAPACITY_CELLS = ((36, 21), (30, 18), (29, 17), (28, 16))
EXPECTED_REPLICATIONS = 50

NAVY = "#0B1F3A"
BLUE = "#2563EB"
TEAL = "#0F766E"
ORANGE = "#EA580C"
RED = "#B91C1C"
GREY = "#64748B"
LIGHT_GREY = "#CBD5E1"
PALE_BLUE = "#EAF2FF"
PALE_ORANGE = "#FDE7D8"
CELL_COLOURS = {
    (36, 21): TEAL,
    (30, 18): BLUE,
    (29, 17): ORANGE,
    (28, 16): RED,
}
GROWTH_CLASSIFICATIONS = {
    "NO_CLEAR_GROWTH_DIRECTION",
    "POSITIVE_FINITE_HORIZON_QUEUE_GROWTH",
}


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
    for filename in (
        "validation.json",
        "crn_alignment.json",
        "cross_batch_reproducibility.json",
        "analysis_manifest.json",
    ):
        payload = _read_json(analysis_dir / filename)
        if payload.get("status") != "PASS":
            raise ValueError(f"{filename} must report PASS before plotting")

    validation = _read_json(analysis_dir / "validation.json")
    expected = {
        "actual_run_count": 1000,
        "capacity_cell_count": len(CAPACITY_CELLS),
        "duration_level_count": len(DURATION_SECONDS),
        "replications_per_cell": EXPECTED_REPLICATIONS,
    }
    for field, expected_value in expected.items():
        if int(validation.get(field, -1)) != expected_value:
            raise ValueError(
                f"validated peak-duration coverage drifted: {field}"
            )
    if (
        validation.get("claim_boundary")
        != "CONDITIONAL_FINITE_HORIZON_DURATION_SENSITIVITY_ONLY"
    ):
        raise ValueError("peak-duration claim boundary drifted")


def _number(row: Mapping[str, str], field: str) -> float:
    value = float(row[field])
    if not np.isfinite(value):
        raise ValueError(f"{field} must be finite")
    return value


def _integer(row: Mapping[str, str], field: str) -> int:
    return int(row[field])


def _cell(row: Mapping[str, str]) -> tuple[int, int]:
    return (
        _integer(row, "security_capacity"),
        _integer(row, "immigration_capacity"),
    )


def _estimate_grid(
    analysis_dir: Path,
    metric: str,
) -> dict[tuple[int, int], list[dict[str, str]]]:
    rows = [
        row
        for row in _read_csv(analysis_dir / "cell_estimates.csv")
        if row["metric"] == metric
    ]
    indexed: dict[tuple[int, int], list[dict[str, str]]] = {
        cell: [] for cell in CAPACITY_CELLS
    }
    for row in rows:
        cell = _cell(row)
        if cell not in indexed:
            raise ValueError(f"unexpected capacity cell {cell} for {metric}")
        indexed[cell].append(row)

    for cell, cell_rows in indexed.items():
        cell_rows.sort(key=lambda row: _integer(row, "arrival_cutoff_seconds"))
        durations = tuple(
            _integer(row, "arrival_cutoff_seconds") for row in cell_rows
        )
        if durations != DURATION_SECONDS:
            raise ValueError(
                f"{metric} duration coverage drifted for {cell}: {durations}"
            )
        for row in cell_rows:
            mean = _number(row, "mean")
            low = _number(row, "ci_low")
            high = _number(row, "ci_high")
            if not low <= mean <= high:
                raise ValueError(f"{metric} CI does not contain its mean")
            if _integer(row, "n_replications") != EXPECTED_REPLICATIONS:
                raise ValueError(f"{metric} replication coverage drifted")
    return indexed


def _growth_grid(
    analysis_dir: Path,
) -> dict[tuple[int, int], list[dict[str, str]]]:
    rows = _read_csv(analysis_dir / "growth_diagnostics.csv")
    indexed: dict[tuple[int, int], list[dict[str, str]]] = {
        cell: [] for cell in CAPACITY_CELLS
    }
    for row in rows:
        cell = _cell(row)
        if cell not in indexed:
            raise ValueError(f"unexpected growth-diagnostic cell {cell}")
        classification = row["growth_classification"]
        if classification not in GROWTH_CLASSIFICATIONS:
            raise ValueError(
                f"unexpected growth classification {classification}"
            )
        indexed[cell].append(row)

    for cell, cell_rows in indexed.items():
        cell_rows.sort(key=lambda row: _integer(row, "arrival_cutoff_seconds"))
        durations = tuple(
            _integer(row, "arrival_cutoff_seconds") for row in cell_rows
        )
        if durations != DURATION_SECONDS:
            raise ValueError(
                f"growth-diagnostic duration coverage drifted for {cell}"
            )
        for row in cell_rows:
            if _integer(row, "n_replications") != EXPECTED_REPLICATIONS:
                raise ValueError("growth-diagnostic replication coverage drifted")
            mean = _number(
                row, "mean_growth_slope_travellers_per_second"
            )
            low = _number(row, "ci_low")
            high = _number(row, "ci_high")
            if not low <= mean <= high:
                raise ValueError("growth-diagnostic CI does not contain mean")
    return indexed


def _max_rho(rows: Sequence[Mapping[str, str]]) -> float:
    values = {
        max(
            _number(row, "security_rho_proxy"),
            _number(row, "immigration_rho_proxy"),
        )
        for row in rows
    }
    if len(values) != 1:
        raise ValueError("rho proxy drifted within one capacity curve")
    return values.pop()


def _curve_label(
    cell: tuple[int, int],
    rows: Sequence[Mapping[str, str]],
) -> str:
    max_rho = _max_rho(rows)
    regime = "<1" if max_rho < 1 else ">=1"
    return f"{cell[0]}/{cell[1]}  max rho={max_rho:.2f} ({regime})"


def _style_axis(axis: plt.Axes, *, grid_axis: str = "y") -> None:
    axis.spines["top"].set_visible(False)
    axis.spines["right"].set_visible(False)
    axis.spines["left"].set_color(LIGHT_GREY)
    axis.spines["bottom"].set_color(LIGHT_GREY)
    axis.tick_params(colors=GREY)
    axis.grid(
        axis=grid_axis,
        color=LIGHT_GREY,
        linewidth=0.7,
        alpha=0.65,
    )
    axis.set_axisbelow(True)


def _draw_estimate_curves(
    axis: plt.Axes,
    grid: Mapping[tuple[int, int], Sequence[Mapping[str, str]]],
) -> None:
    x = np.asarray(DURATION_MINUTES, dtype=float)
    for cell in CAPACITY_CELLS:
        rows = grid[cell]
        max_rho = _max_rho(rows)
        mean = np.asarray([_number(row, "mean") for row in rows])
        low = np.asarray([_number(row, "ci_low") for row in rows])
        high = np.asarray([_number(row, "ci_high") for row in rows])
        if np.any(low <= 0):
            raise ValueError("log-scale confidence bounds must be positive")
        axis.errorbar(
            x,
            mean,
            yerr=np.vstack((mean - low, high - mean)),
            color=CELL_COLOURS[cell],
            marker="o",
            markersize=5.5,
            linewidth=2.1,
            linestyle="-" if max_rho < 1 else (0, (5, 2)),
            capsize=3,
            label=_curve_label(cell, rows),
            zorder=3,
        )
    axis.set_xticks(DURATION_MINUTES, [f"{value:g}" for value in DURATION_MINUTES])
    axis.set_yscale("log")
    axis.set_xlabel("Arrival duration (minutes)", color=NAVY)
    _style_axis(axis)


def _save_figure(fig: plt.Figure, output_dir: Path, stem: str) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    metadata = {
        "Creator": "HTX checkpoint simulation analysis",
        "Date": None,
    }
    for suffix in ("png", "svg"):
        path = output_dir / f"{stem}.{suffix}"
        fig.savefig(
            path,
            dpi=240,
            bbox_inches="tight",
            facecolor="white",
            metadata=metadata,
        )
        if suffix != "svg":
            continue
        text = path.read_text(encoding="utf-8")
        if "<image" in text.lower() or "data:image" in text.lower():
            raise ValueError(f"{path} contains embedded raster content")
        with path.open("w", encoding="utf-8", newline="\n") as stream:
            stream.write(
                "\n".join(line.rstrip() for line in text.splitlines()) + "\n"
            )


def render_queue_sensitivity(
    analysis_dir: Path,
    output_dir: Path,
) -> None:
    metric_panels = (
        (
            "total_queue_wait_p95_seconds",
            "A  Traveller queue-wait tail",
            "Mean replication-level P95 queue wait (seconds, log scale)",
        ),
        (
            "total_waiting_at_cutoff",
            "B  Queue remaining when arrivals stop",
            "Mean travellers waiting at cutoff (log scale)",
        ),
    )
    fig, axes = plt.subplots(1, 2, figsize=(13.2, 5.6))
    for axis, (metric, title, ylabel) in zip(axes, metric_panels):
        grid = _estimate_grid(analysis_dir, metric)
        _draw_estimate_curves(axis, grid)
        axis.set_title(title, loc="left", color=NAVY, fontweight="bold")
        axis.set_ylabel(ylabel, color=NAVY)

    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(
        handles,
        labels,
        loc="lower center",
        ncol=4,
        frameon=False,
        bbox_to_anchor=(0.5, 0.075),
        fontsize=9,
    )
    fig.suptitle(
        "Longer exposure reveals bounded, near-critical, and accumulating regimes",
        x=0.055,
        y=0.985,
        ha="left",
        color=NAVY,
        fontsize=15,
        fontweight="bold",
    )
    fig.text(
        0.055,
        0.925,
        "Stationary-HPP exposure sensitivity; points are means with "
        "Student-t 95% CIs across 50 common-random-number replications.",
        color=GREY,
        fontsize=9.5,
    )
    fig.text(
        0.5,
        0.012,
        "Only 5/15/30/60/120 minutes were simulated; connecting lines are "
        "visual guides. max rho >= 1 cells are finite-horizon "
        "accumulation evidence, not steady-state estimates, forecasts, or "
        "staffing recommendations.",
        ha="center",
        color=GREY,
        fontsize=8.5,
    )
    fig.tight_layout(rect=(0.04, 0.16, 0.99, 0.88))
    _save_figure(
        fig,
        output_dir,
        "peak_duration_queue_sensitivity",
    )
    plt.close(fig)


def _render_growth_heatmap(
    axis: plt.Axes,
    analysis_dir: Path,
) -> None:
    growth = _growth_grid(analysis_dir)
    for row_index, cell in enumerate(CAPACITY_CELLS):
        rows = growth[cell]
        for column_index, row in enumerate(rows):
            classification = row["growth_classification"]
            positive = (
                classification
                == "POSITIVE_FINITE_HORIZON_QUEUE_GROWTH"
            )
            axis.add_patch(
                Rectangle(
                    (column_index - 0.5, row_index - 0.5),
                    1.0,
                    1.0,
                    facecolor=PALE_ORANGE if positive else PALE_BLUE,
                    edgecolor="white",
                    linewidth=1.5,
                )
            )
            slope_per_minute = (
                60
                * _number(
                    row,
                    "mean_growth_slope_travellers_per_second",
                )
            )
            axis.text(
                column_index,
                row_index,
                (
                    f"{slope_per_minute:+.1f}/min\n95% CI > 0"
                    if positive
                    else f"{slope_per_minute:+.2f}/min\nCI spans 0"
                ),
                ha="center",
                va="center",
                color=RED if positive else NAVY,
                fontsize=8.2,
                fontweight="bold" if positive else "normal",
            )

    row_labels = []
    for cell in CAPACITY_CELLS:
        row_labels.append(
            _curve_label(
                cell,
                _estimate_grid(
                    analysis_dir,
                    "cohort_clear_time_after_cutoff_seconds",
                )[cell],
            )
        )
    axis.set_xticks(
        range(len(DURATION_MINUTES)),
        [f"{value:g}" for value in DURATION_MINUTES],
    )
    axis.set_yticks(range(len(CAPACITY_CELLS)), row_labels)
    axis.set_xlim(-0.5, len(DURATION_MINUTES) - 0.5)
    axis.set_ylim(len(CAPACITY_CELLS) - 0.5, -0.5)
    axis.set_xlabel("Arrival duration (minutes)", color=NAVY)
    axis.set_title(
        "B  Queue-growth regime in the final half-window",
        loc="left",
        color=NAVY,
        fontweight="bold",
    )
    axis.tick_params(colors=GREY)
    for spine in axis.spines.values():
        spine.set_visible(False)
    axis.axhline(1.5, color=GREY, linewidth=1.1, linestyle=(0, (4, 3)))


def render_recovery_diagnostics(
    analysis_dir: Path,
    output_dir: Path,
) -> None:
    fig, axes = plt.subplots(
        1,
        2,
        figsize=(13.5, 5.7),
        gridspec_kw={"width_ratios": (0.94, 1.38)},
    )
    recovery_grid = _estimate_grid(
        analysis_dir,
        "cohort_clear_time_after_cutoff_seconds",
    )
    _draw_estimate_curves(axes[0], recovery_grid)
    axes[0].set_title(
        "A  Time to clear the admitted cohort after cutoff",
        loc="left",
        color=NAVY,
        fontweight="bold",
    )
    axes[0].set_ylabel(
        "Mean post-cutoff clearance time (seconds, log scale)",
        color=NAVY,
    )
    axes[0].legend(loc="upper left", frameon=False, fontsize=8.5)

    _render_growth_heatmap(axes[1], analysis_dir)

    fig.suptitle(
        "Post-cutoff recovery reveals whether longer exposure is self-clearing",
        x=0.05,
        y=0.985,
        ha="left",
        color=NAVY,
        fontsize=15,
        fontweight="bold",
    )
    fig.text(
        0.05,
        0.925,
        "Growth cells report the mean replication-level OLS slope across "
        "five equal windows spanning the final 50% of arrivals.",
        color=GREY,
        fontsize=9.5,
    )
    fig.text(
        0.5,
        0.01,
        "Exploratory, finite-horizon and conditional on a stationary-HPP "
        "extension, pooled FCFS, empty start and full drain. This is not a "
        "time-of-day forecast or a steady-state claim.",
        ha="center",
        color=GREY,
        fontsize=8.5,
    )
    fig.tight_layout(rect=(0.035, 0.05, 0.995, 0.88))
    _save_figure(
        fig,
        output_dir,
        "peak_duration_recovery_diagnostics",
    )
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
    render_recovery_diagnostics(analysis_dir, output_dir)
    print(
        json.dumps(
            {
                "status": "PASS",
                "analysis_dir": str(analysis_dir),
                "output_dir": str(output_dir),
                "figures": [
                    "peak_duration_queue_sensitivity.png",
                    "peak_duration_queue_sensitivity.svg",
                    "peak_duration_recovery_diagnostics.png",
                    "peak_duration_recovery_diagnostics.svg",
                ],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
