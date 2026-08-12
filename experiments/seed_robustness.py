"""Is the policy ranking a property of the policies, or of one lucky draw?

`discrete` mode draws a lognormal size and a uniform coin per candle per
direction, so the whole matrix is ONE realisation of a random process. Every
number reported from it -- `DAHook` +245 against the baseline, `BAHook` +506 on
ETH/SHIB -- comes from seed 0.

Under `share` the question did not arise: that mode is deterministic. The
randomness was introduced deliberately, to get the one-sided order flow that
makes the arbitrageur's presence meaningful (see
`2026-08-10-r-correction-preregistration.md`), and this is its price.

Required before any ranking is called stable: spec §2.4 of
`2026-08-09-uu-flow-design.md` ("a few reference cells x 5 seeds, kept under
`results/sensitivity/`") and repeated as a condition in the 2026-08-10
pre-registration. Until it passes, the paper may say "at this seed", not
"beats".

Reference cells, not the whole matrix: 5 x 7,776 would be ~8 hours to answer a
question that a well-chosen subset answers in fifteen minutes. The subset is
where the claim is actually made -- the two volatile pairs, the policies whose
advantage is asserted, and the canonical gas scenario.
"""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

from experiments.calibrate_gas import load as load_gas
from experiments.matrix import BASKET_USDT, DEFAULT_GAS_ESTIMATE, load_windows
from experiments.policies import by_name
from experiments.run_one import kappa_for_pair, run_one

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results" / "sensitivity"

SEEDS = (0, 1, 2, 3, 4)

# The baseline plus every policy whose advantage the paper would assert, plus
# the litmus. A stability check on a policy nobody claims anything about buys
# nothing.
POLICIES = ("MyHook@3000", "DAHook", "BAHook", "ABHook")

# The two volatile pairs. The claim being checked -- "adaptive fees beat a
# well-chosen static fee" -- is made only there; on USDC/USDT both policies
# lose significantly and there is no positive result whose stability is in
# question.
PAIRS = (("ETH/SHIB", "ETHUSDT", "SHIBUSDT"), ("ETH/USDC", "ETHUSDT", "USDCUSDT"))

# One gas scenario, the canonical one. Gas is a separate axis with its own
# result; re-running it five times over would triple the cost of this check
# without touching the question it asks.
GAS_PRICE_WEI = 20_000_000_000

WINDOWS_PER_TERCILE = 8

BASELINE = "MyHook@3000"


# The third experiment has two pre-registered operating points and this check is
# required at both, on the same terms. `turnover` selects which: 1.0 is the
# calibrated kappa of the headline matrix, 0.1 the informed-heavy second point of
# `2026-08-11-informed-share-preregistration.md`.
TURNOVER_DEFAULT = 1.0


def paths_for(turnover: float) -> tuple[Path, str]:
    """Output directory and filename stem for an operating point.

    Separate per turnover, and that is not a nicety. Two runs of this appendix
    at different kappa write cells with identical seven-field trace names, and
    `seeds.csv` carries no kappa column to tell them apart afterwards — so a
    shared path would silently blend two operating points into one table. That
    exact collision has already cost this project a set of traces (the UU matrix
    over the arb-only one) and a whole 26-minute run.
    """
    if turnover == TURNOVER_DEFAULT:
        return RESULTS, "seeds"
    return RESULTS / f"seeds-turnover-{turnover:g}", "seeds"


def _one(job):
    policy_name, pair, seed, window, estimate, turnover = job
    policy = by_name(policy_name)
    pair_name, symbol0, symbol1 = pair
    work = ROOT / ".work" / f"seed{seed}-{policy_name}-{pair_name}-{window['start_ms']}"

    # One directory per seed, for the same reason the kappa sweep uses one per
    # turnover level: `run_one` names a trace from the seven experiment axes and
    # the seed is not one of them, so a shared directory would have each seed
    # overwrite the last.
    root, _ = paths_for(turnover)
    level_dir = root / f"seed-{seed}"
    level_dir.mkdir(parents=True, exist_ok=True)

    # None means "use the calibrated value", exactly as the matrix does, so the
    # headline configuration keeps running through the identical code path it
    # always did rather than through a multiply-by-one.
    kappa = (
        None
        if turnover == TURNOVER_DEFAULT
        else kappa_for_pair(symbol0, symbol1) * turnover
    )

    base = {
        "policy": policy_name,
        "pair": pair_name,
        "seed": seed,
        "window_start_ms": window["start_ms"],
        "regime": window.get("regime"),
        "gas_price_wei": GAS_PRICE_WEI,
        # Recorded per row: without it two operating points' tables are
        # indistinguishable once they leave this module.
        "turnover_multiple": turnover,
        "uu_kappa": kappa,
    }
    try:
        metrics = run_one(
            policy.hook,
            symbol0,
            symbol1,
            window["start_ms"],
            window["end_ms"],
            fee_pips=policy.fee_pips,
            gas_price_wei=GAS_PRICE_WEI,
            gas_estimate=estimate,
            basket_usdt=BASKET_USDT,
            size_dependent=policy.size_dependent,
            work_dir=work,
            results_dir=level_dir,
            uu_mode="discrete",
            uu_seed=seed,
            uu_kappa=kappa,
        )
        return {**base, **metrics, "error": None}
    except Exception as exc:  # noqa: BLE001
        return {**base, "error": f"{type(exc).__name__}: {exc}"}
    finally:
        import shutil

        shutil.rmtree(work, ignore_errors=True)


