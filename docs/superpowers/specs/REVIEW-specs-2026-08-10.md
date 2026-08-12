# Specification review, 2026-08-10

Reviewer: independent agent. Scope: the five specification documents listed
below, checked by re-deriving every formula and re-computing every numeric
constant that could be checked without running the harness.

Documents reviewed:

- `2026-08-02-dynamic-fee-experiments-design.md` (design; §12.1 is a
  pre-registration)
- `2026-08-04-power-extension-preregistration.md` (**PREREG**)
- `2026-08-09-uu-flow-design.md` (design)
- `2026-08-09-uu-matrix-preregistration.md` (**PREREG**)
- `2026-08-10-kappa-sensitivity-preregistration.md` (**PREREG**)

Nothing was edited. Items inside a pre-registration (including §12.1 of the
2026-08-02 design) are marked **REPORT-ONLY / MUST NOT EDIT** with the
disclosure the paper needs.

Impact tags, used throughout:

- **[NUMBER]** — would change a published number if acted on
- **[CLAIM]** — would change a published claim or an equation printed in the
  paper
- **[COSMETIC]** — wording, notation, arithmetic that does not propagate

What was checked by computation is stated as such; everything else was checked
by derivation.

---

## CONFIRMED DEFECTS

### D1. The slippage justification is wrong by two orders of magnitude **[NUMBER]**

`2026-08-09-uu-flow-design.md` §2.2, third bullet:

> **Slippage is deliberately dropped** (marginal price, not average): at the 20M
> basket a per-minute retail slice (~14k USDT) moves the price ~0.03 bps, two
> orders below the smallest fee.

The ~14k figure is right (I reproduced it: mean per-candle `v₀` = 13,888.89
USDT, from the ETH/SHIB profile at the calibrated κ). The price-impact figure is
not. The basket is split equally by value (design §4.3), so each side of the
pool is worth 10,000,000 USDT. A direction gets `v₀/2`. For a constant-product
pool, `Δx/x = d` moves the marginal price by ≈ `2d` and costs the taker ≈ `d` in
average-vs-marginal execution.

Measured over all 527,040 aligned 2024 candles at the calibrated κ:

| candle | half-slice (USDT) | Δx/x    | marginal move | avg-exec slippage |
| ------ | ----------------- | ------- | ------------- | ----------------- |
| median | 3,159             | 3.16e-4 | 6.3 bps       | 3.2 bps           |
| mean   | 6,944             | 6.94e-4 | 13.9 bps      | 6.9 bps           |
| p90    | 16,095            | 1.61e-3 | 32.2 bps      | 16.1 bps          |
| p99    | 57,694            | 5.77e-3 | 115.4 bps     | 57.7 bps          |
| max    | 606,179           | 6.06e-2 | 1212.4 bps    | 606.2 bps         |

So the true slippage is ~3–7 bps at a typical candle — not 0.03 bps, and not
"two orders below the smallest fee" (1 bps) but three to seven times **above**
it. On more than 1% of candles it exceeds the entire fee box (100 bps).

Three consequences, all load-bearing:

1. **Participation is systematically overstated.** `r` omits a real cost of 3–7
   bps at the mean candle. With λ = 231.05 that inflates `P` by
   `exp(231·0.0007) ≈ 1.17` at the mean candle and ≈ 1.45 at p90 — i.e. 17–45%
   too much retained retail volume, hence too much fee income, in every cell.
2. **The same sentence's companion claim in §4 fails.** §4 says "the fixed UU
   order is arbitrary and documented; sizes are small enough that the ordering
   effect is far below the fee scale". At p99 the A→B swap moves the pool 115
   bps before the B→A swap's `r` is evaluated — larger than the whole fee box.
   The ordering is not innocuous on the tail; it is the tail that carries the
   volume.
3. **It interacts with the κ sweep.** At the sweep's top level (κ×3.0) the mean
   candle's slippage is ~21 bps and p99 is ~173 bps. The highest κ level is
   precisely where the omitted term dominates the fee, so the sweep's shape at
   3.0× is partly an artifact of the omission.

**What to do:** the modelling choice (drop slippage to break the
`P → size → slippage → P` loop) is defensible; the stated magnitude is not.
Restate the limitation with the measured numbers above. If the design spec is
annotated, this is the one place a wrong number is used to justify a wrong
"negligible". Note this is a design spec, not a prereg — it may be corrected,
but the matrix already ran under the model it describes, so the honest move is
an annotation plus a limitation paragraph, not a silent edit.

### D2. The "interior optimum" is an identity of the assumed participation function, not a finding **[CLAIM]** — REPORT-ONLY (UU prereg)

`2026-08-09-uu-matrix-preregistration.md`, "Declared in advance":

> **The degeneracy is expected to be gone.** ... static `net_result` over {5,
> 30, 60, 100} bps was non-monotone with an interior optimum at 30–60 bps.

Under the model, retail fee revenue per direction is `f · (v₀/2) · P(f)` and,
when the pool sits near the external price, `P(f) = exp(−λf)`. The function
`f·exp(−λf)` has an interior maximum at **`f* = 1/λ` for every λ**. With λ =
ln2/0.003 that is `1/231.049 = 43.28 bps`.

This is not a prediction about dynamic fees; it is the first-order condition of
the functional form the spec chose. The observed matrix numbers confirm it
arithmetically. Using PROGRESS.md's own reported participation (0.966 / 0.720 /
0.434 / 0.183 at 5 / 30 / 60 / 100 bps), fee revenue `f·P(f)` is proportional to
4.83e-4 / 2.16e-3 / 2.60e-3 / 1.83e-3 — maximised at 60 bps, which is exactly
the reported interior optimum. Adverse selection changes the level of the curve,
not the location of its peak, at this κ.

