"""Uninformed-user (UU) flow trace generation.

Per spec `docs/superpowers/specs/2026-08-09-uu-flow-design.md` §3-4: a
per-candle potential UU volume is derived from Binance quote volumes
(`uu_profile`), scaled to a calibrated daily turnover (`kappa`), and written
to a CSV the Forge harness reads at replay time (`export_uu_trace`). All
randomness (mode "discrete") happens here, in Python, at trace-generation
time -- Solidity stays deterministic; the seed is a manifest field.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

WAD = 1e18
MINUTES_PER_DAY = 1440

# Canonical default: half the willing flow walks at a 30 bps TOTAL transaction
# cost (fee + slippage + signed pool deviation), which is what `r` measures.
#
# `r` is the source model's normalised form, `r = dP(dx,dy)/dP(|dx|,|dy|)`, and
# for a user losing a fraction `eps` of value that is `-eps/(2-eps)` -- about
# HALF the fractional disadvantage. So the calibration is
# `ln(2)/|r(0.003)| = ln(2)/0.001502253 = 461.404973`, not `ln(2)/0.003`.
#
# It was 231_049_060_186_648_440_000 while the implementation used an
# un-normalised marginal-price `r = -eps`; that form was twice the source
# model's value and omitted slippage entirely.
UU_LAMBDA_WAD = 461_404_973_192_736_927_635


def uu_profile(*volume_frames: pd.DataFrame) -> pd.DataFrame:
    """Per-candle UU activity profile: columns `open_time, v_usdt`.

    `v_usdt` is the geometric mean of the given legs' `quote_volume` (one
    frame for USDC/USDT, whose second leg is CONSTANT_ONE and contributes
    nothing; two frames for ETH/SHIB and ETH/USDC). Frames are assumed
    already aligned by the caller (`align_traces`) -- same length, same
    `open_time` at each row.

    A single frame is the identity, not a degenerate geometric mean: routing
    it through log/exp would introduce float round-trip noise for no reason.

    A zero-volume minute is clamped to the smallest positive value present in
    that leg before the log, so one dead minute does not zero the whole
    profile (geometric mean is undefined at zero).
    """
    if not volume_frames:
        raise ValueError("uu_profile requires at least one volume frame")

    open_time = volume_frames[0]["open_time"].reset_index(drop=True)

    if len(volume_frames) == 1:
        v_usdt = volume_frames[0]["quote_volume"].astype(float).reset_index(drop=True)
        return pd.DataFrame({"open_time": open_time, "v_usdt": v_usdt})

    clamped_logs = []
    for frame in volume_frames:
        vol = frame["quote_volume"].astype(float).reset_index(drop=True)
        positive = vol[vol > 0]
        floor = float(positive.min()) if len(positive) else 1.0
        clamped_logs.append(np.log(vol.clip(lower=floor)).to_numpy())

    v_usdt = np.exp(np.mean(np.vstack(clamped_logs), axis=0))
    return pd.DataFrame({"open_time": open_time, "v_usdt": v_usdt})


def kappa(profile: pd.DataFrame, basket_usdt: float) -> float:
    """Scale so mean daily UU volume (Sigma v_usdt over a day) equals one
    basket, i.e. turnover 1x/day (spec §3). Profile candles are 1-minute."""
    mean_daily = float(profile["v_usdt"].mean()) * MINUTES_PER_DAY
    return basket_usdt / mean_daily


def _to_wad_int(x: float) -> int:
    # round(), not truncate: guards against a value like 99999999999999998.9994
    # (float noise just under the intended integer) landing one wei short.
    # round() on a single float arg already returns int, per Python semantics.
    return round(x * WAD)


def export_uu_trace(
    profile: pd.DataFrame,
    kappa: float,
    path: Path,
    mode: str = "share",
    seed: int = 0,
    sigma: float = 1.0,
) -> None:
    """Write the headerless UU trace CSV the harness loads:
    `open_time,size_ab_wad,u_ab_wad,size_ba_wad,u_ba_wad` (all ints; sizes in
    USDT-wad).

    Mode "share" (default, deterministic-share matrix mode): per direction,
    `size = kappa*v/2`, `u = 0`. The harness thins multiplicatively
    (`amount = size * P`).

    Mode "discrete" (hybrid groundwork, spec §2.4): per direction, one
    lognormal potential trade, `size = (kappa*v/2)*exp(sigma*Z - sigma^2/2)`
    with `Z ~ N(0,1)` (mean-preserving: E[exp(sigma*Z - sigma^2/2)] == 1), `u
    = floor(U(0,1)*1e18)`. The harness executes all-or-nothing (`amount =
    size` iff `u <= P*1e18`). Seeded via `numpy.random.default_rng(seed)` for
    bit-for-bit reproducibility.
    """
    path = Path(path)
    v_half = profile["v_usdt"].to_numpy(dtype=float) * kappa / 2.0
    open_time = profile["open_time"].to_numpy()
    n = len(profile)

    if mode == "share":
        size_ab = [_to_wad_int(v) for v in v_half]
        size_ba = size_ab
        u_ab = [0] * n
        u_ba = [0] * n
    elif mode == "discrete":
        rng = np.random.default_rng(seed)
        z_ab = rng.standard_normal(n)
        u_ab_f = rng.uniform(0.0, 1.0, n)
        z_ba = rng.standard_normal(n)
        u_ba_f = rng.uniform(0.0, 1.0, n)
        size_ab = [
            _to_wad_int(v * np.exp(sigma * z - sigma * sigma / 2.0))
            for v, z in zip(v_half, z_ab)
        ]
        size_ba = [
            _to_wad_int(v * np.exp(sigma * z - sigma * sigma / 2.0))
            for v, z in zip(v_half, z_ba)
        ]
        u_ab = [int(np.floor(u * WAD)) for u in u_ab_f]
        u_ba = [int(np.floor(u * WAD)) for u in u_ba_f]
    else:
        raise ValueError(f"unknown uu mode: {mode!r}")

    lines = [
        f"{int(t)},{size_ab[i]},{u_ab[i]},{size_ba[i]},{u_ba[i]}"
        for i, t in enumerate(open_time)
    ]
    path.write_text("\n".join(lines) + ("\n" if lines else ""))
