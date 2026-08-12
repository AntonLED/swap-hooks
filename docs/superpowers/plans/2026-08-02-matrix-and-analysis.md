# Run Matrix and Analysis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Select windows by volatility regime, execute the 4752-run matrix with
a reproducibility manifest per run, and aggregate the results into the tables
and figures the paper needs.

**Architecture:** Python owns window selection, run orchestration, and analysis.
Each run is one Forge invocation writing one JSONL file plus one manifest JSON.
Aggregation reads the whole `results/` tree and produces per-regime tables. The
matrix driver is resumable: a run whose manifest already matches is skipped.

**Tech Stack:** Python 3.13 via uv, pandas, numpy, scipy, matplotlib, pytest;
Forge as a subprocess.

**Depends on:** `2026-08-02-experiment-harness-foundation.md` and
`2026-08-02-policies.md`.

## Global Constraints

- Initial basket: 20,000,000 USDT, identical across runs.
- Window length: 1440 candles. Warm-up: first 60 candles excluded from metrics.
- Windows per pair: 24, being 8 from each volatility tercile.
- Pairs: ETH/SHIB (ETHUSDT, SHIBUSDT), ETH/USDC (ETHUSDT, USDCUSDT), USDC/USDT
  (USDCUSDT, constant 1). Year 2024.
- Gas scenarios: 5, 20, 80 gwei, converted through the ETH/USDT feed at swap
  time. `ETHUSDT` is loaded for every pair, for the stable pair solely to price
  gas.
- Configurations: 7 policy configurations (the six hooks, with
  `PegStabilityHook` run as both `PegDefence` and `PegCapture`) + 4 static
  baseline levels = 11.
- Address modes: `persistent`, `fresh`.
- Gas estimate per policy comes from `experiments/gas_estimates.json` (Plan 2,
  Task 9) and is recorded in each manifest. It is not a global constant: an
  oracle-reading hook costs materially more per swap than a constant-fee one,
  and that gap is what the gas axis measures.
- Matrix: 11 × 2 × 3 × 24 × 3 = **4752 runs**.
- No randomness. Window selection is fully determined by the price data.
- The stable pair is run on the same terms as the others. An empty result is a
  finding, not a failure — never special-case it.
- Never run `git commit` unless a step says to.

---

## File Structure

- `experiments/windows.py` — realised volatility, tercile split, window
  selection. Pure functions over a price frame; no IO.
- `experiments/manifest.py` — builds and compares the reproducibility manifest.
- `experiments/matrix.py` — the driver: enumerate, skip completed, execute,
  collect.
- `experiments/aggregate.py` — load every result, join manifests, group by
  regime.
- `experiments/figures.py` — the plots.
- `tests/` — one suite per module.

---

### Task 1: Realised volatility and tercile selection

**Files:**

- Create: `experiments/windows.py`
- Create: `tests/test_windows.py`

**Interfaces:**

- Produces:
  - `realised_volatility(ratio: pd.Series) -> float` — standard deviation of
    per-minute log returns scaled by `sqrt(1440)`.
  - `daily_segments(df0, df1) -> pd.DataFrame` with columns `start_ms`,
    `end_ms`, `volatility`.
  - `select_windows(segments: pd.DataFrame, per_tercile: int = 8) -> pd.DataFrame`
    adding a `regime` column with values `low`, `mid`, `high`.

- [ ] **Step 1: Write the failing tests**

