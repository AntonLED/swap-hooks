"""The regime x gas grid: each dynamic policy's paired advantage over the
static 30 bps baseline, per volatility regime and gas scenario.

The figure the 2026-08-12 VolatilityHook cycle ends on: the value of
adaptation is conditional on BOTH axes at once — visible only when the
regime and the gas price are crossed, which no existing figure does.
Volatile pairs pooled (ETH/SHIB + ETH/USDC, 48 paired windows per panel);
median paired difference with a 95% percentile bootstrap interval over
windows. End-of-window valuation drawn; both valuations in the CSV.

Writes paper/Image/<prefix>regime_gas_grid.{pdf,csv} (+ the _rel
variant), where <prefix> follows the notebooks' UU_CONFIG convention:

    UU_CONFIG=headline  uv run python analysis/draw_regime_gas_grid.py
    UU_CONFIG=informed  uv run python analysis/draw_regime_gas_grid.py

`headline` reads results-uu/ (kappa = 1.0) and writes uu_*; `informed`
reads results-uu/turnover-0.1/ (kappa = 0.1) and writes uu_t01_*. Any
future operating point is one more entry in CONFIGS.
"""

import os
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
    INK_MUTED,
    NEUTRAL,
    SURFACE,
    _save,
    figure_note,
)
from experiments.stats import bootstrap_median_ci

HOOKS = ["VolatilityHook", "BAHook", "DAHook", "ABHook", "MEVChargeHook"]
REGIMES = ["high", "mid", "low"]  # top row = the interesting one
GAS = [5_000_000_000, 20_000_000_000, 80_000_000_000]
VOLATILE = ["ETH/SHIB", "ETH/USDC"]

# Same switch and naming as notebooks 07/08: figures of different operating
# points are named apart and never overwrite each other.
CONFIGS = {
    "headline": {
        "results": "results-uu",
        "prefix": "uu_",
        "note": "κ = 1.0 — calibrated turnover (post gas-fix rerun of 2026-08-12)",
    },
    "informed": {
        "results": "results-uu/turnover-0.1",
        "prefix": "uu_t01_",
        "note": "κ = 0.1 — informed-heavy operating point (post gas-fix rerun of 2026-08-12)",
    },
    # The remaining sweep levels, run as FULL matrices on 2026-08-12 so the
    # grid exists at every retail scale. Same naming rule: t<multiple sans dot>.
    "t003": {
        "results": "results-uu/turnover-0.03",
        "prefix": "uu_t003_",
        "note": "κ = 0.03 — arbitrage-dominated operating point (post gas-fix run of 2026-08-12)",
    },
    "t03": {
        "results": "results-uu/turnover-0.3",
        "prefix": "uu_t03_",
        "note": "κ = 0.3 — intermediate operating point (post gas-fix run of 2026-08-12)",
    },
    "t3": {
        "results": "results-uu/turnover-3",
        "prefix": "uu_t3_",
        "note": "κ = 3.0 — retail-flooded operating point (post gas-fix run of 2026-08-12)",
    },
}
CONFIG = os.environ.get("UU_CONFIG", "headline")
assert CONFIG in CONFIGS, f"UU_CONFIG must be one of {sorted(CONFIGS)}"
SETTINGS = CONFIGS[CONFIG]


def main() -> None:
    frame = pd.read_csv(ROOT / SETTINGS["results"] / "summary.csv")
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
                for valuation in ["net_result_delta", "net_result_tt_delta"]:
                    deltas = sub[valuation]
                    lo, hi = bootstrap_median_ci(deltas)
                    rows.append(
                        {
                            "policy": policy,
                            "regime": regime,
                            "gas_price_wei": gas,
                            "valuation": valuation,
                            "median": float(deltas.median()),
                            "ci_low": lo,
                            "ci_high": hi,
                            "n_windows": len(deltas),
                        }
                    )
    table = pd.DataFrame(rows)
    drawn = table[table["valuation"] == "net_result_delta"]

    fig, axes = plt.subplots(
        len(REGIMES), len(GAS), figsize=(5.3, 4.5), sharex=True, sharey=True
    )
    fig.patch.set_facecolor(SURFACE)

    ys = list(range(len(HOOKS)))[::-1]  # first policy on top
    for i, regime in enumerate(REGIMES):
        for j, gas in enumerate(GAS):
            ax = axes[i][j]
            ax.set_facecolor(SURFACE)
            ax.axvline(0, color="black", linewidth=0.7, zorder=1)
            panel = drawn[(drawn["regime"] == regime) & (drawn["gas_price_wei"] == gas)]
            for policy, y in zip(HOOKS, ys):
                row = panel[panel["policy"] == policy].iloc[0]
                wins = row["ci_low"] > 0
                loses = row["ci_high"] < 0
                colour = ACCENT if wins else (ACCENT_ALT if loses else NEUTRAL)
                # The interval decides the fill, same convention as
                # uu_operating_points: filled = excludes zero.
                filled = wins or loses
                ax.plot(
                    [row["ci_low"], row["ci_high"]],
                    [y, y],
                    color=colour,
                    linewidth=1.6,
                    solid_capstyle="round",
                    zorder=2,
                )
                ax.plot(
                    row["median"],
                    y,
                    marker="o",
                    markersize=5.0,
                    markerfacecolor=colour if filled else SURFACE,
                    markeredgecolor=colour,
                    markeredgewidth=1.1,
                    zorder=3,
                )
            ax.grid(axis="x", color=GRID, linewidth=0.5, linestyle=(0, (1, 2)))
            ax.set_axisbelow(True)
            ax.tick_params(labelsize=9)
            ax.xaxis.set_major_locator(plt.MaxNLocator(4))
            ax.xaxis.set_major_formatter(
                plt.FuncFormatter(lambda v, _: f"{v / 1000:g}k" if v else "0")
            )
            if j == 0:
                ax.set_yticks(ys)
                ax.set_yticklabels(HOOKS, fontsize=9.5, color=INK)
                ax.set_ylabel(
                    f"{regime} volatility", fontsize=10.5, color=INK, labelpad=8
                )
            if i == 0:
                ax.set_title(f"{gas // 10**9} gwei", fontsize=10.5, color=INK)
            if i == len(REGIMES) - 1 and j == 1:
                ax.set_xlabel(
                    "median Δ vs static 30 bps, USDT/window (k = thousands)",
                    fontsize=9.5,
                    color=INK,
                )
            ax.margins(y=0.18)

    fig.tight_layout()

    out = ROOT / "paper" / "Image" / f"{SETTINGS['prefix']}regime_gas_grid.pdf"
    with figure_note(None):
        _save(fig, out, table=table)
    print(f"written: {out} (+ .csv)")


