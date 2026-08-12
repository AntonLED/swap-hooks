"""Window selection: realised volatility, tercile split, deterministic sampling.

Windows are chosen mechanically. Calm days outnumber volatile ones, so a random
sample would be predominantly calm and would say nothing about how the policies
behave under stress — which is precisely what a volatility-adaptive policy is
supposed to be judged on. Stratifying guarantees all three regimes enter the
sample and lets each be reported separately.

Nothing here is random: the selection is a function of the price data alone, so
two people running it get the same windows.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from experiments.export_trace import align_traces

MINUTE_MS = 60_000
CANDLES_PER_DAY = 1440
DAY_MS = CANDLES_PER_DAY * MINUTE_MS
REGIMES = ("low", "mid", "high")


def realised_volatility(ratio: pd.Series) -> float:
    """Standard deviation of per-minute log returns, scaled to a daily basis."""
    values = pd.Series(ratio).astype(float)
    if len(values) < 3:
        return 0.0
    returns = np.diff(np.log(values.to_numpy()))
    if returns.size < 2:
        return 0.0
    return float(np.std(returns, ddof=1) * np.sqrt(CANDLES_PER_DAY))


def daily_segments(df0: pd.DataFrame, df1: pd.DataFrame) -> pd.DataFrame:
    """Non-overlapping whole-day segments with the volatility of token0/token1.

    The frames are aligned on shared timestamps first: Binance occasionally
    omits a minute for one symbol and not the other, and pairing positionally
    would corrupt every later ratio without anything failing.
    """
    df0, df1 = align_traces(df0, df1)
    usable = min(len(df0), len(df1)) // CANDLES_PER_DAY * CANDLES_PER_DAY
    if usable == 0:
        return pd.DataFrame(columns=["start_ms", "end_ms", "volatility"])

    ratio = df0["close"].to_numpy()[:usable] / df1["close"].to_numpy()[:usable]
    starts = df0["open_time"].to_numpy()[:usable]

    rows = []
    for i in range(0, usable, CANDLES_PER_DAY):
        rows.append(
            {
                "start_ms": int(starts[i]),
                "end_ms": int(starts[i]) + DAY_MS,
                "volatility": realised_volatility(
                    pd.Series(ratio[i : i + CANDLES_PER_DAY])
                ),
            }
        )
    return pd.DataFrame(rows)


def select_windows(segments: pd.DataFrame, per_tercile: int = 8) -> pd.DataFrame:
    """Sort by volatility, cut into terciles, take `per_tercile` from each.

    Within a tercile the picks are spaced evenly by date rather than taken
    consecutively, so a regime does not become a proxy for a season.
    """
    if segments.empty:
        return segments.assign(regime=pd.Series(dtype="object"))

    ordered = segments.sort_values("volatility").reset_index(drop=True)
    blocks = np.array_split(np.arange(len(ordered)), 3)

    picked = []
    for regime, index_block in zip(REGIMES, blocks):
        block = ordered.iloc[index_block].sort_values("start_ms").reset_index(drop=True)
        if len(block) <= per_tercile:
            chosen = block
        else:
            step = len(block) / per_tercile
            chosen = block.iloc[[int(i * step) for i in range(per_tercile)]]
        picked.append(chosen.assign(regime=regime))

    return pd.concat(picked, ignore_index=True)
