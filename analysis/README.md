# Analysis notebooks

Cleaned up 2026-08-12 after the gas-denomination fix (see
`docs/reports/2026-08-12-framework-report.md` §11). **Only the notebooks in
this folder are current**; everything else moved to `archive/` with its
status recorded below.

The scripts under `experiments/` produce data and nothing else; nothing here
runs the matrix, so a figure can be redrawn in seconds without a replay.

## Current

| Notebook                      | Reads                            | Writes                                                  |
| ----------------------------- | -------------------------------- | ------------------------------------------------------- |
| `07-uu-main-results.ipynb`    | `results-uu/summary.csv`         | `paper/Image/uu_*.pdf`, `analysis-*.csv` beside the run |
| `08-uu-flow-behaviour.ipynb`  | `results-uu/`, its traces        | `paper/Image/uu_flow.pdf`, `uu_fee_distribution.pdf`    |
| `09-kappa-sensitivity.ipynb`  | `results/sensitivity/kappa.csv`  | `paper/Image/kappa_response.pdf`                        |

`kappa.csv` holds only levels re-run on the revised harness (currently
0.1×; `run_kappa_01.py` is the one-level driver). Notebook 09 draws
whatever levels exist and extends automatically as more are re-run.

Both report the **corrected** UU matrix (post gas-fix, 2026-08-12): 8
policies — `ABHook`, `BAHook`, `DAHook`, `MEVChargeHook` and the four static
baselines `MyHook@{500,3000,6000,10000}` — × 3 pairs × 72 windows × 3 gas
scenarios = 5,184 cells, `discrete` mode, seed 0, calibrated κ.

`UU_CONFIG=informed` (the κ = 0.1 operating point) is currently **dead**: the
`results-uu/turnover-0.1/` run predates the gas fix and was archived. Run
07/08 in their default `headline` configuration only, until that matrix is
re-run.

## `archive/arb-only/` — valid, frozen, different experiment

Notebooks 01–06: the two **arbitrage-only** experiments, reading the frozen
`results/summary.csv`. They are **not** affected by the 2026-08-12 defect
(retail flow did not exist there) and their figures in `paper/Image/`
(`fee_detail_*`, `capture_share_sensitivity`, `frontier`, `gas_breakeven`,
`net_result_by_regime`, `fee_response`, `volatility_stratification`) remain
valid. Archived only to keep this folder to what is being actively worked
on. Note: their internal relative paths assume they sit in `analysis/`; move
one back up before re-executing it.

## `archive/pre-gasfix-uu/` — inputs contaminated, do not trust outputs

Notebooks 10 (seed robustness) and 11 (operating points). Their input runs
(`results/sensitivity/seeds*`, `results-uu/turnover-0.1/`) predate the gas
fix and are contaminated by the B→A gas-denomination defect. (09 returned
to `analysis/` on 2026-08-12, reading the clean re-run levels only.) Their checked-in outputs and the figures
they drew (moved to `results-uu-gas-unit-defect/figures/`) must not be
quoted. They return to this folder if and when their runs are repeated on
the corrected harness.

## Figures policy

Every figure writes a CSV of its own numbers next to it, so any value in the
paper can be checked without rerunning anything. Figures from contaminated
runs are quarantined in `results-uu-gas-unit-defect/figures/`, never left in
`paper/Image/`: absent beats wrong. `paper/Image/_archive-dropped-policies/`
holds valid arb-only figures for the four policies dropped from the paper
(`MEVChargeHookFixed`, `PegCapture`, `PegDefence`, `VolatilityHook`).
