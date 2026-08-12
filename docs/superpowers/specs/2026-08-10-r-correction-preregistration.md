# Pre-registration: the corrected `r`, and the matrix re-run

Recorded **2026-08-10, before the corrected matrix runs**. Like every
pre-registration in this project it must not be edited once numbers exist. It
amends, and does not replace, `2026-08-09-uu-matrix-preregistration.md`, which
also must not be edited — the two are read together.

## Why this exists

The UU model is taken from the group's previous work, whose definition is

```
r = δP(Δx, Δy) / δP(|Δx|, |Δy|)
P = 1 if r >= 0 else exp(-|r|)
```

The implementation did not compute that. `2026-08-09-uu-flow-design.md` §2.2
redefined `r` as a marginal (zero-size) relative price disadvantage,
`r = γ·p/P_ext − 1`, and the harness implemented that faithfully. Two
consequences, both found on 2026-08-10 and neither noticed when the model was
written:

1. **The normalisation was dropped.** Writing `V_in` and `V_out` for the two
   legs valued at the external price, the source `r` is
   `(V_out − V_in)/(V_out + V_in)`, which for a user losing a fraction `ε` of
   value is `−ε/(2−ε)` — approximately **half** the fractional disadvantage. The
   implemented form was `−ε`, twice the source value.
2. **Slippage left the model.** `Δy` in the source formula is what the pool
   actually pays, so the finite-size execution cost is inside the source `r`. A
   marginal price excludes it. The design spec justified the exclusion by
   asserting that a per-minute retail slice moves the price "~0.03 bps, two
   orders below the smallest fee".

   Measured directly, by differencing the recorded `r` against the same `r`
   evaluated at zero size over the 2,760 UU swaps of one real ETH/SHIB day:
   **1.18 bps at the median, 1.59 at the mean, 3.20 at p90, 7.21 at p99 and 15.7
   at the maximum.** So the omitted term is roughly thirty times the claimed
   figure and sits above the 1 bp floor of the fee box, though it stays inside
   it.

   (An earlier estimate in the 2026-08-10 review put this at 3.2 bps median /
   6.9 mean / 57.7 p99. Those came from `Δx/x` against a notional 10M side, i.e.
   a FULL-RANGE pool. The harness mints a concentrated position, so the depth
   near the price is far greater and the true impact is about a third of that.
   The measured figures above supersede them.)

## What changes

**`r` is computed from the realised trade.** `UUMath.rWad` now takes the pool
liquidity and an input size, derives the output from `SqrtPriceMath` — the same
arithmetic the pool performs, so the rounding matches — and returns
`(V_out − V_in)/(V_out + V_in)`. Slippage is therefore in `r`, and `|r| ≤ 1`.

**It is evaluated at the candle's potential slice**, the pre-thinning volume,
which is known before `P`. Evaluating at the executed size would reintroduce the
`fee → P → size → fee` loop that §2.2 broke for slippage; evaluating at zero
size is what produced the defect. This is a declared modelling choice, not a
neutral implementation detail, and the paper must carry it as such.

**λ = 461_404_973_192_736_927_635 WAD** (461.404973), replacing
231_049_060_186_648_440_000. The calibration _statement_ is unchanged — half the
willing flow walks at a **30 bps total transaction cost** — and the constant
moves only because `r` is now half its former magnitude:
`ln 2 / |r(0.003)| = ln 2 / 0.001502253`. Under the new `r` and λ, a user facing
fee alone at a fair-priced pool has `P` = 0.891 / 0.500 / 0.250 / 0.098 at 5 /
30 / 60 / 100 bps; with this document's own measured **mean 1.59 bps** of
execution cost added, 0.859 / 0.482 / 0.240 / 0.095 (at the median 1.18 bps,
0.867 / 0.487 / 0.243 / 0.096).

