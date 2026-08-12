"""Adversarial, independent property tests for the UU-flow implementation.

Written WITHOUT reading experiments/uu.py, experiments/check_uu.py,
experiments/binance.py, experiments/events.py, experiments/metrics.py,
experiments/run_one.py, experiments/matrix.py, or any Solidity file under
test. All interfaces were taken from:

  - docs/superpowers/specs/2026-08-09-uu-flow-design.md
  - docs/superpowers/plans/2026-08-09-uu-flow.md (Interfaces: blocks)
  - docs/superpowers/specs/2026-08-02-dynamic-fee-experiments-design.md
  - live signature introspection (inspect.signature) and running real event
    JSONL produced by the harness (data, not source)

Every expected number here is computed independently in this file (plain
Python / Fractions), never borrowed from the implementation's own output,
except where explicitly noted (e.g. reusing a real historical window's raw
swap deltas as *inputs*, with the expected aggregate computed here by hand).
"""

from __future__ import annotations

import json
from fractions import Fraction
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from experiments.events import read_events
from experiments.metrics import compute
from experiments.run_one import run_one
from experiments.uu import export_uu_trace, kappa, uu_profile

WAD = 10**18
CALIBRATION_START = 1704067200000  # 2024-01-01T00:00:00Z, per plan §Global Constraints
DAY_MS = 1440 * 60_000

# contracts/foundry.toml fs_permissions only allows the forge test harness to
# read/write under ../.work/ and ../results/ (relative to contracts/) -- NOT
# pytest's tmp_path (which lives under /tmp or /private/var/...). Any test
# that calls run_one() (which shells out to forge) must use directories under
# these repo-relative roots instead of tmp_path.
_ADV_WORK = Path(".work/adversarial")
_ADV_RESULTS = Path("results/adversarial")


def _adv_dirs(name):
    wd = _ADV_WORK / name
    rd = _ADV_RESULTS / name
    wd.mkdir(parents=True, exist_ok=True)
    rd.mkdir(parents=True, exist_ok=True)
    return wd, rd


def _volframe(vols):
    return pd.DataFrame(
        {
            "open_time": np.arange(len(vols)) * 60_000,
            "close": 1.0,
            "quote_volume": vols,
        }
    )


# ---------------------------------------------------------------------------
# Property 3: generator (kappa normalization, geometric mean, trace formats)
# ---------------------------------------------------------------------------


def test_uu_profile_geometric_mean_two_legs_independent_numbers():
    # geo-mean([9,16,100],[1,4,25]) = [3, 8, 50]
    p = uu_profile(_volframe([9.0, 16.0, 100.0]), _volframe([1.0, 4.0, 25.0]))
    got = list(p["v_usdt"])
    assert got == pytest.approx([3.0, 8.0, 50.0], rel=1e-9)


def test_uu_profile_single_leg_is_identity():
    p = uu_profile(_volframe([13.0, 21.0, 34.0]))
    assert list(p["v_usdt"]) == pytest.approx([13.0, 21.0, 34.0], rel=1e-9)


def test_uu_profile_dead_minute_does_not_zero_the_profile():
    # a zero-volume minute must clamp rather than propagate a zero through
    # the geometric mean (plan Task 2 Step 3).
    p = uu_profile(_volframe([0.0, 10.0]), _volframe([5.0, 10.0]))
    assert (p["v_usdt"] > 0).all()


def test_kappa_normalizes_mean_daily_sum_to_basket_nonuniform_profile():
    rng = np.random.default_rng(123)
    days = 5
    vols = rng.uniform(1.0, 100.0, size=1440 * days)
    profile = pd.DataFrame({"open_time": np.arange(len(vols)) * 60_000, "v_usdt": vols})
    basket = 20_000_000.0
    k = kappa(profile, basket_usdt=basket)
    mean_daily = float(vols.sum()) / days
    assert k * mean_daily == pytest.approx(basket, rel=1e-9)