Worse, the choice of λ **sets** the optimum's location. Over the declared
λ-sweep {58, 116, 231, 462, 924}, `1/λ` = 172.4 / 86.2 / 43.3 / 21.6 / 10.8 bps.
At λ = 58 the optimum lies outside the fee box [1, 100] bps, so the curve is
monotone again and "the degeneracy" returns; at λ = 924 it sits near the floor.
The λ-sweep is therefore not a robustness check on the finding — it is a sweep
of the finding itself.

And the design spec closes the loop explicitly. `2026-08-09-uu-flow-design.md`
§10, verification item 5:

> **Degeneracy is gone** (the point of it all) ... If it is still monotone at λ
> = 231, λ is recalibrated before the matrix runs.

A free parameter that is retuned until a qualitative result appears makes that
result unfalsifiable. (In the event no retuning was needed — PROGRESS.md
2026-08-09 — so nothing was actually tuned; but the rule was written down as
licensed, and a referee reading §10.5 will notice.)

**Disclosure the paper needs:** state that the existence and approximate
location of the interior static optimum follow from `argmax_f f·exp(−λf) = 1/λ`
given the assumed participation function and the chosen λ, and that the
experiment's contribution at this point is the _policy ranking at a fixed λ_,
not the existence of the optimum. Report `1/λ` next to the measured optimum in
the same table. Do not write a sentence of the form "the experiment shows an
interior optimum exists" without that qualification.

### D3. `net_result_tt` is not "the same quantity valued differently" **[CLAIM]** — REPORT-ONLY (UU prereg)

`2026-08-09-uu-matrix-preregistration.md`, "Quantity":

> Per-window paired difference in net LP result against HODL, in **two
> valuations, both co-primary** ... 2. `net_result_tt` — the same quantity
> valued at trade-time external prices.

and `2026-08-09-uu-flow-design.md` §6:

> **New co-primary valuation `net_result_tt`**: the same LP-vs-HODL quantity
> valued at trade-time external prices.

Write `Δ_t = (Δ0_t, Δ1_t)` for the pool-side balance deltas of swap `t`. Then

```
net_result     = P0_T·Σ_t Δ0_t  +  P1_T·Σ_t Δ1_t
net_result_tt  = Σ_t ( Δ0_t·P0_t + Δ1_t·P1_t )
```

The first depends on the deltas **only through their sum** — it is the terminal
mark-to-market of one portfolio (LP) against another (HODL), and a "valuation
date" is exactly the free parameter in it. The second is a **path integral**: it
depends on the order and timing of the trades and has no single valuation date,
so it cannot be obtained from the first by re-dating the valuation. Their
difference,

```
net_result − net_result_tt = Σ_t [ Δ0_t (P0_T − P0_t) + Δ1_t (P1_T − P1_t) ]
```

is the inventory-revaluation term the spec correctly identifies — but that term
existing is precisely what makes them _different functionals_, not two readings
of one.

There is a second, sharper problem: `net_result_tt` is not a comparison against
HODL at all. HODL is only defined at a valuation date. `net_result_tt` is the
LP's realised (cash-flow) P&L against its counterparties — indeed under arb-only
flow it is identically `−Π_arb^gross`, which is why it is negative by
construction there.

**Consequence:** the two are "terminal mark-to-market P&L" and "realised
transfer P&L". They answer different questions — _did the LP end up richer than
a holder_ versus _did the LP make money on the trades it did_ — and a
disagreement between them is not a valuation artifact to be explained away, it
is two different facts. The prereg's rule ("the disagreement is reported as a
finding, not resolved by choosing the friendlier number") is the right
behaviour; the _description_ is what needs fixing in the paper.

**Disclosure the paper needs:** name them "terminal mark-to-market" and
"realised / trade-time" P&L, define both algebraically as above, and drop the
phrase "the same quantity". Note explicitly that `net_result_tt` carries no
inventory risk and `net_result` does, so an LP's preference between them is a
modelling stance, not a convention.

### D4. `feeMax` unit error in the UU flow design **[NUMBER, if acted on literally]**

`2026-08-09-uu-flow-design.md` §7:

> Its config `feeMax` is set to **10000 pips** for all runs of the new matrix.

`MEVChargeHook.Config.feeMax` is a `uint16` in **basis points** (contract line
56: `uint16 feeMax; // upper bound for base+time+impact`; default `1000`, and
the audit measured swaps at up to 1000 **bps**). Setting it to `10000` would set
the cap to 10000 bps = 100%, i.e. loosen the box a hundredfold instead of
restoring it. The correct value is `100`, which is what
`2026-08-09-uu-matrix-preregistration.md` states ("`feeMax`: 1000 → **100
bps**") and what the harness does (`HookTest.sol:157`,
`MEVChargeHook(flags).setFeeMax(100)`).

So the executed configuration is correct and no published number is currently
wrong — but the design spec, which is the document another agent will verify
code against, states a value that is 100× the intended one in the wrong unit.

Same section, second half of the defect: §7 says only that `feeMax` changes. The
contract's `setFeeMax` reverts unless
`fixedLpFee + flaggedFeeAdditional ≤ feeMax` (line 183), so `30 + 400 > 100`
makes the stated change impossible on its own. The prereg records the forced
companion change (`flaggedFeeAdditional`: 400 → 40 bps); the design spec omits
it, and with it the fact that the surcharge's absolute size fell by 10×.
**Annotate the design spec** to match the prereg.

### D5. κ fixes _potential_ volume; the claimed turnover is never realised **[NUMBER]** — REPORT-ONLY for the κ prereg's wording

`2026-08-09-uu-flow-design.md` §3:

> `κ_pair` — a constant per pair fixing the scale: **mean daily UU volume over
> 2024 equals one basket (20,000,000 USDT)**, i.e. turnover 1×/day.