> **Corrected 2026-08-10, before this document's first cell was produced.** The
> second row read "with the mean 6.9 bps of slippage added, 0.760 / 0.426 /
> 0.213 / 0.084". Those figures were computed from the 6.9 bps mean that **this
> same document supersedes two paragraphs above** — the full-range estimate from
> the specification review, which does not apply because the harness mints a
> concentrated position. Using the measured figures the document itself
> declares, participation is materially higher. The correction assumes the
> measured 1.18/1.59 bps are stated as a fractional execution **cost** (the same
> units as a fee), which is how the surrounding prose uses them ("sits above the
> 1 bp floor of the fee box"); if they were instead recorded as `Δr`, which is
> half-scale, the corresponding costs are 2.36/3.18 bps and the row should be
> recomputed again. **Confirm which before this row is typeset.** No other
> number in this document depends on it.

**`uu_participation` is redefined** as the retail retention rate — executed
potential volume over potential volume, both in USDT. It was a mean of `P`
weighted by the raw `amountIn`, which mixes token0 and token1 wei (one direction
carried ~5e-9 of the weight on ETH/SHIB) and which weights by a quantity
proportional to `P` itself, returning `E[P²]/E[P]`. Neither the old nor the new
value enters any tested quantity; the column is descriptive.

**Also corrected, and affecting numbers:** the fee quoted to a `size_dependent`
policy is now quoted at the size being traded rather than at zero, so
MEVChargeHook can no longer advertise its base rate and charge a surcharge.
Measured on one cell before the re-run: its fee income falls 15,720 → 6,925.

## Three further changes, recorded before any cell exists

### 1. The matrix runs `discrete`, not `share`

Under `share` both directions receive the same potential volume and are thinned
by their own `P`, so near the reference with a symmetric fee the two flows
**cancel**: net displacement per candle is `v₀/2·(P_AB − P_BA) ≈ 0`. Retail
therefore delivers fee income at almost no inventory cost, there is very little
toxicity in the uninformed flow for a policy to discriminate against, and the
only channel left to win through is fee-revenue optimisation against the
participation curve — which is an identity of the assumed functional form, not a
result.

Measured at the calibrated κ, six ETH/SHIB windows, `MyHook@3000`:

| mode       | arb share of volume | cells with zero arbitrage |
| ---------- | ------------------- | ------------------------- |
| `share`    | 0.011               | **50%**                   |
| `discrete` | **0.109**           | **0%**                    |

`discrete` draws each direction independently and executes all-or-nothing, so
order flow is genuinely one-sided on some candles, the pool is displaced, and
the arbitrageur has something to correct.

**This introduces randomness.** The seed is a manifest field and a run is
reproducible given it, but a single run is one realisation. A seed-robustness
appendix (a few reference cells × 5 seeds, spec §2.4) is required before any
ranking is reported as stable, and is declared here as part of the plan rather
than as an optional extra.

Its design, fixed **2026-08-11 before it produced a cell** and implemented in
`experiments/seed_robustness.py`: seeds `{0,1,2,3,4}`; the baseline
`MyHook@3000` plus `DAHook`, `BAHook` and `ABHook`; ETH/SHIB and ETH/USDC only;
24 windows; 20 gwei. 960 cells.

- **Restricted to the two volatile pairs on purpose.** The claim whose stability
  is in question — adaptive fees beating a well-chosen static fee — is made only
  there. On USDC/USDT both policies lose significantly and there is no positive
  result to destabilise.
- **The baseline is re-paired within each seed.** Pairing across seeds would
  compare two different realisations of the draw.
- **The verdict rule, declared in advance:** a policy whose median keeps its
  sign across all five seeds may be reported as beating (or losing to) the
  baseline. One whose sign flips on any seed may be reported **per seed only**,
  and the paper says so in those words. The spread of the median across seeds is
  reported beside the verdict, because a unanimous sign with a wide spread is
  still weak evidence.

**The imbalance is a free parameter, and this is its extreme.** The
implementation draws ONE lognormal trade per direction per candle. Spec §2.4
describes `k ∈ {1..3}`; that was never implemented. Since the relative imbalance
of `k` independent arrivals falls as `1/√k`, and `share` is the `k → ∞` limit,
`k = 1` is the **most** imbalanced assumption available and `share` the least.
Real retail arrival counts per minute are far above 1, so the truth lies between
— but genuine imbalance comes from correlated demand, which neither mode models.
The paper must state that the degree of uninformed order-flow imbalance is
assumed, that `k = 1` is an upper bound on it, and that the ranking's robustness
to it is untested.

### 2. Retail pays gas, and gas enters `r`

`r` becomes `(V_out − V_in − G)/(V_out + V_in + G)`, with `G` the trade's own
gas at the candle's ETH price. Spec §2.2 excluded it — "a continuum of small
users whose individual gas is out of model" — and that made the gas axis inert.
Measured on the superseded matrix: raising gas from 5 to 80 gwei multiplied the
arbitrageur's gas bill sixteenfold and moved `net_result` by **−1.46%**, while
`uu_participation` went 0.7238 → 0.7200. Retail could not see gas at all, and
retail is ~90% of the flow.

This is expressible only in `discrete` mode: a continuum of infinitesimal users
has no per-user gas, whereas each discrete draw is a trade of a definite size.

Measured after the change, same six windows:

| gas     | uu participation | arb share | net_result |
| ------- | ---------------- | --------- | ---------- |
| 5 gwei  | 0.4198           | 0.125     | 16,335     |
| 20 gwei | 0.3878           | 0.129     | 15,255     |
| 80 gwei | 0.3177           | **0.143** | 13,150     |

The gas axis now moves the result by −19.5% rather than −1.46%, and the
**informed share rises with gas** — expensive gas prices out the small retail
draws first and leaves the toxic flow behind. That mechanism is declared here as
a prediction the matrix will either confirm or not; it was observed on six
calibration windows only.

### 3. The address axis is dropped

`ADDRESS_MODES` is `("persistent",)`. Under UU flow the axis is empty: across
all 7,776 paired cells of the superseded matrix, `fresh` and `persistent` agreed
**to the last bit for every one of the twelve policies**, including
MEVChargeHook, the only one that reads the sender — UU swaps always come from
fresh addresses, and the arbitrageur it could have profiled barely trades. The
analysis already deduplicated this axis (2026-08-03 audit), so half the matrix
was producing rows that were then discarded.

The declared family in `2026-08-09-uu-matrix-preregistration.md` names two
address modes. This is a deviation from it, taken before any cell of the
corrected matrix exists, and it removes duplicates rather than observations: no
comparison loses a paired window. **The risk is stated rather than dismissed** —
at a configuration where the arbitrageur trades more, MEVChargeHook could begin
to distinguish the modes, and this run would not detect that.

The matrix is therefore **7,776 cells**: 12 policies × 3 pairs × 72 windows × 3
gas scenarios.

## What does not change

- **Family**: every policy configuration against static 30 bps (`MyHook@3000`),
  in every stratum — 3 volatility regimes × 3 gas scenarios × 2 arbitrageur
  address modes × 3 pairs; 72 windows per pair.
- **Test**: two-sided Wilcoxon signed-rank per comparison, Benjamini–Hochberg
  across the deduplicated family at `q = 0.05`, `n_effective` reported.
- **Baseline**: `MyHook@3000`. Not re-chosen.
- **The two co-primary valuations**, both always reported side by side.
- **κ** at its calibrated value, the basket, the window set, the gas scenarios,
  and the MEVChargeHook fee-box clamp declared on 2026-08-09. κ is **not**
  lowered to rescue the arbitrage share; `discrete` mode does that at the
  turnover the design already declares.

## The status of the 2026-08-10 matrix

The matrix completed on 2026-08-10 under the marginal `r` is **superseded and
withdrawn as a result**. It is retained at `results-uu-preflight-defect/` as
evidence for the corrections above and cited nowhere else. No number from it
appears in the paper. This document is recorded before the corrected matrix
produces its first cell.

## Declared in advance

- **Participation must fall**, at every fee level, relative to the superseded
  run: `r` now carries a cost it did not carry. This is arithmetic and is
  reported as a check that the change took effect, not as a finding.
- **The interior static optimum is not a finding, and is not claimed as one.**
  Retail fee revenue is `f·P(f)`; with `P = exp(−λ|r|)` and `r ≈ −ε/2` at a
  fair-priced pool, `argmax_f f·exp(−λf/2) = 2/λ`, which at the new λ is **43.3
  bps** — the same location as under the old parameterisation, because λ was
  scaled with `r`. The existence and approximate location of the optimum follow
  from the assumed participation function and the chosen λ. The paper will print
  `2/λ` beside the measured optimum and will not write "the experiment shows an
  interior optimum exists". What the experiment contributes at this point is the
  **policy ranking at a fixed λ**.
- **λ remains a swept axis**, `{58, 116, 231, 462, 924}` in the old
  parameterisation and correspondingly rescaled here. Because the optimum sits
  at `2/λ`, the λ sweep moves the optimum across and out of the fee box: it is a
  sweep _of_ the result, not a robustness check _on_ it, and is reported that
  way.
- **No prediction is made about whether `BAHook` keeps its advantage**, or about
  any policy's ranking, under the corrected `r`. The superseded run's rankings
  are not carried forward as expectations.

## Limitations this does not remove

- **The continuum is evaluated at one point in the candle.** `r` uses the
  pre-swap pool state, so a continuum arriving sequentially through the minute —
  each user facing the pool their predecessors moved — is not modelled. The
  realised average cost across such a continuum is roughly half the aggregate
  move, so participation remains an **upper bound**.
- **The two UU swaps within a candle are ordered A→B then B→A.** The first moves
  the pool before the second's `r` is evaluated. Measured, that displacement is
  worth 1.2 bps of cost at the median candle and 7.2 at p99 — small against the
  fee at the median, not negligible on the tail.
- **Retail gas is still outside `r`** (§2.2), and the arbitrageur's gas gating
  is unchanged.
- **`net_result` and `net_result_tt` are different functionals**, not one
  quantity under two valuations: the first is a terminal mark-to-market against
  HODL, the second a path integral of realised transfers with no valuation date.
  The 2026-08-09 pre-registration describes them as the same quantity; that
  description is wrong and the paper must define both algebraically and name
  them "terminal mark-to-market" and "realised" P&L.
