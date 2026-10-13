# Swap Hooks Experiments

> this repo uses
> [conventional commits](https://gist.github.com/qoomon/5dfcdf8eec66a051ecd85625518cfd13)

Code for **"A Reproducible Evaluation Framework for Adaptive Fee Policies in
Uniswap v4"** (IEEE Blockchain 2026): the dynamic-fee hooks, their deployment on
a local Uniswap v4 pool, a replay harness that runs every policy and the static
baselines over identical 2024 market histories with modelled informed and
uninformed flow, and the paired statistical evaluation of the LP outcome.

## Architecture: three layers

The code follows the three layers described in the paper.

### 1. Contract layer — `contracts/src/`

The dynamic-fee hooks, built on OpenZeppelin's `uniswap-hooks`
(`BaseOverrideFee`). Each hook returns its fee from `beforeSwap` and updates its
own state after a swap.

| file                                                 | role                                                         |
| ---------------------------------------------------- | ------------------------------------------------------------ |
| `BAHook.sol`                                         | external price direction, updated once per block             |
| `DAHook.sol`                                         | executed trade direction, updated every trade                |
| `ABHook.sol`                                         | the pool's own price movement, updated every trade           |
| `VolatilityHook.sol`                                 | EMA volatility of the external ratio, updated once per block |
| `MEVChargeHook.sol`                                  | base fee plus a trade-size surcharge                         |
| `MyHook.sol`                                         | constant fee: the static 5/30/60/100 bps baselines           |
| `CustomBaseHook.sol`, `interfaces/`                  | shared fee interface                                         |
| `libraries/ArbMath.sol`, `UUMath.sol`, `Welford.sol` | arbitrage optimum, user acceptance model, online variance    |

### 2. Deployment layer — `contracts/test/utils/`

Deploys everything a hook needs on a local EVM.

| file                      | role                                                                                                                     |
| ------------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| `Deployers.sol`           | Permit2, `PoolManager`, `PositionManager`, the v4 router, mock ERC-20 tokens (canonical deployments off the local chain) |
| `HookTest.sol`            | Chainlink-compatible mock price feeds, the hook at an address that carries its permission flags, pool initialization     |
| `libraries/HookFlags.sol` | the permission bitmap of every hook                                                                                      |
| `libraries/EasyPosm.sol`  | minting liquidity positions                                                                                              |

The hook's permissions are checked at deployment (`BaseHook` validates its
address against `getHookPermissions()`), and
`contracts/test/HookPermissions.t.sol` tests them for every hook.

### 3. Experiment layer — `contracts/test/Replay.t.sol`, `experiments/`, `analysis/`

| path                                                   | role                                                                                                                                   |
| ------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------- |
| `contracts/test/Replay.t.sol`                          | the replay harness: one day of one-minute candles against one policy, ordinary users and a gas-aware arbitrageur, a per-swap event log |
| `experiments/binance.py`, `windows.py`                 | market data and the volatility-stratified day windows                                                                                  |
| `experiments/uu.py`                                    | the ordinary-user trade trace                                                                                                          |
| `experiments/run_one.py`, `matrix.py`, `run_matrix.py` | one cell, and the full factorial matrix                                                                                                |
| `experiments/manifest.py`                              | the reproducibility manifest of every cell                                                                                             |
| `experiments/calibrate_gas.py`                         | per-policy gas measured in the EVM                                                                                                     |
| `experiments/metrics.py`, `aggregate.py`, `stats.py`   | LP outcome, paired differences, bootstrap intervals                                                                                    |
| `experiments/seed_robustness.py`                       | the seed check                                                                                                                         |
| `analysis/`                                            | notebooks and the scripts that draw the paper figures                                                                                  |

### Install and Setup

You have to install:

