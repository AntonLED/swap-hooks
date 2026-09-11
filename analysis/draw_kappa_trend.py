"""The advantage of each hook vs the 30 bps baseline, across all five
operating points — the figure the five full matrices exist to draw.

One small-multiple panel per hook. X: kappa (log). Y: the headline
estimand at that operating point — median across the 18 volatile-pair
strata of the median paired difference vs `MyHook@3000`, with the 95%
bootstrap interval over strata (identical machinery to §10's headline
table; end-of-window valuation drawn, both valuations in the CSV).
Filled marker = interval excludes zero (blue win / orange loss), the same
convention as every grid figure.

Supersedes the old probe-based `kappa_response`: five FULL matrices
(5,832 cells each), not a one-pair sweep. Writes
paper/Image/uu_kappa_trend.{pdf,csv}.
"""

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from experiments.aggregate import paired_against_baseline, summarise_strata
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
from experiments.stats import analyse

LEVELS = [
    (0.03, "results-uu/turnover-0.03"),
    (0.1, "results-uu/turnover-0.1"),
    (0.3, "results-uu/turnover-0.3"),
    (1.0, "results-uu"),
    (3.0, "results-uu/turnover-3"),
]
HOOKS = ["VolatilityHook", "BAHook", "DAHook", "ABHook", "MEVChargeHook"]
ARB_SHARE = {0.03: "89%", 0.1: "58%", 0.3: "25%", 1.0: "13%", 3.0: "16%"}


def main() -> None:
    rows = []
    for kappa, rel in LEVELS:
        frame = pd.read_csv(ROOT / rel / "summary.csv")
        paired = paired_against_baseline(frame)
        for valuation in ["net_result_delta", "net_result_tt_delta"]:
            head = summarise_strata(analyse(paired, value=valuation))
            for _, r in head.iterrows():
                if r["policy"] not in HOOKS:
                    continue
                rows.append(
                    {
                        "kappa": kappa,
                        "policy": r["policy"],
                        "valuation": valuation,
                        "median": r["median"],
                        "ci_low": r["ci_low"],
                        "ci_high": r["ci_high"],
                        "ci_excludes_zero": r["ci_excludes_zero"],
                    }
                )
    table = pd.DataFrame(rows)
    drawn = table[table["valuation"] == "net_result_delta"]

    fig, axes = plt.subplots(len(HOOKS), 1, figsize=(4.9, 6.6), sharex=True)
    fig.patch.set_facecolor(SURFACE)

    for ax, policy in zip(axes, HOOKS):
        ax.set_facecolor(SURFACE)
        ax.axhline(0, color="black", linewidth=0.7, zorder=1)
        sub = drawn[drawn["policy"] == policy].sort_values("kappa")
        ax.plot(sub["kappa"], sub["median"], color=GRID, linewidth=1.2, zorder=2)
        for _, r in sub.iterrows():
            wins = r["ci_low"] > 0
            loses = r["ci_high"] < 0
            colour = ACCENT if wins else (ACCENT_ALT if loses else NEUTRAL)
            ax.plot(
                [r["kappa"], r["kappa"]],
                [r["ci_low"], r["ci_high"]],
                color=colour,
                linewidth=2.0,
                solid_capstyle="round",
                zorder=3,
            )
            ax.plot(
                r["kappa"],
                r["median"],
                marker="o",
                markersize=5.0,
                markerfacecolor=colour if (wins or loses) else SURFACE,
                markeredgecolor=colour,
                markeredgewidth=1.1,
                zorder=4,
            )
        ax.set_xscale("log")
        ax.set_ylabel(policy, fontsize=9.5, color=INK)
        ax.grid(axis="y", color=GRID, linewidth=0.5, linestyle=(0, (1, 2)))
        ax.set_axisbelow(True)
        ax.tick_params(labelsize=9)
        ax.yaxis.set_major_formatter(
            plt.FuncFormatter(lambda v, _: f"{v / 1000:g}k" if v else "0")
        )
        ax.margins(y=0.32)

    axes[-1].set_xticks([lv for lv, _ in LEVELS])
    axes[-1].set_xticklabels(
        [f"{lv:g}\n(arb {ARB_SHARE[lv]})" for lv, _ in LEVELS], fontsize=9
    )
    axes[-1].set_xlabel(
        "κ — retail turnover, baskets/day (arbitrage share of volume beneath)",
        fontsize=9.5,
        color=INK,
    )
    axes[-1].minorticks_off()
    fig.supylabel(
        "median Δ vs static 30 bps, USDT/window (k = thousands)",
        fontsize=9.5,
        color=INK,
    )

    fig.tight_layout()

    out = ROOT / "paper" / "Image" / "uu_kappa_trend.pdf"
    with figure_note(None):
        _save(fig, out, table=table)
    print(f"written: {out} (+ .csv)")


