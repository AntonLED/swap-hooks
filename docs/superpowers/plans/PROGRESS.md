# Progress checkpoint

Last updated: 2026-08-12, evening. Deadline: 2026-08-18.

## STATE — end of 2026-08-12. Paper-writing phase begins.

**All five κ operating points exist as full matrices on the post-gasfix
harness** (5,832 cells each, 0 errors, conservation ~1e-16):
`results-uu/` (κ=1.0) and `results-uu/turnover-{0.03,0.1,0.3,3}/`.
Measured arb shares: 89/58/25/13/16%.

**Figures (all in `paper/Image/`, CSV beside each, operating-point
stamps):** per-κ regime×gas grids (`uu_*regime_gas_grid{,_rel}` × 5
configs), κ trends `uu_kappa_trend{,_high}`, gas costs
`uu_gas_cost_per_swap`, volume profile `uu_volume_profile`, plus the
notebook 07/08 sets for headline and t01. Drawing scripts:
`analysis/draw_{regime_gas_grid,gas_costs,uu_profile,kappa_trend}.py`
(grids take `UU_CONFIG=headline|informed|t003|t03|t3`).

**Reports:** `docs/reports/2026-08-12-framework-report.md` (EN, complete:
architecture/model/methodology/params-interpreted/results all-κ) and
`.ru.md` (Russian working copy — the owner edits this one; translate back
after). Statistics presentation is bootstrap-interval-only; Wilcoxon/BH
stay computed in CSVs (~96% agreement), one footnote.

**The findings, one paragraph:** pooled, no hook beats a well-chosen
static at ANY κ (`uu_kappa_trend`). Conditionally, the storm ×
cheap-gas corner wins and replicates at every κ with a clean relay:
BAHook owns it at retail-heavy mixes (κ≥0.3; +1,556 at κ=1),
VolatilityHook/DAHook at informed-heavy (κ≤0.1), and at κ=0.03
VolatilityHook wins storms at ALL gas levels. Gas premium (measured:
76k static vs 88–124k hooks) is what kills adaptation elsewhere.

**Still pending:** seed appendix on the fixed harness (owner deferred —
corner claims are one-seed until then); report extras (exec summary,
claim-strength ladder, figure guide) — owner deferred.

**WARNING for the paper phase:**
`docs/superpowers/specs/paper-edits-required-2026-08-10.md` (43 main.tex
edits) predates the gas fix — its numbers (DAHook +341 etc.) are from
withdrawn runs and MUST NOT be applied as written. The current citable
numbers live in the reports and figure CSVs.

## RESULTS — the gas-fix rerun REVERSED the headline, 2026-08-12

**A unit defect invalidated every UU run below this section.**
`_uuGasCost` passed B→A retail gas in token0 units while `UUMath.rWad`
values both legs in token1 — on the volatile pairs B→A retail effectively
paid no gas, so gas thinned only one side of the retail flow and the flow
acquired an artificial directional imbalance growing with the gas price
(AB/BA uu swap counts 543/688 at 5 gwei → 147/541 at 80 on one cell).
Confirmed bit-exactly against a logged `rWad`. Fixed in one line, pinned by
`test_uuHighGasSuppressesBothDirections`, forge 110/110. Contaminated
results archived at `results-uu-gas-unit-defect/` (matrix, turnover-0.1,
κ sweep and seed appendix outputs all predate the fix). Notebooks 09–11
archived under `analysis/archive/pre-gasfix-uu/`; 01–06 (arb-only,
unaffected) under `analysis/archive/arb-only/`; contaminated figures moved
out of `paper/Image/` into the defect archive.

**Rerun of record** (owner's scope: paper keeps ABHook, BAHook, DAHook,
MEVChargeHook): 8 policies (4 hooks + 4 statics) × 3 pairs × 72 windows ×
3 gas = **5,184 cells, 0 errors, worst conservation 5.4e-16**, in
`results-uu/`. Notebooks 07/08 re-executed on it; `uu_*` figures redrawn.

**The headline flipped.** Median across 18 volatile strata vs MyHook@3000
(end-of-window / trade-time):

| policy        | corrected                          | pre-fix (withdrawn) |
| ------------- | ---------------------------------- | ------------------- |
| MyHook@6000   | −2 [−186, +266]                    | +350 vs its own ref |
| BAHook        | −100 [−453, +350]                  | +114 [−108, +549]   |
| DAHook        | **−235 [−381, −104]** / −222       | +341 [+264, +672]   |
| ABHook        | −460 [−630, −288]                  | −254 [−440, −191]   |
| MEVChargeHook | −913 [−1659, −728]                 | (0W/24L)            |

**No dynamic policy beats static 30 bps at the calibrated point.** DAHook's
pre-fix win is attributable to its directional ratchet monetising the
artificial one-sided flow. Static curve 1,644 / 11,890 / 11,932 / 7,936 at
5/30/60/100 bps — the 30–60 plateau is the optimum. IL invariance holds
(fee-income deltas explain the losses; il_delta single digits). Informed
share now RISES with gas, 12.4% → 13.7% — the 2026-08-10 prereg
prediction, which read flat pre-fix, is directionally confirmed.
Participation 0.367 → 0.221 across gas.

**κ = 0.1 probe re-run on the fixed harness (same day): adaptation loses
there too.** 504 cells (7 policies × 24 windows × 3 gas, ETH/SHIB), 0
errors, `results/sensitivity/kappa.csv` + `kappa01-run.log`, driver
`run_kappa_01.py`. Arb share 63.8%. Static curve −300/2,447/3,190/3,349 at
5/30/60/100 — monotone, argmax at the box ceiling. Vs 30 bps over 72
windows: MyHook@6000 +190\*/+126\* wins; DAHook −41/+2 n.s.; ABHook
−79\*/−65\* loses; BAHook mixed (−67 n.s. end vs +42\* tt, all from a
high-regime +461\*/+633\* signal — where static 100 bps gains +1,938\*).
The pre-fix sweep's "BAHook/DAHook positive and significant at every κ" is
withdrawn with its runs. **Still not re-run: seed appendix, the other four
sweep levels, the full κ = 0.1 matrix.** Pre-fix sensitivity outputs
archived at `results-uu-gas-unit-defect/sensitivity-pre-gasfix/`
(capture_share left in place — arb-only, unaffected).

### VolatilityHook recalibration cycle (2026-08-12, after the gas-fix rerun)

Three iterations, run at the owner's direction (formal prereg protocol
waived by the owner mid-cycle; the calibration spec
`2026-08-12-volatilityhook-recalibration-preregistration.md` records the
first iteration's a-priori rule and predictions):

1. **Coefficient rescale** (fBase 5→20 bps, c 20,000→2,000,000, from 2024
   minute-σ quantiles): FAILED −1,267 [−1,979, −565] vs 30 bps. Fee pinned
   at the 100 bps ceiling in storms: the estimator measures variance PER
   UPDATE (swaps land every 3–4 min) against a per-minute calibration.
2. **dt normalisation** (squared change / elapsed minutes, Brownian
   scaling): fee levels now correct (calm ~29 bps, storm ~67, no ceiling
   pinning) but still −809 pooled. Calm-regime loss traced entirely to the
   hook's OWN GAS: 127.5k/swap vs 76.3k static; retail pays it inside `r`
   and walks (retained volume 89/83/67% of baseline at 5/20/80 gwei).
3. **Hot-path slimming** (Welford diagnostic removed, fee/sigma derived on
   read, packed meta slot) + gas re-measured 127,508→123,476 — the oracle
   reads dominate, little to win. Final: pooled −752 [−1,069, −280]; high
   regime covers zero; **by gas: high-vol at 5 gwei POSITIVE on both pairs
   (+191/+692, n.s.), 20 gwei parity, 80 gwei significant loss.**

**The finding:** volatility-tracking creates a storm advantage of the same
order as the policy's own gas premium — realised at cheap gas, destroyed at
dear. The gas axis is what makes this visible.

**κ = 0.1 full matrix re-run post-fix (2026-08-12, evening): 5,832 cells,
0 errors, conservation 4.3e-16, arb share 0.577, 5 zero-trade cells
(stable-pair extremes), `results-uu/turnover-0.1/`.** Notebooks 07/08
executed in `informed` (outputs to scratchpad copies; figures/CSVs in
`paper/Image/uu_t01_*`); grid script parameterised by `UU_CONFIG`
(headline|informed), relative variant refuses non-positive-baseline
panels. **The storm × cheap-gas corner replicates and strengthens:
VolatilityHook +308 end / +499 tt and DAHook +246/+296 beat the baseline
in high-vol × 5 gwei on BOTH valuations; BAHook wins high-vol at all
three gas levels on trade-time only (mixed).** Winner depends on mix:
BAHook at κ = 1.0, VolatilityHook/DAHook at κ = 0.1.

**The regime × gas grid (new figure, `paper/Image/uu_regime_gas_grid.pdf`
+ CSV, drawn by `analysis/draw_regime_gas_grid.py`):** pooling the two
volatile pairs per (regime, gas) panel, **`BAHook` significantly beats the
30 bps baseline in high-vol × 5 gwei (+1,556 [+894, +2,501] end /
+1,481 tt — both valuations) and mid-vol × 5 gwei (+367/+461)**; high ×
20 gwei is mixed (end only); everything at 80 gwei loses. DAHook one
mixed panel; VolatilityHook positive n.s. in the storm-cheap corner. The
conditional headline: adaptation pays where storm earnings exceed the
policy's own gas tax. Estimand caveat: pooled volatile-pair windows, one
seed, corner claim not pre-registered — reported as observed structure. `matrix` now = 9 policies =
5,832 cells; notebooks 07/08 + all `uu_*` figures re-executed on it.
Notebook 07's `assert_one_model` guard REMOVED at the owner's direction
(the matrix dir mixes revisions; a 355-cell differential vs the old
summary showed only CSV round-trip noise, controls confirmed the artifact
rate on untouched policies). Open: owner to choose between reporting this
as the conditional finding vs one more design iteration (oracle-free
pool-price σ estimator, ~100k gas).

Colleague-facing report: `docs/reports/2026-08-12-framework-report.md`
(architecture, model incl. relation to the source Eqs. 8–9 and the λ
rationale, methodology, parameters, corrected results — §10 not yet
updated with the VolatilityHook cycle). Nothing committed.

---

Below this line: state as of 2026-08-11, late. All four runs complete —
matrix, κ sweep, seed appendix, second operating point. **Every UU-flow
number below is superseded by the 2026-08-12 section above.**

## RESULTS — the second operating point (κ = 0.1), 2026-08-11

**7,776 cells, 0 errors, worst conservation 4.3e-16.**
`results-uu/turnover-0.1/summary.csv`.

Arbitrage share by pair: ETH/SHIB **0.514**, ETH/USDC 0.413, USDC/USDT 0.068.
The pre-registration predicted ~0.556 on ETH/SHIB from the sweep; measured
0.514. The prediction about the _mix_ held.

> **Which share.** Those are means of the per-cell shares. Volume-weighted at
> the **baseline policy** — the definition notebook 11 and the figure captions
> use, because it describes the configuration rather than an average over twelve
> policies — ETH/SHIB is **0.148** at κ = 1.0 and **0.558** at κ = 0.1. Pooling
> all twelve policies instead gives 0.216 and 0.621, inflated by `MyHook@10000`
> pricing most retail out. All three are defensible; quoting two of them in the
> same document is not, so the baseline-measured pair is the one that goes in
> the paper.

### The baseline goes negative on the mean, and that breaks the prediction's units

|                                |   κ = 1.0 (headline) |           κ = 0.1 |
| ------------------------------ | -------------------: | ----------------: |
| arbitrage share, ETH/SHIB      |                0.148 |         **0.558** |
| baseline `MyHook@3000`, mean   | **+13,002** USDT/day | **−488** USDT/day |
| baseline `MyHook@3000`, median |              +12,031 |        **+1,201** |

**The mean and the median disagree in sign at κ = 0.1, and that has to be said
both ways.** The typical window still makes money; a minority of windows lose
enough to pull the average below zero. "The LP loses money at this mix" is fair
as a statement about the year an LP actually lives through, and it is false as a
statement about a typical day. Every place this number appears must carry the
median beside it.

With this much less retail, fee income no longer covers adverse selection on
average. The pre-registration predicted "the advantage will be larger than at κ
= 1.0, roughly +10% of the baseline". That statement **cannot be evaluated as
written**: a percentage of a negative baseline is not interpretable, and
dividing by it flips signs. Reported as a prediction whose units did not survive
contact with the configuration, not as a confirmation or a refutation.

In absolute terms, median difference against static 30 bps on the volatile
pairs, with 95% bootstrap intervals:

| policy       |                   κ = 1.0 |                 κ = 0.1 |
| ------------ | ------------------------: | ----------------------: |
| `DAHook`     |     **+341** [+264, +672] |   **+184** [+140, +295] |
| `BAHook`     |         +114 [−108, +549] |        +155 [−28, +713] |
| `ABHook`     |         −254 [−440, −191] |          −47 [−72, −36] |
| `PegDefence` | −10,880 [−20,927, −8,811] | −1,864 [−4,528, −1,274] |

**The intervals in this table were corrected on 2026-08-11 (figures pass).** The
medians are unchanged and reproduce exactly; the intervals recorded earlier that
day — `DAHook` [+64, +647], `BAHook` [−277, +494] — **cannot be reproduced** by
`bootstrap_median_ci` at any seed, on either valuation, on any pair subset. They
came from an intermediate version of the computation and should not be quoted.
The estimand is now stated with the number: **median across the 18 volatile-pair
strata, percentile bootstrap resampling strata**, via
`aggregate.summarise_strata`, which is covered by tests. Pooling the 432
window-level differences instead would narrow every interval by about a factor
of three — and would be wrong, because it treats three gas scenarios of one
window as three independent observations.