`experiments/uu.py::kappa` normalises `Σ v_usdt` over a day — the **potential**
volume, before thinning. Executed volume is `v₀ · P`, and PROGRESS.md reports
`uu_participation` of 0.966 / 0.720 / 0.434 / 0.183 across the four static fee
levels. Realised retail turnover at the 30 bps baseline is therefore ≈ 0.72
baskets/day, and it varies by a factor of 5 **across policies**, because it is
endogenous to the fee — which is the whole mechanism of the model.

This propagates directly into the κ prereg, which is where it becomes a
published-axis problem. `2026-08-10-kappa-sensitivity-preregistration.md`:

> **Swept:** κ, as a multiple of the calibrated value ... Reported as **daily
> turnover in baskets**, which is the same number in readable units.

It is not the same number. The κ multiple is potential turnover; realised
turnover is `κ · E[P] ` baskets/day and is a different number at every fee level
and every policy. Labelling the sweep axis "daily turnover in baskets" mislabels
it by up to 5× at the extremes.

**Disclosure the paper needs (κ prereg is REPORT-ONLY):** state that κ
normalises _potential_ retail volume, give the realised turnover per level
beside it, and either relabel the axis "potential daily turnover (baskets)" in
the text or report both columns. The κ prereg already commits to reporting
against "the arbitrage share of volume each level actually produced", which is
the honest axis — that part is right and should be the headline one.

### D6. The κ prereg's "that is arithmetic" is not arithmetic, and is false at low fees **[CLAIM]** — REPORT-ONLY (κ prereg)

`2026-08-10-kappa-sensitivity-preregistration.md`, "Declared in advance":

> Lowering κ must raise the arbitrage share of volume and must reduce the LP's
> net result at every fee level, because adverse selection grows while
> fee-paying volume shrinks. **That is arithmetic, not a finding**, and is
> reported as a check that the axis works.

The first half (arbitrage share rises) is safe. The second half is not. Retail
flow is not unambiguously good for the LP: retail displaces the pool, and the
arbitrageur harvests the displacement. Retail is net-positive to the LP only
when the fee it pays exceeds what its displacement hands the arbitrageur.

Order of magnitude at the mean candle (basket 20M, half-slice 6,944 USDT, ε ≈
1.39e-3, arbitrage profit ≈ `y·ε²/4` with `y` = 10M):

- fee income at 30 bps: `6944 × 0.003 ≈ 20.8` USDT
- arbitrage extraction from that displacement: `1e7 × (1.39e-3)² / 4 ≈ 4.8` USDT
- fee income at **5 bps**: `6944 × 0.0005 ≈ 3.5` USDT — **less** than the
  extraction

So at `MyHook@500` (5 bps), which is one of the six configurations the sweep
runs, reducing κ can _raise_ the LP's net result. The declared "arithmetic
check" can fail for a correct implementation, and the prereg tells whoever runs
it to read a failure as a broken axis.

(The mitigating factor, which should also be in the paper: under `share` mode
the two directions are thinned symmetrically, so the _net_ displacement per
candle is `v₀/2·(P_AB − P_BA)`, near zero when the pool sits at the reference
and the fee is symmetric. That is what makes retail nearly free money here — see
U6 — and it is why the effect above may not bite in practice. It is still not
arithmetic.)

**Disclosure the paper needs:** downgrade this from "arithmetic" to "expected";
if the check fails at 5 bps, report it as the model behaving as a fee-vs-impact
tradeoff, not as a defect.

### D7. The conservation identity in design §14.1 is algebraically wrong as printed **[CLAIM]**

`2026-08-02-dynamic-fee-experiments-design.md` §14.1:

> ```
> LP loss  =  arbitrageur profit  +  gas  −  LP fees
> ```
>
> IL − R_f = (Π_arb + G) − R_f

The bracketed form reduces to `IL = Π_arb + G`, i.e. the `−R_f` cancels and the
prose's "− LP fees" does nothing. Neither reading is right. In a closed system
where gas leaves it,

```
ΔLP + ΔArb + G = 0,  ΔLP = R_f − IL,  ΔArb = arbitrageur profit net of gas
⇒  IL − R_f = ΔArb + G        (equivalently  IL = R_f + ΔArb + G)
```

There is no convention under which the printed equation holds: with `Π_arb` net
of fee (the §A.4 convention, where the fee is already inside `Π*` via γ) the
identity is `IL − R_f = Π_arb`, and with `Π_arb` gross of fee and gas (the §4.2
convention) it is `IL − R_f = Π_arb − R_f − G + G`. The printed version is off
by `G` under one and by `R_f` under the other.

The implementation is evidently right (conservation closes at 1e-16 per
PROGRESS.md). This is a spec/paper equation defect: §14.1 says "This is the only
substantive invariant", and it is the one most likely to be typeset into the
methodology section as-is.

**What to do:** annotate §14.1 with `IL − R_f = Π_arb^net + G` and delete the "−
LP fees" from the prose, or keep the prose and change "LP loss" to mean `IL`
with a `+ LP fees` sign.

### D8. §4.2 and §A.4 state two different entry conditions **[COSMETIC → CLAIM if typeset]**

§4.2: `Π(Δ) − fee(Δ) − gas > 0`. §A.4: "Execution requires `Π* > gas cost`
expressed in the numeraire."

`Π*` in §A.2–A.4 is derived with `γ = 1 − f` inside it (only `γΔx` reaches the
invariant), so the fee is already subtracted. §4.2 subtracts it a second time.
§A.4 is the correct one and the one the harness follows. §4.2 is the version a
reader meets first and the one most likely to be copied into the paper.

### D9. §A.5's "the whole computation reduces to…" is the sell side only **[CLAIM]**

§A.5 derives `Π* = L(s−t)²/s` with `t = √(P/γ)` and concludes:

> The whole computation therefore reduces to: 1. read the current s from
> `slot0`; 2. compute t = √(P/γ); … No bespoke swap arithmetic is needed.

