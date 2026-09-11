# Pre-registration: the κ (retail-scale) sensitivity sweep

Recorded **2026-08-10, before the sweep runs** and before any result at a κ
other than the calibrated one has been computed or seen. Like
`2026-08-04-power-extension-preregistration.md` and
`2026-08-09-uu-matrix-preregistration.md`, this must not be edited once numbers
exist.

## Why this sweep exists

`2026-08-09-uu-flow-design.md` §3 fixes the uninformed-user scale by one rule:

> κ_pair — a constant per pair fixing the scale: **mean daily UU volume over
> 2024 equals one basket (20,000,000 USDT)**, i.e. turnover 1×/day, mid-range
> for real major pools.

Two problems with that sentence, both visible only after the matrix ran.

1. **It carries no citation.** "Turnover 1×/day, mid-range for real major pools"
   is an assertion. It is exactly the kind of author-chosen constant that
   `captureShare` turned out to be, and that sweep found the constant flipped
   the sign of the result.
2. **It fixes the scale on the wrong axis.** Turnover is not what decides this
   experiment; the **share of flow that is informed** is. The calibrated κ
   produced an arbitrage share of **1–6% of volume**, i.e. 16 to 99 units of
   retail flow for every unit of arbitrage flow. In such a world fee income
   trivially covers adverse selection, which is why every policy posts a profit
   and why the "interior optimum" appeared. Whether that optimum is a fact about
   dynamic fees or a fact about κ is currently unknown, and it is the first
   thing a referee will ask.

   > **Corrected 2026-08-10, before the sweep ran (U4).** This said "roughly
   > thirty retail traders per arbitrageur". There are no discrete retail
   > traders in `share` mode — there is a continuum and a volume ratio — and
   > 1–6% is 16–99×, not thirty. Harmless as rhetoric here; misleading if it
   > reaches the paper as a count of agents.

This is disclosed as a limitation of the third experiment regardless of how the
sweep comes out.

## What is swept, and what is held fixed

**Swept:** κ, as a multiple of the calibrated value —
`{0.03, 0.1, 0.3, 1.0, 3.0}`. Reported as **potential daily turnover in
baskets**, which is the same number in readable units, and **also** against the
arbitrage share of volume each level actually produced, because the mapping
between the two is not linear: less retail also means fewer price displacements
for the arbitrageur to correct, so the informed share rises more slowly than
dividing by κ suggests. The **arbitrage-share axis is the headline one**; the
turnover axis is the readable label, not the quantity that decides the
experiment.

> **Corrected 2026-08-10, before the sweep ran (D5).** The word "potential" was
> missing, and without it the sentence is false. κ normalises `Σ v_usdt` over a
> day (`experiments/uu.py::kappa`) — the volume **before** thinning by `P`.
> Realised retail turnover is `κ·E[P]` baskets/day: at the four static fee
> levels of the matrix, participation ran 0.966 / 0.720 / 0.434 / 0.183, so the
> realised figure is a different number at every fee level and every policy, and
> differs from the κ multiple by up to ~5× at the extremes. Labelling the swept
> axis "daily turnover in baskets" mislabels it by that factor. The κ values
> swept, and everything downstream of them, are unaffected — this is the axis's
> name, not its content.

`1.0` is the pre-registered matrix value. It is re-run inside the sweep rather
than joined in from `results-uu/`, so the sweep is self-contained; the overlap
doubles as a consistency check and any disagreement there is itself reportable.

**Held fixed:** λ at its calibrated value (its own sweep is separate and must
not be merged), `uu_mode = share`, basket 20,000,000 USDT, the 2024 window set,
the gas scenarios, `MyHook@3000` as baseline, address mode `persistent`.

