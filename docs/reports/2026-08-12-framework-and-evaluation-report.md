# A configurable framework for dynamic-fee hooks on Uniswap v4

## Architecture, model, methodology, and evaluation

Prepared 2026-08-12 for integration into the ICBC 2026 submission.

This document answers the eight items requested: framework architecture,
mathematical model, experimental methodology, baselines, parameters, datasets,
metrics, and main results.

---

## 0. What is claimed, and what is not

The **primary contribution is the framework**: a configurable system for
creating, deploying, testing, and experimentally evaluating dynamic-fee hooks
for Uniswap v4. Its value is that a fee policy can be specified, compiled,
deployed against a real `PoolManager`, replayed against a market trace, and
scored — with every input pinned — without writing new infrastructure per
policy.

The **economic evaluation is a secondary contribution**, and it now rests on
controlled comparisons: every dynamic policy is compared against a fixed-fee
baseline **on the same window, the same trace, the same initial state, the same
gas price, and the same random seed**, paired window by window, with the market
term differencing out exactly. Four fixed-fee levels are included as policies in
their own right.

**We do not claim that dynamic fees are universally better, and the results do
not support such a claim.** Three findings in particular cut against it, and are
reported in §8 with the same prominence as the positive result:

1. The advantage is **fee capture**, not reduced adverse selection — impermanent
   loss is unchanged by policy, and structurally must be.
2. The winning policy charges retail a **larger** share of fees than a static
   fee does; it does not shift the burden onto arbitrage.
3. Against a **well-chosen** static fee rather than the pre-registered one, the
   advantage survives at one operating point and vanishes at the other.

Every quantitative claim below is pre-registered, or explicitly labelled
post-hoc.

---

## 1. Framework architecture

Four layers. **This section describes the artifact as it exists**, and marks
designed-but-absent components explicitly — the current paper text claims three
that are not implemented (§1.5).

### 1.1 Contract layer — `contracts/src/`

Hooks, a shared base, and the maths libraries. Built on OpenZeppelin's
`uniswap-hooks` (`BaseDynamicFee`, `BaseOverrideFee`).

**The framework provides four hook templates**, differing in what they read and
how often they may update the fee:

| template        | update granularity     | signal                                      |
| --------------- | ---------------------- | ------------------------------------------- |
| `BAHook`        | at most once per block | change in the external token-price ratio    |
| `DAHook`        | per trade              | deal-level state and swap characteristics   |
| `ABHook`        | block-level            | external ratio, **asymmetric by direction** |
| `MEVChargeHook` | policy-specific        | surcharge on high-impact swaps              |

Supporting code, shared by all four:

| file                            | role                                                            |
| ------------------------------- | --------------------------------------------------------------- |
| `CustomBaseHook.sol`            | shared base: permission bitmap, fee bounds, callback validation |
| `interfaces/IHooksExtended.sol` | the extended hook surface                                       |

`MyHook.sol` is the fixed-fee reference hook. It is an **instrument, not a
template** — it exists so the baseline runs through the identical code path as
every dynamic policy (§4).

**Scope note.** The four templates and `MyHook` are what this report presents as
the framework. Everything else in `contracts/src/` is either evaluated but not
presented as a template, or written for this study:

| component                                       | status                                                                                            |
| ----------------------------------------------- | ------------------------------------------------------------------------------------------------- |
| `PegStabilityHook.sol`                          | present in the original repository and evaluated (§3.1); not presented as a template              |
| `VolatilityHook.sol`, `libraries/Welford.sol`   | **written for this study**                                                                        |
| `MEVChargeHookFixed.sol`                        | **written for this study** — a corrected variant, §3.1                                            |
| `libraries/ArbMath.sol`, `libraries/UUMath.sol` | **written for this study** — harness maths, belonging to the evaluation rather than to any policy |

### 1.2 Deployment layer — `contracts/test/utils/`

`Deployers.sol`, `HookTest.sol`, `BaseTest.sol`, and `libraries/HookFlags.sol`
mine a CREATE2 salt whose address matches the declared permission bitmap, deploy
mock tokens and price feeds plus the Uniswap artifacts, and initialise the pool.
`libraries/EasyPosm.sol` handles positions; `PoolDonateTest.sol` the donate
path.

### 1.3 Experiment layer — `contracts/test/` + `experiments/`

