# main.tex integration edits — 2026-08-12

Supersedes `paper-edits-required-2026-08-10.md` (whose numbers are from
withdrawn runs). Sources of truth for every number: the corrected-run
report `docs/reports/2026-08-12-framework-report.md` and the CSVs beside
each figure in `paper/Image/`. `main.tex` line numbers refer to the
version last modified 2026-08-02 (330 lines).

The single structural fact behind most edits: **the paper currently
disclaims exactly what the repository now contains.** Lines 61, 284, 301,
320 all say some variant of "no baselines, no repeated trials, no
uncertainty intervals, no gas measurements — future work". All four now
exist: 5 operating points × 5,832 cells each, static baselines under
identical conditions, bootstrap CIs, per-policy EVM-measured gas. The
integration turns those disclaimers into the paper's second contribution
while keeping the claim discipline (no unconditional superiority).

---

## A. Global decisions (agree these first)

**A1. Scope of policies.** The evaluated set is 4 hooks (`ABHook`,
`BAHook`, `DAHook`, `MEVChargeHook`) + recalibrated `VolatilityHook` + 4
static baselines `MyHook@{5,30,60,100 bps}`. `MEVChargeHookFixed`,
`PegDefence`, `PegCapture` are out (Table `tab:hooks` rows stay as
*templates*; the evaluation section names its own subset).

**A2. Claim ladder** (what strength each finding is stated at):

- *Strong* (both valuations, pre-declared machinery, replicated across
  operating points): (i) pooled, no hook beats a well-chosen static fee
  at any of five retail scales; (ii) the static curve has an interior
  optimum at the calibrated mix (30–60 bps plateau, model-consistent
  with $2/\lambda$); (iii) IL is policy-invariant — a fee policy prices
  flow, it does not reduce adverse selection; (iv) the informed share
  rises with gas.
- *Medium* (observed structure, both valuations, replicates at every κ,
  but post-hoc and one seed): the storm × cheap-gas corner advantage and
  its κ-dependent ownership (BAHook ↔ VolatilityHook/DAHook relay).
- *Not claimable*: unconditional superiority; adverse-selection
  protection; live-oracle behaviour; anything from the withdrawn
  pre-revision runs (notably DAHook +341 — it is now −235).

