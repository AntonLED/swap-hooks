"""Writes kline frames as the headerless CSV the Forge harness reads."""

from __future__ import annotations

from functools import reduce
from pathlib import Path

import pandas as pd

PRICE_SCALE = 100_000_000  # 1e8, the Chainlink feed convention


def align_traces(*frames: pd.DataFrame) -> tuple[pd.DataFrame, ...]:
    """Restrict every frame to the timestamps all of them share.

    Binance occasionally omits a minute for one symbol and not another. Zipping
    the frames positionally would silently pair mismatched prices from then on,
    and every later ratio would be wrong without anything failing.
    """
    shared = reduce(
        lambda a, b: a.intersection(b), (pd.Index(f["open_time"]) for f in frames)
    )
    if len(shared) == 0:
        raise ValueError("traces share no timestamps")
    shared = shared.sort_values()
    # Deduplicate before filtering. `isin` keeps every copy of a repeated
    # timestamp, so one duplicated minute in a single frame left the frames at
    # different lengths and shifted against each other from that point on --
    # exactly the corruption this function exists to prevent. The cached data
    # is clean today; a re-fetch that overlaps a page boundary would not be.
    aligned = tuple(
        f[f["open_time"].isin(shared)]
        .drop_duplicates(subset="open_time", keep="first")
        .sort_values("open_time")
        .reset_index(drop=True)
        for f in frames
    )
    lengths = {len(f) for f in aligned}
    if len(lengths) != 1:
        raise ValueError(f"aligned traces differ in length: {sorted(lengths)}")
    return aligned


def export_trace(df: pd.DataFrame, path: Path) -> None:
    """Write `open_time,price_1e8` with no header.

    A price that rounds to zero would make the pool's price ratio undefined and
    the harness would divide by it, so reject rather than emit it.
    """
    scaled = (df["close"] * PRICE_SCALE).round().astype("int64")
    if (scaled <= 0).any():
        raise ValueError(
            f"price underflow: a value rounds to {scaled.min()} at 1e8 scale; "
            "the pair needs a finer scale or is unusable"
        )
    lines = [f"{t},{p}" for t, p in zip(df["open_time"], scaled)]
    Path(path).write_text("\n".join(lines) + "\n")
