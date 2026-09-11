# Pre-registration: extending the window count

Recorded **2026-08-04, before the extended run**, and before looking at any
result computed on the additional windows. Pre-registration only counts when it
precedes the data.

## Why

The original design takes 8 windows per volatility tercile, so every comparison
in the family is a Wilcoxon signed-rank test on **8 paired windows**. That
bounds the smallest two-sided p-value the test can return:

$$p_{\min} = \frac{2}{2^{8}} = 0.0078$$

A policy that wins **all eight** windows cannot report anything below 0.0078.
Under Benjamini–Hochberg at `q = 0.05` over 297 distinct comparisons, a p-value
at that floor is accepted only once at least

$$k \ge \frac{0.0078 \times 297}{0.05} \approx 47$$

comparisons reach the floor together. So no isolated effect, however large, is
detectable — and every significant result in the original run sits at exactly
`p = 0.007812`.

The design measures how many comparisons hit the instrument's resolution, not
how large the effects are. That is a property of the sample size, not of the
data.

## What changes

**Only the number of windows.** From 8 to **24 per tercile**, so 72 windows per
pair instead of 24. There are 122 days available per tercile, so the additional
windows come from days the analysis has never touched.

## What does not change

- **Quantity**: per-window paired difference in net LP result against HODL.
- **Test**: two-sided Wilcoxon signed-rank per comparison, then
  Benjamini–Hochberg across the family at `q = 0.05`.
- **Family**: every policy against static 30 bps (`MyHook` at 3000 pips), in
  every stratum — 3 regimes × 3 gas scenarios × 2 address modes × 3 pairs.
- **Baseline**: `MyHook@3000`. Not re-chosen.
- **Selection rule**: unchanged, `windows.select_windows`, evenly spaced by date
  within each tercile. Only its `per_tercile` argument moves.
- **Reported beside every comparison**: median difference, win rate, effect
  size.

The static fee grid stays at four levels and `captureShare` stays at its single
configured value. Both were considered and deliberately excluded, so that this
run changes exactly one thing.

## Declared in advance

More power does not create an effect; it resolves one. The direction of every
estimate is already known from the original run, and this extension can only
sharpen it:

- `ABHook` against static 30 bps currently has a median of **−14.4** and a win
  rate of **0.167**. If the effect is real, the extension makes the litmus
  comparison a **more significant loss**, not a win. That outcome is declared
  here so it cannot later be presented as a surprise.
- `PegCapture` currently has 4 significant comparisons and a win rate above 0.7
  in several strata. If its effect is real, the extension should raise the
  count.
- Policies whose mechanism never activates — `PegDefence` fires on 0 of 1805
  trades — will not change, because no amount of data resolves a mechanism that
  does not run.

## The original result is preserved

The 8-per-tercile run is archived under `results/preregistered-8-per-tercile/`
and is reported in the paper regardless of what the extension shows. Its
headline figures, fixed here:

| quantity                             | value         |
| ------------------------------------ | ------------- |
| distinct comparisons                 | 297           |
| significant after BH                 | 58            |
| smallest p in the family             | 0.007812      |
| `ABHook` median / win rate           | −14.4 / 0.167 |
| `PegCapture` significant comparisons | 4             |

Both runs are reported. Neither replaces the other.
