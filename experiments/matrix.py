"""The run matrix: enumerate every configuration, execute, resume, collect.

Axes and their reasons are in spec §7.2, §8 and §9. The driver is resumable:
a run whose manifest already matches on disk is skipped, so an interrupted
matrix continues rather than restarting. A run that fails is recorded and the
matrix carries on — the stable pair is expected to produce little or nothing,
and that is a finding rather than a reason to stop.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from experiments.policies import ALL, Policy

ROOT = Path(__file__).resolve().parent.parent

# Spec §4.3: identical across every run, because the arbitrageur's entry
# threshold depends on the ratio of gas cost to pool depth.
BASKET_USDT = 20_000_000

# Windows drawn from each volatility tercile, per pair.
#
# Was 8, which put every comparison on 8 paired observations and bounded the
# smallest two-sided Wilcoxon p-value at 2/2^8 = 0.0078. Under BH across the
# family that floor is only cleared when ~47 comparisons reach it together, so
# no isolated effect was detectable at any size -- every significant result in
# that run sat at exactly p = 0.007812. At 24 the floor is 1.2e-07.
#
# 122 days are available per tercile. See the pre-registration in
# docs/superpowers/specs/2026-08-04-power-extension-preregistration.md, which
# was recorded before this run.
WINDOWS_PER_TERCILE = 24

# Fallback when a policy produced no trades during calibration.
DEFAULT_GAS_ESTIMATE = 76_578

# A synthetic feed pinned at 1.0. The stable pair prices USDC against USDT, and
# the second leg has no market series of its own. Formally this is not a market
# observation and the paper must say so (spec §16).
CONSTANT_ONE = "CONST1"


@dataclass(frozen=True)
class Pair:
    name: str
    symbol0: str
    symbol1: str
    regime_label: str


PAIRS: tuple[Pair, ...] = (
    Pair("ETH/SHIB", "ETHUSDT", "SHIBUSDT", "high volatility"),
    Pair("ETH/USDC", "ETHUSDT", "USDCUSDT", "major"),
    Pair("USDC/USDT", "USDCUSDT", CONSTANT_ONE, "stablecoin"),
)

# Gas is not a report line: it enters the arbitrageur's entry condition and so
# changes which trades happen at all.
GAS_SCENARIOS_WEI: tuple[int, ...] = (5_000_000_000, 20_000_000_000, 80_000_000_000)

# MEVChargeHook derives its fee from the history of a specific address, so this
# axis moves it from top to bottom of the table while leaving the others
# untouched — which is itself the check that they are address-insensitive.
# One mode, not two. Under UU flow the axis is empty: measured over all 7,776
# paired cells of the superseded matrix, `fresh` and `persistent` agree to the
# last bit for every one of the twelve policies -- including MEVChargeHook, the
# only one that reads the sender, because UU swaps always come from fresh
# addresses and the arbitrageur it could have profiled barely trades. The
# analysis already deduplicated this axis (2026-08-03 audit: "266 of 270
# comparisons are bit-identical"), so half the matrix was computing rows that
# were then thrown away. Declared in 2026-08-10-r-correction-preregistration.md.
ADDRESS_MODES: tuple[str, ...] = ("persistent",)


@dataclass(frozen=True)
class RunSpec:
    policy: Policy
    pair: Pair
    window: dict
    gas_price_wei: int
    address_mode: str

    @property
    def key(self) -> str:
        return (
            f"{self.policy.name}__{self.pair.name.replace('/', '-')}"
            f"__{self.window['start_ms']}__{self.gas_price_wei}__{self.address_mode}"
        )


def enumerate_runs(windows_by_pair: dict[str, list[dict]]) -> list[RunSpec]:
    """Every cell of the matrix, in a deterministic order."""
    specs: list[RunSpec] = []
    for policy in ALL:
        for mode in ADDRESS_MODES:
            for pair in PAIRS:
                for window in windows_by_pair[pair.name]:
                    for gas in GAS_SCENARIOS_WEI:
                        specs.append(RunSpec(policy, pair, window, gas, mode))
    return specs


def execute(
    specs: list[RunSpec],
    results_dir: Path,
    runner,
    manifest_for=None,
    on_progress=None,
) -> pd.DataFrame:
    """Run every spec, skipping those whose manifest already matches.

    A failing run is recorded in an `error` column and the matrix continues:
    the stable pair may legitimately produce nothing, and one dead cell must not
    take the other 4751 with it.
    """
    from experiments.manifest import matches, write_manifest

    results_dir = Path(results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict] = []
    for index, spec in enumerate(specs):
        manifest_path = results_dir / f"{spec.key}.manifest.json"
        manifest = manifest_for(spec) if manifest_for else None

        base = {
            "policy": spec.policy.name,
            "hook": spec.policy.hook,
            "fee_pips": spec.policy.fee_pips,
            "pair": spec.pair.name,
            "window_start_ms": spec.window["start_ms"],
            "regime": spec.window.get("regime"),
            "gas_price_wei": spec.gas_price_wei,
            "address_mode": spec.address_mode,
        }

        if manifest is not None and matches(manifest_path, manifest):
            cached = results_dir / f"{spec.key}.metrics.json"
            if cached.exists():
                import json

                rows.append({**base, **json.loads(cached.read_text()), "error": None})
                continue

        try:
            metrics = runner(spec)
            rows.append({**base, **metrics, "error": None})
            if manifest is not None:
                import json

                (results_dir / f"{spec.key}.metrics.json").write_text(
                    json.dumps(metrics, indent=2) + "\n"
                )
                write_manifest(manifest_path, manifest)
        except Exception as exc:  # noqa: BLE001 - one dead cell must not stop the sweep
            rows.append({**base, "error": f"{type(exc).__name__}: {exc}"})

        if on_progress:
            on_progress(index + 1, len(specs), spec)

    return pd.DataFrame(rows)


def load_segments(
    data_dir: Path | None = None, per_tercile: int = WINDOWS_PER_TERCILE
) -> tuple[dict[str, pd.DataFrame], dict[str, pd.DataFrame]]:
    """Every day of the year per pair, and the subset the selection rule took.

    Returns `(all_days, selected)`. Both are needed to show *how* the windows
    were chosen rather than assert it, which is the one step in the design a
    reader is most entitled to distrust.
    """
    from experiments.binance import fetch_klines
    from experiments.run_one import _fetch
    from experiments.windows import daily_segments, select_windows

    data = Path(data_dir or ROOT / "data")
    year_start, year_end = 1_704_067_200_000, 1_735_689_600_000

    all_days: dict[str, pd.DataFrame] = {}
    selected: dict[str, pd.DataFrame] = {}
    for pair in PAIRS:
        df0 = fetch_klines(pair.symbol0, year_start, year_end, data)
        df1 = _fetch(pair.symbol1, year_start, year_end, data, df0)
        segments = daily_segments(df0, df1)
        all_days[pair.name] = segments
        selected[pair.name] = select_windows(segments, per_tercile=per_tercile)
    return all_days, selected


def load_windows(
    data_dir: Path | None = None, per_tercile: int = WINDOWS_PER_TERCILE
) -> dict[str, list[dict]]:
    """Stratified windows per pair, computed from the cached candles.

    The run-facing view of `load_segments`: just the chosen windows, as the
    plain dicts the harness and the manifest take.
    """
    _, selected = load_segments(data_dir, per_tercile)
    return {
        name: [
            {
                "start_ms": int(r.start_ms),
                "end_ms": int(r.end_ms),
                "regime": r.regime,
                "volatility": float(r.volatility),
                "pair": name,
            }
            for r in chosen.itertuples()
        ]
        for name, chosen in selected.items()
    }


# The retail scale the matrix runs at, as a multiple of the calibrated kappa
# (one basket of uninformed volume per day). 1.0 is the pre-registered headline.
# A second declared configuration runs at 0.1, where the arbitrage share is
# ~56% rather than ~18%: kappa was fixed by a rule about TURNOVER, and the
# mechanism under test depends on the INFORMED SHARE, which turnover does not
# control. Both points are reported; neither replaces the other.
UU_TURNOVER_DEFAULT = 1.0


def manifest_for(
    spec: RunSpec,
    gas_estimates: dict[str, int] | None = None,
    uu_mode: str = "off",
    uu_turnover: float = UU_TURNOVER_DEFAULT,
) -> dict:
    """The Eq. (9) manifest for one cell, which is also its resume key.

    `S` (the arbitrageur field) gains five fields when UU flow is on: `uu_mode`,
    `uu_lambda_wad`, `uu_kappa`, `uu_seed`, `uu_sigma`, plus the UU trace's own
    checksum. Absent when off, so an old arb-only manifest never matches a UU
    one and vice versa -- the resume-skip protection working as intended
    (2026-08-09-uu-flow.md Task 7).
    """
    from experiments.manifest import (
        build_manifest,
        checksum,
        solc_version,
        submodule_revisions,
    )
    from experiments.run_one import window_fingerprint

    gas_estimates = gas_estimates or {}
    data = ROOT / "data"

    # The window's own candles, not the shared scratch files in `data/`. See
    # `window_fingerprint` for what those two fields used to contain.
    fingerprint, p0_price0, p0_price1 = window_fingerprint(
        spec.pair.symbol0,
        spec.pair.symbol1,
        spec.window["start_ms"],
        spec.window["end_ms"],
    )

    arbitrageur = {
        "gas_price_wei": spec.gas_price_wei,
        "gas_estimate": gas_estimates.get(spec.policy.name, DEFAULT_GAS_ESTIMATE),
        "size_dependent": spec.policy.size_dependent,
        "address_mode": spec.address_mode,
    }
    if uu_mode != "off":
        from experiments.run_one import kappa_for_pair
        from experiments.uu import UU_LAMBDA_WAD

        arbitrageur.update(
            {
                "uu_mode": uu_mode,
                "uu_lambda_wad": UU_LAMBDA_WAD,
                "uu_kappa": kappa_for_pair(spec.pair.symbol0, spec.pair.symbol1)
                * uu_turnover,
                "uu_turnover": uu_turnover,
                "uu_seed": 0,
                "uu_sigma": 1.0,
            }
        )
        uu_trace = data / "uu_trace.csv"
        if uu_trace.exists():
            arbitrageur["uu_trace_checksum"] = checksum([uu_trace])

    return build_manifest(
        policy=spec.policy.name,
        policy_params={"hook": spec.policy.hook, "fee_pips": spec.policy.fee_pips},
        submodules=submodule_revisions(),
        solc=solc_version(),
        # The harness derives the opening sqrt price from these two, so
        # recording them pins P0 without duplicating the harness's arithmetic
        # in Python -- where it could drift.
        p0_sqrt_price_x96={"extPrice0": p0_price0, "extPrice1": p0_price1},
        l0_basket_usdt=BASKET_USDT,
        window=spec.window,
        arbitrageur=arbitrageur,
        input_checksum=fingerprint,
    )


def run_spec(
    spec: RunSpec,
    gas_estimates: dict[str, int] | None = None,
    work_dir: Path | None = None,
    uu_mode: str = "off",
    results_dir: Path | None = None,
    uu_turnover: float = UU_TURNOVER_DEFAULT,
) -> dict:
    """Execute one cell and return its metrics.

    `results_dir` is where the per-swap JSONL event trace goes, and it must be
    the directory of the experiment being run. Omitting it used to be the only
    option, and `run_one` then fell back to its default `results/`: the UU
    matrix wrote 15,552 traces over the arb-only experiment's, under
    byte-identical seven-field filenames, while its metrics went to
    `results-uu/matrix/`. Nothing failed; the two experiments' trace-level
    analyses just swapped inputs.
    """
    from experiments.run_one import kappa_for_pair, run_one

    gas_estimates = gas_estimates or {}
    return run_one(
        spec.policy.hook,
        spec.pair.symbol0,
        spec.pair.symbol1,
        spec.window["start_ms"],
        spec.window["end_ms"],
        fee_pips=spec.policy.fee_pips,
        gas_price_wei=spec.gas_price_wei,
        gas_estimate=gas_estimates.get(spec.policy.name, DEFAULT_GAS_ESTIMATE),
        address_mode=spec.address_mode,
        basket_usdt=BASKET_USDT,
        size_dependent=spec.policy.size_dependent,
        work_dir=work_dir,
        uu_mode=uu_mode,
        results_dir=results_dir,
        uu_kappa=(
            None
            if uu_mode == "off" or uu_turnover == 1.0
            else kappa_for_pair(spec.pair.symbol0, spec.pair.symbol1) * uu_turnover
        ),
    )


# ---------------------------------------------------------------- parallel run


def _worker(payload):
    """One cell, in its own process and its own trace directory.

    The directory lives under the project rather than the system temp: Forge's
    `fs_permissions` is a path allowlist, and on macOS `tempfile` hands out
    `/var/folders/...` which no reasonable allowlist covers.
    """
    import shutil

    spec, gas_estimates, uu_mode, results_dir, uu_turnover = payload
    work = ROOT / ".work" / spec.key
    try:
        return (
            spec.key,
            run_spec(
                spec,
                gas_estimates,
                work_dir=work,
                uu_mode=uu_mode,
                results_dir=results_dir,
                uu_turnover=uu_turnover,
            ),
            None,
        )
    except Exception as exc:  # noqa: BLE001
        return spec.key, None, f"{type(exc).__name__}: {exc}"
    finally:
        shutil.rmtree(work, ignore_errors=True)


def base_row(spec: RunSpec) -> dict:
    """The axes of one cell, as they appear in `summary.csv`."""
    return {
        "policy": spec.policy.name,
        "hook": spec.policy.hook,
        "fee_pips": spec.policy.fee_pips,
        "pair": spec.pair.name,
        "window_start_ms": spec.window["start_ms"],
        "regime": spec.window.get("regime"),
        "volatility": spec.window.get("volatility"),
        "gas_price_wei": spec.gas_price_wei,
        "address_mode": spec.address_mode,
    }


def collect(specs: list[RunSpec], results_dir: Path) -> pd.DataFrame:
    """Every cell of `specs` that has a metrics file on disk, as one frame.

    Separate from `execute_parallel` because the summary must describe the whole
    matrix even when only part of it was just run. Building it from the runner's
    return value instead meant that `--pair ETH/SHIB`, or any other restriction,
    silently truncated `summary.csv` to the subset -- the other two thirds of the
    matrix were still on disk, and the file that every notebook reads no longer
    mentioned them.

    Manifests are deliberately not consulted here. Whether a cell is up to date
    is the runner's question; this one only asks what has been computed.
    """
    rows = []
    for spec in specs:
        metrics_path = Path(results_dir) / f"{spec.key}.metrics.json"
        if not metrics_path.exists():
            continue
        rows.append(
            {**base_row(spec), **json.loads(metrics_path.read_text()), "error": None}
        )
    return pd.DataFrame(rows)


def execute_parallel(
    specs: list[RunSpec],
    results_dir: Path,
    gas_estimates: dict[str, int] | None = None,
    workers: int | None = None,
    on_progress=None,
    uu_mode: str = "off",
    uu_turnover: float = UU_TURNOVER_DEFAULT,
) -> pd.DataFrame:
    """Run the matrix across processes.

    Each worker gets its own trace directory, so nothing is shared but the
    read-only kline cache. Completed cells are skipped by manifest, so an
    interrupted run resumes rather than restarting.

    Forge is single-threaded per invocation and the work is CPU-bound, so
    `workers` should be around the core count; leaving one core free keeps the
    machine usable.
    """
    import json
    import os
    from concurrent.futures import ProcessPoolExecutor, as_completed

    from experiments.manifest import matches, write_manifest

    gas_estimates = gas_estimates or {}
    results_dir = Path(results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)
    workers = workers or max(1, (os.cpu_count() or 2) - 1)

    base_of: dict[str, dict] = {}
    pending: list[RunSpec] = []
    rows: list[dict] = []

    for spec in specs:
        base_of[spec.key] = base_row(spec)
        manifest_path = results_dir / f"{spec.key}.manifest.json"
        cached = results_dir / f"{spec.key}.metrics.json"
        if cached.exists() and matches(
            manifest_path, manifest_for(spec, gas_estimates, uu_mode, uu_turnover)
        ):
            rows.append(
                {**base_of[spec.key], **json.loads(cached.read_text()), "error": None}
            )
        else:
            pending.append(spec)

    done = 0
    with ProcessPoolExecutor(max_workers=workers) as pool:
        # The traces go one level above the per-cell metrics, which is where
        # `results/` sits relative to `results/matrix/` -- so the two
        # experiments keep their traces apart instead of sharing `results/`.
        traces_dir = results_dir.parent
        futures = {
            pool.submit(
                _worker, (s, gas_estimates, uu_mode, traces_dir, uu_turnover)
            ): s
            for s in pending
        }
        for future in as_completed(futures):
            key, metrics, error = future.result()
            spec = futures[future]
            if error is None:
                rows.append({**base_of[key], **metrics, "error": None})
                (results_dir / f"{key}.metrics.json").write_text(
                    json.dumps(metrics, indent=2) + "\n"
                )
                write_manifest(
                    results_dir / f"{key}.manifest.json",
                    manifest_for(spec, gas_estimates, uu_mode, uu_turnover),
                )
            else:
                rows.append({**base_of[key], "error": error})
            done += 1
            if on_progress:
                on_progress(done, len(pending), key)

    return pd.DataFrame(rows)
