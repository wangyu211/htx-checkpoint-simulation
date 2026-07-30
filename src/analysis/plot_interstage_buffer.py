"""Render the audited finite interstage-buffer Chart D.

The plotting layer reads only compact outputs from
``analyse_interstage_buffer``.  It does not calculate simulation metrics or
confidence intervals from raw data, and it fails closed unless all registered
validation gates report PASS.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Mapping, Sequence

import matplotlib

matplotlib.use("Agg")
matplotlib.rcParams["svg.hashsalt"] = "htx-interstage-buffer-chart-d-v1"
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.ticker import PercentFormatter

from src.analysis.analyse_interstage_buffer import (
    BUFFER_LEVELS,
    CHART_METRICS,
    DEFAULT_OUTPUT_DIR as DEFAULT_ANALYSIS_DIR,
    EXPECTED_RUN_COUNT,
    REPLICATION_IDS,
    REGIME_NAMES,
    REGIMES,
)


DEFAULT_OUTPUT_DIR = DEFAULT_ANALYSIS_DIR / "figures"

NAVY = "#0B1F3A"
BLUE = "#2563EB"
ORANGE = "#EA580C"
GREEN = "#16A34A"
GREY = "#64748B"
LIGHT_GREY = "#CBD5E1"
PALE_BLUE = "#EAF2FF"
REGIME_STYLE = {
    (36, 16): {
        "label": "Immigration bottleneck  S36 / I16",
        "color": ORANGE,
        "marker": "o",
    },
    (30, 21): {
        "label": "Security bottleneck control  S30 / I21",
        "color": BLUE,
        "marker": "s",
    },
}


def _read_json(path: Path) -> dict[str, object]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain one JSON object")
    return payload


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _number(row: Mapping[str, str], field: str) -> float:
    value = float(row[field])
    if not math.isfinite(value):
        raise ValueError(f"{field} must be finite")
    return value


def _integer(row: Mapping[str, str], field: str) -> int:
    return int(row[field])


def _require_pass(analysis_dir: Path) -> None:
    for filename in (
        "validation.json",
        "registered_contract.json",
        "crn_alignment.json",
        "exact_replay_validation.json",
        "negative_control_invariance.json",
        "analysis_manifest.json",
    ):
        payload = _read_json(analysis_dir / filename)
        if payload.get("status") != "PASS":
            raise ValueError(f"{filename} must report PASS before plotting")

    validation = _read_json(analysis_dir / "validation.json")
    expected = {
        "actual_run_count": EXPECTED_RUN_COUNT,
        "expected_run_count": EXPECTED_RUN_COUNT,
        "regime_count": len(REGIMES),
        "buffer_level_count": len(BUFFER_LEVELS),
        "replications_per_cell": len(REPLICATION_IDS),
    }
    for field, expected_value in expected.items():
        if int(validation.get(field, -1)) != expected_value:
            raise ValueError(f"finite-buffer validated coverage drifted: {field}")

    replay = _read_json(analysis_dir / "exact_replay_validation.json")
    if int(replay.get("replay_buffer_capacity", -1)) != 100:
        raise ValueError("exact-replay buffer capacity drifted")
    if int(replay.get("nonbinding_buffer_capacity", -1)) != 5000:
        raise ValueError("non-binding comparator drifted")


def _estimate_grid(
    analysis_dir: Path,
) -> dict[tuple[int, int, str], list[dict[str, str]]]:
    rows = _read_csv(analysis_dir / "cell_estimates.csv")
    expected_keys = {
        (security, immigration, metric)
        for security, immigration in REGIMES
        for metric in CHART_METRICS
    }
    indexed: dict[tuple[int, int, str], list[dict[str, str]]] = {
        key: [] for key in expected_keys
    }
    for row in rows:
        key = (
            _integer(row, "security_capacity"),
            _integer(row, "immigration_capacity"),
            row["metric"],
        )
        if key not in indexed:
            raise ValueError(f"unexpected finite-buffer estimate series {key}")
        indexed[key].append(row)

    for key, series in indexed.items():
        series.sort(key=lambda row: _integer(row, "interstage_buffer_capacity"))
        buffers = tuple(
            _integer(row, "interstage_buffer_capacity") for row in series
        )
        if buffers != BUFFER_LEVELS:
            raise ValueError(
                f"buffer coverage drifted for estimate series {key}: {buffers}"
            )
        expected_regime = REGIME_NAMES[(key[0], key[1])]
        for row in series:
            if row["regime"] != expected_regime:
                raise ValueError(f"regime label drifted for estimate series {key}")
            if _integer(row, "n_replications") != len(REPLICATION_IDS):
                raise ValueError(
                    f"replication coverage drifted for estimate series {key}"
                )
            mean = _number(row, "mean")
            low = _number(row, "ci_low")
            high = _number(row, "ci_high")
            if not low <= mean <= high:
                raise ValueError(f"CI does not contain mean for series {key}")
    return indexed


def _style_axis(axis: plt.Axes) -> None:
    axis.spines["top"].set_visible(False)
    axis.spines["right"].set_visible(False)
    axis.spines["left"].set_color(LIGHT_GREY)
    axis.spines["bottom"].set_color(LIGHT_GREY)
    axis.tick_params(colors=GREY)
    axis.grid(axis="y", color=LIGHT_GREY, linewidth=0.7, alpha=0.65)
    axis.set_axisbelow(True)


def _draw_series(
    axis: plt.Axes,
    grid: Mapping[tuple[int, int, str], Sequence[Mapping[str, str]]],
    *,
    metric: str,
    scale: float = 1.0,
) -> None:
    x = np.arange(len(BUFFER_LEVELS), dtype=float)
    for regime in REGIMES:
        rows = grid[(regime[0], regime[1], metric)]
        means = np.asarray([_number(row, "mean") * scale for row in rows])
        lows = np.asarray([_number(row, "ci_low") * scale for row in rows])
        highs = np.asarray([_number(row, "ci_high") * scale for row in rows])
        style = REGIME_STYLE[regime]
        axis.errorbar(
            x,
            means,
            yerr=np.vstack((means - lows, highs - means)),
            color=str(style["color"]),
            marker=str(style["marker"]),
            markersize=6,
            linewidth=2.2,
            capsize=3.5,
            label=str(style["label"]),
            zorder=3,
        )
    axis.set_xticks(
        x,
        ("25", "50", "100", "Non-binding\n(5000 guard)"),
    )
    axis.set_xlabel("Security-to-Immigration waiting-space capacity B", color=NAVY)
    axis.axvspan(1.75, 3.25, color=PALE_BLUE, alpha=0.55, zorder=0)
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


def render_chart_d(
    analysis_dir: Path = DEFAULT_ANALYSIS_DIR,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
) -> None:
    """Render the compact two-panel finite-buffer decision chart."""

    _require_pass(analysis_dir)
    grid = _estimate_grid(analysis_dir)

    fig, axes = plt.subplots(1, 2, figsize=(12.8, 5.15))
    time_axis, block_axis = axes
    _draw_series(
        time_axis,
        grid,
        metric="system_time_p95_seconds",
    )
    time_axis.set_title(
        "A  Traveller system-time tail",
        loc="left",
        color=NAVY,
        fontweight="bold",
    )
    time_axis.set_ylabel(
        "Mean replication-level P95 system time (seconds)",
        color=NAVY,
    )

    _draw_series(
        block_axis,
        grid,
        metric="security_blocked_resource_fraction",
        scale=100.0,
    )
    block_axis.set_title(
        "B  Upstream capacity stranded by spillback",
        loc="left",
        color=NAVY,
        fontweight="bold",
    )
    block_axis.set_ylabel(
        "Full-horizon Security resource-time blocked (%)",
        color=NAVY,
    )
    block_axis.yaxis.set_major_formatter(PercentFormatter(xmax=100))
    block_axis.set_ylim(bottom=0)

    handles, labels = time_axis.get_legend_handles_labels()
    fig.legend(
        handles,
        labels,
        loc="upper center",
        bbox_to_anchor=(0.5, 0.915),
        ncol=2,
        frameon=False,
        labelcolor=NAVY,
    )
    fig.suptitle(
        "D  Finite interstage space creates spillback only under "
        "downstream pressure",
        x=0.04,
        y=0.995,
        ha="left",
        color=NAVY,
        fontsize=15,
        fontweight="bold",
    )
    fig.text(
        0.04,
        0.935,
        "Means of 50 replication-level statistics; bars are two-sided "
        "Student-t 95% CIs. Shaded levels satisfy the registered "
        "B100 = B5000 exact-replay gate.",
        color=GREY,
        fontsize=9.5,
    )
    fig.text(
        0.04,
        0.015,
        "Conditional finite-buffer sensitivity only | B=5000 is a "
        "computational non-binding comparator, not measured physical space.",
        color=GREY,
        fontsize=8.5,
    )
    fig.tight_layout(rect=(0.03, 0.06, 0.99, 0.86), w_pad=2.6)
    _save_figure(fig, output_dir, "interstage_buffer_chart_d")
    plt.close(fig)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Render validated finite-buffer Chart D as PNG and SVG."
    )
    parser.add_argument(
        "--analysis-dir",
        type=Path,
        default=DEFAULT_ANALYSIS_DIR,
        help="Validated finite-buffer analysis package.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Destination for PNG/SVG figures.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    render_chart_d(args.analysis_dir, args.output_dir)
    print(f"Rendered finite-buffer Chart D: {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