```python
import numpy as np
import pandas as pd
import pytest

from experiments.windows import daily_segments, realised_volatility, select_windows

MINUTE = 60_000
DAY = 1440 * MINUTE


def _flat(n, value=100.0, start=0):
    return pd.DataFrame(
        {"open_time": [start + i * MINUTE for i in range(n)], "close": [value] * n}
    )


def _wobbly(n, amplitude, start=0):
    closes = [100.0 * (1 + amplitude * (-1) ** i) for i in range(n)]
    return pd.DataFrame(
        {"open_time": [start + i * MINUTE for i in range(n)], "close": closes}
    )


def test_flat_price_has_zero_volatility():
    assert realised_volatility(pd.Series([100.0] * 100)) == pytest.approx(0.0)


def test_volatility_grows_with_amplitude():
    calm = realised_volatility(pd.Series(_wobbly(100, 0.001)["close"]))
    wild = realised_volatility(pd.Series(_wobbly(100, 0.010)["close"]))
    assert wild > calm


def test_misaligned_symbols_do_not_shift_the_ratio():
    """A gap in one symbol must drop that minute, not slide every later price."""
    a = _flat(1440 * 2, value=100.0)
    b = _flat(1440 * 2, value=50.0).drop(index=5).reset_index(drop=True)
    segs = daily_segments(a, b)

    assert (segs["volatility"] == pytest.approx(0.0)).all(), (
        "two flat series must stay flat after alignment"
    )


def test_segments_are_whole_days_and_do_not_overlap():
    df0 = _flat(1440 * 3)
    df1 = _flat(1440 * 3, value=50.0)
    segs = daily_segments(df0, df1)

    assert len(segs) == 3
    assert (segs["end_ms"] - segs["start_ms"] == DAY).all()
    assert (segs["start_ms"].diff().dropna() == DAY).all()


def test_select_returns_equal_counts_per_regime():
    segs = pd.DataFrame(
        {
            "start_ms": [i * DAY for i in range(90)],
            "end_ms": [(i + 1) * DAY for i in range(90)],
            "volatility": np.linspace(0.01, 0.9, 90),
        }
    )
    chosen = select_windows(segs, per_tercile=8)

    assert len(chosen) == 24
    assert chosen["regime"].value_counts().to_dict() == {"low": 8, "mid": 8, "high": 8}


def test_selection_is_deterministic():
    segs = pd.DataFrame(
        {
            "start_ms": [i * DAY for i in range(90)],
            "end_ms": [(i + 1) * DAY for i in range(90)],
            "volatility": np.linspace(0.01, 0.9, 90),
        }
    )
    first = select_windows(segs, per_tercile=8)
    second = select_windows(segs, per_tercile=8)

    pd.testing.assert_frame_equal(first, second)


def test_low_regime_really_is_the_calmest():
    segs = pd.DataFrame(
        {
            "start_ms": [i * DAY for i in range(90)],
            "end_ms": [(i + 1) * DAY for i in range(90)],
            "volatility": np.linspace(0.01, 0.9, 90),
        }
    )
    chosen = select_windows(segs, per_tercile=8)

    low = chosen.loc[chosen["regime"] == "low", "volatility"].max()
    high = chosen.loc[chosen["regime"] == "high", "volatility"].min()
    assert low < high
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_windows.py -v` Expected: FAIL — module missing.

- [ ] **Step 3: Implement**

