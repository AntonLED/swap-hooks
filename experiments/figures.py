"""Figures for the paper.

Design decisions worth stating, because they are not arbitrary:

- **Policy is an axis, not a colour.** There are eleven configurations and any
  validated categorical palette carries eight hues; cycling them would make two
  policies share a colour. Small multiples and axis position carry identity
  instead, which also survives greyscale printing.
- **One accent hue.** Validated against the chart surface with the skill's
  checker; the contrast warning it raises is relieved by direct labels and by
  the CSV table every figure writes beside itself.
- **No dual axes anywhere.** Two measures of different scale get two panels.
- **Retained volume is never omitted.** Net result alone makes "charge the
  maximum so nobody trades" look like a win (spec §12.1).
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

import matplotlib

try:  # inside IPython/Jupyter keep whatever backend %matplotlib chose
    get_ipython()  # type: ignore[name-defined]  # noqa: F821
except NameError:
    matplotlib.use("Agg")

# The LaTeX look, without a LaTeX dependency: STIX is metrically and
# visually a Times clone (what IEEEtran sets the paper in), and mathtext
# rendered in the same face makes $\kappa$, subscripts and minus signs
# match the surrounding text exactly.
matplotlib.rcParams.update(
    {
        "font.family": "serif",
        "font.serif": ["STIXGeneral", "STIX Two Text", "Times New Roman"],
        "mathtext.fontset": "stix",
        # The pgfplots anatomy: a closed frame, ticks pointing inward and
        # mirrored on all four sides, a framed legend.
        "axes.linewidth": 0.6,
        "axes.edgecolor": "black",
        "xtick.direction": "in",
        "ytick.direction": "in",
        "xtick.top": True,
        "ytick.right": True,
        "xtick.major.size": 3.2,
        "ytick.major.size": 3.2,
        "legend.frameon": True,
        "legend.fancybox": False,
        "legend.framealpha": 1.0,
        "legend.edgecolor": "black",
    }
)
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from experiments.events import FEE_BOXES_BPS, applied_fees

# The pgfplots-look palette of 2026-08-14: restrained dark blue / brick red
# (win / loss), matching native TikZ figures in an IEEEtran page. The original
# pair ("#2a78d6"/"#eb6834") passed the dataviz palette checker; this darker
# pair keeps larger lightness separation from both white and the neutral grey.
ACCENT = "#1f4e9c"
ACCENT_ALT = "#c0392b"
INK = "#000000"
INK_MUTED = "#333333"  # secondary text; still near-black, the pgfplots way
NEUTRAL = "#6a6a6a"  # interval covers zero
GRID = "#cccccc"
SURFACE = "#ffffff"

REGIME_ORDER = ["low", "mid", "high"]


def order_policies(policies) -> list[str]:
    """Hooks first, alphabetically; then the static levels in ascending order.

    Alphabetical order alone interleaves `MyHook@10000` between the hooks, which
    is exactly the comparison a reader most wants kept together.
    """
    names = list(policies)
    hooks = sorted(n for n in names if not n.startswith("MyHook@"))
    statics = sorted(
        (n for n in names if n.startswith("MyHook@")),
        key=lambda n: int(n.removeprefix("MyHook@")),
    )
    return hooks + statics


def _style(ax) -> None:
    """Recessive grid and axes; the data is the only prominent thing."""
    ax.set_facecolor(SURFACE)
    ax.grid(True, axis="x", color=GRID, linewidth=0.6, zorder=0)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=INK_MUTED, labelsize=7, length=0)


# The caption every figure carries while a `figure_note` block is open. Module
# state rather than a parameter on all fourteen drawing functions: the note says
# WHICH RUN produced the figure, and a figure that omits it is the hazard, so it
# must not be possible to add a drawing function that forgets to thread it.
_FIGURE_NOTE: str | None = None


@contextmanager
def figure_note(note: str | None):
    """Stamp every figure drawn inside the block with `note`.

    The third experiment now has two operating points (κ = 1.0 and κ = 0.1) that
    produce the same set of figures with the same axes and different numbers.
    Told apart only by filename, two such PDFs are one careless drag away from
    being swapped in the paper, and neither would look wrong. So each says on
    its own face which configuration it came from.
    """
    global _FIGURE_NOTE
    previous = _FIGURE_NOTE
    _FIGURE_NOTE = note
    try:
        yield
    finally:
        _FIGURE_NOTE = previous


def _save(fig, out: Path, table: pd.DataFrame | None = None) -> None:
    fig.patch.set_facecolor(SURFACE)
    if _FIGURE_NOTE:
        # Bottom-left, muted, outside the axes: identification, not content.
        fig.text(0.0, -0.04, _FIGURE_NOTE, fontsize=6.5, color=INK_MUTED, ha="left")
    fig.savefig(out, bbox_inches="tight", facecolor=SURFACE)
    plt.close(fig)
    # The table view is the relief for the contrast warning, and it is what a
    # reader needs to check a number anyway.
    if table is not None:
        table.to_csv(Path(out).with_suffix(".csv"), index=False)


# The two co-primary valuations of the 2026-08-09 pre-registration, and how
# each is named on an axis. Both are the same LP-vs-HODL quantity; they differ
# only in the prices the leftover inventory is marked at, and the audit found
# that difference large enough to flip a conclusion's sign.
VALUATION_LABEL = {
    "net_result": "net LP result vs HODL, end-of-window prices",
    "net_result_tt": "net LP result vs HODL, trade-time prices",
}


def _valuation_label(value: str) -> str:
    return VALUATION_LABEL.get(value, value.replace("_", " "))


def _require(frame: pd.DataFrame, columns) -> None:
    """Fail on the missing column rather than drawing an empty axis.

    An arb-only frame has no UU column at all, and an empty panel reads as
    "the policy did nothing" -- which is a false finding, not a blank figure.
    """
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise KeyError(
            f"{', '.join(map(str, missing))} absent: "
            "this frame is not from a UU-flow run"
        )


def net_result_by_regime(
    frame: pd.DataFrame, out: Path, value: str = "net_result"
) -> None:
    """Horizontal bars, one panel per volatility regime.

    Policy sits on the axis because eleven of them exceed any categorical
    palette; the regimes are panels because comparing within a regime is the
    question and comparing across them is not.

    `value` selects the valuation. It defaults to the end-of-window one, so
    every existing call draws exactly what it drew before.
    """
    _require(frame, [value])
    grouped = (
        frame.groupby(["policy", "regime"], dropna=False)[value]
        .agg(["mean", "sem", "size"])
        .reset_index()
    )
    # Named in the table view: the two valuations otherwise write CSVs with
    # identical columns and a reader cannot tell which one they are holding.
    grouped["value"] = value
    # barh draws bottom-up, so reverse to read top-down in the intended order.
    policies = order_policies(frame["policy"].unique())[::-1]

    fig, axes = plt.subplots(1, 3, figsize=(9, 0.32 * len(policies) + 1.4), sharey=True)
    for ax, regime in zip(axes, REGIME_ORDER):
        subset = (
            grouped[grouped["regime"] == regime].set_index("policy").reindex(policies)
        )
        ax.barh(
            policies,
            subset["mean"].fillna(0),
            xerr=subset["sem"].fillna(0),
            color=ACCENT,
            height=0.62,
            error_kw={"ecolor": INK_MUTED, "elinewidth": 0.8, "capsize": 2},
            zorder=2,
        )
        ax.axvline(0, color=INK_MUTED, linewidth=0.8, zorder=1)
        ax.set_title(f"{regime} volatility", fontsize=8, color=INK)
        _style(ax)
    axes[0].set_ylabel("")
    fig.supxlabel(
        f"{_valuation_label(value)}, USDT per window (mean ± s.e.)",
        fontsize=8,
        color=INK,
    )
    _save(fig, out, grouped)


def _place_labels(ax, items) -> None:
    """Annotate points, moving each label to the first free slot.

    Hand-tuned offsets held only for one dataset: the frontier points move
    whenever the matrix is rerun, and three pairs of labels ended up overlapping.
    So the boxes are measured on a real renderer and each label takes the first
    candidate slot that touches nothing already placed. Anything that finds no
    free slot gets a leader line to a spot further out, rather than being
    silently dropped on top of a neighbour.

    `items` is a sequence of (x, y, text, colour).
    """
    # Candidates run near-to-far: right, left, above, below, then diagonals at
    # increasing distance. Nearest wins, so the common case stays tight.
    candidates = [
        (7, -2, "left", "center"),
        (-7, -2, "right", "center"),
        (0, 7, "center", "bottom"),
        (0, -9, "center", "top"),
        (7, 7, "left", "bottom"),
        (-7, 7, "right", "bottom"),
        (7, -10, "left", "top"),
        (-7, -10, "right", "top"),
        (0, 16, "center", "bottom"),
        (0, -18, "center", "top"),
        (0, 26, "center", "bottom"),
        (0, -28, "center", "top"),
    ]
    figure = ax.get_figure()
    figure.canvas.draw()
    renderer = figure.canvas.get_renderer()
    # A slot that leaves the axes is not free: MEVChargeHook sits at the left
    # edge, and its label ran out of the frame and over the y-axis title.
    frame_box = ax.get_window_extent(renderer)
    taken = []

    for x, y, text, colour in items:
        placed = None
        for dx, dy, ha, va in candidates:
            note = ax.annotate(
                text,
                (x, y),
                textcoords="offset points",
                xytext=(dx, dy),
                fontsize=7,
                color=colour,
                ha=ha,
                va=va,
                zorder=6,
            )
            # 1.5 pt of slack: boxes that merely touch still read as collided.
            box = note.get_window_extent(renderer).expanded(1.0, 1.15)
            inside = frame_box.contains(box.x0, box.y0) and frame_box.contains(
                box.x1, box.y1
            )
            if inside and not any(box.overlaps(other) for other in taken):
                taken.append(box)
                placed = note
                break
            note.remove()

        if placed is None:
            # Every slot was busy. Push it out with a leader line so the reader
            # can still tell which point it belongs to.
            note = ax.annotate(
                text,
                (x, y),
                textcoords="offset points",
                xytext=(0, 38),
                fontsize=7,
                color=colour,
                ha="center",
                va="bottom",
                zorder=6,
                arrowprops={"arrowstyle": "-", "color": GRID, "linewidth": 0.6},
            )
            taken.append(note.get_window_extent(renderer).expanded(1.0, 1.15))


def frontier(frame: pd.DataFrame, out: Path, value: str = "net_result") -> None:
    """Net result against retained volume.

    The static levels trace a curve; each dynamic policy is one point. Winning
    means sitting above that curve at the same retained volume — which is the
    only way to read a fee comparison without the degenerate "charge the
    maximum" answer.

    `value` selects the valuation; the default reproduces the arb-only figure.
    """
    _require(frame, [value])
    agg = (
        frame.groupby("policy", dropna=False)[["retained_volume", value]]
        .mean()
        .reset_index()
    )
    agg["value"] = value
    statics = agg[agg["policy"].str.startswith("MyHook@")].copy()
    statics["level"] = statics["policy"].str.removeprefix("MyHook@").astype(int)
    statics = statics.sort_values("retained_volume")
    dynamics = agg[~agg["policy"].str.startswith("MyHook@")]

    fig, ax = plt.subplots(figsize=(7.0, 4.4))
    ax.plot(
        statics["retained_volume"],
        statics[value],
        color=ACCENT,
        linewidth=2,
        marker="o",
        markersize=5,
        zorder=3,
        label="static fee",
    )
    ax.scatter(
        dynamics["retained_volume"],
        dynamics[value],
        color=ACCENT_ALT,
        s=42,
        zorder=4,
        label="dynamic policy",
    )
    # Room for the labels of the points that sit hard against the frame.
    ax.margins(x=0.13, y=0.10)
    ax.set_xlabel("retained volume, USDT per window", fontsize=8, color=INK)
    ax.set_ylabel(f"{_valuation_label(value)}, USDT", fontsize=8, color=INK)
    # Labelled after both series are drawn so collisions across the two are
    # visible to the placer -- "5 bps" against VolatilityHook was one of them.
    _place_labels(
        ax,
        [
            (
                r["retained_volume"],
                r[value],
                f"{r['level'] // 100} bps",
                INK_MUTED,
            )
            for _, r in statics.iterrows()
        ]
        + [
            (r["retained_volume"], r[value], r["policy"], INK)
            for _, r in dynamics.iterrows()
        ],
    )
    ax.legend(frameon=False, fontsize=7, labelcolor=INK_MUTED, loc="upper right")
    _style(ax)
    ax.grid(True, axis="y", color=GRID, linewidth=0.6, zorder=0)
    _save(fig, out, agg)


def gas_breakeven(
    frame: pd.DataFrame, out: Path, baseline: str = "MyHook@3000"
) -> None:
    """Advantage over the baseline against gas price, one panel per policy.

    Small multiples rather than seven lines in one frame: the crossing of zero
    is the number that matters, and a shared frame hides it in a thicket.
    """
    base = (
        frame[frame["policy"] == baseline].groupby("gas_price_wei")["net_result"].mean()
    )
    others = [p for p in order_policies(frame["policy"].unique()) if p != baseline]

    columns = 4
    rows = (len(others) + columns - 1) // columns
    fig, axes = plt.subplots(rows, columns, figsize=(9, 2.1 * rows), sharey=True)
    flat = axes.ravel() if hasattr(axes, "ravel") else [axes]

    records = []
    for ax, policy in zip(flat, others):
        series = (
            frame[frame["policy"] == policy]
            .groupby("gas_price_wei")["net_result"]
            .mean()
        )
        gwei = [g / 1e9 for g in series.index]
        delta = (series - base.reindex(series.index)).to_numpy()
        records += [
            {"policy": policy, "gwei": g, "net_result_delta": d}
            for g, d in zip(gwei, delta)
        ]

        # Three declared scenarios are categories, not a continuum: a log axis
        # renders them as an unreadable "6x10^0 2x10^1" smear.
        positions = list(range(len(gwei)))
        ax.axhline(0, color=INK_MUTED, linewidth=0.8, zorder=1)
        ax.plot(
            positions,
            delta,
            color=ACCENT,
            linewidth=2,
            marker="o",
            markersize=5,
            zorder=3,
        )
        ax.set_xticks(positions)
        ax.set_xticklabels([f"{g:g}" for g in gwei])
        ax.set_xlim(-0.35, len(positions) - 0.65)
        ax.set_title(policy, fontsize=8, color=INK)
        _style(ax)
        ax.grid(True, axis="y", color=GRID, linewidth=0.6, zorder=0)

    for ax in flat[len(others) :]:
        ax.set_visible(False)

    # Panel titles in a lower row otherwise sit on the tick labels above them.
    fig.subplots_adjust(hspace=0.55)
    fig.supxlabel("gas price, gwei", fontsize=8, color=INK)
    fig.supylabel(f"net result minus {baseline}, USDT", fontsize=8, color=INK)
    _save(fig, out, pd.DataFrame(records))


def fee_distribution(fees: pd.DataFrame, out: Path) -> None:
    """Where each policy's applied fee actually sits inside its own fee box.

    The question is whether a policy adapts or is pinned at a bound, and the
    histogram this replaces could not answer it. Four of its ten panels held an
    exact constant, which a histogram renders as a one-pixel spike that reads as
    an empty panel; it drew a single 1-100 bps box across every policy, which is
    MEVChargeHook's box off by a factor of ten and is not a box at all for the
    static levels; and it omitted MEVChargeHook entirely.

    Quantile intervals instead. A constant collapses to a dot, which is the
    truth about it rather than an artefact. The bounds are drawn per policy from
    `FEE_BOXES_BPS`, and the share pinned at one is written out, because "pinned"
    is the actual claim and a reader should not have to infer it from a bar that
    happens to touch a line.
    """
    pairs = [
        p for p in ("ETH/SHIB", "ETH/USDC", "USDC/USDT") if (fees["pair"] == p).any()
    ]
    policies = order_policies(fees["policy"].unique())[::-1]
    positions = {policy: i for i, policy in enumerate(policies)}

    fig, axes = plt.subplots(
        1,
        len(pairs),
        figsize=(4.3 * len(pairs), 0.34 * len(policies) + 1.5),
        sharey=True,
    )
    flat = axes.ravel() if hasattr(axes, "ravel") else [axes]

    records = []
    for ax, pair in zip(flat, pairs):
        subset = fees[fees["pair"] == pair]
        for policy in policies:
            values = subset[subset["policy"] == policy]["fee_bps"].to_numpy()
            y = positions[policy]
            low, high = FEE_BOXES_BPS.get(policy, (None, None))
            if low is not None:
                # The box belongs to the row, not to the frame: these differ by
                # an order of magnitude between policies.
                ax.plot(
                    [low, high],
                    [y, y],
                    color=GRID,
                    linewidth=4.5,
                    solid_capstyle="butt",
                    zorder=1,
                )
            if not len(values):
                continue
            q = {
                p: float(pd.Series(values).quantile(p))
                for p in (0.05, 0.25, 0.5, 0.75, 0.95)
            }
            ax.plot([q[0.05], q[0.95]], [y, y], color=ACCENT, linewidth=1.2, zorder=3)
            ax.plot(
                [q[0.25], q[0.75]],
                [y, y],
                color=ACCENT,
                linewidth=4.0,
                solid_capstyle="butt",
                zorder=4,
            )
            ax.plot(
                [q[0.5]], [y], marker="o", markersize=4.5, color=ACCENT_ALT, zorder=5
            )

            at_floor = float((values <= low).mean()) if low is not None else 0.0
            at_cap = float((values >= high).mean()) if high is not None else 0.0
            # Only the pinning worth reading; below a twentieth it is noise.
            pinned = []
            if at_floor >= 0.05:
                pinned.append(f"{at_floor:.0%} at floor")
            if at_cap >= 0.05:
                pinned.append(f"{at_cap:.0%} at cap")
            if pinned:
                ax.annotate(
                    ", ".join(pinned),
                    (q[0.95], y),
                    textcoords="offset points",
                    xytext=(5, 0),
                    fontsize=6,
                    color=INK_MUTED,
                    va="center",
                    zorder=6,
                )
            records.append(
                {
                    "policy": policy,
                    "pair": pair,
                    "n": len(values),
                    "p5_bps": q[0.05],
                    "median_bps": q[0.5],
                    "p95_bps": q[0.95],
                    "share_at_floor": at_floor,
                    "share_at_cap": at_cap,
                }
            )

        ax.set_xscale("log")
        ax.set_xlim(0.7, 3000)
        ax.set_xticks([1, 10, 100, 1000])
        ax.set_xticklabels(["1", "10", "100", "1000"])
        ax.minorticks_off()
        ax.set_yticks(range(len(policies)))
        ax.set_yticklabels(policies, fontsize=7)
        ax.set_title(pair, fontsize=8, color=INK)
        _style(ax)

    # Never "basis points" against pip values: Uniswap stores uint24 hundredths
    # of a bp, and the paper's Fig. 5 currently mislabels exactly this.
    fig.supxlabel(
        "applied fee, basis points (log scale). Grey bar is the policy's own fee box; "
        "line spans p5-p95, thick bar the quartiles, dot the median.",
        fontsize=7.5,
        color=INK,
    )
    _save(fig, out, pd.DataFrame(records))


def volatility_stratification(
    segments_by_pair: dict[str, pd.DataFrame],
    selected_by_pair: dict[str, pd.DataFrame],
    out: Path,
) -> None:
    """How the windows were chosen: every day of the year, the tercile cuts, and
    which 24 were taken.

    This figure exists because "we picked 24 windows" is the step a reader is
    most entitled to distrust. Showing all 366 days with the cuts drawn on them
    makes the rule checkable rather than asserted: no day was chosen by hand,
    and the picks are spread across the year rather than clustered in a season.

    Grey for every day, accent for the selected ones — a two-level contrast, not
    a categorical palette, because "selected" is not an identity but a state.
    """
    import datetime as _dt

    import matplotlib.dates as mdates

    pairs = list(segments_by_pair)
    fig, axes = plt.subplots(
        len(pairs), 1, figsize=(8.4, 2.5 * len(pairs)), sharex=True
    )
    flat = axes.ravel() if hasattr(axes, "ravel") else [axes]

    records = []
    for ax, pair in zip(flat, pairs):
        segments = segments_by_pair[pair]
        selected = selected_by_pair[pair]
        if segments.empty:
            ax.set_visible(False)
            continue

        dates = [
            _dt.datetime.fromtimestamp(t / 1000, tz=_dt.UTC)
            for t in segments["start_ms"]
        ]
        vol = segments["volatility"].to_numpy()

        # Tercile cuts, drawn where the sorted split actually falls.
        ordered = sorted(vol)
        n = len(ordered)
        cuts = [ordered[n // 3], ordered[2 * n // 3]]

        ax.scatter(dates, vol, s=9, color=GRID, zorder=2, label="all days")
        for cut in cuts:
            ax.axhline(
                cut, color=INK_MUTED, linewidth=0.8, linestyle=(0, (4, 3)), zorder=3
            )

        sel_dates = [
            _dt.datetime.fromtimestamp(t / 1000, tz=_dt.UTC)
            for t in selected["start_ms"]
        ]
        ax.scatter(
            sel_dates,
            selected["volatility"],
            s=34,
            color=ACCENT,
            zorder=4,
            label="selected window",
        )

        ax.set_yscale("log")
        ax.set_title(pair, fontsize=8, color=INK, loc="left")
        ax.set_ylabel("realised\nvolatility", fontsize=7, color=INK_MUTED)
        _style(ax)
        ax.grid(True, axis="y", color=GRID, linewidth=0.5, zorder=0)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b"))
        # A log axis labels every minor tick by default, which on this range is
        # a wall of "6x10^-2 4x10^-2 3x10^-2". Decades only.
        ax.yaxis.set_minor_formatter(matplotlib.ticker.NullFormatter())

        for regime in ("low", "mid", "high"):
            block = selected[selected["regime"] == regime]
            records.append(
                {
                    "pair": pair,
                    "regime": regime,
                    "n_selected": len(block),
                    "vol_min": float(block["volatility"].min()) if len(block) else None,
                    "vol_max": float(block["volatility"].max()) if len(block) else None,
                    "n_days_total": len(segments),
                    "tercile_cut_low": float(cuts[0]),
                    "tercile_cut_high": float(cuts[1]),
                }
            )

    flat[0].legend(
        frameon=False, fontsize=7, labelcolor=INK_MUTED, loc="upper right", ncol=2
    )
    fig.supxlabel(
        "2024; dashed lines are the tercile cuts, eight windows taken from each band",
        fontsize=8,
        color=INK,
    )
    fig.subplots_adjust(hspace=0.42)
    _save(fig, out, pd.DataFrame(records))


def capture_share_sensitivity(frame: pd.DataFrame, out: Path) -> None:
    """PegCapture against its own `captureShare`, with the volume it gives up.

    This is a sensitivity analysis, not a pre-registered comparison, and the
    figure has to say so: `captureShare` was fixed at 0.5 during implementation
    and the headline PegCapture result rests on it.

    Small multiples, and each net-result panel keeps its own y scale. High
    volatility moves by thousands and low volatility by hundreds; on a shared
    scale the low and mid curves flatten onto zero and the sign change -- the
    entire point of the sweep -- becomes invisible.

    The volume row is not optional. The parameter works by leaving the
    arbitrageur less, so "earns more" and "trades less" move together, and net
    result shown alone would reward the degenerate answer (spec §12.1).
    """
    frame = frame[frame["error"].isna()].copy()
    frame["share"] = frame["capture_share"] / 1e6

    fig, axes = plt.subplots(2, 3, figsize=(8.2, 4.2), sharex=True)
    records = []
    rows = [
        ("net_result", "net result vs HODL, USDT"),
        ("retained_volume", "retained volume, USDT"),
    ]
    for row, (column, label) in enumerate(rows):
        for col, regime in enumerate(REGIME_ORDER):
            ax = axes[row][col]
            series = (
                frame[frame["regime"] == regime]
                .groupby("share")[column]
                .mean()
                .sort_index()
            )
            ax.plot(
                series.index,
                series.to_numpy(),
                color=ACCENT,
                linewidth=1.6,
                marker="o",
                markersize=3.5,
                zorder=3,
            )
            # The value the matrix actually ran, so the reader can see where the
            # pre-registered number sits on a curve that did not choose it.
            ax.axvline(
                0.5, color=INK_MUTED, linewidth=0.8, linestyle=(0, (2, 3)), zorder=1
            )
            if column == "net_result":
                ax.axhline(0, color=INK_MUTED, linewidth=0.8, zorder=2)
                ax.set_title(f"{regime} volatility", fontsize=8, color=INK)
                records += [
                    {"regime": regime, "share": s, "net_result": v}
                    for s, v in series.items()
                ]
            if col == 0:
                ax.set_ylabel(label, fontsize=7.5, color=INK)
            if row == 1:
                ax.set_xlabel("captureShare", fontsize=8, color=INK)
            ax.margins(x=0.10, y=0.16)
            _style(ax)
            ax.grid(True, axis="y", color=GRID, linewidth=0.6, zorder=0)

    axes[0][0].annotate(
        "0.5 as run",
        (0.5, 1.0),
        xycoords=("data", "axes fraction"),
        textcoords="offset points",
        xytext=(3, -7),
        fontsize=6.5,
        color=INK_MUTED,
        va="top",
    )
    _save(fig, out, pd.DataFrame(records))


def valuation_comparison(frame: pd.DataFrame, out: Path) -> None:
    """Both co-primary valuations of the same policies, on one axis.

    The 2026-08-09 audit found the end-of-window valuation carries an inventory
    revaluation term large enough to flip a conclusion's sign: four arb-only
    comparisons changed verdict between the two. The pre-registration answers
    that by declaring both and requiring them side by side, so this figure
    exists to make a disagreement impossible to miss rather than something a
    reader has to reconstruct from two tables.

    A dumbbell, not two bar charts: what matters is the gap between the two
    marks for one policy, and a paired mark puts that gap on the page directly.
    """
    _require(frame, ["net_result", "net_result_tt"])
    agg = (
        frame.groupby("policy", dropna=False)[["net_result", "net_result_tt"]]
        .mean()
        .reset_index()
    )
    # Sign disagreement is the reportable event, so it is a column rather than
    # something the reader infers by comparing two numbers by eye. Exact zeros
    # count as agreement: a policy that neither wins nor loses under one
    # valuation is not evidence the two disagree.
    agg["disagrees"] = (agg["net_result"] * agg["net_result_tt"]) < 0
    agg["gap"] = agg["net_result_tt"] - agg["net_result"]

    policies = order_policies(agg["policy"].unique())[::-1]
    agg = agg.set_index("policy").reindex(policies).reset_index()
    positions = range(len(policies))

    fig, ax = plt.subplots(figsize=(7.0, 0.34 * len(policies) + 1.4))
    for y, row in zip(positions, agg.itertuples()):
        ax.plot(
            [row.net_result, row.net_result_tt],
            [y, y],
            color=GRID if not row.disagrees else INK_MUTED,
            linewidth=1.4 if row.disagrees else 1.0,
            zorder=2,
        )
    ax.scatter(
        agg["net_result"],
        list(positions),
        color=ACCENT,
        s=38,
        zorder=3,
        label="end-of-window prices",
    )
    ax.scatter(
        agg["net_result_tt"],
        list(positions),
        color=ACCENT_ALT,
        s=38,
        zorder=3,
        marker="D",
        label="trade-time prices",
    )
    ax.axvline(0, color=INK_MUTED, linewidth=0.8, zorder=1)
    ax.set_yticks(list(positions))
    ax.set_yticklabels(policies)
    ax.set_xlabel(
        "net LP result vs HODL, USDT per window (mean)", fontsize=8, color=INK
    )
    ax.legend(frameon=False, fontsize=7, labelcolor=INK_MUTED, loc="lower right")
    _style(ax)
    _save(fig, out, agg)


def uu_flow(frame: pd.DataFrame, out: Path) -> None:
    """What the uninformed-user flow actually did, per policy.

    Three panels, because a claim about discriminating between toxic and benign
    flow needs all three at once: what share of volume was retail, what share of
    that retail flow chose to trade, and what share of the fee income it paid.
    A policy that "wins" while retaining no retail flow has not discriminated,
    it has repeated the arb-only degeneracy under a new name.

    Participation is the calibration check the whole model rests on: it must
    fall as the static fee level rises, or the second blade of the scissors is
    not cutting.
    """
    _require(frame, ["uu_volume", "arb_volume", "uu_participation", "uu_fee_share"])
    grouped = frame.groupby("policy", dropna=False)
    agg = grouped.agg(
        uu_volume=("uu_volume", "mean"),
        arb_volume=("arb_volume", "mean"),
        uu_participation=("uu_participation", "mean"),
        uu_fee_share=("uu_fee_share", "mean"),
    ).reset_index()
    total = agg["uu_volume"] + agg["arb_volume"]
    # A cell with no volume at all has no share; zero would read as "all of it
    # was arbitrage", which is a different and false statement.
    agg["uu_share_of_volume"] = (agg["uu_volume"] / total).where(total > 0)

    policies = order_policies(agg["policy"].unique())[::-1]
    agg = agg.set_index("policy").reindex(policies).reset_index()

    panels = [
        ("uu_share_of_volume", "UU share of retained volume"),
        ("uu_participation", "UU participation P (volume-weighted)"),
        ("uu_fee_share", "UU share of fee income"),
    ]
    fig, axes = plt.subplots(1, 3, figsize=(9, 0.32 * len(policies) + 1.4), sharey=True)
    for ax, (column, title) in zip(axes, panels):
        ax.barh(
            policies,
            agg[column].fillna(0),
            color=ACCENT,
            height=0.62,
            zorder=2,
        )
        ax.set_xlim(0, 1)
        ax.set_title(title, fontsize=8, color=INK)
        _style(ax)
    axes[0].set_ylabel("")
    fig.supxlabel("fraction of the total (mean over cells)", fontsize=8, color=INK)
    _save(fig, out, agg)


def operating_points(table: pd.DataFrame, out: Path) -> None:
    """The same policies at both operating points of the third experiment.

    One panel per configuration, each on its **own** x-scale. Sharing an axis
    would be the more obvious choice and it would be the wrong one: the two runs
    differ by a factor of ten in retail flow, so every quantity denominated in
    USDT is ten times smaller in one of them. A shared axis would render the
    κ = 0.1 panel as a column of near-zero stubs and invite the reading that the
    policies stopped doing anything, when what changed is the size of the flow
    they act on. What transfers between panels is sign, rank, and whether an
    interval clears zero — and those are exactly what separate panels preserve.

    The policies are split into two rows by the size of their effect, each row
    on its own scale. Without the split the figure is unreadable: `PegDefence`
    loses eleven thousand USDT a window and sets an axis on which the entire
    contest between `DAHook`, `BAHook` and the baseline — a few hundred — is
    three pixels wide. Every policy still appears exactly once and no row is
    dropped; only the zoom differs, and each row says what its own is.

    Columns required: `configuration`, `policy`, `median`, `ci_low`, `ci_high`.
    An optional `subtitle`, constant within a configuration, becomes the panel
    title's second line — the baseline's own result belongs there, because a
    difference against a baseline that is losing money means something different
    from the same difference against one that is making it.
    """
    _require(table, ["configuration", "policy", "median", "ci_low", "ci_high"])
    configurations = list(dict.fromkeys(table["configuration"]))
    # Ranked once, by the first configuration, so a policy sits at the same
    # height in every panel and the eye can travel across.
    first = table[table["configuration"] == configurations[0]].set_index("policy")
    policies = list(first.sort_values("median", ascending=True).index)

    # Split on the widest interval a policy shows in ANY configuration, not on
    # its median: a policy whose median is small but whose interval runs to
    # thousands belongs with the wide ones, or the zoomed row gets an axis
    # stretched by a single whisker.
    reach = table.assign(
        reach=table[["median", "ci_low", "ci_high"]].abs().max(axis=1)
    ).groupby("policy")["reach"]
    near = [p for p in policies if reach.max().get(p, 0.0) <= NEAR_LIMIT]
    far = [p for p in policies if p not in near]
    groups = [(g, label) for g, label in ((near, "near"), (far, "far")) if g]

    fig, axes = plt.subplots(
        len(groups),
        len(configurations),
        figsize=(3.6 * len(configurations) + 1.2, 0.34 * len(policies) + 2.2),
        squeeze=False,
        gridspec_kw={"height_ratios": [len(g) for g, _ in groups], "hspace": 0.22},
    )
    for row, (group, _) in enumerate(groups):
        for column, configuration in enumerate(configurations):
            _operating_point_panel(
                axes[row][column],
                table[table["configuration"] == configuration],
                group,
                title=configuration if row == 0 else None,
                ylabels=column == 0,
            )
    fig.supxlabel(
        "median difference vs static 30 bps, USDT per window "
        "(95% bootstrap interval over strata; filled = excludes zero)\n"
        "every panel has its own scale — compare sign and rank across them, "
        "not distance",
        fontsize=8,
        color=INK,
    )
    _save(fig, out, table)


# Where the figure splits its two rows, in USDT per window. Chosen to separate
# the policies that compete with the baseline from the ones that lose by orders
# of magnitude, not tuned to a result: everything on either side of it keeps the
# sign and rank it has in the table beside the figure.
NEAR_LIMIT = 1_000.0


def _operating_point_panel(ax, frame, policies, title, ylabels) -> None:
    """One configuration × one effect-size group of `operating_points`."""
    subset = frame.set_index("policy").reindex(policies)
    centre = subset["median"].to_numpy(dtype=float)
    # errorbar wants distances from the point, and a bootstrap interval is not
    # symmetric about the median. Clipped at zero because a rounding crumb of
    # negative width makes matplotlib raise rather than draw.
    lower = np.clip(centre - subset["ci_low"].to_numpy(dtype=float), 0, None)
    upper = np.clip(subset["ci_high"].to_numpy(dtype=float) - centre, 0, None)
    clears_zero = (subset["ci_low"] > 0) | (subset["ci_high"] < 0)
    positions = np.arange(len(policies))

    ax.axvline(0, color=INK_MUTED, linewidth=0.8, zorder=1)
    ax.errorbar(
        centre,
        positions,
        xerr=np.vstack([lower, upper]),
        fmt="none",
        ecolor=GRID,
        elinewidth=1.6,
        zorder=2,
    )
    # Filled where the interval excludes zero, hollow where it does not: the
    # uncertainty sits in the figure rather than in a significance column the
    # reader has to look up somewhere else.
    ax.scatter(
        centre,
        positions,
        s=22,
        facecolors=np.where(clears_zero, ACCENT, SURFACE),
        edgecolors=ACCENT,
        linewidths=1.1,
        zorder=3,
    )
    ax.set_ylim(-0.6, len(policies) - 0.4)
    ax.set_yticks(positions)
    if ylabels:
        ax.set_yticklabels(policies)
    else:
        ax.set_yticklabels([])

    if title is not None:
        subtitle = subset["subtitle"].dropna() if "subtitle" in subset else []
        if len(subtitle):
            title = f"{title}\n{subtitle.iloc[0]}"
        ax.set_title(title, fontsize=8, color=INK)
    _style(ax)


def draw_all_uu(
    frame: pd.DataFrame,
    traces_dir: Path,
    figures_dir: Path,
    prefix: str = "uu_",
    note: str | None = None,
) -> list[Path]:
    """Every figure of the third experiment, in one call.

    Same reason `draw_all` exists: a figure reachable only from a notebook cell
    someone forgot to run is a figure that goes stale unnoticed, and one already
    did. Both valuations are drawn unconditionally — the pre-registration does
    not allow reporting one without the other.

    `traces_dir` is separate from the metrics directory because the UU matrix
    wrote its JSONL traces to `results/` and its metrics to `results-uu/matrix/`
    (`run_spec` never passed a `results_dir`, so `run_one` used its default).
    An empty traces directory raises here rather than drawing a fee figure from
    nothing — that exact silence is how `fee_distribution` went a whole matrix
    run without anyone noticing it was wrong.

    `prefix` names the operating point. The two configurations of the third
    experiment draw the identical figure set from different runs, and they must
    never write over each other: the pre-registration requires both be reported,
    so losing one to a filename collision loses the comparison itself.

    Returns the paths written, in order. The caller needs that rather than a
    glob: `uu_*` also matches `uu_t01_*`, so a notebook listing what it just
    produced was claiming the other configuration's figures as its own.
    """
    written: list[Path] = []
    with figure_note(note):
        for value in ("net_result", "net_result_tt"):
            suffix = "" if value == "net_result" else "_tt"
            written.append(figures_dir / f"{prefix}net_result_by_regime{suffix}.pdf")
            net_result_by_regime(frame, written[-1], value)
            written.append(figures_dir / f"{prefix}frontier{suffix}.pdf")
            frontier(frame, written[-1], value)
        written.append(figures_dir / f"{prefix}valuation_comparison.pdf")
        valuation_comparison(frame, written[-1])
        written.append(figures_dir / f"{prefix}flow.pdf")
        uu_flow(frame, written[-1])
        written.append(figures_dir / f"{prefix}gas_breakeven.pdf")
        gas_breakeven(frame, written[-1])

        traces_dir = Path(traces_dir)
        fees = applied_fees(traces_dir)
        if fees.empty:
            raise FileNotFoundError(
                f"no swap traces matched under {traces_dir}: the fee figures "
                "cannot be drawn from the per-cell metrics, only from the JSONL "
                "event logs"
            )
        fees.to_parquet(traces_dir / "applied_fees.parquet")
        written.append(figures_dir / f"{prefix}fee_distribution.pdf")
        fee_distribution(fees, written[-1])
    return written


def draw_all(frame: pd.DataFrame, results_dir: Path, figures_dir: Path) -> None:
    """Every matrix figure, in one call so that one call exercises all of them.

    Lives here rather than in the runner because the notebooks in `analysis/`
    are the intended way to draw these, and the runner should not be the only
    place that knows the full set. Nothing covered this path before, which is
    how `fee_distribution` sat imported-but-uncalled through a whole matrix run.
    """
    net_result_by_regime(frame, figures_dir / "net_result_by_regime.pdf")
    frontier(frame, figures_dir / "frontier.pdf")
    gas_breakeven(frame, figures_dir / "gas_breakeven.pdf")

    # Read from the retained swap traces, not from summary.csv: the applied fee
    # is per swap and never reaches the per-cell metrics. Traces land in
    # results/, one level above the per-cell metrics in results/matrix/.
    fees = applied_fees(results_dir)
    fees.to_parquet(results_dir / "applied_fees.parquet")
    fee_distribution(fees, figures_dir / "fee_distribution.pdf")


# The dynamic templates, in the order the paper introduces them. Static levels
# are not panels here: they would be flat lines, and the baseline already
# appears inside every panel as the dashed reference.
RESPONSE_POLICIES = [
    "PegCapture",
    "BAHook",
    "DAHook",
    "ABHook",
    "VolatilityHook",
    "MEVChargeHook",
]


def fee_response(
    trajectories: pd.DataFrame,
    prices: pd.Series,
    out: Path,
    baseline_bps: float = 30.0,
) -> None:
    """One window's price path, and what each policy charged through it.

    Small multiples on a shared x-axis so a price move can be traced down
    through every policy's response. One series per panel, so identity never
    rests on colour.

    The fee y-axis is **shared and logarithmic**, which is the honest choice
    rather than the flattering one. Fees across these policies span three
    decades, and per-panel scaling would magnify a 0.3 bps wobble into the same
    picture as a 300 bps swing. On a shared log axis the policies that barely
    move look like they barely move -- which is the finding, not a defect of the
    chart.

    Marks are observations at trades, held forward: a hook only revises its fee
    when it is called, so a step is what happened, not an interpolation.
    """
    policies = [p for p in RESPONSE_POLICIES if p in set(trajectories["policy"])]
    fig, axes = plt.subplots(
        len(policies) + 1,
        1,
        figsize=(7.2, 1.25 * len(policies) + 1.9),
        sharex=True,
        gridspec_kw={"height_ratios": [1.5] + [1] * len(policies)},
    )

    hours = prices.index / 60.0
    axes[0].plot(hours, prices.to_numpy(), color=INK_MUTED, linewidth=1.4, zorder=3)
    axes[0].set_ylabel("price,\nindexed", fontsize=7.5, color=INK)
    axes[0].set_title(
        "external token1-per-token0 price, indexed to the window open",
        fontsize=8,
        color=INK,
    )
    _style(axes[0])
    axes[0].grid(True, axis="y", color=GRID, linewidth=0.6, zorder=0)

    records = []
    for ax, policy in zip(axes[1:], policies):
        subset = trajectories[trajectories["policy"] == policy].sort_values("candle")
        ax.axhline(
            baseline_bps,
            color=INK_MUTED,
            linewidth=0.8,
            linestyle=(0, (4, 3)),
            zorder=2,
        )
        ax.plot(
            subset["candle"] / 60.0,
            subset["fee_bps"].to_numpy(),
            color=ACCENT,
            linewidth=1.2,
            drawstyle="steps-post",
            zorder=3,
        )
        ax.set_yscale("log")
        ax.set_ylim(0.7, 1500)
        ax.set_yticks([1, 10, 100, 1000])
        ax.set_yticklabels(["1", "10", "100", "1000"])
        ax.minorticks_off()
        # Direct label instead of a legend: one series per panel, so a legend box
        # would only repeat the name further from the mark. It sits on a surface
        # patch because MEVChargeHook fills the top of its panel and the bare
        # text landed on the line.
        ax.annotate(
            policy,
            (0.012, 0.93),
            xycoords="axes fraction",
            fontsize=7.5,
            color=INK,
            va="top",
            zorder=5,
            bbox={"facecolor": SURFACE, "edgecolor": "none", "pad": 1.5},
        )
        _style(ax)
        ax.grid(True, axis="y", color=GRID, linewidth=0.6, zorder=0)
        records += [
            {"policy": policy, "candle": int(c), "fee_bps": float(f)}
            for c, f in zip(subset["candle"], subset["fee_bps"])
        ]

    axes[-1].set_xlabel("hours into the window", fontsize=8, color=INK)
    fig.supylabel("applied fee, basis points (log)", fontsize=8, color=INK)
    fig.align_ylabels()
    _save(fig, out, pd.DataFrame(records))


def fee_response_detail(
    trajectories: pd.DataFrame,
    prices: pd.Series,
    policy: str,
    out: Path,
    directional: bool = True,
) -> None:
    """One policy's fee against the price it reacted to, at its own scale.

    The companion to `fee_response`, which shares a log axis across six policies
    so their magnitudes stay comparable and therefore flattens anything that
    moves by less than a decade. Here a single policy gets a linear axis fitted
    to its own range, so a two-basis-point adjustment is legible.

    x is trade index rather than clock time: a hook only revises its fee when it
    is called, so successive trades are its actual step sequence, and the gaps
    between them carry no fee information.

    **Units.** The y-axis is basis points, converted from the `uint24` pip value
    the pool stores. The paper's current Fig. 5 plots the raw pip values under a
    "bps" label, which reads as a 30% fee where the pool charges 30 bps.
    """
    subset = trajectories[trajectories["policy"] == policy].sort_values("candle")
    if subset.empty:
        raise ValueError(f"no trades recorded for {policy}")

    # The reference price at each trade, so both panels share the trade index.
    at_trade = prices.reindex(subset["candle"]).to_numpy()
    index = range(len(subset))

    fig, axes = plt.subplots(
        2, 1, figsize=(7.2, 4.4), sharex=True, gridspec_kw={"height_ratios": [1, 1]}
    )

    axes[0].plot(index, at_trade, color=ACCENT, linewidth=1.3, zorder=3)
    axes[0].set_ylabel("external price,\nindexed to window open", fontsize=8, color=INK)
    _style(axes[0])
    axes[0].grid(True, axis="y", color=GRID, linewidth=0.6, zorder=0)

    # Two views of the same hook, and the difference matters.
    #
    # `fee_bps` is what the trade paid, which for a directional policy is
    # whichever side the trade used -- so it jumps between the two whenever the
    # flow reverses, and a 23% reversal rate turns a smooth policy into a
    # sawtooth. That is a property of the order flow, not of the hook.
    #
    # The directional view plots the hook's own state, both sides at once. For
    # ABHook the two are mirrored about K/2 by construction, and seeing them
    # together is what shows the constant-sum mechanism rather than implying it.
    two_sided = (subset["fee_ab_bps"] != subset["fee_ba_bps"]).any()
    if directional and two_sided:
        for column, label, style in (
            ("fee_ab_bps", "fee on A→B", "-"),
            ("fee_ba_bps", "fee on B→A", "--"),
        ):
            axes[1].plot(
                index,
                subset[column].to_numpy(),
                color=ACCENT_ALT,
                linewidth=1.3,
                linestyle=style,
                drawstyle="steps-post",
                zorder=3,
                label=label,
            )
        # Two series, so a legend is required; it sits on a surface patch in
        # the top-left, which is the only corner both lines leave free.
        axes[1].legend(
            loc="upper left",
            fontsize=7,
            labelcolor=INK_MUTED,
            ncols=2,
            frameon=True,
            facecolor=SURFACE,
            edgecolor="none",
            framealpha=1.0,
            borderpad=0.3,
        )
        axes[1].margins(y=0.22)
    else:
        axes[1].plot(
            index,
            subset["fee_bps"].to_numpy(),
            color=ACCENT_ALT,
            linewidth=1.3,
            drawstyle="steps-post",
            zorder=3,
        )
    axes[1].set_ylabel("applied fee, basis points", fontsize=8, color=INK)
    axes[1].set_xlabel("trade index", fontsize=8, color=INK)
    _style(axes[1])
    axes[1].grid(True, axis="y", color=GRID, linewidth=0.6, zorder=0)

    axes[0].set_title(policy, fontsize=9, color=INK)
    fig.align_ylabels()
    _save(
        fig,
        out,
        pd.DataFrame(
            {
                "trade_index": list(index),
                "candle": subset["candle"].to_numpy(),
                "price_indexed": at_trade,
                "fee_bps": subset["fee_bps"].to_numpy(),
                "fee_ab_bps": subset["fee_ab_bps"].to_numpy(),
                "fee_ba_bps": subset["fee_ba_bps"].to_numpy(),
            }
        ),
    )


def kappa_response(tests: pd.DataFrame, curve: pd.DataFrame, out: Path) -> None:
    """Each policy's advantage over the baseline, against the retail scale.

    Two panels because the sweep answers two questions with different y units:
    does the *ranking* survive the retail/arbitrage mix (top), and does the
    static curve's interior optimum survive it (bottom). The x axis is turnover
    in baskets per day, log-spaced because the grid is.

    `tests` is `kappa_sensitivity.analyse(...)` and `curve` is
    `kappa_sensitivity.static_curve(...)` -- passed in rather than recomputed, so
    the figure draws exactly the numbers the notebook printed above it.
    """
    pooled = tests[(tests["valuation"] == "net_result") & (tests["regime"] == "ALL")]
    hooks = pooled[~pooled["policy"].str.startswith("MyHook@")]
    levels = sorted(curve.columns)

    fig, axes = plt.subplots(2, 1, figsize=(7.0, 6.4), sharex=True)

    top = axes[0]
    for policy in order_policies(hooks["policy"].unique()):
        row = hooks[hooks["policy"] == policy].sort_values("turnover_multiple")
        # An advantage that holds at every level is the thing the sweep is for.
        holds = bool((row["median"] > 0).all())
        colour = ACCENT if holds else INK_MUTED
        top.plot(
            row["turnover_multiple"],
            row["median"],
            marker="o",
            markersize=4,
            linewidth=1.8 if holds else 1.0,
            color=colour,
            zorder=3 if holds else 2,
        )
        last = row.iloc[-1]
        top.annotate(
            policy,
            (last["turnover_multiple"], last["median"]),
            textcoords="offset points",
            xytext=(5, 0),
            fontsize=7,
            color=colour,
            va="center",
        )
    top.axhline(0, color=INK_MUTED, linewidth=0.8, zorder=1)
    top.set_xscale("log")
    top.set_ylabel("median vs static 30 bps, USDT", fontsize=8, color=INK)
    top.set_title(
        "advantage over the static baseline, by retail scale", fontsize=8, color=INK
    )
    _style(top)

    bottom = axes[1]
    for bps in curve.index:
        values = curve.loc[bps, levels].to_numpy(dtype=float)
        emphasised = bps in (30.0, 60.0)
        bottom.plot(
            levels,
            values,
            marker="o",
            markersize=4,
            linewidth=1.6 if emphasised else 1.0,
            color=ACCENT if emphasised else INK_MUTED,
        )
        bottom.annotate(
            f"{bps:.0f} bps",
            (levels[-1], values[-1]),
            textcoords="offset points",
            xytext=(5, 0),
            fontsize=7,
            color=INK_MUTED,
            va="center",
        )
    bottom.set_xscale("log")
    bottom.set_xticks(levels)
    bottom.set_xticklabels([f"{v:g}x" for v in levels])
    bottom.set_xlabel("retail turnover, baskets per day", fontsize=8, color=INK)
    bottom.set_ylabel("net LP result, USDT", fontsize=8, color=INK)
    bottom.set_title("the static curve, by retail scale", fontsize=8, color=INK)
    _style(bottom)

    fig.subplots_adjust(right=0.84)
    _save(fig, out, pooled)


def seed_stability(table: pd.DataFrame, out: Path) -> None:
    """Every seed's estimate, so a unanimous sign is not mistaken for a
    precise one.

    One row per policy and pair, five marks, and the range drawn as a bar. The
    sign is the verdict the appendix licenses; the spread is what stops a single
    number being quoted for the size (`BAHook` on ETH/SHIB spans +22 to +697).
    """
    rows = table.sort_values(["pair", "policy"]).reset_index(drop=True)
    labels = [f"{r.policy}\n{r.pair}" for r in rows.itertuples()]
    positions = range(len(rows))

    fig, ax = plt.subplots(figsize=(7.0, 0.46 * len(rows) + 1.4))
    for y, r in zip(positions, rows.itertuples()):
        wins = r.seeds_positive == r.seeds
        colour = ACCENT if wins else ACCENT_ALT if r.seeds_positive == 0 else INK_MUTED
        ax.plot(
            [r.median_min, r.median_max], [y, y], color=colour, linewidth=3, alpha=0.35
        )
        ax.plot(r.median_median, y, marker="D", markersize=6, color=colour, zorder=3)
        ax.annotate(
            f"{r.seeds_positive}/{r.seeds} seeds positive",
            (r.median_max, y),
            textcoords="offset points",
            xytext=(8, 0),
            fontsize=6.5,
            color=INK_MUTED,
            va="center",
        )
    ax.axvline(0, color=INK_MUTED, linewidth=0.8, zorder=1)
    ax.set_yticks(list(positions))
    ax.set_yticklabels(labels, fontsize=7)
    ax.set_xlabel(
        "median difference vs static 30 bps, USDT (diamond = across-seed median,"
        " bar = full range)",
        fontsize=7.5,
        color=INK,
    )
    ax.margins(x=0.22)
    _style(ax)
    _save(fig, out, rows)
