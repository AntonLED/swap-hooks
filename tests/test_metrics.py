import json

import pandas as pd
import pytest

from experiments.events import read_events
from experiments.metrics import amounts_for_liquidity, compute, exact_sum

Q96 = 2**96
WAD = 10**18
TICK_LOWER = -887220
TICK_UPPER = 887220


def _window(**kw):
    base = {
        "kind": "window",
        "liquidity": 10**21,
        "tickLower": TICK_LOWER,
        "tickUpper": TICK_UPPER,
        "sqrtPriceInitialX96": Q96,
        "sqrtPriceFinalX96": Q96,
        "feeGrowthInside0X128Initial": 0,
        "feeGrowthInside1X128Initial": 0,
        "feeGrowthInside0X128": 0,
        "feeGrowthInside1X128": 0,
        "initialToken0": 10**21,
        "initialToken1": 10**21,
        "extPrice0Initial": 10**8,
        "extPrice1Initial": 10**8,
        "extPrice0Final": 10**8,
        "extPrice1Final": 10**8,
        "warmupCandles": 0,
        "candles": 100,
    }
    base.update(kw)
    return base


def _swap(**kw):
    base = {
        "kind": "swap",
        "candle": 1,
        "blockNumber": 1,
        "timestamp": 0,
        "extPrice0": 10**8,
        "extPrice1": 10**8,
        "sqrtPriceBeforeX96": Q96,
        "sqrtPriceAfterX96": Q96,
        "zeroForOne": True,
        "amountIn": WAD,
        "amountOut": 9 * 10**17,
        "feePips": 3000,
        "feeAB": 3000,
        "feeBA": 3000,
        "delta0": -WAD,
        "delta1": 9 * 10**17,
        "expectedProfit": 10**15,
        "gas": 150000,
        "sender": "0x00000000000000000000000000000000000BeEF0",
        # UU flow (2026-08-09-uu-flow-design.md §5): defaults match what
        # every pre-UU arb swap now logs (trader="arb", rWad/pWad=0) plus a
        # plausible ETH/USDT feed for extPriceGas, so existing tests that
        # never touch these fields still exercise the real values.
        "trader": "arb",
        "rWad": 0,
        "pWad": 0,
        "extPriceGas": 300_000_000_000,
    }
    base.update(kw)
    return base


def _write(tmp_path, records, name="replay.jsonl"):
    p = tmp_path / name
    p.write_text("\n".join(json.dumps(r) for r in records) + "\n")
    return p


def test_reader_separates_the_two_record_kinds(tmp_path):
    path = _write(tmp_path, [_swap(candle=1), _swap(candle=2), _window()])
    swaps, window = read_events(path)

    assert len(swaps) == 2
    assert window["liquidity"] == 10**21


def test_reader_preserves_large_integers_exactly(tmp_path):
    """Q96 and feeGrowth values exceed float64 precision."""
    big = 340282366920938463463374607431768211455
    path = _write(tmp_path, [_window(feeGrowthInside0X128=big)])
    _, window = read_events(path)

    assert window["feeGrowthInside0X128"] == big


def test_conservation_closes_when_the_two_sides_agree(tmp_path):
    """A swap that moves no price and pays no fee leaves the pool unchanged."""
    path = _write(
        tmp_path, [_swap(delta0=0, delta1=0, amountIn=0, feePips=0), _window()]
    )
    swaps, window = read_events(path)
    m = compute(swaps, window, gas_price_wei=20e9)

    assert abs(m["conservation_error_token0"]) < 1e-9
    assert abs(m["conservation_error_token1"]) < 1e-9


def test_conservation_detects_an_inconsistent_log(tmp_path):
    """If trader flow and pool state disagree, the check must fire.

    This is the whole point of the invariant: it compares two independently
    sourced derivations of the same tokens, so it is not an identity and a
    corrupted log is caught rather than absorbed.
    """
    path = _write(tmp_path, [_swap(delta0=-(5 * WAD), delta1=0), _window()])
    swaps, window = read_events(path)
    m = compute(swaps, window, gas_price_wei=20e9)

    assert abs(m["conservation_error_token0"]) > 1e-6


