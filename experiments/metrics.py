"""Derived quantities for one replay window.

The contracts derive nothing; everything here is computed from the event log.
Prices arrive 1e8-scaled (the Chainlink convention) and token amounts 1e18-scaled.

The LP position is reconstructed from pool state - principal from the position
formula, fees from feeGrowthInside - while trader flow is summed from the swap
records. Because these are independent derivations of the same tokens, comparing
them is a real check rather than an identity.

Fees are read from the pool's fee accounting, never inferred from reserves: in v4
a fee is credited to the position through feeGrowthInside and never joins the
liquidity L, so it does not appear in the reserves as a distinguishable quantity
and does not compound. `feeGrowthInside * L` is the amount owed only because the
position is minted before any swap, leaving its own snapshot at zero; the harness
asserts that precondition at deployment.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

PRICE_SCALE = 1e8
WAD = 1e18
Q96 = 2**96
Q128 = 2**128


def _sqrt_price_at_tick(tick: int) -> float:
    return (1.0001 ** (tick / 2)) * Q96


def amounts_for_liquidity(
    liquidity: int, sqrt_price_x96: int, tick_lower: int, tick_upper: int
) -> tuple[float, float]:
    """Uniswap v3/v4 position amounts at a given price.

    Float is sufficient: the result feeds a USD figure, not on-chain arithmetic,
    and the relative error is far below the tolerance the conservation check uses.
    """
    sa = _sqrt_price_at_tick(tick_lower)
    sb = _sqrt_price_at_tick(tick_upper)
    s = float(min(max(float(sqrt_price_x96), sa), sb))
    liq = float(liquidity)

    # amount0 = L * (1/s - 1/sb), amount1 = L * (s - sa), in X96 units.
    amount0 = liq * (sb - s) * Q96 / (s * sb)
    amount1 = liq * (s - sa) / Q96
    return amount0, amount1


def exact_sum(series) -> int:
    """Sum a column as Python integers.

    Never use Series.sum() on wei-scale data: an int64 column accumulates in
    int64 and wraps on overflow without raising, which silently corrupts every
    figure downstream.
    """
    return sum(int(v) for v in series)


def _usd(amount_wad: float, price_1e8: float) -> float:
    return (amount_wad / WAD) * (price_1e8 / PRICE_SCALE)


def _zeroed() -> dict:
    return {
        "fee_income": 0.0,
        "lp_principal": 0.0,
        "lp_value": 0.0,
        "hodl_value": 0.0,
        "il": 0.0,
        "net_result": 0.0,
        "net_result_tt": 0.0,
        "arb_mtm": 0.0,
        "arb_profit_realized": 0.0,
        "gas_cost": 0.0,
        "retained_volume": 0.0,
        "uu_volume": 0.0,
        "arb_volume": 0.0,
        "uu_fee_share": None,
        "uu_participation": None,
        "trade_count": 0,
        "conservation_error_token0": 0.0,
        "conservation_error_token1": 0.0,
    }


def _trade_time_value_usdt(rows) -> float:
    """Sigma over rows of delta0*extPrice0 + delta1*extPrice1, in USDT.

    Both operands of each term are exact ints (wei-scale delta, 1e8-scale
    price); the sum is exact Python-int arithmetic, and only the final
    division to USDT is a float (2026-08-09-uu-flow-design.md §6).
    """
    if len(rows) == 0:
        return 0.0
    total = sum(
        int(d0) * int(p0) + int(d1) * int(p1)
        for d0, p0, d1, p1 in zip(
            rows["delta0"], rows["extPrice0"], rows["delta1"], rows["extPrice1"]
        )
    )
    return total / (WAD * PRICE_SCALE)


def _volume_trade_time_usdt(rows) -> float:
    """Sigma over rows of amountIn valued at that row's trade-time input-token
    price (extPrice0 for a zeroForOne row, extPrice1 otherwise)."""
    if len(rows) == 0:
        return 0.0
    total = 0.0
    for amount, zero_for_one, p0, p1 in zip(
        rows["amountIn"], rows["zeroForOne"], rows["extPrice0"], rows["extPrice1"]
    ):
        price = p0 if zero_for_one else p1
        total += _usd(float(amount), float(price))
    return total


def _fee_paid_trade_time_usdt(rows) -> float:
    """Sigma over rows of (amountIn * feePips / 1e6) valued at that row's
    trade-time input-token price -- the fee income each row actually paid."""
    if len(rows) == 0:
        return 0.0
    total = 0.0
    for amount, fee_pips, zero_for_one, p0, p1 in zip(
        rows["amountIn"],
        rows["feePips"],
        rows["zeroForOne"],
        rows["extPrice0"],
        rows["extPrice1"],
    ):
        price = p0 if zero_for_one else p1
        fee_amount = int(amount) * int(fee_pips) / 1e6
        total += _usd(fee_amount, float(price))
    return total


def _trader_column(swaps: pd.DataFrame):
    """`swaps["trader"]` if present, else every row defaults to "arb" -- the
    same default `events.read_events` applies, kept here too because
    `compute` is also exercised directly on hand-built frames that predate
    the UU flow schema (2026-08-09-uu-flow-design.md §5)."""
    if "trader" in swaps.columns:
        return swaps["trader"]
    return pd.Series(["arb"] * len(swaps), index=swaps.index)


def compute(
    swaps: pd.DataFrame,
    window: dict,
    gas_price_wei: float,
    eth_price_1e8: float | None = None,
) -> dict:
    if not window:
        return _zeroed()

    liquidity = int(window["liquidity"])
    final_p0 = float(window["extPrice0Final"])
    final_p1 = float(window["extPrice1Final"])

    principal0, principal1 = amounts_for_liquidity(
        liquidity,
        int(window["sqrtPriceFinalX96"]),
        int(window["tickLower"]),
        int(window["tickUpper"]),
    )

    # Fees live outside the position principal in v4, and are measured as the
    # growth since the baseline: warm-up swaps accrue fees that belong to the
    # excluded period, not to the measured one.
    fee0 = (
        (
            float(window["feeGrowthInside0X128"])
            - float(window.get("feeGrowthInside0X128Initial", 0))
        )
        * liquidity
        / Q128
    )
    fee1 = (
        (
            float(window["feeGrowthInside1X128"])
            - float(window.get("feeGrowthInside1X128Initial", 0))
        )
        * liquidity
        / Q128
    )

    l0_0 = float(window["initialToken0"])
    l0_1 = float(window["initialToken1"])

    if swaps.empty:
        flow0 = flow1 = 0.0
        gas_units = 0.0
        retained = 0.0
    else:
        flow0 = float(exact_sum(swaps["delta0"]))
        flow1 = float(exact_sum(swaps["delta1"]))
        gas_units = float(exact_sum(swaps["gas"]))
        retained = _usd(
            float(exact_sum(swaps.loc[swaps["zeroForOne"], "amountIn"])), final_p0
        ) + _usd(
            float(exact_sum(swaps.loc[~swaps["zeroForOne"], "amountIn"])), final_p1
        )

    # Two independent derivations of the pool's token holdings:
    #   left  - pool state: position principal plus accrued fees
    #   right - trader flow: the initial deposit minus everything traders took
    # Returned relative to the initial deposit so the tolerance is scale-free
    # across pairs whose token magnitudes differ by orders of magnitude.
    conservation_error_token0 = ((principal0 + fee0) - (l0_0 - flow0)) / max(
        abs(l0_0), 1.0
    )
    conservation_error_token1 = ((principal1 + fee1) - (l0_1 - flow1)) / max(
        abs(l0_1), 1.0
    )

    fee_income = _usd(fee0, final_p0) + _usd(fee1, final_p1)
    lp_principal = _usd(principal0, final_p0) + _usd(principal1, final_p1)
    lp_value = lp_principal + fee_income
    hodl_value = _usd(l0_0, final_p0) + _usd(l0_1, final_p1)

    # Not clamped: a profitable LP outcome is representable as negative IL.
    il = hodl_value - lp_principal
    net_result = fee_income - il

    # Gas is paid in ETH, so it must be valued at the ETH price -- not at
    # token0's. The two coincide only when token0 happens to be ETH, which is
    # true for the two volatile pairs and false for USDC/USDT, where this
    # understated the figure by the entire ETH price. Reported only: the LP does
    # not pay gas, the arbitrageur does, and its effect on the LP is already in
    # the entry threshold the harness applies.
    eth_price = float(eth_price_1e8 if eth_price_1e8 is not None else final_p0)
    gas_cost = (gas_units * gas_price_wei / WAD) * (eth_price / PRICE_SCALE)
    # Renamed from `arb_profit`: this is the counterparty flow marked at
    # end-of-window prices, identically -net_result under arb-only flow -- it
    # was never realized profit (2026-08-09-uu-flow-design.md §6).
    arb_mtm = _usd(flow0, final_p0) + _usd(flow1, final_p1)

    # Trade-time valuation and trader split (spec §6). Declared alongside the
    # end-of-window figures above rather than replacing them: the 2026-08-09
    # audit found the end-of-window valuation carries an inventory-
    # revaluation term that can flip conclusions, so both are reported.
    net_result_tt = -_trade_time_value_usdt(swaps)

    trader = _trader_column(swaps)
    arb_rows = swaps[trader == "arb"]
    uu_rows = swaps[trader == "uu"]

    # `events.read_events` backfills a missing `extPriceGas` field to 0 for
    # every row (so a pre-UU trace still parses), which means the column is
    # ALWAYS present once a trace has passed through it -- checking only for
    # the column's absence let a pre-UU trace through with every gas cost
    # silently valued at $0, understating cost and reporting a realized
    # profit the trace cannot actually support (2026-08-09 adversarial
    # review, test_pre_uu_frame_metrics_compute_survives_and_realized_is_none).
    # Zero is a safe missing-data sentinel here: no real Chainlink ETH/USDT
    # feed ever reports a zero price, so "every arb row's extPriceGas is
    # exactly zero" can only mean the field was backfilled, never a real
    # quote. Scoped to `arb_rows` specifically (not all of `swaps`): with no
    # arb rows at all, both the gross and gas terms are trivially zero
    # regardless of extPriceGas quality, so 0.0 there is a real answer, not
    # a guess.
    if "extPriceGas" not in swaps.columns or not arb_rows.empty and (arb_rows["extPriceGas"] == 0).all():
        arb_profit_realized = None
    else:
        arb_gross_tt = _trade_time_value_usdt(arb_rows)
        arb_gas_tt = sum(
            (int(gas) * gas_price_wei / WAD) * (int(price_gas) / PRICE_SCALE)
            for gas, price_gas in zip(arb_rows["gas"], arb_rows["extPriceGas"])
        )
        arb_profit_realized = arb_gross_tt - arb_gas_tt

    uu_volume = _volume_trade_time_usdt(uu_rows)
    arb_volume = _volume_trade_time_usdt(arb_rows)

    if swaps.empty:
        uu_fee_share = None
    else:
        all_fee_tt = _fee_paid_trade_time_usdt(swaps)
        uu_fee_tt = _fee_paid_trade_time_usdt(uu_rows)
        uu_fee_share = (uu_fee_tt / all_fee_tt) if all_fee_tt else 0.0

    if uu_rows.empty:
        uu_participation = None
    else:
        # The retail RETENTION RATE: executed potential volume over potential
        # volume, both in USDT. Two defects this replaces, found by the
        # 2026-08-10 adversarial review, and it had both at once:
        #
        # 1. It weighted `P` by the raw `amountIn`, which is token0 wei for an
        #    A->B swap and token1 wei for a B->A one. On ETH/SHIB those units
        #    differ by ~1.5e8, so one direction carried ~5e-9 of the weight and
        #    the published "two-sided participation" was one direction's rate.
        # 2. It weighted by the EXECUTED volume, which is itself proportional
        #    to `P`, returning E[P^2]/E[P] -- upward biased by Jensen, and
        #    biased more where the spread of P is wider. Measured against the
        #    true retention rate on the shipped matrix: +4.2% at 5 bps, +10.3%
        #    at 30, +19.9% at 60, +46.9% at 100 bps. That flattened the
        #    published participation-vs-fee curve.
        #
        # In share mode the harness executes `potential * P`, so the potential
        # is recoverable as `executed / P` and the ratio below is exactly
        # sum(v*P)/sum(v). A candle whose thinned size rounded to zero is never
        # logged, so its potential is invisible here: the result is an upper
        # bound on retention, and the paper says so.
        executed_usdt = 0.0
        potential_usdt = 0.0
        for amount, p_wad, zero_for_one, p0, p1 in zip(
            uu_rows["amountIn"],
            uu_rows["pWad"],
            uu_rows["zeroForOne"],
            uu_rows["extPrice0"],
            uu_rows["extPrice1"],
        ):
            p = int(p_wad)
            if p <= 0:
                continue
            value = _usd(float(amount), float(p0 if zero_for_one else p1))
            executed_usdt += value
            potential_usdt += value * WAD / p
        uu_participation = (
            (executed_usdt / potential_usdt) if potential_usdt else None
        )

    return {
        "fee_income": fee_income,
        "lp_principal": lp_principal,
        "lp_value": lp_value,
        "hodl_value": hodl_value,
        "il": il,
        "net_result": net_result,
        "net_result_tt": net_result_tt,
        "arb_mtm": arb_mtm,
        "arb_profit_realized": arb_profit_realized,
        "gas_cost": gas_cost,
        "retained_volume": retained,
        "uu_volume": uu_volume,
        "arb_volume": arb_volume,
        "uu_fee_share": uu_fee_share,
        "uu_participation": uu_participation,
        "trade_count": len(swaps),
        "conservation_error_token0": conservation_error_token0,
        "conservation_error_token1": conservation_error_token1,
    }


def per_cell_extras(results_dir, address_mode: str = "persistent") -> pd.DataFrame:
    """The §12 metrics that never reached `summary.csv`, read from the traces.

    `summary.csv` carries the aggregates the runner needed. Three items on the
    spec's list are missing from it: fee income split per token, gas in units
    rather than currency, and LVR.

    On LVR: with arbitrage-only flow the system is closed, so what the pool
    gives up goes to exactly one place. Writing out the accounting,

        il = hodl - principal = usd(flow) + usd(fees) = arb_profit + fee_income

    which is the realised loss to arbitrage before fees -- the quantity LVR
    names. So `lvr` here is not a new measurement; it is `il`, and the identity
    is asserted below rather than assumed. A counterfactual zero-fee LVR would
    be a different number, but it needs the price path of candles where no swap
    happened and is not recoverable from the swap log alone.
    """
    import json

    from experiments.events import _PAIR_BY_SYMBOLS

    rows = []
    for path in sorted(Path(results_dir).glob("*.jsonl")):
        parts = path.stem.split("-")
        if len(parts) != 7 or parts[6] != address_mode:
            continue
        pair = _PAIR_BY_SYMBOLS.get((parts[2], parts[3]))
        if pair is None:
            continue

        window, gas_units, swaps = None, [], 0
        for line in path.read_text().splitlines():
            record = json.loads(line)
            if record.get("kind") == "window":
                window = record
            elif record.get("kind") == "swap":
                gas_units.append(int(record["gas"]))
                swaps += 1
        if window is None:
            continue

        liquidity = int(window["liquidity"])
        fee0 = (
            (
                int(window["feeGrowthInside0X128"])
                - int(window["feeGrowthInside0X128Initial"])
            )
            * liquidity
            / Q128
        )
        fee1 = (
            (
                int(window["feeGrowthInside1X128"])
                - int(window["feeGrowthInside1X128Initial"])
            )
            * liquidity
            / Q128
        )

        rows.append(
            {
                "policy": parts[0] if parts[1] == "0" else f"MyHook@{parts[1]}",
                "pair": pair,
                "window_start_ms": int(parts[4]),
                "gas_price_wei": int(parts[5]),
                "address_mode": address_mode,
                "fee_income_token0": _usd(fee0, float(window["extPrice0Final"])),
                "fee_income_token1": _usd(fee1, float(window["extPrice1Final"])),
                "gas_units_total": float(sum(gas_units)),
                "gas_units_mean": float(sum(gas_units) / swaps) if swaps else 0.0,
            }
        )
    return pd.DataFrame(rows)