> **Corrected 2026-08-10, before the sweep ran.** This named the constant
> directly, as λ = ln(2)/0.003 ≈ 231.05. That constant belongs to the
> **superseded** marginal `r`. `2026-08-10-r-correction-preregistration.md`,
> recorded the same day, redefines `r` as the normalised
> `(V_out − V_in)/(V_out + V_in)` computed from the realised trade, which is
> about half the former magnitude, and rescales λ to **461.404973** for the
> identical calibration statement. This sweep runs on the corrected harness, so
> it runs at λ = 461.404973. The calibration statement — half the willing flow
> walks at a 30 bps total transaction cost — is unchanged, which is why naming
> the statement rather than the constant is the durable form. Nothing else in
> this document depends on the numeric value.

**Restricted, and why:** ETH/SHIB only, seven configurations
(`MyHook@500/3000/6000/10000`, `DAHook`, `BAHook`, `ABHook`), 8 windows per
tercile.

> **Amended 2026-08-11, before this sweep produced a cell.** Two changes, both
> forced by the corrected matrix that landed that morning. The sweep now runs
> **`uu_mode = discrete`**, matching the matrix — running it in `share` would
> have swept κ through a different flow model, and its 1.0× level would not have
> reproduced the matrix at all. And **`DAHook` was added**: the corrected matrix
> made it the only policy with a positive median against the baseline (+245
> USDT, 12 wins to 5), the role `BAHook` held on the withdrawn matrix. `BAHook`
> stays, because it is the policy whose ranking the correction moved most and
> its response to κ is itself informative. The sweep asks whether the _shape_ of
> the result survives, not what the smallest detectable effect is at any one κ.
> The static levels are needed to see whether the interior optimum moves,
> `BAHook` because it is the only policy that won, and `ABHook` because it is
> the litmus the paper highlights. Running all twelve configurations would
> double the cost to re-derive rankings the matrix already reports.

## Declared in advance

- **The direction is asserted for one quantity only.** Lowering κ **must** raise
  the arbitrage share of volume — that is arithmetic, and it is reported as a
  check that the axis works at all.

  The LP's net result is **expected** to fall with κ, but this is a prediction,
  not an identity, and it can fail for a correct implementation. Retail is not
  unambiguously good for the LP: it displaces the pool, and the arbitrageur
  harvests the displacement. Retail pays off only where its fee exceeds what its
  displacement hands the arbitrageur. At the mean candle (basket 20M, half-slice
  6,944 USDT) fee income is ≈ 20.8 USDT at 30 bps and ≈ 3.5 USDT at 5 bps,
  against ≈ **1.1 USDT** handed to the arbitrageur. So the margin at
  `MyHook@500` — one of the six configurations this sweep runs — is thin, and
  less retail may **raise** the LP's net result there. If that happens it is the
  model behaving as a fee-versus-impact tradeoff and is reported as such, not as
  a broken axis.

  > **Corrected 2026-08-10, before the sweep ran.** This read "ε ≈ 1.39e-3,
  > extraction ≈ `y·ε²/4` with `y` = 10M ⇒ ≈ 4.8 USDT extracted — but at 5 bps
  > it is ≈ 3.5 USDT, _less_ than the extraction". The ε came from the
  > specification review's full-range estimate of retail price impact, which
  > `2026-08-10-r-correction-preregistration.md` supersedes: the harness mints a
  > **concentrated** position, so depth near the price is far greater and the
  > measured impact is roughly a third of that — 1.18 bps at the median candle
  > and 1.59 at the mean, against the 6.9 bps the old figure implied. To leading
  > order what the arbitrageur recovers equals what the retail trade gave up in
  > execution cost, `V_r·d` (substituting `y = V_r/d` into `y·ε²/4` with
  > `ε = 2d`), so at the mean candle it is 6,944 × 1.59e-4 ≈ 1.1 USDT, not 4.8.
  > **The qualitative claim is unchanged and is the point of the bullet** — this
  > is a prediction, not arithmetic, and it can fail for a correct
  > implementation. What changes is that the 5 bps level no longer sits on the
  > wrong side of the comparison, so the failure is less likely to be observed.
  > The illustration is corrected rather than deleted because the bullet's
  > standing is a declared expectation and must be read as it will be judged.

  (Mitigating, and also to be stated: under `share` mode both directions are
  thinned symmetrically, so the net per-candle displacement is
  `v₀/2·(P_AB − P_BA)`, near zero when the pool sits at the reference and the
  fee is symmetric. That is why the effect may not bite in practice — it is not
  a reason to call the prediction arithmetic.)