The replay harness is a Forge test driven by a Python orchestrator.

- **`Replay.t.sol` / `ReplayUU.t.sol`** — replay a market window against a
  deployed pool, emit a per-swap event log. `ReplayUU` adds the uninformed flow.
- **`experiments/run_one.py`** — one cell: build inputs, invoke Forge, parse the
  event log, compute metrics, write a manifest.
- **`experiments/matrix.py`** — the full factorial, parallel, resumable, with
  manifest-based deduplication.
- **`experiments/metrics.py`, `aggregate.py`, `stats.py`, `figures.py`** —
  metrics, pairing, tests, plots.
- **`experiments/binance.py`, `windows.py`** — data ingestion and window
  selection.
- **`experiments/manifest.py`** — the reproducibility record (§3.4).

**Test coverage: 109 Solidity tests across 18 suites, 380 Python tests.** The
Solidity suites cover fee direction, bounds, update granularity and edge values
per policy (`test/policies/`), plus deployment permissions, the arbitrage closed
forms, size-search unimodality, the event log, and the UU decision variable
including 16 adversarial cases. The Python suite includes a **differential
golden test** pinning byte-for-byte reproduction of a reference window.

### 1.4 Application layer — `dex/`

A Flask configurator that selects and parameterises a hook, displays the
generated source, and exports a self-contained Foundry project.

### 1.5 Designed but **not** implemented

The submitted text claims these as if built. They must be restated as intended
work:

| claimed                                                                | actual                                    |
| ---------------------------------------------------------------------- | ----------------------------------------- |
| Go backend integration tests                                           | no `.go` file in the tree                 |
| Playwright e2e tests                                                   | no config, no test, no dependency         |
| PostgreSQL with `HookParamsHistory`, `ChainEvent`, `PoolStateSnapshot` | no schema, no code; prose only            |
| Anvil provides the local EVM                                           | Forge's in-process EVM; Anvil is not used |

Reproducibility is currently carried by the per-run manifest and immutable
result files, **not** by a database. Replacement text for each is drafted in
`docs/superpowers/specs/paper-edits-required-2026-08-10.md` (items A6, A7).

---

## 2. Mathematical model

A fee policy is $f_t = F(s_t, z_t; \theta)$ — on-chain state $s_t$, external
signal $z_t$, parameter vector $\theta$. Fees are `uint24` in pips
($10^6 = 100\%$); prices are Chainlink-style 1e8; amounts are WAD 1e18.

### 2.1 Two flows

Order flow is the sum of an **informed** (arbitrage) and an **uninformed**
(retail) process. Modelling them together rather than separately is essential:
under arbitrage-only flow every trade is a loss to the LP by construction, the
LP result improves monotonically as volume is suppressed, and the highest fee
always "wins" by pricing the arbitrageur out. That degeneracy is what the second
flow removes.

### 2.2 Informed flow

With pool price $P$, external price $P^{\text{ext}}$ and fee $\gamma = 1 - f$,
no trade is profitable while

$$P^{\text{ext}} \in \left[ P\gamma,\; P/\gamma \right]$$

Outside the band the arbitrageur trades the profit-maximising size, obtained in
closed form from the constant-product invariant (`ArbMath.sol`). Because gas is
**size-independent**, $\partial G/\partial \Delta x = 0$: it shifts the profit
curve down without moving its peak, so the optimal size is computed first and
gas checked after. That two-step is exactly equivalent to a one-step
optimisation, and it holds only because the arbitrageur cannot split a trade.

### 2.3 Uninformed flow

Per candle and per direction, a trade of size drawn from a lognormal is offered.
It executes with probability

$$P_{\text{exec}} = \begin{cases} 1 & r \ge 0 \\ e^{-\lambda |r|} & r < 0 \end{cases}$$

where $r$ is the source model's **normalised realised return**, computed on the
actual executed amounts (`UUMath.rWad`):

$$r = \frac{V_{\text{out}} - (V_{\text{in}} + G)}{V_{\text{out}} + V_{\text{in}} + G}$$

with $V_{\text{in}}$, $V_{\text{out}}$ the trade's legs valued in a common
currency and $G$ the trade's own gas cost. **Slippage and gas are inside $r$ by
construction**, because $V_{\text{out}}$ is what the pool actually pays out.
This was corrected on 2026-08-10; the earlier form used a marginal-price ratio
and excluded both, which left the gas axis inert.

