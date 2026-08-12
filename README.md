# Swap Hooks Experiments

> this repo uses
> [conventional commits](https://gist.github.com/qoomon/5dfcdf8eec66a051ecd85625518cfd13)

### Install and Setup

you have to install:

- python package manager: [uv](https://docs.astral.sh/uv/);
- python linter and formatter: [ruff](https://github.com/astral-sh/ruff) ;
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

Check it works - this is also the fastest way to find a broken toolchain:

```bash
cd contracts && forge test && cd ..
uv run pytest -q
```

#### 1. A single cell, to see the machinery

One policy, one pair, one day, with the paper's two-flow model. Takes seconds
and writes a per-swap event log.

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
> its event log to `results/` under a name built from the run's axes — which is
> exactly the name the matrix cell for those axes uses. The probe silently
> overwrites a matrix trace, the cell's manifest still matches so nothing
> recomputes, and every trace-reading analysis then reads the probe. This has
> happened twice in this repo, once destroying a whole experiment's traces.
>
> Omit `uu_mode` and you get arbitrage-only flow (`uu_volume` will be 0) — a
> different experiment, not a lighter version of this one.

#### 2. The matrix

Two experiments, and they never write to each other's directory.

```bash
# Arbitrage-only flow -> results/          15,552 cells
uv run python run_matrix.py

# Arbitrage + uninformed-user flow -> results-uu/    7,776 cells  (the paper's)
uv run python run_matrix.py --uu

# The second operating point -> results-uu/turnover-0.1/
uv run python run_matrix.py --uu --uu-turnover 0.1
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

Expect roughly an hour on twelve cores for the UU matrix. The runner reads
available memory and caps its own worker count before starting — a single replay
peaks around 290 MB. Override with `--mb-per-worker`, or `--no-memory-guard` to
disable it; the guard exists because the absence of one exhausted a machine.

#### 3. Robustness sweeps

Each has its own pre-registration and its own results directory, and none of
them may be merged into the matrix.

```bash
uv run python -m experiments.kappa_sensitivity              # the retail scale
uv run python -m experiments.seed_robustness                # 5 seeds, κ = 1.0
uv run python -m experiments.seed_robustness --turnover 0.1 # 5 seeds, κ = 0.1
uv run python -m experiments.sensitivity                    # captureShare
```

**After changing any hook, recalibrate gas:**

```bash
uv run python -m experiments.calibrate_gas
```

It writes `experiments/gas_estimates.json` — median gas per swap, per policy,
plus the 21,000 intrinsic cost. That figure is the arbitrageur's entry
threshold, so a stale one silently changes which trades happen. It is per policy
because an oracle-reading hook costs roughly twice a constant-fee one, and that
gap is what the gas axis measures.

#### 4. Figures and analysis

Notebooks, never scripts — so redrawing a figure never costs a replay, and a
figure cannot go stale behind a flag nobody passes.

```bash
uv run jupyter lab                     # then open analysis/

# or headlessly, in place:
uv run jupyter nbconvert --to notebook --execute --inplace analysis/*.ipynb
```

Notebooks 07, 08 and 10 report **one operating point at a time**, selected by an
environment variable:

```bash
UU_CONFIG=informed uv run jupyter nbconvert --to notebook --execute \
    --inplace analysis/07-uu-main-results.ipynb
```

See `analysis/README.md` for what each notebook reads and writes.

#### 5. What to check in the output

| check                  | expected                                                                                                                            |
| ---------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| `errors: N`            | **0**. A failed cell is recorded and the sweep continues, so this is never implied by the run finishing.                            |
| `conservation_error_*` | **0 violations**, asserted. It once caught a silent int64 overflow that would have corrupted every figure without anything failing. |
| `contracts revision`   | one hash. Two means a results directory holds two different models — the analysis refuses to read it.                               |
| zero-trade cells       | expected on `USDC/USDT`; it held too tight in 2024 for arbitrage to clear its gas. A finding, not a fault.                          |

#### 6. Where the output lands

`<run>` is `results/` (arbitrage-only), `results-uu/` (the headline) or
`results-uu/turnover-0.1/` (the second operating point).

| path                           | what                                      |
| ------------------------------ | ----------------------------------------- |
| `<run>/matrix/*.metrics.json`  | one cell's metrics                        |
| `<run>/matrix/*.manifest.json` | its manifest, and the resume key          |
| `<run>/*.jsonl`                | the per-swap event log, one file per cell |
| `<run>/summary.csv`            | every cell, one row each                  |
| `<run>/analysis-*.csv`         | Wilcoxon + bootstrap CI + FDR per stratum |
| `<run>/headline-*.csv`         | one row per policy: median and interval   |
| `paper/Image/uu_*.pdf`         | headline figures, drawn by the notebooks  |
| `paper/Image/uu_t01_*.pdf`     | the same figures at the second point      |
| `paper/Image/*.csv`            | the table view behind each figure         |

**A matrix directory must hold exactly one model.**
`manifest.assert_one_model()` checks that every manifest in it agrees on the
contract source hash, and the analysis calls it before reading anything.
`results-uu/matrix/` was once found holding the current matrix and a withdrawn
one side by side, on which a directory load returned 15,552 cells across two
models and `DAHook`'s median read 16,816 against a true 12,240.

### Useful Links

- `analysis/README.md` — the notebooks, and which experiment each reports
- `learning/what-we-ran-and-what-it-says.md` — what exists and what each run may
  claim
- `learning/the-model-end-to-end.md` — the model, with the parameter table
- `docs/superpowers/specs/` — the pre-registrations
