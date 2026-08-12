import pytest

from experiments.binance import fetch_klines, months_spanning

JAN_2024 = 1_704_067_200_000  # 2024-01-01T00:00:00Z
MINUTE = 60_000


class FakeApi:
    """Serves 1-minute candles with Binance's 12 fields and 1000-row cap."""

    def __init__(self, first_ms: int, count: int):
        self.first_ms = first_ms
        self.count = count
        self.calls = 0

    def __call__(self, symbol, start_ms, end_ms, limit):
        self.calls += 1
        rows = []
        t = max(start_ms, self.first_ms)
        last = self.first_ms + (self.count - 1) * MINUTE
        while t <= min(end_ms, last) and len(rows) < limit:
            close = 100.0 + (t - self.first_ms) / MINUTE
            rows.append(
                [
                    t,
                    "1.0",
                    "1.0",
                    "1.0",
                    str(close),
                    "1.0",
                    t + MINUTE - 1,
                    "1.0",
                    1,
                    "1.0",
                    "1.0",
                    "0",
                ]
            )
            t += MINUTE
        return rows


def test_paginates_beyond_the_1000_candle_cap(tmp_path):
    api = FakeApi(JAN_2024, 1440)
    df = fetch_klines("ETHUSDT", JAN_2024, JAN_2024 + 1440 * MINUTE, tmp_path, api=api)

    assert len(df) == 1440, "a full day must come back, not the first 1000"
    assert api.calls >= 2


def test_accepts_binances_twelve_field_rows(tmp_path):
    """The real endpoint returns 12 fields per kline, not 6."""
    api = FakeApi(JAN_2024, 60)
    df = fetch_klines("ETHUSDT", JAN_2024, JAN_2024 + 60 * MINUTE, tmp_path, api=api)

    assert list(df.columns) == ["open_time", "close"]
    assert df["close"].dtype.kind == "f"
    assert df["close"].iloc[0] == pytest.approx(100.0)


def test_rows_are_sorted_and_unique(tmp_path):
    api = FakeApi(JAN_2024, 1440)
    df = fetch_klines("ETHUSDT", JAN_2024, JAN_2024 + 1440 * MINUTE, tmp_path, api=api)

    assert df["open_time"].is_monotonic_increasing
    assert not df["open_time"].duplicated().any()


def test_a_narrow_request_is_served_from_a_wide_cache(tmp_path):
    """The matrix prefetches whole months, then reads single days out of them."""
    api = FakeApi(JAN_2024, 1440 * 31)
    fetch_klines("ETHUSDT", JAN_2024, JAN_2024 + 1440 * 31 * MINUTE, tmp_path, api=api)
    calls_after_prefetch = api.calls

    day = fetch_klines(
        "ETHUSDT",
        JAN_2024 + 1440 * 5 * MINUTE,
        JAN_2024 + 1440 * 6 * MINUTE,
        tmp_path,
        api=api,
    )

    assert api.calls == calls_after_prefetch, "no network for an already-cached month"
    assert len(day) == 1440


def test_a_request_spanning_two_months_is_assembled(tmp_path):
    api = FakeApi(JAN_2024, 1440 * 40)
    start = JAN_2024 + 1440 * 29 * MINUTE
    df = fetch_klines("ETHUSDT", start, start + 1440 * 3 * MINUTE, tmp_path, api=api)

    assert len(df) == 1440 * 3
    assert df["open_time"].is_monotonic_increasing


def test_months_spanning_covers_the_boundary():
    spans = months_spanning(JAN_2024, JAN_2024 + 40 * 1440 * MINUTE)
    assert len(spans) == 2, "January and February"
    assert spans[0][0] == JAN_2024


def test_fetch_with_volume_returns_quote_volume(tmp_path):
    api = FakeApi(JAN_2024, 2)
    frame = fetch_klines(
        "ETHUSDT", JAN_2024, JAN_2024 + 2 * MINUTE, tmp_path, api=api, with_volume=True
    )

    assert list(frame.columns) == ["open_time", "close", "quote_volume"]
    assert (frame["quote_volume"] > 0).all()


def test_volume_cache_is_separate(tmp_path):
    api = FakeApi(JAN_2024, 1)
    fetch_klines("ETHUSDT", JAN_2024, JAN_2024 + MINUTE, tmp_path, api=api)
    fetch_klines(
        "ETHUSDT", JAN_2024, JAN_2024 + MINUTE, tmp_path, api=api, with_volume=True
    )

    names = {p.name for p in tmp_path.glob("*.parquet")}
    assert any("-v2-" in n for n in names) and any("-v2-" not in n for n in names)


def test_default_contract_unchanged(tmp_path):
    api = FakeApi(JAN_2024, 1)
    frame = fetch_klines("ETHUSDT", JAN_2024, JAN_2024 + MINUTE, tmp_path, api=api)

    assert list(frame.columns) == ["open_time", "close"]