def test_share_mode_csv_format_matches_plan_schema(tmp_path):
    profile = pd.DataFrame(
        {"open_time": [0, 60_000, 120_000], "v_usdt": [40.0, 60.0, 0.0]}
    )
    k = 5.0
    out = tmp_path / "share.csv"
    export_uu_trace(profile, k, out, mode="share")
    rows = [line.split(",") for line in out.read_text().splitlines()]
    assert len(rows) == 3
    for (ot, v), row in zip([(0, 40.0), (60_000, 60.0), (120_000, 0.0)], rows):
        assert row[0] == str(ot)
        expected_size = int(k * v / 2 * 1e18)
        assert row[1] == str(expected_size)  # size_ab_wad
        assert row[2] == "0"  # u_ab_wad == 0 in share mode
        assert row[3] == str(expected_size)  # size_ba_wad
        assert row[4] == "0"  # u_ba_wad == 0 in share mode
        # all ints, exactly 5 columns
        assert len(row) == 5
        for cell in row:
            int(cell)  # must parse as int, no floats/scientific notation


def test_discrete_mode_is_seed_deterministic_and_seed_sensitive(tmp_path):
    profile = pd.DataFrame({"open_time": [0, 60_000], "v_usdt": [200.0, 200.0]})
    export_uu_trace(profile, 2.0, tmp_path / "a.csv", mode="discrete", seed=99)
    export_uu_trace(profile, 2.0, tmp_path / "b.csv", mode="discrete", seed=99)
    export_uu_trace(profile, 2.0, tmp_path / "c.csv", mode="discrete", seed=100)
    a = (tmp_path / "a.csv").read_text()
    b = (tmp_path / "b.csv").read_text()
    c = (tmp_path / "c.csv").read_text()
    assert a == b, "same seed must reproduce byte-for-byte"
    assert a != c, "different seed must produce a different trace"


def test_discrete_mode_geometric_mean_matches_share_scale(tmp_path):
    # lognormal size = (kappa*v/2)*exp(sigma*Z - sigma^2/2) has mean (kappa*v/2)
    # under the stated parameterization; check over many candles.
    profile = pd.DataFrame({"open_time": np.arange(5_000) * 60_000, "v_usdt": 50.0})
    export_uu_trace(
        profile, 1.0, tmp_path / "d.csv", mode="discrete", seed=7, sigma=1.0
    )
    sizes_ab = [
        int(line.split(",")[1]) / 1e18
        for line in (tmp_path / "d.csv").read_text().splitlines()
    ]
    # kappa*v/2 = 1.0*50/2 = 25
    assert np.mean(sizes_ab) == pytest.approx(25.0, rel=0.05)


# ---------------------------------------------------------------------------
# Property 4: inertness (uu_mode="off" reproduces the pre-UU harness exactly)
# ---------------------------------------------------------------------------


def test_uu_off_reproduces_pinned_golden():
    golden = json.loads(
        Path("tests/golden/eth-shib-2024-01-01-myhook-3000.json").read_text()
    )
    wd, _ = _adv_dirs("golden_off")
    result = run_one(
        "MyHook",
        "ETHUSDT",
        "SHIBUSDT",
        CALIBRATION_START,
        CALIBRATION_START + DAY_MS,
        fee_pips=3000,
        work_dir=wd,
        uu_mode="off",
    )
    assert set(result.keys()) == set(golden.keys())
    for key, expected in golden.items():
        got = result[key]
        if expected is None:
            assert got is None, f"{key}: expected None, got {got}"
        else:
            assert got == pytest.approx(expected, rel=1e-6, abs=1e-9), f"{key} mismatch"