The correction does not move any conclusion: `DAHook` still clears zero at both
points, `BAHook` still covers it at both, `ABHook` still loses at both. It
widens `BAHook`'s intervals, which strengthens rather than weakens the reading
that it is not a winner.

So in **dollars** the advantage is _smaller_ at the higher informed share, not
larger — the opposite of what the sweep suggested. What the sweep measured was
the ratio to a baseline that was still positive at 24 windows and one gas
scenario; the full matrix at three gas scenarios drives the baseline below zero
and the ratio stops meaning anything.

The defensible reading, and the one to put in the paper:

> at a retail-dominated mix the LP profits and the adaptive policies add a few
> hundred USDT a day on top; at a mix where arbitrage is about half the volume
> the LP loses money on average and the adaptive policies **reduce that average
> loss by about 60%** without eliminating it

**Corrected 2026-08-11 (breakdown pass): "roughly a third", and `DAHook` turning
−488 into −304, were both wrong.** The −304 was produced by adding a _median_
paired difference (+184) to a _mean_ baseline (−488) — two different estimands,
and the sum is not a quantity. Measured directly, the mean level of `DAHook` at
κ = 0.1 is **−195** against the baseline's **−488**: the average loss falls by
293 USDT per window, or 60%. Do not quote the old figures.

### Where the advantage actually comes from — it is not reduced impermanent loss

Decomposing the paired difference on the volatile pairs:

| policy   | net result | fee income | impermanent loss | retained volume |
| -------- | ---------: | ---------: | ---------------: | --------------: |
| `DAHook` |       +376 |   **+346** |           **−7** |          −1.27M |
| `BAHook` |       +124 |       +182 |              −11 |          −1.75M |
| `ABHook` |       −261 |       −263 |               −1 |          −0.07M |

**`il_delta` is noise at every policy — single-digit USDT against effects in the
hundreds.** That is structural, not a coincidence: for a constant-product pool
impermanent loss depends only on the price the pool ends at, arbitrage pins that
to the external price at the end of every window, and every policy therefore
inherits the same IL. **A fee policy in this model cannot reduce adverse
selection. It can only price flow better.**

So the mechanism is revenue, not protection: `DAHook` charges more, keeps
**1.27M less** volume, and still nets +346 in fees. Any prose saying these hooks
"protect the LP from arbitrage" or "mitigate adverse selection" is not supported
by these runs and must be rewritten as what it is — better fee capture on a
smaller retained flow.

### And it is not achieved by taxing arbitrage

Share of fee income paid by retail, divided by retail's share of volume. A
static fee is 1.000 by construction, which is the control:

| policy       |   κ = 1.0 |   κ = 0.1 |
| ------------ | --------: | --------: |
| `PegCapture` |     0.797 |     0.588 |
| static (any) |     1.000 |     0.998 |
| `BAHook`     |     0.998 |     0.985 |
| `DAHook`     | **1.035** | **1.235** |
| `PegDefence` |     1.254 |     1.976 |

**`DAHook` loads a larger share of fees onto retail than a static fee does**,
and markedly so at the informed-heavy point. The only policy that genuinely
shifts the burden onto arbitrage is `PegCapture`, and it is one of the worst
performers. The framework's own §III framing — discriminating against toxic flow
— is therefore **not** what the winning policy does here, and notebook 08
already says this must be stated plainly when it happens.

### Against the best static fee, not just the pre-registered 30 bps (post-hoc)

The pre-registered baseline is `MyHook@3000`. A reader will immediately ask what
happens against a _well-chosen_ static fee, so: at both points the best static
in the box is `MyHook@6000` (60 bps). **This comparison is exploratory — it was
not pre-registered — and must be labelled as such.**

| policy   |               κ = 1.0 |            κ = 0.1 |
| -------- | --------------------: | -----------------: |
| `DAHook` | **+350 [+224, +449]** | **−2 [−177, +82]** |
| `BAHook` |     +319 [−150, +575] |     −26 [−82, −11] |
| `ABHook` |      −143 [−637, −60] |   −247 [−691, −39] |

At the calibrated point `DAHook` beats even the best static fee, cleanly. **At
the informed-heavy point it is indistinguishable from it, and `BAHook` loses to
it.** At κ = 0.1 the whole ranking by mean level is led by a static 60 bps
(−147) ahead of `BAHook` (−181) and `DAHook` (−195).

That is the sharpest limitation the study has, and it points the same way as
everything else above: what the adaptive policies buy is a better _average_
price for flow, and when the flow is informed enough, a single well-chosen
constant buys the same thing.

### What is stable across both configurations

- **`DAHook` is the only policy whose interval clears zero in both.**
- **`BAHook`'s interval covers zero in both** (−108 to +549, and −28 to +713).
  It is not a winner on effect size at either operating point, despite 10 of 18
  significant strata at each.
- **`ABHook` loses in both**, at every κ in the sweep, and at every seed.
- The catastrophic policies stay catastrophic in rank, though their absolute
  losses shrink with the smaller retail flow they were mispricing.

### RESULTS — the seed appendix at κ = 0.1, 2026-08-11

**960 cells, 0 errors, worst conservation 4.3e-16.** Arbitrage share 0.437.
`results/sensitivity/seeds-turnover-0.1/`.

**Every policy keeps its sign across all five seeds**, as at the headline point.
The second operating point's ranking may now be reported without an "at this
seed" qualifier, on the same terms as the first.

| pair     | policy   |        κ = 1.0 spread |        κ = 0.1 spread |
| -------- | -------- | --------------------: | --------------------: |
| ETH/SHIB | `DAHook` |  +94 … +738 (**644**) |  +350 … +380 (**30**) |
| ETH/SHIB | `BAHook` |  +22 … +696 (**674**) | +227 … +347 (**121**) |
| ETH/SHIB | `ABHook` |     −328 … −222 (105) |        −85 … −18 (67) |
| ETH/USDC | `DAHook` | +232 … +881 (**648**) |  +177 … +208 (**31**) |
| ETH/USDC | `BAHook` |  +26 … +442 (**416**) |  +33 … +213 (**179**) |

**Seed sensitivity collapses at the informed-heavy point** — `DAHook`'s spread
falls from 644 to 30, a factor of twenty. That is mechanical rather than
surprising: most of the per-window variance comes from the retail draw, and
there is ten times less retail to draw. It is worth stating anyway, because it
is the one dimension on which the second operating point is the _better_-behaved
of the two.

#### Two integrity results, and one correction

**Seed 0 of the appendix reproduces the matrix bit for bit** — max |difference|
exactly 0.0 across all 192 cells the two share, at **both** operating points.
The appendix is the matrix on a subset, not a separate simulation.

**But its magnitudes must not be compared to the matrix's.** The appendix runs 8
windows per tercile against the matrix's 24, and that subset is unrepresentative
in an inconsistent direction. `DAHook`, ETH/SHIB, 20 gwei:

|         | appendix's 24 windows | all 72 windows |
| ------- | --------------------: | -------------: |
| κ = 1.0 |                  +284 |       **+484** |
| κ = 0.1 |                  +350 |       **+196** |

The subset **understates** the advantage at one point and **nearly doubles** it
at the other. Notebook 10's prose said "the medians here sit below the
matrix's", which was true at κ = 1.0 by accident and false at κ = 0.1 —
corrected to say the appendix is read for **sign and spread only**, and a
magnitude comes from the matrix.

This also means the appendix must not be used to argue that the dollar advantage
is larger at κ = 0.1. On the full matrix it is smaller (+184 against +341).

### How the appendix runs at both points

`experiments/seed_robustness.py` now takes `--turnover`, so the appendix runs at
either operating point:

```bash
uv run python -m experiments.seed_robustness                  # κ = 1.0
uv run python -m experiments.seed_robustness --turnover 0.1   # κ = 0.1
```

960 cells, ~12 minutes. Two things it does deliberately:

- **Separate output paths per operating point** —
  `results/sensitivity/seeds-turnover-0.1/`, nested rather than a sibling.
  Traces are named from the seven experiment axes and κ is not one of them, so a
  shared directory would have the second point overwrite the first cell for
  cell, and `seeds.csv` carries no κ column to detect it afterwards. Tested.
- **1.0× still means "use the calibrated value"**, not "multiply it by one", so
  the headline appendix keeps running through the identical code path that
  produced the numbers already on disk.

`turnover_multiple` and `uu_kappa` are now recorded per row, so the two tables
cannot be confused once they leave the module.

Notebook 10 takes the same `UU_CONFIG` switch as 07 and 08, writing
`seed_stability.pdf` or `t01_seed_stability.pdf`.

Its prose also carried a claim it could not support — "the advantage of the
adaptive policies over **a well-chosen static fee** survives every realisation".
The appendix compares against the pre-registered 30 bps, not against the best
static, and against the best static the answer differs by operating point (see
the post-hoc table above). Corrected to say what it tests.

### A results artifact was being destroyed by the test suite

Found 2026-08-11 while assembling this breakdown.
`experiments/seed_robustness.analyse()` wrote
`results/sensitivity/seed_tests.csv` **unconditionally**, and
`tests/test_seed_robustness.py` calls it with a fixture. So every `pytest` run
overwrote the real appendix with fixture medians of exactly ±200 / ±100 and p =
0.0078, and the file on disk had been fixture data for an unknown length of
time.

Nothing published was affected: `seeds.csv` is the record and was untouched
since the run, and `paper/Image/seed_stability.csv` (09:55) predates the damage
— regenerating from `seeds.csv` reproduces it value for value. The write is now
gated (`write=` defaults to "only when reading the real run from disk"), the
file is regenerated, and a regression test asserts a fixture run leaves it byte
identical. **Third occurrence in three days of "a run wrote where it should
not"; this class of defect is not being caught by review, only by accident.**

## STATE — 2026-08-11, late. Read this before anything else.

### Nothing is running

All four runs are complete: the headline matrix (κ = 1.0), the κ sweep, the seed
appendix, and the second operating point (κ = 0.1). Results for each are in the
sections below.

**Next compute job** is the seed appendix for κ = 0.1 — five seeds on the
reference cells, ~15 min, same terms as the headline's.
`experiments/ seed_robustness.py` currently hardcodes the calibrated κ; it needs
the same `uu_kappa` override the sweep uses before it can run against this
configuration.

Pre-registration for the second point, written before it ran:
`docs/superpowers/specs/2026-08-11-informed-share-preregistration.md`.

### The second configuration, and why it exists

κ was fixed by a rule about **turnover**; the mechanism depends on the **share
of flow that is informed**, which turnover does not control. At the calibrated κ
the arbitrage share is 13.3%, and the κ sweep showed the advantage of the
adaptive policies is ~+17-21% of baseline at 82% arbitrage falling to under
+1.5% at 18%. **The headline configuration sits at the weakest point of that
curve.**

That is not a reason to move the headline — κ = 1.0 is the calibrated, realistic
turnover, and choosing an operating point because it flatters the result is what
pre-registration exists to prevent. It is a reason to report a second point
(0.1×, arbitrage ~56%) beside it. Both are reported; neither replaces the other;
their FDR families are not pooled.

### The first attempt at it failed entirely, and the guard that now prevents that

All 7,776 cells failed for 26 minutes and it only surfaced at the final
assembly. Cause: `fs_permissions` in `contracts/foundry.toml` is an
**allowlist**, and the run wrote to `results-uu-t0.1/` — a _sibling_ of the
allowed `results-uu/`, not a subtree. Forge aborted in `setUp`, `_worker`
recorded it as a per-cell error, and the sweep continued happily. **Second time
in two days on this same defect class.**

Three fixes, all with tests:

- **Nested, not sibling:** `results-uu/turnover-0.1/`. The allowlist covers a
  subtree — proven by the κ sweep writing to `results/sensitivity/turnover-*/`
  and working — so any future operating point is allowed automatically.
- **Pre-flight guard:** `run_matrix.assert_forge_can_write()` parses
  `fs_permissions` out of `foundry.toml` and refuses to start in a second, with
  the allowed paths listed. Parsed, not hardcoded, so it cannot drift from the
  file it protects.
- **The crash it hid:** when every cell fails there is nothing on disk to
  deduplicate against, and the duplicate-guard merged on an empty frame, raising
  `KeyError: 'policy'` and burying the real cause.

### Bootstrap confidence intervals added; Benjamini–Hochberg kept

`stats.bootstrap_median_ci()` — percentile bootstrap of the median paired
difference, 10,000 resamples, seeded. `analyse()` now returns `ci_low`,
`ci_high`, `ci_excludes_zero` on **every** comparison, not on request.

**It changed a conclusion.** On the volatile pairs (intervals corrected
2026-08-11 — see the correction note in the κ = 0.1 results section; the medians
were always right, the intervals in the first version of this table were not):

| policy   |   median |           95% CI | significant | CI excludes 0 |
| -------- | -------: | ---------------: | ----------: | ------------: |
| `DAHook` | **+341** | **[+263, +672]** |       12/18 |         11/18 |
| `BAHook` |     +114 | **[−108, +549]** |       10/18 |          9/18 |
| `ABHook` |     −254 |     [−440, −191] |       18/18 |         18/18 |

**`BAHook`'s interval covers zero.** It read as a winner on significance (10
significant strata) and is not one on effect size. Consistent with the seed
appendix, where its spread is +22 to +697. `DAHook` clears zero but its interval
is ten times its median — between +0.5% and +5% of baseline.

**BH was deliberately NOT removed**, though it moves only 2 verdicts of 297. It
is pre-registered, and more decisively it only ever _removes_ flags: dropping it
would have _added_ two significant results. Removing a conservative correction
after seeing the data, in the direction of more significance, is the worst
possible post-hoc protocol change. It costs nothing and can only make us claim
less.

### Documentation written today

- **`learning/the-model-end-to-end.md`** (new) — the whole model in one place:
  the two flows, `r`, λ, κ, `share` vs `discrete`, the policies, the candle
  loop, the metrics, the statistics, and a table of **every parameter with its
  status — measured, chosen, assumed, or swept**. That table is the honest core.
  Formulas in LaTeX per the repo convention.
