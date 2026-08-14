# Analysis notebooks and figure scripts

Everything here draws from data on disk; nothing replays. Every figure writes a
CSV of its own numbers beside the PDF and stamps the operating point on its
face.

## Notebooks

| Notebook                     | Reads                                | Writes                                             |
| ---------------------------- | ------------------------------------ | -------------------------------------------------- |
| `07-uu-main-results.ipynb`   | `<run>/summary.csv`                  | `paper/Image/<prefix>*.pdf`, `analysis-*.csv`      |
| `08-uu-flow-behaviour.ipynb` | `<run>/summary.csv`, per-swap traces | `<prefix>flow.pdf`, `<prefix>fee_distribution.pdf` |

Both take the operating point from `UU_CONFIG`:

| `UU_CONFIG`          | run directory               | figure prefix |
| -------------------- | --------------------------- | ------------- |
| `headline` (default) | `results-uu/`               | `uu_`         |
| `informed`           | `results-uu/turnover-0.1/`  | `uu_t01_`     |
| `t003`               | `results-uu/turnover-0.03/` | `uu_t003_`    |
| `t03`                | `results-uu/turnover-0.3/`  | `uu_t03_`     |
| `t3`                 | `results-uu/turnover-3/`    | `uu_t3_`      |

The checked-in notebook outputs are the headline's; other configurations are
executed headlessly when needed.

## Figure scripts

| Script                    | Draws                                                              |
| ------------------------- | ------------------------------------------------------------------ |
| `draw_regime_gas_grid.py` | regime × gas grids, absolute + baseline-relative (per `UU_CONFIG`) |
| `draw_kappa_trend.py`     | advantage vs κ across all five matrices: pooled + storm slice      |
| `draw_gas_costs.py`       | per-swap gas in dollars per policy (κ-independent)                 |
| `draw_uu_profile.py`      | the measured intraday demand shape $V_{\text{profile}}$            |

```bash
UU_CONFIG=informed uv run python analysis/draw_regime_gas_grid.py
uv run python analysis/draw_kappa_trend.py
```

## History

The arb-only notebooks (01–06), the pre-gasfix robustness notebooks and the
probe-based κ notebook (09) were removed on 2026-08-12 when the paper's scope
settled on the UU experiment across five full κ matrices; they remain in git
history before that date if ever needed.
