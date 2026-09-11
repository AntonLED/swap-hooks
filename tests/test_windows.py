import numpy as np
import pandas as pd
import pytest

from experiments.windows import (
    CANDLES_PER_DAY,
    daily_segments,
    realised_volatility,
    select_windows,
)

MINUTE = 60_000
DAY = CANDLES_PER_DAY * MINUTE


def _flat(n, value=100.0, start=0):
    return pd.DataFrame(
        {"open_time": [start + i * MINUTE for i in range(n)], "close": [value] * n}
    )


def _wobbly(n, amplitude, start=0):
    closes = [100.0 * (1 + amplitude * (-1) ** i) for i in range(n)]
    return pd.DataFrame(
        {"open_time": [start + i * MINUTE for i in range(n)], "close": closes}
    )


def _segments(n_days, volatilities):
    return pd.DataFrame(
        {
            "start_ms": [i * DAY for i in range(n_days)],
            "end_ms": [(i + 1) * DAY for i in range(n_days)],
            "volatility": volatilities,
        }
    )


def test_flat_price_has_zero_volatility():
    assert realised_volatility(pd.Series([100.0] * 100)) == pytest.approx(0.0)


def test_volatility_grows_with_amplitude():
    calm = realised_volatility(_wobbly(100, 0.001)["close"])
    wild = realised_volatility(_wobbly(100, 0.010)["close"])
    assert wild > calm


def test_segments_are_whole_days_and_do_not_overlap():
    df0 = _flat(CANDLES_PER_DAY * 3)
    df1 = _flat(CANDLES_PER_DAY * 3, value=50.0)
    segs = daily_segments(df0, df1)

    assert len(segs) == 3
    assert (segs["end_ms"] - segs["start_ms"] == DAY).all()
    assert (segs["start_ms"].diff().dropna() == DAY).all()


def test_misaligned_symbols_do_not_shift_the_ratio():
    """A gap in one symbol must drop that minute, not slide every later price.

    Zipping positionally would pair mismatched prices from the gap onward and
    every later ratio would be wrong with nothing failing.
    """
    a = _flat(CANDLES_PER_DAY * 2, value=100.0)
    b = _flat(CANDLES_PER_DAY * 2, value=50.0).drop(index=5).reset_index(drop=True)
    segs = daily_segments(a, b)

    assert (segs["volatility"].abs() < 1e-12).all(), (
        f"two flat series must stay flat after alignment, got {segs['volatility'].tolist()}"
    )


def test_select_returns_equal_counts_per_regime():
    segs = _segments(90, np.linspace(0.01, 0.9, 90))
    chosen = select_windows(segs, per_tercile=8)

    assert len(chosen) == 24
    assert chosen["regime"].value_counts().to_dict() == {"low": 8, "mid": 8, "high": 8}


def test_selection_is_deterministic():
    segs = _segments(90, np.linspace(0.01, 0.9, 90))
    pd.testing.assert_frame_equal(
        select_windows(segs, per_tercile=8), select_windows(segs, per_tercile=8)
    )


def test_low_regime_really_is_the_calmest():
    segs = _segments(90, np.linspace(0.01, 0.9, 90))
    chosen = select_windows(segs, per_tercile=8)

    low = chosen.loc[chosen["regime"] == "low", "volatility"].max()
    high = chosen.loc[chosen["regime"] == "high", "volatility"].min()
    assert low < high


def test_selection_spreads_across_the_year_not_one_corner():
    """Even spacing by date inside a tercile. Clustering every calm window into
    one fortnight would make the regime a proxy for a season."""
    rng = np.random.default_rng(0)
    segs = _segments(360, rng.permutation(np.linspace(0.01, 0.9, 360)))
    chosen = select_windows(segs, per_tercile=8)

    lows = chosen.loc[chosen["regime"] == "low", "start_ms"].to_numpy()
    span = lows.max() - lows.min()
    assert span > 100 * DAY, "the sample must not sit in one corner of the year"


def test_a_short_tercile_is_taken_whole_rather_than_failing():
    segs = _segments(9, np.linspace(0.01, 0.9, 9))
    chosen = select_windows(segs, per_tercile=8)

    assert len(chosen) == 9, "3 per tercile is all there is; take them"


def test_selection_carries_the_bounds_needed_to_run_a_window():
    segs = _segments(90, np.linspace(0.01, 0.9, 90))
    chosen = select_windows(segs, per_tercile=8)

    assert {"start_ms", "end_ms", "volatility", "regime"} <= set(chosen.columns)
