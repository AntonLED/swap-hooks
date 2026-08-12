"""Binance kline loading with pagination and a calendar-month disk cache.

Two properties matter for reproducibility. The public endpoint caps a single
response at 1000 candles regardless of the requested range, so any window longer
than 1000 minutes needs a loop. And the cache is keyed by calendar month rather
than by requested range, so a prefetch of whole months satisfies every later
window request without touching the network.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd
import requests

MINUTE_MS = 60_000
MAX_LIMIT = 1000
_BASE_URL = "https://api.binance.com/api/v3/klines"

# The endpoint returns twelve fields per kline. Naming all of them lets the
# frame be built without guessing the width.
KLINE_FIELDS = [
    "open_time",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "close_time",
    "quote_volume",
    "trades",
    "taker_base",
    "taker_quote",
    "ignore",
]

_EMPTY = {"open_time": "int64", "close": "float64"}
_EMPTY_WITH_VOLUME = {
    "open_time": "int64",
    "close": "float64",
    "quote_volume": "float64",
}


def _empty_frame(with_volume: bool = False) -> pd.DataFrame:
    schema = _EMPTY_WITH_VOLUME if with_volume else _EMPTY
    return pd.DataFrame({k: pd.Series(dtype=v) for k, v in schema.items()})


def _http_api(symbol: str, start_ms: int, end_ms: int, limit: int) -> list:
    response = requests.get(
        _BASE_URL,
        params={
            "symbol": symbol,
            "interval": "1m",
            "startTime": start_ms,
            "endTime": end_ms,
            "limit": limit,
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def months_spanning(start_ms: int, end_ms: int) -> list[tuple[int, int]]:
    """Calendar-month [start, end) bounds covering the requested range."""
    spans: list[tuple[int, int]] = []
    cursor = datetime.fromtimestamp(start_ms / 1000, UTC).replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    )
    while int(cursor.timestamp() * 1000) < end_ms:
        nxt = (cursor + timedelta(days=32)).replace(day=1)
        spans.append((int(cursor.timestamp() * 1000), int(nxt.timestamp() * 1000)))
        cursor = nxt
    return spans


def _fetch_range(
    symbol: str, start_ms: int, end_ms: int, api, with_volume: bool = False
) -> pd.DataFrame:
    rows: list[list] = []
    cursor = start_ms
    while cursor < end_ms:
        batch = api(symbol, cursor, end_ms - 1, MAX_LIMIT)
        if not batch:
            break
        rows.extend(batch)
        next_cursor = int(batch[-1][0]) + MINUTE_MS
        if next_cursor <= cursor:
            break
        cursor = next_cursor

    if not rows:
        return _empty_frame(with_volume)

    columns = (
        ["open_time", "close", "quote_volume"]
        if with_volume
        else ["open_time", "close"]
    )
    frame = pd.DataFrame(rows, columns=KLINE_FIELDS[: len(rows[0])])
    frame = frame[columns].copy()
    frame["open_time"] = frame["open_time"].astype("int64")
    frame["close"] = frame["close"].astype("float64")
    if with_volume:
        frame["quote_volume"] = frame["quote_volume"].astype("float64")
    return frame


def _month_cache(
    cache_dir: Path, symbol: str, month_start: int, with_volume: bool = False
) -> Path:
    tag = "1m-v2" if with_volume else "1m"
    return cache_dir / f"{symbol}-{tag}-{month_start}.parquet"


def fetch_klines(
    symbol: str,
    start_ms: int,
    end_ms: int,
    cache_dir: Path,
    api=_http_api,
    with_volume: bool = False,
) -> pd.DataFrame:
    """Return 1-minute candles for [start_ms, end_ms) as open_time, close (and
    quote_volume when with_volume=True). Volume-bearing frames are cached
    under a separate `-v2-` filename so the existing two-column cache and
    every current caller stay valid untouched."""
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)

    parts = []
    for month_start, month_end in months_spanning(start_ms, end_ms):
        cached = _month_cache(cache_dir, symbol, month_start, with_volume)
        if cached.exists():
            parts.append(pd.read_parquet(cached))
            continue
        month = _fetch_range(symbol, month_start, month_end, api, with_volume)
        month.to_parquet(cached, index=False)
        parts.append(month)

    if not parts:
        return _empty_frame(with_volume)

    frame = pd.concat(parts, ignore_index=True)
    return (
        frame[(frame["open_time"] >= start_ms) & (frame["open_time"] < end_ms)]
        .drop_duplicates(subset="open_time")
        .sort_values("open_time")
        .reset_index(drop=True)
    )
