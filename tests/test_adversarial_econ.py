"""Adversarial verification of the economics, 2026-08-10.

Method: derive an independent reference from the SPEC (mpmath / Decimal / exact
integer arithmetic) and compare, rather than reading the implementation and
agreeing with it. Every test's docstring says WHAT WOULD BE WRONG IN THE PAPER
if it failed.

Specs used as ground truth:
  docs/superpowers/specs/2026-08-09-uu-flow-design.md   (UU model: SS2, SS3, SS6)
  docs/superpowers/specs/2026-08-02-dynamic-fee-experiments-design.md

Tests marked FAILS-BY-DESIGN document a defect found in this pass; they are not
scaffolding to be deleted, they are the report.
"""

from __future__ import annotations

import glob
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from mpmath import exp as mp_exp
from mpmath import mp, mpf

from experiments.aggregate import AXES, paired_against_baseline
from experiments.metrics import amounts_for_liquidity, compute, exact_sum
from experiments.stats import benjamini_hochberg, wilcoxon_paired
from experiments.uu import UU_LAMBDA_WAD, export_uu_trace, kappa, uu_profile

mp.dps = 60

ROOT = Path(__file__).resolve().parents[1]
Q96 = 2**96
WAD = 10**18
PRICE_SCALE = 10**8
ONE_PIPS = 10**6
TICK_LOWER = -887220
TICK_UPPER = 887220

# One basket, spec SS4.3 / SS3.
BASKET_USDT = 20_000_000


# --------------------------------------------------------------------------
# frame builders -- deliberately independent of tests/test_metrics.py
# --------------------------------------------------------------------------


def _window(**kw) -> dict:
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
        "extPrice0Initial": PRICE_SCALE,
        "extPrice1Initial": PRICE_SCALE,
        "extPrice0Final": PRICE_SCALE,
        "extPrice1Final": PRICE_SCALE,
        "warmupCandles": 0,
        "candles": 100,
    }
    base.update(kw)
    return base


def _swap(**kw) -> dict:
    base = {
        "candle": 1,
        "blockNumber": 1,
        "timestamp": 0,
        "extPrice0": PRICE_SCALE,
        "extPrice1": PRICE_SCALE,
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
        "expectedProfit": 0,
        "gas": 150_000,
        "sender": "0x00000000000000000000000000000000000BeEF0",
        "trader": "arb",
        "rWad": 0,
        "pWad": 0,
        "extPriceGas": 300_000_000_000,
    }
    base.update(kw)
    return base


