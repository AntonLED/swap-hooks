# Design: Uninformed-User (UU) Flow

Date: 2026-08-09. Status: approved in discussion; supersedes §2 "Out of Scope:
noise traders" of `2026-08-02-dynamic-fee-experiments-design.md`. Everything not
amended here stays as the 2026-08-02 design specifies.

## 1. Why

Under arbitrage-only flow the pre-registered quantity degenerates: every trade
is a net loss to the LP by construction of the entry condition (verified on
30,274 swaps: zero negative realized arbitrageur profits), so net-vs-HODL
improves monotonically as volume is suppressed and the observed ranking follows
trade count. Three of the six policies (`PegDefence`, `MEVChargeHook`, the
directional forecasts of `BAHook`/`ABHook`) are aimed at flow that does not
exist in the simulation. UU flow supplies the second blade of the scissors:
raising the fee now costs retained retail revenue, so an interior optimum exists
and a dynamic policy can win honestly — by discriminating between toxic and
benign flow — rather than by strangling volume.

> **AMENDED 2026-08-10 (U6).** The clause "by discriminating between toxic and
> benign flow" is the sentence that licenses the strongest claim in this
> experiment, and **the model as specified does not support it as stated**.
> Under `share` mode (§2.3) both directions are thinned deterministically from
> the same `v₀`, so when the pool sits near the external price under a symmetric
> fee, `P_AB = P_BA` and the two retail flows cancel: net displacement per
> candle is `v₀/2·(P_AB − P_BA) ≈ 0`. Uninformed flow is therefore balanced **by
> construction**, which makes it unusually benign — it delivers fee income at
> almost no inventory cost, and there is very little toxicity in it to
> discriminate against. `2026-08-10-kappa-sensitivity-preregistration.md`
> reaches the same conclusion from the numbers ("fee income trivially covers
> adverse selection, which is why every policy posts a profit").
>
> The channel through which a policy can actually win in this matrix is
> **fee-revenue optimisation against the participation curve** — see the
> `argmax_f f·exp(−λ|r|)` note in `2026-08-10-r-correction-preregistration.md`.
> The one genuine discrimination channel that survives is **directional**: a
> policy setting `f_AB ≠ f_BA` induces `P_AB ≠ P_BA` and so does move the pool.
> That is a real mechanism and it is exactly the ABHook litmus — but it is far
> narrower than "toxic vs benign". §2.4's discrete mode is what would restore
> order-flow imbalance, and it is the thing deferred.
>
> **For the paper:** state that the main result is obtained under a flow model
> in which uninformed flow is balanced by construction, and that robustness of
> the ranking to unbalanced uninformed flow is untested. Do not write the "toxic
> vs benign" sentence.

## 2. The Model

Carried over from the group's previous work: a psychological parameter `r`
(normalized disadvantage of the transaction) and an execution probability

```
P = 1            if r >= 0
P = exp(-λ·|r|)  if r <  0
```

> **ASSUMPTION, uncited — flagged 2026-08-10 (U1).** "Carried over from the
> group's previous work" is the whole justification this model has. There is no
> reference, no empirical anchor, and no argument for the exponential form over
> any other decreasing function. This matters more than a missing citation
> normally would, because the functional form **determines** the interior
> optimum: retail fee revenue is `f·P(f)`, and `argmax_f f·exp(−λ|r(f)|)` is a
> closed-form function of λ alone (`1/λ` under the marginal `r`, `2/λ` under the
> corrected `r`; see `2026-08-10-r-correction-preregistration.md`). It is the
> single most load-bearing uncited assumption in the third experiment. The paper
> needs either a citation to the prior work or an explicit statement that the
> form is **assumed** and every result is conditional on it. Do not delete this
> note by supplying a plausible-sounding reference; supply the actual one.

Two adaptations, both load-bearing:

### 2.1 Scale parameter λ

Raw `exp(-|r|)` at basis-point scale is flat (P ∈ [0.99, 0.9999] over the whole
fee box), which silently restores the degeneracy. λ makes the psychology
explicit and calibratable. **Default λ = ln(2)/0.003 ≈ 231.05**: at a total
transaction cost of 30 bps, half of the willing flow executes. λ is a swept
sensitivity axis (like `captureShare`), values `{58, 116, 231, 462, 924}`, i.e.
P(30 bps) ∈ {0.84, 0.71, 0.50, 0.25, 0.0625}. The main matrix runs only the
default.

> **AMENDED 2026-08-10.** Three things.
>
> **(a) The constant moved.** Under the corrected `r`, λ = **461.404973**, not
> 231.049060, for the identical calibration statement — see
> `2026-08-10-r-correction-preregistration.md`. The value above is retained
> because the 2026-08-09 pre-registration was written against it.
>
> **(b) U2 — the calibration statement names a broader cost than λ is applied
> to.** "At a **total transaction cost** of 30 bps" is not what happens: `r`
> contains the fee and the signed pool deviation, and under the corrected model
> the finite-size execution cost; retail **gas is excluded by construction**
> (§2.2, §11). So λ is calibrated against a notion of cost strictly broader than
> the one it is then applied to, which biases participation upward. The exactly
> true statement, which should replace it in the paper: _at a pool sitting on
> the external price, `r` is a function of the fee alone, and `P` = 0.5 at 30
> bps_. **Away from the external price that reading does not hold** — `r`
> carries the signed deviation too — and §2.2's body says so, but this headline
> sentence does not carry the caveat.
>
> **(c) The λ sweep is a sweep _of_ the result, not a robustness check _on_
> it.** Because the optimum sits at a closed-form multiple of `1/λ`, moving λ
> across `{58, 116, 231, 462, 924}` moves the optimum across and out of the [1,
> 100] bps fee box. Reported that way, per the r-correction pre-registration. As
> of 2026-08-10 the sweep is **declared here and implemented nowhere** — there
> is no analogue of `sensitivity.py` for λ — so §9's "its λ, κ are swept, not
> asserted" is currently false for λ. Either the sweep runs or the paper says
> plainly that λ was fixed and not varied.

### 2.2 What r is here

> **AMENDED 2026-08-10.** Everything in this subsection describes the FIRST
> implementation and is superseded by
> `2026-08-10-r-correction-preregistration.md`. It is kept unedited because the
> 2026-08-09 pre-registration was written against it.
>
> Two things below are wrong. The source model's `r` is
> `δP(Δx,Δy)/δP(|Δx|,|Δy|)` — a **normalised** ratio, about half the fractional
> disadvantage — and it is computed from the **realised** `Δy`, so slippage is
> inside it. The form given here is twice that magnitude and marginal, so it
> omits slippage entirely.
>
> The bullet below justifying that omission ("~0.03 bps, two orders below the
> smallest fee") is false by roughly two orders of magnitude: measured over all
> 527,040 aligned 2024 candles at the calibrated κ, the execution cost is 3.2
> bps at the median candle and 6.9 bps at the mean, and exceeds the whole 100
> bps fee box on more than 1% of candles. The same false premise underpins §4's
> claim that the intra-candle ordering of the two UU swaps is innocuous.
>
> λ moves with the definition: 461.404973, not 231.049060, for the same
> calibration statement.
>
> **A third thing is under-specified rather than wrong (D12a): where the fee in
> `r` is quoted.** "Marginal (zero-size) execution price" fixes where the
> _price_ is read but is silent on where the _fee_ is read, and for a
> `size_dependent` policy the two are different questions. The harness first
> quoted the fee at zero size, which let `MEVChargeHook` advertise its base rate
> and charge a surcharge — retail decided to trade at 30 bps and was charged
> ~65. It now quotes at the candle's **potential** volume
> (`contracts/test/Replay.t.sol:433-440`). Both behaviours are outside what this
> subsection says, and the correct one is still not neutral: the fee is quoted
> at `v₀/2` while the charge lands on `v₀/2·P < v₀/2`, so retail is quoted a fee
> it will not be charged. Quoting at the executed size would reintroduce the
> `fee → P → size → fee` loop this subsection broke for slippage, so the choice
> is deliberate. It is declared in `2026-08-10-r-correction-preregistration.md`
> and the paper must carry it as a **declared modelling choice**. Recorded here
> so that an agent verifying code against this spec does not flag the correct
> implementation as a defect.

Per direction, evaluated at the pre-swap pool state, marginal (zero-size)
execution price against the external price. With pool price `p` (token1 per
token0), external `P`, and direction fee `f_d` (fraction), `γ_d = 1 − f_d`:

```
UU selling token0 (A→B):  r = γ_AB · p / P − 1
UU selling token1 (B→A):  r = γ_BA · P / p − 1
```

- The **fee** enters through γ — the whole point.
- The **pool deviation** enters signed: a user trading toward the external price
  gets a bonus (r ≥ 0 → P = 1, the formula's upper branch); a user trading
  against it is penalized. Policies that keep the pool near the external price
  retain more two-sided flow.
- **Slippage is deliberately dropped** (marginal price, not average): at the 20M
  basket a per-minute retail slice (~14k USDT) moves the price ~0.03 bps, two
  orders below the smallest fee. Dropping it also breaks the circularity P →
  size → slippage → P, keeping the computation closed-form. Stated as a
  limitation.
- **Gas is not in r**: the UU side is a continuum of small users whose
  individual gas is out of model. Stated as a limitation. (Arbitrageur gas
  gating is unchanged.)

UU users "see" the external price (anyone with a price app does); _uninformed_
means they do not time, size, or route strategically — they arrive with
exogenous demand and either trade or walk away per P.

> **ASSUMPTION — flagged 2026-08-10 (U8).** "Anyone with a price app does" is an
> assertion, and it is a load-bearing one, not an aside: it is what makes the
> pool-deviation term enter `r` **signed**, and therefore what produces the
> "users trading toward the reference execute regardless of fee" effect that is
> then invoked to explain the gap between observed participation and `exp(−λf)`.
> If retail did not observe the reference, `r` would carry the fee and slippage
> only, participation would be lower and unsigned, and no policy could earn
> retention by keeping the pool near the reference. It belongs in the paper's
> limitations as a stated modelling assumption.

### 2.3 Deterministic share application (main mode)

P is applied as a **deterministic volume fraction**, not a coin flip: the
per-candle potential volume in each direction is thinned to
`v_d = v₀/2 · P(r_d)`. Interpretation: a continuum of small users, P is the
participation rate. Spec §7.5 (zero randomness, bit-for-bit replay) remains
true; the matrix does not grow; the analysis keeps one run per cell.

### 2.4 Hybrid groundwork (discrete mode, not run in the main matrix)

The generator takes `--uu-mode {share, discrete}`. `discrete` draws **one**
potential UU trade **per direction** — two per candle — with a lognormal size
`(κ·V/2)·exp(σZ − σ²/2)`, `Z ~ N(0,1)`, which is mean-preserving since
`E[exp(σZ − σ²/2)] = 1`, so the two together still have expectation `v₀`. Each
is executed all-or-nothing with probability P via a seeded PRNG **in Python at
trace generation time** — Solidity stays deterministic; the seed is a manifest
field (S). Mode `share` is the default everywhere. Discrete mode exists so a
later robustness appendix (a few reference cells × 5 seeds, kept under
`results/sensitivity/`, exact-filename filtering as with `captureShare`) can
show the thinning approximation does not change signs or ordering. Implemented
and tested now; executed later, time permitting.

> **Corrected 2026-08-10 (D11).** This said `discrete` "draws k ∈ {1..3}
> potential UU trades per candle". No such draw exists.
> `experiments/uu.py::export_uu_trace` draws exactly one lognormal potential
> trade per direction, two per candle; the trace carries a per-direction size
> and a per-direction uniform `u`, and the harness executes iff `u ≤ P·1e18`.
> The **expectation** was right, so nothing downstream is affected, and discrete
> mode is not in the main matrix — but the robustness appendix this subsection
> promises would have been described wrongly. Corrected in place.
>
> Note the consequence for §1's amendment: because the two directions are drawn
> independently here, discrete mode is precisely the mode in which uninformed
> flow stops being balanced by construction. That is what makes the deferred
> appendix worth running, and it should be said in the paper as the named
> untested robustness axis rather than as tidiness.

## 3. Calibration of v₀

Per-candle potential UU volume (in USDT, split half per direction):

```
v₀(candle) = κ_pair · V_profile(candle)
```

- `V_profile` — the activity profile from data already on disk: the geometric
  mean of the available legs' Binance quote volumes for that minute (two legs
  for ETH/SHIB and ETH/USDC; the single real leg for USDC/USDT, whose second
  feed is CONSTANT_ONE).
- `κ_pair` — a constant per pair fixing the scale: **mean daily UU volume over
  2024 equals one basket (20,000,000 USDT)**, i.e. turnover 1×/day, mid-range
  for real major pools. κ is recorded in the manifest.

> **AMENDED 2026-08-10.** Two things about this rule, neither of which changes
> what κ is or what ran.
>
> **(a) U3 — "mid-range for real major pools" carries no citation.** It is an
> author-chosen constant of exactly the kind `captureShare` turned out to be,
> and that one flipped the sign of a policy's result.
> `2026-08-10-kappa-sensitivity-preregistration.md` concedes this and sweeps κ
> for that reason; the concession must reach the paper, not stop at the
> pre-registration.
>
> **(b) D5 — κ fixes _potential_ volume, not realised turnover.**
> `experiments/uu.py::kappa` normalises `Σ v_usdt` over a day, which is the
> volume **before** thinning by P. Executed retail volume is `v₀·P`, so realised
> turnover is `κ·E[P]` baskets/day — endogenous to the fee, and varying by a
> factor of ~5 across the four static fee levels, which is the whole mechanism
> of the model. "Turnover 1×/day" is therefore the **potential** turnover only.
> Wherever the axis is drawn or named, label it "potential daily turnover
> (baskets)" and report the realised turnover, or the arbitrage share of volume,
> beside it.

Input token amounts: A→B input = `(v_AB) / P0`, B→A input = `(v_BA) / P1`,
valued at that candle's external feed prices.

## 4. Candle Loop and Execution

Per candle: **update feeds → UU swap A→B → UU swap B→A → arbitrage check** (the
fixed UU order is arbitrary and documented; sizes are small enough that the
ordering effect is far below the fee scale). UU swaps move the pool; the
arbitrageur cleans up, which couples the flows honestly.

> **AMENDED 2026-08-10.** The parenthetical rests on §2.2's "~0.03 bps" slippage
> claim, which is false — see the §2.2 banner. Measured on one real ETH/SHIB
> day, the A→B swap's displacement is worth **1.2 bps of cost to the B→A swap at
> the median candle and 7.2 bps at p99**. That is small against a 30 bps fee at
> the median but not negligible on the tail, and the tail is where the volume
> is. The ordering remains fixed and arbitrary; the claim that it is innocuous
> is withdrawn and replaced by these numbers, which
> `2026-08-10-r-correction-preregistration.md` carries as a standing limitation.

- UU swaps execute from **fresh addresses** (a continuum of users). The
  persistent/fresh axis continues to apply to the arbitrageur only.
- Warm-up: UU flow runs during warm-up; metrics still start at the warm-up
  boundary snapshot — no change needed.
- A UU swap whose computed size rounds to zero (P ≈ 0 or dust) is skipped, not
  logged.

### 4.1 exp in Solidity

`P = exp(-λ|r|)` is computed in the harness (r depends on runtime pool state). A
new `contracts/src/libraries/UUMath.sol` provides `expNegWad` — a port of
solady's `expWad` restricted to non-positive inputs, with attribution — plus the
r computation. Tested against a Python `mpmath` reference on a grid including
the branch boundaries (differential tolerance ≤ 1e-9 relative). Policy contracts
are untouched: this is harness math, like `ArbMath`.

## 5. Event Schema

Swap records gain `"trader": "arb" | "uu"` and, for UU swaps, diagnostic fields
`r` and `P` (WAD-scaled ints). The window record is unchanged.

## 6. Metrics

- `net_result` (end-of-window, vs HODL) — definition unchanged; it is now
  non-degenerate because UU fees are revenue.
- **New co-primary valuation `net_result_tt`**: the same LP-vs-HODL quantity
  valued at trade-time external prices (equal to minus the sum over swaps of
  `Δ0·P0_t + Δ1·P1_t`). The 2026-08-09 audit showed end-of-window valuation
  carries an inventory-revaluation term that can flip conclusions; both
  valuations are declared up front this time and reported side by side.

> **AMENDED 2026-08-10 (D3).** "The same LP-vs-HODL quantity valued at
> trade-time external prices" is wrong, and the wrongness is not cosmetic.
> Writing `Δ_t = (Δ0_t, Δ1_t)` for the pool-side balance deltas of swap `t`:
>
> ```
> net_result     = P0_T·Σ_t Δ0_t  +  P1_T·Σ_t Δ1_t
> net_result_tt  = Σ_t ( Δ0_t·P0_t + Δ1_t·P1_t )
> ```
>
> The first depends on the deltas **only through their sum** — it is a terminal
> mark-to-market of one portfolio against another, and the valuation date is
> exactly the free parameter in it. The second is a **path integral**: it
> depends on the order and timing of the trades and has no valuation date at
> all, so it cannot be obtained from the first by re-dating anything. Their
> difference is the inventory-revaluation term named above, and that term
> existing is precisely what makes them **different functionals**. Sharper
> still: `net_result_tt` is not a comparison against HODL, because HODL is only
> defined at a valuation date — it is the LP's realised P&L against its
> counterparties, which under arb-only flow is identically `−Π_arb^gross` and
> hence negative by construction.
>
> Name them "terminal mark-to-market" and "realised / trade-time" P&L, define
> both algebraically, and drop "the same quantity". `net_result_tt` carries no
> inventory risk and `net_result` does, so a preference between them is a
> modelling stance, not a convention — and a disagreement between them is two
> different facts, not a valuation artifact to be explained away. The rule in
> the 2026-08-09 pre-registration (report the disagreement as a finding, do not
> resolve it by choosing the friendlier number) is the right behaviour and
> stands; only the description was wrong. Carried as a limitation in
> `2026-08-10-r-correction-preregistration.md`.

- `arb_profit` is **renamed `arb_mtm`** (it is the arbitrageur inventory marked
  at end-of-window prices, identically −net_result under arb-only flow; it was
  never realized profit). New `arb_profit_realized`: Σ over arb swaps of
  trade-time deltas value, minus gas at trade-time ETH price.
- New columns: `uu_volume`, `arb_volume` (retained_volume splits),
  `uu_fee_share` (fraction of fee income paid by UU flow), `uu_participation`
  (volume-weighted mean P).

> **AMENDED 2026-08-10.** Two corrections to this bullet.
>
> **(a) D12b — "volume-weighted mean P" was under-specified, and the weight it
> got is not a participation rate.** The implementation weighted `P` by
> `amountIn`, i.e. by the **executed** amount, which is itself `potential × P`;
> the published column was therefore `Σ v P² / Σ v P = E[P²]/E[P]`, biased
> upward by the Jensen gap, and it mixed token0 and token1 wei so that one
> direction on ETH/SHIB carried ~5e-9 of the weight. Swaps rounding to zero are
> additionally skipped and never logged (§4), removing the low-`P` candles from
> the average and biasing it up again. This matters because the number was used
> as evidence: the gap between the observed participation and `exp(−λf)` was
> attributed entirely to the signed pool deviation, and part of it was the
> estimator. `2026-08-10-r-correction-preregistration.md` redefines the column
> as the **retail retention rate** — executed potential volume over potential
> volume, both in USDT — which is the quantity the name always implied. Neither
> the old nor the new value enters any tested quantity; the column is
> descriptive. The paper must not attribute an estimator artifact to a
> mechanism.
>
> **(b) "retained_volume splits" is loose.** `uu_volume` and `arb_volume` are
> valued at **trade-time** prices while `retained_volume` uses end-of-window
> prices, so they are not splits of it in the exact sense. Measured across all
> 15,552 UU cells the median ratio is 1.0000050 and the share figures are formed
> from the two new columns directly, so nothing is wrong numerically — but the
> word "splits" should be "the UU and arbitrage components, valued at trade-time
> prices".

- Conservation invariant unchanged in form — the system is still closed; flows
  now sum over both trader kinds. The existing tolerance gate is unchanged.

## 7. Fee-Box Compliance Fix (rides along)

The 2026-08-09 audit found `MEVChargeHook` charging above the shared box on 49%
of its swaps (up to 1000 bps against the declared 100 bps cap, spec §4.5). Its
config `feeMax` is set to **100 bps (= 10000 pips)** for all runs of the new
matrix, and `flaggedFeeAdditional` from 400 bps to **40 bps** with it. This is a
configuration change, not a policy-logic change (§13 discipline holds).
`MEVChargeHookFixed` is unaffected (never leaves 3000).

> **AMENDED 2026-08-10.** Two edits above, and one correction to the 2026-08-10
> specification review.
>
> **The unit was restated, not the value.** This section originally read "10000
> pips", the only place in the project that states this constant in pips. 1 bp =
> 100 pips, so 10000 pips = 100 bps: the value **agreed with the
> pre-registration all along**. The review's D4 claims `feeMax` is a `uint16` in
> basis points and that "10000" would therefore set a 100% cap — the field is
> indeed bps (`contracts/src/MEVChargeHook.sol:56`, and `_getFee` converts with
> `fee = candidateBps * 100`), but this document was quoting pips and said so.
> **D4's first half is wrong; no value was ever off by 100×.** Since fee units
> are the named hazard of this project, both units are now given.
>
> **D4's second half is right and is the reason for the second edit.**
> `setFeeMax` reverts unless `fixedLpFee + flaggedFeeAdditional ≤ feeMax`
> (`MEVChargeHook.sol:183`), and `30 + 400 > 100`, so the stated change is
> impossible on its own. The harness sets `setFlaggedFeeAdditional(40)`
> **first** and then `setFeeMax(100)`
> (`contracts/test/utils/HookTest.sol:156-157`); the 2026-08-09 pre-registration
> records the companion change and this document omitted it. It is not
> bookkeeping: the surcharge's absolute size fell by 10×, while 40/100 preserves
> the original 400/1000 = 40% share.
>
> **Consequence the paper must carry:** `MEVChargeHook`'s effective fee box
> differs between the two experiments — [30, 1000] bps in `results/`, [30, 100]
> bps in `results-uu/` — so its rows are **not** comparable across them.

## 8. Matrix

Unchanged axes: 12 policies × 2 arb address modes × 3 pairs × 72 windows × 3 gas
scenarios. New defaults: UU mode `share`, λ = 231.05, κ per §3. The arb-only
matrix in `results/matrix/` is **not** overwritten; the new matrix writes to
`results-uu/matrix/`. λ-sweep goes to `results/sensitivity/` later, never
merged.

> **Corrected 2026-08-10.** Two things.
>
> **The directory name was wrong** — this said `results/matrix-uu/`. The tree,
> `run_matrix.py:137-138` and the 2026-08-09 pre-registration all say
> `results-uu/matrix/`. The removed parenthetical ("exact-filename filters
> updated — the lesson from the sensitivity-leak defect stands") is worse than
> stale: filename filtering was the **wrong mechanism**, the output directory
> was never threaded through to `run_one`, and on 2026-08-10 the UU matrix's
> traces landed on top of the arb-only experiment's and destroyed 10,363 of
> them. The fix that worked was threading `results_dir` through
> `execute_parallel → _worker → run_spec → run_one` **and** allowlisting
> `../results-uu/` in `contracts/foundry.toml`; either alone fails. This belongs
> in the paper's reproducibility note as one honest sentence.
>
> **"Unchanged axes: 12 policies" — the axis changed.** The 2026-08-02 design §5
> declares eleven configurations; the twelfth, `MEVChargeHookFixed`, was added
> on 2026-08-03 and appears in no design document as an approved configuration.
> The 2026-08-02 §5 now carries an amendment recording it. The change itself is
> defensible; calling the axis "unchanged" while it changed is the problem.

## 9. Pre-Registration

A new pre-registration amendment is recorded **after implementation is verified
and before the new matrix runs**, following the pattern of 2026-08-04: family,
test (Wilcoxon + BH at q = 0.05), baseline (MyHook@3000) unchanged; quantity now
declared as the pair (end-of-window, trade-time) valuations, both reported. It
will state honestly that the trade-time valuation was chosen after inspecting
arb-only results (the 2026-08-09 audit), and that the arb-only matrix remains
reported as the paper's first experiment. The claim boundary moves from
"engineering feasibility" to "controlled comparison under a synthetic two-flow
model"; the UU model is synthetic and its λ, κ are swept, not asserted.

## 10. Verification

1. **Unit**: `UUMath` against Python reference (exp, r, both branches, P=1
   region); generator κ normalization (mean daily = basket); profile geometric
   mean incl. the one-leg pair.
2. **Differential**: with `v₀ = 0` the harness reproduces the arb-only golden
   window bit-for-bit (UU code inert).
3. **Directional**: with a pinned off-price pool, P = 1 on the favorable
   direction and < 1 on the other; monotone in λ and in fee.
4. **Conservation**: closes with both flows on a full window, all policies.
5. **Degeneracy is gone** (the point of it all): on one calibration window,
   static net_result vs fee level is no longer monotone — an interior static
   optimum exists. If it is still monotone at λ = 231, λ is recalibrated before
   the matrix runs and the change is recorded in the prereg amendment.

   > **AMENDED 2026-08-10 (D2).** The retuning licence in the last sentence
   > should never have been written. A free parameter retuned until a
   > qualitative result appears makes that result unfalsifiable, and a referee
   > reading this item will say so. In the event **nothing was retuned** — the
   > check passed at λ = 231 on the first attempt (PROGRESS, 2026-08-09) — so
   > the licence was never exercised; it is left in place because the 2026-08-09
   > pre-registration was written against this document, and it is disclosed
   > rather than deleted.
   >
   > The deeper point is that the check itself is close to vacuous. Retail fee
   > revenue per direction is `f·(v₀/2)·P(f)`, and with `P = exp(−λ|r(f)|)` the
   > first-order condition of the **assumed functional form** places an interior
   > maximum at a closed-form multiple of `1/λ` for every λ — 43.3 bps at the
   > calibrated value, which is exactly where the measured optimum landed.
   > Across the declared λ-sweep the optimum moves to 172 / 86 / 43 / 22 / 11
   > bps, i.e. outside the [1, 100] bps fee box at the low end, where the curve
   > becomes monotone and "the degeneracy" returns. So the sweep is a sweep of
   > the finding. **The paper must not write "the experiment shows an interior
   > optimum exists"**; it must print the analytic optimum beside the measured
   > one and claim only the _policy ranking at a declared λ and κ_. Committed to
   > in `2026-08-10-r-correction-preregistration.md`.

6. **Golden window**: new golden with UU flow pinned, plus the arb-only golden
   kept green.

## 11. Out of Scope (unchanged or newly explicit)

- UU strategic behavior (routing, timing, splitting) — excluded by definition.
- UU gas in the participation decision (§2.2).
- Cross-candle UU demand dynamics (each candle independent).
- Concentrated liquidity, mempool microstructure — as before.

## 12. Disclosure list for the paper — corrections that cannot be made in place

Added 2026-08-10. Each item below is a defect in a **frozen** document — one for
which data exists, so the text is left exactly as recorded and the correction
lives here. Nothing in this section licenses an edit to any pre-registration.

**In `2026-08-09-uu-matrix-preregistration.md`:**

1. **"The degeneracy is expected to be gone", and the interior optimum.** The
   existence and approximate location of the interior static optimum follow from
   `argmax_f f·exp(−λ|r(f)|)` given the assumed participation function and the
   chosen λ. Print the analytic optimum next to the measured one in the same
   table; claim the policy ranking, not the optimum. See §10 item 5 above.
2. **"`net_result_tt` — the same quantity valued differently."** It is not. See
   the §6 amendment for the two definitions and the naming the paper should use.
3. **The disclosed-peeking section contradicts itself.** The preamble confines
   the seen runs to "ETH/SHIB, window 2024-01-01, `MyHook`"; the list then
   includes three `MEVChargeHook` probes, one of them a high-volatility window,
   which 2024-01-01 is not; and the closing sentence ("no other policy's UU
   behavior and no other window's UU numbers have been observed") contradicts
   the bullet three lines above it. The **substance** checks out — an
   independent pass against PROGRESS found no undisclosed peek — so the fix is
   to restate the scope accurately: MyHook on 2024-01-01, plus three
   MEVChargeHook probes including one high-volatility window, on which the
   fee-box bound and not the outcome metric was inspected.
4. **`MEVChargeHookFixed` "expected to remain indistinguishable from static 30
   bps"** was a prediction about the instrument's resolution, not a mechanism,
   and it was falsified (22/27 significant losses, median −6.17 USDT = the gas
   difference). That is a **good** outcome for the pre-registration's
   credibility. Keep it, with the handling already recorded: detectable because
   72 windows are a lot, and economically nil — report both numbers or neither.
5. **One FDR family or two was left open.** This document says "Benjamini–
   Hochberg across the deduplicated family", singular, and never says whether
   the two co-primary valuations are one family or two. The implementation chose
   **separate families per valuation**, which is the statistically right call
   (BH's threshold `k·q/m` is adaptive, so pooling lets a strong valuation lift
   a weak one) — but it was fixed after the UU data existed. State in the paper
   that FDR is controlled **per valuation**, that every claim is reported under
   both, and that no claim rests on significance in one valuation alone: a claim
   satisfied by a win in _either_ is an unadjusted union with roughly double the
   error rate, and neither pre-registration gives a decision rule for the
   two-valuation case.
6. **"The deduplicated family" is not countable in advance from any
   pre-registered text.** The rule — collapse comparisons bit-identical across
   the address axis — is documented only in PROGRESS. BH is invariant to exact
   duplication and zero verdicts changed, so nothing moves numerically; one
   sentence defining the rule closes it.

**In `2026-08-04-power-extension-preregistration.md` and §12.1 of the 2026-08-02
design:**

7. **§12.1's Bonferroni justification is wrong twice.** It says "roughly 90
   comparisons ⇒ threshold 0.00056" and "a Wilcoxon test on 24 windows cannot
   reach it". The declared family is 3 regimes × 3 gas × 2 address modes × 3
   pairs × 10 non-baseline configurations = **540** (297 after deduplication),
   so Bonferroni is 1.7e-4; and each comparison runs on **8** windows, not 24 —
   at n = 24 the minimum two-sided p is 1.2e-7, which clears 0.00056 easily, so
   the sentence as written is false. The same n error recurs in §12.1's
   rationale for preferring Wilcoxon to a t-test. **The conclusion survives**:
   at n = 8 the p-floor is 0.0078, above Bonferroni at either m. No published
   number changes; the stated reasoning does not support the stated conclusion,
   and the 2026-08-04 amendment derives the same conclusion correctly. If
   §12.1's reasoning is reproduced in the methodology, correct m and n there.
8. **`captureShare` is pinned by reference, not by value** — for the parameter
   that flips the sign of `PegCapture`'s headline. See the 2026-08-02 design §5
   amendment.

**Also for the reproducibility note, from the 2026-08-10 traceability pass:**

9. The `captureShare` sweep and the κ sweep are **exploratory, not
   pre-registered**. §12.1 contains no `captureShare` sweep; the only
   pre-registered statement about that constant is the opposite commitment in
   the 2026-08-04 document. Do not describe either sweep as pre-registered.
10. `results-uu/` was executed under **two** harness revisions (the
    `MEVChargeHook` re-run), and `results/matrix/`'s field `D` does not pin the
    harness at all — the fee-box clamp lives in `contracts/test/utils/`, one
    directory outside the hash that manifest generation used at the time.
11. `P₀` is `null` in every manifest on disk and the two input checksums are
    constant across all 15,552 cells, so Eq. (9) is not closed by the manifest
    as it stands. Either fix the fields or claim only what is recorded.
12. The `_feeForSender` modelling choice (§2.2 amendment) and the trade-time
    valuation's post-hoc motivation both have to be stated, the latter because
    the 2026-08-09 pre-registration requires it.