```python
"""Window selection: realised volatility, tercile split, deterministic sampling."""

from __future__ import annotations

import numpy as np
import pandas as pd

from experiments.export_trace import align_traces

MINUTE_MS = 60_000
CANDLES_PER_DAY = 1440
DAY_MS = CANDLES_PER_DAY * MINUTE_MS
REGIMES = ("low", "mid", "high")


def realised_volatility(ratio: pd.Series) -> float:
    """Std of per-minute log returns, scaled to a daily basis."""
    values = pd.Series(ratio).astype(float)
    if len(values) < 2:
        return 0.0
    returns = np.diff(np.log(values.to_numpy()))
    if returns.size < 2:
        return 0.0
    return float(np.std(returns, ddof=1) * np.sqrt(CANDLES_PER_DAY))


def daily_segments(df0: pd.DataFrame, df1: pd.DataFrame) -> pd.DataFrame:
    """Non-overlapping whole-day segments with the volatility of token0/token1.

    The frames are aligned on shared timestamps first. Binance occasionally omits
    a minute for one symbol and not the other; zipping positionally would pair
    mismatched prices from that point on and corrupt every later ratio.
    """
    df0, df1 = align_traces(df0, df1)
    n = min(len(df0), len(df1)) // CANDLES_PER_DAY * CANDLES_PER_DAY
    ratio = df0["close"].to_numpy()[:n] / df1["close"].to_numpy()[:n]
    starts = df0["open_time"].to_numpy()[:n]

    rows = []
    for i in range(0, n, CANDLES_PER_DAY):
        chunk = ratio[i : i + CANDLES_PER_DAY]
        rows.append(
            {
                "start_ms": int(starts[i]),
                "end_ms": int(starts[i]) + DAY_MS,
                "volatility": realised_volatility(pd.Series(chunk)),
            }
        )
    return pd.DataFrame(rows)


def select_windows(segments: pd.DataFrame, per_tercile: int = 8) -> pd.DataFrame:
    """Sort by volatility, cut into terciles, take `per_tercile` evenly from each.

    Even spacing by date within a tercile avoids clustering the sample in one
    part of the year, and keeps the choice mechanical: no manual picking and no
    random seed.
    """
    ordered = segments.sort_values("volatility").reset_index(drop=True)
    bounds = np.array_split(np.arange(len(ordered)), 3)

    picked = []
    for regime, index_block in zip(REGIMES, bounds):
        block = ordered.iloc[index_block].sort_values("start_ms").reset_index(drop=True)
        if len(block) <= per_tercile:
            chosen = block
        else:
            step = len(block) / per_tercile
            positions = [int(i * step) for i in range(per_tercile)]
            chosen = block.iloc[positions]
        chosen = chosen.assign(regime=regime)
        picked.append(chosen)

    return pd.concat(picked, ignore_index=True)
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_windows.py -v` Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add experiments/windows.py tests/test_windows.py
git commit -m "feat: add volatility stratified window selection"
```

---

### Task 2: Run manifest

**Files:**

- Create: `experiments/manifest.py`
- Create: `tests/test_manifest.py`

**Interfaces:**

- Produces:
  - `build_manifest(**fields) -> dict` carrying `C_theta`, `D`, `P0`, `L0`, `W`,
    `S`, and `input_checksum`.
  - `write_manifest(path: Path, manifest: dict) -> None`
  - `matches(path: Path, manifest: dict) -> bool` — true when a completed run
    already used exactly this configuration.
  - `submodule_revisions(contracts_dir: Path) -> dict[str, str]`

- [ ] **Step 1: Write the failing tests**

```python
import json

import pytest

from experiments.manifest import build_manifest, matches, write_manifest


def _fields():
    return dict(
        policy="ABHook",
        policy_params={"K": 6000, "A": 100},
        submodules={"v4-core": "d153b04"},
        solc="0.8.30",
        p0_sqrt_price_x96=79228162514264337593543950336,
        l0_token0=1,
        l0_token1=2,
        window={"start_ms": 0, "end_ms": 86_400_000, "regime": "low"},
        arbitrageur={"gas_price_wei": 20_000_000_000, "size_dependent": False},
        input_checksum="abc123",
    )


def test_manifest_carries_every_manifest_field():
    m = build_manifest(**_fields())
    for key in ("C_theta", "D", "P0", "L0", "W", "S", "input_checksum"):
        assert key in m, f"Eq. (9) field {key} missing"


def test_matches_is_true_for_an_identical_configuration(tmp_path):
    m = build_manifest(**_fields())
    path = tmp_path / "run.manifest.json"
    write_manifest(path, m)
    assert matches(path, m)


def test_matches_is_false_when_any_field_differs(tmp_path):
    m = build_manifest(**_fields())
    path = tmp_path / "run.manifest.json"
    write_manifest(path, m)

    changed = _fields()
    changed["arbitrageur"] = {"gas_price_wei": 5_000_000_000, "size_dependent": False}
    assert not matches(path, build_manifest(**changed))