- **`learning/how-our-framework-works.md`** — four model errors fixed, each with
  a dated note: the entry condition double-counted the fee (D8); the closed-form
  profit was given for one branch of two, missing the $1/\gamma$ on the buy side
  (D9); the clock said 12 s and 1 block per candle rather than 60 s and 5; the
  candle loop had no UU step. Also a new subsection deriving **why gas can be
  checked after the optimisation rather than inside it** — gas is
  size-independent, so it shifts the profit curve down without moving its peak,
  and the two-step is strictly equivalent to a one-step. That argument holds
  only because the arbitrageur cannot split a trade.
- **`learning/statistics-for-our-experiment.md`** — new §0, a walkthrough on one
  real stratum from raw numbers through the Wilcoxon computed by hand to the
  code; §18 mapping each step to its file and line; §19 on what each notebook
  does; §0.10 on the bootstrap and the BH decision.

### Figures brought up to the second operating point, 2026-08-11

Every figure of the third experiment now exists for **both** configurations, and
they cannot overwrite each other.

- **Notebooks 07 and 08 take `UU_CONFIG`** — `headline` (default, `results-uu/`,
  figures `uu_*.pdf`) or `informed` (`results-uu/turnover-0.1/`, figures
  `uu_t01_*.pdf`). Analysis CSVs are written beside their own results, so the
  two FDR families stay unpooled by construction rather than by discipline. The
  checked-in notebook outputs are the headline's.
- **Each figure is stamped on its face** with the operating point that drew it
  (`figures.figure_note`, a context manager `_save` reads). Two PDFs with the
  same axes and different numbers are one careless drag apart in a paper, and
  neither would look wrong; a filename is not enough.
- **New: `analysis/11-operating-points.ipynb`** and
  `paper/Image/uu_operating_points.pdf` — the only place the two runs meet. Two
  columns (configuration) × two rows (effect size), every policy once, filled
  marker = bootstrap interval excludes zero. Rows are split because `PegDefence`
  at −10,880 otherwise renders the entire `DAHook`/`BAHook` contest as three
  pixels.
- **`aggregate.summarise_strata`** is now the one definition of the headline
  number — median across the 18 volatile-pair strata, bootstrap over strata —
  with tests. It replaces an ad-hoc computation whose intervals could not be
  reproduced (see the correction above).
- **`CELLS_EXPECTED` fixed to 7,776** in notebook 07. It said 15,552, counting
  the address axis dropped on 2026-08-10, so every run since had printed
  "PARTIAL MATRIX — every number below is provisional" against a total that
  could not be reached.

### Notebook 07 now reads by the interval, not the flag

The bootstrap was added on 2026-08-11 and went into `analyse()` and the CSVs —
but **notebook 07 still told the whole story with `significant_fdr`**. Every
displayed table, the win/loss ledger, the by-pair table and all three
pre-registered prediction checks were flag-driven; the intervals existed on disk
and nowhere a reader would see them. Fixed:

- **A headline table per policy** — `aggregate.summarise_strata` on both
  valuations, written to `headline-net_result.csv` /
  `headline-net_result_tt.csv` beside each run, and drawn as
  `uu_effect_sizes.pdf` / `uu_t01_effect_sizes.pdf` (the single-configuration
  form of `uu_operating_points.pdf`).
- **The ledger counts wins by the interval**, not the flag, and reports the
  undecided comparisons rather than dropping them: 17 wins / 172 losses / **27
  undecided** at κ = 1.0.
- **The by-pair table prints `median [low, high]`** instead of a significance
  star.
- **The prediction checks print effect size, interval, then the flag**, in that
  order of prominence.
- **Agreement across valuations is measured on the interval too** (283/297)
  beside the flag's (288/297), and the two instruments are compared directly:
  they **disagree on 10 of 297 comparisons at κ = 1.0 and 16 of 297 at κ =
  0.1**. That number is the justification for having added the interval at all.

Two defects found while doing it:

- **`uu_*` globs also match `uu_t01_*`**, so the headline run's "here is what I
  drew" listing claimed the other configuration's eight figures as its own.
  `draw_all_uu` now returns the paths it wrote and the notebook prints those.
- **A percentage of a negative baseline was being printed.** At κ = 0.1 the
  `MEVChargeHookFixed` line reported a 52 USDT **loss** as "+10.7% of the
  baseline result" — the sign flips on the negative denominator. The exact trap
  the second pre-registration's prediction fell into, reappearing in a notebook
  cell. It now refuses to print the ratio and says why.

### Open, in order

1. Results of the second configuration (above).
2. Seed appendix for it.
3. **`paper/main.tex` — 43 edits listed in
   `docs/superpowers/specs/paper-edits-required-2026-08-10.md`.** Untouched
   since 2026-08-02 and reserved for the owner; do not edit it.
4. Lead the write-up with effect sizes and intervals, significance second.

## RESULTS — the seed appendix, 2026-08-11

960 cells, 0 errors, worst conservation 5.5e-16.
`results/sensitivity/seeds.csv`, `seed_tests.csv`. Five seeds × the baseline and
three policies × two volatile pairs × 24 windows × 20 gwei, in `discrete` mode.
Design was fixed in the pre-registration before it produced a cell, including
the verdict rule.

Sign stability, end-of-window valuation, median difference against static 30
bps:

| pair     | policy     | seeds positive | unanimous |  min |   median |  max | spread |
| -------- | ---------- | -------------: | --------- | ---: | -------: | ---: | -----: |
| ETH/SHIB | **DAHook** |            5/5 | yes       |  +94 | **+284** | +738 |    644 |
| ETH/SHIB | **BAHook** |            5/5 | yes       |  +22 | **+174** | +697 |    674 |
| ETH/SHIB | ABHook     |            0/5 | yes       | −328 |     −265 | −222 |    105 |
| ETH/USDC | **DAHook** |            5/5 | yes       | +232 | **+387** | +881 |    648 |
| ETH/USDC | **BAHook** |            5/5 | yes       |  +26 | **+281** | +442 |    416 |
| ETH/USDC | ABHook     |            0/5 | yes       | −366 |     −335 | −168 |    198 |

**Every policy keeps its sign across all five seeds.** By the rule declared in
advance, `DAHook` and `BAHook` may now be reported as beating the baseline on
the volatile pairs, and `ABHook` as losing — not merely "at this seed".

**The magnitude is not stable, and the paper must say so.** `BAHook` on ETH/SHIB
has a median of +174 across a range of +22 to +697 — a thirtyfold spread
depending only on the draw. `DAHook` is the firmer of the two: its worst seed is
+94 on ETH/SHIB and +232 on ETH/USDC. The defensible sentence is that the _sign_
of the advantage is robust to the realisation while its _size_ is not, and no
single number may be quoted for it.

The medians here sit below the matrix's (+284 against +569 for `DAHook` on
ETH/SHIB). Not a contradiction: this appendix uses 8 windows per tercile rather
than 24 and one gas scenario rather than three. Sign and order of magnitude
agree.

## RESULTS — the κ sweep, 2026-08-11

2,520 cells, 0 errors, worst conservation 4.9e-16.
`results/sensitivity/kappa.csv`. Seven configurations × five turnover levels ×
24 windows × 3 gas, ETH/SHIB, `discrete` mode to match the matrix.

### The pre-registered prediction is confirmed

The prereg said the optimal static fee would **rise** as κ falls, and that below
some κ the curve would go monotone again — the arb-only degeneracy returning.
Mean `net_result` by static level:

| turnover |  5 bps | 30 bps |     60 bps |   100 bps | argmax   |
| -------- | -----: | -----: | ---------: | --------: | -------- |
| 0.03×    |   −543 |  1,691 |      2,436 | **2,741** | boundary |
| 0.10×    |   −150 |  2,925 |      3,646 | **3,728** | boundary |
| 0.30×    |  1,051 |  6,564 |  **7,275** |     6,401 | interior |
| 1.00×    |  4,504 | 17,270 | **18,097** |    14,010 | interior |
| 3.00×    | 10,155 | 34,711 | **34,988** |    24,969 | interior |

At 0.03–0.10× the best static fee is the ceiling: too little retail, so
suppressing volume wins again. The arbitrage share runs 0.825 → 0.556 → 0.292 →
0.179 → 0.196 across the levels.

### The two winners hold across the entire range

Median difference against static 30 bps, `*` = significant at q = 0.05:

| policy       |  0.03× |    0.10× |    0.30× |    1.00× |     3.00× |
| ------------ | -----: | -------: | -------: | -------: | --------: |
| **BAHook**   | +352\* |   +319\* |   +236\* |    +78\* |    +385\* |
| **DAHook**   | +291\* |   +308\* |   +190\* |   +231\* |       +45 |
| ABHook       |  −38\* |    −60\* |   −110\* |   −211\* |    −363\* |
| MyHook@6000  | +246\* |   +205\* |    +27\* |      −99 |      −870 |
| MyHook@10000 | +269\* |    +69\* |   −490\* | −3,000\* |  −8,937\* |
| MyHook@500   | −637\* | −1,002\* | −2,274\* | −7,361\* | −18,497\* |

**`BAHook` is positive and significant at every level; `DAHook` at four of
five.** The advantage does not depend on where the retail/arbitrage mix sits —
which is exactly what the sweep was built to test, and it passes.

### The apparent contradiction with the matrix, resolved

The matrix reported `BAHook` at a **negative** pooled median (−168, 6 wins
to 13) while the sweep shows +78 at the same κ. Both are right: the sweep is
ETH/SHIB only. By pair, on the matrix:

| policy | ETH/SHIB | ETH/USDC | USDC/USDT |
| ------ | -------: | -------: | --------: |
| DAHook |   +569\* |   +420\* |    −239\* |
| BAHook |   +506\* |   +316\* |    −543\* |
| ABHook |   −302\* |   −379\* |    −403\* |

Significant win/loss by pair — `DAHook` 6W/0L, 6W/0L, 0W/5L; `BAHook` 3W/2L,
3W/2L, **0W/9L**. The pooled negative was the stable pair dragging the volatile
ones down.

**This is the finding.** Both adaptive policies beat a well-chosen static fee on
the two volatile pairs and lose on the stable one — where there is nothing to
adapt to and the adaptation only costs. Pooling the three pairs into one median
hides it, so the paper must report by pair.

`ABHook` — the litmus the paper highlights — loses everywhere, at every κ, and
gets worse as retail grows.

## RESULTS — the corrected matrix landed, 2026-08-11

**7,776 cells, 0 errors, worst conservation 4.9e-16, no zero-trade cells.**
`results-uu/summary.csv`. Notebooks 07 and 08 re-executed on it; 22 `uu_*`
figures redrawn from 7,382,251 swaps.

### The three corrections did what they were meant to

|                                  | withdrawn matrix | corrected matrix             |
| -------------------------------- | ---------------- | ---------------------------- |
| cells with zero arbitrage        | 24.3%            | **6.4%**                     |
| arbitrage share of volume        | 1–3%             | **13.3% mean, 10.7% median** |
| `net_result` across the gas axis | −1.5%            | **−32.2%**                   |
| `uu_participation`, 5 → 80 gwei  | 0.724 → 0.720    | **0.396 → 0.267**            |

Both flows are now genuinely present and gas is a live axis.

### The headline changed completely, and the old one was an artifact

Ledger, significant at `q = 0.05`, end-of-window valuation:

| policy             |   wins | losses | median vs 30 bps | % of baseline | win rate |
| ------------------ | -----: | -----: | ---------------: | ------------: | -------: |
| **DAHook**         | **12** |      5 |         **+245** |     **+1.9%** |     0.56 |
| BAHook             |      6 |     13 |             −168 |         −1.3% |     0.42 |
| ABHook             |      0 |     27 |             −296 |         −2.3% |     0.10 |
| MEVChargeHookFixed |      0 |     27 |             −359 |         −2.8% |     0.10 |
| MEVChargeHook      |      0 |     24 |             −683 |         −5.3% |     0.15 |
| PegCapture         |      0 |     27 |           −4,297 |        −33.0% |     0.02 |
| VolatilityHook     |      0 |     27 |           −8,237 |        −63.4% |     0.00 |
| PegDefence         |      0 |     27 |          −10,687 |        −82.2% |     0.00 |

Baseline `MyHook@3000` averages 13,002 USDT per window.

**`BAHook` was reported as 21 wins to 1 loss on the withdrawn matrix. It is now
6 to 13.** **`MEVChargeHook` was 18 wins to 9; it is now 0 to 24** — its
advantage was entirely the zero-size fee quote, exactly as the differential
predicted. Nothing from the withdrawn run's ranking survived, which is why that
matrix is withdrawn rather than merely superseded.

**Read the effect sizes beside the flags.** The only winner beats the baseline
by **1.9%** with a win rate of **0.56** — statistically clear across 24 windows,
economically slight. The losses at the bottom are the opposite: PegDefence gives
up 82% of the baseline result.

Valuations agree on 288 of 297 distinct comparisons, with 8 sign flips.

### A pre-registered prediction failed, and is reported as such

`2026-08-10-r-correction-preregistration.md` declared that the **informed share
would rise with gas**, expensive gas pricing out the small retail draws first.
It did on the six-window calibration probe (12.5% → 14.3%). **On the full matrix
it does not**: 0.1388 → 0.1300 across 5 → 80 gwei, essentially flat. Gas prices
out both sides roughly proportionally. The mechanism is real in the model but
too weak to survive at scale, and the paper reports the prediction and its
failure together.

### The interior optimum is where the model says it is

Static curve, mean `net_result`: 2,016 / 13,002 / 13,040 / 8,611 at 5 / 30 / 60
/ 100 bps — interior, argmax at 60 bps on a four-point grid, against
`2/λ = 43.3 bps`. This is the D2 point holding: the optimum's existence and
location follow from the assumed participation function, not from the data.
Participation falls 0.538 → 0.328 → 0.178 → 0.081, monotone as required.

