import numpy as np
import pandas as pd
import pytest

from experiments.uu import export_uu_trace, kappa, uu_profile


def _frame(vols):
    return pd.DataFrame(
        {"open_time": np.arange(len(vols)) * 60_000, "close": 1.0, "quote_volume": vols}
    )


def test_profile_geometric_mean_two_legs():
    p = uu_profile(_frame([4.0, 9.0]), _frame([1.0, 4.0]))
    assert list(p["v_usdt"]) == [2.0, 6.0]


def test_profile_single_leg_identity():
    p = uu_profile(_frame([5.0, 7.0]))
    assert list(p["v_usdt"]) == [5.0, 7.0]


def test_kappa_normalizes_mean_daily_to_basket():
    p = _frame([10.0] * 2880)[["open_time"]].assign(v_usdt=10.0)  # 2 days
    k = kappa(p, basket_usdt=20_000_000)
    assert k * 10.0 * 1440 == pytest.approx(20_000_000)


def test_share_trace_format(tmp_path):
    p = pd.DataFrame({"open_time": [0, 60_000], "v_usdt": [100.0, 200.0]})
    export_uu_trace(p, 2.0, tmp_path / "t.csv", mode="share")
    rows = [l.split(",") for l in (tmp_path / "t.csv").read_text().splitlines()]
    assert rows[0] == ["0", str(int(100 * 1e18)), "0", str(int(100 * 1e18)), "0"]


def test_discrete_trace_is_seed_deterministic(tmp_path):
    p = pd.DataFrame({"open_time": [0], "v_usdt": [100.0]})
    export_uu_trace(p, 1.0, tmp_path / "a.csv", mode="discrete", seed=7)
    export_uu_trace(p, 1.0, tmp_path / "b.csv", mode="discrete", seed=7)
    assert (tmp_path / "a.csv").read_text() == (tmp_path / "b.csv").read_text()


def test_discrete_sizes_have_the_right_mean(tmp_path):
    p = pd.DataFrame({"open_time": np.arange(20_000) * 60_000, "v_usdt": 100.0})
    export_uu_trace(p, 1.0, tmp_path / "t.csv", mode="discrete", seed=1)
    sizes = [
        int(l.split(",")[1]) / 1e18
        for l in (tmp_path / "t.csv").read_text().splitlines()
    ]
    assert np.mean(sizes) == pytest.approx(50.0, rel=0.05)
