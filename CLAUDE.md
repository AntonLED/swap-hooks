# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with
code in this repository.

## What this repo is

Experiment code for the paper **"A Reproducible Evaluation Framework for
Adaptive Fee Policies in Uniswap v4"** (paper `#1571326575`, **accepted** at
IEEE-Blockchain 2026 as a full paper; 7–8 pages free, pages 9–10 cost €100
each). Current phase: answering reviewers and preparing camera-ready.

The paper sources live in `paper/`. `paper/main.tex` is the colleague's file —
do not edit it directly; supply text and numbers for them to integrate.
`paper/evaluation-draft.tex` is our standalone draft of the evaluation section.
`paper/Image/` holds every figure the paper uses (PDF + a CSV of its numbers).

The full description of the model, parameters, and results is
`docs/reports/2026-08-12-framework-report.md` (Russian copy `.ru.md` beside it).
Pre-registrations and review notes are in `docs/superpowers/specs/`; the
progress log is `docs/superpowers/plans/PROGRESS.md`.

## What the paper claims

The contribution is a **framework**, with the economic comparison as its case
study: common Solidity hooks (OpenZeppelin `BaseOverrideFee`), permission-aware
deployment, local Uniswap v4 pool in Forge, Chainlink-compatible mock feeds
replaying Binance 2024 1-minute candles, modelled retail + arbitrage flow, and
paired statistics.

The evaluation (run of record):

- 9 policy configurations — `BAHook`, `DAHook`, `ABHook`, `VolatilityHook`,
  `MEVChargeHook`, plus static 5/30/60/100 bps (static = `MyHook`, itself a
  hook) — × 3 pairs (ETH/SHIB, ETH/USDC, USDC/USDT) × 72 one-day windows (24 per
  volatility tercile) × 3 gas prices (5/20/80 gwei) = 5,832 cells per operating
  point; × 5 retail scales κ ∈ {0.03, 0.1, 0.3, 1, 3} = 29,160.
- Pool: 20M USDT basket, 50/50, full-range, opens at the external price; first
  60 of 1,440 candles are warm-up. Fee box [1, 100] bps for every policy.
- Every comparison is paired against static 30 bps on the same window, pair,
  gas, κ, and seed; median paired difference, 95% percentile bootstrap (10,000
  resamples), cell-first aggregation (headline = 18 volatile-pair strata).
- LP metric: `LPNet = R_f − IL` against holding, marked at end-of-window prices.
- Gas is **measured** in the EVM (static 76k; hooks 88–123k) and fed back into
  both the arbitrageur's threshold and retail's acceptance ratio `r`.
- Seed appendix: seeds 0–4 on a 24-window subset; seed 0 reproduces the matrix
  bit-for-bit; storm-corner signs hold at every seed.

Findings: no dynamic hook beats static 30 bps unconditionally at any κ (DA, AB,
Volatility, MEV lose significantly at κ=1; BA ties). A conditional advantage
exists in high-volatility × 5 gwei windows (`BAHook` +1,556 [+894, +2,501]
USDT/window at κ=1), owned by `VolatilityHook`/`DAHook` at informed-heavy κ, and
erased by the hooks' own gas premium as gas rises. Policy effects run through
fee income; IL differs across policies by single-digit USDT.

## Claim boundary — keep it in every reply, comment, plot, and prose

- **Allowed:** a working reproducible framework (primary); the conditional
  finding above, with intervals and the paired 30 bps baseline (secondary).
- **Not allowed:** universal superiority of dynamic fees, adverse-selection
  protection, anything about live oracle behaviour, live-pool profitability.
- **Pre-registered vs observed.** Unconditional findings and the
  informed-share-rises-with-gas prediction (12.4% → 13.7%) were pre-registered.
  The storm × cheap-gas corner was **not** — report it as observed structure.
- **Model limits to state, not hide:** one arbitrageur once per candle with
  perfect information; no mempool, latency, or builder ordering; retail has no
  strategy or correlated demand; passive full-range liquidity; κ is swept, not
  calibrated to real pools; one year, three pairs, one venue; USDC/USDT's second
  leg is a synthetic 1.0 feed.