def test_uu_off_is_deterministic_across_two_independent_runs():
    kwargs = dict(
        hook="MyHook",
        symbol0="ETHUSDT",
        symbol1="SHIBUSDT",
        start_ms=CALIBRATION_START,
        end_ms=CALIBRATION_START + DAY_MS,
        fee_pips=3000,
        uu_mode="off",
    )
    wd1, _ = _adv_dirs("det_run1")
    wd2, _ = _adv_dirs("det_run2")
    r1 = run_one(work_dir=wd1, **kwargs)
    r2 = run_one(work_dir=wd2, **kwargs)
    assert r1 == r2, "uu_mode=off must be bit-for-bit deterministic (spec §7.5)"


# ---------------------------------------------------------------------------
# Property 5: event-schema backward compatibility
# ---------------------------------------------------------------------------


def _pre_uu_window_record():
    # Hand-built from the field names observed on real emitted JSONL
    # (results/*.jsonl, data not source) and §11.1's description of a
    # per-window record (initial/final pool state, LP position parameters).
    return {
        "kind": "window",
        "liquidity": 65065830064971588276441207,
        "tickLower": -887220,
        "tickUpper": 887220,
        "sqrtPriceInitialX96": 1176484634295854095105905813111310,
        "sqrtPriceFinalX96": 1173846112538322483650299483408880,
        "feeGrowthInside0X128Initial": 0,
        "feeGrowthInside1X128Initial": 0,
        "feeGrowthInside0X128": 367963788326467173595922494992,
        "feeGrowthInside1X128": 47048198497988651388180700004180599368,
        "initialToken0": 4381736920515288725311,
        "initialToken1": 966183574879227053140096608528,
        "extPrice0Initial": 229429000000,
        "extPrice1Initial": 1038,
        "extPrice0Final": 235204000000,
        "extPrice1Final": 1068,
        "warmupCandles": 0,
        "candles": 2,
    }


def _pre_uu_swap_record(candle, zero_for_one, amount_in, amount_out, delta0, delta1):
    # Deliberately OMITS trader / rWad / pWad / extPriceGas -- the pre-UU
    # format per §11.1: "direction, input size, output size, applied fee,
    # both current hook fees, balance deltas, gas for this swap, sender".
    return {
        "kind": "swap",
        "candle": candle,
        "blockNumber": candle * 5,
        "timestamp": candle * 60,
        "extPrice0": 200000000000,  # $2000.00000000 (1e8-scaled)
        "extPrice1": 100000000,  # $1.00000000
        "sqrtPriceBeforeX96": 1176484634295854095105905813111310,
        "sqrtPriceAfterX96": 1176484634295854095105905813111310,
        "zeroForOne": zero_for_one,
        "amountIn": amount_in,
        "amountOut": amount_out,
        "feePips": 3000,
        "feeAB": 3000,
        "feeBA": 3000,
        "delta0": delta0,
        "delta1": delta1,
        "expectedProfit": 0,
        "gas": 90000,
        "sender": "0x0000000000000000000000000000000000dEaD",
    }


def test_pre_uu_jsonl_parses_with_trader_defaulting_to_arb(tmp_path):
    lines = [
        json.dumps(
            _pre_uu_swap_record(
                0, True, 10**18, 1990 * 10**18, -(10**18), 1990 * 10**18
            )
        ),
        json.dumps(
            _pre_uu_swap_record(
                1, False, 500 * 10**18, int(0.24e18), int(0.24e18), -500 * 10**18
            )
        ),
        json.dumps(_pre_uu_window_record()),
    ]
    path = tmp_path / "pre_uu.jsonl"
    path.write_text("\n".join(lines) + "\n")

    df, window = read_events(path)

    assert "trader" in df.columns
    assert (df["trader"] == "arb").all(), "missing trader field must default to 'arb'"
    assert "extPriceGas" in df.columns
    assert (df["extPriceGas"] == 0).all(), "missing extPriceGas field must default to 0"


