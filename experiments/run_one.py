"""Drives one replay: fetch, align, export, run Forge, parse, compute."""

from __future__ import annotations

import os
import subprocess
from functools import cache
from pathlib import Path

import pandas as pd

from experiments.binance import fetch_klines
from experiments.events import read_events
from experiments.export_trace import PRICE_SCALE, align_traces, export_trace
from experiments.metrics import compute
from experiments.uu import UU_LAMBDA_WAD, export_uu_trace, uu_profile
from experiments.uu import kappa as _uu_kappa

ROOT = Path(__file__).resolve().parent.parent
FORGE = Path.home() / ".foundry" / "bin" / "forge"
GAS_SYMBOL = "ETHUSDT"  # values gas in USDT for every pair

# The stable pair prices USDC against USDT and its second leg has no market
# series of its own, so it is a synthetic feed pinned at 1.0. Formally this is
# not a market observation; spec §16 carries the caveat.
CONSTANT_ONE = "CONST1"

# kappa's calibration window (2026-08-09-uu-flow-design.md §3): 2024 UTC. A
# constant per pair, not a per-window quantity -- calibrating it on the
# window's own candles is exactly the mistake the spec calls out.
UU_CALIBRATION_YEAR_START_MS = 1_704_067_200_000
UU_CALIBRATION_YEAR_END_MS = 1_735_689_600_000
UU_BASKET_USDT = 20_000_000


def _fetch(
    symbol: str,
    start_ms: int,
    end_ms: int,
    data: Path,
    like: pd.DataFrame | None,
    with_volume: bool = False,
):
    if symbol != CONSTANT_ONE:
        return fetch_klines(symbol, start_ms, end_ms, data, with_volume=with_volume)
    if like is None:
        raise ValueError(
            "the constant feed needs a real series to take its timestamps from"
        )
    # Never carries volume: CONST1 has no market series of its own, and the
    # single-leg pair (USDC/USDT) never passes this frame to `uu_profile` --
    # its profile is the real leg alone (spec §3).
    return pd.DataFrame({"open_time": like["open_time"].to_numpy(), "close": 1.0})


@cache
def kappa_for_pair(symbol0: str, symbol1: str) -> float:
    """kappa for one pair, cached: a 2024-wide constant (spec §3), not a
    per-window quantity, and refetching the calibration year per matrix cell
    would be wasteful -- it is the same number for every window of the pair.
    """
    data = ROOT / "data"
    df0 = fetch_klines(
        symbol0,
        UU_CALIBRATION_YEAR_START_MS,
        UU_CALIBRATION_YEAR_END_MS,
        data,
        with_volume=True,
    )
    if symbol1 == CONSTANT_ONE:
        profile = uu_profile(df0)
    else:
        df1 = fetch_klines(
            symbol1,
            UU_CALIBRATION_YEAR_START_MS,
            UU_CALIBRATION_YEAR_END_MS,
            data,
            with_volume=True,
        )
        df0, df1 = align_traces(df0, df1)
        profile = uu_profile(df0, df1)
    return _uu_kappa(profile, UU_BASKET_USDT)


@cache
def window_fingerprint(
    symbol0: str, symbol1: str, start_ms: int, end_ms: int
) -> tuple[str, int, int]:
    """`(checksum, extPrice0Initial, extPrice1Initial)` for one window's candles.

    Closes two holes in the reproducibility manifest at once, because both are
    determined by the same rows (2026-08-10 traceability review):

    * **`input_checksum` described nothing.** It hashed `data/trace0.csv` and
      `data/trace1.csv` -- the SHARED scratch files. A matrix cell writes its
      candles to its own worker directory, so those two were whatever some
      earlier ad-hoc `run_one` had left behind: all 15,552 manifests of both
      matrices carried the identical value `d3b98a44090795fd`. The field could
      not detect the silent data change it exists to detect.
    * **`P0` was literally `null`** in every manifest, while the paper's
      Eq. (9) names it as one of six fields. It is a function of the window's
      first candle, and "derivable" is not "recorded".

    The candles are the same ones `run_one` replays: the three legs fetched
    over `[start_ms, end_ms)` and aligned, so a change in any of them -- a
    re-fetch that returns different data, a cache corruption, a different
    alignment -- moves the checksum. Cached per window, so the parent process
    pays each pair-window once rather than once per cell.
    """
    import hashlib

    data = ROOT / "data"
    df0 = _fetch(symbol0, start_ms, end_ms, data, None)
    df1 = _fetch(symbol1, start_ms, end_ms, data, df0)
    dfg = _fetch(GAS_SYMBOL, start_ms, end_ms, data, df0)
    df0, df1, dfg = align_traces(df0, df1, dfg)

    digest = hashlib.sha256()
    for frame in (df0, df1, dfg):
        digest.update(frame["open_time"].to_numpy().tobytes())
        digest.update(frame["close"].to_numpy().tobytes())

    # The pool opens at the first candle's external ratio, so these two are P0
    # in the units the harness reads them in (Chainlink 1e8-scaled).
    p0 = round(float(df0["close"].iloc[0]) * PRICE_SCALE)
    p1 = round(float(df1["close"].iloc[0]) * PRICE_SCALE)
    return digest.hexdigest()[:16], p0, p1