$r \ge 0$ means the user is trading _toward_ the external price and executes
regardless of the fee — which is why measured participation sits above the
pure-fee curve $e^{-\lambda f/2}$. ($\lambda$ is discussed in §5.1; the factor
of two is the normalisation of $r$, and getting it wrong is what made the
constant too small for two days.)

Two participation modes exist: `share` (deterministic thinning) and `discrete`
(all-or-nothing draws). **All reported results use `discrete`**, chosen because
deterministic thinning produces balanced flow on every candle, which leaves the
arbitrageur with nothing to correct — 24.3% of cells traded no arbitrage at all.
Under `discrete` that falls to 6.4%. The price of the choice is that the matrix
is one realisation of a random process, which is what the seed appendix (§3.6)
answers.

### 2.4 What the model does not contain

- Mocked feeds reproduce **integration**, not oracle behaviour: no aggregation,
  heartbeat, deviation threshold, or latency.
- One retail trade per direction per candle ($k = 1$, §5.2) — the most
  imbalanced assumption available, structural rather than configurable, and an
  assumption rather than a measurement.
- The interior static optimum near $2/\lambda$ is a **property of the assumed
  participation function**, not a finding.
- Impermanent loss depends only on the price the pool ends at; arbitrage pins
  that to the external price at each window's end. **No fee policy can reduce IL
  in this model** (§8.2).

---

## 3. Experimental methodology

### 3.1 Design

Full factorial, replayed per cell:

$$\text{12 policies} \times \text{3 pairs} \times \text{72 windows} \times \text{3 gas scenarios} = 7{,}776 \text{ cells}$$

Windows are one day. 24 per volatility tercile, 72 per pair, so each regime is
equally represented by construction rather than by chance.

**The 12 policies.** The four framework templates of §1.1; four fixed-fee levels
of `MyHook` (§4); and four further policies, evaluated on the same terms but not
presented as templates:

- **`PegDefence`, `PegCapture`** — the two readings of `PegStabilityHook`. One
  charges flow moving the pool _away_ from the peg, the other charges flow
  moving it _back_; they differ in mechanism and not in parameters, so one entry
  cannot represent both.
- **`VolatilityHook`** — EMA and Welford online variance. Written for this
  study.
- **`MEVChargeHookFixed`** — `MEVChargeHook` with a dimensionless impact
  measure. The original computes `absAmount / L`, dividing a token amount by the
  pool's liquidity $L=\sqrt{xy}$, which is not a token quantity, so the ratio
  depends on the price level and on which token is paid in. The variant divides
  by the reserve of the token actually paid in. Written for this study.

All four are in the matrix because a policy is only evidence about a fee
mechanism if it is scored under the same conditions as everything else, and
because reporting only the policies that did well would be selective. **All four
lose to the baseline** (§8.1).

### 3.2 Pairing — the core of the method

Policies are **never** compared as averages. Each policy is joined to the
baseline on every axis except the policy itself:

```python
AXES = ["pair", "window_start_ms", "gas_price_wei", "address_mode"]
merged = others.merge(baseline[AXES + metrics], on=AXES, how="inner")
```

Writing $X_i = M_i + a_i$ and $Y_i = M_i + b_i$ with $M_i$ the common market
term, the difference $d_i = X_i - Y_i = a_i - b_i$ removes $M_i$ **exactly**,
because window, initial price, liquidity, gas and trace are identical. Measured
on one stratum: the range of levels is 228,064 USDT and the range of differences
is 11,725 — a twentyfold noise reduction. Without pairing the effects reported
in §8 are invisible.

### 3.3 Statistics

- **Two-sided Wilcoxon signed-rank** per comparison. Window P&L is heavy-tailed;
  a t-test puts the outlier into its own denominator. Documented case: eight
  wins of eight with one large value gives $p = 0.34$ by t-test and significance
  by Wilcoxon.
- **95% percentile bootstrap interval on the median**, 10,000 resamples, seeded,
  on **every** comparison.
- **Benjamini–Hochberg** at $q = 0.05$ across the declared family, computed per
  valuation, families never pooled.
- **Effect sizes lead; significance is secondary.** The two instruments disagree
  on 10 of 297 comparisons at one operating point and 16 of 297 at the other.
  Concrete case: `MEVChargeHookFixed` is significant in 27 of 27 strata at a
  median of −308 USDT (−2.4% of baseline) — reliable and unimportant.
