# Pre-registration: a second operating point, chosen by informed share

Recorded **2026-08-11, before this configuration produced a cell**. It amends
neither `2026-08-09-uu-matrix-preregistration.md` nor
`2026-08-10-r-correction-preregistration.md`; both stand, and the κ = 1.0 matrix
they govern remains the headline. This declares a **second** configuration,
reported beside it.

## Why a second point, and why this one

κ was fixed by a rule about **turnover** — mean daily uninformed volume over
2024 equals one basket. The quantity the mechanism under test depends on is the
**share of flow that is informed**, and turnover does not control it: at the
calibrated κ the arbitrage share came out at **13.3% of volume, with 6.4% of
cells trading no arbitrage at all**.

The κ sweep (`results/sensitivity/kappa.csv`, its own pre-registration) measured
what that costs. Advantage over the static 30 bps baseline, as a percentage of
the baseline's own result:

| turnover | arbitrage share | DAHook | BAHook |
| -------- | --------------: | -----: | -----: |
| 0.03×    |           82.5% | +17.2% | +20.8% |
| 0.10×    |       **55.6%** | +10.5% | +10.9% |
| 0.30×    |           29.2% |  +2.9% |  +3.6% |
| 1.00×    |           17.9% |  +1.3% |  +0.5% |
| 3.00×    |           19.6% |  +0.1% |  +1.1% |

The headline configuration sits at the **weakest point of that curve**. That is
not a reason to move the headline — κ = 1.0 is the calibrated, realistic
turnover, and choosing an operating point because it flatters the result is
precisely what pre-registration exists to prevent. It is a reason to report a
second point where both flows are comparably present, and to let the two be read
together.

**The second point is 0.1× the calibrated κ**, selected because it puts the
arbitrage share nearest a balanced mix (55.6%), not because of its outcome. Its
outcome for the six configurations the sweep already covered is known and stated
above; the outcomes for the other six policies, for ETH/USDC and USDC/USDT, and
for every stratum, are not.

## What is fixed

- `uu_mode = discrete`, seed 0; `r` and λ as corrected on 2026-08-10; retail
  pays gas; the address axis dropped. Identical to the headline configuration in
  every respect but κ.
- The full matrix: 12 policies × 3 pairs × 72 windows × 3 gas = **7,776 cells**.
- Family, test, baseline (`MyHook@3000`), both co-primary valuations, BH at
  `q = 0.05` — all unchanged, and **controlled within this configuration**. The
  two configurations are not pooled into one FDR family; they are two
  experiments, and the paper reports both.
- Output to `results-uu/turnover-0.1/`, never merged into the headline's own
  files. Nested rather than a sibling directory: `fs_permissions` in
  `foundry.toml` is an allowlist covering a subtree, and a sibling is not
  covered — the first attempt at this run used `results-uu-t0.1/` and every one
  of its 7,776 cells failed on that. `results-uu/*.jsonl` is a non-recursive
  glob, so the two configurations' traces never see each other.

## Declared in advance

- **The arbitrage share is expected near 56%** on ETH/SHIB, from the sweep. If
  the full matrix disagrees materially, that is reported, not quietly accepted.
- **The advantage is expected to be larger than at κ = 1.0**, roughly +10% of
  the baseline for `DAHook` and `BAHook` on ETH/SHIB, from the sweep's six
  configurations. **This is an extrapolation from 24 windows and one gas
  scenario to 72 windows and three, and it may not hold.**
- **No prediction is made** about the other six policies, about the two pairs
  the sweep did not cover, or about whether the volatile/stable split survives.
  `PegDefence` and `VolatilityHook` lose catastrophically at κ = 1.0; whether
  more arbitrage changes that is open.
- **A seed appendix is required here too** before this configuration's ranking
  is called stable, on the same terms as the headline's: five seeds, sign
  unanimity, spread reported beside the verdict.

## How this must be reported

Both configurations, always, with the arbitrage share each produced stated
beside the result. The claim the pair supports is conditional and mechanistic:

> the value of a dynamic fee scales with the share of informed flow — large when
> arbitrage dominates, slight when uninformed flow does

and **not** an unconditional "these policies beat a static fee". A reader must
be able to see that the headline configuration is the unfavourable one and that
it was kept as the headline anyway.
