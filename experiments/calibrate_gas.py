"""Measures the gas an arbitrageur should expect to pay, per policy.

The arbitrageur decides whether a trade clears its gas cost *before* swapping,
so it works from an estimate. That estimate is per policy and not a free
parameter: a hook that reads two oracle feeds and writes variance state costs
materially more per swap than one returning a constant, and that gap is exactly
what the gas axis of the matrix measures. An earlier placeholder of 180,000
suppressed roughly twice as many trades as reality.

Calibration runs at a low gas price so that plenty of trades occur and the
median is well determined; the estimate itself does not feed back into the
median in any material way.
"""

from __future__ import annotations

import json
from pathlib import Path

from experiments.events import read_events
from experiments.policies import ALL, INTRINSIC_GAS, Policy
from experiments.run_one import run_one

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "experiments" / "gas_estimates.json"

CALIBRATION_GAS_PRICE_WEI = 5_000_000_000  # 5 gwei, to maximise trade count
CALIBRATION_GAS_ESTIMATE = 76_578  # seed; the result replaces it


def calibrate_one(
    policy: Policy, symbol0: str, symbol1: str, start_ms: int, end_ms: int
) -> tuple[int, int]:
    """Return (median execution gas, trade count) for one policy."""
    run_one(
        policy.hook,
        symbol0,
        symbol1,
        start_ms,
        end_ms,
        fee_pips=policy.fee_pips,
        gas_price_wei=CALIBRATION_GAS_PRICE_WEI,
        gas_estimate=CALIBRATION_GAS_ESTIMATE,
        size_dependent=policy.size_dependent,
    )
    name = (
        f"{policy.hook}-{policy.fee_pips}-{symbol0}-{symbol1}-{start_ms}"
        f"-{CALIBRATION_GAS_PRICE_WEI}-persistent.jsonl"
    )
    swaps, _ = read_events(ROOT / "results" / name)
    if swaps.empty:
        return 0, 0
    return int(swaps["gas"].median()), len(swaps)


def calibrate(symbol0: str, symbol1: str, start_ms: int, end_ms: int) -> dict[str, int]:
    """Median total gas per swap, per policy, including the intrinsic cost."""
    estimates: dict[str, int] = {}
    for policy in ALL:
        execution, trades = calibrate_one(policy, symbol0, symbol1, start_ms, end_ms)
        if trades == 0:
            print(f"{policy.name:16} no trades; leaving unset")
            continue
        estimates[policy.name] = execution + INTRINSIC_GAS
        print(
            f"{policy.name:16} execution {execution:>7,}  "
            f"+intrinsic {estimates[policy.name]:>7,}  ({trades} trades)"
        )
    return estimates


def write(estimates: dict[str, int]) -> None:
    OUTPUT.write_text(json.dumps(estimates, indent=2, sort_keys=True) + "\n")


def load() -> dict[str, int]:
    if not OUTPUT.exists():
        return {}
    return json.loads(OUTPUT.read_text())


if __name__ == "__main__":
    JAN_2024 = 1_704_067_200_000
    day = 1440 * 60_000
    result = calibrate("ETHUSDT", "SHIBUSDT", JAN_2024, JAN_2024 + day)
    write(result)
    print(f"\nwritten to {OUTPUT}")