`PegDefence` fires under UU flow — 73.3% at its floor on its worst pair against
100% under arb-only — so the mechanism is live. It is still last by a wide
margin.

### Two contaminations caught while regenerating

- **7,776 stale `-fresh` traces** from the withdrawn matrix sat in
  `results-uu/`. The new run never overwrote them because the address axis is
  gone, and notebook 08 pooled them with the real ones. Moved to
  `results-uu-preflight-defect/withdrawn-fresh-traces/`. `results-uu/` now holds
  exactly 7,776, one per cell.
- **Notebook 07 crashed** with `KeyError: 'fresh'` — its address-mode cell
  pivoted on two modes. It now reports that the axis was dropped, and why.

## Configuration of record (the run above used this)

**Nothing is running.** The matrix is complete. Relaunching is only needed if
something changes:

```bash
export PATH="$HOME/.foundry/bin:$PATH"
caffeinate -is uv run python run_matrix.py --uu 2>&1 | tee -a results-uu/run-discrete.log
```

`caffeinate -is` is not optional — an earlier run died at 07:47 to clamshell
sleep. Completed cells are skipped by manifest.

Do **not** judge progress by counting files. `results-uu/matrix/` still holds
15,552 metrics files from the withdrawn matrix, overwritten in place as cells
complete; the file count reads 15,552 from the first second. Read the log.

### What the experiment is now

|         |                                                                                     |
| ------- | ----------------------------------------------------------------------------------- |
| `r`     | the source model's `(V_out − V_in − G)/(V_out + V_in + G)`, from the realised trade |
| λ       | 461_404_973_192_736_927_635 WAD (461.404973)                                        |
| UU mode | **`discrete`**, seed 0                                                              |
| κ       | calibrated, unchanged (one basket of retail per day)                                |
| gas     | paid by retail as well as the arbitrageur                                           |
| axes    | 12 policies × 3 pairs × 72 windows × 3 gas = **7,776 cells**, ~1.5 h                |

The model of record is
`docs/superpowers/specs/2026-08-10-r-correction-preregistration.md`. Every
change above is recorded there, and all of it was written before the first cell
existed.

### Everything from 2026-08-10 that a future session must not re-derive

Four review agents ran (two on the code, two on the specs). Their outputs are
`REVIEW-specs-2026-08-10.md` and `REVIEW-traceability-2026-08-10.md`, plus
`tests/test_adversarial_econ.py` and `tests/test_audit_changes.py`. Between them
they found 16 spec defects, 7 contradictions and 8 unsupported assertions, and
13 failing tests — all since fixed or explained.

**The three that changed what the experiment is:**

1. **`r` was never the model we cite.** The owner produced the source paper's
   slide: `r = δP(Δx,Δy)/δP(|Δx|,|Δy|)`. The implementation used a marginal
   relative price disadvantage — twice the source magnitude, and with slippage
   excluded. Corrected; λ doubled to keep the same calibration statement.
2. **Retail crowded the arbitrageur out.** Under `share` mode both directions
   get equal potential volume and are thinned by their own `P`, so the flows
   cancel and the pool is never displaced: measured on the withdrawn matrix,
   **24.3% of cells had exactly zero arbitrage volume and 46.8% had under 1%**.
   `discrete` mode draws each direction independently and executes
   all-or-nothing, which restores one-sided flow: arb share 1.1% → 10.9%, zero
   empty cells.
3. **Retail paid no gas, so the gas axis was inert.** Raising gas 5 → 80 gwei
   multiplied the arbitrageur's gas bill sixteenfold and moved `net_result` by
   −1.46%, with `uu_participation` flat at 0.7238 → 0.7200. Gas now enters `r`.
   After: `net_result` moves **−19.5%** across the axis, participation 0.42 →
   0.32, and the **informed share rises with gas** (12.5% → 14.3%) as expensive
   gas prices out the small retail draws first.

Point 3 is expressible only in `discrete` mode: a continuum of infinitesimal
users has no per-user gas.

**What the reviews got wrong, and must not be re-applied:**

- **D10 (fee jumps down at the 500 bps impact trigger) is FALSE.** The reviewer
  read `_calculateImpactFee` without the `max(impactFee, timeFee)` at its call
  site; the impact branch starts at exactly `staticFee ≤ timeFee`, so the
  applied fee is continuous and non-decreasing in size. Verified numerically
  across the whole cooldown ramp. The ternary search is sound.
  `contracts/test/SizeSearchUnimodal.t.sol` previously tested a smooth linear
  surcharge — the wrong function — and now exercises the real shape.
- **D1's slippage magnitudes were ~3× too large.** The review computed impact
  against a full-range pool; the harness mints a concentrated position. Measured
  on 2,760 real swaps: **1.18 bps median, 1.59 mean, 7.21 p99**, not 3.2 / 6.9 /
  57.7. The qualitative point stands — the spec claimed 0.03 bps.

**Two axes examined for trimming, with numbers:**

- **Address mode: empty.** `fresh` and `persistent` agreed to the last bit in
  all 7,776 paired cells, for every policy including MEVChargeHook. Dropped.
- **Gas: kept.** Between-group variance of the paired delta was 0.0000 and the
  ranking was identical across all three scenarios — but that was measured where
  the arbitrageur was crowded out and retail paid no gas. Both are now fixed,
  and the axis moves the result by −19.5%.
- **Pairs: kept.** All three carry signal, and USDC/USDT has a _different_
  winner (`MyHook@6000`, not `MEVChargeHook`), which is its own result.
- **Windows: never cut.** 24 per tercile is the 2026-08-04 power extension; at 8
  the smallest two-sided Wilcoxon p-value is bounded at 0.0078 and no isolated
  effect survives BH.

**A known limitation, declared rather than hidden.** The implementation draws
ONE lognormal trade per direction per candle. Spec §2.4's `k ∈ {1..3}` was never
implemented. Since the imbalance of `k` independent arrivals falls as `1/√k` and
`share` is the `k → ∞` limit, **`k = 1` is the most imbalanced assumption
available**. Real per-minute arrival counts are far higher, so the truth lies
between — and genuine imbalance comes from correlated demand, which neither mode
models. `discrete` also makes results seed-dependent: a seed-robustness appendix
(a few cells × 5 seeds) is required before any ranking is called stable.

### Waiting, not started

- `docs/superpowers/specs/paper-edits-required-2026-08-10.md` — **43 edits**
  `main.tex` needs, each with the current sentence, replacement text and the
  evidence. `paper/main.tex` and `reference.bib` are **untouched since
  2026-08-02** and stay that way; the owner applies these himself.
- `experiments/kappa_sensitivity.py` + its pre-registration — 2,160 cells, ~2 h,
  run after the matrix.
- `paper/Image/uu_*.pdf` — nine figures drawn from the **withdrawn** matrix.
  None may enter the paper until redrawn from notebooks 07/08.
- Notebooks 07 and 08 need re-executing once the matrix lands.

Suites at end of day: **341 Python** (6 deselected, 2 xfail whose references
only become valid after this run), **109 Solidity**. Nothing committed.

## Session 2026-08-10 (late): `r` corrected to the source model, matrix re-running

### The headline: `r` was never the model we cite

Four review agents ran against the code and the specs. The decisive finding came
from the owner, who produced the source paper's slide:

```
r = δP(Δx, Δy) / δP(|Δx|, |Δy|)        P = 1 if r >= 0 else exp(-|r|)
```

The implementation computed `r = γ·p/P_ext − 1`, a marginal relative price
disadvantage. Two differences, both load-bearing:

1. **The normalisation was dropped.** With `V_in`, `V_out` the two legs at the
   external price, the source `r` is `(V_out−V_in)/(V_out+V_in) = −ε/(2−ε)` —
   about **half** the fractional disadvantage. The implemented form was `−ε`. λ
   therefore had to double: **461.404973**, WAD `461_404_973_192_736_927_635`,
   to preserve "half the willing flow walks at a 30 bps total cost".
2. **Slippage left the model.** `Δy` is what the pool actually pays, so the
   finite-size cost is inside the source `r`. The design spec justified dropping
   it with "~0.03 bps, two orders below the smallest fee". Measured on the 2,760
   UU swaps of one real day by differencing the recorded `r` against the same
   `r` at zero size: **1.18 bps median, 1.59 mean, 7.21 at p99** — thirty times
   the claimed figure and above the 1 bp floor, though inside the box.

   The review's own estimate (3.2 median / 6.9 mean / 57.7 p99) assumed a
   full-range pool; the harness mints a concentrated position, so the real
   impact is about a third of that. Numbers to quote are the measured ones.

`UUMath.rWad` now takes liquidity and a size and derives the output from
`SqrtPriceMath`, so the rounding matches the pool. It is evaluated at the
candle's **potential** slice — known before `P`, so the `fee → P → size → fee`
loop stays broken. The old form survives as `rWadMarginal`, with its 22 tests
retargeted, purely so the differential is inspectable.

Recorded in `2026-08-10-r-correction-preregistration.md` before the run. The
2026-08-10 matrix is **superseded and withdrawn**; it lives at
`results-uu-preflight-defect/` as evidence and is cited nowhere else.

### What "must not edit" actually covers

Three documents of seven are frozen, and only because data exists for them:
`2026-08-04-power-extension`, `2026-08-09-uu-matrix`, and design §12.1. A bad
pre-registration is not repaired by editing — that destroys the only thing it is
evidence of — it is superseded by a new one that discloses the defect.

Everything else is editable and was edited: both design specs, and **both of
today's pre-registrations, because neither has produced a cell yet**. The κ
prereg's "that is arithmetic" claim was downgraded to "expected" (it is false at
5 bps, where retail's fee income is less than the arbitrage extraction its
displacement funds), and its false attribution of pre-registered status to the
`captureShare` sweep was removed.

### Everything else fixed before launching

`uu_participation` (mixed token0/token1 wei in the weights, and weighting by the
executed volume, giving E[P²]/E[P]) → the USDT retention rate. NaN handling in
`wilcoxon_paired` and `benjamini_hochberg` — the latter's `sorted()` left the
family unordered and flipped verdicts for unrelated comparisons. The snapshot
leak on `_optimalSize`'s early return, and a second in
`_countTradesWithGasPrice`. `FEE_BOXES_BPS` for the MEVCharge clamp. The
duplicate-row bug in `collect()` (confirmed in the wild: 15,850 rows for a
15,552-cell matrix, the excess exactly the 298 failures). `--pair` truncating
the summary, and unknown pairs silently emptying it. The κ sweep's private gas
default.

**And the manifest's two dead fields.** `P0` was literally `null` in all 15,552
manifests; `input_checksum` was a hash of the shared scratch files in `data/`
and read `d3b98a44090795fd` for every cell of both matrices — it could not
detect the data change it exists to detect. `run_one.window_fingerprint` now
hashes the window's own aligned candles and returns the opening external prices
with them. One second per distinct window, cached. Eq. (9) is closed for the
first time.

### The 298 failures were mine

I edited `UUMath.sol` and `Replay.t.sol` while eleven forge workers were live.
Between the two edits the harness called `rWad` with the old four-argument
signature against the new six-argument one, so every cell in that window failed
to compile. I had told the agents not to touch the harness during a run and then
did it myself. Nothing is lost — those cells are superseded — but the rule is
now: **no source edits while a run is live, none.**

### One arb-only figure was lost, and it is out of `paper/Image/`

`fee_distribution.{pdf,png,csv}` was redrawn at 15:04 by the first execution of
notebook 03 — **before** the `HAVE_TRACES` guard existed. It therefore drew from
the three stray traces that survived the seven-field filter: 11 swaps of
`MyHook@3000` and 893 of `PegDefence`, two policies, against the 147,880 swaps
across ten policies the real figure carried. The valid version was overwritten
and cannot be regenerated — the arb-only traces are gone.

The three files are moved to `results-uu-preflight-defect/clobbered-figures/`
rather than deleted, so nobody includes a fee distribution built from 904 swaps
and the incident stays inspectable. **`paper/Image/` no longer holds a
`fee_distribution` figure at all**, which is the correct state: absent beats
wrong.

What that figure showed is recorded in the 2026-08-03 entry below — `PegDefence`
pinned at its 1 bps floor on 100% of swaps, `MEVChargeHook` regime-split at 98%
at floor on ETH/USDC against a 236 bps median on ETH/SHIB. Those numbers survive
in prose and in this file; the figure does not.

Checked at the same time: `fee_detail_*` (2026-08-04) and `fee_response`
(2026-08-09) are untouched, and the damage is exactly these three files.

**`paper/main.tex` and `paper/reference.bib` are untouched, last modified
2026-08-02.** Only `paper/Image/` has changed, and every `uu_*` figure in it is
drawn from the superseded matrix — none of them may enter the paper until they
are redrawn from the corrected run.

### State at launch — SUPERSEDED the same evening

