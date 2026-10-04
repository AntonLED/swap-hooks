"""Per-policy fee behaviour through one example day, from the UU traces.

The successor of the retired arb-only fee_detail figures, in the visual
style of the group's original two-panel plot (price on top, fee
trajectory below) — but from the experiment of record (kappa = 1 matrix
traces, both flows live) and honest about direction: each panel draws
the two directional fee series feeAB / feeBA separately, so directional
ratchets show two smooth trajectories instead of the sawtooth an
interleaved "fee of the executed swap" produces. Symmetric policies
collapse to one visible line.

One representative high-volatility ETH/SHIB window, middle gas scenario.
Writes paper/Image/uu_fee_response.{pdf,csv}.
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
    ACCENT_ALT,
    GRID,
    INK,
    SURFACE,
    _save,
    figure_note,
    snug_suplabel,
)

WINDOW_MS = 1_709_251_200_000  # 2024-03-01: a genuinely stormy ETH/SHIB day
GAS = 20_000_000_000
HOOKS = ["BAHook", "DAHook", "ABHook", "VolatilityHook", "MEVChargeHook"]


def load_swaps(policy: str):
    path = (
        ROOT
        / "results-uu"
        / (f"{policy}-0-ETHUSDT-SHIBUSDT-{WINDOW_MS}-{GAS}-persistent.jsonl")
    )
    return [r for r in map(json.loads, path.open()) if r.get("kind") == "swap"]


def _style(ax):
    ax.set_facecolor(SURFACE)
    ax.tick_params(labelsize=10)
    ax.grid(True, axis="y", color=GRID, linewidth=0.5, linestyle=(0, (1, 2)), zorder=0)
    ax.set_axisbelow(True)


def main() -> None:
    per_policy = {p: load_swaps(p) for p in HOOKS}

    price_rows = {}
    for s in next(iter(per_policy.values())):
        price_rows.setdefault(s["candle"], s["extPrice0"] / s["extPrice1"])
    prices = pd.Series(price_rows).sort_index()
    prices = prices / prices.iloc[0]

    fig, axes = plt.subplots(
        len(HOOKS) + 1,
        1,
        # Printed at .82\textwidth (~5.9 in), so a 7.2 in canvas cost a 0.83
        # downscale. A 6.4 in canvas plus larger point sizes lands every label
        # above 8 pt on the page while keeping the same aspect.
        figsize=(6.1, 1.0 * len(HOOKS) + 1.75),
        sharex=True,
        gridspec_kw={"height_ratios": [1.5] + [1] * len(HOOKS)},
    )
    fig.patch.set_facecolor(SURFACE)

    hours = prices.index / 60.0
    axes[0].plot(hours, prices.to_numpy(), color=INK, linewidth=1.3, zorder=3)
    axes[0].set_ylabel("price,\nindexed", fontsize=9.5, color=INK)
    _style(axes[0])

    records = []
    grid_idx = pd.RangeIndex(int(prices.index.min()), int(prices.index.max()) + 1)
    for ax, policy in zip(axes[1:], HOOKS):
        swaps = per_policy[policy]
        # Fee STATE on the minute grid, not raw per-swap samples: the fee a
        # policy quotes persists between swaps, so forward-filling the last
        # seen value per candle is the honest trajectory — and it removes the
        # sawtooth that made the per-swap rendering look ragged.
        frame = (
            pd.DataFrame(
                {
                    "candle": [s["candle"] for s in swaps],
                    "ab": [s["feeAB"] / 100.0 for s in swaps],
                    "ba": [s["feeBA"] / 100.0 for s in swaps],
                }
            )
            .groupby("candle")
            .last()
            .reindex(grid_idx)
            .ffill()
            .dropna()
        )
        hrs = frame.index / 60.0

        ax.axhline(30, color=INK, linewidth=0.8, linestyle=(0, (4, 3)), zorder=2)
        ax.plot(
            hrs,
            frame["ab"],
            color=ACCENT,
            linewidth=1.0,
            drawstyle="steps-post",
            zorder=3,
            label=r"fee A$\rightarrow$B",
        )
        ax.plot(
            hrs,
            frame["ba"],
            color=ACCENT_ALT,
            linewidth=1.0,
            drawstyle="steps-post",
            zorder=3,
            label=r"fee B$\rightarrow$A",
        )
        # Linear axis over the fee box: the box is [1, 100] bps, and a log
        # axis to 1000 both wastes headroom and blows every touch of the
        # 1 bps floor into a chasm.
        ax.set_ylim(-4, 108)
        ax.set_yticks([0, 30, 60, 100])
        ax.annotate(
            policy,
            (0.012, 0.93),
            xycoords="axes fraction",
            fontsize=10.5,
            color=INK,
            va="top",
            zorder=5,
            bbox={"facecolor": SURFACE, "edgecolor": "none", "pad": 1.5},
        )
        _style(ax)
        records += [
            {"policy": policy, "candle": int(c), "fee_ab_bps": a, "fee_ba_bps": b}
            for c, a, b in zip(frame.index, frame["ab"], frame["ba"])
        ]

    legend = axes[1].legend(
        loc="upper left", bbox_to_anchor=(0.16, 1.0), frameon=True, fontsize=10, ncol=2
    )
    legend.get_frame().set_linewidth(0.6)
    axes[-1].set_xlabel("hours into the window", fontsize=11, color=INK)
    # Short form: the legend already names the two directions and the caption
    # spells out the colour convention. A rotated label costs one line-height
    # of width whatever its length, so the saving goes straight into size.
    ylabel = fig.supylabel("applied fee, bps", fontsize=11.5, color=INK)
    fig.align_ylabels()
    fig.tight_layout()
    snug_suplabel(fig, ylabel, axes)

    out = ROOT / "paper" / "Image" / "uu_fee_response.pdf"
    with figure_note(None):
        _save(fig, out, pd.DataFrame(records))
    print(f"written: {out} (+ .csv)")


if __name__ == "__main__":
    main()
