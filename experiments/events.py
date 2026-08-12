"""Reader for the JSONL log emitted by the Forge replay harness.

Values such as sqrtPriceX96 and feeGrowthInsideX128 exceed float64 precision, so
the file is parsed with the stdlib json module rather than pandas' JSON reader,
which coerces large integers to floats. Losing precision here would silently
corrupt exactly the quantities the conservation check depends on.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

WINDOW_INT_FIELDS = [
    "liquidity",
    "tickLower",
    "tickUpper",
    "sqrtPriceInitialX96",
    "sqrtPriceFinalX96",
    "feeGrowthInside0X128Initial",
    "feeGrowthInside1X128Initial",
    "feeGrowthInside0X128",
    "feeGrowthInside1X128",
    "initialToken0",
    "initialToken1",
    "extPrice0Initial",
    "extPrice1Initial",
    "extPrice0Final",
    "extPrice1Final",
    "warmupCandles",
    "candles",
]

# Columns whose values are wei-scale and therefore routinely exceed int64 when
# summed. pandas accumulates an int64 column in int64 and wraps silently on
# overflow -- a real run produced a flow of +8.1e18 where the true value was
# -1.0e19, sign included. These are held as object dtype so every sum is exact
# Python integer arithmetic.
#
# rWad/pWad (UU flow, 2026-08-09-uu-flow-design.md §5) join this group rather
# than the small one: they are WAD-scaled (up to 1e18) diagnostics, the same
# order of magnitude discipline as the wei-scale columns above, even though no
# metric sums them today.
SWAP_BIG_COLUMNS = [
    "sqrtPriceBeforeX96",
    "sqrtPriceAfterX96",
    "amountIn",
    "amountOut",
    "delta0",
    "delta1",
    "expectedProfit",
    "rWad",
    "pWad",
]

# Columns that are small by construction: candle indices, 1e8-scaled prices,
# fees in pips, gas units.
SWAP_SMALL_COLUMNS = [
    "candle",
    "blockNumber",
    "timestamp",
    "extPrice0",
    "extPrice1",
    "feePips",
    "feeAB",
    "feeBA",
    "gas",
    "extPriceGas",
]

SWAP_INT_COLUMNS = SWAP_BIG_COLUMNS + SWAP_SMALL_COLUMNS

# Columns UU flow added (2026-08-09-uu-flow-design.md §5) that a trace written
# before that change never has. Every pre-UU trace on disk must keep parsing:
# "arb" is exactly what every historical swap was, and 0 is UUMath's neutral
# value for a record with no UU diagnostics.
_UU_INT_DEFAULTS = {"rWad": 0, "pWad": 0, "extPriceGas": 0}
_TRADER_DEFAULT = "arb"


def read_events(path: Path) -> tuple[pd.DataFrame, dict]:
    """Return (swap frame, window record) from one run's JSONL."""
    swaps: list[dict] = []
    window: dict = {}

    for line in Path(path).read_text().splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        if record.get("kind") == "window":
            window = record
        else:
            swaps.append(record)

    if not swaps:
        frame = pd.DataFrame(
            columns=SWAP_INT_COLUMNS + ["zeroForOne", "sender", "trader"]
        )
    else:
        frame = pd.DataFrame(swaps)
        for column in SWAP_SMALL_COLUMNS:
            if column not in frame.columns:
                frame[column] = _UU_INT_DEFAULTS.get(column, 0)
            frame[column] = frame[column].map(int)
        for column in SWAP_BIG_COLUMNS:
            if column not in frame.columns:
                frame[column] = _UU_INT_DEFAULTS.get(column, 0)
            frame[column] = pd.Series(
                [int(v) for v in frame[column]], dtype="object", index=frame.index
            )
        if "trader" not in frame.columns:
            frame["trader"] = _TRADER_DEFAULT
        else:
            frame["trader"] = frame["trader"].fillna(_TRADER_DEFAULT)

    return frame, window