def test_pre_uu_frame_metrics_compute_survives_and_realized_is_none(tmp_path):
    lines = [
        json.dumps(
            _pre_uu_swap_record(
                0, True, 10**18, 1990 * 10**18, -(10**18), 1990 * 10**18
            )
        ),
        json.dumps(
            _pre_uu_swap_record(
                1, False, 500 * 10**18, int(0.24e18), int(0.24e18), -500 * 10**18
            )
        ),
        json.dumps(_pre_uu_window_record()),
    ]
    path = tmp_path / "pre_uu2.jsonl"
    path.write_text("\n".join(lines) + "\n")

    df, window = read_events(path)
    result = compute(
        df, window, gas_price_wei=20_000_000_000, eth_price_1e8=200000000000
    )

    assert "net_result" in result and result["net_result"] is not None
    assert result["arb_profit_realized"] is None, (
        "arb_profit_realized must be None on a trace with no extPriceGas field "
        f"(got {result['arb_profit_realized']!r})"
    )


# ---------------------------------------------------------------------------
# Property 6: metrics identities (hand-computed, independent of the source)
# ---------------------------------------------------------------------------


def _base_window_from_real_run(name):
    """Get a structurally valid window dict from one real, cheap replay."""
    wd, rd = _adv_dirs(name)
    run_one(
        "MyHook",
        "ETHUSDT",
        "SHIBUSDT",
        CALIBRATION_START,
        CALIBRATION_START + 5 * 60_000,  # tiny 5-candle window, just for shape
        fee_pips=3000,
        work_dir=wd,
        results_dir=rd,
        uu_mode="off",
        warmup_candles=0,  # a 5-candle trace is shorter than the default 60-candle warm-up
    )
    jf = next(rd.rglob("*.jsonl"))
    _, window = read_events(jf)
    return window


def test_net_result_tt_matches_hand_computed_sum():
    window = _base_window_from_real_run("net_result_tt")

    # price0 = $2000.00000000, price1 = $1.00000000 (1e8-scaled)
    extPrice0, extPrice1 = 200000000000, 100000000

    # Row A (arb): sells 1 token0, receives 1990 token1 (a $10 loss to fee/spread)
    rowA = _pre_uu_swap_record(0, True, 10**18, 1990 * 10**18, -(10**18), 1990 * 10**18)
    rowA["trader"], rowA["rWad"], rowA["pWad"], rowA["extPriceGas"] = (
        "arb",
        0,
        0,
        extPrice0,
    )

    # Row B (uu): sells 500 token1, receives 0.24 token0 (a $20 loss)
    rowB = _pre_uu_swap_record(
        1, False, 500 * 10**18, int(0.24e18), int(0.24e18), -500 * 10**18
    )
    rowB["trader"], rowB["rWad"], rowB["pWad"], rowB["extPriceGas"] = (
        "uu",
        -3 * 10**15,
        int(0.5e18),
        extPrice0,
    )

    swaps = pd.DataFrame([rowA, rowB])

    # Independent reference: net_result_tt = -sum(delta0*P0 + delta1*P1) / (1e18*1e8)
    total = Fraction(0)
    for row in (rowA, rowB):
        total += Fraction(row["delta0"]) * Fraction(extPrice0) + Fraction(
            row["delta1"]
        ) * Fraction(extPrice1)
    expected_net_result_tt = float(-total / Fraction(10**18 * 10**8))

    result = compute(
        swaps, window, gas_price_wei=20_000_000_000, eth_price_1e8=extPrice0
    )
    assert result["net_result_tt"] == pytest.approx(expected_net_result_tt, rel=1e-9)
    # Sanity: matches the hand-derived -10 + -20 = -30 => net_result_tt = +30
    assert expected_net_result_tt == pytest.approx(30.0, rel=1e-9)


def test_arb_mtm_equals_negative_net_result_on_all_arb_frame():
    # Independent confirmation using a full real arb-only run (uu off):
    # the identity is a closed-system property of a real window, not
    # something that can be honestly checked on a 2-row toy frame (which
    # has no consistent LP/HODL baseline). Uses the pinned golden fixture.
    golden = json.loads(
        Path("tests/golden/eth-shib-2024-01-01-myhook-3000.json").read_text()
    )
    assert golden["uu_volume"] == 0.0, "fixture must be an all-arb (uu-off) run"
    assert golden["arb_mtm"] == pytest.approx(-golden["net_result"], rel=1e-9, abs=1e-6)