- python package manager: [uv](https://docs.astral.sh/uv/);
- python linter and formatter: [ruff](https://github.com/astral-sh/ruff);
- node js for code linting and formatting:
  [node](https://nodejs.org/en/download);
- smart-contracts framework:
  [foundry](https://www.getfoundry.sh/introduction/installation);

Then run:

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
uv run pytest -q                         # ~360 tests (slow ones excluded)
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

The paper's experiment is one matrix: 9 policy configurations (`BAHook`,
`DAHook`, `ABHook`, `VolatilityHook`, `MEVChargeHook`, and static 5/30/60/100
bps) x 3 pairs x 72 day-windows x 3 gas scenarios = 5'832 cells, run at five
retail scales κ (29,160 cells). Each operating point writes to its own directory
and is never pooled with another.

```bash
uv run python run_matrix.py --uu                      # κ = 1.0 -> results-uu/
uv run python run_matrix.py --uu --uu-turnover 0.1    # -> results-uu/turnover-0.1/
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

The seed appendix re-runs a 24-window subset with seeds 0–4: all six policy
configurations (baseline + five hooks), both volatile pairs, at 5 **and** 20
gwei - the cheap-gas scenario is included because the storm-corner conditional
claims live there. 2'880 cells per operating point. It prints a per-(pair,
policy, gas) sign-stability table and writes `results/sensitivity/seeds.csv` (κ
= 0.1 goes to `results/sensitivity/seeds-turnover-0.1/`); the directory is
gitignored — traces are ~1 GB per point. Seed 0 must reproduce the matching
matrix cells exactly; the 2026-08-14 run did, and every high-volatility, 5 gwei
finding kept its sign at all five seeds. `--policy NAME` runs one more policy
and merges its rows into the existing table. `analysis/draw_seed_forest.py`
draws the result.

**After changing any hook, recalibrate gas:**

```bash
uv run python -m experiments.calibrate_gas
```

It writes `experiments/gas_estimates.json` — median gas per swap, per policy,
measured in the EVM, plus the 21,000 intrinsic cost. That figure is the
arbitrageur's entry threshold and part of the retail participation decision, so
a stale one silently changes which trades happen. It is per policy because an
oracle-reading hook costs roughly 1.5x a constant-fee one, and that gap is what
the gas axis measures.

#### 4. Figures and analysis

Notebooks 07/08 report one operating point at a time, selected by `UU_CONFIG`;
standalone scripts draw the paper figures. For interactive styling there is
`analysis/99-figure-sandbox.ipynb` — every paper figure in its own editable cell
with live (ipympl) rendering; it writes nothing until its `WRITE` flag is
flipped. See `analysis/README.md` for the full table.

```bash
uv run jupyter lab                                   # then open analysis/

UU_CONFIG=informed uv run jupyter nbconvert --to notebook --execute \
    --inplace analysis/07-uu-main-results.ipynb

# the four figures in the paper
uv run python analysis/draw_demand_calibration.py    # Fig. 1  uu_demand_calibration
uv run python analysis/draw_regime_gas_grid_merged.py # Fig. 2  uu_regime_gas_grid (κ = 1 and 0.1)
uv run python analysis/draw_seed_forest.py           # Fig. 3  uu_seed_robustness (needs the seed appendix)
uv run python analysis/draw_kappa_trend.py           # Fig. 4  uu_kappa_trend_high (needs all five matrices)

# per-operating-point and supporting figures
UU_CONFIG=headline uv run python analysis/draw_regime_gas_grid.py   # uu_classic_regime_gas_grid
uv run python analysis/draw_fee_behaviour.py
uv run python analysis/draw_gas_costs.py
uv run python analysis/draw_uu_profile.py
```

Every figure lands in `paper/Image/` with a CSV of its own numbers beside it.
Figures carry no in-figure titles — captions live in the LaTeX — and share one
style, defined once in `experiments/figures.py`: STIX serif (the Times face
IEEEtran uses), a closed pgfplots-style frame with inward ticks, dark blue =
beats the baseline, brick red = loses, grey = interval covers zero. Operating
points are told apart by filename prefix (`uu_`, `uu_t01_`, …).

#### 5. What to check in the output

| check                  | expected                                                                                                                                                                   |
| ---------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `errors: N`            | **0**. A failed cell is recorded and the sweep continues, so this is never implied by the run finishing.                                                                   |
| `conservation_error_*` | ~1e-16. It once caught a silent int64 overflow that would have corrupted every figure without anything failing.                                                            |
| zero-trade cells       | none at κ ≥ 0.3; at κ = 0.03 about 100 (mostly `USDC/USDT`, which held too tight in 2024 for arbitrage to clear its gas) and at κ = 0.1 a handful. A finding, not a fault. |

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

- `analysis/README.md` — the notebooks and figure scripts
- `docs/reports/2026-08-12-framework-report.md` — the full description of the
  model, parameters, and results (Russian copy `.ru.md` beside it)
- `docs/superpowers/specs/` — the dated experiment designs and pre-registrations
- `docs/superpowers/plans/PROGRESS.md` — the running project log