def main_relative() -> None:
    """The same grid normalised by each panel's median baseline result.

    The absolute grid reads deceptively: high-volatility windows are 2-3x
    larger in every dollar quantity (median baseline +22.4k at 5 gwei high
    against +9.2k low), so equal RELATIVE losses draw longer bars in storms
    and the eye concludes adaptation does worse there. Normalised, the
    structure is monotone the mechanism's way for every policy: relative
    performance improves with volatility and degrades with gas.

    Panel-level normalisation (divide by the panel's median baseline
    result, positive in every panel at this operating point) rather than
    per-window ratios: individual windows can have small or negative
    baseline results, and a ratio to those is the sign-flipping trap the
    2026-08-11 analysis banned.
    """
    frame = pd.read_csv(ROOT / SETTINGS["results"] / "summary.csv")
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
                scale = float(sub["net_result_baseline"].median())
                deltas = sub["net_result_delta"]
                lo, hi = bootstrap_median_ci(deltas)
                if scale <= 0:
                    # A ratio to a non-positive baseline flips sign -- the
                    # exact trap the 2026-08-11 analysis banned. The panel is
                    # reported as absent, not as a wrong number.
                    rows.append(
                        {
                            "policy": policy,
                            "regime": regime,
                            "gas_price_wei": gas,
                            "baseline_median": scale,
                            "median_pct": float("nan"),
                            "ci_low_pct": float("nan"),
                            "ci_high_pct": float("nan"),
                            "n_windows": len(deltas),
                        }
                    )
                    continue
                rows.append(
                    {
                        "policy": policy,
                        "regime": regime,
                        "gas_price_wei": gas,
                        "baseline_median": scale,
                        "median_pct": 100.0 * float(deltas.median()) / scale,
                        "ci_low_pct": 100.0 * lo / scale,
                        "ci_high_pct": 100.0 * hi / scale,
                        "n_windows": len(deltas),
                    }
                )
    table = pd.DataFrame(rows)

    fig, axes = plt.subplots(
        len(REGIMES), len(GAS), figsize=(5.3, 4.5), sharex=True, sharey=True
    )
    fig.patch.set_facecolor(SURFACE)

    ys = list(range(len(HOOKS)))[::-1]
    for i, regime in enumerate(REGIMES):
        for j, gas in enumerate(GAS):
            ax = axes[i][j]
            ax.set_facecolor(SURFACE)
            ax.axvline(0, color="black", linewidth=0.7, zorder=1)
            panel = table[(table["regime"] == regime) & (table["gas_price_wei"] == gas)]
            for policy, y in zip(HOOKS, ys):
                row = panel[panel["policy"] == policy].iloc[0]
                if pd.isna(row["median_pct"]):
                    continue  # non-positive baseline: panel entry absent by rule
                wins = row["ci_low_pct"] > 0
                loses = row["ci_high_pct"] < 0
                colour = ACCENT if wins else (ACCENT_ALT if loses else NEUTRAL)
                filled = wins or loses
                ax.plot(
                    [row["ci_low_pct"], row["ci_high_pct"]],
                    [y, y],
                    color=colour,
                    linewidth=1.6,
                    solid_capstyle="round",
                    zorder=2,
                )
                ax.plot(
                    row["median_pct"],
                    y,
                    marker="o",
                    markersize=5.0,
                    markerfacecolor=colour if filled else SURFACE,
                    markeredgecolor=colour,
                    markeredgewidth=1.1,
                    zorder=3,
                )
            ax.grid(axis="x", color=GRID, linewidth=0.5, linestyle=(0, (1, 2)))
            ax.set_axisbelow(True)
            ax.tick_params(labelsize=9)
            ax.xaxis.set_major_locator(plt.MaxNLocator(4))
            if j == 0:
                ax.set_yticks(ys)
                ax.set_yticklabels(HOOKS, fontsize=9.5, color=INK)
                ax.set_ylabel(
                    f"{regime} volatility", fontsize=10.5, color=INK, labelpad=8
                )
            if i == 0:
                ax.set_title(f"{gas // 10**9} gwei", fontsize=10.5, color=INK)
            if i == len(REGIMES) - 1 and j == 1:
                ax.set_xlabel(
                    "median Δ, % of panel's median baseline result",
                    fontsize=9.5,
                    color=INK,
                )
            ax.margins(y=0.18)

    fig.tight_layout()

    out = ROOT / "paper" / "Image" / f"{SETTINGS['prefix']}regime_gas_grid_rel.pdf"
    with figure_note(None):
        _save(fig, out, table=table)
    print(f"written: {out} (+ .csv)")


if __name__ == "__main__":
    main()
    main_relative()