def run_one(
    hook: str,
    symbol0: str,
    symbol1: str,
    start_ms: int,
    end_ms: int,
    fee_pips: int = 0,
    gas_price_wei: int = 20_000_000_000,
    gas_estimate: int = 76_578,
    address_mode: str = "persistent",
    basket_usdt: int = 20_000_000,
    warmup_candles: int = 60,
    size_dependent: bool = False,
    work_dir: Path | None = None,
    capture_share: int = 0,
    results_dir: Path | None = None,
    uu_mode: str = "off",
    uu_lambda_wad: int = UU_LAMBDA_WAD,
    uu_seed: int = 0,
    uu_sigma: float = 1.0,
    uu_kappa: float | None = None,
) -> dict:
    # The event log goes to `results/` under a name built from the run's axes,
    # which is exactly the name the matrix cell for those axes uses. An ad-hoc
    # call with the same axes therefore OVERWRITES a matrix trace, and because
    # the cell's manifest still matches, nothing recomputes and the stale trace
    # is what every trace-reading analysis then sees. That happened: a debugging
    # probe replaced one MEVChargeHook trace and its fee income disagreed with
    # summary.csv by 15 USDT until the integrity checks caught it.
    #
    # Pass `results_dir` to keep an exploratory run out of the shared directory.
    data = ROOT / "data"
    results = Path(results_dir) if results_dir else ROOT / "results"
    data.mkdir(exist_ok=True)
    results.mkdir(exist_ok=True)

    # Trace files are per-run, not shared: parallel workers would otherwise
    # overwrite each other's inputs and every result would be silently wrong.
    # The kline cache in `data/` stays shared -- it is read-only here.
    traces = Path(work_dir) if work_dir else data
    traces.mkdir(parents=True, exist_ok=True)

    uu_enabled = uu_mode != "off"

    # Volume-bearing frames only when UU flow needs the profile; mode "off"
    # must fetch (and cache) exactly as before -- byte-identical behaviour,
    # not just a byte-identical env.
    df0 = _fetch(symbol0, start_ms, end_ms, data, None, with_volume=uu_enabled)
    df1 = _fetch(symbol1, start_ms, end_ms, data, df0, with_volume=uu_enabled)
    dfg = _fetch(GAS_SYMBOL, start_ms, end_ms, data, df0)
    df0, df1, dfg = align_traces(df0, df1, dfg)

    export_trace(df0, traces / "trace0.csv")
    export_trace(df1, traces / "trace1.csv")
    export_trace(dfg, traces / "trace_gas.csv")

    uu_trace_path = None
    if uu_enabled:
        profile = uu_profile(df0) if symbol1 == CONSTANT_ONE else uu_profile(df0, df1)
        # None means the calibrated constant of spec §3 -- mean daily UU volume
        # over 2024 equals one basket. That rule fixes the retail scale by
        # turnover and never checked what informed/uninformed ratio it implied:
        # it implies 94-99% retail. An override makes that a swept axis instead
        # of an assumption, which is the same treatment `captureShare` got and
        # for the same reason. Default None keeps every existing call identical.
        kappa = kappa_for_pair(symbol0, symbol1) if uu_kappa is None else uu_kappa
        uu_trace_path = traces / "uu_trace.csv"
        export_uu_trace(
            profile, kappa, uu_trace_path, mode=uu_mode, seed=uu_seed, sigma=uu_sigma
        )

    share_tag = f"-cs{capture_share}" if capture_share else ""
    name = (
        f"{hook}-{fee_pips}-{symbol0}-{symbol1}-{start_ms}"
        f"-{gas_price_wei}-{address_mode}{share_tag}.jsonl"
    )
    out = results / name

    env = {
        **os.environ,
        "HOOK_NAME": hook,
        "FEE_PIPS": str(fee_pips),
        "TRACE0": str((traces / "trace0.csv").resolve()),
        "TRACE1": str((traces / "trace1.csv").resolve()),
        "TRACE_GAS": str((traces / "trace_gas.csv").resolve()),
        "OUT": str(out.resolve()),
        "GAS_PRICE_WEI": str(gas_price_wei),
        "GAS_ESTIMATE": str(gas_estimate),
        "ADDRESS_MODE": address_mode,
        "BASKET_USDT": str(basket_usdt),
        "WARMUP_CANDLES": str(warmup_candles),
        "SIZE_DEPENDENT": "true" if size_dependent else "false",
        "CAPTURE_SHARE": str(capture_share),
    }
    # Mode "off" must be byte-identical to before this feature existed: no
    # UU_TRACE key at all, not even an empty one (2026-08-09-uu-flow-design.md
    # §10.2, the differential golden).
    if uu_enabled:
        env["UU_TRACE"] = str(uu_trace_path.resolve())
        env["UU_MODE"] = uu_mode
        env["UU_LAMBDA_WAD"] = str(uu_lambda_wad)

    forge = str(FORGE) if FORGE.exists() else "forge"
    subprocess.run(
        [
            forge,
            "test",
            "--match-test",
            "testReplay",
            "--match-path",
            "test/Replay.t.sol",
        ],
        cwd=ROOT / "contracts",
        check=True,
        capture_output=True,
        env=env,
    )

    swaps, window = read_events(out)
    # Gas is paid in ETH, so it is valued at the ETH series -- the same one the
    # harness uses for the arbitrageur's entry threshold -- and not at token0's
    # price, which only happens to be ETH for two of the three pairs.
    eth_price_1e8 = float(dfg["close"].iloc[-1]) * PRICE_SCALE
    return compute(swaps, window, float(gas_price_wei), eth_price_1e8=eth_price_1e8)