def run(workers: int = 10, turnover: float = TURNOVER_DEFAULT) -> pd.DataFrame:
    root, stem = paths_for(turnover)
    root.mkdir(parents=True, exist_ok=True)
    gas = load_gas()
    windows = load_windows(per_tercile=WINDOWS_PER_TERCILE)

    jobs = [
        (policy, pair, seed, window, gas.get(policy, DEFAULT_GAS_ESTIMATE), turnover)
        for policy in POLICIES
        for pair in PAIRS
        for seed in SEEDS
        for window in windows[pair[0]]
    ]
    print(
        f"{len(jobs)} cells: {len(POLICIES)} policies x {len(PAIRS)} pairs x "
        f"{len(SEEDS)} seeds x {len(windows[PAIRS[0][0]])} windows "
        f"at {turnover:g}x the calibrated kappa -> {root.relative_to(ROOT)}/"
    )

    rows = []
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_one, job) for job in jobs]
        for i, future in enumerate(as_completed(futures), 1):
            rows.append(future.result())
            if i % 50 == 0:
                print(f"  {i}/{len(jobs)}", flush=True)

    frame = pd.DataFrame(rows)
    frame.to_csv(root / f"{stem}.csv", index=False)
    return frame


def analyse(
    frame: pd.DataFrame | None = None,
    write: bool | None = None,
    turnover: float = TURNOVER_DEFAULT,
) -> pd.DataFrame:
    """Per seed and pair, each policy against the baseline, paired by window.

    The baseline is re-paired WITHIN a seed. Pairing across seeds would compare
    two different realisations and is not a comparison of policies at all.

    `write` controls whether `seed_tests.csv` is rewritten. It defaults to
    "only when reading the real run from disk", because this function used to
    write unconditionally: **every unit-test run silently overwrote the real
    `results/sensitivity/seed_tests.csv` with fixture medians** of exactly
    ±200/±100, and the file on disk had been fixture data for an unknown time
    when this was found on 2026-08-11. Nothing published was wrong -- `seeds.csv`
    is the record and was untouched, and `paper/Image/seed_stability.csv`
    predates the damage -- but a real artifact was destroyed by running the
    tests, which is the third occurrence of "a run wrote where it should not"
    in three days.
    """
    from experiments.stats import wilcoxon_paired

    root, stem = paths_for(turnover)
    if write is None:
        write = frame is None
    frame = pd.read_csv(root / f"{stem}.csv") if frame is None else frame
    ok = frame[frame["error"].isna()]

    rows = []
    for (pair, seed), group in ok.groupby(["pair", "seed"]):
        base = group[group["policy"] == BASELINE].set_index("window_start_ms")
        for policy, sub in group.groupby("policy"):
            if policy == BASELINE:
                continue
            indexed = sub.set_index("window_start_ms")
            for valuation in ("net_result", "net_result_tt"):
                deltas = (
                    indexed[valuation] - base[valuation].reindex(indexed.index)
                ).dropna()
                rows.append(
                    {
                        "pair": pair,
                        "seed": seed,
                        "policy": policy,
                        "valuation": valuation,
                        **wilcoxon_paired(deltas),
                    }
                )
    result = pd.DataFrame(rows)
    if write:
        root.mkdir(parents=True, exist_ok=True)
        result.to_csv(root / "seed_tests.csv", index=False)
    return result


def stability(
    tests: pd.DataFrame | None = None, turnover: float = TURNOVER_DEFAULT
) -> pd.DataFrame:
    """Does the sign of the advantage survive every seed?

    This is the whole point of the appendix, so it is a table rather than a
    paragraph: for each policy and pair, how many of the seeds put the median on
    the same side of zero, and how far the estimate moves between them.

    A policy whose sign is unanimous across seeds may be reported as beating (or
    losing to) the baseline. One that flips may only be reported per seed.
    """
    root, _ = paths_for(turnover)
    tests = pd.read_csv(root / "seed_tests.csv") if tests is None else tests
    end = tests[tests["valuation"] == "net_result"]

    rows = []
    for (pair, policy), group in end.groupby(["pair", "policy"]):
        medians = group["median"]
        positive = int((medians > 0).sum())
        rows.append(
            {
                "pair": pair,
                "policy": policy,
                "seeds": len(group),
                "seeds_positive": positive,
                "unanimous": positive in (0, len(group)),
                "median_min": medians.min(),
                "median_median": medians.median(),
                "median_max": medians.max(),
                "spread": medians.max() - medians.min(),
            }
        )
    return pd.DataFrame(rows).sort_values(["pair", "policy"])


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--turnover",
        type=float,
        default=TURNOVER_DEFAULT,
        help=(
            "retail scale as a multiple of the calibrated kappa. 1.0 is the "
            "headline matrix; 0.1 the informed-heavy second operating point. "
            "Anything but 1.0 writes to its own directory."
        ),
    )
    parser.add_argument("--workers", type=int, default=10)
    args = parser.parse_args()

    frame = run(workers=args.workers, turnover=args.turnover)
    print(f"\nerrors: {int(frame['error'].notna().sum())}")
    ok = frame[frame["error"].isna()]
    worst = (
        ok[["conservation_error_token0", "conservation_error_token1"]].abs().max().max()
    )
    print(f"worst conservation error: {worst:.2e}")

    # The axis this operating point is chosen on, measured rather than assumed.
    arb = ok["arb_volume"].sum()
    print(f"arbitrage share of volume: {arb / (arb + ok['uu_volume'].sum()):.3f}")

    tests = analyse(frame, write=True, turnover=args.turnover)
    table = stability(tests)
    print("\nsign stability across seeds (end-of-window valuation):")
    print(table.round(1).to_string(index=False))

    flipped = table[~table["unanimous"]]
    if len(flipped):
        print("\nNOT unanimous -- these may only be reported per seed:")
        print(
            flipped[["pair", "policy", "seeds_positive", "seeds"]].to_string(
                index=False
            )
        )
    else:
        print("\nEvery policy keeps its sign across all seeds.")
