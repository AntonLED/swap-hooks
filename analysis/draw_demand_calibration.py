"""The demand-calibration figure for the paper: one measured intraday
shape, five kappa heights.

A single log-y panel. The curve is the median 2024 trading day of the
ETH/SHIB legs (the measured shape s-hat), normalised so its daily sum is
exactly one basket at kappa = 1; the five operating points are the SAME
curve shifted vertically. Each is labelled with kappa, the daily demand
it implies, the kind of pool it describes, and the arbitrage share of
volume it produced in the experiment. One glance: the shape comes from
data, kappa only scales it, and the scale sets the flow mix.

Writes paper/Image/uu_demand_calibration.{pdf,csv}. Sized for one IEEE
column.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from experiments.binance import fetch_klines
from experiments.figures import GRID, INK, INK_MUTED, SURFACE, figure_note, _save
from experiments.uu import uu_profile

YEAR_START, YEAR_END = 1_704_067_200_000, 1_735_689_600_000
BASKET = 20_000_000
SMOOTH_MIN = 20

LEVELS = [  # kappa, label lines (kept short), measured arb share
    (3.0, "flagship pool", "16%"),
    (1.0, "primary venue (calibrated)", "13%"),
    (0.3, "mid-tier pool", "25%"),
    (0.1, "secondary venue", "58%"),
    (0.03, "over-provisioned pool", "89%"),
]
# One hue, dark = calibrated emphasis handled by linewidth instead:
# sequential lightness encodes kappa (magnitude), same as the gas figure.
SHADES = {
    3.0: "#9dc1ea",
    1.0: "#2a78d6",
    0.3: "#7fb2e8",
    0.1: "#5f9be0",
    0.03: "#bcd4f0",
}
ORDERED_SHADES = ["#123c6e", "#2a78d6", "#5f9be0", "#8ab5e8", "#bcd4f0"]  # top->bottom


def median_day_shape() -> np.ndarray:
    data = ROOT / "data"
    df0 = fetch_klines("ETHUSDT", YEAR_START, YEAR_END, data, with_volume=True)
    df1 = fetch_klines("SHIBUSDT", YEAR_START, YEAR_END, data, with_volume=True)
    n = min(len(df0), len(df1))
    prof = uu_profile(df0.iloc[:n].reset_index(), df1.iloc[:n].reset_index())
    prof = prof.assign(minute=(prof["open_time"] // 60_000) % 1440)
    day = prof.groupby("minute")["v_usdt"].median().to_numpy()
    padded = np.concatenate([day] * 3)
    smoothed = pd.Series(padded).rolling(SMOOTH_MIN, center=True, min_periods=1).mean()
    day = smoothed[1440 : 2 * 1440].to_numpy()
    return day / day.sum()  # s-hat of the median day: sums to one


def main() -> None:
    shape = median_day_shape()
    hours = np.arange(1440) / 60.0

    fig, ax = plt.subplots(figsize=(3.5, 2.9))
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)

    for (kappa, kind, arb), colour in zip(LEVELS, ORDERED_SHADES):
        v = kappa * BASKET * shape  # USDT per minute
        emphasis = kappa == 1.0
        ax.plot(
            hours,
            v,
            color=colour,
            linewidth=2.0 if emphasis else 1.2,
            zorder=3 if emphasis else 2,
        )
        daily = kappa * BASKET
        daily_label = f"{daily / 1e6:g}M"
        ax.annotate(
            f"κ = {kappa:g} · {daily_label}/day · arb {arb}\n{kind}",
            (24.15, v[-1]),
            fontsize=6.4,
            color=INK if emphasis else INK_MUTED,
            va="center",
            ha="left",
            annotation_clip=False,
            fontweight="bold" if emphasis else "normal",
        )

    # Session captions in a clear band above all curves
    top = 3.0 * BASKET * shape.max()
    ax.set_ylim(0.03 * BASKET * shape.min() * 0.55, top * 3.2)
    for x, txt in [(3.2, "Asia (quiet)"), (15.8, "US session")]:
        ax.annotate(txt, (x, top * 1.9), fontsize=6.8, color=INK, ha="center")

    ax.set_yscale("log")
    ax.set_xlim(0, 24)
    ax.set_xticks(range(0, 25, 6))
    ax.set_xticklabels([f"{h:02d}:00" for h in range(0, 25, 6)], fontsize=7.5)
    ax.set_xlabel("time of day (UTC)", fontsize=8, color=INK)
    ax.set_ylabel("potential retail demand, USDT/min", fontsize=8, color=INK)
    ax.tick_params(labelsize=7.5)
    ax.grid(axis="y", color=GRID, linewidth=0.5, linestyle=(0, (1, 2)))
    ax.set_axisbelow(True)

    fig.tight_layout()
    # room for the right-edge labels
    fig.subplots_adjust(right=0.64)

    table = pd.DataFrame(
        {
            "minute": np.arange(1440),
            **{f"kappa_{k:g}_usdt_per_min": k * BASKET * shape for k, _, _ in LEVELS},
        }
    )
    out = ROOT / "paper" / "Image" / "uu_demand_calibration.pdf"
    with figure_note(None):
        _save(fig, out, table=table)
    print(f"written: {out} (+ .csv)")


if __name__ == "__main__":
    main()