def test_matches_is_false_when_no_manifest_exists(tmp_path):
    assert not matches(tmp_path / "absent.json", build_manifest(**_fields()))
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_manifest.py -v` Expected: FAIL — module missing.

- [ ] **Step 3: Implement**

`build_manifest` maps the arguments onto the Eq. (9) names. `matches` compares
the parsed JSON to the candidate dict for exact equality; any difference means
the run must be redone. `submodule_revisions` shells out to
`git submodule status` in `contracts/` and returns a name→SHA map.

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_manifest.py -v` Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add experiments/manifest.py tests/test_manifest.py
git commit -m "feat: add reproducibility manifest per run"
```

---

### Task 3: Matrix driver

**Files:**

- Create: `experiments/matrix.py`
- Create: `tests/test_matrix.py`

**Interfaces:**

- Consumes: `run_one` from the foundation plan, `select_windows`,
  `build_manifest`, `matches`.
- Produces:
  - `enumerate_runs(...) -> list[RunSpec]` where `RunSpec` is a dataclass with
    `policy`, `fee_pips`, `pair`, `window`, `gas_price_wei`, `address_mode`.
  - `execute(specs, results_dir, runner=run_one) -> pd.DataFrame`

- [ ] **Step 1: Write the failing tests**

```python
import pandas as pd

from experiments.matrix import enumerate_runs, execute


def test_matrix_has_the_expected_cardinality():
    specs = enumerate_runs()
    assert len(specs) == 4752, "11 configs x 2 modes x 3 pairs x 24 windows x 3 gas"


def test_every_axis_is_fully_covered():
    specs = enumerate_runs()
    assert len({s.gas_price_wei for s in specs}) == 3
    assert len({s.address_mode for s in specs}) == 2
    assert len({s.pair for s in specs}) == 3
    assert len({(s.policy, s.fee_pips) for s in specs}) == 11


def test_completed_runs_are_skipped(tmp_path):
    calls = []

    def runner(spec):
        calls.append(spec)
        return {"trade_count": 1, "conservation_error_token0": 0.0}

    specs = enumerate_runs()[:3]
    execute(specs, tmp_path, runner=runner)
    first_pass = len(calls)
    execute(specs, tmp_path, runner=runner)

    assert len(calls) == first_pass, "a matching manifest must short-circuit"


def test_a_failing_run_does_not_abort_the_matrix(tmp_path):
    def runner(spec):
        if spec.pair[0] == "USDCUSDT":
            raise RuntimeError("no flow")
        return {"trade_count": 1, "conservation_error_token0": 0.0}

    frame = execute(enumerate_runs()[:50], tmp_path, runner=runner)
    assert "error" in frame.columns
    assert frame["error"].notna().any()
    assert frame["error"].isna().any(), "healthy runs still recorded"
```

The last test matters because the stable pair may legitimately produce nothing;
the matrix must record that and carry on rather than stop.

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_matrix.py -v` Expected: FAIL — module missing.

- [ ] **Step 3: Implement**

`enumerate_runs` takes the product of the axes declared in Global Constraints.
`execute` iterates, builds the manifest, skips when `matches`, otherwise calls
the runner, writes the manifest on success, and records the exception text in an
`error` column on failure. Progress is logged per run so a four-hour matrix is
observable.

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_matrix.py -v` Expected: 4 passed.

- [ ] **Step 5: Smoke the driver on a two-run slice**

```bash
uv run python -c "
from experiments.matrix import enumerate_runs, execute
from pathlib import Path
frame = execute(enumerate_runs()[:2], Path('results'))
print(frame[['policy','pair','trade_count','conservation_error_token0']])
"
```

Expected: two rows, closure error near zero.

- [ ] **Step 6: Commit**

```bash
git add experiments/matrix.py tests/test_matrix.py
git commit -m "feat: add resumable run matrix driver"
```

---

### Task 4: Aggregation

**Files:**

- Create: `experiments/aggregate.py`
- Create: `tests/test_aggregate.py`

**Interfaces:**

- Produces:
  - `load_results(results_dir: Path) -> pd.DataFrame` — one row per run, joined
    with its manifest.
  - `by_regime(frame) -> pd.DataFrame` — mean and standard error per (policy,
    regime, gas scenario).
  - `BASELINE_POLICY = "MyHook"` — the baseline is identified by policy name,
    not inferred. Every other policy is compared against it.
  - `paired_against_baseline(frame, baseline_fee_pips=3000) -> pd.DataFrame` —
    per-window difference against the static baseline at the given level. `3000`
    pips is the default because it is the level `ABHook`'s constant-sum `K/2`
    coincides with, making that comparison exactly paired; other policies are
    additionally reported against all four levels.

- [ ] **Step 1: Write the failing tests**

```python
import pandas as pd
import pytest

