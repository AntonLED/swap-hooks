# Swap Hooks Experiments

Experiment code for **"A Configurable Dynamic-Fee Hook Framework for Uniswap v4
Liquidity Pools"** (ICBC 2026): a replay harness that runs dynamic-fee hook
policies and static baselines over identical 2024 market histories with modelled
informed and uninformed flow, and a paired statistical evaluation of the LP
outcome.

The full description — architecture, trader model, parameters, metrics and
results — is `docs/reports/2026-08-12-framework-report.md` (Russian working copy
beside it).

> this repo uses
> [conventional commits](https://gist.github.com/qoomon/5dfcdf8eec66a051ecd85625518cfd13)

### Install and Setup

you have to install:

- python package manager: [uv](https://docs.astral.sh/uv/);
- python linter and formatter: [ruff](https://github.com/astral-sh/ruff);
- node js for code linting and formatting:
  [node](https://nodejs.org/en/download);
- smart-contracts framework:
  [foundry](https://www.getfoundry.sh/introduction/installation);

than run:

1. `npm install` to install all the node stuff;
2. `uv venv` to create a python virtual environment;
3. `uv sync` to sync all deps;

### Dev Guide

- _Format_: via `npm run format`;
- _Add dependency_: via `uv add <DEP_NAME>`;
- _Mirror pip_: `pip ...` is equivalent to `uv pip ...`;

### Run Simulations

A simulation replays a real market window against a pool deployed on a local
EVM, one Forge test per cell, and scores the liquidity provider against holding
the tokens. This is the path from a clean checkout to numbers.

#### 0. Before the first run

```bash
git submodule update --init --recursive   # pinned revisions; do NOT update them
uv sync
cd contracts && forge build && cd ..      # first build takes minutes (via_ir)
```

**Do not update the submodules.** The current tip of `uniswap-hooks` changed
`BaseHook`'s constructor and made `poolManager` a public immutable; every policy
here is written against the older API and **nothing compiles** against the tip.
The pinned commits are field `D` of the reproducibility manifest.

Market data is cached under `data/`, keyed by calendar month. The first
full-year fetch takes about fifteen minutes; after that every run is offline.
**If a window re-fetches, the cache key is wrong** — that breaks
reproducibility, so investigate rather than wait it out.

Check it works — this is also the fastest way to find a broken toolchain:

```bash
cd contracts && forge test && cd ..      # 110 tests
uv run pytest -q                         # ~340 tests
```

#### 1. A single cell, to see the machinery

One policy, one pair, one day, with the two-flow model. Takes seconds and writes
a per-swap event log.

```bash
uv run python -c "
from pathlib import Path
from experiments.run_one import run_one
m = run_one('DAHook', 'ETHUSDT', 'SHIBUSDT',
            1704067200000, 1704067200000 + 1440*60_000,
            uu_mode='discrete',
            work_dir=Path('.work/probe'),
            results_dir=Path('.work/probe'))   # <- see the warning below
print({k: round(v, 2) for k, v in m.items() if isinstance(v, float)})
"
```

> **Always pass `results_dir` on an ad-hoc call.** Without it `run_one` writes
> its event log to the shared results directory under a name built from the
> run's axes — exactly the name the matrix cell for those axes uses. The probe
> silently overwrites a matrix trace, the cell's manifest still matches so
> nothing recomputes, and every trace-reading analysis then reads the probe.
> This has happened in this repo.
>
> `uu_mode='discrete'` is the experiment's mode; omitting it gives
> arbitrage-only flow — a different (retired) experiment, not a lighter version
> of this one.

#### 2. The matrix, at five operating points

The experiment is one matrix — 9 policy configurations (4 hooks, the
recalibrated `VolatilityHook`, 4 static baselines) × 3 pairs × 72 day-windows ×
3 gas scenarios = 5,832 cells — run at five retail scales κ. Each operating
point writes to its own directory and is never pooled with another.

```bash
uv run python run_matrix.py --uu                     # κ = 1.0 -> results-uu/
uv run python run_matrix.py --uu --uu-turnover 0.1   # -> results-uu/turnover-0.1/
# likewise 0.03, 0.3, 3.0
```

Useful while developing:

```bash
uv run python run_matrix.py --uu --limit 48          # smoke run
uv run python run_matrix.py --uu --pair ETH/SHIB     # one pair; repeatable
uv run python run_matrix.py --uu --policy DAHook     # one policy; repeatable
uv run python run_matrix.py --uu --workers 8         # default is cores-1
```

**Interrupting is safe.** Every completed cell writes a reproducibility manifest
and a rerun skips any cell whose manifest matches. Change a contract, a compiler
version or an input, and exactly the affected cells recompute — because their
numbers would otherwise answer a different question.

Expect roughly an hour on twelve cores per operating point. The runner reads
available memory and caps its own worker count before starting; override with
`--mb-per-worker`, or `--no-memory-guard` to disable it.

#### 3. Robustness and calibration

```bash
uv run python -m experiments.seed_robustness                # 5 seeds, κ = 1.0
uv run python -m experiments.seed_robustness --turnover 0.1 # 5 seeds, κ = 0.1
```

**After changing any hook, recalibrate gas:**

```bash
uv run python -m experiments.calibrate_gas
```

It writes `experiments/gas_estimates.json` — median gas per swap, per policy,
measured in the EVM, plus the 21,000 intrinsic cost. That figure is the
arbitrageur's entry threshold and part of the retail participation decision, so
a stale one silently changes which trades happen. It is per policy because an
oracle-reading hook costs roughly 1.5× a constant-fee one, and that gap is what
the gas axis measures.

#### 4. Figures and analysis

Notebooks 07/08 report one operating point at a time, selected by `UU_CONFIG`;
standalone scripts draw the cross-cutting figures. See `analysis/README.md` for
the full table.

```bash
uv run jupyter lab                                   # then open analysis/

UU_CONFIG=informed uv run jupyter nbconvert --to notebook --execute \
    --inplace analysis/07-uu-main-results.ipynb

UU_CONFIG=headline uv run python analysis/draw_regime_gas_grid.py
uv run python analysis/draw_kappa_trend.py           # needs all five matrices
uv run python analysis/draw_gas_costs.py
uv run python analysis/draw_uu_profile.py
```

Every figure lands in `paper/Image/` with a CSV of its own numbers beside it and
the operating point stamped on its face.

#### 5. What to check in the output

| check                  | expected                                                                                                             |
| ---------------------- | -------------------------------------------------------------------------------------------------------------------- |
| `errors: N`            | **0**. A failed cell is recorded and the sweep continues, so this is never implied by the run finishing.             |
| `conservation_error_*` | ~1e-16. It once caught a silent int64 overflow that would have corrupted every figure without anything failing.      |
| zero-trade cells       | a handful on `USDC/USDT` at low κ; it held too tight in 2024 for arbitrage to clear its gas. A finding, not a fault. |

> A results directory must hold cells of one harness revision unless a
> differential check has licensed the mix — manifests carry the source hash, so
> `experiments.manifest.models_in()` will show a blend.

#### 6. Where the output lands

`<run>` is `results-uu/` (κ = 1.0) or `results-uu/turnover-<κ>/`.

| path                            | what                                                                |
| ------------------------------- | ------------------------------------------------------------------- |
| `<run>/matrix/*.metrics.json`   | one cell's metrics                                                  |
| `<run>/matrix/*.manifest.json`  | its manifest, and the resume key                                    |
| `<run>/*.jsonl`                 | the per-swap event log, one file per cell                           |
| `<run>/summary.csv`             | every cell, one row each                                            |
| `<run>/analysis-*.csv`          | per-stratum medians, bootstrap CIs (and the classical test columns) |
| `<run>/headline-*.csv`          | one row per policy: median and interval                             |
| `paper/Image/uu_*.pdf`          | headline figures                                                    |
| `paper/Image/uu_t01_*.pdf` etc. | the same figures at the other operating points                      |
| `paper/Image/*.csv`             | the table view behind each figure                                   |

### Useful Links

- `docs/reports/2026-08-12-framework-report.md` — the complete description:
  model, parameters interpreted, methodology, results
- `analysis/README.md` — the notebooks and figure scripts
- `docs/superpowers/specs/` — the dated pre-registrations and the main.tex
  integration plan (`paper-edits-required-2026-08-12.md`)
- `docs/superpowers/plans/PROGRESS.md` — the running project log