- **Known soft spots** (likely reviewer targets; check before quoting):
  - λ ≈ 461 is set so half the retail flow declines at 30 bps, which puts the
    model's static optimum at f* ≈ 2/λ ≈ 43 bps — the baseline sits near the
    optimum by construction of the participation function.
  - The paper cites LVR as "the LP-risk benchmark used in the evaluation", but
    the metric is IL/LPNet; `lvr` in `experiments/metrics.py` equals `il` by
    construction.
  - "Monotone in volatility and gas, every regime, every κ" holds only in
    relative (baseline-normalised) terms at κ=1, not in the absolute
    `uu_regime_gas_grid.csv`.
- **Withdrawn results.** Runs before the 2026-08-12 gas-unit fix (B→A retail gas
  in token0) are in `results-uu-gas-unit-defect/` and are not citable; the fix
  flipped `DAHook` from +341 to −235.

## Rules this domain imposes

- **Fee units are protocol-specific.** Uniswap v4 LP fees are `uint24` in pips
  (hundredths of a basis point; 30 bps = 3000). A value can be syntactically
  valid and semantically wrong.
- **Data boundaries are deliberate.** Configured constants, reference-market
  inputs, and endogenous pool outputs are three distinct kinds of value and must
  not be conflated. The pool never infers the external price; the feed never
  reads the pool.
- **Mocks validate integration, not oracle behavior.** Replaying Binance data
  through a mock feed does not reproduce a live feed's aggregation, heartbeat,
  deviation threshold, or latency.
- **Replay identity.** Each cell writes a manifest
  `E = <h(C), θ, D, P_0, L_0, W, S>` plus a fingerprint of its candles; a rerun
  skips cells whose manifest matches. Changing a contract, compiler, or input
  recomputes exactly the affected cells.

## Layout

| Path                     | Role                                                  |
| ------------------------ | ----------------------------------------------------- |
| `contracts/src/`         | hooks + `ArbMath`/`UUMath` libraries                  |
| `contracts/test/`        | `Replay.t.sol` (the harness) + unit/adversarial tests |
| `experiments/`           | matrix runner, trader models, metrics, stats, figures |
| `run_matrix.py`          | entry point for a full operating point                |
| `analysis/`              | notebooks and `draw_*.py` figure scripts              |
| `tests/`                 | Python test suite                                     |
| `results-uu*/`, `data/`  | experiment outputs and cached candles (gitignored)    |
| `dex/`, `dex-framework/` | colleague's side repos (gitignored, not ours)         |

## Toolchain

- **uv** (Python ≥3.13) owns all Python code and dependencies.
- **Foundry** (`contracts/`, `via_ir`); dependencies are git submodules pinned
  to field `D` of the manifest. **Do not update the submodules** — current
  `uniswap-hooks` tip breaks every policy.
- **npm** exists only for Prettier. Do not add runtime JS dependencies.

## Commands

```bash
uv sync                                        # Python deps
git submodule update --init --recursive        # pinned contract deps
cd contracts && forge build && forge test      # ~110 Solidity tests
uv run pytest -q                               # Python tests (excludes slow)
uv run pytest -q -m slow                       # slow tests: drive forge replays
npm run format                                 # Prettier + forge fmt + ruff

uv run python run_matrix.py --uu                     # κ = 1.0 -> results-uu/
uv run python run_matrix.py --uu --uu-turnover 0.1   # other κ, own directory
uv run python run_matrix.py --uu --limit 48          # smoke run
uv run python -m experiments.seed_robustness         # seed appendix
```

Never invoke bare `pip` or `python`; go through `uv run`.

## Traps

- **Ad-hoc `run_one` calls must pass `results_dir`.** Otherwise the probe
  overwrites the matrix trace for the same axes, the manifest still matches, and
  every analysis silently reads the probe.
- **Do not run slow tests while a matrix is running** — they write the shared
  trace files in `data/`.
- **After changing any hook, recalibrate gas** (`experiments/calibrate_gas.py`)
  — measured gas feeds both traders' decisions.
- **Never pool operating points.** Each κ writes to its own directory.
- If a window re-fetches Binance data, the cache key is wrong — investigate.

## Conventions

- Commits follow
  [conventional commits](https://gist.github.com/qoomon/5dfcdf8eec66a051ecd85625518cfd13).
  The owner makes every commit; leave changes in the working tree.
- Prettier formats Markdown with `proseWrap: always` (hard-wrapped — don't fight
  it); `forge fmt` owns `.sol`; ruff owns Python. `.prettierignore` keeps
  Prettier out of `paper/`.
