"""Sensitivity of PegCapture to `captureShare`.

NOT part of the pre-registered analysis plan (spec §12.1). PegCapture is the
only policy with a positive headline result, and that result rests on a constant
chosen during implementation rather than declared in advance. Reporting it
without a sweep would invite exactly the objection it deserves.

Kept in its own results directory so it can never be mistaken for, or merged
into, the pre-registered matrix.
"""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

from experiments.calibrate_gas import load as load_gas
from experiments.matrix import BASKET_USDT, GAS_SCENARIOS_WEI, load_windows
from experiments.run_one import run_one

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results" / "sensitivity"

# The upper end is dense on purpose. Net result rises monotonically to 0.75 and
# a single probe at 0.90 already trades zero times, so the turnover sits inside
# that gap; a grid that stopped at 0.75 would report a boundary as an optimum.
SHARES = (100_000, 250_000, 500_000, 750_000, 800_000, 850_000, 900_000)
PAIR = ("ETH/SHIB", "ETHUSDT", "SHIBUSDT")


def _one(job):
    share, window, gas, estimate = job
    work = ROOT / ".work" / f"cs{share}-{window['start_ms']}-{gas}"
    try:
        m = run_one(
            "PegCapture",
            PAIR[1],
            PAIR[2],
            window["start_ms"],
            window["end_ms"],
            gas_price_wei=gas,
            gas_estimate=estimate,
            basket_usdt=BASKET_USDT,
            capture_share=share,
            work_dir=work,
        )
        return {
            "capture_share": share,
            "window_start_ms": window["start_ms"],
            "regime": window["regime"],
            "gas_price_wei": gas,
            **m,
            "error": None,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "capture_share": share,
            "window_start_ms": window["start_ms"],
            "gas_price_wei": gas,
            "error": f"{type(exc).__name__}: {exc}",
        }
    finally:
        import shutil

        shutil.rmtree(work, ignore_errors=True)


def run(workers: int = 8) -> pd.DataFrame:
    RESULTS.mkdir(parents=True, exist_ok=True)
    estimate = load_gas().get("PegCapture", 104_368)
    windows = load_windows()[PAIR[0]]

    jobs = [
        (share, window, gas, estimate)
        for share in SHARES
        for window in windows
        for gas in GAS_SCENARIOS_WEI
    ]
    print(f"{len(jobs)} cells across {len(SHARES)} values of captureShare")

    rows = []
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_one, j) for j in jobs]
        for i, fut in enumerate(as_completed(futures), 1):
            rows.append(fut.result())
            if i % 50 == 0:
                print(f"  {i}/{len(jobs)}", flush=True)

    frame = pd.DataFrame(rows)
    frame.to_csv(RESULTS / "capture_share.csv", index=False)
    return frame


def analyse(
    frame: pd.DataFrame | None = None,
    summary_csv: Path | None = None,
    baseline: str = "MyHook@3000",
) -> pd.DataFrame:
    """Each `captureShare` against the static baseline, paired by window.

    Same machinery as the pre-registered analysis -- Wilcoxon signed-rank per
    comparison, then Benjamini-Hochberg across the family -- but a separate
    family: these comparisons were not declared in advance, and pooling them
    into the pre-registered `analysis.csv` would change that file's FDR
    threshold after the fact.
    """
    from experiments.stats import benjamini_hochberg, wilcoxon_paired

    frame = pd.read_csv(RESULTS / "capture_share.csv") if frame is None else frame
    frame = frame[frame["error"].isna()]

    summary = pd.read_csv(summary_csv or ROOT / "results" / "summary.csv")
    key = ["window_start_ms", "gas_price_wei"]
    base = summary[
        (summary["policy"] == baseline)
        & (summary["pair"] == PAIR[0])
        & (summary["address_mode"] == "persistent")
    ].set_index(key)["net_result"]

    rows = []
    for share, group in frame.groupby("capture_share"):
        # "ALL" alongside the three regimes: the regime split is the finding,
        # but a reader wants the headline number too.
        for regime, subset in list(group.groupby("regime")) + [("ALL", group)]:
            indexed = subset.set_index(key)
            deltas = (indexed["net_result"] - base.reindex(indexed.index)).dropna()
            rows.append(
                {
                    "capture_share": share,
                    "share": share / 1e6,
                    "regime": regime,
                    "baseline": baseline,
                    **wilcoxon_paired(deltas),
                }
            )

    result = pd.DataFrame(rows)
    # Same name as `stats.analyse` uses: two functions called `analyse` that
    # disagree on a column name is a trap for whoever reads both.
    result["significant_fdr"] = benjamini_hochberg(result["p"].tolist())
    RESULTS.mkdir(parents=True, exist_ok=True)
    result.to_csv(RESULTS / "capture_share_tests.csv", index=False)
    return result


if __name__ == "__main__":
    f = run()
    print("errors:", f["error"].notna().sum())
    ok = f[f["error"].isna()]
    worst = (
        ok[["conservation_error_token0", "conservation_error_token1"]].abs().max().max()
    )
    print(f"worst conservation error: {worst:.2e}")
    print()
    print(
        ok.groupby("capture_share")
        .agg(
            trades=("trade_count", "mean"),
            fees=("fee_income", "mean"),
            net=("net_result", "mean"),
            volume=("retained_volume", "mean"),
        )
        .round(1)
        .to_string()
    )