That is the token0-**sell** branch. For the buy branch, §A.4's own
`Π*_{1→0} = (√(Px) − √(y/γ))²` maps, in Uniswap coordinates with `t = √(Pγ)`, to

```
Π*_{1→0} = L (t − s)² / (γ s)
```

— larger by `1/γ`, because the fee is paid in the token the profit is
denominated in and nothing cancels. §A.5 never states this, and the omission
produced a real bug: PROGRESS.md 2026-08-03 audit item 1 records
`ArbMath.profit` using the sell-side form for both directions, suppressing 23 of
80,243 buys whose true profit fell in `[gas, gas/γ]`. Fixed in code; the spec
still reads as though one formula covers both.

**What to do:** annotate §A.5 with the buy-side form. This is the single most
copy-pasted formula in the document.

### D10. §A.8's unimodality argument is false, and the discontinuity is exercised **[NUMBER, potentially]**

§A.8, on the ternary search used for size-dependent policies:

> `Π` stays unimodal because an increasing `f(Δx)` only makes it more concave.

`_calculateImpactFee` (contract lines 463–481) returns `timeFee` when
`impactBps ≤ 500` and `staticFee + ramp` when `impactBps > 500`, where the ramp
is zero at the boundary. So the fee **jumps discontinuously** at `Δx = 0.05·L`,
and the jump is _downward_ whenever `timeFee > staticFee` — i.e. whenever the
15-second cooldown or the flagged bump is active, which PROGRESS.md notes is
almost always the case for a persistent address. A downward fee jump is an
upward jump in `Π`, which creates a second local maximum. A ternary search is
not valid on such a function; it will return whichever local optimum its
bracketing happens to enclose.

This is not hypothetical: the 2026-08-03 audit measured `amount/L` at **1,749.6
bps** for the buy-token0 direction on ETH/SHIB (100% of trades above the 500
trigger), so the search range spans the discontinuity on essentially every buy.

The `Π` shape argument is also weaker than stated even inside a smooth branch —
"increasing `f` makes it more concave" is asserted, not shown.

**Consequence:** the arbitrage pressure against `MEVChargeHook` may be
understated by an unknown amount. This is a spec defect that the code-verifying
agents should be pointed at specifically: check whether the implementation
brackets each branch separately or searches across the jump.

Related, one line: §A.8's "The search range is `[0, Δx*(f_min)]`, since a larger
fee only ever reduces the optimal size" holds only while `γ·p < 4P` (from
`dΔx*/dγ > 0 ⇔ x' < 2x`). True for every realistic deviation here; state it as a
condition rather than as a fact.

### D11. §2.4's discrete mode does not describe the implementation **[COSMETIC]**

`2026-08-09-uu-flow-design.md` §2.4:

> `discrete` draws k ∈ {1..3} potential UU trades per candle (lognormal sizes
> summing in expectation to v₀)

`experiments/uu.py::export_uu_trace` draws exactly **one** lognormal potential
trade per direction (two per candle), mean-preserving via `exp(σZ − σ²/2)`. The
expectation is right (`v₀` in total); `k ∈ {1..3}` does not exist. Discrete mode
is not in the main matrix, so nothing published depends on it — but the
robustness appendix the section promises would be described wrongly.

### D12. Two under-specified definitions that the implementation had to resolve, silently **[NUMBER]**

**(a) Where the fee in `r` is quoted.** §2.2 specifies `r` "evaluated at the
pre-swap pool state, **marginal (zero-size) execution price**". PROGRESS.md
2026-08-10 (night) records that `_uuStep` now quotes the fee at "the candle's
**potential** volume", explicitly as a modelling choice — and that before this
change retail "decided to trade at 30 bps and was charged ~65". Both the old and
the new behaviour are outside what §2.2 says: for a size-dependent policy the
fee is now quoted at `v₀/2` while the charge lands on `v₀/2·P < v₀/2`, so retail
is quoted a fee it will not be charged. The design spec was never amended.
**Annotate §2.2**, otherwise an agent verifying code against spec will flag the
correct implementation as a defect (or bless the wrong one).

**(b) What `uu_participation` is weighted by.** §6 says "volume-weighted mean
P". `metrics.py:290-297` weights by `amountIn` — the **executed** amount, which
is itself `potential × P`. So the published column is `Σ v P² / Σ v P`, not the
participation rate `Σ v P / Σ v`; it is biased upward by the Jensen gap.
Zero-size swaps are additionally skipped and never logged (§4), removing the
low-`P` candles from the average entirely, which biases it up again.

This matters because the number is used as evidence: PROGRESS.md attributes the
whole gap between the observed 0.720 and `exp(−λ·0.003) = 0.500` at 30 bps to
"the signed pool deviation, users trading toward the reference executing
regardless of fee". Part of that gap is the weighting. Notebook 08 plots exactly
this comparison. **Define the weighting in the spec and report the
potential-weighted mean beside it**, or the paper attributes an estimator
artifact to a mechanism.

### D13. The disclosed-peeking section contradicts itself **[CLAIM]** — REPORT-ONLY (UU prereg)

`2026-08-09-uu-matrix-preregistration.md`, "Disclosed peeking":

> the following UU-flow runs were executed and their outputs seen, **all
> confined to ETH/SHIB, window 2024-01-01, `MyHook`**:

then, in the same list:

> one `MEVChargeHook` high-volatility window at 80 gwei checking only the
> fee-box bound, plus two lower-volatility MEVChargeHook probes that produced
> constant 30 bps fees

and immediately after:

> **No other policy's UU behavior and no other window's UU numbers have been
> observed.**

Three MEVChargeHook runs are listed, so the preamble's "confined to … `MyHook`"
is false, and a "high-volatility window" is by construction not 2024-01-01
(2024-01-01 is not in the high tercile — the high tercile picks up 2024-08-05,
per PROGRESS.md). The closing sentence contradicts the bullet three lines above
it.