# Each hook's own fee box, in basis points, read off the contracts:
# ABHook/BAHook/DAHook/VolatilityHook `F_MIN=100, MAX_FEE=10000` pips,
# PegStabilityHook `MIN_FEE_BPS=100, MAX_FEE_BPS=10000` pips, and MEVChargeHook
# `fixedLpFee=30, config.feeMax=1000` -- the last one already in bps, and an
# order of magnitude wider than every other box. A figure that draws one shared
# box across all policies states something false about four of them.
FEE_BOXES_BPS = {
    # Not 100 bps: ABHook's constant sum binds before any ceiling, so one
    # direction reaches 59 bps only by pinning the other to the floor.
    "ABHook": (1.0, 59.0),
    "BAHook": (1.0, 100.0),
    "DAHook": (1.0, 100.0),
    "VolatilityHook": (1.0, 100.0),
    "PegCapture": (1.0, 100.0),
    "PegDefence": (1.0, 100.0),
    # Clamped to the shared 100 bps box for the UU matrix
    # (2026-08-09 prereg). Judged against the old 1000 bps ceiling a
    # policy sitting at its real cap reads as nowhere near it.
    "MEVChargeHook": (30.0, 100.0),
    # Same bounds as the template it derives from; only the impact measure
    # differs.
    "MEVChargeHookFixed": (30.0, 100.0),
    # MyHook@N is a constant and has no box at all.
}

# Keyed by the symbols that appear in a trace filename, which for the stable
# pair is the synthetic constant feed and NOT "USDTUSDT" -- see
# `matrix.CONSTANT_ONE`. The wrong key here silently dropped all 864 USDC/USDT
# traces, and the fee-distribution figure reported the pair as producing no
# swaps when in fact its traces were never read.
_PAIR_BY_SYMBOLS = {
    ("ETHUSDT", "SHIBUSDT"): "ETH/SHIB",
    ("ETHUSDT", "USDCUSDT"): "ETH/USDC",
    ("USDCUSDT", "CONST1"): "USDC/USDT",
}


def applied_fees(results_dir: Path, address_mode: str = "persistent") -> pd.DataFrame:
    """Every fee actually charged, over the whole matrix, as (policy, pair, bps).

    Reads the retained swap traces rather than a single ad-hoc window: the fee a
    policy applies depends on the window and on which trades cleared gas, so one
    window describes one window.

    One address mode only. The two modes are a control that produced identical
    results for every policy but MEVChargeHook, so pooling them would double-
    count each swap and tighten the spread for no reason.
    """
    rows: list[dict] = []
    for path in sorted(Path(results_dir).glob("*.jsonl")):
        parts = path.stem.split("-")
        # Exactly seven fields, and the mode matched exactly. The sensitivity
        # sweep writes an eighth (`-cs<share>`); a prefix match on the mode let
        # those through and pooled 62k sensitivity swaps into PegCapture's
        # pre-registered row. The two must never mix.
        if len(parts) != 7 or parts[6] != address_mode:
            continue
        pair = _PAIR_BY_SYMBOLS.get((parts[2], parts[3]))
        if pair is None:
            continue
        policy = parts[0] if parts[1] == "0" else f"MyHook@{parts[1]}"
        for line in path.read_text().splitlines():
            if '"feePips"' not in line:
                continue
            record = json.loads(line)
            if record.get("kind") == "swap":
                rows.append(
                    {
                        "policy": policy,
                        "pair": pair,
                        "fee_bps": int(record["feePips"]) / 100.0,
                    }
                )
    return pd.DataFrame(rows, columns=["policy", "pair", "fee_bps"])


def fee_vs_deviation(results_dir, address_mode: str = "persistent") -> pd.DataFrame:
    """Applied fee against the price gap it was charged on, per swap.

    To beat the static fee curve a policy has to charge more exactly when the
    trade is more toxic, and under arbitrage-only flow toxicity is the gap
    between the pool and the reference: the arbitrageur extracts roughly
    L(s-t)^2/s. A fee that varies without tracking that gap is noise, and
    convexity makes noise slightly worse than the constant equal to its mean.

    Returns one row per swap with the fee in basis points and the pre-trade
    relative deviation, so the correlation between them can be measured rather
    than asserted.
    """
    rows: list[dict] = []
    for path in sorted(Path(results_dir).glob("*.jsonl")):
        parts = path.stem.split("-")
        if len(parts) != 7 or parts[6] != address_mode:
            continue
        pair = _PAIR_BY_SYMBOLS.get((parts[2], parts[3]))
        if pair is None:
            continue
        policy = parts[0] if parts[1] == "0" else f"MyHook@{parts[1]}"
        for line in path.read_text().splitlines():
            if '"feePips"' not in line:
                continue
            record = json.loads(line)
            if record.get("kind") != "swap":
                continue
            pool = (int(record["sqrtPriceBeforeX96"]) / 2**96) ** 2
            reference = int(record["extPrice0"]) / int(record["extPrice1"])
            if reference == 0:
                continue
            rows.append(
                {
                    "policy": policy,
                    "pair": pair,
                    "fee_bps": int(record["feePips"]) / 100.0,
                    "deviation": abs(pool / reference - 1.0),
                }
            )
    return pd.DataFrame(rows, columns=["policy", "pair", "fee_bps", "deviation"])