- **Two co-primary valuations**, always reported together: `net_result`
  (leftover inventory at end-of-window prices) and `net_result_tt` (at
  trade-time prices). An audit found the choice can flip a conclusion's sign, so
  neither is reported alone.

The headline per-policy number is the **median across the 18 volatile-pair
strata** with the bootstrap resampling **strata**, not windows. Pooling the 432
window-level differences would narrow every interval about threefold by treating
three gas scenarios of one window as independent observations.

### 3.4 Reproducibility

A run is identified by $E = \langle C_\theta, D, P_0, L_0, W, S \rangle$:
configured contract, dependency and compiler revisions, initial price, initial
liquidity, market-data window, swap-generation config. A manifest carrying all
six is written per cell and is the deduplication key — a cell recomputes if any
field differs.

`D` includes a hash over `contracts/src/` **and** `contracts/test/`, the solc
version, and submodule revisions. This is load-bearing: on 2026-08-12 it was how
we detected that a results directory held two different models (§9).

### 3.5 Pre-registration

Every experiment has a pre-registration recorded **before** it produced a cell,
fixing family, test, baseline, valuations and predictions. They are not edited
once data exists. Predictions are reported whichever way they come out — one
failed and is reported as failed; one had its **units** invalidated by the
configuration (a percentage of a baseline that turned out negative) and is
reported as unevaluable rather than quietly reinterpreted.

### 3.6 Robustness

| sweep         | question                                            | scope                          |
| ------------- | --------------------------------------------------- | ------------------------------ |
| κ sweep       | does the result depend on the retail/arbitrage mix? | 5 turnover levels              |
| seed appendix | does it depend on the one random draw?              | 5 seeds, both operating points |
| captureShare  | parameter sweep of the arbitrage-only experiment    | 7 levels                       |

Each has its own pre-registration and its own FDR family; none is merged into
the matrix's.

---

## 4. Baselines

**Fixed-fee hooks are run as first-class policies through the identical code
path** — same contract base, same deployment, same replay, same metrics. They
are not analytic reference curves.

| policy            | fee        | role                                                 |
| ----------------- | ---------- | ---------------------------------------------------- |
| `MyHook@500`      | 5 bps      | fee-response curve                                   |
| **`MyHook@3000`** | **30 bps** | **the pre-registered baseline for every comparison** |
| `MyHook@6000`     | 60 bps     | fee-response curve; turns out to be the best static  |
| `MyHook@10000`    | 100 bps    | fee-response curve                                   |

30 bps was fixed in advance as the comparator because it is the common Uniswap
tier. Because the four levels are present, the fee-response curve is measured
and we can also ask the harder question — **how a dynamic policy compares to the
best static fee** — which we report as post-hoc (§8.4).

---

## 5. Parameters

Each parameter is classified by how its value was obtained. This table is the
honest core of the work.

| parameter                     | value                                                          | status                                                                     |
| ----------------------------- | -------------------------------------------------------------- | -------------------------------------------------------------------------- |
| pairs                         | ETH/SHIB, ETH/USDC, USDC/USDT                                  | chosen: volatile, mixed, peg                                               |
| windows                       | 24 per tercile, 72 per pair, 1 day                             | chosen; terciles measured from data                                        |
| gas scenarios                 | 5 / 20 / 80 gwei                                               | chosen to span observed conditions                                         |
| gas per swap                  | calibrated per policy from replay                              | **measured**                                                               |
| initial liquidity $L_0$       | 20,000,000 USDT basket                                         | chosen                                                                     |
| initial price $P_0$           | first candle of the window                                     | **measured**                                                               |
| fee bounds                    | per policy, `uint24` pips                                      | chosen                                                                     |
| $\lambda$ (§5.1)              | 461.404973 = ln(2)/0.0015023                                   | **chosen**, not estimated — see §5.1                                       |
| $\kappa$ (retail scale)       | 0.055174 (ETH/SHIB), 0.025528 (ETH/USDC), 0.023922 (USDC/USDT) | **calibrated** so mean daily uninformed volume over 2024 equals one basket |
| $\sigma$ (lognormal size)     | 1.0                                                            | assumed                                                                    |
| $k$ (trades per candle, §5.2) | 1 per direction                                                | **fixed by the trace format**, never swept — the weakest assumption        |
| seed                          | 0 for the matrix                                               | one draw; **swept** in the appendix                                        |
| $\kappa$ multiplier           | 1.0 headline, 0.1 second point                                 | **swept** (5 levels)                                                       |