This section launched a 15,552-cell run at `results-uu/run-corrected-r.log` in
`share` mode with the address axis intact. It was stopped twice and replaced:
first because the verification pass was not finished (it found D10 to be a false
positive and D1's magnitudes to be wrong), then because the arbitrageur turned
out to be crowded out of it entirely. **Read the "state at end of 2026-08-10"
section at the top of this file instead** — the experiment now runs `discrete`
mode with retail gas, 7,776 cells.

## Session 2026-08-10 (night): fee-quote fix, full re-run, κ sweep prepared

### `_feeForSender` fixed, and it needed a manifest fix to matter

`Replay.t.sol` now quotes the fee at the amount actually being swapped instead
of at `amountSpecified: 0`. Two call sites, three changes:

- **Logging** (`_executeUU`, `_executeArb`): quoted at the executed `amountIn`,
  so the logged fee is the fee the pool charged.
- **UU participation** (`_uuStep`): quoted at the candle's **potential** volume,
  known before `P`. Quoting at the _actual_ amount would reintroduce a loop —
  fee → P → size → fee — and spec §2.2 already dropped slippage to break the
  identical loop. Recorded as a modelling choice, not a silent one.

**`manifest.source_hash` hashed only `contracts/src/`.** `Replay.t.sol` is in
`contracts/test/`, so this change would have left all 15,552 manifests
byte-identical and a rerun would have skipped every cell — precisely the hole
field `D` exists to close, one directory over. Now hashes `src/` **and**
`test/`, with a test.

### Differential: what the fix moves, and what it must not

Re-ran seven cells (ETH/SHIB, 2024-01-01, 20 gwei) against the stored metrics:

| policy                                                      | outcome                                                 |
| ----------------------------------------------------------- | ------------------------------------------------------- |
| PegCapture, VolatilityHook, MyHook@3000, MEVChargeHookFixed | **bit-identical**                                       |
| BAHook, ABHook                                              | `gas_cost` only, −0.5%; every economic metric identical |
| **MEVChargeHook**                                           | fee income **15,720 → 6,925**, −56%                     |

That is the whole finding in one line: once retail is quoted the price it will
actually pay, MEVChargeHook's inflated fee income collapses. Its second-place
ranking was an artifact. The `gas_cost` drift on the two oracle hooks is the
warm-storage instrumentation drift already documented on 2026-08-03; it enters
no conclusion and `trade_count` is unchanged.

### Only MEVChargeHook is being re-run, not the matrix

First attempt was a **full** 15,552-cell re-run, because extending `source_hash`
to `contracts/test/` invalidated every manifest at once. That is 13 h of wall
time to correct one policy, and the owner stopped it — correctly. Aborted at 209
cells, all `BAHook`, whose only change is `gas_cost`; those were restored
byte-for-byte from `results-uu-preflight-defect/` (verified: 31,104 files
compared, 0 differ). Now running `--policy MEVChargeHook`, 1,296 cells, ~75 min,
log at `results-uu/run-mevcharge.log`.

**Consequence to state in the paper's reproducibility note:** eleven policies
carry manifests from the pre-fix harness and `MEVChargeHook` from the post-fix
one. The differential above is what licenses that — the fix is provably inert
for the other eleven except `gas_cost` on two, and `gas_cost` enters no
conclusion.

Two runner defects fixed on the way:

- **`--policy` did not exist.** Added, with the same shape as `--pair`.
- **A restricted run truncated `summary.csv`.** It was written from the runner's
  return value, so `--pair ETH/SHIB` would have left the file every notebook
  reads describing one pair while the other two thirds sat on disk unmentioned.
  `matrix.collect` now rebuilds it from every metrics file on disk regardless of
  what this invocation ran.

### Notebooks 01-06 brought up to date

They were deliberately not touched when the UU work landed, and had drifted:

- **`arb_profit` → `arb_mtm`.** But the frozen `results/summary.csv` predates
  the rename and still carries the old name, so 05 and 06 resolve it once
  (`ARB_MTM = "arb_mtm" if ... else "arb_profit"`) rather than hardcoding
  either. Hardcoding the new name was my first attempt and it broke both.
- **Window counts.** 24 per tercile = 72 per pair since the power extension. 01
  and 02 said "24 per pair" (the pre-extension number); 06's "24 windows per
  regime" was already right and was left alone.
- **Dead traces.** 03, 05 and 06 read per-swap traces from `results/`, which no
  longer holds arb-only ones. Each now counts seven-field traces at the top,
  sets `HAVE_TRACES`, and skips the dependent cells with a printed explanation.
  Guarding matters more than failing: `applied_fees` would otherwise have drawn
  a fee figure from the three ad-hoc probes that survive the filter.
- 05 also drops trace-derived entries from its `METRICS` list by presence, so
  the list cannot drift out of step with a second one.

All six execute end to end and are committed with outputs. **06 reports 19 PASS
/ 0 FAIL** with the trace checks skipped.

### Superseded: the full matrix re-run

Launched `caffeinate -is .venv/bin/python3 run_matrix.py --uu`, log at
`results-uu/run.log`. All 15,552 cells are pending, which confirms the manifest
fix works. **Wall time is ~13 h, not the ~4 h estimated earlier** — that
estimate was taken from the tail of cheap `MyHook` cells; the full matrix with
the oracle hooks took ~13 h of compute the first time too.

The pre-fix results are archived under **`results-uu-preflight-defect/`**
(metrics and manifests only, 188 MB — traces not copied). Keep them: the
before/after on MEVChargeHook is the evidence for the write-up.

Watch it with `tail -f results-uu/run.log`. Do **not** count files —
`results-uu/matrix/` already holds all 15,552 from the previous run and they are
overwritten in place, so the file count reads 15,552 from the first second.

### κ sweep written, not yet run

`experiments/kappa_sensitivity.py` plus
`docs/superpowers/specs/2026-08-10-kappa-sensitivity-preregistration.md`,
recorded before any non-calibrated κ result exists. 2,160 cells: 6
configurations × 5 turnover levels × 24 windows × 3 gas scenarios, ETH/SHIB, ~2
h. Grid is `{0.03, 0.1, 0.3, 1.0, 3.0}` × the calibrated κ, spread downward
because the open question is what happens when arbitrage stops being 1–6% of
flow. Reported against the **arbitrage share of volume** each level produced,
not only against the input.

`run_one` gained `uu_kappa=None` (None = the calibrated constant, so every
existing call is unchanged). Each turnover level writes traces to its own
`results/sensitivity/turnover-<multiple>/`: `run_one` names a trace from the
seven experiment axes and κ is not one of them, so a shared directory would have
each level overwrite the last.

Cannot start until the MEVChargeHook re-run finishes — both are CPU-bound on all
cores.

156 Python tests green, forge 109/109. The five `ruff check` findings
(`metrics.py` SIM114, four in `test_uu_adversarial.py`) predate this session and
are untouched.

## Session 2026-08-10 (evening): the UU matrix landed

**15,552 / 15,552 cells, 0 errors, worst conservation 6.4e-16, zero zero-trade
cells** (USDC/USDT trades now — UU flow always trades). `results-uu/summary.csv`
and `analysis.csv` written. Notebooks 07 and 08 executed end to end on the full
matrix and committed with outputs. forge 109/109, pytest 140/140.

### Trace directory repaired — the defect had a second half

Threading `results_dir` through `execute_parallel` → `_worker` → `run_spec` →
`run_one` was **not sufficient**. `contracts/foundry.toml` `fs_permissions` is a
path allowlist and only had `../results/`; with the directory threaded but not
allowlisted, forge fails outright. That is why the original fallback to
`results/` looked like it worked. Both halves are now fixed
(`{access = "read-write", path = "../results-uu/"}`).

15,551 traces moved `results/` → `results-uu/`, classified **by content** (a
file moves only if it contains a `"trader":"uu"` swap), with mtime used only to
cross-check. One disagreement, and it was real: the golden-window cell
`MyHook@3000 / ETH-SHIB / 2024-01-01 / 20 gwei / persistent` had its UU trace
overwritten at 14:39:45 — two minutes after the matrix finished — by an arb-only
`run_one`, i.e. somebody ran `pytest -m slow`. Regenerated; the regenerated
metrics are **bit-identical** to what the matrix stored at 11:51, which is a
free end-to-end reproducibility check on the whole pipeline. `results-uu/` now
holds all 15,552.

Left behind in `results/`: 1,524 sensitivity `-cs` traces, 3 ad-hoc arb-only
probes at 1 gwei, and 4 `_replayuu_*.jsonl` fixtures the Solidity tests write.
All are invisible to the seven-field filter.

### Headline results

- **The degeneracy is gone, as pre-registered.** Static net result over
  5/30/60/100 bps is 5,749 → 37,675 → 41,089 → 22,354, an **interior optimum at
  60 bps**, under _both_ valuations. Participation falls 0.966 → 0.720 → 0.434 →
  0.183, tracking `exp(−λ·fee)` from above — the gap is the signed pool
  deviation, users trading toward the reference executing regardless of fee.
- **The valuation-timing worry largely dissolves under UU flow.** 285 of 297
  distinct comparisons agree across the two valuations and **no paired median
  changes sign**. The 12 disagreements are all borderline (p either side of the
  threshold). Declaring both was still right; it did not change the story.
- **Ledger, significant at q = 0.05** (end-of-window / trade-time). BAHook 21
  wins–1 loss / 21–0; MEVChargeHook 18–9 / 18–9; DAHook 3–17 / 3–17; ABHook,
  MEVChargeHookFixed, PegCapture, PegDefence, VolatilityHook: **zero wins**,
  22–27 losses each.
- **`PegDefence` fires now**, as predicted: 68.7% at its floor on its worst pair
  against 100% under arb-only, p95 up to 15.3 bps. It is still last by mean net
  result (−313 end / +254 trade-time — a sign flip at the policy-mean level,
  though not in any paired median).
- **`ABHook` litmus: loses.** Median −185, significant in 27/27 strata
  (end-of-window), 25/27 (trade-time).
- **`MEVChargeHookFixed` behaves as predicted** — a constant 30 bps on all three
  pairs, fee spread 0.00 bps, its surcharge never fires. Its 22/27 significant
  losses have a median of −6.17 USDT, −0.016% of the baseline result: detectable
  because 72 windows are a lot, and economically nil. Report both numbers or
  neither.
- **`VolatilityHook` is still not volatility-responsive** — fee spread 0.35 bps
  around a 5.1 bps median. The 2026-08-03 note that its coefficient is two
  orders of magnitude too small holds under UU flow too.

### Defect: the logged per-swap fee misses `MEVChargeHook`'s surcharge

`Replay.t.sol:732 _feeForSender` asks the hook for its fee with
`amountSpecified: 0`. For a `size_dependent` policy that returns the
**zero-size** fee, so the size surcharge never reaches the log.

Measured, ETH/SHIB, two windows, fee summed from the log in USDT against the
pool's own `feeGrowthInside`: eleven of twelve policies sit at a ratio of
0.93–0.96 — a uniform offset that is a _convention_ difference, `fee_income`
being valued at end-of-window prices and the log at trade-time prices — and
`MEVChargeHook` alone sits at **0.426**. Its log says a constant 30 bps; the
pool credited ~65 bps. `MEVChargeHookFixed` shares the mechanism and is
unaffected, because its corrected surcharge never fires — which corroborates the
diagnosis rather than weakening it.

Two consequences, and they differ in severity:

1. **Its economic results stand.** `fee_income` is read from the pool's fee
   accounting, never from the logged `feePips`, so net result, the frontier and
   its 18 significant wins are not built on the bad number.
2. **Every fee-behaviour statement about it is wrong**, and worse than wrong in
   one place: `Replay.t.sol:426` uses the _same_ zero-size read for the UU
   participation decision. Retail decided to trade at 30 bps and was charged
   ~65. That is a modelling inconsistency, not only an instrumentation one, and
   it is the mechanism behind MEVChargeHook's +24,343 USDT of fee income at
   essentially unchanged volume — the thing that makes it the second-ranked
   policy. **Its ranking must not be reported until this is resolved.**

Scope: the two `size_dependent` policies only, and in practice only
`MEVChargeHook` — 1,296 cells, about an hour to re-run once `_feeForSender`
takes the real `amountSpecified`. Ten policies, including the headline winner
`BAHook`, are untouched.

## Session 2026-08-10: why the matrix stalled, a trace defect, notebooks 07–08

### The stall was not a bug

The matrix stopped producing cells at **07:47:36** and produced nothing until it
was relaunched at 10:37. One clean gap, no partial output, no error.
`pmset -g log` names the cause:

```
2026-08-10 07:47:56 +0300 Sleep  Entering Sleep state due to 'Clamshell Sleep'
                                 TCPKeepAlive=active Using Batt (Charge:100%)
```

The lid was closed, on battery. Caffeine was running but holds only
`PreventUserIdleDisplaySleep`, which does not stop clamshell sleep. **Launch
long runs as
`caffeinate -is uv run python run_matrix.py --uu 2>&1 | tee results-uu/run.log`**
— the run had no log at all, so this had to be reconstructed from file mtimes.

### Defect: the UU matrix overwrote the arb-only traces

`run_matrix.py --uu` writes metrics and manifests to `results-uu/matrix/` but
its per-swap JSONL traces to **`results/`**, under the identical seven-field
filename the arb-only matrix used. Cause: `experiments/matrix.py` `run_spec`
never passes a `results_dir`, so `run_one` falls back to its default
(`experiments/run_one.py:116`) — directly under the comment warning that this
overwrites matrix traces. Plan Task 7 said "UU-ness is carried by the
directory"; the directory was never threaded through.

Measured at 10:50, mid-run: 10 374 of 17 078 traces in `results/` replaced, of
which 10 363 carry the exact seven-field name and are therefore
indistinguishable from arb-only traces to `events.applied_fees` /
`fee_vs_deviation` / `fee_trajectories`. `results/` is gitignored, so there is
no VCS recovery.

**All seven dynamic policies' arb-only traces are gone.** Only the four static
`MyHook@*` levels survived at the time of measurement, and the run was working
through them. What is _not_ lost: `results/summary.csv`, `results/analysis.csv`,
and every `paper/Image/*.pdf` with its `*.csv` table view — so no published
arb-only number is affected. What is lost is the ability to re-derive or
re-verify trace-level arb-only claims (fee distributions, fee-vs-deviation,
notebook 06's integrity checks).

Owner's decision (2026-08-10): whether to regenerate is deferred until the paper
makes it clear whether those figures need redrawing. Note for whoever picks it
up: a plain rerun will **not** regenerate them — the metrics and manifests still
match, so every cell is skipped by the resume logic.

Not fixed during the run, deliberately: stopping would have saved only the
static-baseline traces, whose fee distribution is a constant. The fix (thread
`results_dir` through `execute_parallel` → `_worker` → `run_spec` → `run_one`,
then move the UU traces out of `results/` by mtime — the 2026-08-09 22:40
boundary separates them cleanly) is queued for after the run lands.

### Defect: `pytest -q` never excluded the slow tests

`RUNNING.md` has always claimed it did. Nothing implemented it — no `addopts`,
no conftest. The slow tests drive `run_one`, which writes the shared trace files
in `data/`, so running them during a matrix run corrupts live cells with
deterministic-looking but wrong numbers (see "Traps", below). Fixed:
`addopts = ["-m", "not slow"]` in `pyproject.toml`; an explicit `-m slow` on the
command line still wins, so `uv run pytest -q -m slow` behaves as documented.

### Analysis prepared for the new columns

Library, all TDD, 138 Python tests green (7 slow deselected):

- `aggregate.PAIRED_METRICS` — the differenced metrics are declared once instead
  of a hardcoded four, and columns absent from a frame are skipped. Without this
  `analyse(paired, value="net_result_tt_delta")` raised `KeyError`, i.e. the
  co-primary valuation was unreachable and only the friendlier one could be
  reported. The frozen arb-only `summary.csv` still pairs.
- `aggregate.by_regime` reports `net_result_tt`, the volume split,
  `uu_fee_share` and `uu_participation` when the frame has them.
- `figures.net_result_by_regime` and `figures.frontier` take `value=`, default
  unchanged, and name the valuation in the CSV table view.
- New `figures.valuation_comparison` (dumbbell; flags sign disagreement as a
  column, not something to spot by eye), `figures.uu_flow` (volume split,
  participation, fee share), `figures.draw_all_uu`. `draw_all_uu` raises when
  the traces directory is empty rather than drawing a fee figure from nothing.

Notebooks:

- **`analysis/07-uu-main-results.ipynb`** — the third experiment. Reads
  `results-uu/matrix/` directly when `summary.csv` is not there yet, so it runs
  against a matrix still in flight. Asserts the calibration (participation falls
  as the static fee rises), checks the interior-optimum prediction, runs the
  pre-registered analysis **twice with separate FDR control**, one per
  valuation, and tables every comparison where the two disagree.
- **`analysis/08-uu-flow-behaviour.ipynb`** — what the synthetic flow did:
  participation against fee (with the pure-fee curve `exp(−λ·fee)` beside it, so
  the signed-deviation contribution is visible), who supplied volume against who
  paid fees, whether `PegDefence` finally fires, and fee-vs-toxicity re-read for
  two flows.

Both were executed cell by cell against a synthetic complete frame, which caught
a real argument-order bug in the notebooks' `show()` helper. They are committed
**unexecuted** — the matrix was still running, and baking partial numbers into
notebook outputs is how a provisional figure becomes a quoted one.

Neither notebook can be executed for real until the matrix finishes: with the
baseline policy barely present, `paired_against_baseline` correctly yields
almost nothing.

## Session 2026-08-09: audit, UU flow, third experiment launched

Read this section first; everything below "Status" describes the two arb-only
experiments, which are now frozen artifacts.

### Where things stand right now

- **The full UU matrix is running in the background**
  (`uv run python run_matrix.py --uu`, launched ~22:45 local), writing to
  `results-uu/`. 12 policies × 2 arb address modes × 3 pairs × 72 windows × 3
  gas scenarios. On startup it fetches a year of USDCUSDT 1-minute volume for κ
  (~13 min); ETHUSDT+SHIBUSDT volumes are already cached
  (`data/*-1m-v2-*.parquet`). If it died, just relaunch the same command —
  manifests make it resume.
- **Suites green at launch: forge 109/109, pytest 135/135.** Formatting run.
  Nothing committed (owner's standing rule).
- Analysis notebooks (`analysis/*.ipynb`) have NOT been updated for the new
  columns — that is the next work item once the matrix lands.

### Audit of the arb-only results (morning)

Verified sound: metrics arithmetic (bit-exact independent recompute), per-swap
arbitrageur entry condition (30,274 swaps, zero negative realized profits,
expected==realized), conservation ~1e-16. Three findings:

1. **MEVChargeHook violated the shared fee box** (spec §4.5): 28,068 of 56,756
   swaps above 100 bps, median violator 188 bps, max 1000 bps
   (`config.feeMax = 1000` bps). Every arb-only MEVCharge comparison is
   confounded by "was allowed to charge more".
2. **Valuation timing flips conclusions.** `net_result` (end-of-window) =
   realized extraction + inventory revaluation, and the second term dominates.
   Paired vs MyHook@3000 on ETH/SHIB persistent: BAHook
   null(end)→win(trade-time), DAHook loss→win, MEVCharge loss→win, PegCapture
   win(+46, p=2.5e-4)→null(p=0.63). The arb-only PegCapture headline is NOT
   robust to valuation. ABHook is a stable null/-10 in both.
3. **`arb_profit` was mislabeled**: identically −net_result (arb inventory MTM
   at end prices, gas excluded), not realized profit. Renamed `arb_mtm`;
   realized profit is a new column.

### UU flow (the third experiment) — why and what

Arb-only flow is degenerate: every trade is a net LP loss by construction, so
net-vs-HODL rewards strangling volume (MyHook@10000 "won" the matrix). Decision
with the owner: add uninformed-user flow, the previous paper's psychological
model `P = 1 if r ≥ 0 else exp(−λ|r|)`, adapted: λ scale (canonical ln2/0.003 ≈
231.05 WAD-scaled), r = per-direction γ·(price ratio) − 1 (fee + signed pool
deviation, slippage & gas excluded), applied as a deterministic volume share
(continuum of users; zero randomness preserved). Full model:
`docs/superpowers/specs/2026-08-09-uu-flow-design.md`. Plan (executed, all 8
tasks): `docs/superpowers/plans/2026-08-09-uu-flow.md`. Pre-registration
(recorded before the matrix run, incl. disclosed peeking):
`docs/superpowers/specs/2026-08-09-uu-matrix-preregistration.md`.

Headline verification numbers: with UU on (ETH/SHIB 2024-01-01, MyHook, 20 gwei)
static net_result is **non-monotone** — 5 bps: +2258, 30 bps: +7255, 60 bps:
+7250, 100 bps: +4853 — the degeneracy is gone at the canonical λ, no retuning
needed. κ(ETH/SHIB) = 0.05517408261312724.

Implementation was done by a Sonnet subagent (TDD, checkboxes in the plan file),
then adversarially verified by a second Sonnet subagent that wrote independent
property tests WITHOUT reading the implementation
(`tests/test_uu_adversarial.py`, `contracts/test/UUAdversarial.t.sol` — 34
properties, own mpmath references). Two real bugs found and fixed:

- `UUMath.rWad` truncated r at pips granularity (inner mulDiv) — 0.1 bp
  quantization; fixed via exact `gammaWad = gammaPips * 1e12`, single mulDiv.
- `metrics.compute` never returned `arb_profit_realized = None` on pre-UU traces
  because `read_events` backfills `extPriceGas = 0`; all-zero column is now the
  missing-data sentinel (a zero ETH price cannot occur).

### New interfaces a future session needs

- `run_one(..., uu_mode="off"|"share"|"discrete", uu_lambda_wad, uu_seed, uu_sigma)`;
  mode "off" is byte-identical to the pre-UU harness (differential golden
  asserts it).
- New metrics columns: `net_result_tt` (trade-time co-primary), `arb_mtm`
  (renamed from `arb_profit`), `arb_profit_realized`, `uu_volume`, `arb_volume`,
  `uu_fee_share`, `uu_participation`.
- Swap events now carry `trader` ("arb"/"uu"), `rWad`, `pWad`, `extPriceGas`.
  Old traces parse with defaults ("arb", 0).
- MEVChargeHook is clamped in the harness deploy path: `feeMax` 1000→100 bps,
  `flaggedFeeAdditional` 400→40 bps (forced by the contract's own invariant).
  MEVCharge rows are NOT comparable across the arb-only and UU matrices.
- Golden tests: `tests/golden/eth-shib-2024-01-01-myhook-3000.json` (arb-only,
  also the UU-off differential reference) and `...-myhook-3000-uu.json`.
- `uv run python -m experiments.check_uu` (module form required) re-runs the
  degeneracy + conservation check.

### Traps discovered this session

- **Concurrent `run_one` calls race through the shared `data/` trace files**
  (`trace0/1/gas.csv`, `uu_trace.csv`): two processes running goldens/checks
  simultaneously produce deterministic-looking but wrong numbers (observed
  −11352 and −479.9 vs the true −7256 / −284.8 during agent overlap). The matrix
  is safe (per-worker `work_dir`); tests are not. Never run the pytest goldens
  while anything else drives `run_one`.
- Forge runs env vars process-global: `vm.setEnv` races across concurrently
  running tests in one file — hence `ReplayTest.configureForTest(...)`, a
  test-only seam that bypasses env.
- `foundry.toml` `fs_permissions` restricts the harness to `../.work/` and
  `../results/` — pytest `tmp_path` fixtures cannot be handed to forge.

### Next actions, in order

1. When the matrix finishes: aggregate + `stats.analyse` on BOTH valuations, per
   the 2026-08-09 pre-registration. Report medians/win rates beside every
   significance flag. — **prepared 2026-08-10**; it is notebook 07, which only
   needs executing.
2. ~~Update `analysis/` notebooks for the new columns and the third experiment~~
   — **done 2026-08-10**, notebooks 07 and 08, committed unexecuted. Execute
   them once the matrix lands, and fix the trace directory first (see the
   2026-08-10 session above) or their fee cells read the wrong experiment.
3. λ-sensitivity sweep {58,116,231,462,924} → `results/sensitivity/` (same
   pattern as captureShare; exact-filename filters).
4. Discrete-mode robustness appendix (a few reference cells × 5 seeds) —
   groundwork is implemented, spec §2.4.
5. The paper: three experiments, claim boundary moves per the UU prereg;
   valuation-timing finding and MEVCharge clamp must be in the text.

## Status

**Plan 1 (foundation): COMPLETE, all 8 tasks. 46 tests green — 22 Solidity, 24
Python.** See `REVIEW-2026-08-03.md` for what needs your decision. Nothing is
committed; everything sits in the working tree by the repository owner's
standing rule.

| Task                            | State | Tests |
| ------------------------------- | ----- | ----- |
| 1. Foundry, migration, `MyHook` | done  | 3     |
| 2. Python harness               | done  | 1     |
| 3. Binance loader               | done  | 6     |
| 4. `ArbMath`                    | done  | 12    |
| 5. `EventLog`                   | done  | 4     |
| 6. Replay harness               | done  | 3     |
| 7. Event parser and metrics     | done  | 13    |
| 8. End-to-end run               | done  | 4     |

### Plan 2 (policies) — COMPLETE

| Task                         | State | Tests |
| ---------------------------- | ----- | ----- |
| 1. Characterisation tests    | done  | 7     |
| 2. `f_min` in three ratchets | done  | 3     |
| 3. `ABHook` delta resolution | done  | 5     |
| 4. `ABHook` both directions  | done  | —     |
| 5. `PegStability` two modes  | done  | 10    |
| 6. `Welford`                 | done  | 9+4   |
| 7. `VolatilityHook`          | done  | 8     |
| 8. Size search for MEVCharge | done  | 3     |
| 9. Gas calibration           | done  | 4     |

### Plan 3 (matrix and analysis) — in progress

| Task                       | State | Tests |
| -------------------------- | ----- | ----- |
| 1. Volatility and terciles | done  | 10    |
| 2. Run manifest            | done  | 13    |
| 3. Matrix driver           | done  | 7     |
| 4. Aggregation             | done  | 6     |
| 5. Wilcoxon + BH           | done  | 10    |
| 6. Figures                 | done  | 8     |
| 7. Golden window           | next  | —     |
| 8. Execute the matrix      | —     | —     |

Window selection on real 2024 ETH/SHIB: 366 daily segments, volatility 0.018 to
0.300, median 0.036. Eight windows per tercile, spread across the year. The high
tercile picks up 2024-08-05, the yen carry-trade unwind.

Plan 3 notes:

- Two test expectations were wrong rather than the code. `pytest.approx` does
  not compare elementwise against a pandas Series — it silently yields a scalar.
  And BH is **not** uniformly stricter than the naive threshold: ten p-values
  all at 0.04 are jointly strong evidence, expected false discoveries 0.4, an
  FDR of 4%, so accepting all ten is exactly what controlling the FDR at 5%
  means.
- Figures: **policy is an axis, not a colour.** Eleven configurations exceed the
  eight hues any validated categorical palette carries, and cycling them would
  make two policies share one. Small multiples plus axis position carry identity
  and survive greyscale printing. One accent hue, validated with the skill's
  checker; every figure writes a CSV beside itself, which is both the relief for
  the contrast warning and what a reader needs to check a number.
- Rendering and **looking** caught four layout defects no test would have: a log
  axis over three discrete gas scenarios rendered as an unreadable "6x10^0
  2x10^1" smear; panel titles in lower rows sat on the tick labels above; a
  static-fee label collided with a policy label; and policy order interleaved
  `MyHook@10000` between the hooks, separating exactly the comparison a reader
  wants together.
- `USDC/USDT`'s second leg has no market series; it is a synthetic feed pinned
  at 1.0 (`CONSTANT_ONE`). Formally not a market observation — spec §16 already
  carries the caveat.

Calibrated gas per swap, including the 21,000 intrinsic. **Transcribed from
`experiments/gas_estimates.json` on 2026-08-10; that file is the source of truth
and this table is a copy.**

| Policy               | Gas     |
| -------------------- | ------- |
| `MyHook@3000`        | 76,268  |
| `MyHook@6000`        | 76,705  |
| `MyHook@500`         | 76,786  |
| `DAHook`             | 87,970  |
| `ABHook`             | 93,842  |
| `MEVChargeHook`      | 94,739  |
| `MEVChargeHookFixed` | 98,824  |
| `PegDefence`         | 100,713 |
| `PegCapture`         | 104,335 |
| `BAHook`             | 107,847 |
| `VolatilityHook`     | 127,508 |

`MyHook@10000` produces no trades on the calibration day and is absent from the
JSON; the harness default (`DEFAULT_GAS_ESTIMATE = 76_578`) covers it.

> **Corrected 2026-08-10.** The table previously printed the **pre**-calibration
> figures and disagreed with the JSON on every policy. The JSON is what the
> matrix actually reads (`matrix.manifest_for:238`, `run_spec:300`), and
> `gasEstimate` is the arbitrageur's entry threshold, so these numbers gate flow
> rather than merely describing it. Two of the differences are real and recorded
> elsewhere in this file: `BAHook` went **124,312 → 107,847 (−13.2%)** when two
> dead oracle reads were removed, and `MEVChargeHookFixed` was not in the table
> at all. The rest are sub-1% recalibration drift. Gas overhead per policy is on
> the paper's own list of what a controlled study must report, so anything
> quoted from here would have been quoted wrong. The JSON was not touched.

**Basket raised to 20,000,000 USDT** on 2026-08-03 (spec §4.3 records why).

Plan 2 notes:

- `DAHook`'s `FSTEP` is 100 (1 bp), not 500; its source comment saying "5 bps"
  is wrong. `BAHook`'s is 500.
- The 7 characterisation tests still pass after `f_min` landed, which is the
  differential check: the floor changed behaviour only at the floor.
- `F_MIN` is a **public** constant on all three hooks — the bound tests and the
  run manifest read it from outside.
- `ABHook` now responds to a 5 bps square-root move and to both directions. Its
  `DELTA_SCALE` went from 1e4 to 1e6; the old scale truncated every adjustment
  below a 1% move to zero, so the hook had been static in every prior run.
- Removing the `if (isAToB)` guard was not cosmetic: the hook previously saw
  only half the order flow.

## How to resume

```bash
export PATH="$HOME/.foundry/bin:$PATH"
cd /Users/antonled/science/uniswapv4-hooks/swap-hooks

cd contracts && forge test          # 22 pass
cd .. && uv run pytest -q           # 24 pass

# regenerate the synthetic trace the harness reads, if data/ was cleared
uv run python -c "
from pathlib import Path
n = 200
Path('data/trace0.csv').write_text('\n'.join(f'{i},{int(3000e8)}' for i in range(n)) + '\n')
Path('data/trace1.csv').write_text('\n'.join(f'{i},{int((0.03 + 0.0004 * ((i * 7) % 11)) * 1e8)}' for i in range(n)) + '\n')
Path('data/trace_gas.csv').write_text('\n'.join(f'{i},{int(3000e8)}' for i in range(n)) + '\n')
"
```

Next action: Plan 2, `docs/superpowers/plans/2026-08-02-policies.md`.

## Environment facts worth not rediscovering

- **Foundry 1.7.1** installed at `~/.foundry/bin`, not on the default PATH of a
  fresh shell until `~/.zshenv` is sourced.
- **Submodule revisions are load-bearing, not cosmetic.** The current tip of
  `uniswap-hooks` changed `BaseHook`: it now takes `IPoolManager` in the
  constructor and exposes `poolManager` as a public immutable variable. Every
  hook here is written against the older API where `poolManager()` is an
  overridable function and the constructor takes no arguments. **On the tips
  nothing compiles.** Pinned and recorded:

  | Submodule         | Revision  | Tag        |
  | ----------------- | --------- | ---------- |
  | `uniswap-hooks`   | `ca8fe74` | v1.1.0-213 |
  | `forge-std`       | `a6d71da` | v1.11.0-6  |
  | `hookmate`        | `33408fb` | v0.2.0~3   |
  | `chainlink-local` | `a3ace4e` | v0.2.7     |

- **Pin order matters.** `git submodule update` resets submodules to whatever
  the superproject index records. Check out the pinned SHA,
  `git add contracts/lib` to record it, _then_ update. Doing it the other way
  silently reverts the pins — which happened once here.
- **`chainlink-evm` is not needed.** `chainlink-local` declares it as a nested
  submodule; it is the whole Chainlink node repository and takes tens of
  minutes. `MockV3Aggregator` and the feed interfaces import only sibling files
  via `./`, so it is deliberately left uninitialised.
- Nested submodules of `uniswap-hooks` (`v4-core`, `v4-periphery`,
  `openzeppelin-contracts`, and in turn `solmate`, `permit2`) are initialised.

## Incident: the first full matrix run exhausted the machine's RAM

2026-08-03. Two compounding mistakes, both mine, both in code I wrote:

1. **`gas_limit` set to `u64` max** in `foundry.toml`. I raised it because the
   size search was hitting the default, but the right fix was to make the search
   cheaper — which I also did — and I left the bound removed. The gas limit is
   the only thing that stops a runaway test allocating until the machine dies.
2. **State snapshots were never deleted.** `_optimalSize` takes one per candle;
   `vm.revertToState` restores the state but keeps the snapshot alive, ~1.6 MB
   each, 2880 per window. One `MEVChargeHook` process held **4.76 GB**.

Ten workers were launched without measuring per-process memory first.

Measured, before and after:

| Run                                            | Peak RSS    |
| ---------------------------------------------- | ----------- |
| `MyHook`, one window                           | 186 MB      |
| `MEVChargeHook`, no size search                | 187 MB      |
| `MEVChargeHook` with search, snapshots leaked  | **4756 MB** |
| `MEVChargeHook` with search, snapshots deleted | 286 MB      |

Fixes: `vm.deleteStateSnapshot` after every revert; `gas_limit = 2e10`, eight
times the measured worst case of 2.46e9; and `run_matrix.py` now reads available
memory and caps the worker count before starting. Eighteen `MEVChargeHook` cells
across ten workers now peak at 3.1 GB in total.

**Rule this leaves behind:** measure peak RSS of the heaviest single cell before
running anything in parallel, and never remove a resource bound to make a test
pass — fix what is consuming the resource.

## Defects found beyond the plan, and fixed

- **`lib/` in `.gitignore` blocked `git submodule add`.** The pattern matched
  `contracts/lib/`. Removed with a comment: under submodules only the pinned
  hashes live here, and those are field `D` of the reproducibility manifest.
- **`MyHook` was undeployable.** No entry in `HookFlags` and no branch in the
  `HookTest` dispatch, so `flags` stayed `address(0)`. Hook permissions live in
  the low bits of the address, so this would have produced a hook with no
  permissions and an unrelated-looking failure at pool initialisation. Added
  `MY_HOOK_FLAGS` (`afterInitialize | beforeSwap`) and a
  `require(flags != address(0), "unknown hook name")` so the next such typo
  fails at the point of the mistake. `MyHook` is the baseline for all of Plan 1.
- **`MyHook` lacked the extended fee interface.** Added external `getFee` and
  changed `setFee(uint24)` to `setFee(uint24, PoolKey)`, which also pushes the
  value through `updateDynamicLPFee` so the stored LP fee tracks `_getFee`.
  Without the second, the four static baseline levels could not be set at all.
- **Forge tests share the filesystem.** `setUp()` runs once and each test then
  starts from a snapshot of EVM state, but file writes are not EVM state and are
  never rolled back. A shared JSONL path accumulated every test's records
  (`7 != 3`). Each test now takes its own file. **The same trap applies to Task
  6's gas guard test**, which runs the trace twice.

## Two defects the conservation invariant caught

Both returned plausible numbers and neither would have failed any test.

- **Warm-up broke the baseline.** Warm-up swaps execute but are not logged, so
  their flow was missing while the pool state reflected them. Off by 3.9%. The
  baseline is now captured at the warm-up boundary, fee growth included.
- **pandas silently overflowed int64.** Wei-scale deltas reach 5.8e18 against a
  9.2e18 ceiling; `Series.sum()` wrapped and returned `+8.1e18` where the truth
  was `-1.0e19` — wrong magnitude and wrong sign. Wei-scale columns are now
  object dtype summed as Python integers (`exact_sum`), with a regression test.
  This would have corrupted the whole 4752-run matrix silently.

After both fixes conservation closes at 1.8e-16 across all sweep configurations.

## Task 6 notes

- The harness runs and emits: 140 swap records plus one window record over a
  200-candle synthetic trace, warm-up respected, both trade directions present.
- With `FEE_PIPS=3000` fee growth is non-zero on both sides, which is what the
  Task 7 conservation check needs. **Without `FEE_PIPS` the fee defaults to 0
  and no fees accrue** — worth remembering when a run looks fee-less.
- Trade count did not change between fee 0 and fee 3000 on the synthetic trace,
  because that trace swings ~13% between candles, two orders of magnitude wider
  than a 30 bps band, so every candle triggers regardless. The gas guard test
  does show the expected reduction, so the mechanism is live. Real minute data
  will exercise the fee sensitivity properly.
- `using` directives are contract-scoped in Solidity and are **not** inherited.
  `HookTest` declares `using EasyPosm for IPositionManager`, but `ReplayTest`
  had to repeat it.

## Decisions in force (from the design review, 2026-08-02)

1. Negative results are published as findings.
2. No single primary hypothesis; the whole family of comparisons is
   pre-registered with Benjamini–Hochberg at `q = 0.05`.
3. No policy is invented; a policy is built only where the paper already claims
   it. `VolatilityHook` is in scope for this reason; an oracle-informed
   constant-sum hook is not.
4. `PegStabilityHook` ships in both readings — `PegDefence` and `PegCapture`.
5. Two-sided Wilcoxon signed-rank per comparison.
6. Order of work: Plan 1 → Plan 2 → Plan 3 → paper text.
7. `ABHook` vs static 30 bps is a litmus comparison, highlighted in prose, with
   no statistical privilege.

The full pre-registration is §12.1 of the design spec. It was written before any
run, and must not be edited once numbers exist.

## Open items

- **No plan covers rewriting the paper.** Deliberately deferred, but it is the
  thing most likely to be squeezed against 2026-08-18.
- `dex/` in the working tree is now redundant; the needed sources live in
  `contracts/`. Deleting it is proposed but not done.
- `scipy` is not yet installed; Plan 3 Task 5 adds it.

## Sensitivity analysis: PegCapture x captureShare (2026-08-03)

504 cells, ETH/SHIB, all 24 windows x 3 gas scenarios x 7 values of
`captureShare`. 0 errors, worst conservation error 4.9e-16. Paired against
`MyHook@3000` on the same windows with the same Wilcoxon + BH machinery; 23 of
28 comparisons significant at q = 0.05.

`captureShare` is the dominant parameter -- it flips the sign of the result:

| share | mean net | trades | volume    | median vs 30 bps | significant |
| ----- | -------- | ------ | --------- | ---------------- | ----------- |
| 0.10  | -656     | 264    | 2 841 351 | -713             | yes (loses) |
| 0.25  | +674     | 216    | 2 206 444 | -382             | yes (loses) |
| 0.50  | +2 040   | 143    | 1 365 310 | +69              | yes         |
| 0.75  | +2 557   | 79     | 717 538   | +187             | yes         |
| 0.80  | +2 527   | 66     | 617 851   | +353             | yes         |
| 0.85  | +2 447   | 51     | 527 577   | +366             | yes         |
| 0.90  | +2 392   | 37     | 469 409   | +387             | yes         |

Three things follow, and all three belong in the paper:

1. **0.5 is not the optimum and not cherry-picked.** It is the _weakest_ winning
   setting -- the smallest positive median of the four, not significant in mid
   or low volatility. The pre-registered number is conservative, which is the
   right direction for a value the author chose.
2. **The sign flips below 0.5.** At 0.1 PegCapture significantly _loses_ to
   static 30 bps in every regime. The policy is not robust to its own parameter,
   and the paper must say so rather than report a single tuned point.
3. **The optimum is interior.** Net result peaks at 0.75 and falls after, while
   retained volume falls monotonically throughout. The kappa -> 1 degeneracy
   bites well before 1.0 -- one probe at 0.9 traded zero times -- because the
   arbitrageur must also clear gas. In low volatility 0.9 significantly loses.

Figure: `paper/Image/capture_share_sensitivity.pdf`. Kept in
`results/sensitivity/`, never merged into `results/matrix/`.

### Frontier labels

Hand-tuned offsets in `frontier()` had three collisions (BAHook/MEVChargeHook,
DAHook/ABHook, VolatilityHook/"5 bps"). Replaced with `_place_labels`, which
measures each text box on a real renderer and takes the first candidate slot
that neither overlaps a placed label nor leaves the axes. The out-of-axes check
is load-bearing: without it MEVChargeHook's label ran off the left edge and over
the y-axis title.

## Defect: `fee_distribution` was wrong on four counts (2026-08-03)

Found by inspection of the axes. Root cause of all four: the function was
imported into `run_matrix.py` and **never called**, so nothing ever exercised
it. Its PDF was timestamped an hour before every other figure.

1. **Drawn from one ad-hoc window** (n = 31..258) while 147,880 swaps sat in the
   retained traces under `results/*.jsonl`. Now read from the whole matrix.
2. **A single 1-100 bps fee box drawn on every panel.** That is not
   MEVChargeHook's box -- `config.feeMax = 1000` bps, an order of magnitude
   wider -- and the static levels have no box at all. Consequence: measured
   against the drawn box, MEVChargeHook was 90.7% "at cap" on ETH/SHIB; against
   its real box it is 0.8%. The figure asserted the opposite of the truth. Boxes
   now come per policy from `events.FEE_BOXES_BPS`.
3. **MEVChargeHook was missing from the figure entirely** -- ten panels for
   eleven policies.
4. **Histograms of constants render as an invisible spike.** Four of the ten
   panels (`MyHook@500/3000/6000/10000`) read as empty. Replaced with quantile
   intervals, where a constant is honestly a dot.

Rebuilt as one row per policy, two panels (ETH/SHIB, ETH/USDC), log x from 1 to
1000 bps, with the share pinned at a bound written out. USDC/USDT is absent
because it produced no swaps at all, consistent with its 1542 zero-trade cells.

Two findings the corrected figure surfaces:

- **PegDefence is pinned at its 1 bps floor for 100% of swaps on both pairs.**
  It never adapts once in the entire matrix, which is the mechanism behind its
  worst-in-class net result.
- **MEVChargeHook is regime-split**: 98% at its 30 bps floor on ETH/USDC, but a
  median of 236 bps on ETH/SHIB.

### Second defect, caught while fixing the first

The trace filter matched the address mode by prefix, so the 504 sensitivity runs
(`...-persistent-cs<share>.jsonl`) passed it. PegCapture's ETH/SHIB row was
built from 71,951 swaps instead of 10,306 and its p95 read 95.8 bps instead of
43.7. The sensitivity sweep had leaked into a pre-registered figure -- exactly
what keeping it in a separate directory was meant to prevent, defeated by a
filename match. Now an exact seven-field match, with a regression test in
`tests/test_events.py`.

## Formatting: `npm run format` was broken, and two defects behind it (2026-08-03)

`.prettierrc` named a `"slang"` parser for `*.sol`. That parser ships with
`prettier-plugin-solidity`, which was never installed here -- the config came
from `adaptive-liquidity`, whose own `.prettierignore` header says Prettier
touches "MD / JSON / YAML / CSS / HTML / JS here", i.e. it kept Prettier away
from Solidity too. Dead config, silent until `contracts/` existed, then fatal:
Prettier aborted at the first `.sol` and never reached `docs/`, `RUNNING.md` or
anything alphabetically after it.

Resolved in favour of `forge fmt`, not by installing the plugin: a second
Solidity formatter would fight Foundry's, and the 80 columns the old override
asked for rewrap 344 lines of otherwise untouched code for no gain. `[fmt]` is
now pinned in `foundry.toml` (120 / 4 / double / no bracket spacing) so a
toolchain upgrade cannot silently rewrap the sources. `*.sol` is Prettier-
ignored; `npm run format:sol` is the Solidity half, deliberately not chained
onto `format` because that would break the command for anyone whose PATH lacks
foundry.

Two things surfaced once the command ran to completion:

- **Prettier was reformatting generated JSON.** `experiments/gas_estimates.json`
  and `tests/golden/` are written with `indent=2` while the JSON override asks
  for 4, so each regeneration and each format run would undo the other forever.
  Both now ignored.
- **`run_matrix.py` had a latent `NameError`.** `applied_fees` and
  `fee_distribution` were used at the call site but absent from the imports, so
  the module imported cleanly and `--figures-only` died only after three figures
  were already on disk. Root cause is the same one that let `fee_distribution`
  rot in the first place: nothing exercised the figure path. Extracted as
  `figures.draw_all(frame, results_dir, figures_dir)` and covered by
  `tests/test_figures.py::test_draw_all_produces_every_figure`, which asserts
  all four PDFs and their CSV table views appear from one call.

## Restructure: data scripts vs analysis notebooks (2026-08-03)

Everything is now driven by explicit, reusable files. Nothing is produced by an
ad-hoc script that exists only in a session.

**Scripts produce data and nothing else.** `run_matrix.py` writes
`results/summary.csv` and `results/analysis.csv`; `experiments/sensitivity.py`
writes `results/sensitivity/`. `--figures-only` is gone: a figure reachable only
behind a flag nobody passes is a figure that goes stale unnoticed, which is
exactly what happened to `fee_distribution`.

**Figures and research live in `analysis/*.ipynb`.** Four notebooks, each
stating at the top what must exist first, each executed end-to-end and committed
with outputs:

| Notebook                             | Covers                                        |
| ------------------------------------ | --------------------------------------------- |
| `01-window-selection.ipynb`          | how the 24 windows per pair were chosen       |
| `02-main-results.ipynb`              | the pre-registered comparison and its figures |
| `03-fee-behaviour.ipynb`             | what fee each policy actually charged         |
| `04-capture-share-sensitivity.ipynb` | the PegCapture sweep (not pre-registered)     |

Three things had to move into the library first, because they existed only as
throwaway analysis:

- `matrix.load_segments()` -- all 366 days per pair plus the selected subset.
  The stratification figure needed both and had been fed by hand.
- `figures.draw_all()` -- moved out of the runner, so the runner is not the only
  place that knows the full set of figures.
- `sensitivity.analyse()` -- the paired Wilcoxon + BH against the static
  baseline. It reproduces the reported numbers exactly.

Its significance column was renamed `significant_fdr` to match `stats.analyse`:
two functions both called `analyse` that disagreed on a column name is a trap
for whoever reads both, and it had already broken notebook 02.

## Thorough correctness audit (2026-08-03)

Every claim below was verified by running something, not by reading. Ten defects
found; all fixed except the two that are findings rather than bugs.

### Fixed: harness and analysis

1. **`ArbMath.profit` was wrong for one of the two directions.** The closed form
   `L(s-t)^2/s` holds only when selling token0. Buying token0 pays the fee out
   of the token1 input -- the unit profit is denominated in -- so nothing
   cancels and the true value is `L(t-s)^2/(gamma*s)`, larger by `1/gamma`.
   Verified against the pool's own swap math: sell matched to the wei, buy was
   short by exactly gamma (0.99700 at 3000 pips, 0.99000 at 10000). Since
   `expected` gates entry against gas, it suppressed buys whose true profit fell
   in `[gasCost, gasCost/gamma]` -- measured at 23 of 80,243 buys, 0.029%. Now
   takes `feePips` and applies the factor. `test/ArbProfit.t.sol` asserts both
   directions against the pool.

2. **Gas was valued at token0's price, but gas is paid in ETH.** The two
   coincide only because token0 is ETH for the volatile pairs; on USDC/USDT it
   understated the figure by the whole ETH price. `gas_cost` never entered
   `net_result`, so no result was affected -- but the number was in
   `summary.csv`. Now valued at the ETH series, threaded through `run_one`.

3. **The manifest did not hash our own contracts.** Field `D` recorded
   submodules, solc and the gas limit, and nothing about `contracts/src`. A hook
   edit changed every number while leaving the manifest identical, so the resume
   logic would skip the cell and `results/` would silently mix two experiments.
   Eq. (9) was open. Added `source_hash()`, with a test.

4. **Logging wrote hook state.** `_executeArb` read both directional fees for
   the record, unwrapped and with the wrong sender. MEVChargeHook's `_getFee`
   stamps `_lastBuyToken0/1[payer]` on every call including read-only ones, so
   this stamped BOTH directions after each swap and fed a fee the policy never
   charged into the next candle. Measured impact today: **zero** -- that policy
   trades far more rarely than its 15-second cooldown. It would wake up the
   moment uninformed order flow raises the trade rate. Now snapshotted, deleted,
   and given the real sender.

5. **Simulated time ran five times too fast.** The clock advanced 12 seconds per
   candle -- Ethereum's block time -- while a candle is a minute of market data.
   Checked who cares: BAHook and VolatilityHook gate on `block.number` and see
   one swap per candle either way, so only MEVChargeHook was affected, its
   15-second cooldown spanning more than a candle instead of a quarter of one.
   Now 60 seconds and 5 blocks per candle.

6. **`extPrice0/1Initial` came from candle 0** while the holdings beside them
   came from the warm-up boundary. Unused in `metrics.compute`, so harmless
   today, but anyone valuing those holdings at those prices would be off by the
   warm-up's price movement. Now captured with the rest of the baseline.

7. **The reported `n` overstated the evidence.** The signed-rank test discards
   exact ties; on USDC/USDT a comparison reported as `n = 8` ran on a mean of
   **0.23** usable differences. Nothing there was flagged significant, so no
   claim was false. `wilcoxon_paired` now also returns `n_effective`.

8. **ABHook's fee box was wrong in the figures.** A dead `MAX_FEE = 10000`
   suggested a 100 bps ceiling, but the constant sum binds first: with
   `K = 6000` and `F_MIN = 100` one side reaches 5900 only by pinning the other
   to the floor. The real box is [1, 59] bps. Replaced with `F_MAX = 5900` and
   corrected `FEE_BOXES_BPS`.

9. **VolatilityHook was not volatility-responsive.** Its fee read an EMA of
   Welford's _cumulative_ standard deviation. A cumulative estimator moves by
   O(1/n), so it stops moving; the EMA on top smoothed what remained. Measured
   over one window the fee range fell 8 -> 5 -> 3 -> 1 -> **0** pips across
   successive fifths -- frozen by the end, total range 0.17 bps. Replaced with
   an exponentially weighted variance (fixed horizon, ~1/alpha observations);
   Welford is kept for the reported diagnostic. After: 12 -> 6 -> 5 -> 7 -> 7,
   responsive throughout.

   **This does not by itself make the policy dynamic.** At `coefficient = 20000`
   the volatility term contributes about 45 pips of a 545-pip fee. Making it
   meaningfully responsive needs a coefficient perhaps two orders of magnitude
   larger -- a parameter choice, not a correctness fix, and best handled as a
   swept axis like `captureShare`. Deliberately not retuned here.

### Findings, not bugs

10. **PegDefence cannot activate under arbitrage-only flow.** It charges only
    trades that push the pool _away_ from the reference. An arbitrageur by
    definition trades _toward_ it. Measured: **0 of 1805 trades** were moving
    away, and the fee was exactly 100 pips every time. It is not a dynamic
    policy in this experiment -- it is a static 1 bps fee, which is why it lands
    on the static frontier (+61) and posts the worst net result (lowest fee ->
    most volume -> most adverse selection). Its mechanism is aimed at uninformed
    or manipulative flow, which the design does not contain.

11. **The FDR family double-counted.** The address axis produces exact
    duplicates: 266 of 270 comparisons are bit-identical between `persistent`
    and `fresh`, only MEVChargeHook differs. Re-ran BH on the deduplicated
    family of 274: **zero verdict changes** -- the procedure is invariant to
    exact duplication. But the headline is **56 significant of 274**, not 112
    of 540. Report the distinct count.

### Verified sound

Closed-form arbitrage on the sell side (exact to the wei); charged fee against
logged fee, recovered independently from the price move and liquidity -- **0.0
discrepancy** across five policies including MEVChargeHook; price tracking
(residual gap 0.06-0.32%, inside each policy's no-arbitrage band); token
conservation from two genuinely independent derivations (worst 1e-16); the units
of `_gasCostInToken1`; the HODL baseline; per-window pairing; the BH step-up;
Wilcoxon's tie handling; realised volatility; warm-up boundary alignment; and
the price convention, which the hook and the harness derive separately and agree
on.

### Golden window after all fixes

Only `gas_cost` moved, by 5.8e-05 relative. Every economic metric -- trades, fee
income, IL, net result, retained volume, conservation -- was bit-identical. The
drift is instrumentation: warm storage slots are cheaper to read, so measured
gas depends on what the harness touched just before the swap. Far below the
granularity of `gasEstimate`, the per-policy median that actually gates entry.

## Full read of BAHook, DAHook and MEVChargeHook (2026-08-03)

### BAHook

Direction is right: when the external ratio falls the pool sits above it, so
arbitrage will sell token0, and the hook raises exactly that side. One fixed
500-pip step per swap, and the fee only moves when a swap happens -- so a long
quiet stretch is compressed into a single step no matter how far price went.
That is a design limit, not a defect; the observed range spans the whole box.

**Defect: both price feeds were read a second time into variables used only by
commented-out logging.** Two dead external calls on every swap. It mattered
beyond gas: `gasEstimate` is the arbitrageur's entry threshold, so the policy
was being charged for dead code inside the experiment. Recalibrated, **124,312
-> 107,847 gas per swap, -13.2%.**

### DAHook

Momentum on flow direction only, no external price, updated per trade -- which
matches the granularity the paper claims for it.

**Defect: `lastSwapDirection` was written on every swap and never read.** Dead
state, one SSTORE per trade. Removed; 88,561 -> 87,970.

### MEVChargeHook

Dead code first: `_getCollusionPairId` walked `userInfo[].primary` up to
MAX_LINK_DEPTH and **was never called** -- the collusion feature it implies does
not exist in the contract. Two unused `pairId` locals alongside it. Removed.

**The substantive finding: the impact surcharge is dimensionally wrong.** It
sizes a trade as `amountSpecified / L`. Those are not the same kind of quantity:
`L` is sqrt-price-scaled, the amount is denominated in whichever token is paid
in. Measured over the matrix on ETH/SHIB:

| direction             | amount/L (bps) | above the 500 trigger |  median fee |
| --------------------- | -------------: | --------------------: | ----------: |
| buy token0 (pay SHIB) |        1,749.6 |              **100%** | **354 bps** |
| sell token0 (pay ETH) |           0.00 |                **0%** |  **30 bps** |

The surcharge tracks which token the input is denominated in, not price impact.
This explains the policy's whole behaviour: median 236 bps on ETH/SHIB against
30 bps on ETH/USDC (where the two tokens are only three orders of magnitude
apart), its position far below the static frontier, and its 4.6% residual price
gap.

**Both versions are now run.** The template stays as shipped, with the defect
documented; `MEVChargeHookFixed` overrides one `virtual` method to divide by the
reserve of the token actually paid in -- dimensionless and direction-symmetric.
The only change to the original is that one method became `virtual` and
`FEE_DENOMINATOR` became `internal`; a golden window reproduced exactly after
the refactor (3 trades, net 92.91).

On that window the corrected variant gives **11 trades and net 284.77 with both
directions at 30 bps** -- identical to static 30 bps. Once the measure is
dimensionless the surcharge never fires at all, because its 5%-of-reserves
trigger is far above anything arbitrage does against a 20M pool. That is the
honest result: corrected, the policy collapses to its static base.

Matrix is now 12 policies, 5184 cells. `tests/test_matrix.py` no longer pins the
total to 4752 -- that only recorded how many policies existed the day it was
written.
