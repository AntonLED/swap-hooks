# Evaluation brief — the eight points

Structured exactly as requested: _framework architecture, mathematical model,
experimental methodology, baselines, parameters, datasets, metrics, and main
results._ Each section is the short version; depth lives in the full report
(`2026-08-12-framework-report.md`), and a paper-ready LaTeX rendering of the
evaluation part is `paper/evaluation-draft.tex` (compiles standalone). Every
number below is traceable to a CSV beside its figure in `paper/Image/`.

## 1. Framework architecture

Four layers in one repository:

- **Contracts** (`contracts/src/`): hook policies on OpenZeppelin's
  `BaseOverrideFee` + pure math libraries (arbitrage band/optimum, retail
  participation). All policies share a [1, 100] bps fee box.
- **Replay harness** (`contracts/test/Replay.t.sol`): a Forge test that replays
  one day of market data against one policy in a real EVM. Per minute: update
  mock feeds and clock, run retail flow both directions, give one arbitrageur a
  single chance. Emits a per-swap JSONL log and derives no metrics itself.
- **Experiment layer** (`experiments/`, Python): matrix runner with resumable
  per-cell reproducibility manifests $E=\langle C_\theta,D,P_0,L_0,W,S\rangle$
  (the main paper's Eq. 9 — now implemented, not aspirational), trace
  generation, gas calibration.
- **Analysis layer** (`analysis/`): notebooks + figure scripts; every figure
  ships with a CSV of its own numbers.

Key capability: because swaps execute in a real EVM, **gas is measured, not
assumed** — per-policy median gas (76k static, 88–124k adaptive) feeds back into
both traders' decisions.

## 2. Mathematical model

Two flows, asymmetric by design.

**Arbitrageur (informed).** No-arbitrage band $[P\gamma, P/\gamma]$,
$\gamma=1-f$. Once per minute, after retail, it pushes the pool to the nearest
band edge iff the closed-form profit exceeds its gas bill:

$$ \Pi^*_{0\to1}=\frac{L(s-t)^2}{s},\qquad
\Pi^*_{1\to0}=\frac{L(t-s)^2}{\gamma s},\qquad
\Pi^*>g\,p_{\text{gas}}$$

(derivation: appendix of the tex draft). $\Pi^*$ decides trades; all
metrics come from executed swaps' balance changes.

**Uninformed users (retail).** The acceptance model of the prior paper
(its Eqs. 8–9): normalized outcome ratio
$r=(V_{\text{out}}-V_{\text{in}}-G)/(V_{\text{out}}+V_{\text{in}}+G)$
with fee, slippage and gas inside; execution probability
$P_{\text{exec}}=e^{-\lambda|r|}$ for $r<0$, else 1. One deviation to
state in the paper: $\lambda=\ln 2/|r(30\text{bps})|\approx 461.4$ — a
sensitivity calibration ("half the willing flow walks at a 30 bps total
cost"); the uncalibrated $e^{-|r|}$ is fee-insensitive at our trade
sizes. Retail arrives as one mean-preserving lognormal draw per
direction per minute, executed all-or-nothing, seeded.

**Demand scale.** $v_0(c)=\kappa\cdot\text{basket}\cdot\hat s(c)$:
shape $\hat s$ measured (Binance intraday profile), the single knob
$\kappa$ = daily turnover in baskets/day.

## 3. Experimental methodology

- Full factorial per operating point: 9 policies × 3 pairs × 72
  day-windows (24 per volatility tercile) × 3 gas scenarios = 5,832
  cells; five $\kappa$ operating points = 29,160 cells total.
- **Paired comparison**: every policy differenced against the baseline
  on the same window/pair/gas.
- **Statistics**: median paired difference with a 95% percentile
  bootstrap CI (10,000 seeded resamples); *the interval excluding zero
  is the only win/loss criterion*. Aggregation is cell-first so three
  gas scenarios of one day are never counted as independent. Classical
  Wilcoxon+BH tests remain in the CSVs (~96% agreement) as a footnote.
- Reproducibility: manifests resume/invalidate cells exactly;
  conservation of value closes at ~1e-16 per cell.

## 4. Baselines

Static fees at 5 / 30 / 60 / 100 bps run through the identical
machinery. The pre-declared comparison baseline is **30 bps**
(Uniswap's classic tier); the comparison against the best static in the
box (60 bps) is reported and labeled post-hoc. The measured static
curve has an interior optimum on the 30–60 bps plateau, consistent with
the model's $2/\lambda\approx 43$ bps.

## 5. Parameters

| parameter | value | status |
| --- | --- | --- |
| basket (TVL) | 20M USDT, 50/50, full range | chosen |
| window | 1 day = 1,440 min candles; 60 warm-up | chosen |
| windows | 24 per volatility tercile per pair | chosen (power) |
| price series & intraday shape | Binance 2024 | **measured** |
| κ (retail scale) | 1 basket/day reference | assumed, **swept** ×{0.03…3} |
| λ (price sensitivity) | 461.4 | assumed (calibration statement), swept |
| retail granularity | 1 lognormal draw/direction/min, σ=1 | assumed |
| gas per swap | per-policy EVM-measured median | **measured** |
| gas scenarios | 5 / 20 / 80 gwei (≈\$1/\$4/\$15 per static swap) | chosen |
| policy constants | as shipped (per contract) | fixed |
| RNG seed | 0 (5-seed appendix defined) | chosen |

Interpretation of κ levels (measured arbitrage share in brackets):
3.0 = flagship pool (16%); **1.0 = active primary venue, the a-priori
reference (13%)**; 0.3 = mid-tier (25%); 0.1 = secondary venue (58%);
0.03 = over-provisioned pool (89%). Literature estimates put
non-primary venues at 40–70% informed share, so κ≤0.1 is arguably the
median DEX pool, not a stress test.

## 6. Datasets

Binance 1-minute klines, calendar 2024: ETHUSDT, SHIBUSDT, USDCUSDT
closes (prices; ETHUSDT also values gas) and quote volumes (intraday
demand shape). USDC/USDT's second leg is a synthetic constant 1.0.
2024 contains a mania (March), a crash (Aug 5) and quiet months; the
high-volatility tercile of ETH/SHIB spans 4.3–16% daily realized vol.
Mock feeds validate integration, not live-oracle behavior.

## 7. Metrics

Primary LP outcome per cell: `net = fee income − IL` = LP value minus
HODL value, marked at end-of-window prices (negative = worse than
holding; equals $-L_{\text{net}}$ of the main paper's Eq. 4). A
trade-time valuation is computed as robustness; all findings are
unchanged under it. Also recorded: retained volume, retail/arbitrage
volume split, retail participation rate, fee income share paid by
retail, realized arbitrage P&L, per-swap gas. Fees follow v4 accounting
(accrue to the position, never compound). Validity check per cell:
pool-state ledger ≡ trader-flow ledger to ~1e-16.

## 8. Main results

1. **No unconditional winner.** At the reference point, vs 30 bps
   (median over 18 volatile-pair strata, 95% CI): 60 bps −2 [−186,+266];
   BAHook −100 [−453,+350]; DAHook −235 [−381,−104]; ABHook −460
   [−630,−288]; VolatilityHook −752 [−1069,−280]; MEVCharge −913
   [−1659,−728]. Pooled, no hook's interval clears zero at **any** κ.
2. **A fee policy prices flow; it does not protect.** The IL term of
   every paired difference is single-digit USDT (arbitrage pins the
   closing price under every policy); the differences are fee income,
   minus each hook's own gas premium.
3. **Where adaptation pays — the conditional corner.** High-volatility
   windows × cheap gas, replicated at every κ with a clean hand-over:
   BAHook owns it at retail-heavy mixes (+1,556 [+894,+2,501] per
   window at κ=1, 5 gwei), VolatilityHook/DAHook at informed-heavy
   ones (+308/+246 at κ=0.1), and at κ=0.03 VolatilityHook wins storms
   at *all* gas prices. At 80 gwei everything loses or ties.
4. **Gas is first-order.** Adaptive hooks pay 88–124k gas vs 76k
   static; at 80 gwei even a static swap costs ~47 bps of a \$4,000
   trade. The informed share rises with gas (12.4→13.7%).
5. **Figures**: regime×gas grids per κ (`uu_*regime_gas_grid*`), κ
   trends pooled and storm-slice (`uu_kappa_trend*`), per-policy fee
   behaviour on a storm day (`uu_fee_response`), demand construction
   (`uu_demand_calibration`), gas costs (`uu_gas_cost_per_swap`).

**How strongly to claim (suggested):**

- *Strong* (pre-declared machinery, replicated across κ and both
  valuations): no-unconditional-winner; the static interior optimum;
  IL invariance; informed share rising with gas.
- *Secondary but real* (observed structure, replicates at every κ, one
  seed until the appendix runs): the storm × cheap-gas corner and its
  κ-dependent ownership — phrased as "where and for whom adaptation
  pays", never as "dynamic fees are better".
- *Not claimable*: unconditional superiority; adverse-selection
  protection; live-oracle behavior.
$$