### 5.1 $\lambda$ — the participation scale

$\lambda$ is the only parameter of the participation rule
$P_{\text{exec}} = e^{-\lambda|r|}$ for $r < 0$. Since $r$ is dimensionless,
$\lambda$ is dimensionless too: it converts a normalised loss into a probability
of walking away. Large $\lambda$ means price-sensitive retail; $\lambda \to 0$
means retail that trades regardless of cost.

**Value and derivation.** $\lambda = 461.404973$, from the calibration statement
"**half the willing flow walks at a 30 bps total transaction cost**" — total
meaning fee _plus_ slippage _plus_ the signed pool deviation _plus_ the trade's
own gas, since that is what $r$ measures.

The conversion is the part that is easy to get wrong, and we did get it wrong
once. A user who loses a fraction $\varepsilon$ of value has

$$r = \frac{-\varepsilon}{2-\varepsilon} \approx -\frac{\varepsilon}{2}$$

because the numerator is the net loss while the denominator is the **sum** of
both legs. So a 30 bps disadvantage is $|r| = 0.0015023$, not $0.003$, and

$$\lambda = \frac{\ln 2}{0.0015023} = 461.404973$$

**It was 231.049 until 2026-08-10** — $\ln 2 / 0.003$ — from when the
implementation used an un-normalised marginal-price $r = -\varepsilon$ that
excluded slippage entirely. That form is twice the source model's value, so the
old constant made retail decay at half the intended rate. A stale copy of it
survived in one analysis notebook until 2026-08-12 (§9).

**What it controls, beyond participation.** $\lambda$ sets where the static fee
curve turns over. Fee revenue is approximately $f \cdot e^{-\lambda f/2}$, which
is maximised at

$$f^{\star} \approx \frac{2}{\lambda} = 43.3~\text{bps}$$

That lands between our 30 and 60 bps levels, and 60 bps is indeed the best
static level measured. **So the interior optimum is a property of the assumed
participation function, not a discovery** — a point the paper must make
explicitly, because an interior optimum otherwise reads as an empirical finding.
It is also why §8.4's comparison against the best static fee is the demanding
one: that comparator sits near an optimum this model put there.

**Status: chosen.** No retail fee-elasticity was estimated from data — the AMM
traces that would support one were not collected, and Binance quote volume gives
volume, not the counterfactual of a walked-away trade. $\lambda$ is **not**
swept. $\kappa$ is swept instead, and the two are not interchangeable: $\kappa$
scales _how much_ retail there is, $\lambda$ decides _how it responds to price_.
A sensitivity analysis in $\lambda$ is the most valuable single addition this
model could receive, and it does not exist.

### 5.2 $k$ — potential trades per candle, and why it is 1

$k$ is the number of potential retail trades offered **per direction per
candle**. It is **1**, and it is not a runtime parameter: the trace CSV the
harness reads has exactly one `(size, u)` pair per direction per candle,

```
open_time, size_ab_wad, u_ab_wad, size_ba_wad, u_ba_wad
```

so $k = 1$ is baked into the file format. The design spec proposed
$k \in \{1,2,3\}$; that was never implemented, and no result varies it.

**Why it matters far more than it looks.** In `discrete` mode each direction is
an independent all-or-nothing draw. With $k=1$ a candle commonly executes one
direction and not the other, so retail flow is **one-sided**, the pool is
displaced, and the arbitrageur has something to correct. Raising $k$ would
average the directions within a candle, shrink net displacement, and push the
model toward `share` mode — where measured arbitrage falls to 1.1% of volume
with half the cells trading no arbitrage at all.

So $k=1$ is **the most imbalanced assumption available**, and the
retail/arbitrage mix reported throughout this work rests on it.

**The honest statement.** One might expect the imbalance between retail and
arbitrage to emerge from volatility rather than be imposed. It does for the
arbitrageur — volatility moves the external price, which is what creates
arbitrage opportunity. It does **not** for retail: retail one-sidedness here is
a consequence of $k=1$ and the independent coin per direction, not of anything
measured. Real retail order flow is imbalanced for reasons this model does not
contain (momentum, sentiment, listing events).