Against PROGRESS.md the _substance_ of the disclosure checks out: the 2026-08-09
session records exactly the degeneracy check (5/30/60/100 bps → +2258 / +7255 /
+7250 / +4853, matching the prereg's "interior optimum at 30–60 bps"), the
goldens, and adversarial verification. I found no undisclosed peek. The defect
is that the section's own summary sentences overclaim the confinement, which is
the part a referee will test.

**Disclosure the paper needs:** restate the peeking scope accurately — MyHook on
2024-01-01 plus three MEVChargeHook probes including one high-volatility window
— and say that the fee-box bound, not the outcome metric, is what was inspected
on those.

### D14. The κ prereg attributes a pre-registered status the captureShare sweep does not have **[CLAIM]** — REPORT-ONLY (κ prereg)

> this sweep is reported beside it as a robustness analysis, in the same role
> **§12.1's `captureShare` sweep** plays for `PegCapture`.

§12.1 contains no `captureShare` sweep. The only mention in the pre-registered
text is the opposite commitment, in
`2026-08-04-power-extension-preregistration.md`:

> The static fee grid stays at four levels and `captureShare` stays at its
> single configured value.

The sweep was run on 2026-08-03, after the fact, and the repository's own
notebook index calls it "the PegCapture sweep (**not pre-registered**)". If the
paper repeats the κ prereg's sentence it will assert pre-registration for an
exploratory analysis.

### D15. §12.1's Bonferroni justification is wrong twice **[CLAIM]** — REPORT-ONLY (design §12.1 is a prereg)

> Benjamini–Hochberg rather than Bonferroni: with roughly **90 comparisons** the
> Bonferroni threshold is `0.00056`, which a Wilcoxon test on **24 windows**
> cannot reach even at 24 wins out of 24.

- The family §12.1 declares in the paragraph above is 3 regimes × 3 gas × 2
  address modes × 3 pairs × 10 non-baseline configurations = **540** comparisons
  (297 after deduplication, per the 2026-08-04 prereg). "Roughly 90" is the
  count with the address and pair axes dropped. Bonferroni at m = 297 is 1.7e-4,
  not 5.6e-4.
- Each comparison runs on **8** windows, not 24 — the family is stratified by
  regime and there are 8 windows per tercile. This is stated correctly in the
  2026-08-04 prereg ("every comparison in the family is a Wilcoxon signed-rank
  test on 8 paired windows"). With n = 24 the minimum two-sided p is
  `2/2^24 = 1.2e-7`, which reaches 0.00056 easily — the sentence as written is
  false. The same error recurs in §12.1's rationale for the Wilcoxon ("a t-test
  on 24 observations").

The **conclusion survives**: at n = 8 the floor is 0.0078, above Bonferroni at
either m. So no published number changes; the stated reasoning does not support
the stated conclusion.

**Disclosure the paper needs:** if §12.1's reasoning is reproduced in the
methodology, correct m and n there and note that the pre-registration's own
arithmetic was corrected in the 2026-08-04 amendment, which derives the same
conclusion correctly.

### D16. The single most decisive parameter in `PegCapture` is not pinned by any pre-registration, and the design names the wrong value **[NUMBER]**

`2026-08-02-dynamic-fee-experiments-design.md` §5, policy table:

> `PegStabilityHook` | pool deviation from the external price | capture
> (**κ=1**)

The contract's default is `captureShare = 500_000` = **0.5**
(`PegStabilityHook.sol:70`), and 0.5 is what ran. §12.1 pre-registers only
"`captureShare` stays at its single configured value" — it never names the
value. The 2026-08-03 sweep then found that this parameter **flips the sign of
the result** (at 0.10 PegCapture significantly loses in every regime; at 0.75 it
significantly wins).

So: the design spec states a value (1) that was never used, and the
pre-registration pins a parameter by reference rather than by value, for the
parameter that determines the sign of one policy's headline. The saving grace,
which belongs in the paper, is the one PROGRESS.md already identifies — 0.5 is
the _weakest_ winning setting, so the pre-registered choice is conservative.

Also note the notation collision: κ means `captureShare` in design §5 and the
retail-volume scale in the UU documents. Two different κ in one paper, one of
them in a document titled "the κ sensitivity sweep". Rename one.

---

## CONTRADICTIONS

### C1. Output directory: `results/matrix-uu/` vs `results-uu/` **[COSMETIC, but it already cost data]**

`2026-08-09-uu-flow-design.md` §8:

> the new matrix writes to `results/matrix-uu/` (exact-filename filters updated
> — the lesson from the sensitivity-leak defect stands)

`2026-08-09-uu-matrix-preregistration.md`:

> The UU matrix is a third experiment (**`results-uu/`**)

The actual tree has `results-uu/`. The §8 parenthetical is doubly unfortunate
because the collision it claims to have learned from is exactly what then
happened — the κ prereg records it: "the same collision that put the UU matrix's
traces on top of the arb-only experiment's on 2026-08-10", and PROGRESS.md
documents 10,363 arb-only traces destroyed. The design's claimed mitigation
(filename filters) was the wrong mechanism; the directory was never threaded
through. Worth one honest sentence in the reproducibility note.

### C2. "Unchanged axes: 12 policies" — the design says eleven **[CLAIM]**

`2026-08-09-uu-flow-design.md` §8:

> **Unchanged axes: 12 policies** × 2 arb address modes × 3 pairs × 72 windows ×
> 3 gas scenarios.

`2026-08-02-dynamic-fee-experiments-design.md` §5:

> **Eleven configurations in total.**

The 12th is `MEVChargeHookFixed`, added 2026-08-03. It appears in no design
document as an approved configuration; it is introduced only in PROGRESS.md and
then referred to as established in the UU design (§7) and the UU prereg. It is
also the one place §13's discipline ("Policy logic is not changed — otherwise
this ceases to be an evaluation of the existing framework") is bent: the variant
overrides the impact-measure method to make it dimensionless, which is a logic
change, justified and documented but never amended into the design.

Calling the axis "unchanged" while it changed is the problem, not the change
itself. **Annotate the 2026-08-02 design §5 and §9** with the twelfth
configuration and the reason, and say plainly in the paper that
`MEVChargeHookFixed` is a corrected variant authored here, not part of the
evaluated artifact.

### C3. One FDR family or two? **[CLAIM]**

`2026-08-09-uu-matrix-preregistration.md`, "What does not change":

> **Test**: two-sided Wilcoxon signed-rank per comparison, Benjamini–Hochberg
> across **the deduplicated family** at `q = 0.05`

— singular, and it does not say whether the two co-primary valuations form one
family or two. `2026-08-10-kappa-sensitivity-preregistration.md` then declares:

> run on **both** co-primary valuations ... with a **separate family per
> valuation** — they are the same comparisons measured twice and pooling them
> would let a win in one borrow significance from the other

while claiming "Same machinery as the pre-registered analysis and no more". The
implementation chose separate families (PROGRESS.md: notebook 07 "runs the
pre-registered analysis twice with separate FDR control"). So a procedural
choice that the UU prereg left open was fixed after the UU data existed, and the
κ prereg presents it as if it had always been the machinery.

On the statistics themselves, the κ prereg's reasoning is **correct**: BH's
threshold `k·q/m` is adaptive to how many small p-values are present, so pooling
a strongly-significant valuation with a weak one raises the weak one's rejection
count. Separate families is the right call. But it is a choice made after seeing
data, and it is the more conservative direction only for the weaker valuation.

The real gap is downstream of both documents: **neither prereg gives a decision
rule mapping (result under valuation 1, result under valuation 2) to a
conclusion.** Two co-primary families of 297 each control FDR at 0.05 _within_
each; a claim of the form "policy X beats the baseline" that is satisfied by a
win in _either_ is an unadjusted union with roughly double the error rate. The
prereg's "report the disagreement as a finding" prevents the worst version of
this, and PROGRESS.md's ledger does report both counts ("BAHook 21–1 / 21–0"),
which is the honest presentation.

**Disclosure the paper needs:** state that FDR is controlled per valuation, that
every claim is reported under both, and that no claim rests on significance in
one valuation alone. Any sentence of the form "significant after BH" without
naming the valuation is not covered by either pre-registration.

### C4. Declared family vs analysed family: deduplication was never pre-registered **[COSMETIC]**

The 2026-08-04 prereg declares the family as "3 regimes × 3 gas scenarios × 2
address modes × 3 pairs" (540 raw comparisons) and then reports "distinct
comparisons: 297" in its frozen-figures table. The deduplication rule — collapse
comparisons that are bit-identical across the address axis — is documented only
in PROGRESS.md (2026-08-03 audit item 11) and never defined in a prereg; the UU
prereg then refers to "the deduplicated family" as though it were a declared
object. BH is invariant to exact duplication (PROGRESS.md verified zero verdict
changes), so no number moves. But "the deduplicated family" is not
countable-in-advance from any pre-registered text, which is the property a
pre-registered family is supposed to have. One sentence in the paper defining
the rule closes it.

### C5. `net_result_tt` vs the design's declared valuation time **[COSMETIC — properly superseded]**

§12 of the 2026-08-02 design: "Both tokens are valued from their feeds at the
valuation time, **which is the end of the window**." The UU design §6 declares
the second valuation explicitly and the UU prereg declares it before the data,
with the post-hoc motivation disclosed. This is a superseding amendment done
correctly. Noted so nobody flags it later as a silent reopening.

### C6. Randomness **[COSMETIC — properly scoped]**

§7.5 ("no randomness remains … the 'random seed' element of §V-B is absent") vs
UU design §2.4 (seeded PRNG in discrete mode). §2.4 states that share mode is
the default everywhere and that the seed becomes manifest field `S`. Correctly
handled; the paper must not repeat "no randomness" if the discrete appendix
lands.

### C7. 365 vs 366 daily segments **[COSMETIC]**

Design §7.3: "all **365** daily segments are sorted by volatility and cut into
three equally sized groups". 2024 is a leap year; PROGRESS.md and the code
report **366**, hence the 2026-08-04 prereg's "122 days available per tercile"
(366/3 = 122 exactly). Fix the 365 if §7.3 is typeset.

---

## UNSUPPORTED ASSERTIONS

Statements presented as fact with no derivation, citation, or measurement.
Ranked by how much weight the paper puts on them.

**U1. The entire participation model is uncited.** UU design §2: "Carried over
from the group's previous work: a psychological parameter `r` … and an execution
probability `P = exp(−λ|r|)`". No reference, no empirical anchor, no
justification for the exponential form over any other decreasing function. Since
D2 shows the functional form _determines_ the interior optimum at `1/λ`, this is
the single most load-bearing uncited assumption in the third experiment. The
paper needs either a citation to the prior work or an explicit statement that
the form is assumed and the results are conditional on it.

**U2. λ's calibration statement does not match λ's domain.** §2.1: "at a **total
transaction cost** of 30 bps, half of the willing flow executes." `r` contains
the fee and the signed pool deviation only — slippage (D1) and gas are both
explicitly excluded (§2.2). A retail user's _total_ transaction cost includes
both. So λ is calibrated against a broader notion of cost than the one it is
then applied to, which biases participation upward on top of D1. The narrower
statement is exactly true and should replace it: at a pool sitting on the
external price, `r = −f`, so `P(f = 30 bps) = 0.5`. **Away from the external
price the 30 bps interpretation does not hold** — `r ≈ δ − f` where
`δ = p/P_ext − 1` — and the spec's own §2.2 says so, but §2.1's headline
sentence does not carry the caveat.

**U3. "turnover 1×/day, mid-range for real major pools"** (UU design §3) — no
citation. The κ prereg already concedes this and is right to; the concession
should reach the paper, not stop at the prereg.

**U4. "roughly thirty retail traders per arbitrageur"** (κ prereg) — there are
no discrete retail traders in `share` mode; there is a volume ratio (1–6%
arbitrage share ⇒ 16–99×, not "roughly thirty"). Rhetorical, harmless in the
prereg, misleading if it reaches the paper as a count of agents.

**U5. "Arbitrage profit scales as `V·ε²/4`"** (design §4.3). From
`Π* = L(s−t)²/s`, the small-deviation limit is `Π* ≈ y·ε²/4` where `y` is the
**quote-side reserve**, i.e. half the basket. With `V` the basket — which is how
§4.3 reads, since it is discussing 1M vs 20M baskets — it is `V·ε²/8`. Factor 2.

**U6. "a dynamic policy can win honestly — by discriminating between toxic and
benign flow"** (UU design §1). This is the sentence that licenses the strongest
claim in the third experiment, and the model as specified does not support it as
stated. Under `share` mode both directions are thinned deterministically from
the same `v₀`, so when the pool sits near the external price with a symmetric
fee, `P_AB = P_BA` and the retail flows **cancel**: net displacement per candle
is `v₀/2·(P_AB − P_BA) ≈ 0`. Retail therefore delivers fee income with almost no
inventory cost to the LP, by construction. The κ prereg reaches the same
conclusion empirically ("In such a world fee income trivially covers adverse
selection, which is why every policy posts a profit").

The consequence is that the channel through which a policy can win in this
matrix is **fee-revenue optimisation against the participation curve** (D2:
`argmax f·exp(−λf)`), not discrimination between toxic and benign flow — there
is very little toxicity in the benign flow to discriminate against. The one
genuine discrimination channel that survives is _directional_: a policy that
sets `f_AB ≠ f_BA` induces `P_AB ≠ P_BA` and so does move the pool. That is a
real mechanism and it is the ABHook litmus — but it is much narrower than
"discriminating between toxic and benign flow".

**The discrete mode (§2.4) is what would restore order-flow imbalance**, and it
is the thing deferred to "later, time permitting". The paper should say that the
main result is obtained under a flow model in which uninformed flow is balanced
by construction, that this makes uninformed flow unusually benign, and that the
robustness of the ranking to unbalanced uninformed flow is untested.

**U7. "`MEVChargeHookFixed` is expected to remain indistinguishable from static
30 bps"** (UU prereg). Since it charges a constant 30 bps and the baseline
charges a constant 30 bps, the two differ only by gas — so this is a prediction
about the instrument's resolution, not about a mechanism. It was in fact
falsified (22/27 significant losses, median −6.17 USDT = the gas difference),
which is a _good_ outcome for the prereg's credibility, and PROGRESS.md's
handling of it ("detectable because 72 windows are a lot, and economically nil.
Report both numbers or neither") is exactly right. Keep that sentence in the
paper.

**U8. "UU users 'see' the external price (anyone with a price app does)"**
(§2.2). Asserted; it is the assumption that makes the pool-deviation term enter
`r` signed and thereby produces the "users trading toward the reference execute
regardless of fee" effect that PROGRESS.md invokes to explain the participation
gap. It deserves to be listed as a modelling assumption in the limitations, not
as an aside.

---

## VERIFIED SOUND

Everything below I re-derived or re-computed and found correct. This list is as
important as the defect list — the code-verifying agents can rely on these.

**Appendix A, arbitrage mathematics — all correct.**

- §A.2 `Δy = yγΔx/(x+γΔx)`, the derivative `γxy/(x+γΔx)²`, and
  `Δx* = (1/γ)(√(γxy/P) − x)`: re-derived, correct. The positivity condition
  `γy/x > P ⇔ p > P/γ` is correct.
- §A.3 the pool lands exactly at `P/γ` (and `Pγ` for the mirror), and the
  no-arbitrage band `[Pγ, P/γ]`: re-derived both directions, correct. The
  "optimisation collapses to a single target price" claim is right.
- §A.4 both closed forms, `Π*_{0→1} = (√y − √(Px/γ))²` and
  `Π*_{1→0} = (√(Px) − √(y/γ))²`: re-derived by substitution, both exact. The
  worked numerical check (x=y=1, P=0.81, γ=1 ⇒ 0.01) is correct and I reproduced
  it.
- §A.5's coordinate change `x = L/s, y = Ls, xy = L²`, `γΔx* = L(1/t − 1/s)`,
  and `Π* = L(s−t)²/s`: correct **for the sell branch** (see D9 for the missing
  buy branch).
- §A.6 (one `beforeSwap` per swap, so the derivation holds verbatim for a
  dynamic fee) and §A.7 (the asymmetric band `[P(1−f_{1→0}), P/(1−f_{0→1})]`,
  the fragmentation caveat, the no-fixed-point argument): correct.
- §A.8's piecewise fee formula matches `MEVChargeHook._calculateImpactFee`
  exactly, including the `impactBps − 500` numerator and the 9500 denominator,
  and `impactBps = Δx·10⁴/L > 500 ⇔ Δx > 0.05L`. Only the unimodality claim is
  wrong (D10).

**The UU participation model.**

- `r_AB = γ_AB·p/P_ext − 1` and `r_BA = γ_BA·P_ext/p − 1` **are** dimensionless
  and **are** symmetric in the sense the spec claims: each is (what you get
  here) / (what you'd get at the external price) − 1, per unit sold. Direction
  A→B sells token0 and receives `γ·p` token1 against `P_ext` externally;
  direction B→A sells token1 and receives `γ/p` token0 against `1/P_ext`. Both
  reduce to `r ≈ δ − f` for small `δ = p/P_ext − 1`, with the sign of `δ`
  flipping between directions as the spec describes. The "trading toward the
  external price gets a bonus" reading is correct: A→B has `r ≥ 0` exactly when
  the pool overprices token0 by more than the fee.
- λ arithmetic: `ln2/0.003 = 231.0490601866484`, and the WAD constant in the
  prereg, `231_049_060_186_648_440_000`, is that value to the last digit that
  matters. The claimed sweep table
  `P(30 bps) ∈ {0.84, 0.71, 0.50, 0.25, 0.0625}` for λ ∈ {58, 116, 231, 462,
  924} reproduces exactly (0.8403, 0.7061, 0.5001, 0.2501, 0.0625).
- The calibration claim "P = 0.5 at 30 bps" is **exactly true when the pool sits
  at the external price**, since `r = γ − 1 = −f` there. See U2 for the caveat
  the headline sentence drops.
- Discrete mode's lognormal is mean-preserving: `E[exp(σZ − σ²/2)] = 1`.
  Correct.

**κ.** I recomputed κ(ETH/SHIB) from the cached 2024 Binance volumes using the
spec's own rule (per-minute geometric mean of the two legs' quote volume, mean
daily × 1440, basket / that) and obtained **0.05517408261312724** — identical to
the constant fixed in the UU prereg, to all 17 digits. The rule is reproducible
and the number is right. (What the number _means_ is D5.)

**Fee units.** Design §4.5's box, `f_min = 100 pips = 1 bps` and
`f_max = 10000 pips = 100 bps`, is correct in v4's `uint24` hundredths-of-a-bp
convention, and the four static levels 5/30/60/100 bps map correctly to
500/3000/6000/10000 pips. The UU prereg's MEVCharge clamp is unit-consistent
(`feeMax` and `flaggedFeeAdditional` are both `uint16` bps in the contract);
`30 + 40 ≤ 100` satisfies the contract's `setFeeMax` invariant, and 40/100
preserves the 400/1000 = 40% share as claimed. The only unit error found
anywhere is D4.

**Power arithmetic (2026-08-04 prereg).** `p_min = 2/2⁸ = 0.0078125` is the
correct exact two-sided minimum for a Wilcoxon signed-rank test at n = 8, and
`k ≥ 0.0078125 × 297 / 0.05 = 46.4 ⇒ 47` is the correct BH condition. The
reported 58 significant at that floor is consistent with it. The reasoning in
this document — that the original design measured instrument resolution rather
than effect size — is sound and is the most rigorous passage in the whole spec
set.

**Window sets nest.** The κ prereg re-runs κ = 1.0 inside the sweep at 8 windows
per tercile and calls the overlap with the 72-window matrix "a consistency
check". That requires the 8-window set to be a subset of the 24-window set. It
is: with 122 days per tercile, `select_windows(8)` picks indices
{0,15,30,45,61,76,91,106} and `select_windows(24)` picks a superset of them
(verified by executing the selection arithmetic). The consistency check is
well-posed.

**`arb_mtm ≡ −net_result` under arb-only flow** (UU design §6): correct. The
system is closed at end-of-window prices with gas excluded, so the arbitrageur's
marked inventory is the negation of the pool's. The rename from `arb_profit` is
right — the old name asserted realisation the quantity never had.

**Deduplication is BH-invariant** for exact duplicates, so C4 costs nothing
numerically. PROGRESS.md's independent verification (zero verdict changes) is
consistent with the theory.

**The ABHook litmus construction** (design §4.5 / §12.1):
`feeAB + feeBA = K = 6000` pips gives a mean of exactly 30 bps, matching the
static baseline, so budget is held and only allocation varies. The construction
does what it claims. One footnote for the paper: the constant-sum constraint
binds before the shared box does, so ABHook's effective per-direction box is [1,
59] bps, not [1, 100] — already corrected in the code per PROGRESS.md, but the
design spec never says it.

**Scope and claim-boundary language**, section by section: the 2026-08-02
design's §16 risks, §4.2's "upper bound on arbitrage pressure", §4.1.1's mock-
feed caveat, §5's framing of PegDefence's inactivity as "a legitimate finding
about applicability rather than a failure", §12.1's "no difference detected at
this sample size, never no difference exists", and the κ prereg's "A negative
outcome is published" are all correctly bounded and should be preserved
verbatim. The two sentences that reach past the design are U6 (UU design §1) and
UU design §10 item 5 (D2's retuning licence).

---

## Summary, ranked

**Would change a published number if acted on:** D1 (slippage, ~2 orders of
magnitude), D5 (turnover axis mislabelled by the participation factor), D12
(participation estimator and the fee-quote point), D10 (arbitrage pressure
against MEVChargeHook), D16 (captureShare value never pinned).

**Would change a published claim or a printed equation:** D2 (interior optimum
is an identity of `1/λ`), D3 (the two valuations are different functionals), D6
("that is arithmetic" is not), D7 (conservation identity), D9 (buy-side closed
form), D13 (peeking disclosure contradicts itself), D14 (captureShare sweep
mis-attributed to §12.1), D15 (§12.1's m and n), C2 (eleven vs twelve
configurations), C3 (one FDR family or two), U6 (what the model can actually
demonstrate).

**Cosmetic:** D4 (wrong in the spec, right in the code), D8, D11, C1, C4, C5,
C6, C7, U4, U5.

**Single highest-value action:** put D2 and U6 in the paper's limitations in the
authors' own words, before a referee puts them there. The third experiment's
defensible contribution is the _policy ranking at a declared λ and κ under a
declared synthetic flow model_ — not the existence of the interior optimum, and
not "discriminating between toxic and benign flow".