def test_uu_and_arb_volume_split_by_trader_tag():
    window = _base_window_from_real_run("volume_split")
    extPrice0, extPrice1 = 200000000000, 100000000

    rowA = _pre_uu_swap_record(0, True, 10**18, 1990 * 10**18, -(10**18), 1990 * 10**18)
    rowA["trader"], rowA["rWad"], rowA["pWad"], rowA["extPriceGas"] = (
        "arb",
        0,
        0,
        extPrice0,
    )

    rowB = _pre_uu_swap_record(
        1, False, 500 * 10**18, int(0.24e18), int(0.24e18), -500 * 10**18
    )
    rowB["trader"], rowB["rWad"], rowB["pWad"], rowB["extPriceGas"] = (
        "uu",
        -3 * 10**15,
        int(0.5e18),
        extPrice0,
    )

    rowC = _pre_uu_swap_record(
        2, True, 2 * 10**18, 3900 * 10**18, -2 * 10**18, 3900 * 10**18
    )
    rowC["trader"], rowC["rWad"], rowC["pWad"], rowC["extPriceGas"] = (
        "uu",
        int(1e15),
        int(0.8e18),
        extPrice0,
    )

    swaps = pd.DataFrame([rowA, rowB, rowC])
    result = compute(
        swaps, window, gas_price_wei=20_000_000_000, eth_price_1e8=extPrice0
    )

    # arb_volume: row A input is token0, amountIn=1e18 valued at extPrice0 => $2000
    expected_arb_volume = 1.0 * 2000.0
    # uu_volume: row B input token1 amountIn=500e18 @ $1 => $500;
    #            row C input token0 amountIn=2e18 @ $2000 => $4000
    expected_uu_volume = 500.0 * 1.0 + 2.0 * 2000.0

    assert result["arb_volume"] == pytest.approx(expected_arb_volume, rel=1e-6)
    assert result["uu_volume"] == pytest.approx(expected_uu_volume, rel=1e-6)


# `test_uu_participation_is_amountIn_weighted_mean_of_pWad` lived here and was
# removed on 2026-08-10. It pinned the IMPLEMENTATION rather than the quantity,
# and the implementation was wrong twice: it weighted P by the raw `amountIn`,
# which mixes token0 and token1 wei, and it weighted by the EXECUTED volume,
# which is itself proportional to P and so returns E[P^2]/E[P]. A test written
# from the code cannot catch either. The property -- `uu_participation` is the
# retail retention rate, executed potential over potential, in one currency --
# is covered by `test_uu_participation_weights_the_two_directions_in_a_common_currency`
# and `test_uu_participation_is_the_executed_over_potential_volume_ratio` in
# `tests/test_adversarial_econ.py`, both written from the spec's intent rather
# than from this file.

def test_mevcharge_never_exceeds_the_shared_fee_box():
    from experiments.matrix import load_windows

    windows = load_windows()["ETH/SHIB"]
    highs = sorted(
        (w for w in windows if w.get("regime") == "high"),
        key=lambda w: -w["volatility"],
    )
    window = highs[0]  # highest realised volatility real window available

    wd, rd = _adv_dirs("mevcharge_box")
    result = run_one(
        "MEVChargeHook",
        "ETHUSDT",
        "SHIBUSDT",
        window["start_ms"],
        window["end_ms"],
        fee_pips=0,
        size_dependent=True,
        gas_price_wei=80_000_000_000,  # highest gas scenario -> larger arb sizes
        work_dir=wd,
        results_dir=rd,
        uu_mode="off",
    )
    jf = next(rd.rglob("*.jsonl"))
    df, _ = read_events(jf)

    assert len(df) > 0, (
        "interface underdocumented: no swaps logged, cannot exercise the box"
    )
    assert df["feePips"].max() <= 10000, (
        f"fee box violated: max feePips={df['feePips'].max()}"
    )
    assert (df["feePips"] > 10000).sum() == 0
    # The surcharge branch should actually have fired (fee above the 3000-pip
    # base) for this to be a meaningful check, not a vacuous pass.
    fired = (df["feePips"] > 3000).sum()
    assert fired > 0, (
        "surcharge branch never fired in this window -- the >=10000 check "
        "would be vacuous; picked the highest-volatility real window and "
        "highest gas scenario available, still saw no elevated fee"
    )
    assert result["trade_count"] == len(df)