$k$ is therefore the weakest assumption in the model — weaker than $\lambda$,
which at least has a stated calibration, and weaker than $\sigma$, whose effect
is absorbed into the seed spread. **It is fixed, unswept, and structural**, and
any claim about the flow mix should be read as conditional on it.

**Why there are two operating points.** $\kappa$ was calibrated on **turnover**,
but the mechanism under test depends on the **share of flow that is informed**,
which turnover does not control. At the calibrated $\kappa$ the arbitrage share
is 15% of ETH/SHIB volume. The κ sweep showed the advantage of an adaptive fee
rising steeply with the informed share — meaning **the calibrated point is the
weakest point on that curve.**

That is not a reason to move the headline. $\kappa = 1.0$ is the calibrated
value, and selecting an operating point because it flatters the result is what
pre-registration exists to prevent. It is a reason to report a second point
where both flows are comparably present, and to let a reader see that the
unfavourable configuration was kept as the headline.

| point           |   κ | arbitrage share, ETH/SHIB | baseline result (mean) |
| --------------- | --: | ------------------------: | ---------------------: |
| **A, headline** | 1.0 |                       15% |    +13,002 USDT/window |
| **B, informed** | 0.1 |                       56% |       −488 USDT/window |

Both are reported; neither replaces the other; **their FDR families are not
pooled.**

---

## 6. Datasets

**Binance 1-minute klines, calendar year 2024**, for ETHUSDT, SHIBUSDT and
USDCUSDT. Cached locally and replayed offline; no live feed is involved.

- **Windows** span 2024-01-01 to 2024-12-26, one day each, 72 per pair.
- **Volatility terciles** are computed from realised volatility over the year,
  and windows are drawn 24 per tercile so each regime is equally represented.
- **The stable pair's second leg** (`CONST1`) is a synthetic feed pinned at 1.0.
  It is **not** a market observation and is documented as such.
- κ's calibration window is the full 2024 UTC year, so κ is a per-pair constant,
  not a per-window quantity.

Three kinds of value are kept strictly distinct and never conflated: configured
constants, reference-market inputs, and endogenous pool outputs. Canonical hook
sources are never simulation results; raw market observations are never inferred
from the pool.

---

## 7. Metrics

Per cell, 18 metrics. The ones that carry the argument:

| metric                           | meaning                                                   |
| -------------------------------- | --------------------------------------------------------- |
| `net_result`                     | LP value vs HODL at end-of-window prices — **co-primary** |
| `net_result_tt`                  | the same at trade-time prices — **co-primary**            |
| `fee_income`                     | fees accrued to the LP                                    |
| `il`                             | impermanent loss vs HODL                                  |
| `gas_cost`                       | gas paid, valued in USDT                                  |
| `retained_volume`                | volume that actually executed                             |
| `uu_volume` / `arb_volume`       | the flow split                                            |
| `uu_fee_share`                   | share of fee income paid by retail                        |
| `uu_participation`               | retained potential retail volume ÷ potential              |
| `arb_mtm`, `arb_profit_realized` | arbitrageur inventory and realised profit                 |
| `trade_count`                    | trades executed                                           |
| `conservation_error_token0/1`    | **integrity**: token conservation residual                |

**Retained volume travels with every result.** Without it, "charge the maximum
so nobody trades" reads as a win. Conservation error is asserted, not inspected:
worst observed across all runs is 5.5e-16, and it once caught a silent int64
overflow that would have corrupted every figure without anything failing.

---

## 8. Main results

7,776 cells per operating point, **0 errors**, worst conservation 4.3e-16.

### 8.1 The comparison against the fixed-fee baseline

Median difference vs static 30 bps, across the 18 volatile-pair strata, with 95%
bootstrap intervals:

| policy               |           point A (κ=1.0) |         point B (κ=0.1) |
| -------------------- | ------------------------: | ----------------------: |
| **`DAHook`**         |     **+341 [+263, +672]** |   **+184 [+140, +295]** |
| `BAHook`             |         +114 [−108, +549] |        +155 [−28, +713] |
| `MyHook@6000`        |          −81 [−197, +280] |        +193 [+11, +673] |
| `ABHook`             |         −254 [−440, −191] |          −47 [−72, −36] |
| `MEVChargeHookFixed` |         −308 [−499, −151] |          −52 [−98, −42] |
| `MEVChargeHook`      |       −847 [−1,399, −656] |          −59 [−84, +63] |
| `PegCapture`         |   −4,602 [−5,847, −4,144] |       −487 [−842, −309] |
| `VolatilityHook`     |  −8,716 [−15,772, −6,786] |   −1,444 [−3,387, −841] |
| `PegDefence`         | −10,880 [−20,927, −8,811] | −1,864 [−4,528, −1,274] |

