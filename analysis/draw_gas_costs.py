"""What one swap actually costs in gas, per policy — in dollars.

The gas story in the results (§10's gas gradient) rests on two measured
numbers per policy: its execution gas in the EVM and the scenario's gas
price. This figure turns them into money so the reader sees at a glance
that (a) an adaptive hook pays 'rent' on every swap that a static fee does
not, and (b) at congested gas that rent rivals the trading fee itself.

Gas per swap = the measured per-policy median (Forge EVM execution gas +
21,000 intrinsic, `experiments/gas_estimates.json`), valued at the mean
2024 ETH price. Independent of kappa, so one figure serves every operating
point. Writes paper/Image/uu_gas_cost_per_swap.{pdf,csv}.
"""

import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from experiments.figures import (
    ACCENT,
    GRID,
    INK,
    INK_MUTED,
    SURFACE,
    _save,
    figure_note,
)

ETH_USD = 3044.0  # mean 2024 ETHUSDT close, from the experiment's own data
GAS_GWEI = [5, 20, 80]
# One sequential ramp: light -> dark of the accent hue, magnitude = gas price.
SCENARIO_COLOUR = {5: "#a9c8ec", 20: ACCENT, 80: "#123c6e"}
REFERENCE_TRADE_USD = 4_000  # a typical retail trade at the calibrated kappa

POLICIES = [  # display order: static first, then hooks by measured gas
    ("MyHook@3000 (static)", "MyHook@3000"),
    ("DAHook", "DAHook"),
    ("ABHook", "ABHook"),
    ("MEVChargeHook", "MEVChargeHook"),
    ("BAHook", "BAHook"),
    ("VolatilityHook", "VolatilityHook"),
]


def main() -> None:
    gas = json.loads((ROOT / "experiments" / "gas_estimates.json").read_text())

    rows = []
    for label, key in POLICIES:
        for gwei in GAS_GWEI:
            usd = gas[key] * gwei * 1e9 * ETH_USD / 1e18
            rows.append(
                {
                    "policy": label,
                    "gas_units": gas[key],
                    "gas_price_gwei": gwei,
                    "usd_per_swap": round(usd, 3),
                    "bps_of_reference_trade": round(usd / REFERENCE_TRADE_USD * 1e4, 1),
                }
            )
    table = pd.DataFrame(rows)

    fig, ax = plt.subplots(figsize=(8.6, 4.6))
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)

    ys = list(range(len(POLICIES)))[::-1]
    for (label, key), y in zip(POLICIES, ys):
        sub = table[table["policy"] == label].sort_values("gas_price_gwei")
        xs = sub["usd_per_swap"].tolist()
        ax.plot(xs, [y] * 3, color=GRID, linewidth=1.4, zorder=1)
        for gwei, x in zip(GAS_GWEI, xs):
            ax.plot(
                x,
                y,
                marker="o",
                markersize=8,
                markerfacecolor=SCENARIO_COLOUR[gwei],
                markeredgecolor=SURFACE,
                markeredgewidth=1.2,
                zorder=3,
            )
        # Selective direct labels: the congested-gas value carries the story.
        ax.annotate(
            f"${xs[-1]:,.0f}",
            (xs[-1], y),
            textcoords="offset points",
            xytext=(10, -3),
            fontsize=8.5,
            color=INK,
        )

    ax.set_xscale("log")
    ax.set_xlim(0.9, 45)
    ax.set_xticks([1, 2, 5, 10, 20, 40])
    ax.set_xticklabels(["$1", "$2", "$5", "$10", "$20", "$40"])
    ax.set_yticks(ys)
    ax.set_yticklabels(
        [f"{label}\n{gas[key] / 1000:.0f}k gas" for label, key in POLICIES],
        fontsize=9,
        color=INK,
    )
    ax.set_xlabel("cost of one swap, USD (log scale)", fontsize=9, color=INK_MUTED)
    ax.grid(axis="x", color=GRID, linewidth=0.7)
    ax.set_axisbelow(True)
    for spine in ["top", "right", "left"]:
        ax.spines[spine].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(colors=INK_MUTED, labelsize=8.5)

    # Secondary axis: the same dollars as a share of a typical retail trade.
    top = ax.secondary_xaxis(
        "top",
        functions=(
            lambda usd: usd / REFERENCE_TRADE_USD * 1e4,
            lambda bps: bps * REFERENCE_TRADE_USD / 1e4,
        ),
    )
    top.set_xticks([2.5, 5, 12.5, 25, 50, 100])
    top.set_xticklabels(["2.5", "5", "12.5", "25", "50", "100"])
    top.set_xlabel(
        f"…as basis points of a ${REFERENCE_TRADE_USD:,} retail trade "
        "(the fee box tops out at 100 bps)",
        fontsize=8.5,
        color=INK_MUTED,
    )
    top.tick_params(colors=INK_MUTED, labelsize=8)
    top.spines["top"].set_color(GRID)

    handles = [
        plt.Line2D(
            [],
            [],
            marker="o",
            linestyle="",
            markersize=8,
            markerfacecolor=SCENARIO_COLOUR[g],
            markeredgecolor=SURFACE,
            label=f"{g} gwei",
        )
        for g in GAS_GWEI
    ]
    ax.legend(handles=handles, loc="upper right", frameon=False, fontsize=8.5)

    ax.set_title(
        "What one swap costs in gas: measured per-policy execution (Forge EVM) "
        f"valued at mean 2024 ETH = ${ETH_USD:,.0f}",
        fontsize=10,
        color=INK,
        pad=14,
    )
    fig.tight_layout()

    out = ROOT / "paper" / "Image" / "uu_gas_cost_per_swap.pdf"
    with figure_note(
        "per-policy median gas incl. 21k intrinsic (gas_estimates.json); "
        "independent of the operating point"
    ):
        _save(fig, out, table=table)
    print(f"written: {out} (+ .csv)")


if __name__ == "__main__":
    main()
