"""Sensitivity of the UU-flow experiment to `kappa` -- the retail scale.

NOT part of any pre-registered analysis plan. See
`docs/superpowers/specs/2026-08-10-kappa-sensitivity-preregistration.md`, which
was written before this ran.

Why it exists. `kappa` fixes how much uninformed volume the model supplies, and
spec §3 of `2026-08-09-uu-flow-design.md` fixes it by one rule: mean daily UU
volume over 2024 equals one basket, "i.e. turnover 1x/day, mid-range for real
major pools". That sentence carries no citation and, more to the point, it sets
the retail scale on the *turnover* axis while the quantity that actually decides
the experiment is the **share of flow that is informed**. At the calibrated
value that share came out at 1-6%: a world with thirty retail traders per
arbitrageur, in which fee income trivially covers adverse selection and every
policy posts a profit.

So the sweep is expressed in the units a reader can judge -- daily turnover as a
multiple of the basket -- and reported against the arbitrage share of volume it
actually produced, which is the axis the literature parameterises.

Kept in its own results directory, and filtered by an exact filename shape, so
it can never be mistaken for or merged into the pre-registered matrix. That
discipline is not theoretical: a prefix match once let 504 `captureShare` cells
leak into a pre-registered figure.
"""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

from experiments.calibrate_gas import load as load_gas
from experiments.matrix import (
    BASKET_USDT,
    DEFAULT_GAS_ESTIMATE,
    GAS_SCENARIOS_WEI,
    load_windows,
)
from experiments.policies import by_name
from experiments.run_one import kappa_for_pair, run_one

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results" / "sensitivity"

PAIR = ("ETH/SHIB", "ETHUSDT", "SHIBUSDT")

# Multiples of the calibrated kappa, i.e. of "one basket of UU volume per day".
# Spread downward because that is the direction that matters: less retail means
# a larger informed share, and the open question is whether the interior
# optimum and the policy ranking survive when arbitrage stops being a rounding
# error. 1.0 is the pre-registered value and is re-run here rather than joined
# in from the matrix, so the sweep is self-contained and the overlap doubles as
# a consistency check.
TURNOVER_MULTIPLES = (0.03, 0.1, 0.3, 1.0, 3.0)

# Seven configurations, not twelve: the sweep answers "does the shape of the
# result survive", and that needs the static curve (to see whether the interior
# optimum moves), the winner, and the litmus. Running all twelve would cost
# nearly twice the time to re-derive rankings the main matrix already reports.
#
# `DAHook` was added on 2026-08-11: the corrected matrix made it the only policy
# with a positive median against the baseline (+245 USDT, 12 wins to 5), a role
# `BAHook` held on the withdrawn matrix. `BAHook` stays -- it is the one whose
# ranking the correction moved most, so how it responds to kappa is itself
# informative.
POLICIES = (
    "MyHook@500",
    "MyHook@3000",
    "MyHook@6000",
    "MyHook@10000",
    "DAHook",
    "BAHook",
    "ABHook",
)

# Eight per tercile rather than the matrix's 24. The sweep asks about the shape
# of the response across kappa, not about the smallest detectable effect at one
# kappa, and 24 windows keep the cost near two hours instead of six.
WINDOWS_PER_TERCILE = 8


def _one(job):
    policy_name, multiple, kappa, window, gas, estimate = job
    policy = by_name(policy_name)
    tag = f"k{multiple}-{policy_name}-{window['start_ms']}-{gas}"
    work = ROOT / ".work" / tag

    # One directory per turnover level. `run_one` names a trace from the seven
    # experiment axes and kappa is not one of them, so every level would write
    # over the last into a single directory -- the same collision that had the
    # UU matrix overwriting the arb-only traces. The captureShare sweep solved
    # it with an eighth filename field; a directory is the same protection and
    # leaves the seven-field shape (and therefore the exact-filename filters in
    # `events.py`) alone.
    level_dir = RESULTS / f"turnover-{multiple}"
    level_dir.mkdir(parents=True, exist_ok=True)
    base = {
        "policy": policy_name,
        "turnover_multiple": multiple,
        "uu_kappa": kappa,
        "window_start_ms": window["start_ms"],
        "regime": window.get("regime"),
        "gas_price_wei": gas,
    }
    try:
        metrics = run_one(
            policy.hook,
            PAIR[1],
            PAIR[2],
            window["start_ms"],
            window["end_ms"],
            fee_pips=policy.fee_pips,
            gas_price_wei=gas,
            gas_estimate=estimate,
            basket_usdt=BASKET_USDT,
            size_dependent=policy.size_dependent,
            work_dir=work,
            results_dir=level_dir,
            # Must match the matrix. Running the sweep in `share` while the
            # matrix runs `discrete` would sweep kappa through a different flow
            # model, and the 1.0x level would not reproduce the matrix at all.
            uu_mode="discrete",
            uu_seed=0,
            uu_kappa=kappa,
        )
        return {**base, **metrics, "error": None}
    except Exception as exc:  # noqa: BLE001
        return {**base, "error": f"{type(exc).__name__}: {exc}"}
    finally:
        import shutil

        shutil.rmtree(work, ignore_errors=True)


