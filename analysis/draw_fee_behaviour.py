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
    INK_MUTED,
    SURFACE,
    figure_note,
    _save,
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
    ax.tick_params(labelsize=8)
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
        figsize=(7.2, 1.15 * len(HOOKS) + 1.9),
        sharex=True,
        gridspec_kw={"height_ratios": [1.5] + [1] * len(HOOKS)},
    )
    fig.patch.set_facecolor(SURFACE)

    hours = prices.index / 60.0
    axes[0].plot(hours, prices.to_numpy(), color=INK, linewidth=1.3, zorder=3)
    axes[0].set_ylabel("price,\nindexed", fontsize=7.5, color=INK)
    _style(axes[0])

    records = []
    for ax, policy in zip(axes[1:], HOOKS):
        swaps = per_policy[policy]
        candles = [s["candle"] for s in swaps]
        ab = [s["feeAB"] / 100.0 for s in swaps]
        ba = [s["feeBA"] / 100.0 for s in swaps]
        hrs = [c / 60.0 for c in candles]

        ax.axhline(30, color=INK, linewidth=0.8, linestyle=(0, (4, 3)), zorder=2)
        ax.plot(
            hrs,
            ab,
            color=ACCENT,
            linewidth=1.2,
            drawstyle="steps-post",
            zorder=3,
            label=r"fee A$\rightarrow$B",
        )
        ax.plot(
            hrs,
            ba,
            color=ACCENT_ALT,
            linewidth=1.2,
            drawstyle="steps-post",
            zorder=3,
            label=r"fee B$\rightarrow$A",
        )
        ax.set_yscale("log")
        ax.set_ylim(0.7, 1500)
        ax.set_yticks([1, 10, 100, 1000])
        ax.set_yticklabels(["1", "10", "100", "1000"])
        ax.minorticks_off()
        ax.annotate(
            policy,
            (0.012, 0.93),
            xycoords="axes fraction",
            fontsize=8.5,
            color=INK,
            va="top",
            zorder=5,
            bbox={"facecolor": SURFACE, "edgecolor": "none", "pad": 1.5},
        )
        _style(ax)
        records += [
            {"policy": policy, "candle": c, "fee_ab_bps": a, "fee_ba_bps": b}
            for c, a, b in zip(candles, ab, ba)
        ]

    axes[1].legend(loc="lower left", frameon=True, fontsize=8, ncol=2)
    axes[-1].set_xlabel("hours into the window", fontsize=9, color=INK)
    fig.supylabel("applied fee by direction, basis points (log)", fontsize=9, color=INK)
    fig.align_ylabels()
    fig.tight_layout()

    out = ROOT / "paper" / "Image" / "uu_fee_response.pdf"
    with figure_note(None):
        _save(fig, out, pd.DataFrame(records))
    print(f"written: {out} (+ .csv)")


if __name__ == "__main__":
    main()
