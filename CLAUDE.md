# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with
code in this repository.

## What this repo is

Experiment code for the paper **"A Configurable Dynamic-Fee Hook Framework for
Uniswap v4 Liquidity Pools"** (IEEE ICBC 2026 submission `1571326575`). The
LaTeX sources are to be added to the repo; `.prettierignore` already reserves
`ICBC 2026 - Hooks LP/` as the Overleaf-synced paper folder — do not let
Prettier touch it, it will fight the sync.

**Current state: scaffold only.** `main.py` is a stub, `experiments/test.ipynb`
is a three-cell scratch notebook, `materials/` is empty. None of the
architecture below exists in the tree yet. Expect to build structure, not
discover it.

## What the paper builds (target architecture)

A framework for configuring, deploying, and replay-testing dynamic-fee hooks on
Uniswap v4. Fee policies are `f_t = F(s_t, z_t; θ)` — on-chain state `s_t`,
optional external signal `z_t`, parameter vector `θ`. Four layers:

- **Contract layer** — hooks, base contracts, interfaces. Computes directional
  fees, validates callbacks, talks to `PoolManager`. Built on OpenZeppelin's
  uniswap-hooks (`BaseDynamicFee`, `BaseOverrideFee`).
- **Deployment layer** — `BaseScript`, `Deployers`, `HookHelpers`: mine a
  CREATE2 salt matching the declared permission bitmap, deploy mock tokens and
  feeds plus Uniswap artifacts, initialize the pool.
- **Experiment layer** — Forge tests, `Simulation.t.sol`, data utilities, and a
  result parser that replays observations and records price, volume, fees,
  holdings, and LP metrics.
- **Application layer** — Flask + browser code to select/configure hooks, show
  generated source, export a self-contained Foundry project, run simulations.

Hook templates and their update granularity:

| Template      | Granularity            | Signal                                       |
| ------------- | ---------------------- | -------------------------------------------- |
| `BAHook`      | at most once per block | change in external token-price ratio         |
| `DAHook`      | per trade              | deal-level state and swap characteristics    |
| `ABHook`      | block-level            | external ratio, asymmetric by swap direction |
| MEV-charge    | policy-specific        | MEV-oriented rule                            |
| Peg-stability | policy-specific        | deviation from a target peg                  |

Volatility templates use EMA and Welford's online algorithm for variance.

Toolchain the paper commits to: Foundry (Forge for tests, Anvil for the local
EVM), Chainlink-compatible price-feed mocks, Flask for the local HTTP interface,
Playwright for e2e, PostgreSQL for off-chain history (`HookParamsHistory`,
`ChainEvent`, `PoolStateSnapshot`), and Binance kline/candlestick data as the
offline market trace. (§III-E also mentions Go for backend integration tests
alongside the Flask interface — resolve that inconsistency against the actual
paper sources once they land, don't guess.)

## Rules this domain imposes

- **Fee units are protocol-specific.** Uniswap v4 LP fees are `uint24` in
  hundredths of a basis point. A value can be syntactically valid and
  semantically wrong (e.g. a minimum above the configured maximum) — the paper's
  own §III-B calls this out as a known gap.
- **Keep the claim boundary.** The paper claims end-to-end _engineering
  feasibility_, explicitly **not** economic superiority: one ETH/SHIB trace,
  1,492 simulated swaps, no fixed-fee baseline, no repeated trials, no
  uncertainty intervals. Do not write code comments, plots, or prose that imply
  the dynamic policy beats a static fee. If asked to make a comparative claim,
  say what would be required first (same-trace static baseline, multiple pairs
  and regimes, repeated windows).
- **Data boundaries are deliberate.** Configured constants, reference-market
  inputs, and endogenous pool outputs are three distinct kinds of value and must
  not be conflated. Canonical hook sources are never simulation results; raw
  market observations are never inferred from the pool.
- **Mocks validate integration, not oracle behavior.** Replaying Binance data
  through a mock feed does not reproduce a live feed's aggregation, heartbeat,
  deviation threshold, or latency. Don't claim otherwise.
- **Replay identity.** A run is identified by `E = <C_θ, D, P_0, L_0, W, S>` —
  configured contract, dependency/compiler revisions, initial price, initial
  liquidity, market-data window, swap-generation config. Pin all six; without
  them two runs on the same nominal month and pair diverge.

## Toolchain (as it exists today)

Two independent toolchains, deliberately:

- **uv** (Python ≥3.13) owns all runtime code and dependencies —
  `pyproject.toml` / `uv.lock` / `.venv`.
- **npm** exists only to provide Prettier as a formatter. Do not add runtime JS
  dependencies for it.

Foundry is not installed or configured yet; `.prettierignore` pre-ignores `lib/`
in anticipation of `forge install`.

## Commands

```bash
npm install          # installs Prettier (formatter only)
npm run format       # everything: Prettier, then forge fmt
npm run format:sol   # Solidity only (forge fmt)
npm run format:check # verify without writing
uv venv              # create .venv
uv sync              # install/sync Python deps from uv.lock

npm run format       # Prettier, then forge fmt — the only formatting step
uv add <dep>         # add a Python dependency (edits pyproject.toml + uv.lock)
uv run main.py       # run the entrypoint stub
uv run jupyter lab   # experiments/ notebooks
```

`pip ...` maps to `uv pip ...`. Never invoke bare `pip` or `python`; go through
`uv run` so the project venv is used. There is no test suite or Python linter
configured — if you add one, record the command here.

## Conventions

- Commits follow
  [conventional commits](https://gist.github.com/qoomon/5dfcdf8eec66a051ecd85625518cfd13).
- Formatting is Prettier-driven per file type (see `.prettierrc`): 4-space
  indent for Solidity/TS/JS/JSON, 80-col + `bracketSpacing: false` + double
  quotes for `.sol` (via the `slang` parser), `proseWrap: always` for Markdown —
  so Markdown gets hard-wrapped, don't fight it. Prettier does not touch Python.
- `.prettierignore` came from a sibling project (`adaptive-liquidity`) and
  pre-ignores paths that do not exist here yet: `lib/`, `research/`,
  `references/`, `ICBC 2026 - Hooks LP/`, mlruns. Read it as the intended
  layout, not the current tree.