def _frame(swaps: list[dict]) -> pd.DataFrame:
    """Build the frame the way `events.read_events` does: wei-scale columns as
    object dtype so nothing accumulates in int64."""
    frame = pd.DataFrame(swaps)
    big = [
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
    for column in big:
        frame[column] = pd.Series(
            [int(v) for v in frame[column]], dtype="object", index=frame.index
        )
    return frame


def _uu_swaps():
    """A hand-built UU candle on an ETH/SHIB-shaped pair, where the answer is
    known exactly.

    token0 = ETH at 3000 USDT, token1 = SHIB at 0.00002 USDT. Both directions
    carry EXACTLY 100_000 USDT of *potential* volume (v0/2 per spec SS2.3).
    A->B executes at P = 1.0, B->A at P = 0.2, so:

      executed volume  = 100_000*1.0 + 100_000*0.2 = 120_000 USDT
      potential volume = 200_000 USDT
      participation    = 120_000 / 200_000 = 0.6
    """
    price0 = 3000 * PRICE_SCALE
    price1 = 2000  # 0.00002 * 1e8
    p_ab, p_ba = WAD, WAD // 5
    pot_usdt_wad = 100_000 * WAD

    exec_ab_wad = pot_usdt_wad * p_ab // WAD
    exec_ba_wad = pot_usdt_wad * p_ba // WAD
    amount_ab = exec_ab_wad * PRICE_SCALE // price0  # token0 wei
    amount_ba = exec_ba_wad * PRICE_SCALE // price1  # token1 wei

    return [
        _swap(
            trader="uu",
            zeroForOne=True,
            extPrice0=price0,
            extPrice1=price1,
            amountIn=amount_ab,
            delta0=-amount_ab,
            delta1=0,
            pWad=p_ab,
            feePips=3000,
        ),
        _swap(
            trader="uu",
            zeroForOne=False,
            extPrice0=price0,
            extPrice1=price1,
            amountIn=amount_ba,
            delta0=0,
            delta1=-amount_ba,
            pWad=p_ba,
            feePips=3000,
        ),
    ]


# --------------------------------------------------------------------------
# 1. uu_participation -- the metric the third experiment's headline rests on
# --------------------------------------------------------------------------


def test_uu_participation_weights_the_two_directions_in_a_common_currency():
    """WHAT WOULD BE WRONG: `uu_participation` is reported per policy and
    plotted against `exp(-lambda*fee)` (notebook 08, PROGRESS headline). It is
    weighted by the RAW `amountIn`, which is token0 wei for an A->B swap and
    token1 wei for a B->A swap. On ETH/SHIB those units differ by ~1.5e8, so
    the A->B direction carries ~5e-9 of the weight: the published number is
    the B->A participation rate wearing a two-sided name.

    Here both directions carry exactly 100k USDT of potential volume, so any
    honest weighting is bounded by the two P values (0.2 and 1.0). The raw-wei
    weighting returns 0.2 -- outside the range a mean of the two can occupy
    once either direction has non-negligible weight.
    """
    metrics = compute(_frame(_uu_swaps()), _window(), gas_price_wei=2e10)
    got = metrics["uu_participation"]

    # Executed-USDT weighting (the least favourable honest reading) gives
    # (1.0*100k + 0.2*20k) / 120k = 0.8667; potential-USDT weighting gives 0.6.
    assert got > 0.5, (
        f"uu_participation={got!r}: the A->B leg (P=1.0, 100k USDT) has been "
        "weighted out of existence by the token1-denominated B->A amountIn"
    )


def test_uu_participation_is_the_executed_over_potential_volume_ratio():
    """WHAT WOULD BE WRONG: the paper reports participation as the retail
    RETENTION RATE and reads the gap against `exp(-lambda*fee)` as the signed
    pool deviation (spec SS2.2, notebook 08 prose). A retention rate is
    executed volume / potential volume = sum(v0*P) / sum(v0).

    `metrics.compute` weights P by the EXECUTED volume, which is itself
    proportional to P, so it returns E[P^2]/E[P] -- upward biased by Jensen,
    and biased MORE at higher fees where the spread of P is wider. Measured on
    the shipped matrix (ETH/SHIB+ETH/USDC+USDC/USDT, 12 traces per level) the
    reported figure overstates the true retention rate by +4.2% at 5 bps,
    +10.3% at 30 bps, +19.9% at 60 bps and +46.9% at 100 bps: the published
    participation-vs-fee curve is flattened, and the "sits above the pure-fee
    curve" reading is largely self-selection rather than pool deviation.

    Hand-built here so the true answer is exact: 120_000 executed of 200_000
    potential = 0.6.
    """
    metrics = compute(_frame(_uu_swaps()), _window(), gas_price_wei=2e10)
    assert metrics["uu_participation"] == pytest.approx(0.6, rel=1e-12)


def test_uu_participation_is_bounded_by_the_p_values_it_averages():
    """WHAT WOULD BE WRONG: any weighted mean of P must lie between min(P) and
    max(P). This is the weakest possible statement about the metric and it
    still catches the unit mixing, so it is here as the floor of the claim.
    """
    metrics = compute(_frame(_uu_swaps()), _window(), gas_price_wei=2e10)
    assert 0.2 <= metrics["uu_participation"] <= 1.0


# --------------------------------------------------------------------------
# 2. trade-time valuation, volumes and fee share
# --------------------------------------------------------------------------


def test_net_result_tt_is_minus_the_exact_integer_trade_time_flow_value():
    """WHAT WOULD BE WRONG: `net_result_tt` is a pre-registered CO-PRIMARY
    quantity (spec SS6). If it were computed in float over wei-scale deltas, or
    if the deltas were summed through pandas, the number the paper reports for
    every one of 15,552 cells would be silently wrong -- a real run already
    produced +8.1e18 where the truth was -1.0e19.

    Reference: exact Python-int sum, deltas chosen to overflow int64 when
    accumulated (5.8e18 + 5.8e18 > 9.22e18).
    """
    big = 5_800_000_000_000_000_000
    swaps = [
        _swap(
            delta0=big, delta1=-big, extPrice0=2 * PRICE_SCALE, extPrice1=PRICE_SCALE
        ),
        _swap(
            delta0=big, delta1=-big, extPrice0=3 * PRICE_SCALE, extPrice1=PRICE_SCALE
        ),
    ]
    frame = _frame(swaps)

    reference = -sum(
        int(r["delta0"]) * int(r["extPrice0"]) + int(r["delta1"]) * int(r["extPrice1"])
        for r in swaps
    ) / (WAD * PRICE_SCALE)

    metrics = compute(frame, _window(), gas_price_wei=2e10)
    assert metrics["net_result_tt"] == pytest.approx(reference, rel=1e-15)
    # And the sign: the LP loses when the counterparty walks away with value.
    assert reference < 0
    assert metrics["net_result_tt"] < 0


def test_net_result_equals_minus_arb_mtm_on_a_closed_system():
    """WHAT WOULD BE WRONG: spec SS6 states `arb_mtm` is identically
    `-net_result` under arb-only flow. That identity is what licenses reading
    `net_result` as "what the counterparty took". If it broke, the LP ledger
    and the counterparty ledger would no longer be two views of one closed
    system and the conservation gate would be measuring nothing.
    """
    liquidity = 10**21
    sqrt_start, sqrt_end = Q96, int(Q96 * 1.05**0.5)
    start0, start1 = amounts_for_liquidity(
        liquidity, sqrt_start, TICK_LOWER, TICK_UPPER
    )
    end0, end1 = amounts_for_liquidity(liquidity, sqrt_end, TICK_LOWER, TICK_UPPER)

    # Trader delta = what left the pool. Built from the position formula so the
    # window state and the swap log are two views of one closed system, exactly
    # as the harness produces them.
    swaps = [
        _swap(
            zeroForOne=False,
            delta0=int(start0 - end0),
            delta1=int(start1 - end1),
            amountIn=int(end1 - start1),
        )
    ]
    window = _window(
        liquidity=liquidity,
        sqrtPriceFinalX96=sqrt_end,
        initialToken0=int(start0),
        initialToken1=int(start1),
        extPrice0Final=2 * PRICE_SCALE,
        extPrice1Final=PRICE_SCALE,
    )
    metrics = compute(_frame(swaps), window, gas_price_wei=2e10)

    assert abs(metrics["conservation_error_token0"]) < 1e-12
    assert abs(metrics["conservation_error_token1"]) < 1e-12
    assert metrics["net_result"] == pytest.approx(-metrics["arb_mtm"], abs=1e-3)


def test_arb_profit_realized_nets_gas_at_the_trade_time_eth_price_and_ignores_uu():
    """WHAT WOULD BE WRONG: `arb_profit_realized` is the new column that
    replaces the mislabelled `arb_profit`. If UU rows leaked into it, or if gas
    were valued at token0's price rather than the ETH feed, the paper's
    statement about how much the arbitrageur actually earned would be wrong --
    and on USDC/USDT it would be wrong by the entire ETH price.
    """
    gas_price = 2e10
    eth = 3000 * PRICE_SCALE
    arb = _swap(
        delta0=-(10**18),
        delta1=2 * 10**18,
        extPrice0=PRICE_SCALE,
        extPrice1=PRICE_SCALE,
        extPriceGas=eth,
        gas=100_000,
    )
    uu = _swap(
        trader="uu",
        delta0=-(10**20),
        delta1=10**20,
        extPrice0=PRICE_SCALE,
        extPrice1=PRICE_SCALE,
        extPriceGas=eth,
        gas=100_000,
        pWad=WAD,
    )
    metrics = compute(_frame([arb, uu]), _window(), gas_price_wei=gas_price)

    gross = (-(10**18) * PRICE_SCALE + 2 * 10**18 * PRICE_SCALE) / (WAD * PRICE_SCALE)
    gas_usd = (100_000 * gas_price / WAD) * (eth / PRICE_SCALE)
    assert metrics["arb_profit_realized"] == pytest.approx(gross - gas_usd, rel=1e-12)


def test_arb_profit_realized_is_none_only_when_the_eth_feed_was_backfilled():
    """WHAT WOULD BE WRONG: `events.read_events` backfills a missing
    `extPriceGas` to 0. If that zero were taken at face value, every pre-UU
    trace would report gas as free and a realized arbitrage profit the trace
    cannot support. The sentinel must fire on backfill and NOT fire on a cell
    that genuinely has no arbitrage.
    """
    backfilled = _swap(extPriceGas=0)
    assert compute(_frame([backfilled]), _window(), 2e10)["arb_profit_realized"] is None

    uu_only = _swap(trader="uu", extPriceGas=0, pWad=WAD)
    assert compute(_frame([uu_only]), _window(), 2e10)["arb_profit_realized"] == 0.0


def test_volume_and_fee_share_convert_both_directions_through_prices():
    """WHAT WOULD BE WRONG: `uu_volume`, `arb_volume` and `uu_fee_share` are
    the columns that separate "kept the benign flow" from "priced everyone
    out". Summing a token0 amount and a token1 amount without converting
    through prices would make the ETH/SHIB volume split meaningless (SHIB
    amounts are ~1e8x larger numerically), and `uu_fee_share` would read ~1.0
    for every policy regardless of who actually paid.
    """
    price0, price1 = 3000 * PRICE_SCALE, 2000
    # 100k USDT of UU volume in token1, 100k USDT of arb volume in token0.
    amount_uu = 100_000 * WAD * PRICE_SCALE // price1
    amount_arb = 100_000 * WAD * PRICE_SCALE // price0
    swaps = [
        _swap(
            trader="uu",
            zeroForOne=False,
            extPrice0=price0,
            extPrice1=price1,
            amountIn=amount_uu,
            feePips=3000,
            pWad=WAD,
        ),
        _swap(
            trader="arb",
            zeroForOne=True,
            extPrice0=price0,
            extPrice1=price1,
            amountIn=amount_arb,
            feePips=3000,
        ),
    ]
    metrics = compute(_frame(swaps), _window(), gas_price_wei=2e10)

    assert metrics["uu_volume"] == pytest.approx(100_000, rel=1e-9)
    assert metrics["arb_volume"] == pytest.approx(100_000, rel=1e-9)
    # Equal volume at an equal fee rate is an equal fee bill.
    assert metrics["uu_fee_share"] == pytest.approx(0.5, rel=1e-9)


def test_uu_volume_plus_arb_volume_is_not_the_retained_volume_column():
    """WHAT WOULD BE WRONG: spec SS6 calls `uu_volume`/`arb_volume` the
    "retained_volume splits". They are not: `retained_volume` values every
    amountIn at END-OF-WINDOW prices while the two splits value each at its own
    TRADE-TIME price. On the shipped matrix the sum ranges 0.912x to 1.040x of
    `retained_volume`. Any prose or figure that treats `arb_volume /
    retained_volume` as the arbitrage share (the kappa pre-registration says it
    reports exactly that share) is off by up to 9%.

    This test pins the current convention so it cannot drift silently; the
    notebooks' `uu_volume / (uu_volume + arb_volume)` is self-consistent and is
    the form that must be used.
    """
    price_then, price_now = PRICE_SCALE, 2 * PRICE_SCALE
    swaps = [
        _swap(
            trader="uu",
            zeroForOne=True,
            amountIn=WAD,
            extPrice0=price_then,
            extPrice1=price_then,
        )
    ]
    window = _window(extPrice0Final=price_now, extPrice1Final=price_now)
    metrics = compute(_frame(swaps), window, gas_price_wei=2e10)

    assert metrics["uu_volume"] == pytest.approx(1.0, rel=1e-12)  # trade-time
    assert metrics["retained_volume"] == pytest.approx(2.0, rel=1e-12)  # final
    assert metrics["uu_volume"] + metrics["arb_volume"] != pytest.approx(
        metrics["retained_volume"]
    )


def test_exact_sum_beats_pandas_on_wei_scale_columns():
    """WHAT WOULD BE WRONG: an int64 column wraps silently. Every wei-scale sum
    in `metrics` must go through `exact_sum`; this is the canary for that rule.
    """
    values = [5_800_000_000_000_000_000, 5_800_000_000_000_000_000]
    series = pd.Series(values, dtype="int64")
    assert series.sum() < 0  # the wrap, reproduced
    assert exact_sum(series) == 11_600_000_000_000_000_000


# --------------------------------------------------------------------------
# 3. UUMath -- Solidity verified against an mpmath reference written from SS2
# --------------------------------------------------------------------------


def _sdiv(a: int, b: int) -> int:
    """Solidity/EVM signed division: truncation toward zero."""
    q = abs(a) // abs(b)
    return q if (a >= 0) == (b >= 0) else -q


def _exp_neg_wad(x: int) -> int:
    """Faithful Python port of `UUMath.expNegWad` (the Solady algorithm).

    Written from the Solidity so the algorithm can be executed and differenced
    against mpmath without forge. Solidity's `>>` on a signed value is an
    arithmetic shift, which is Python's `>>`; `/` and `sdiv` truncate toward
    zero, which is `_sdiv`.
    """
    assert x <= 0
    if x <= -41446531673892822313:
        return 0

    x = _sdiv(x << 78, 5**18)
    k = (_sdiv(x << 96, 54916777467707473351141471128) + 2**95) >> 96
    x = x - k * 54916777467707473351141471128

    y = x + 1346386616545796478920950773328
    y = ((y * x) >> 96) + 57155421227552351082224309758442
    p = y + x - 94201549194550492254356042504812
    p = ((p * y) >> 96) + 28719021644029726153956944680412240
    p = p * x + (4385272521454847904659076985693276 << 96)

    q = x - 2855989394907223263936484059900
    q = ((q * x) >> 96) + 50020603652535783019961831881945
    q = ((q * x) >> 96) - 533845033583426703283633433725380
    q = ((q * x) >> 96) + 3604857256930695427073651918091429
    q = ((q * x) >> 96) - 14423608567350463180887372962807573
    q = ((q * x) >> 96) + 26449188498355588339934803723976023

    r = _sdiv(p, q)
    return (r * 3822833074963236453042738258902158003155416615667) >> (195 - k)


def _r_wad(sqrt_price_x96: int, ext_price_x96: int, fee_pips: int, zero_for_one: bool):
    """Faithful port of `UUMath.rWad`."""
    pool_price_x96 = sqrt_price_x96 * sqrt_price_x96 // Q96
    gamma_wad = (ONE_PIPS - fee_pips) * 10**12
    num, den = (
        (pool_price_x96, ext_price_x96)
        if zero_for_one
        else (ext_price_x96, pool_price_x96)
    )
    return num * gamma_wad // den - WAD


def _r_spec(pool_price, ext_price, fee_pips, zero_for_one):
    """The spec SS2.2 formula in exact rationals, no fixed-point at all:
    A->B  r = gamma*p/P - 1 ;  B->A  r = gamma*P/p - 1.
    """
    gamma = mpf(ONE_PIPS - fee_pips) / mpf(ONE_PIPS)
    ratio = (
        mpf(pool_price) / mpf(ext_price)
        if zero_for_one
        else mpf(ext_price) / mpf(pool_price)
    )
    return gamma * ratio - 1


@pytest.mark.parametrize("fee_pips", [0, 100, 3000, 5900, 10000, 100000])
@pytest.mark.parametrize(
    "deviation", [-0.5, -0.01, -0.001, -1e-6, 0.0, 1e-6, 0.001, 0.01, 0.5]
)
@pytest.mark.parametrize("zero_for_one", [True, False])
def test_uumath_r_matches_the_spec_formula_in_exact_arithmetic(
    fee_pips, deviation, zero_for_one
):
    """WHAT WOULD BE WRONG: `r` is the whole UU model. A quantization or a
    swapped numerator/denominator changes who trades, which changes retained
    volume, fee income and therefore every net-result comparison in the third
    experiment. The previous adversarial pass found `rWad` quantized to 0.1 bp;
    this checks the fixed-point path against exact rationals instead.
    """
    ext_price_x96 = Q96  # external price fixed at 1.0
    pool_price = 1.0 + deviation
    sqrt_price_x96 = int(pool_price**0.5 * Q96)
    pool_price_x96 = sqrt_price_x96 * sqrt_price_x96 // Q96

    got = mpf(_r_wad(sqrt_price_x96, ext_price_x96, fee_pips, zero_for_one)) / mpf(WAD)
    want = _r_spec(pool_price_x96, ext_price_x96, fee_pips, zero_for_one)

    assert abs(got - want) < mpf("1e-15"), f"r off by {float(got - want):.3e}"


@pytest.mark.parametrize(
    "x_wad",
    [
        0,
        -1,
        -(10**12),
        -(10**15),
        -(10**17),
        -(10**18),
        -(2 * 10**18),
        -(10**19),
        -(41 * 10**18),
        -41446531673892822312,
    ],
)
def test_uumath_expnegwad_matches_mpmath(x_wad):
    """WHAT WOULD BE WRONG: `P = exp(-lambda|r|)` decides how much retail
    executes. Spec SS4.1 requires <= 1e-9 relative against an mpmath reference,
    including at the range-reduction boundaries and just above the
    underflow cutoff.
    """
    got_wei = _exp_neg_wad(x_wad)
    want_wei = mp_exp(mpf(x_wad) / mpf(WAD)) * WAD
    error = abs(mpf(got_wei) - want_wei)
    # Either the spec's 1e-9 relative bound (SS4.1) or -- deep in the tail,
    # where exp(x)*1e18 is a handful of wei -- one wei of representation
    # granularity. Both are far below any economically meaningful volume.
    assert error <= mpf("1e-9") * want_wei or error < 1, f"exp off at x={x_wad}"


@pytest.mark.xfail(
    reason=(
        "2026-08-10: `r` moved to the source model's normalised form "
        "(V_out-V_in)/(V_out+V_in) and lambda to 461.404973; its P = 0.5 anchor is lambda = 231 against the un-normalised r = -eps. "
        "Re-point it once the matrix has been re-run under the new r."
    ),
    strict=False,
)
def test_uumath_participation_branches_at_r_zero_and_is_monotone():
    """WHAT WOULD BE WRONG: spec SS2 says `P = 1` for `r >= 0`. If the branch
    were `r > 0`, the exactly-fair case would take the exp path (still 1.0), but
    if it were inverted the "trading toward the reference always executes"
    property -- the mechanism the paper credits for retaining two-sided flow --
    would not exist.
    """
    lam = UU_LAMBDA_WAD

    def participation(r_wad: int) -> int:
        if r_wad >= 0:
            return WAD
        return _exp_neg_wad(_sdiv(lam * r_wad, WAD))

    assert participation(0) == WAD
    assert participation(1) == WAD
    assert participation(-1) < WAD or participation(-1) == WAD  # continuity at 0

    # Monotone decreasing in |r|, and half the flow at 30 bps by construction.
    previous = WAD + 1
    for bps in range(0, 200, 5):
        value = participation(-(bps * WAD) // 10_000)
        assert value <= previous
        previous = value
    assert participation(-(30 * WAD) // 10_000) / WAD == pytest.approx(0.5, rel=1e-3)


def test_r_direction_convention_pool_above_external_favours_the_token0_seller():
    """WHAT WOULD BE WRONG: spec SS2.2 says the pool deviation enters SIGNED --
    a user trading toward the external price gets a bonus. If the two branches
    were swapped, every policy that keeps the pool near the reference would be
    penalised instead of rewarded and the entire ranking of the third
    experiment would invert.
    """
    ext = Q96
    above = int((1.02**0.5) * Q96)  # pool price 2% above external
    below = int((0.98**0.5) * Q96)

    # Pool above external: the seller of token0 gets more token1 than fair.
    assert _r_wad(above, ext, 0, True) > 0
    assert _r_wad(above, ext, 0, False) < 0
    # Pool below external: mirrored.
    assert _r_wad(below, ext, 0, True) < 0
    assert _r_wad(below, ext, 0, False) > 0


@pytest.mark.parametrize("zero_for_one", [True, False])
def test_a_fee_always_makes_r_worse(zero_for_one):
    """WHAT WOULD BE WRONG: "raising the fee now costs retained retail revenue"
    is the second blade of the scissors the whole third experiment is built on
    (spec SS1). If the fee did not enter `r` monotonically for BOTH directions,
    the interior optimum the paper reports would be an artifact.
    """
    ext = Q96
    pool = int((1.01**0.5) * Q96)
    previous = None
    for fee in (0, 100, 500, 3000, 6000, 10000):
        value = _r_wad(pool, ext, fee, zero_for_one)
        if previous is not None:
            assert value < previous, f"fee {fee} did not lower r"
        previous = value


# --------------------------------------------------------------------------
# 4. uu.py -- calibration and the trace generator
# --------------------------------------------------------------------------


def test_kappa_makes_mean_daily_potential_volume_exactly_one_basket():
    """WHAT WOULD BE WRONG: kappa fixes the retail scale (spec SS3, turnover
    1x/day). If it normalised by something else -- a per-candle mean, a sum
    over the profile, the median day -- every absolute USDT figure in the third
    experiment would be off by that factor and the arbitrage share of volume
    (the axis the kappa pre-registration reports against) would be wrong.

    Reference: build a profile of exactly three days with a known mean, then
    require sum(kappa*v) over the profile == 3 baskets.
    """
    minutes = 3 * 1440
    volumes = np.arange(1, minutes + 1, dtype=float)
    profile = pd.DataFrame(
        {"open_time": np.arange(minutes) * 60_000, "v_usdt": volumes}
    )
    k = kappa(profile, BASKET_USDT)
    assert float((profile["v_usdt"] * k).sum()) == pytest.approx(
        3 * BASKET_USDT, rel=1e-12
    )


def test_kappa_reproduces_the_manifest_constant_from_the_cached_year():
    """WHAT WOULD BE WRONG: `uu_kappa` is a manifest field (D/S of the replay
    identity). If the shipped constant could not be re-derived from the data on
    disk, the run would not be reproducible in the sense Eq. (9) requires.

    Reference: geometric mean of the two legs' quote volumes over 2024,
    recomputed here from the cached parquets, not from `uu.uu_profile`.
    """
    files0 = sorted(glob.glob(str(ROOT / "data" / "ETHUSDT-1m-v2-*.parquet")))
    files1 = sorted(glob.glob(str(ROOT / "data" / "SHIBUSDT-1m-v2-*.parquet")))
    if not files0 or not files1:
        pytest.skip("2024 volume cache not present")

    def load(files):
        frame = pd.concat([pd.read_parquet(f) for f in files])
        frame = frame.drop_duplicates("open_time").sort_values("open_time")
        mask = (frame.open_time >= 1_704_067_200_000) & (
            frame.open_time < 1_735_689_600_000
        )
        return frame[mask].reset_index(drop=True)

    merged = load(files0).merge(load(files1), on="open_time", suffixes=("_0", "_1"))
    v0 = merged.quote_volume_0.astype(float).to_numpy()
    v1 = merged.quote_volume_1.astype(float).to_numpy()
    geo = np.exp(
        (
            np.log(np.clip(v0, v0[v0 > 0].min(), None))
            + np.log(np.clip(v1, v1[v1 > 0].min(), None))
        )
        / 2
    )
    reference = BASKET_USDT / (geo.mean() * 1440)

    manifests = sorted(
        glob.glob(str(ROOT / "results-uu" / "matrix" / "*ETH-SHIB*.manifest.json"))
    )
    if not manifests:
        pytest.skip("results-uu matrix not present")
    shipped = json.loads(Path(manifests[0]).read_text())["S"]["uu_kappa"]
    assert reference == pytest.approx(shipped, rel=1e-12)


def test_uu_profile_one_leg_is_the_identity_and_two_legs_the_geometric_mean():
    """WHAT WOULD BE WRONG: spec SS3 defines V_profile as the geometric mean of
    the available legs -- two for ETH/SHIB and ETH/USDC, the single real leg
    for USDC/USDT. An arithmetic mean would over-weight the larger leg and
    change kappa, hence the retail scale, per pair and only for some pairs.
    """
    a = pd.DataFrame({"open_time": [0, 60_000], "quote_volume": [4.0, 100.0]})
    b = pd.DataFrame({"open_time": [0, 60_000], "quote_volume": [9.0, 1.0]})

    assert list(uu_profile(a)["v_usdt"]) == [4.0, 100.0]
    got = list(uu_profile(a, b)["v_usdt"])
    assert got[0] == pytest.approx(6.0, rel=1e-12)  # sqrt(4*9)
    assert got[1] == pytest.approx(10.0, rel=1e-12)  # sqrt(100*1)


def test_share_mode_splits_the_potential_volume_evenly_between_directions():
    """WHAT WOULD BE WRONG: spec SS2.3 thins each direction from `v0/2`. If the
    generator wrote `v0` per direction the pool would see twice the modelled
    retail demand and every fee-income figure would double.
    """
    profile = pd.DataFrame({"open_time": [0], "v_usdt": [1000.0]})
    path = ROOT / ".pytest-uu-share.csv"
    try:
        export_uu_trace(profile, kappa=1.0, path=path, mode="share")
        _, ab, u_ab, ba, u_ba = path.read_text().strip().split(",")
        assert int(ab) == int(ba) == 500 * WAD
        assert int(u_ab) == int(u_ba) == 0
    finally:
        path.unlink(missing_ok=True)


def test_discrete_mode_sizes_are_mean_preserving():
    """WHAT WOULD BE WRONG: spec SS2.4 requires the discrete mode's lognormal
    sizes to sum in expectation to v0 -- `E[exp(sigma*Z - sigma^2/2)] == 1`.
    If the -sigma^2/2 correction were dropped, the robustness appendix would
    run at exp(sigma^2/2) times the calibrated retail scale (1.65x at
    sigma = 1) and any sign change it reported would be a scale change.

    Reference: the analytic expectation, checked against the generator's own
    seeded draws over 20,000 candles.
    """
    n = 20_000
    profile = pd.DataFrame({"open_time": np.arange(n) * 60_000, "v_usdt": [1000.0] * n})
    path = ROOT / ".pytest-uu-discrete.csv"
    try:
        export_uu_trace(
            profile, kappa=1.0, path=path, mode="discrete", seed=7, sigma=1.0
        )
        rows = [line.split(",") for line in path.read_text().strip().splitlines()]
        sizes = np.array([int(r[1]) for r in rows], dtype=float) / WAD
    finally:
        path.unlink(missing_ok=True)

    # Mean of 20k lognormal(-0.5, 1) draws x 500; se of the mean is
    # 500*sqrt(e-1)/sqrt(n) ~= 4.6, so 5 se is a safe, non-flaky band.
    assert abs(sizes.mean() - 500.0) < 25.0

    uniforms = np.array([int(r[2]) for r in rows], dtype=float) / WAD
    assert 0.0 <= uniforms.min() and uniforms.max() < 1.0
    assert abs(uniforms.mean() - 0.5) < 0.02


def test_discrete_mode_draws_one_potential_trade_per_direction_not_k_in_1_to_3():
    """Documents a SPEC DEVIATION rather than an arithmetic error. Spec SS2.4
    says discrete mode "draws k in {1..3} potential UU trades per candle"; the
    generator draws exactly one per direction. Harmless today (discrete mode is
    not in the main matrix), but the robustness appendix the mode exists for
    would then not be testing what SS2.4 describes -- one lognormal draw has a
    different variance from a sum of k of them, and the appendix's whole claim
    is about the variance of the thinning approximation.
    """
    profile = pd.DataFrame({"open_time": [0, 60_000], "v_usdt": [1000.0, 1000.0]})
    path = ROOT / ".pytest-uu-k.csv"
    try:
        export_uu_trace(profile, kappa=1.0, path=path, mode="discrete", seed=1)
        rows = [line.split(",") for line in path.read_text().strip().splitlines()]
    finally:
        path.unlink(missing_ok=True)
    # Five fields only: one size and one uniform per direction. No k.
    assert all(len(r) == 5 for r in rows)


# --------------------------------------------------------------------------
# 5. pairing and the Wilcoxon / BH machinery
# --------------------------------------------------------------------------


def test_pairing_joins_on_every_axis_but_policy_and_does_not_fan_out():
    """WHAT WOULD BE WRONG: if the join fanned out, one window would enter the
    signed-rank test several times and every p-value in the pre-registered
    family would be computed on inflated evidence.
    """
    rows = []
    for policy in ("MyHook@3000", "BAHook"):
        for window_start in (1, 2):
            for gas in (5, 20):
                for mode in ("persistent", "fresh"):
                    rows.append(
                        {
                            "policy": policy,
                            "pair": "ETH/SHIB",
                            "window_start_ms": window_start,
                            "gas_price_wei": gas,
                            "address_mode": mode,
                            "regime": "low",
                            "net_result": 1.0 if policy == "BAHook" else 0.25,
                            "net_result_tt": 2.0,
                            "trade_count": 3,
                        }
                    )
    frame = pd.DataFrame(rows)
    paired = paired_against_baseline(frame)

    assert len(paired) == 8
    assert len(paired.drop_duplicates(AXES + ["policy"])) == 8
    # pytest.approx does not compare elementwise against a Series -- it
    # silently yields a scalar (PROGRESS, Plan 3 notes). Compare in numpy.
    assert np.allclose(paired["net_result_delta"].to_numpy(), 0.75)


def test_benjamini_hochberg_is_a_correct_step_up_procedure():
    """WHAT WOULD BE WRONG: BH decides which of ~300 declared comparisons the
    paper may call significant. A step-DOWN implementation (stopping at the
    first failure) would silently drop true discoveries; forgetting to accept
    everything below the largest passing rank would do the same.

    Reference: an independent vectorised implementation, on random families and
    on the adversarial case where a large p-value passes and small ones do not
    pass their own thresholds.
    """

    def reference(pvalues, q=0.05):
        m = len(pvalues)
        order = np.argsort(np.asarray(pvalues, dtype=float), kind="stable")
        ranked = np.asarray(pvalues, dtype=float)[order]
        passing = ranked <= (np.arange(1, m + 1) / m) * q
        k = int(np.max(np.nonzero(passing)[0]) + 1) if passing.any() else 0
        out = np.zeros(m, dtype=bool)
        out[order[:k]] = True
        return out.tolist()

    rng = np.random.default_rng(20260810)
    for _ in range(200):
        m = int(rng.integers(1, 40))
        pvalues = np.round(rng.beta(0.3, 3.0, m), 6).tolist()
        assert benjamini_hochberg(pvalues) == reference(pvalues)

    # Ten p-values at 0.04: jointly strong evidence, all ten accepted.
    assert benjamini_hochberg([0.04] * 10) == [True] * 10
    # Step-up, not step-down: 0.001 fails its own 0.0125 threshold only if the
    # family is large; here rank 4 passes and drags ranks 1-3 in with it.
    assert benjamini_hochberg([0.049, 0.001, 0.002, 0.003]) == [
        True,
        True,
        True,
        True,
    ]


def test_wilcoxon_paired_reports_effective_n_after_ties():
    """WHAT WOULD BE WRONG: the signed-rank test discards exact ties. Quoting
    `n` as the sample size overstates the evidence -- a comparison reported as
    n = 8 once ran on 0.23 usable differences.
    """
    result = wilcoxon_paired([0.0, 0.0, 0.0, 1.0, 2.0])
    assert result["n"] == 5
    assert result["n_effective"] == 2


def test_wilcoxon_paired_drops_missing_differences():
    """WHAT WOULD BE WRONG (LATENT, not yet reached by the shipped matrix):
    `arb_profit_realized` is in `aggregate.PAIRED_METRICS` and
    `metrics.compute` can return None for it (the backfilled-feed sentinel).
    A None becomes NaN, the delta becomes NaN, and `wilcoxon_paired` neither
    drops it nor raises: `values != 0` is True for NaN, so the NaN reaches
    scipy and the p-value comes back NaN.

    That NaN then enters `stats.analyse`'s family. Two consequences: it inflates
    `m`, weakening the BH threshold for every other comparison in the paper;
    and `benjamini_hochberg` sorts with `sorted()`, whose ordering is undefined
    when NaN is present, so the step-up can be computed against a corrupted
    ranking. A missing observation must be dropped, exactly as a tie is.
    """
    clean = wilcoxon_paired([1.0, 2.0, 3.0, -1.0, 4.0, 5.0])
    with_nan = wilcoxon_paired([1.0, 2.0, 3.0, -1.0, 4.0, 5.0, float("nan")])

    assert not np.isnan(with_nan["p"]), "a NaN difference silently poisons the p-value"
    assert with_nan["n_effective"] == clean["n_effective"]


def test_benjamini_hochberg_ordering_survives_a_nan_pvalue():
    """WHAT WOULD BE WRONG (LATENT): `benjamini_hochberg` uses `sorted()`, and
    every comparison against NaN is False. A single NaN p-value can therefore
    leave the family unsorted, and the step-up threshold `rank/m*q` is then
    applied to the wrong p-values -- flipping significance verdicts for
    comparisons that have nothing to do with the missing one.
    """
    pvalues = [0.5, float("nan"), 0.001, 0.002]
    flags = benjamini_hochberg(pvalues)
    # Whatever happens to the NaN, the two genuinely small p-values must not
    # lose their significance because of it.
    reference = benjamini_hochberg([0.5, 0.001, 0.002])
    assert [flags[0], flags[2], flags[3]] == reference


# --------------------------------------------------------------------------
# 6. differential against the shipped matrix (skipped when it is not on disk)
# --------------------------------------------------------------------------

_TRACE_GLOB = "results-uu/*-ETHUSDT-SHIBUSDT-1704067200000-20000000000-persistent.jsonl"


def _sample_traces(limit: int = 3) -> list[Path]:
    return [Path(p) for p in sorted(glob.glob(str(ROOT / _TRACE_GLOB)))[:limit]]


@pytest.mark.xfail(
    reason=(
        "2026-08-10: `r` moved to the source model's normalised form "
        "(V_out-V_in)/(V_out+V_in) and lambda to 461.404973; it validates traces recorded under the superseded marginal r. "
        "Re-point it once the matrix has been re-run under the new r."
    ),
    strict=False,
)
def test_recorded_r_and_p_match_an_independent_mpmath_reference():
    """WHAT WOULD BE WRONG: forge cannot be run here, so this is the end-to-end
    check that the DEPLOYED `UUMath` produced the numbers in the matrix. `r`
    and `P` are recomputed from the recorded pre-swap sqrt price, the two
    external prices and the applied fee, in exact integers plus mpmath, and
    differenced against the values the harness logged. If they disagreed, the
    participation model described in the paper would not be the one that ran.
    """
    traces = _sample_traces()
    if not traces:
        pytest.skip("results-uu traces not present")

    lam = mpf(UU_LAMBDA_WAD) / mpf(WAD)
    checked = 0
    for path in traces:
        for line in path.read_text().splitlines():
            record = json.loads(line)
            if record.get("kind") != "swap" or record.get("trader") != "uu":
                continue
            ext_x96 = int(record["extPrice0"]) * Q96 // int(record["extPrice1"])
            want_r = _r_wad(
                int(record["sqrtPriceBeforeX96"]),
                ext_x96,
                int(record["feePips"]),
                bool(record["zeroForOne"]),
            )
            assert want_r == int(record["rWad"]), f"r mismatch in {path.name}"

            r = mpf(want_r) / mpf(WAD)
            want_p = mpf(1) if r >= 0 else mp_exp(-lam * abs(r))
            got_p = mpf(int(record["pWad"])) / mpf(WAD)
            assert abs(got_p - want_p) <= mpf("1e-9") * want_p
            checked += 1

    assert checked > 100, f"only {checked} UU swaps checked"


def test_recorded_fee_log_agrees_with_the_pools_own_fee_accounting():
    """WHAT WOULD BE WRONG: `uu_fee_share` is built from the logged `feePips`,
    while `fee_income` comes from the pool's `feeGrowthInside`. The 2026-08-10
    audit found MEVChargeHook's log at 0.426 of the pool's number because the
    fee was quoted at zero size. Every policy must now sit at the same ratio --
    a uniform offset is the end-of-window vs trade-time valuation convention; a
    policy-specific one is a defect in the log.
    """
    traces = _sample_traces(limit=8)
    if not traces:
        pytest.skip("results-uu traces not present")

    ratios = {}
    for path in traces:
        records = [json.loads(line) for line in path.read_text().splitlines()]
        window = next((r for r in records if r.get("kind") == "window"), None)
        swaps = [r for r in records if r.get("kind") == "swap"]
        if window is None or not swaps:
            continue
        liquidity = int(window["liquidity"])
        fee0 = (
            (
                int(window["feeGrowthInside0X128"])
                - int(window["feeGrowthInside0X128Initial"])
            )
            * liquidity
            / 2**128
        )
        fee1 = (
            (
                int(window["feeGrowthInside1X128"])
                - int(window["feeGrowthInside1X128Initial"])
            )
            * liquidity
            / 2**128
        )
        pool = (
            fee0 / WAD * int(window["extPrice0Final"]) / PRICE_SCALE
            + fee1 / WAD * int(window["extPrice1Final"]) / PRICE_SCALE
        )
        logged = sum(
            int(r["amountIn"])
            * int(r["feePips"])
            / ONE_PIPS
            / WAD
            * (int(r["extPrice0"]) if r["zeroForOne"] else int(r["extPrice1"]))
            / PRICE_SCALE
            for r in swaps
        )
        if pool > 0:
            ratios[path.stem.split("-")[0]] = logged / pool

    if len(ratios) < 2:
        pytest.skip("not enough policies on disk")
    spread = max(ratios.values()) - min(ratios.values())
    assert spread < 0.02, f"policy-specific fee-log discrepancy: {ratios}"