**A3. Statistics language**: bootstrap intervals only ("the 95% interval
excludes zero"); Wilcoxon/BH exist in the artifact's CSVs and get one
methods footnote. No stars, no p-values in prose.

**A4. Units note**: our `net_result` = $R_f - IL$ = $-L_{\text{net}}$ of
Eq. (4). State the sign mapping once where metrics are introduced so the
paper's Eqs. (3)–(4) and the artifact's CSVs reconcile.

---

## B. Edits by location

### Abstract (line 31)

**B1.** Replace the last three sentences ("A prototype execution …
common workflow.") with text of this shape:

> The framework couples this engineering layer with a controlled
> evaluation layer: a paired replay experiment that runs each policy and
> four static-fee baselines over identical 2024 market histories (three
> pairs, 72 day-windows each, three gas scenarios, five retail-scale
> operating points; 29,160 cells in total), with modelled informed and
> uninformed flow, per-policy gas measured in the EVM, and effect sizes
> reported as bootstrap confidence intervals. Pooled across conditions,
> no evaluated dynamic policy outperforms a well-chosen static fee at
> any flow mix; conditionally, a reproducible advantage appears in
> high-volatility windows at low gas prices, carried by different
> policies at different informed-flow shares and consumed by the
> policies' own gas overhead as gas rises. The framework's contribution
> is that this conditional structure is measurable at all — the same
> infrastructure yields both the deployable hooks and the controlled
> comparison.

(29,160 = 5 × 5,832. Keep "not economic superiority" spirit: the
sentence "no evaluated dynamic policy outperforms … unconditionally"
carries it with data instead of absence of data.)

**B2.** Keywords: consider adding "backtesting" / "liquidity-provider
returns".

### §I Introduction

**B3 (line 56, contributions).** Extend the bullet list with two items:

- the evaluation methodology: paired same-window comparison against
  static baselines with modelled informed/uninformed flow, measured gas,
  and pre-declared aggregation (cite report §4/§6);
- the conditional economic finding (state at A2-medium strength, one
  sentence).

**B4 (line 61, boundary paragraph).** Replace entirely. Old text says
the artifact "lacks the fixed-fee baselines and repeated trials required
to claim improved LP performance". New shape:

> The evaluation includes same-trace fixed-fee baselines, repeated
> windows across volatility regimes, and uncertainty intervals; the
> boundary we maintain is different in kind: the measured advantage of
> adaptation is conditional (on volatility regime, gas price, and the
> informed share of flow), and we do not claim unconditional
> superiority. Where a result depends on an assumed parameter, the
> parameter is declared and swept.

### §II Background

**B5 (after Eq. 4).** One sentence tying notation: "In the evaluation we
report $R_f(T)-IL(T) = -L_{\mathrm{net}}(T)$ under two valuation
conventions (terminal and trade-time)."

**B6 (line 96–100).** The related-work positioning ("enables a later
controlled economic comparison") should switch tense: the comparison is
in this paper. Also the Table `tab:relatedwork` row for "This work" can
add "…and a controlled paired evaluation against static baselines".

### §III Framework Design

**B7 (line 135, §III-A).** Experiment layer sentence: replace
`Simulation.t.sol` with the current name (`Replay.t.sol`) or a neutral
"the replay test contract".

**B8 (line 212).** "volatility-based hooks … react to trade volume
variance" — implementation reacts to **price-ratio variance**, not trade
volume. Fix the noun. Also mention the two units corrections briefly or
silently (recommended: silently; the shipped constants are the current
ones).

**B8b (Table `tab:hooks`, line 227).** The `ABHook` row's signal column
says "External ratio with asymmetric response" — the implementation (and
the original dex artifact) reacts to the **pool's own price change**, not
an external ratio; its constructor accepts feeds but never reads them.
Fix the signal to "pool price change, asymmetric by direction". Oracle
readers among the evaluated set are exactly `BAHook` and
`VolatilityHook` (PegStability reads feeds but is out of scope).

**B9 (line 247, Eq. 9 manifest).** "recording all elements of $E$ is a
concrete extension needed" → now implemented: every cell writes the full
manifest (source-tree hash for $D$, window fingerprint for $W$, RNG seed
in $S$), and re-runs are skipped/invalidated by it. Rewrite as a
statement of fact; this is a genuinely strong reproducibility point.

**B10 (line 260, §III-E Testing).** The Go backend claim: the artifact's
test reality is 110 Solidity tests + ~341 Python tests + notebook-level
integrity checks. Either drop "backend integration tests (in Go)" or
scope it to the dex web layer explicitly. (This was a known
inconsistency; decide with the colleague.)

### §IV — replace "Replay and Prototype Evaluation" with the experiment

This is the big rewrite. Suggested structure (all content exists in the
report; translate/condense from there):

**B11. §IV-A Trader model.** Two flows. Arbitrageur: no-arbitrage band
$[P\gamma, P/\gamma]$, closed-form optimal trade, executes only if
$\Pi^* > g\,p_{\text{gas}}$ with $g$ the policy's EVM-measured median
gas (report §4.1). Uninformed users: the prior work's Eqs. (8)–(9)
($r$ = normalised portfolio-value ratio with fee, slippage and gas
inside; $P_{\text{exec}} = e^{-\lambda|r|}$), with the sensitivity
calibration $\lambda = \ln 2 / |r(30\,\text{bps})| = 461.4$ — cite the
prior paper for the model, present λ as a calibration statement ("half
the willing flow walks at a 30 bps total cost") and note it is swept.
Retail arrives as one lognormal draw per direction per minute, executed
all-or-nothing (report §4.5, incl. the "why this construction" para).

**B12. §IV-B Demand calibration.** $v_0(c) = \kappa \cdot \text{basket}
\cdot \hat s(c)$: measured intraday shape (Binance per-minute quote
volumes, geometric mean of the pair's legs; figure
`uu_volume_profile.pdf`), dimensionless turnover κ in baskets/day,
calibrated κ=1 and swept over {0.03…3} producing measured arbitrage
shares 89/58/25/13/16% — with the operating-points-as-pool-types table
(report §4.4) if space allows; it disarms the "is κ=0.1 meaningful?"
review question.

**B13. §IV-C Design & statistics.** Matrix axes; 24 windows per
volatility tercile per pair; pairing by identical window; percentile
bootstrap CI of the median as the only significance instrument; cell-first
aggregation; baseline 30 bps declared, 60 bps comparison labelled
post-hoc. One footnote for Wilcoxon/BH (~96% agreement).

**B14. §IV-D Results.** The tables/figures to carry:

1. Headline table (κ=1): median Δ vs 30 bps over 18 volatile strata,
   both valuations — MyHook@6000 −2 [−186,+266]; BAHook −100 [−453,+350];
   DAHook −235 [−381,−104]; ABHook −460 [−630,−288]; VolatilityHook
   −752 [−1069,−280]; MEVChargeHook −913 [−1659,−728].
2. Static curve interior optimum (1,644/11,890/11,932/7,936 at
   5/30/60/100 bps) + the $2/\lambda \approx 43$ bps consistency +
   the caveat that the optimum follows the assumed participation
   function.
3. IL invariance / decomposition (fee-income deltas in the hundreds, IL
   deltas single digits) → "a fee policy prices flow; it does not
   protect".
4. The regime × gas grids (figure `uu_regime_gas_grid.pdf`, and
   `uu_t01_…` if two operating points are shown): the storm ×
   cheap-gas corner, +1,556 [+894,+2,501] for BAHook at κ=1; ownership
   relay across κ (table in report §10, "The full κ range");
   `uu_kappa_trend_high.pdf` as the compact cross-κ storm view and/or
   `uu_kappa_trend.pdf` for the pooled no-win view.
5. Gas: `uu_gas_cost_per_swap.pdf` — per-swap dollars and the "gas
   premium rivals the fee box at 80 gwei" reading; informed share rising
   with gas (12.4→13.7%).
6. Relative-vs-absolute reading note (one sentence + pointer to `_rel`
   figures) — prevents the "adaptation is worse in storms" misread.

**B15.** The 1,492-swap prototype paragraph (lines 288–301): keep
`dynamic_fee_reaction` as the mechanism illustration if desired, but the
"does not establish economic superiority / provides no baselines …"
paragraph (line 301) must be replaced — that list is now the paper's
content, per B4.

### §V Security, Validity, and Discussion

**B16 (line 316, validity).** Keep the microstructure limitations
(mempool, latency, routing, one arbitrageur) — still true. Add the
model-side declared limits: κ assumed and swept (not calibrated to real
pools), k=1 lumpiness, no correlated demand, mocks ≠ live oracles, one
seed pending the seed appendix. Source: report §12.

**B17 (line 320).** "A controlled economic study within such a framework
should hold the trace … constant while varying only the policy … These
additions are future evaluation work" → replace: this is now the
implemented protocol (enumerate: same trace/reserves/range/valuation/
seed; static baselines; LP value, fee income, IL, net outcome, retained
volume, fee distributions, measured gas overhead; multiple pairs,
regimes, repeated windows, uncertainty intervals). What remains future
work: multi-seed robustness (in progress), κ calibrated from real
pool volume/TVL, correlated-demand flow, testnet validation.

**B18 (line 322, next steps).** Update: event-level result export,
manifest identity, version pinning — done; keep typed schema,
containerisation, property-based tests, fault injection as future.

### §VI Conclusion

**B19 (line 326).** Rewrite to the two-contribution shape: the
framework (primary) + the conditional finding (secondary, one sentence,
A2-medium strength). Kill "It does not prove that a dynamic policy
outperforms static fees" in favour of the precise version: "It shows
that none of the evaluated policies outperforms a well-chosen static fee
unconditionally, and localises where and for whom adaptation does pay."

---

## C. Figure inventory for the paper (all in `paper/Image/`, CSV beside each)

| figure | shows | suggested placement |
| --- | --- | --- |
| `uu_regime_gas_grid.pdf` | the conditional structure at κ=1 | Results, main |
| `uu_kappa_trend_high.pdf` | storm slice across all κ (the relay) | Results, main |
| `uu_kappa_trend.pdf` | pooled no-win across κ | Results or appendix |
| `uu_gas_cost_per_swap.pdf` | measured per-swap gas in $ and bps | Methodology/Results |
| `uu_volume_profile.pdf` | measured intraday demand shape | Methodology |
| `uu_effect_sizes.pdf` | headline CIs at κ=1 | Results (alt. to table) |
| `uu_regime_gas_grid_rel.pdf`, `uu_t01_*` | robustness views | appendix |
| `uu_fee_distribution.pdf` | what each policy actually charged | appendix |
| `dynamic_fee_reaction.pdf` | mechanism illustration (kept from v1) | Framework section |

Reproducibility line for the artifact statement: every figure is drawn
by a script/notebook in `analysis/`, carries its operating-point stamp,
and writes a CSV of its own numbers; every cell carries the Eq. (9)
manifest; conservation of value closes at ~1e-16 per cell.
