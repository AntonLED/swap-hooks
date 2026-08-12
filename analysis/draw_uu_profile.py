"""The measured intraday retail profile V_profile(c), visualised.

One panel per pair: the median potential retail demand of each minute of
the (UTC) day across all of 2024, with the interquartile band, at the
calibrated kappa — i.e. exactly the curve v0(c) = kappa * V_profile(c)
that feeds the UU flow, folded by time of day. This is the "shape is
measured, height is assumed" claim of §4.4 made visible: the session
structure (quiet Asian night, European morning, the US afternoon hump)
comes from data; kappa only scales the y axis.

Writes paper/Image/uu_volume_profile.{pdf,csv}.
"""

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from experiments.binance import fetch_klines
from experiments.figures import (
    ACCENT,
    GRID,
    INK,
    INK_MUTED,
    SURFACE,
    _save,
    figure_note,
)
from experiments.run_one import CONSTANT_ONE, kappa_for_pair
from experiments.uu import uu_profile

YEAR_START, YEAR_END = 1_704_067_200_000, 1_735_689_600_000
PAIRS = [
    ("ETH/SHIB", "ETHUSDT", "SHIBUSDT"),
    ("ETH/USDC", "ETHUSDT", "USDCUSDT"),
    ("USDC/USDT", "USDCUSDT", CONSTANT_ONE),
]
SMOOTH_MIN = 15  # rolling window over minutes-of-day, purely cosmetic


def folded_profile(symbol0: str, symbol1: str) -> pd.DataFrame:
    data = ROOT / "data"
    df0 = fetch_klines(symbol0, YEAR_START, YEAR_END, data, with_volume=True)
    if symbol1 == CONSTANT_ONE:
        prof = uu_profile(df0)
    else:
        df1 = fetch_klines(symbol1, YEAR_START, YEAR_END, data, with_volume=True)
        n = min(len(df0), len(df1))
        prof = uu_profile(df0.iloc[:n].reset_index(), df1.iloc[:n].reset_index())
    kappa = kappa_for_pair(symbol0, symbol1)
    prof = prof.assign(
        v_usdt=prof["v_usdt"] * kappa,
        minute=(prof["open_time"] // 60_000) % 1440,
    )
    g = prof.groupby("minute")["v_usdt"]
    out = pd.DataFrame(
        {"median": g.median(), "p25": g.quantile(0.25), "p75": g.quantile(0.75)}
    ).reset_index()
    # circular smoothing so midnight does not get a seam
    for col in ["median", "p25", "p75"]:
        padded = np.concatenate([out[col].to_numpy()] * 3)
        smoothed = (
            pd.Series(padded).rolling(SMOOTH_MIN, center=True, min_periods=1).mean()
        )
        out[col] = smoothed[1440 : 2 * 1440].to_numpy()
    return out


def main() -> None:
    fig, axes = plt.subplots(3, 1, figsize=(8.6, 7.2), sharex=True)
    fig.patch.set_facecolor(SURFACE)

    tables = []
    for ax, (pair, s0, s1) in zip(axes, PAIRS):
        prof = folded_profile(s0, s1)
        tables.append(prof.assign(pair=pair))

        hours = prof["minute"] / 60.0
        ax.set_facecolor(SURFACE)
        ax.fill_between(
            hours,
            prof["p25"] / 1e3,
            prof["p75"] / 1e3,
            color=ACCENT,
            alpha=0.18,
            linewidth=0,
        )
        ax.plot(hours, prof["median"] / 1e3, color=ACCENT, linewidth=1.8)
        # The assumed flat mean at kappa=1: 20M / 1440 minutes.
        ax.axhline(
            20_000 / 1.44 / 1e3, color=INK_MUTED, linewidth=1.0, linestyle=(0, (4, 3))
        )

        ax.set_ylabel(f"{pair}\nkUSDT / min", fontsize=8.5, color=INK)
        ax.grid(axis="both", color=GRID, linewidth=0.6)
        ax.set_axisbelow(True)
        for spine in ["top", "right"]:
            ax.spines[spine].set_visible(False)
        for spine in ["left", "bottom"]:
            ax.spines[spine].set_color(GRID)
        ax.tick_params(colors=INK_MUTED, labelsize=8)
        ax.set_xlim(0, 24)
        ax.margins(y=0.1)

    axes[0].annotate(
        "dashed: the assumed flat mean at κ = 1 (20M/day ÷ 1440 min ≈ 13.9k)",
        (0.02, 0.86),
        xycoords="axes fraction",
        fontsize=8,
        color=INK_MUTED,
    )
    axes[-1].set_xticks(range(0, 25, 4))
    axes[-1].set_xticklabels([f"{h:02d}:00" for h in range(0, 25, 4)])
    axes[-1].set_xlabel("time of day, UTC", fontsize=9, color=INK_MUTED)

    fig.suptitle(
        "V_profile(c): the measured intraday shape of potential retail demand\n"
        "(median minute across all 2024 days at the calibrated κ; band = interquartile range)",
        fontsize=10.5,
        color=INK,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.94))

    out = ROOT / "paper" / "Image" / "uu_volume_profile.pdf"
    with figure_note(
        "shape measured from Binance 2024 per-minute quote volumes; κ scales the height only"
    ):
        _save(fig, out, table=pd.concat(tables, ignore_index=True))
    print(f"written: {out} (+ .csv)")


if __name__ == "__main__":
    main()