**`DAHook` is the only policy whose interval clears zero at both operating
points.** At point B it wins in 18 of 18 strata.

**`BAHook`'s interval covers zero at both**, despite being significant in 10 of
18 strata at each. It is not a winner on effect size anywhere. **Most policies
lose to the fixed-fee baseline**, several catastrophically.

The advantage is concentrated: `DAHook` on ETH/SHIB is +211 in low volatility
and +1,228 in high; on the peg pair every dynamic policy loses. `BAHook`
additionally collapses across the gas axis at point A (+547 at 5 gwei, **−309**
at 80 gwei) while `DAHook` holds (357 / 519 / 209).

### 8.2 The advantage is fee capture, not reduced adverse selection

Decomposing the paired difference on the volatile pairs:

| policy   | net result | fee income | **impermanent loss** | retained volume |
| -------- | ---------: | ---------: | -------------------: | --------------: |
| `DAHook` |       +376 |   **+346** |               **−7** |          −1.27M |
| `BAHook` |       +124 |       +182 |                  −11 |          −1.75M |
| `ABHook` |       −261 |       −263 |                   −1 |          −0.07M |

`il_delta` is single-digit USDT against effects in the hundreds, at every
policy. This is structural: for a constant-product pool IL depends only on the
price the pool ends at, arbitrage pins that to the external price at each
window's end, and every policy therefore inherits the same IL.

> **A fee policy in this model cannot reduce adverse selection. It can only
> price flow better.** Prose describing these hooks as "protecting the LP from
> arbitrage" is not supported.

### 8.3 It is not achieved by taxing arbitrage

Retail's share of fee income ÷ retail's share of volume. A static fee is 1.000
by construction, which is the control:

| policy       |   point A |   point B |
| ------------ | --------: | --------: |
| `PegCapture` |     0.797 |     0.588 |
| any static   |     1.000 |     0.998 |
| `BAHook`     |     0.998 |     0.985 |
| **`DAHook`** | **1.035** | **1.235** |
| `PegDefence` |     1.254 |     1.976 |

`DAHook` loads a **larger** share of fees onto retail than a static fee does.
The only policy that genuinely shifts the burden onto arbitrage is `PegCapture`,
which is among the worst performers. The "discriminate against toxic flow"
framing is **not** what the winning policy does here.

### 8.4 Against the best static fee (post-hoc, not pre-registered)

The pre-registered baseline is 30 bps. The best static in the box is 60 bps:

| policy   |               point A |            point B |
| -------- | --------------------: | -----------------: |
| `DAHook` | **+350 [+224, +449]** | **−2 [−177, +82]** |
| `BAHook` |     +319 [−150, +575] |     −26 [−82, −11] |
| `ABHook` |      −143 [−637, −60] |   −247 [−691, −39] |

At the calibrated point `DAHook` beats even a well-chosen static fee, cleanly.
**At the informed-heavy point it is indistinguishable from one**, and the
ranking there is led by a static 60 bps. This is the sharpest limitation the
study has, and it should be stated in the paper rather than left for a reader to
find.

### 8.5 Reading the baseline at point B

Mean **−488** USDT/window, median **+1,201**. Both are true and they say
different things: the typical window still makes money, and a minority of
windows lose enough to take the average below zero. "The LP loses money at this
mix" is fair about the year and false about a typical day. The two must be
quoted together.

This is also why point B's pre-registered prediction — "the advantage will be
roughly +10% of the baseline" — **cannot be evaluated as written**: a percentage
of a negative baseline flips sign. Reported as a prediction whose units did not
survive the configuration, neither confirmed nor refuted.

### 8.6 Robustness