# ---------------------------------------------------------------------------
# Property 8: economic sanity end-to-end (real short run, UU on, MyHook)
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_higher_fee_strictly_thins_uu_amount_in():
    low_wd, low_rd = _adv_dirs("uu_fee_low")
    high_wd, high_rd = _adv_dirs("uu_fee_high")

    run_one(
        "MyHook",
        "ETHUSDT",
        "SHIBUSDT",
        CALIBRATION_START,
        CALIBRATION_START + DAY_MS,
        fee_pips=500,
        work_dir=low_wd,
        results_dir=low_rd,
        uu_mode="share",
    )
    run_one(
        "MyHook",
        "ETHUSDT",
        "SHIBUSDT",
        CALIBRATION_START,
        CALIBRATION_START + DAY_MS,
        fee_pips=6000,
        work_dir=high_wd,
        results_dir=high_rd,
        uu_mode="share",
    )

    df_low, _ = read_events(next(low_rd.rglob("*.jsonl")))
    df_high, _ = read_events(next(high_rd.rglob("*.jsonl")))

    uu_low = df_low[df_low["trader"] == "uu"]
    uu_high = df_high[df_high["trader"] == "uu"]

    total_in_low = sum(uu_low["amountIn"].tolist())
    total_in_high = sum(uu_high["amountIn"].tolist())

    assert len(uu_low) > 0 and len(uu_high) > 0, (
        "UU swaps must be present at both fee levels"
    )
    assert total_in_high < total_in_low, (
        f"higher static fee should thin UU volume: low-fee total amountIn={total_in_low}, "
        f"high-fee total amountIn={total_in_high}"
    )

    # UU swaps present in both directions, at both fee levels
    for df, label in [(uu_low, "low"), (uu_high, "high")]:
        assert set(df["zeroForOne"].unique()) == {True, False}, (
            f"{label}-fee run missing a UU direction"
        )

    # every UU record: 0 < pWad <= 1e18, and pWad == 1e18 iff rWad >= 0
    for df, label in [(uu_low, "low"), (uu_high, "high")]:
        assert (df["pWad"] > 0).all(), f"{label}: found non-positive pWad"
        assert (df["pWad"] <= WAD).all(), f"{label}: found pWad > 1e18"
        favorable = df["rWad"] >= 0
        assert (df.loc[favorable, "pWad"] == WAD).all(), (
            f"{label}: r>=0 rows must have pWad==1e18 exactly"
        )
        assert (df.loc[~favorable, "pWad"] < WAD).all(), (
            f"{label}: r<0 rows must have pWad<1e18"
        )


@pytest.mark.slow
def test_conservation_error_below_tolerance_with_uu_on():
    wd, rd = _adv_dirs("conservation")
    result = run_one(
        "MyHook",
        "ETHUSDT",
        "SHIBUSDT",
        CALIBRATION_START,
        CALIBRATION_START + DAY_MS,
        fee_pips=3000,
        work_dir=wd,
        results_dir=rd,
        uu_mode="share",
    )
    assert abs(result["conservation_error_token0"]) < 1e-9
    assert abs(result["conservation_error_token1"]) < 1e-9
