# Pre-registration: the UU-flow matrix

Recorded **2026-08-09, before the UU matrix runs** and before looking at any
result computed under UU flow beyond the calibration checks disclosed below.
Pre-registration only counts when it precedes the data. This document follows
the pattern of `2026-08-04-power-extension-preregistration.md` and, like it,
must not be edited once numbers exist.

## What changes

**The order-flow model.** The arbitrage-only assumption of the 2026-08-02 design
(§2 "Out of Scope: noise traders") is lifted per `2026-08-09-uu-flow-design.md`:
a deterministic uninformed-user (UU) flow with participation
`P = 1 if r ≥ 0 else exp(−λ|r|)`, applied as a volume share. Fixed for the whole
matrix:

- `uu_mode = share` (zero randomness; §7.5 of the original design still holds)
- `λ = 231_049_060_186_648_440_000` WAD (= ln 2 / 0.003: half the willing flow
  executes at a 30 bps total cost). The λ-sweep {58, 116, 231, 462, 924} is a
  sensitivity axis, stored under `results/sensitivity/`, never merged.
- `κ_pair` fixed by rule — mean daily UU volume over 2024 equals one basket
  (20,000,000 USDT) — and recorded per pair in every manifest. Known before any
  run: κ(ETH/SHIB) = 0.05517408261312724. The other two are computed by the same
  rule at run time.

**Configuration of `MEVChargeHook`,** declared here because it changes a
policy's effective behavior:

- `feeMax`: 1000 → **100 bps**. The 2026-08-09 audit found 49% of its swaps
  charging above the shared 100 bps fee box (up to 1000 bps), violating §4.5 of
  the design ("shared by every policy"). The clamp restores comparability.
- `flaggedFeeAdditional`: 400 → **40 bps**, forced by the contract's own
  invariant (`fixedLpFee + flaggedFeeAdditional ≤ feeMax` rejects 30+400>100);
  40 preserves the surcharge's ~40% share of the (now smaller) box.

Because of this clamp, MEVChargeHook rows are **not comparable** between the
arb-only matrix and the UU matrix.

## What does not change

- **Family**: every policy configuration against static 30 bps (`MyHook@3000`),
  in every stratum — 3 volatility regimes × 3 gas scenarios × 2 arbitrageur
  address modes × 3 pairs; 72 windows per pair; the same window set as the power
  extension.
- **Test**: two-sided Wilcoxon signed-rank per comparison, Benjamini–Hochberg
  across the deduplicated family at `q = 0.05`; `n_effective` reported.
- **Baseline**: `MyHook@3000`. Not re-chosen.
- **Reported beside every comparison**: median difference in USDT, % APR on the
  basket, win rate, effect size.

## Quantity: now a declared pair of valuations

Per-window paired difference in net LP result against HODL, in **two valuations,
both co-primary and always reported side by side**:

1. `net_result` — valued at end-of-window external prices (the original
   pre-registered quantity, unchanged);
2. `net_result_tt` — the same quantity valued at trade-time external prices.

**Honesty note.** The trade-time valuation was chosen _after_ inspecting
arb-only results: the 2026-08-09 audit found the end-of-window valuation carries
an inventory-revaluation term that flipped several arb-only conclusions
(documented in `PROGRESS.md`). It is declared here _before any UU data exists_,
but its motivation is post-hoc with respect to the arb-only experiment, and the
paper must say so. Where the two valuations disagree under UU flow, the
disagreement is reported as a finding, not resolved by choosing the friendlier
number.

## Declared in advance

- **The degeneracy is expected to be gone.** Verified on one calibration window
  before this registration (disclosed peeking, listed below): static
  `net_result` over {5, 30, 60, 100} bps was non-monotone with an interior
  optimum at 30–60 bps. The corresponding prediction for the matrix: the static
  100 bps baseline no longer dominates, and rankings stop tracking raw trade
  suppression.
- **`PegDefence` can now activate**: UU flow pushes the pool away from the
  reference, which is exactly the flow its mechanism charges. Its arb-only
  result (a de-facto static 1 bps) should not persist. If it still never fires,
  that is a reportable mechanism failure, not a data artifact.
- **The `ABHook` litmus now has a mechanism to win**: retail volume responds to
  the fee of its own direction, so reallocating a constant sum across directions
  can retain more benign flow than a uniform 30 bps. Direction of the effect is
  not asserted; that is what the experiment measures.
- **`MEVChargeHookFixed`** is expected to remain indistinguishable from static
  30 bps (its surcharge trigger sits far above retail and arbitrage sizes at
  this basket).
- A UU-flow result older than this document does not exist; nothing is being
  re-run to a preferred outcome.

## Disclosed peeking (calibration and verification runs)

Before this registration, the following UU-flow runs were executed and their
outputs seen, all confined to **ETH/SHIB, window 2024-01-01, `MyHook`**:

- the degeneracy check at 4 static fee levels (5/30/60/100 bps, 20 gwei);
- the UU golden window (`MyHook@3000`) and the differential golden (UU off);
- adversarial verification runs (`MyHook` at 5/60 bps; one `MEVChargeHook`
  high-volatility window at 80 gwei checking only the fee-box bound, plus two
  lower-volatility MEVChargeHook probes that produced constant 30 bps fees).

No other policy's UU behavior and no other window's UU numbers have been
observed. The 2024-01-01 window remains in the matrix (excluding it would break
pairing with the two frozen arb-only experiments); its role in calibration is
disclosed here instead.

## Relationship to the previous experiments

The arb-only 8-per-tercile run (`results/preregistered-8-per-tercile/`) and the
arb-only 72-window matrix (`results/matrix/`, summarized in
`results/summary.csv`) are both frozen and both reported. The UU matrix is a
third experiment (`results-uu/`), answering a different question: not "what
happens under pure adverse selection" but "can a dynamic fee discriminate
between toxic and benign flow". None of the three replaces another.