- **The question is whether the interior optimum survives.** Prediction, made
  before the run: the optimal static fee level **rises** as κ falls, and below
  some κ the curve becomes monotone in the fee again — the arb-only degeneracy
  returning. The κ at which that happens is not predicted.
- **Whether `BAHook` keeps its advantage is not predicted.** Its mechanism is
  directional and oracle-driven, so an argument exists in both directions: more
  arbitrage means more for a directional fee to defend against, but also less
  retail whose retention is the source of the gain. This is what the sweep
  measures.
- **A negative outcome is published.** If the interior optimum and the policy
  ranking exist only at 1×/day turnover, the third experiment's claim narrows to
  "under a retail-dominated flow mix", and the paper says so in those words.

## Test

Same machinery as the pre-registered analysis and no more: two-sided Wilcoxon
signed-rank per comparison, Benjamini–Hochberg at `q = 0.05`, run on **both**
co-primary valuations (`net_result`, `net_result_tt`) with a **separate family
per valuation** — they are the same comparisons measured twice and pooling them
would let a win in one borrow significance from the other. Baseline pairing
happens **within** a turnover level; pairing across levels compares two
different worlds and is not a comparison of policies.

Medians in USDT, win rates and `n_effective` are reported beside every
significance flag.

> **Two notes added 2026-08-10, before the sweep ran.**
>
> **(a) "Same machinery … and no more" is not quite true of the code, and it is
> a deviation this document must resolve rather than inherit.**
> `kappa_sensitivity.analyse:232` iterates
> `groupby("regime") + [("ALL", group)]`, adding an `ALL` stratum that is the
> **union** of the three regime strata. Each policy therefore contributes four
> tests, one of which is a superset of the other three, inflating the family by
> 4/3 with non-independent members; §12.1's strata are per-regime. The `ALL` row
> is **excluded from the BH family** and reported, if at all, as a descriptive
> pooled row. No number exists yet, so nothing is retracted by saying so.
>
> **(b) The separate-family-per-valuation rule is stated here as if it were
> established machinery; it is not.** `2026-08-09-uu-matrix-preregistration.md`
> says "Benjamini–Hochberg across the deduplicated family", singular, and never
> resolves whether the two co-primary valuations are one family or two. The
> choice made here is the statistically correct one — BH's threshold `k·q/m` is
> adaptive, so pooling would let a strongly-significant valuation raise the weak
> one's rejection count — but it was fixed **after** the UU data existed. It is
> a post-hoc procedural choice, disclosed as such, not a pre-registered one.

## Separation from the pre-registered results

Outputs go to `results/sensitivity/kappa.csv` and
`results/sensitivity/kappa_tests.csv`, with per-swap traces under
`results/sensitivity/turnover-<multiple>/`. **This sweep is never merged into
`results-uu/` and never enters `analysis-net_result*.csv`.** Its family is its
own; its FDR threshold is its own.

The per-level trace subdirectories are not tidiness. `run_one` names a trace
from the seven experiment axes and κ is not one of them, so a shared directory
would have each level silently overwrite the last — the same collision that put
the UU matrix's traces on top of the arb-only experiment's on 2026-08-10.

## Relationship to the other pre-registrations

Neither the arb-only matrix, the UU matrix, nor the `captureShare` sweep is
re-opened by this document. The UU matrix remains the third experiment and is
reported at κ = 1×; this sweep is reported beside it as a robustness analysis,
in the same role the `captureShare` sweep plays for `PegCapture`.

Both are **exploratory, and neither is pre-registered**. §12.1 contains no
`captureShare` sweep; the only pre-registered statement about that constant is
the opposite commitment in `2026-08-04-power-extension-preregistration.md` --
"`captureShare` stays at its single configured value" -- and the sweep was run
afterwards, on 2026-08-03. The paper must not describe either sweep as
pre-registered.
