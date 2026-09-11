"""Loading, grouping and pairing of run results.

Pairing is per window, never per average. Window-to-window variation dwarfs the
effect being measured: a calm day loses the LP a few dollars and a stormy one
thousands, so comparing column means would drown the difference between
policies in noise that both of them share.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

# The baseline is named, not inferred. 30 bps is the level ABHook's constant sum
# K/2 coincides with, which makes that one pair exactly budget-matched.
BASELINE_POLICY = "MyHook@3000"

AXES = ["pair", "window_start_ms", "gas_price_wei", "address_mode"]

# Metrics differenced against the baseline, per window. Declared once here
# rather than spelled out at the call site: the UU experiment added a
# *co-primary* valuation (`net_result_tt`) and a flow split, and a hardcoded
# four-column list dropped them silently -- `analyse(paired,
# value="net_result_tt_delta")` raised KeyError, which is one keystroke away
# from reporting only whichever valuation is friendlier. Columns absent from
# the frame are skipped, so the frozen arb-only `summary.csv` still pairs.
PAIRED_METRICS = (
    "net_result",  # pre-registered, end-of-window valuation
    "net_result_tt",  # pre-registered co-primary, trade-time valuation
    "fee_income",
    "il",
    "retained_volume",
    "uu_volume",
    "arb_volume",
    "arb_profit_realized",
    "trade_count",
)

# Reported per stratum when the run produced them. Same rule: presence in the
# frame decides, so one function serves both experiments.
UU_REGIME_METRICS = (
    "net_result_tt",
    "uu_volume",
    "arb_volume",
    "uu_fee_share",
    "uu_participation",
    "arb_profit_realized",
)


def load_results(results_dir: Path) -> pd.DataFrame:
    """One row per completed run, metrics joined to their manifest."""
    rows = []
    for metrics_path in sorted(Path(results_dir).glob("*.metrics.json")):
        key = metrics_path.name.removesuffix(".metrics.json")
        manifest_path = metrics_path.with_name(f"{key}.manifest.json")
        if not manifest_path.exists():
            continue
        manifest = json.loads(manifest_path.read_text())
        window = manifest.get("W", {})
        rows.append(
            {
                "policy": manifest["C_theta"]["policy"],
                "pair": window.get("pair"),
                "window_start_ms": window.get("start_ms"),
                "regime": window.get("regime"),
                "gas_price_wei": manifest["S"].get("gas_price_wei"),
                "address_mode": manifest["S"].get("address_mode"),
                **json.loads(metrics_path.read_text()),
            }
        )
    return pd.DataFrame(rows)


def by_regime(frame: pd.DataFrame) -> pd.DataFrame:
    """Mean and standard error per policy, regime and gas scenario."""
    grouped = frame.groupby(["policy", "regime", "gas_price_wei"], dropna=False)
    aggregations = {
        "net_result_mean": ("net_result", "mean"),
        "net_result_sem": ("net_result", "sem"),
        # Retained volume travels with every metric: without it the degenerate
        # "charge the maximum and nobody trades" outcome looks like a win.
        "retained_volume_mean": ("retained_volume", "mean"),
        "fee_income_mean": ("fee_income", "mean"),
        "il_mean": ("il", "mean"),
        "gas_cost_mean": ("gas_cost", "mean"),
        "trade_count_mean": ("trade_count", "mean"),
        "n": ("net_result", "size"),
    }
    # Under UU flow the trade-time valuation is co-primary, and the volume
    # split is what separates "kept the benign flow" from "priced everyone
    # out" -- the distinction the whole third experiment exists to make.
    for column in UU_REGIME_METRICS:
        if column in frame.columns:
            aggregations[f"{column}_mean"] = (column, "mean")
    if "net_result_tt" in frame.columns:
        aggregations["net_result_tt_sem"] = ("net_result_tt", "sem")

    return grouped.agg(**aggregations).reset_index()


def paired_against_baseline(
    frame: pd.DataFrame, baseline_policy: str = BASELINE_POLICY
) -> pd.DataFrame:
    """Per-window difference of each policy against the baseline.

    Joined on every axis except the policy, so each difference compares two runs
    over identical data with identical settings.
    """
    baseline = frame[frame["policy"] == baseline_policy]
    others = frame[frame["policy"] != baseline_policy]
    if baseline.empty or others.empty:
        return pd.DataFrame()

    metrics = [column for column in PAIRED_METRICS if column in frame.columns]
    merged = others.merge(
        baseline[AXES + metrics],
        on=AXES,
        suffixes=("", "_baseline"),
        how="inner",
    )
    for column in metrics:
        merged[f"{column}_delta"] = merged[column] - merged[f"{column}_baseline"]
    return merged


# The two pairs whose price actually moves. USDC/USDT is held separately in
# every headline number: it is a peg, arbitrage is 7% of its volume, and most of
# its cells trade nothing at all, so pooling it in dilutes every effect toward
# zero without adding evidence about the mechanism.
VOLATILE_PAIRS = ("ETH/SHIB", "ETH/USDC")


def summarise_strata(
    tests: pd.DataFrame,
    pairs: tuple[str, ...] = VOLATILE_PAIRS,
    confidence: float = 0.95,
) -> pd.DataFrame:
    """One row per policy: the median of its per-stratum medians, with interval.

    The pre-registered unit of analysis is the stratum — policy × pair × regime
    × gas — and there are eighteen of them per policy across the volatile pairs.
    A headline number has to combine them, and this takes the **median across
    strata**, resampling strata rather than windows.

    That is deliberately the more conservative of the two available estimands.
    Pooling all 432 window-level differences into one bootstrap would give an
    interval roughly three times narrower, but it would be answering a different
    question — it treats three gas scenarios of the same window as three
    independent observations, which they are not. Resampling strata keeps the
    uncertainty that matters: whether the effect survives a change of regime,
    pair, or gas price.
    """
    from experiments.stats import bootstrap_median_ci

    subset = tests[tests["pair"].isin(pairs)]
    rows = []
    for policy, group in subset.groupby("policy"):
        medians = group["median"]
        low, high = bootstrap_median_ci(medians, confidence=confidence)
        rows.append(
            {
                "policy": policy,
                "median": float(medians.median()),
                "ci_low": low,
                "ci_high": high,
                "strata": len(medians),
                "strata_positive": int((medians > 0).sum()),
                "ci_excludes_zero": bool(low > 0 or high < 0),
            }
        )
    return pd.DataFrame(rows).sort_values("median", ascending=False, ignore_index=True)
