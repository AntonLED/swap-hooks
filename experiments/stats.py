"""The pre-registered analysis plan of spec §12.1.

No single primary hypothesis: this evaluates a framework, and privileging one
pairing would quietly turn the work into a paper about that pairing. The whole
family of comparisons is declared in advance and the false discovery rate is
controlled across it.

Wilcoxon rather than a t-test because window-level LP P&L is heavy-tailed: one
large price move dominates, and a t-test on 24 observations puts that outlier
into its own denominator. Eight wins out of eight with one large value gives
p = 0.34 by t-test and significance by Wilcoxon.

Benjamini-Hochberg rather than Bonferroni because with ~90 comparisons the
Bonferroni threshold is 0.00056, which a Wilcoxon test on 24 windows cannot
reach even at 24 wins out of 24. Controlling the false discovery rate keeps the
design able to detect anything at all.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
from scipy import stats

ALPHA = 0.05
Q_FDR = 0.05


def wilcoxon_paired(deltas) -> dict:
    """Two-sided signed-rank test plus the effect size that must accompany it.

    A significance flag without an effect size is never reported: "significant"
    answers whether an effect exists, not whether it matters.
    """
    values = np.asarray([float(v) for v in deltas], dtype=float)
    # A missing difference is an ABSENT observation, not a zero one. Without
    # this, one NaN makes the median NaN and sends scipy down its error path,
    # so the comparison silently reports p = 1.0 -- indistinguishable from
    # "no effect". Reachable: `arb_profit_realized` is None on a pre-UU trace,
    # and notebook 05 tests every declared metric (2026-08-10 review).
    values = values[~np.isnan(values)]
    n = int(values.size)
    if n == 0:
        return {"p": 1.0, "median": 0.0, "win_rate": 0.0, "n": 0, "n_effective": 0}

    median = float(np.median(values))
    win_rate = float(np.mean(values > 0))

    # The signed-rank test discards exact ties, so `n` alone overstates the
    # evidence: on the stable pair almost every cell trades zero times in both
    # arms, and a comparison reported as n = 8 was run on a mean of 0.23 usable
    # differences. Report both, and never quote `n` as the sample size.
    non_zero = values[values != 0]
    if non_zero.size < 1:
        # Every difference is exactly zero: no evidence of any effect.
        return {
            "p": 1.0,
            "median": median,
            "win_rate": win_rate,
            "n": n,
            "n_effective": 0,
        }

    try:
        p = float(stats.wilcoxon(non_zero, alternative="two-sided").pvalue)
    except ValueError:
        p = 1.0
    return {
        "p": p,
        "median": median,
        "win_rate": win_rate,
        "n": n,
        "n_effective": int(non_zero.size),
    }


def bootstrap_median_ci(
    deltas,
    confidence: float = 0.95,
    resamples: int = 10_000,
    seed: int = 0,
) -> tuple[float, float]:
    """Percentile bootstrap interval for the median paired difference.

    A p-value answers whether an effect exists. It says nothing about how well
    the effect is pinned down, and that is what a reader of this work actually
    needs: "+341 USDT per day, 95% CI [a, b]" carries the uncertainty that
    "p < 0.05" hides.

    The gap is not hypothetical here. `ABHook` losing 79 USDT a day produces
    p = 0.00004 -- three orders of magnitude smaller than `DAHook` winning
    1,561 -- purely because the small loss is more consistent. Significance
    ranks by reliability; the interval ranks by size, with its own reliability
    attached.

    Percentile rather than BCa: the samples here are 24 paired windows, the
    statistic is a median, and the bias correction BCa adds is small against an
    interval this wide. Stated as a choice rather than hidden -- for a
    strongly skewed statistic BCa would be the better instrument.

    Seeded, so the number printed in a notebook does not move between runs of
    the same cell.
    """
    values = np.asarray([float(v) for v in deltas], dtype=float)
    values = values[~np.isnan(values)]
    if values.size == 0:
        return (float("nan"), float("nan"))
    if values.size == 1:
        return (float(values[0]), float(values[0]))

    rng = np.random.default_rng(seed)
    draws = rng.integers(0, values.size, size=(resamples, values.size))
    medians = np.median(values[draws], axis=1)

    tail = (1.0 - confidence) / 2.0
    low, high = np.quantile(medians, [tail, 1.0 - tail])
    return (float(low), float(high))


def benjamini_hochberg(pvalues, q: float = Q_FDR) -> list[bool]:
    """Flag the p-values whose false discovery rate is controlled at `q`.

    Sort ascending, compare the i-th against the sliding threshold (i/m)·q, take
    the largest passing index, and accept everything up to it. The threshold
    slides: the smallest p-value is judged by q/m, which is Bonferroni, and the
    largest by q.
    """
    values = list(pvalues)
    m = len(values)
    if m == 0:
        return []

    # `sorted()` on a list containing NaN leaves it unsorted -- every
    # comparison against NaN is False -- and the step-up threshold `rank/m*q`
    # is then applied to the wrong p-values, flipping verdicts for comparisons
    # that have nothing to do with the missing one. A test with no p-value
    # cannot be a discovery, so it enters as 1.0 and is never flagged, while
    # still counting toward `m` (dropping it would loosen every other
    # threshold). Found by two independent reviewers, 2026-08-10.
    values = [1.0 if v is None or math.isnan(float(v)) else float(v) for v in values]

    order = sorted(range(m), key=lambda i: values[i])
    largest_passing = -1
    for rank, index in enumerate(order, start=1):
        if values[index] <= rank / m * q:
            largest_passing = rank

    flags = [False] * m
    # Step-up: everything up to the largest passing rank is accepted, including
    # entries that failed their own threshold.
    for rank, index in enumerate(order, start=1):
        if rank <= largest_passing:
            flags[index] = True
    return flags


def analyse(
    paired: pd.DataFrame,
    value: str = "net_result_delta",
    strata: tuple[str, ...] = (
        "policy",
        "pair",
        "regime",
        "gas_price_wei",
        "address_mode",
    ),
    q: float = Q_FDR,
) -> pd.DataFrame:
    """Test every declared comparison, then control the FDR across the family."""
    if paired.empty:
        return pd.DataFrame()

    rows = []
    for keys, group in paired.groupby(list(strata), dropna=False):
        result = wilcoxon_paired(group[value])
        # The interval travels with every comparison, never on request. A
        # median without one is the number this project has most often been
        # tempted to over-read.
        low, high = bootstrap_median_ci(group[value])
        result["ci_low"] = low
        result["ci_high"] = high
        result["ci_excludes_zero"] = bool(low > 0 or high < 0)
        rows.append({**dict(zip(strata, keys)), **result})

    out = pd.DataFrame(rows)
    out["significant_fdr"] = benjamini_hochberg(out["p"].tolist(), q=q)
    return out.sort_values("p").reset_index(drop=True)
