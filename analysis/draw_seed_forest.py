"""Seed robustness of the storm-corner findings, as a forest plot.

Two panels — the two pre-registered operating points. For each policy:
the matrix-of-record estimate (bold, 48 paired high-volatility windows at
5 gwei, volatile pairs pooled) above its five seed replicates (thin, 16
windows each — the appendix subset). Same convention as every grid
figure: filled marker = the 95% bootstrap interval excludes zero, blue
win / orange loss. Seed intervals are wider than the matrix one because
the window set is three times smaller, not because seeds disagree — the
figure exists to show the SIGN surviving every seed.

Writes paper/Image/uu_seed_robustness.{pdf,csv}.
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
    INK_MUTED,
    NEUTRAL,
    SURFACE,
    _save,
    figure_note,
)
from experiments.stats import bootstrap_median_ci

HOOKS = ["VolatilityHook", "BAHook", "DAHook", "ABHook", "MEVChargeHook"]
VOLATILE = ["ETH/SHIB", "ETH/USDC"]
GAS = 5_000_000_000
SEEDS = range(5)
BASELINE = "MyHook@3000"

POINTS = [  # panel label, matrix summary, seed appendix csv
    ("κ = 1.0", "results-uu/summary.csv", "results/sensitivity/seeds.csv"),
    (
        "κ = 0.1",
        "results-uu/turnover-0.1/summary.csv",
        "results/sensitivity/seeds-turnover-0.1/seeds.csv",
    ),
]


def corner_matrix(summary_csv: str) -> dict[str, tuple[float, float, float]]:
    """The matrix-of-record estimate of the corner, per policy."""
    paired = paired_against_baseline(pd.read_csv(ROOT / summary_csv))
    sub = paired[
        (paired["regime"] == "high")
        & (paired["gas_price_wei"] == GAS)
        & paired["pair"].isin(VOLATILE)
    ]
    out = {}
    for policy in HOOKS:
        d = sub[sub["policy"] == policy]["net_result_delta"]
        lo, hi = bootstrap_median_ci(d)
        out[policy] = (float(d.median()), lo, hi, len(d))
    return out


def corner_seeds(seeds_csv: str) -> dict[tuple[str, int], tuple[float, float, float]]:
    """The appendix replicate of the same estimand, per (policy, seed)."""
    df = pd.read_csv(ROOT / seeds_csv)
    ok = df[df["error"].isna()]
    sub = ok[(ok["regime"] == "high") & (ok["gas_price_wei"] == GAS)]
    out = {}
    for seed in SEEDS:
        s = sub[sub["seed"] == seed]
        base = s[s["policy"] == BASELINE].set_index(["pair", "window_start_ms"])[
            "net_result"
        ]
        for policy in HOOKS:
            pol = s[s["policy"] == policy].set_index(["pair", "window_start_ms"])[
                "net_result"
            ]
            d = (pol - base).dropna()
            lo, hi = bootstrap_median_ci(d)
            out[(policy, seed)] = (float(d.median()), lo, hi, len(d))
    return out


def main() -> None:
    fig, axes = plt.subplots(1, 2, figsize=(6.2, 4.6), sharey=True)
    fig.patch.set_facecolor(SURFACE)

    rows = []
    band = 1.0  # vertical space per policy cluster
    # matrix on top, seeds beneath, symmetric within the band
    inner = [0.325, 0.195, 0.065, -0.065, -0.195, -0.325]
    STRIPE = "#f3f2ef"  # alternating cluster background

    for ax, (label, matrix_csv, seeds_csv) in zip(axes, POINTS):
        matrix = corner_matrix(matrix_csv)
        seeds = corner_seeds(seeds_csv)

        ax.set_facecolor(SURFACE)
        ax.axvline(0, color="black", linewidth=0.7, zorder=1)

        for p_i, policy in enumerate(HOOKS):
            y0 = (len(HOOKS) - 1 - p_i) * band
            if p_i % 2 == 0:  # zebra stripe: unambiguous cluster boundaries
                ax.axhspan(y0 - band / 2, y0 + band / 2, color=STRIPE, zorder=0)
            entries = [("matrix", *matrix[policy])] + [
                (f"s{s}", *seeds[(policy, s)]) for s in SEEDS
            ]
            for (tag, med, lo, hi, n), dy in zip(entries, inner):
                is_matrix = tag == "matrix"
                wins, loses = lo > 0, hi < 0
                colour = ACCENT if wins else (ACCENT_ALT if loses else NEUTRAL)
                y = y0 + dy
                ax.plot(
                    [lo, hi],
                    [y, y],
                    color=colour,
                    linewidth=1.8 if is_matrix else 1.1,
                    alpha=1.0 if is_matrix else 0.75,
                    solid_capstyle="round",
                    zorder=3 if is_matrix else 2,
                )
                ax.plot(
                    med,
                    y,
                    marker="o",
                    markersize=5.6 if is_matrix else 3.6,
                    markerfacecolor=colour if (wins or loses) else SURFACE,
                    markeredgecolor=colour,
                    markeredgewidth=1.1,
                    zorder=4 if is_matrix else 3,
                )
                rows.append(
                    {
                        "operating_point": label,
                        "policy": policy,
                        "estimate": tag,
                        "n_windows": n,
                        "median": med,
                        "ci_low": lo,
                        "ci_high": hi,
                    }
                )

        ax.set_title(label, fontsize=10.5, color=INK)
        ax.grid(axis="x", color=GRID, linewidth=0.5, linestyle=(0, (1, 2)))
        ax.set_axisbelow(True)
        ax.tick_params(labelsize=9)
        ax.xaxis.set_major_locator(plt.MaxNLocator(5))
        ax.xaxis.set_major_formatter(
            plt.FuncFormatter(lambda v, _: f"{v / 1000:g}k" if v else "0")
        )

    handles = [
        plt.Line2D([], [], color="black", linewidth=1.8, marker="o",
                   markersize=5.6, markerfacecolor="black",
                   label="matrix of record (48 windows)"),
        plt.Line2D([], [], color="black", linewidth=1.1, marker="o",
                   markersize=3.6, markerfacecolor="white",
                   label="seed replicates (16 windows)"),
    ]
    ys = [(len(HOOKS) - 1 - i) * band for i in range(len(HOOKS))]
    axes[0].set_yticks(ys)
    axes[0].set_yticklabels(HOOKS, fontsize=9.5, color=INK)
    axes[0].set_ylim(min(ys) - band / 2, max(ys) + band / 2)
    fig.supxlabel(
        "median Δ vs static 30 bps in high-volatility windows at 5 gwei, USDT/window",
        fontsize=9.5,
        color=INK,
    )
    fig.tight_layout()
    # legend above the panels: inside any panel it collides with a cluster
    fig.subplots_adjust(top=0.86)
    legend = fig.legend(
        handles=handles,
        loc="upper center",
        bbox_to_anchor=(0.5, 1.0),
        ncol=2,
        fontsize=7.5,
        borderpad=0.5,
        handlelength=1.8,
        columnspacing=1.6,
    )
    legend.get_frame().set_linewidth(0.6)

    out = ROOT / "paper" / "Image" / "uu_seed_robustness.pdf"
    with figure_note(None):
        _save(fig, out, table=pd.DataFrame(rows))
    print(f"written: {out} (+ .csv)")


if __name__ == "__main__":
    main()
