"""Manual end-to-end verification for UU flow (spec §10.3-10.5).

Not a pytest module: it shells out to Forge on real network data and takes
minutes to run. Invoke as a module (a plain `python experiments/check_uu.py`
fails to import the `experiments` package, since only the script's own
directory lands on `sys.path` that way):

    uv run python -m experiments.check_uu

Two checks, both against the golden window (ETH/SHIB, 2024-01-01, one day),
UU flow on (share mode, canonical lambda):

  1. Degeneracy is gone (spec §10.5, the point of this whole feature): under
     arbitrage-only flow every trade is a net loss to the LP by construction,
     so static net_result vs fee level improves monotonically as volume is
     suppressed. With UU flow on, raising the fee now also costs retained
     retail revenue, so an interior optimum should exist: static net_result
     across {500, 3000, 6000, 10000} pips should be NON-monotone.

     If it is still monotone at the canonical lambda, this prints the four
     numbers and STOPS. Lambda recalibration is the owner's call, recorded in
     the prereg amendment (spec §10.5) -- never done silently here.

  2. Conservation closes (spec §10.4): both conservation errors stay under
     1e-9 relative on every run this script makes (they should sit near
     1e-16, the existing arb-only golden's order of magnitude).
"""

from __future__ import annotations

from itertools import pairwise

from experiments.run_one import run_one

ETHUSDT = "ETHUSDT"
SHIBUSDT = "SHIBUSDT"
JAN_2024 = 1_704_067_200_000
DAY_MS = 1440 * 60_000
GAS_PRICE_WEI = 20_000_000_000
FEE_LEVELS_PIPS = (500, 3000, 6000, 10000)
CONSERVATION_TOLERANCE = 1e-9


def main() -> None:
    results: dict[int, dict] = {}
    for fee_pips in FEE_LEVELS_PIPS:
        metrics = run_one(
            "MyHook",
            ETHUSDT,
            SHIBUSDT,
            JAN_2024,
            JAN_2024 + DAY_MS,
            fee_pips=fee_pips,
            gas_price_wei=GAS_PRICE_WEI,
            uu_mode="share",
        )
        results[fee_pips] = metrics
        print(
            f"fee={fee_pips:>6} pips  "
            f"net_result={metrics['net_result']:.6f}  "
            f"net_result_tt={metrics['net_result_tt']:.6f}  "
            f"conservation0={metrics['conservation_error_token0']:.3e}  "
            f"conservation1={metrics['conservation_error_token1']:.3e}"
        )

    net_results = [results[f]["net_result"] for f in FEE_LEVELS_PIPS]
    increasing = all(a <= b for a, b in pairwise(net_results))
    decreasing = all(a >= b for a, b in pairwise(net_results))
    monotone = increasing or decreasing

    print()
    print("net_result by fee level:", dict(zip(FEE_LEVELS_PIPS, net_results)))
    if monotone:
        print(
            "STILL MONOTONE at the canonical lambda -- degeneracy is not gone. "
            "Recording the four numbers above; NOT retuning lambda silently. "
            "Lambda recalibration is the owner's call (spec §10.5, prereg "
            "amendment)."
        )
    else:
        print("NON-MONOTONE: an interior static optimum exists. Degeneracy is gone.")

    print()
    worst0 = max(abs(results[f]["conservation_error_token0"]) for f in FEE_LEVELS_PIPS)
    worst1 = max(abs(results[f]["conservation_error_token1"]) for f in FEE_LEVELS_PIPS)
    print(f"worst conservation_error_token0: {worst0:.3e}")
    print(f"worst conservation_error_token1: {worst1:.3e}")
    assert worst0 < CONSERVATION_TOLERANCE, (
        f"conservation_error_token0 {worst0} exceeds {CONSERVATION_TOLERANCE}"
    )
    assert worst1 < CONSERVATION_TOLERANCE, (
        f"conservation_error_token1 {worst1} exceeds {CONSERVATION_TOLERANCE}"
    )
    print("conservation closes (< 1e-9 relative) on every run.")


if __name__ == "__main__":
    main()