GAS = [5_000_000_000, 20_000_000_000, 80_000_000_000]
SCENARIO_COLOUR = {
    5_000_000_000: "#7fb2e8",
    20_000_000_000: ACCENT,
    80_000_000_000: "#123c6e",
}
VOLATILE = ["ETH/SHIB", "ETH/USDC"]


def main_high() -> None:
    """The storm slice: the same trend, high-volatility regime only, split
    by gas scenario — the corner of the grid figures as a function of κ.

    Per (κ, policy, gas): the 48 high-regime paired window differences of
    the two volatile pairs pooled, median + 95% bootstrap CI over windows
    (the grid figures' panel estimand). Colour = gas scenario (identity);
    filled marker = CI excludes zero. Writes uu_kappa_trend_high.{pdf,csv}.
    """
    from experiments.stats import bootstrap_median_ci

    rows = []
    for kappa, rel in LEVELS:
        frame = pd.read_csv(ROOT / rel / "summary.csv")
        paired = paired_against_baseline(frame)
        sub = paired[(paired["regime"] == "high") & paired["pair"].isin(VOLATILE)]
        for policy in HOOKS:
            for gas in GAS:
                deltas = sub[(sub["policy"] == policy) & (sub["gas_price_wei"] == gas)][
                    "net_result_delta"
                ]
                lo, hi = bootstrap_median_ci(deltas)
                rows.append(
                    {
                        "kappa": kappa,
                        "policy": policy,
                        "gas_price_wei": gas,
                        "median": float(deltas.median()),
                        "ci_low": lo,
                        "ci_high": hi,
                        "n_windows": len(deltas),
                    }
                )
    table = pd.DataFrame(rows)

    fig, axes = plt.subplots(len(HOOKS), 1, figsize=(4.9, 6.8), sharex=True)
    fig.patch.set_facecolor(SURFACE)

    offsets = {GAS[0]: 0.88, GAS[1]: 1.0, GAS[2]: 1.14}  # de-overlap on log x
    for ax, policy in zip(axes, HOOKS):
        ax.set_facecolor(SURFACE)
        ax.axhline(0, color="black", linewidth=0.7, zorder=1)
        for gas in GAS:
            sub = table[
                (table["policy"] == policy) & (table["gas_price_wei"] == gas)
            ].sort_values("kappa")
            xs = sub["kappa"] * offsets[gas]
            ax.plot(
                xs,
                sub["median"],
                color=SCENARIO_COLOUR[gas],
                linewidth=1.0,
                alpha=0.5,
                zorder=2,
            )
            for x, (_, r) in zip(xs, sub.iterrows()):
                filled = r["ci_low"] > 0 or r["ci_high"] < 0
                ax.plot(
                    [x, x],
                    [r["ci_low"], r["ci_high"]],
                    color=SCENARIO_COLOUR[gas],
                    linewidth=1.8,
                    solid_capstyle="round",
                    zorder=3,
                )
                ax.plot(
                    x,
                    r["median"],
                    marker="o",
                    markersize=5.0,
                    markerfacecolor=SCENARIO_COLOUR[gas] if filled else SURFACE,
                    markeredgecolor=SCENARIO_COLOUR[gas],
                    markeredgewidth=1.1,
                    zorder=4,
                )
        ax.set_xscale("log")
        ax.set_ylabel(policy, fontsize=9.5, color=INK)
        ax.grid(axis="y", color=GRID, linewidth=0.5, linestyle=(0, (1, 2)))
        ax.set_axisbelow(True)
        ax.tick_params(labelsize=9)
        ax.yaxis.set_major_formatter(
            plt.FuncFormatter(lambda v, _: f"{v / 1000:g}k" if v else "0")
        )
        ax.margins(y=0.32)

    axes[-1].set_xticks([lv for lv, _ in LEVELS])
    axes[-1].set_xticklabels(
        [f"{lv:g}\n(arb {ARB_SHARE[lv]})" for lv, _ in LEVELS], fontsize=9
    )
    axes[-1].set_xlabel("κ — retail turnover, baskets/day", fontsize=9, color=INK)
    axes[-1].minorticks_off()
    fig.supylabel(
        "median Δ vs static 30 bps in high-volatility windows, "
        "USDT/window (k = thousands)",
        fontsize=9,
        color=INK,
    )

    handles = [
        plt.Line2D(
            [],
            [],
            marker="o",
            linestyle="",
            markersize=7,
            markerfacecolor=SCENARIO_COLOUR[g],
            markeredgecolor=SURFACE,
            label=f"{g // 10**9} gwei",
        )
        for g in GAS
    ]
    axes[0].legend(handles=handles, loc="upper right", frameon=True, fontsize=9)

    fig.tight_layout()

    out = ROOT / "paper" / "Image" / "uu_kappa_trend_high.pdf"
    with figure_note(None):
        _save(fig, out, table=table)
    print(f"written: {out} (+ .csv)")


if __name__ == "__main__":
    main()
    main_high()
