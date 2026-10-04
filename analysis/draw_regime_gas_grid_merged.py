"""The regime x gas grid, merged across the two pre-registered operating
points into one figure.

Same 3x3 (regime x gas) layout as draw_regime_gas_grid.py, but each of the
9 cells is now split horizontally: top half = kappa=1.0 (plain background),
bottom half = kappa=0.1 (the same light STRIPE tone draw_seed_forest.py
uses), both halves sharing one x-axis. This replaces the two separate
figures (fig:grid, fig:grid-t01) with one, at the cost of kappa=0.1's much
smaller magnitudes (~4x) reading compressed toward zero -- an honest
consequence of the shared scale, not a rendering bug.

Writes paper/Image/uu_regime_gas_grid.{pdf,csv}, overwriting the
kappa=1.0-only figure that draw_regime_gas_grid.py produces. That script is
untouched and still the source for the other operating points
(t003/t03/t3) and the *_rel variants, which this merge does not replace.
"""

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from experiments.aggregate import paired_against_baseline
from experiments.figures import (
    ACCENT,
    ACCENT_ALT,
    GRID,
    INK,
    NEUTRAL,
    SURFACE,
    _save,
    figure_note,
)
from experiments.stats import bootstrap_median_ci

HOOKS = ["VolatilityHook", "BAHook", "DAHook", "ABHook", "MEVChargeHook"]
REGIMES = ["high", "mid", "low"]
GAS = [5_000_000_000, 20_000_000_000, 80_000_000_000]
VOLATILE = ["ETH/SHIB", "ETH/USDC"]

LIGHT = SURFACE  # kappa = 1.0 half
DARK = "#f3f2ef"  # kappa = 0.1 half, matches draw_seed_forest.py's STRIPE

KAPPAS = [(1.0, "results-uu"), (0.1, "results-uu/turnover-0.1")]


def build_table(kappa: float, results_dir: str) -> pd.DataFrame:
    frame = pd.read_csv(ROOT / results_dir / "summary.csv")
    paired = paired_against_baseline(frame)
    paired = paired[paired["pair"].isin(VOLATILE)]
    rows = []
    for policy in HOOKS:
        for regime in REGIMES:
            for gas in GAS:
                sub = paired[
                    (paired["policy"] == policy)
                    & (paired["regime"] == regime)
                    & (paired["gas_price_wei"] == gas)
                ]
                deltas = sub["net_result_delta"]
                lo, hi = bootstrap_median_ci(deltas)
                rows.append(
                    {
                        "kappa": kappa,
                        "policy": policy,
                        "regime": regime,
                        "gas_price_wei": gas,
                        "median": float(deltas.median()),
                        "ci_low": lo,
                        "ci_high": hi,
                        "n_windows": len(deltas),
                    }
                )
    return pd.DataFrame(rows)


def main() -> None:
    tables = {kappa: build_table(kappa, path) for kappa, path in KAPPAS}

    # Canvas sized for the width it is actually PRINTED at: 0.49\textwidth
    # (~3.45 in) in main.tex Fig. 2 and \columnwidth (~3.5 in) in the
    # evaluation draft. A 5.6 in canvas meant a 0.62 downscale and 8 pt type
    # arriving on the page at 5 pt. Shrinking the canvas and raising the point
    # sizes together puts every label above 8 pt effective.
    fig, axes = plt.subplots(len(REGIMES), len(GAS), figsize=(4.25, 6.75), sharex="col")
    fig.patch.set_facecolor(SURFACE)

    # top half y=9..5 -> kappa=1.0, hooks top to bottom; bottom half y=4..0 -> kappa=0.1
    top_ys = list(range(9, 4, -1))
    bot_ys = list(range(4, -1, -1))
    all_rows = []

    for i, regime in enumerate(REGIMES):
        for j, gas in enumerate(GAS):
            ax = axes[i][j]
            ax.set_facecolor(SURFACE)
            ax.axhspan(4.5, 9.5, color=LIGHT, zorder=0)
            ax.axhspan(-0.5, 4.5, color=DARK, zorder=0)
            ax.axhline(4.5, color=INK, linewidth=0.8, zorder=1)
            ax.axvline(0, color="black", linewidth=0.7, zorder=1)

            for kappa, ys in [(1.0, top_ys), (0.1, bot_ys)]:
                table = tables[kappa]
                panel = table[
                    (table["regime"] == regime) & (table["gas_price_wei"] == gas)
                ]
                for policy, y in zip(HOOKS, ys):
                    row = panel[panel["policy"] == policy].iloc[0]
                    wins, loses = row["ci_low"] > 0, row["ci_high"] < 0
                    colour = ACCENT if wins else (ACCENT_ALT if loses else NEUTRAL)
                    filled = wins or loses
                    ax.plot(
                        [row["ci_low"], row["ci_high"]],
                        [y, y],
                        color=colour,
                        linewidth=1.5,
                        solid_capstyle="round",
                        zorder=2,
                    )
                    ax.plot(
                        row["median"],
                        y,
                        marker="o",
                        markersize=4.6,
                        markerfacecolor=colour if filled else SURFACE,
                        markeredgecolor=colour,
                        markeredgewidth=1.0,
                        zorder=3,
                    )
                    all_rows.append(row.to_dict())

            ax.grid(
                axis="x", color=GRID, linewidth=0.5, linestyle=(0, (1, 2)), zorder=0.5
            )
            ax.set_axisbelow(True)
            ax.tick_params(labelsize=10)
            # Three ticks, not four: a panel is ~1.15 in wide on the page and
            # four "-1.5k"-sized labels at the enlarged size collide.
            ax.xaxis.set_major_locator(plt.MaxNLocator(3))
            ax.xaxis.set_major_formatter(
                plt.FuncFormatter(lambda v, _: f"{v / 1000:g}k" if v else "0")
            )
            ax.set_ylim(-0.5, 9.5)
            if j == 0:
                ax.set_yticks(top_ys + bot_ys)
                short = [h.removesuffix("Hook") or h for h in HOOKS]
                ax.set_yticklabels(short + short, fontsize=8.5, color=INK)
                ax.set_ylabel(
                    f"{regime} volatility", fontsize=10.5, color=INK, labelpad=6
                )
            else:
                ax.set_yticks([])
            if i == 0:
                ax.set_title(f"{gas // 10**9} gwei", fontsize=11.5, color=INK)
            if i == len(REGIMES) - 1 and j == 1:
                ax.set_xlabel(
                    "median Δ vs static 30 bps, USDT/window", fontsize=11, color=INK
                )

    fig.tight_layout(rect=[0, 0, 1, 0.96])

    handles = [
        plt.Rectangle(
            (0, 0),
            1,
            1,
            facecolor=LIGHT,
            edgecolor=INK,
            linewidth=0.5,
            label=r"$\kappa = 1.0$",
        ),
        plt.Rectangle(
            (0, 0),
            1,
            1,
            facecolor=DARK,
            edgecolor=INK,
            linewidth=0.5,
            label=r"$\kappa = 0.1$",
        ),
    ]
    fig.legend(
        handles=handles,
        loc="upper center",
        bbox_to_anchor=(0.5, 1.0),
        ncol=2,
        fontsize=10.5,
        frameon=True,
    )

    out = ROOT / "paper" / "Image" / "uu_regime_gas_grid.pdf"
    with figure_note(None):
        _save(fig, out, table=pd.DataFrame(all_rows))
    print(f"written: {out} (+ .csv)")


if __name__ == "__main__":
    main()