**Seeds.** Five seeds, both operating points, 960 cells each, 0 errors. **Every
policy keeps its sign across all five seeds at both points**, so neither ranking
needs an "at this seed" qualifier. The **magnitude** is another matter: at point
A `BAHook` on ETH/SHIB spans +22 to +696 around a median of +174, a factor
of 31. **Sign may be reported; a single number for the size may not.** Seed
sensitivity collapses at point B (`DAHook`'s spread falls from 644 to 30) —
mechanically, since most per-window variance comes from the retail draw and
there is ten times less retail.

Seed 0 of the appendix reproduces the matrix **bit for bit** across all 192
shared cells at both points. Its _magnitudes_ are not comparable to the matrix's
— it uses 8 windows per tercile rather than 24, and that subset understates the
effect at point A (+284 vs +484) and nearly doubles it at point B (+350 vs
+196). It is read for sign and spread only.

**κ.** The advantage rises with the informed share: from about +1% of baseline
at 18% arbitrage to +17–21% at 82%. Its **ratios do not transfer** to the full
matrix — the sweep measured a ratio to a baseline still positive on 24 windows
and one gas scenario, while the full matrix at three gas scenarios drives that
baseline negative.

### 8.7 The sentence the evidence supports

> The value of a dynamic fee scales with the share of informed flow, and what it
> buys is better fee capture on a smaller retained flow — not protection from
> adverse selection.

Conditions: one year, three pairs, a synthetic retail model whose key parameters
are chosen rather than measured, one seed per cell with the spread reported, and
a comparison against a static fee that a well-chosen constant matches at one of
the two operating points.

**Not** "dynamic fees beat static fees."

---

## 9. Known integrity issues, and what was done about them

Stated because a reader integrating this work is entitled to know how the
artifacts were checked, and because the checks found real problems.

**Two models in one results directory (found 2026-08-12).** `results-uu/matrix/`
held 7,776 current cells beside 7,776 from the run withdrawn by the `r`
correction, distinguished only by a field inside the filename. A directory load
returned 15,552 cells across two models, on which `DAHook`'s median reads 16,816
against the true 12,240 — a 37% error. **`results-uu/summary.csv` was never
affected**, as it is built from the run's own spec list. The withdrawn half is
quarantined; `manifest.assert_one_model()` now refuses a directory whose
manifests disagree on the contract source hash, and the analysis calls it before
reading anything. Cell counts could not have caught this — a blended directory
has _more_ cells, and the existing guard fired only on fewer.

**A stale λ in an analysis notebook (found 2026-08-12).** A reference curve was
computed with λ = 231.05, the value from before `r` was corrected to include
slippage and gas; the model uses 461.40. Affected one displayed diagnostic
column, no result. The constant is now imported rather than retyped.

**A results artifact overwritten by the test suite (found 2026-08-11).** The
seed appendix's test file wrote its fixture over the real `seed_tests.csv` on
every `pytest` run. Nothing published was affected — the raw `seeds.csv` is the
record and was untouched — and the file regenerates from it exactly. The write
is now gated and a regression test asserts a fixture run leaves it
byte-identical.

**Mixed provenance in the arbitrage-only matrix.** 111 of 15,552 cells carry a
different contract revision. Their numbers are **bit-identical** to their twins
at the original revision, so the metadata is inconsistent and the results are
not; the change did not touch the arbitrage-only path.

**Lost artifacts.** The arbitrage-only per-swap traces were destroyed by a
filename collision on 2026-08-10 and cannot be regenerated; per-cell metrics
survive. The affected notebooks detect this and skip the trace-dependent cells
rather than drawing from the few stray files that remain. One arbitrage-only
figure is unrecoverable and is not in the paper.

---

## 10. What integration requires

1. **Restate the three unimplemented components** as designed work (§1.5).
   Drafted replacement text exists.
2. **Report both operating points**, always, with the arbitrage share each
   produced stated beside the result. A figure from one without the other
   violates the pre-registration.
3. **Lead with effect sizes and intervals**; significance second.
4. **Carry §8.2, §8.3 and §8.4 into the paper** at the same prominence as the
   positive result. They are the reason the economic claim is defensible.
5. The paper's own claim boundary moves from "engineering feasibility" to
   "engineering feasibility, plus a controlled comparison under a synthetic
   two-flow model" — and no further.

Full detail: `learning/the-model-end-to-end.md` (model and parameter table),
`learning/statistics-for-our-experiment.md` (methods),
`learning/what-we-ran-and-what-it-says.md` (inventory), and the
pre-registrations under `docs/superpowers/specs/`.
