# Pre-registration: VolatilityHook recalibration

Written 2026-08-12, before any cell of the recalibrated policy has run.

## What is being changed, and why it is legitimate

`VolatilityHook` computes $f = f_{\text{base}} + c\,\hat\sigma$, where
$\hat\sigma$ is an EMA ($\alpha = 0.1$) of the per-block (one-minute) relative
change of the external price ratio. As shipped, $f_{\text{base}} =
500$ pips and
$c = 20{,}000$ — a coefficient written against a daily-scale sigma while the
estimator measures a minute-scale one ($\approx\sqrt{1440}
\approx 38\times$
smaller). Measured effect: the fee moves by ~0.35 bps over a whole window. The
policy was volatility-adaptive in name only, and its matrix result (last place
among the kept configurations) is a statement about a parameter's units, not
about the mechanism.

This is a **units fix plus an a-priori calibration**, not outcome tuning: no
parameter is chosen by optimising any experiment result.

## The calibration rule (fixed before the run)

Measured EMA-sigma quantiles over calendar 2024, computed with the hook's own
estimator ($\alpha = 0.1$, per-minute relative ratio change):

| pair      |     p10 |     p50 |     p90 |     p95 |     p99 |
| --------- | ------: | ------: | ------: | ------: | ------: |
| ETH/SHIB  | 5.4e-04 | 8.3e-04 | 1.7e-03 | 2.4e-03 | 4.9e-03 |
| ETH/USDC  | 3.3e-04 | 6.1e-04 | 1.3e-03 | 1.6e-03 | 2.5e-03 |
| USDC/USDT | 3.3e-05 | 6.6e-05 | 8.0e-05 | 8.5e-05 | 9.8e-05 |

Anchors, chosen from the pre-registered static grid and the measured static
optimum plateau (30–60 bps at the calibrated κ):

- calm — pooled volatile-pair $\sigma \approx 4\cdot10^{-4}$ (~p10) → ~28 bps,
  the baseline's neighbourhood;
- storm — $\sigma \approx 2\cdot10^{-3}$ (~p95) → ~60 bps, the measured optimal
  static of the high-volatility regime.

Rounded to whole constants:

$$f_{\text{base}} = 2000 \text{ pips (20 bps)}, \qquad c = 2{,}000{,}000$$

Consequences of the mapping, stated in advance: p99 minutes reach the 100 bps
ceiling; the stable pair sits flat near 21 bps (nothing to adapt to); $\alpha$,
the fee box, and every other parameter are unchanged.

**Disclosure.** The storm anchor uses the per-regime static curve measured on
the same 72-window set the policy will be evaluated on (high regime: 60 bps at
+16,526 vs 30 bps at +15,315, mean, volatile pairs). This is the same kind of
information the choice of the 30 bps baseline itself encodes, and it bounds the
achievable effect rather than fitting the policy's own behaviour — but a reader
should know the anchor and the evaluation windows overlap. The σ quantiles use
all of 2024, which contains the evaluation windows; σ is input data, not an
outcome.

## Design

The full corrected matrix re-runs with `VolatilityHook` added to the 2026-08-12
policy set: 9 configurations (4 hooks + 4 statics + recalibrated VolatilityHook)
× 3 pairs × 72 windows × 3 gas = 5,832 cells, `discrete` mode, seed 0,
calibrated κ. Same estimand and machinery as the matrix of record: median across
the 18 volatile-pair strata of the median paired difference vs `MyHook@3000`,
percentile bootstrap over strata, both valuations co-primary, BH at q = 0.05 per
declared family.

## Predictions (falsifiable, written before the run)

1. **Primary.** Recalibrated `VolatilityHook` beats `MyHook@3000` on the
   volatile pairs: positive stratum median with the bootstrap interval excluding
   zero, on both valuations. Mechanism: it tracks the regime-dependent optimum
   (≈30 bps calm, ≈60 bps storm) that no single constant can.
2. **Magnitude bound.** The mean advantage cannot exceed what a perfect
   per-regime constant would earn: ≈ +1,200 USDT/window in the high regime and ≈
   0 in low/mid, i.e. ≈ +400 pooled. Predicted realised effect: between +100 and
   +400 (median, volatile strata). Anything materially above +400 indicates an
   intra-window adaptation gain the static curve cannot explain and must be
   investigated, not celebrated.
3. **Against the best static (`MyHook@6000`, post-hoc family):** expected
   indistinguishable (interval covers zero). The recalibrated policy and the 60
   bps constant occupy the same plateau; the win over 30 bps comes from storms,
   where they roughly tie.
4. **Stable pair:** no advantage; expected a small significant loss vs 30 bps
   (it charges ~21 bps where 30 is better, per the static curve).
5. **Fee behaviour sanity:** per-swap fees span ≈ 20–100 bps on volatile pairs
   with visible regime structure, and are ≈ flat ≈ 21 bps on USDC/USDT. If the
   fee still barely moves, the recalibration failed as engineering and no
   economic reading is attempted.

## Verdict rule

Prediction 1 is confirmed only if BOTH valuations' intervals exclude zero in the
positive direction. A one-valuation result is reported as mixed. If prediction 1
fails, the result is reported exactly as the matrix of record reports every
other policy — the recalibration is not iterated on this window set. Prediction
4's expected loss does not count against the policy's primary claim, which is
scoped to volatile pairs; it counts as consistency evidence for the mechanism
(adaptation only pays where something varies).

## Superseding note

The pre-revision matrix result for `VolatilityHook` (−8,237 median vs baseline,
last place, at $f_{\text{base}} = 5$ bps / $c = 20{,}000$) was produced under
both the gas-denomination defect and the mis-scaled coefficient, and is not
comparable to the recalibrated policy's result. Both configurations' constants
are recorded here so neither can be silently conflated with the other.