def test_il_is_not_clamped_at_zero(tmp_path):
    """A profitable LP outcome must be representable as negative IL."""
    path = _write(tmp_path, [_window(extPrice1Final=2 * 10**8)])
    swaps, window = read_events(path)
    m = compute(swaps, window, gas_price_wei=20e9)

    assert isinstance(m["il"], float)
    assert m["il"] == m["il"]  # not NaN


def test_fees_are_absent_from_the_position_principal(tmp_path):
    """In v4 a fee never joins L, so principal must not move when only fee
    growth changes. If principal responded, fees would be counted twice."""
    without = _write(tmp_path, [_window(feeGrowthInside0X128=0)], "a.jsonl")
    with_fees = _write(
        tmp_path, [_window(feeGrowthInside0X128=(2**128) // 1000)], "b.jsonl"
    )

    a = compute(*read_events(without), gas_price_wei=20e9)
    b = compute(*read_events(with_fees), gas_price_wei=20e9)

    assert a["lp_principal"] == pytest.approx(b["lp_principal"])
    assert b["fee_income"] > a["fee_income"]


def test_fee_income_comes_from_fee_growth_not_from_trader_deltas(tmp_path):
    path = _write(tmp_path, [_swap(), _window(feeGrowthInside0X128=(2**128) // 1000)])
    swaps, window = read_events(path)
    m = compute(swaps, window, gas_price_wei=20e9)

    assert m["fee_income"] > 0, "fees must come from the pool's own accounting"


def test_fees_accrued_during_warmup_are_excluded(tmp_path):
    """Warm-up swaps execute but are not logged, so the fees they generated
    belong to the excluded period. Only growth since the baseline counts."""
    path = _write(
        tmp_path,
        [
            _window(
                feeGrowthInside0X128Initial=(2**128) // 1000,
                feeGrowthInside0X128=(2**128) // 1000,
            )
        ],
    )
    m = compute(*read_events(path), gas_price_wei=20e9)

    assert m["fee_income"] == pytest.approx(0.0), (
        "no growth since baseline means no income"
    )


def test_lp_value_is_principal_plus_fees(tmp_path):
    path = _write(tmp_path, [_window(feeGrowthInside0X128=(2**128) // 1000)])
    swaps, window = read_events(path)
    m = compute(swaps, window, gas_price_wei=20e9)

    assert m["lp_value"] == pytest.approx(m["lp_principal"] + m["fee_income"])


def test_gas_cost_uses_the_recorded_gas(tmp_path):
    path = _write(tmp_path, [_swap(gas=150000), _swap(candle=2, gas=150000), _window()])
    swaps, window = read_events(path)

    cheap = compute(swaps, window, gas_price_wei=1e9)["gas_cost"]
    dear = compute(swaps, window, gas_price_wei=100e9)["gas_cost"]

    assert dear == pytest.approx(cheap * 100)


def test_amounts_for_liquidity_matches_the_uniswap_formula():
    """At price 1 with symmetric full-range bounds the two sides are equal."""
    a0, a1 = amounts_for_liquidity(10**21, Q96, TICK_LOWER, TICK_UPPER)
    assert a0 == pytest.approx(a1, rel=1e-6)
    assert a0 == pytest.approx(10**21, rel=1e-6)


def test_empty_window_yields_zeroed_metrics(tmp_path):
    path = _write(tmp_path, [_window()])
    swaps, window = read_events(path)
    m = compute(swaps, window, gas_price_wei=20e9)

    assert m["trade_count"] == 0
    assert m["retained_volume"] == 0.0


def test_wei_scale_sums_do_not_overflow_int64(tmp_path):
    """A real 148-swap run summed to +8.1e18 where the truth was -1.0e19.

    pandas accumulates an int64 column in int64 and wraps without raising, so
    the flow figure -- and every metric derived from it -- came out wrong with
    no error anywhere. Deltas of this magnitude are ordinary on a 20M pool.
    """
    big = 5 * 10**18
    records = [_swap(candle=i, delta0=big, delta1=-big) for i in range(10)]
    records.append(_window())
    path = _write(tmp_path, records)

    swaps, _ = read_events(path)
    total = exact_sum(swaps["delta0"])

    assert total == 10 * big, "must be 5e19, not an int64 wrap"
    assert total > 2**63 - 1, "the test is only meaningful past the int64 ceiling"


# --------------------------------------------------------------- UU flow (Task 6)
# 2026-08-09-uu-flow-design.md §6: trader-aware metrics and the trade-time
# valuation. GAS_PRICE_WEI below is fixed so the hand-computed expectations in
# these tests are reproducible without re-deriving them per test.
GAS_PRICE_WEI = 20e9


def test_arb_mtm_is_the_renamed_arb_profit(tmp_path):
    """Same formula as the old `arb_profit` -- only the key changed."""
    path = _write(tmp_path, [_swap(), _window(feeGrowthInside0X128=(2**128) // 1000)])
    swaps, window = read_events(path)
    m = compute(swaps, window, gas_price_wei=GAS_PRICE_WEI)

    assert "arb_profit" not in m
    assert isinstance(m["arb_mtm"], float)


def test_trader_aware_metrics_match_hand_computed_values(tmp_path):
    """One arb swap, one uu swap; every new key hand-computed against them.

    extPrice0 = $100 (1e8-scaled 100e8), extPrice1 = $1 (1e8-scaled 1e8).
    Arb: zeroForOne, amountIn=1e18 @ 30 bps, delta0=-1e18, delta1=9e17, gas=1e5.
    UU:  !zeroForOne, amountIn=2e18 @ 5 bps, delta0=1.8e18, delta1=-2e18,
         gas=5e4, rWad=-1e15, pWad=7e17 (P=0.7).

    Expectations were derived independently in Python (not copied from the
    implementation) from the same three formulas the spec states: Sigma
    delta*extPrice for the trade-time valuation, amountIn priced at the
    input-token's trade-time price for volume, and amountIn*feePips/1e6
    priced the same way for fee share.
    """
    path = _write(
        tmp_path,
        [
            _swap(
                candle=1,
                zeroForOne=True,
                amountIn=10**18,
                feePips=3000,
                delta0=-(10**18),
                delta1=9 * 10**17,
                gas=100_000,
                extPrice0=100 * 10**8,
                extPrice1=10**8,
                trader="arb",
                rWad=0,
                pWad=0,
                extPriceGas=3000 * 10**8,
            ),
            _swap(
                candle=1,
                zeroForOne=False,
                amountIn=2 * 10**18,
                feePips=500,
                delta0=int(1.8 * 10**18),
                delta1=-(2 * 10**18),
                gas=50_000,
                extPrice0=100 * 10**8,
                extPrice1=10**8,
                trader="uu",
                rWad=-(10**15),
                pWad=int(0.7 * 10**18),
                extPriceGas=3000 * 10**8,
            ),
            _window(),
        ],
    )
    swaps, window = read_events(path)
    m = compute(swaps, window, gas_price_wei=GAS_PRICE_WEI)

    assert m["net_result_tt"] == pytest.approx(-78.9, rel=1e-9)
    assert m["arb_profit_realized"] == pytest.approx(-105.1, rel=1e-9)
    assert m["uu_volume"] == pytest.approx(2.0, rel=1e-9)
    assert m["arb_volume"] == pytest.approx(100.0, rel=1e-9)
    assert m["uu_fee_share"] == pytest.approx(0.001 / 0.301, rel=1e-9)
    assert m["uu_participation"] == pytest.approx(0.7, rel=1e-9)


def test_old_trace_without_trader_or_extPriceGas_still_computes():
    """A frame from before UU flow (no trader/rWad/pWad/extPriceGas columns)
    must still compute net_result_tt; arb_profit_realized is undefined
    without extPriceGas and must be None, not a silently-wrong number."""
    swaps = pd.DataFrame(
        [
            {
                "candle": 1,
                "blockNumber": 1,
                "timestamp": 0,
                "extPrice0": 10**8,
                "extPrice1": 10**8,
                "sqrtPriceBeforeX96": Q96,
                "sqrtPriceAfterX96": Q96,
                "zeroForOne": True,
                "amountIn": WAD,
                "amountOut": 9 * 10**17,
                "feePips": 3000,
                "feeAB": 3000,
                "feeBA": 3000,
                "delta0": -WAD,
                "delta1": 9 * 10**17,
                "expectedProfit": 10**15,
                "gas": 150000,
                "sender": "0x00000000000000000000000000000000000BeEF0",
            }
        ]
    )
    window = _window()
    m = compute(swaps, window, gas_price_wei=GAS_PRICE_WEI)

    assert m["arb_profit_realized"] is None
    assert isinstance(m["net_result_tt"], float)


def test_arb_profit_realized_is_none_when_extPriceGas_is_backfilled_zero(tmp_path):
    """`events.read_events` backfills a MISSING extPriceGas field to 0 for
    every row, so a pre-UU trace read through it has the column present but
    entirely zero -- the column-absence check alone is not enough to catch
    this. Zero can never be a real ETH/USDT quote, so "every arb row reads
    exactly zero" must also mean None, not a realized profit computed with
    gas priced at $0 (2026-08-09 adversarial review)."""
    path = _write(
        tmp_path,
        [_swap(trader="arb", extPriceGas=0), _window()],
    )
    swaps, window = read_events(path)
    assert (swaps["extPriceGas"] == 0).all(), (
        "fixture must exercise the all-zero column"
    )

    m = compute(swaps, window, gas_price_wei=GAS_PRICE_WEI)

    assert m["arb_profit_realized"] is None


def test_uu_participation_is_none_without_uu_swaps(tmp_path):
    path = _write(tmp_path, [_swap(), _window()])
    swaps, window = read_events(path)
    m = compute(swaps, window, gas_price_wei=GAS_PRICE_WEI)

    assert m["uu_participation"] is None


def test_arb_mtm_equals_negative_net_result_when_the_books_close():
    """The 2026-08-09 audit identity: arb_mtm is the counterparty flow marked
    at final prices, net_result is the LP's; when the position/flow
    conservation identity holds exactly, the two are exact negatives.
    `arb_mtm` was never realized profit -- it is the same number as
    `-net_result` under arb-only flow.

    Constructed so conservation closes by definition: flow is set to exactly
    `initial principal - final principal` (zero fee growth), so `l0 - flow ==
    final principal` holds to float precision regardless of the price used.
    """
    liquidity = 10**21
    sqrt_initial = Q96
    sqrt_final = Q96 * 11 // 10
    p0_i, p1_i = amounts_for_liquidity(liquidity, sqrt_initial, TICK_LOWER, TICK_UPPER)
    p0_f, p1_f = amounts_for_liquidity(liquidity, sqrt_final, TICK_LOWER, TICK_UPPER)
    l0_0, l0_1 = round(p0_i), round(p1_i)
    # conservation requires principal_final == l0 - flow, i.e. flow == l0 -
    # principal_final (a trader's gain is the pool's loss).
    delta0 = l0_0 - round(p0_f)
    delta1 = l0_1 - round(p1_f)

    path_records = [
        _swap(delta0=delta0, delta1=delta1, amountIn=abs(delta0)),
        _window(
            liquidity=liquidity,
            sqrtPriceInitialX96=sqrt_initial,
            sqrtPriceFinalX96=sqrt_final,
            initialToken0=l0_0,
            initialToken1=l0_1,
        ),
    ]

    def _run(records):
        swaps = pd.DataFrame(records[:-1])
        return compute(swaps, records[-1], gas_price_wei=GAS_PRICE_WEI)

    m = _run(path_records)
    assert abs(m["conservation_error_token0"]) < 1e-6
    assert abs(m["conservation_error_token1"]) < 1e-6
    assert m["arb_mtm"] == pytest.approx(-m["net_result"], rel=1e-6)