from experiments.aggregate import by_regime, paired_against_baseline


def _frame():
    rows = []
    for policy in ("ABHook", "MyHook"):
        for regime in ("low", "mid", "high"):
            for window in range(4):
                rows.append(
                    {
                        "policy": policy,
                        "fee_pips": 3000,
                        "regime": regime,
                        "window_start_ms": window,
                        "gas_price_wei": 20_000_000_000,
                        "net_result": 10.0 if policy == "ABHook" else 8.0,
                        "retained_volume": 100.0,
                        "trade_count": 5,
                    }
                )
    return pd.DataFrame(rows)


def test_by_regime_reports_a_standard_error():
    out = by_regime(_frame())
    assert {"net_result_mean", "net_result_sem"} <= set(out.columns)
    assert len(out) == 2 * 3


def test_pairing_is_per_window_not_per_average():
    """Windows differ wildly; comparing averages hides the pairing."""
    out = paired_against_baseline(_frame())
    assert (out["net_result_delta"] == pytest.approx(2.0)).all()


def test_baseline_rows_are_excluded_from_the_comparison():
    out = paired_against_baseline(_frame())
    assert "MyHook" not in set(out["policy"])


def test_retained_volume_travels_with_every_metric():
    out = by_regime(_frame())
    assert "retained_volume_mean" in out.columns, (
        "spec 12.1: retained volume must be reported beside the headline metric"
    )
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_aggregate.py -v` Expected: FAIL — module missing.

- [ ] **Step 3: Implement**

`load_results` walks `results/*.manifest.json`, reads the sibling metrics JSON,
and flattens both into one row. `by_regime` groups and aggregates mean and
standard error. `paired_against_baseline` joins each policy row to the baseline
row sharing pair, window, gas scenario, and address mode, then differences them
— pairing per window, because window-to-window variation dwarfs the effect being
measured.

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_aggregate.py -v` Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add experiments/aggregate.py tests/test_aggregate.py
git commit -m "feat: aggregate runs by regime with per-window pairing"
```

---

### Task 5: Statistics — Wilcoxon per comparison, Benjamini–Hochberg across the family

Implements the pre-registered analysis plan of spec §12.1. No single primary
hypothesis: the whole family of comparisons is tested, then the false discovery
rate is controlled across it.

**Files:**

- Create: `experiments/stats.py`, `tests/test_stats.py`

**Interfaces:**

- Consumes: `paired_against_baseline` from Task 4.
- Produces:
  - `wilcoxon_paired(deltas) -> dict` with `p`, `median`, `win_rate`, `n`
  - `benjamini_hochberg(pvalues, q=0.05) -> list[bool]`
  - `analyse(frame, q=0.05) -> pd.DataFrame` — one row per comparison with the
    effect size and the FDR-adjusted flag.

- [ ] **Step 1: Add scipy**

```bash
uv add scipy
```

- [ ] **Step 2: Write the failing tests**

```python
import numpy as np
import pandas as pd
import pytest

from experiments.stats import benjamini_hochberg, wilcoxon_paired


def test_all_positive_differences_are_detected():
    """Eight wins out of eight: a t-test would miss this because of the outlier,
    Wilcoxon must not. See learning/statistics-for-our-experiment.md section 8."""
    r = wilcoxon_paired([2, 1, 3, 2, 1, 2, 1, 400])
    assert r["p"] < 0.05
    assert r["win_rate"] == 1.0
    assert r["n"] == 8


def test_effect_size_travels_with_the_p_value():
    r = wilcoxon_paired([2, 1, 3, 2, 1, 2, 1, 400])
    assert "median" in r, "a significance flag without an effect size is banned"
    assert r["median"] == pytest.approx(2.0)


def test_symmetric_noise_is_not_detected():
    r = wilcoxon_paired([1, -1, 2, -2, 3, -3, 4, -4])
    assert r["p"] > 0.05


def test_bh_worked_example():
    """Spec 12.1 example: naive alpha declares 4, Bonferroni 1, BH 2."""
    ps = [0.001, 0.008, 0.02, 0.04, 0.13, 0.21, 0.33, 0.48, 0.62, 0.91]
    flags = benjamini_hochberg(ps, q=0.05)
    assert sum(flags) == 2
    assert flags[0] and flags[1]


def test_bh_step_up_admits_a_value_that_failed_its_own_threshold():
    ps = [0.001, 0.012, 0.013, 0.019, 0.30, 0.4, 0.5, 0.6, 0.7, 0.8]
    flags = benjamini_hochberg(ps, q=0.05)
    assert sum(flags) == 4
    assert flags[1], "p=0.012 rides in on the largest passing index"


def test_bh_is_stricter_than_the_naive_threshold():
    ps = [0.04] * 10
    assert sum(benjamini_hochberg(ps, q=0.05)) == 0
    assert sum(p <= 0.05 for p in ps) == 10
```

- [ ] **Step 3: Run to verify failure**

Run: `uv run pytest tests/test_stats.py -v` Expected: FAIL — module missing.

- [ ] **Step 4: Implement**

`wilcoxon_paired` wraps `scipy.stats.wilcoxon(deltas, alternative="two-sided")`
and returns the p-value together with the median difference, the fraction of
positive differences, and `n`. It returns `p = 1.0` when every difference is
zero, which `scipy` would otherwise raise on.

`benjamini_hochberg` sorts the p-values, compares each to `(i/m)·q`, finds the
largest passing index, and flags every entry up to it — the step-up rule the
tests pin.

`analyse` applies the first to each comparison and the second across the whole
family, returning one row per comparison carrying `policy`, `stratum`, `n`,
`median_usdt`, `median_apr_pct`, `win_rate`, `p`, `significant_fdr`.

- [ ] **Step 5: Run to verify pass**

Run: `uv run pytest tests/test_stats.py -v` Expected: 6 passed.

- [ ] **Step 6: Commit**

```bash
git add experiments/stats.py tests/test_stats.py pyproject.toml uv.lock
git commit -m "feat: add wilcoxon tests with benjamini-hochberg fdr control"
```

---

### Task 6: Figures

**Files:**

- Create: `experiments/figures.py`
- Create: `tests/test_figures.py`

**Interfaces:**

- Produces: `net_result_by_regime(frame, out: Path)`,
  `frontier(frame, out: Path)`, `gas_breakeven(frame, out: Path)`,
  `fee_distribution(frame, out: Path)` — each writing a PDF.

- [ ] **Step 1: Write the failing test**

```python
from pathlib import Path

from experiments.figures import frontier, gas_breakeven, net_result_by_regime


def test_each_figure_writes_a_nonempty_pdf(tmp_path, monkeypatch):
    import matplotlib

    matplotlib.use("Agg")

    from tests.test_aggregate import _frame

    for fn, name in (
        (net_result_by_regime, "regime"),
        (frontier, "frontier"),
        (gas_breakeven, "gas"),
    ):
        out = tmp_path / f"{name}.pdf"
        fn(_frame(), out)
        assert out.exists() and out.stat().st_size > 0
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_figures.py -v` Expected: FAIL — module missing.

- [ ] **Step 3: Implement**

Four figures, all vector PDF for the paper:

- **net result by regime** — grouped bars, policy × regime, error bars from the
  standard error. The headline.
- **frontier** — net result against retained volume, static levels forming one
  curve and each dynamic policy a point. Shows whether a policy dominates or
  merely trades volume for fees.
- **gas break-even** — net result advantage over baseline against gas price, one
  line per policy. The crossing of zero is the substantive number.
- **fee distribution** — histogram of applied fees per policy, demonstrating
  that dynamic policies actually move within the box rather than sitting at a
  bound.

Axis label for anything in fee units reads "hundredths of a basis point", or
values are divided by 100 and labelled "basis points" — never the mislabelling
the paper's Fig. 5 currently carries.

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_figures.py -v` Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add experiments/figures.py tests/test_figures.py
git commit -m "feat: add result figures for the paper"
```

---

### Task 7: Golden window test

Spec §14.4. With the full pipeline in place, pin one complete window so that any
later change that shifts results is noticed.

**Files:**

- Create: `tests/test_golden.py`
- Create: `tests/golden/eth-shib-2024-01-01-myhook-3000.json`

**Interfaces:**

- Consumes: `run_one`.

- [ ] **Step 1: Generate the golden file**

```bash
uv run python -c "
import json
from pathlib import Path
from experiments.run_one import run_one
m = run_one('MyHook', 'ETHUSDT', 'SHIBUSDT', 1704067200000, 1704067200000 + 1440*60_000)
Path('tests/golden').mkdir(parents=True, exist_ok=True)
Path('tests/golden/eth-shib-2024-01-01-myhook-3000.json').write_text(json.dumps(m, indent=2))
print(json.dumps(m, indent=2))
"
```

Inspect the output before pinning it. A golden file recording wrong numbers is
worse than none.

- [ ] **Step 2: Write the test**

```python
import json
from pathlib import Path

import pytest

from experiments.run_one import run_one

GOLDEN = Path("tests/golden/eth-shib-2024-01-01-myhook-3000.json")


@pytest.mark.slow
def test_full_window_reproduces_the_golden_result():
    expected = json.loads(GOLDEN.read_text())
    actual = run_one(
        "MyHook", "ETHUSDT", "SHIBUSDT", 1704067200000, 1704067200000 + 1440 * 60_000
    )

    for key, value in expected.items():
        assert actual[key] == pytest.approx(value, rel=1e-9), f"{key} drifted"
```

- [ ] **Step 3: Register the marker**

Append to `pyproject.toml`:

```toml
markers = ["slow: runs a full replay window through forge"]
```

under the existing `[tool.pytest.ini_options]`.

- [ ] **Step 4: Run**

Run: `uv run pytest tests/test_golden.py -v -m slow` Expected: PASS. Determinism
is a property of the design (spec §7.5), so any tolerance beyond floating-point
noise means something is wrong.

- [ ] **Step 5: Commit**

```bash
git add tests/test_golden.py tests/golden pyproject.toml
git commit -m "test: pin a full replay window as a golden result"
```

---

### Task 8: Execute the matrix

**Files:**

- Create: `results/summary.csv` (committed; the per-run JSONL stays ignored)

- [ ] **Step 1: Fetch every trace first**

```bash
uv run python -c "
from experiments.matrix import enumerate_runs
from experiments.binance import fetch_klines
from pathlib import Path
pairs = {s.pair for s in enumerate_runs()}
symbols = {sym for pair in pairs for sym in pair} | {'ETHUSDT'}
for sym in sorted(symbols):
    fetch_klines(sym, 1704067200000, 1735689600000, Path('data'))
    print('cached', sym)
"
```

Fetching separately keeps the matrix itself offline and therefore reproducible.
This works because the cache is keyed by calendar month (Plan 1, Task 3), so a
whole-year prefetch satisfies every later single-day window request. A cache
keyed on the exact requested range would not, and the matrix would hit the
network once per run.

- [ ] **Step 2: Run the matrix**

```bash
uv run python -c "
from pathlib import Path
from experiments.matrix import enumerate_runs, execute
frame = execute(enumerate_runs(), Path('results'))
frame.to_csv('results/summary.csv', index=False)
print(frame.groupby('policy')['conservation_error_token0'].abs().max())
"
```

Expected: roughly 4 hours. Every closure error near zero. It is resumable —
interrupt and re-run freely.

- [ ] **Step 2a: Confirm the matrix ran offline**

```bash
uv run python -c "
from pathlib import Path
n = len(list(Path('data').glob('*.parquet')))
print(f'{n} cached months')
assert n > 0, 'the prefetch produced nothing'
"
```

Re-running any single window must not add parquet files. If it does, the cache
key is wrong and the matrix has been fetching from Binance throughout, which
breaks reproducibility.

- [ ] **Step 3: Verify the invariant held everywhere**

```bash
uv run python -c "
import pandas as pd
f = pd.read_csv('results/summary.csv')
bad = f[(f['conservation_error_token0'].abs() > 1e-6)
        | (f['conservation_error_token1'].abs() > 1e-6)]
print(f'{len(bad)} runs violate token conservation')
assert bad.empty, bad[['policy','pair','window_start_ms']].head(20)
print(f[f[\"trade_count\"] == 0].groupby([\"pair\"]).size())
"
```

A non-empty violation set blocks the analysis. Zero-trade runs are reported, not
treated as errors — the stable pair is expected to show up here.

- [ ] **Step 4: Produce the figures**

```bash
uv run python -c "
import pandas as pd
from pathlib import Path
from experiments.aggregate import by_regime, paired_against_baseline
from experiments.figures import net_result_by_regime, frontier, gas_breakeven, fee_distribution
f = pd.read_csv('results/summary.csv')
Path('paper/Image').mkdir(parents=True, exist_ok=True)
net_result_by_regime(f, Path('paper/Image/net_result_by_regime.pdf'))
frontier(f, Path('paper/Image/frontier.pdf'))
gas_breakeven(f, Path('paper/Image/gas_breakeven.pdf'))
fee_distribution(f, Path('paper/Image/fee_distribution.pdf'))
"
```

- [ ] **Step 5: Commit the summary and figures**

```bash
git add -f results/summary.csv
git add paper/Image
git commit -m "feat: run the full experiment matrix and produce figures"
```

---

## Self-Review

**Spec coverage.** §7.2 pairs → Task 3 `enumerate_runs`. §7.3 stratification →
Task 1. §8 gas scenarios → Task 3 axis, Task 5 break-even figure. §9 matrix →
Tasks 3 and 7. §10 manifest → Task 2. §12 metrics → consumed from the foundation
plan; §12.1's retained-volume requirement is enforced by a test in Task 4. §14.1
token conservation → verified across the whole matrix in Task 8 Step 3. §14.4
golden test → Task 7. §15 stable-pair risk → Task 3's failure-tolerance test and
Task 8 Step 3's zero-trade report, neither of which special-cases the pair. §16
headline metric → deliberately not decided here; Task 4 computes every candidate
so the choice is a query, not a re-run.

**Placeholders.** Tasks 2–5 Step 3 describe implementations in prose while the
tests carry the exact contract. This is deliberate for modules whose bodies are
mechanical given their tests, and each names the file, the inputs, and the
required behaviour. Task 5 additionally specifies each figure's axes and the
fee-unit labelling rule.

**Type consistency.** `RunSpec` fields (`policy`, `fee_pips`, `pair`, `window`,
`gas_price_wei`, `address_mode`) match between `enumerate_runs`, `execute`, and
the manifest built in Task 2. `select_windows` emits `regime` with exactly the
values `by_regime` groups on. `run_one`'s returned keys, defined in the
foundation plan, are what `load_results` flattens and what the golden test
compares.