def fee_by_reversal(results_dir, address_mode: str = "persistent") -> pd.DataFrame:
    """Applied fee and price gap, split by whether the trade reversed direction.

    Written to test one explanation for why `ABHook` loses. It holds
    f(A->B) + f(B->A) constant, so raising one side is a discount on the other.
    Under arbitrage-only flow the side that becomes active next is decided by
    where the pool sits against the reference, and on a reversal that is exactly
    the side just discounted -- while a reversal is also where the LP is most
    exposed, because the price came back and the position is on the wrong side.

    Returns one row per swap, in trade order within each run.
    """
    rows: list[dict] = []
    for path in sorted(Path(results_dir).glob("*.jsonl")):
        parts = path.stem.split("-")
        if len(parts) != 7 or parts[6] != address_mode:
            continue
        pair = _PAIR_BY_SYMBOLS.get((parts[2], parts[3]))
        if pair is None:
            continue
        policy = parts[0] if parts[1] == "0" else f"MyHook@{parts[1]}"

        previous: bool | None = None
        for line in path.read_text().splitlines():
            if '"feePips"' not in line:
                continue
            record = json.loads(line)
            if record.get("kind") != "swap":
                continue
            direction = bool(record["zeroForOne"])
            pool = (int(record["sqrtPriceBeforeX96"]) / 2**96) ** 2
            reference = int(record["extPrice0"]) / int(record["extPrice1"])
            if reference:
                rows.append(
                    {
                        "policy": policy,
                        "pair": pair,
                        "fee_bps": int(record["feePips"]) / 100.0,
                        "deviation": abs(pool / reference - 1.0),
                        "reversal": previous is not None and direction != previous,
                        "first": previous is None,
                    }
                )
            previous = direction
    return pd.DataFrame(rows)


def fee_trajectories(
    results_dir,
    pair_symbols: tuple[str, str],
    window_start_ms: int,
    gas_price_wei: int = 20_000_000_000,
    address_mode: str = "persistent",
) -> pd.DataFrame:
    """Every policy's applied fee through one window, in trade order.

    One window, one gas scenario: the point is to watch the policies respond to
    the same price path, so anything that would let them see different prices is
    held fixed.
    """
    symbol0, symbol1 = pair_symbols
    rows: list[dict] = []
    pattern = (
        f"*-{symbol0}-{symbol1}-{window_start_ms}-{gas_price_wei}-{address_mode}.jsonl"
    )
    for path in sorted(Path(results_dir).glob(pattern)):
        parts = path.stem.split("-")
        if len(parts) != 7:
            continue
        policy = parts[0] if parts[1] == "0" else f"MyHook@{parts[1]}"
        for line in path.read_text().splitlines():
            if '"feePips"' not in line:
                continue
            record = json.loads(line)
            if record.get("kind") != "swap":
                continue
            rows.append(
                {
                    "policy": policy,
                    "candle": int(record["candle"]),
                    "fee_bps": int(record["feePips"]) / 100.0,
                    # The hook's own state for both directions, read after the swap.
                    # `fee_bps` is whichever of these the trade actually paid, so it
                    # jumps between them whenever the direction flips -- which is a
                    # property of the order flow, not of the policy.
                    "fee_ab_bps": int(record["feeAB"]) / 100.0,
                    "fee_ba_bps": int(record["feeBA"]) / 100.0,
                    "zero_for_one": bool(record["zeroForOne"]),
                }
            )
    return pd.DataFrame(
        rows,
        columns=[
            "policy",
            "candle",
            "fee_bps",
            "fee_ab_bps",
            "fee_ba_bps",
            "zero_for_one",
        ],
    )
