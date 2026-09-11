"""Tests for reading swap traces back off disk."""

import json

from experiments.events import applied_fees, read_events


def test_applied_fees_excludes_the_sensitivity_sweep(tmp_path):
    """The sensitivity runs must never enter a pre-registered figure.

    Their filenames differ only by a trailing `-cs<share>` field. A prefix match
    on the address mode let all 504 of them through, pooling 62k swaps into
    PegCapture's row and widening its reported fee range by a factor of two.
    """
    swap = {
        "kind": "swap",
        "feePips": 3000,
        "candle": 0,
        "blockNumber": 1,
        "timestamp": 0,
        "zeroForOne": True,
        "amountIn": "1",
        "amountOut": "1",
        "feeAB": 3000,
        "feeBA": 3000,
        "delta0": "1",
        "delta1": "-1",
        "expectedProfit": "0",
        "gas": 1,
        "sender": "0x0",
        "extPrice0": "1",
        "extPrice1": "1",
        "sqrtPriceBeforeX96": "1",
        "sqrtPriceAfterX96": "1",
    }
    line = json.dumps(swap)
    stem = "PegCapture-0-ETHUSDT-SHIBUSDT-1704067200000-20000000000-persistent"
    (tmp_path / f"{stem}.jsonl").write_text(line + "\n")
    (tmp_path / f"{stem}-cs750000.jsonl").write_text(line + "\n")
    (tmp_path / f"{stem[:-10]}fresh.jsonl").write_text(line + "\n")

    fees = applied_fees(tmp_path)
    assert len(fees) == 1, "only the pre-registered persistent run counts"
    assert fees.iloc[0]["fee_bps"] == 30.0
    assert fees.iloc[0]["pair"] == "ETH/SHIB"


def test_the_stable_pair_is_recognised_from_its_trace_name():
    """Its second leg is a synthetic constant feed, not a market symbol.

    The mapping was keyed on "USDTUSDT", which no trace filename ever contains,
    so every USDC/USDT trace was silently skipped and the pair was reported as
    having produced no swaps at all.
    """
    from experiments.matrix import CONSTANT_ONE, PAIRS

    stable = next(p for p in PAIRS if p.name == "USDC/USDT")
    assert stable.symbol1 == CONSTANT_ONE
    from experiments.events import _PAIR_BY_SYMBOLS

    assert _PAIR_BY_SYMBOLS.get((stable.symbol0, stable.symbol1)) == "USDC/USDT"
    for pair in PAIRS:
        assert (pair.symbol0, pair.symbol1) in _PAIR_BY_SYMBOLS, pair.name


def _swap(**overrides) -> dict:
    record = {
        "kind": "swap",
        "feePips": 3000,
        "candle": 0,
        "blockNumber": 1,
        "timestamp": 0,
        "zeroForOne": True,
        "amountIn": "1",
        "amountOut": "1",
        "feeAB": 3000,
        "feeBA": 3000,
        "delta0": "1",
        "delta1": "-1",
        "expectedProfit": "0",
        "gas": 1,
        "sender": "0x0",
        "extPrice0": "1",
        "extPrice1": "1",
        "sqrtPriceBeforeX96": "1",
        "sqrtPriceAfterX96": "1",
    }
    record.update(overrides)
    return record


def test_old_traces_without_trader_or_extPriceGas_parse_with_defaults(tmp_path):
    """Pre-UU traces never wrote `trader`/`rWad`/`pWad`/`extPriceGas`.

    A missing `trader` must default to "arb" (every historical swap was an
    arbitrageur trade) and a missing `extPriceGas` to 0, or every pre-UU trace
    on disk stops parsing.
    """
    path = tmp_path / "old.jsonl"
    path.write_text(json.dumps(_swap()) + "\n")

    frame, _ = read_events(path)
    assert frame.iloc[0]["trader"] == "arb"
    assert int(frame.iloc[0]["extPriceGas"]) == 0
    assert int(frame.iloc[0]["rWad"]) == 0
    assert int(frame.iloc[0]["pWad"]) == 0


def test_a_uu_line_round_trips(tmp_path):
    path = tmp_path / "uu.jsonl"
    path.write_text(
        json.dumps(
            _swap(
                trader="uu",
                rWad=-3_000_000_000_000_000,
                pWad=500_000_000_000_000_000,
                extPriceGas="300000000000",
            )
        )
        + "\n"
    )

    frame, _ = read_events(path)
    row = frame.iloc[0]
    assert row["trader"] == "uu"
    assert int(row["rWad"]) == -3_000_000_000_000_000
    assert int(row["pWad"]) == 500_000_000_000_000_000
    assert int(row["extPriceGas"]) == 300000000000