def run(workers: int = 8) -> pd.DataFrame:
    RESULTS.mkdir(parents=True, exist_ok=True)
    gas = load_gas()
    windows = load_windows(per_tercile=WINDOWS_PER_TERCILE)[PAIR[0]]
    calibrated = kappa_for_pair(PAIR[1], PAIR[2])

    jobs = [
        (
            policy,
            multiple,
            calibrated * multiple,
            window,
            gas_price,
            # The matrix's own fallback, not a second copy of it: MyHook@10000
            # has no calibrated estimate, so a different default would give the
            # arbitrageur a different entry threshold and the kappa = 1.0 level
            # would disagree with the matrix for a reason that is not kappa.
            gas.get(policy, DEFAULT_GAS_ESTIMATE),
        )
        for policy in POLICIES
        for multiple in TURNOVER_MULTIPLES
        for window in windows
        for gas_price in GAS_SCENARIOS_WEI
    ]
    print(
        f"{len(jobs)} cells: {len(POLICIES)} policies x "
        f"{len(TURNOVER_MULTIPLES)} turnover levels x {len(windows)} windows x "
        f"{len(GAS_SCENARIOS_WEI)} gas scenarios"
    )
    print(f"calibrated kappa(ETH/SHIB) = {calibrated!r}")

    rows = []
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_one, job) for job in jobs]
        for i, future in enumerate(as_completed(futures), 1):
            rows.append(future.result())
            if i % 50 == 0:
                print(f"  {i}/{len(jobs)}", flush=True)

    frame = pd.DataFrame(rows)
    frame.to_csv(RESULTS / "kappa.csv", index=False)
    return frame


def flow_composition(frame: pd.DataFrame) -> pd.DataFrame:
    """What each turnover level actually produced, on the axis that matters.

    `turnover_multiple` is an input; the arbitrage share of volume is what a
    reader of the dynamic-fee literature will want, because that is how toxic
    flow is normally parameterised. Reporting the input alone would hide that
    the mapping between the two is not linear -- less retail also means fewer
    price displacements for the arbitrageur to correct, so the informed share
    rises more slowly than dividing by kappa suggests.
    """
    ok = frame[frame["error"].isna()]
    grouped = ok.groupby("turnover_multiple")
    out = grouped.agg(
        uu_volume=("uu_volume", "sum"),
        arb_volume=("arb_volume", "sum"),
        uu_participation=("uu_participation", "mean"),
        net_result=("net_result", "mean"),
        net_result_tt=("net_result_tt", "mean"),
        trades=("trade_count", "mean"),
    )
    total = out["uu_volume"] + out["arb_volume"]
    out["arb_share_of_volume"] = (out["arb_volume"] / total).where(total > 0)
    return out.drop(columns=["uu_volume", "arb_volume"])


def static_curve(frame: pd.DataFrame) -> pd.DataFrame:
    """Net result against static fee level, one column per turnover level.

    This is the table the sweep exists for. The third experiment's headline is
    that an interior optimum appeared once retail flow could walk away; if that
    optimum only exists when retail is 97% of the flow, the headline is a
    statement about `kappa` and not about dynamic fees.
    """
    ok = frame[frame["error"].isna()]
    statics = ok[ok["policy"].str.startswith("MyHook@")].copy()
    statics["level_bps"] = (
        statics["policy"].str.removeprefix("MyHook@").astype(int) / 100
    )
    return statics.pivot_table(
        index="level_bps", columns="turnover_multiple", values="net_result"
    )


def analyse(
    frame: pd.DataFrame | None = None,
    baseline: str = "MyHook@3000",
) -> pd.DataFrame:
    """Each policy against the static baseline, paired by window, per kappa.

    Same machinery as the pre-registered analysis -- Wilcoxon signed-rank then
    Benjamini-Hochberg -- over its own family, and run on both valuations
    because the 2026-08-09 pre-registration declares them co-primary and does
    not allow one to be reported without the other.

    The baseline is re-paired *within* each turnover level. Pairing across
    levels would compare two different worlds and is not a comparison of
    policies at all.
    """
    from experiments.stats import benjamini_hochberg, wilcoxon_paired

    frame = pd.read_csv(RESULTS / "kappa.csv") if frame is None else frame
    ok = frame[frame["error"].isna()]
    key = ["window_start_ms", "gas_price_wei"]

    rows = []
    for valuation in ("net_result", "net_result_tt"):
        for multiple, level in ok.groupby("turnover_multiple"):
            base = level[level["policy"] == baseline].set_index(key)[valuation]
            for policy, group in level.groupby("policy"):
                if policy == baseline:
                    continue
                for regime, subset in list(group.groupby("regime")) + [("ALL", group)]:
                    indexed = subset.set_index(key)
                    deltas = (indexed[valuation] - base.reindex(indexed.index)).dropna()
                    rows.append(
                        {
                            "valuation": valuation,
                            "turnover_multiple": multiple,
                            "policy": policy,
                            "regime": regime,
                            "baseline": baseline,
                            **wilcoxon_paired(deltas),
                        }
                    )

    result = pd.DataFrame(rows)
    # Each valuation is its own family: they are the same comparisons measured
    # twice, and pooling them would let a win in one borrow significance from
    # the other.
    result["significant_fdr"] = False
    for valuation, group in result.groupby("valuation"):
        flags = benjamini_hochberg(group["p"].tolist())
        result.loc[group.index, "significant_fdr"] = flags

    RESULTS.mkdir(parents=True, exist_ok=True)
    result.to_csv(RESULTS / "kappa_tests.csv", index=False)
    return result


if __name__ == "__main__":
    f = run()
    print("\nerrors:", int(f["error"].notna().sum()))
    ok = f[f["error"].isna()]
    worst = (
        ok[["conservation_error_token0", "conservation_error_token1"]].abs().max().max()
    )
    print(f"worst conservation error: {worst:.2e}")

    print("\nwhat each turnover level produced:")
    print(flow_composition(f).round(4).to_string())

    print("\nnet result against static fee level, per turnover multiple:")
    print(static_curve(f).round(1).to_string())
