# Experiment Design: Dynamic Fees on Uniswap v4

Date: 2026-08-02

Paper: "A Configurable Dynamic-Fee Hook Framework for Uniswap v4 Liquidity
Pools" (IEEE ICBC 2026, submission 1571326575)

## 1. Purpose

The paper currently claims engineering feasibility and explicitly declines any
claim of economic superiority: it has no same-trace fixed-fee baseline, no
repeated trials, no uncertainty intervals, and no gas measurements. The purpose
of this work is to supply all four and obtain a controlled comparison of
dynamic-fee policies.

The target claim, to be either confirmed or honestly refuted: **at an equal fee
budget, allocating the fee dynamically across swap directions yields a better LP
outcome than allocating it uniformly, and the advantage survives the gas
overhead.**

## 2. Out of Scope

- Noise (uninformed) traders. Order flow is arbitrage-only.
- Concentrated liquidity. Full range only.
- Public-chain microstructure: mempool visibility, block-builder ordering, gas
  competition, strategic arbitrage, endogenous routing.
- The web configurator and project export.
- Execution against an Anvil node. Everything runs in Foundry's built-in EVM.
- Testnet validation.

## 3. Repository Layout

`dex` (github.com/ifde/dex) is abandoned, so the needed parts are moved into
`swap-hooks` and maintained there. It is not attached as a submodule.

```
swap-hooks/
├── paper/            the paper (LaTeX)
├── contracts/        Solidity: src/, test/, lib/, foundry.toml, remappings.txt
├── experiments/      Python: data loading, event parsing, metrics, plots
├── data/             Binance kline cache (gitignored)
├── results/          run outputs (gitignored, except final tables)
└── docs/             specs and plans
```

**Moved over:** `src/` (six policies + `MyHook` + `CustomBaseHook` +
`interfaces/`), `test/utils/` (`BaseTest`, `Deployers`, `HookTest`, `EasyPosm`,
`HookFlags`, `HookConstants`), `foundry.toml`, `remappings.txt`, the six
submodules from `.gitmodules`, and `fetch_binance_data.py` as a starting point.

**Not moved:** `web_interface/`, `notes/`, `.typ` files, the slide deck, stale
CSVs, `simulation_output.txt`, `trades*.csv/json`, `Counter.sol`, and `script/`
(deployment scripts are unnecessary under forge-only execution).

**Deleted:** `experiments/test.ipynb` — a three-cell stub.

Prerequisites: `foundryup`; `git submodule update --init --recursive`.

## 4. Experiment Definition

### 4.1 A Single Run

The input is a window of historical data — one-minute klines for two pairs from
Binance. A Uniswap v4 pool is deployed with the selected policy and liquidity is
placed across the full range.

Full range reproduces Uniswap v2's **curve shape**, but not its fee handling. In
v2 the fee stays in the reserves and grows `k`, so an LP earns fees on fees. In
v4 the fee never joins the position's liquidity `L`: it is credited to the
position through `feeGrowthInside` and claimed separately. Fee income therefore
does not compound within a window, and it must be read from the pool's fee
accounting rather than inferred from reserves — see §14.1.

Iterating over the candles, at each step:

1. The mock feeds are updated with the new prices.
2. The arbitrage condition is evaluated.
3. If profitable, a swap of the optimal size is executed.
4. The hook emits an event carrying every observable quantity.

### 4.1.1 What a Mock Feed Is

A smart contract cannot reach outside the chain and query Binance. Price oracles
exist for this reason: contracts in the same network that hold a current price
(Chainlink Data Feeds). A hook that needs an external price calls
`latestRoundData()` on one.

No real oracle exists inside a test. Instead a contract with the same interface
is deployed, holding a value we set: at each candle, `updateAnswer(price)` is
called with the historical price. The hook cannot tell the difference — it calls
exactly the function it would call on mainnet. In this repository that contract
is `MockV3Aggregator` from `chainlink-local` (`HookTest.sol:67`).

A mock validates **integration** — that the hook reads the feed correctly,
normalises decimals, and computes the ratio — but not the behaviour of a
production oracle, which has update latency, a heartbeat, a deviation threshold,
and the possibility of a stale round. In our setup the price changes
instantaneously and is always fresh. The paper states this caveat at line 286;
it must be preserved when interpreting results.

### 4.2 The Arbitrageur

This is the only model that requires justification.

Entry condition:

$$\Pi^{*}(\Delta) - \text{gas} > 0$$

where $\Delta$ is the trade size. The size is derived in Appendix A.

> **Corrected 2026-08-10 (D8).** This line previously read
> $\Pi(\Delta) - \text{fee}(\Delta) - \text{gas} > 0$, which subtracts the fee
> twice: $\Pi^{*}$ as derived in §A.2–§A.4 already has the fee inside it through
> $\gamma = 1 - f$, since only $\gamma\Delta x$ reaches the invariant. §A.4's
> "execution requires $\Pi^{*} >$ gas cost" was always the correct statement and
> is what the harness implements — `contracts/test/Replay.t.sol:399` gates on
> `expected <= _gasCostInToken1(candle)`, with `expected` returned by
> `ArbMath.profit`. No executed run was affected; only this sentence was wrong,
> and it is the one a reader meets first.

The size is chosen **optimally** — trading up to the point where the marginal
unit of volume stops being profitable. For a constant-product pool whose fee
does not depend on the trade size, that point has a closed form and no numerical
search is required; this covers every policy except `MEVChargeHook`, whose
impact surcharge reads `amountSpecified` and therefore requires a search. See
§A.8.

Consequences:

- **The fee affects flow.** A higher fee widens the no-arbitrage band, so the
  arbitrageur arrives less often and in smaller size. This is precisely what the
  previous implementation lacked: its entry threshold was the constant
  `minPriceGap = 5` and ignored the fee entirely.
- **Gas affects flow.** An expensive policy raises the entry threshold. Gas is
  part of the mechanism, not a line in a report.
- **Direction is set by the external market**, not by a random number generator.

Capital is unconstrained: the optimal size is always executable. This is a
simplification and must be stated in the validity section — it yields an upper
bound on arbitrage pressure.

### 4.3 Liquidity

Full range. The pool is initialised **exactly at the external price at the start
of the window** — otherwise the first action would be an arbitrage that removes
an artificial discrepancy, contaminating the metrics more the shorter the
window.

Initial liquidity `L₀` is specified as a basket size in the numeraire, identical
across all runs: **20,000,000 USDT**, split equally by value between the two
tokens at window start.

The figure was set empirically on 2026-08-03. Arbitrage profit scales as
`y·ε²/4`, where `y` is the **quote-side reserve** — half the basket — so in
basket terms `V·ε²/8`. A shallow pool therefore needs a large price deviation
before a trade clears its gas cost.

> **Corrected 2026-08-10 (U5).** This read `V·ε²/4` with `V` the basket, a
> factor of 2 too large. From §A.5's `Π* = L(s−t)²/s`, the small-deviation limit
> is `y·ε²/4`; §4.3 discusses 1M vs 20M **baskets**, so the substitution
> `y = V/2` has to be made explicit. The empirical table below is a measurement
> and is unaffected; only the scaling law quoted beside it was wrong. The same
> `y·ε²/4` form is used correctly (with `y` = 10M against a 20M basket) in
> `2026-08-10-kappa-sensitivity-preregistration.md`.

Measured over 1 Jan 2024 on ETH/SHIB at 30 bps, one day yields:

| Basket | 5 gwei | 20 gwei | 80 gwei |
| ------ | ------ | ------- | ------- |
| 1M     | 5      | 1       | 0       |
| 20M    | 25     | 11      | 7       |

At 1M the whole low-volatility tercile would carry a handful of trades per
window or none at all, for every policy at once, and a window that thin says
nothing about policy differences. At 20M the same days are workable, and the
depth is closer to a real ETH pool. A uniform size matters because the
arbitrageur's entry threshold depends on the ratio of gas cost to pool depth; at
differing depths the policies would be compared under different regimes. The
basket size is recorded in the manifest and promoted to a separate axis only if
a sensitivity check becomes necessary.

### 4.4 Baseline

`MyHook` with a fixed fee — not a hookless pool. Same execution path, same
callbacks, same wrapper gas cost. Any difference in results is then a difference
between policies, not between having and not having a hook.

Four levels: **5, 30, 60, and 100 bps.**

### 4.5 The Fee Box

Shared by every policy and every baseline, per direction:

```
f_min =   100 pips =   1 bps
f_max = 10000 pips = 100 bps
```

This forecloses the obvious objection — that a dynamic policy won merely because
it was permitted to charge more.

`ABHook` additionally retains its own constraint on top of the box:
`feeAB + feeBA = K`, with `K = 6000` pips. Its average fee is therefore exactly
`K/2 = 30` bps, coinciding with the 30 bps static level and giving an exactly
paired comparison: identical fee budget, the only difference being how it is
allocated across directions.

## 5. Policies Under Test

| Policy                 | Signal                                        | Role                           |
| ---------------------- | --------------------------------------------- | ------------------------------ |
| `MyHook` × 4 levels    | constant                                      | baseline                       |
| `BAHook`               | sign of external ratio change, once per block | naive                          |
| `DAHook`               | direction of the previous trade               | naive, oracle-free             |
| `ABHook`               | pool price change, constant fee sum           | reallocation                   |
| `PegStabilityHook`     | pool deviation from the external price        | capture (`captureShare` = 0.5) |
| `MEVChargeHook`        | per-address history, trade size               | behavioural                    |
| `VolatilityHook` (new) | EMA + Welford variance                        | volatility-adaptive            |

`PegStabilityHook` is run in **both** available readings, as two configurations:

- **`PegDefence`** — the fee applies to trades pushing the pool _away_ from the
  reference. Faithful to the name and to §III of the paper. Under arbitrage-only
  flow every trade is restoring, so this configuration is expected to sit at
  `f_min` throughout; that is a legitimate finding about applicability rather
  than a failure.
- **`PegCapture`** — the fee is proportional to `|deviation|` on whichever trade
  occurs, taxing the arbitrageur for correcting the pool. This is the
  oracle-informed policy that captures LVR.

Running both makes the distinction explicit instead of resolving it by
assumption, which matters because the two differ in mechanism, not in
parameters.

Eleven configurations in total.

> **Corrected 2026-08-10 (E3).** The `PegStabilityHook` row read "capture
> (κ=1)". No run ever used 1. The contract's configured value is
> `captureShare = 500_000` = **0.5** (`contracts/src/PegStabilityHook.sol:70`),
> and κ = 1 is provably inert: the proof at lines 59–68 shows it makes the
> no-arbitrage band exactly contain the pool price, so the arbitrageur is left
> nothing and never trades — measured as zero trades under every gas price and
> pool depth. The symbol was also changed from κ to `captureShare` because the
> UU documents use κ for the retail-volume scale; two different κ in one paper,
> one of them in a document titled "the κ sensitivity sweep", is a collision the
> paper must not inherit. Note what this exposes: `captureShare` is the single
> most decisive parameter in `PegCapture` — the 2026-08-03 sweep found it flips
> the sign of the result (at 0.10 the policy significantly loses in every
> regime, at 0.75 it significantly wins) — and
> `2026-08-04-power-extension-preregistration.md` pins it only **by reference**
> ("`captureShare` stays at its single configured value"), never by value. That
> pre-registration is frozen and is not edited; the paper must state the value
> that ran and note that 0.5 is the _weakest_ winning setting, so the choice is
> conservative rather than favourable.

> **Amended 2026-08-10 (C2).** "Eleven configurations" is left as written
> because the 2026-08-04 pre-registration's family count derives from it. A
> **twelfth**, `MEVChargeHookFixed`, was added on 2026-08-03 and is what
> `2026-08-09-uu-flow-design.md` §8 and the UU pre-registration mean by "12
> policies". It is a corrected variant authored here, not part of the evaluated
> artifact: it overrides `_impactRatioBps` to divide by the reserve of the token
> actually paid in, which is a policy-logic change and therefore an exception to
> §13's discipline. The exception is defensible — it repairs a dimensional
> error, and the shipped template runs unchanged beside it — but it was never
> amended into this document, and the paper must say plainly that the variant is
> ours. §9's run-matrix arithmetic is left at eleven for the same reason and is
> superseded by the UU design §8.

## 6. New Hook: `VolatilityHook`

Rationale: the paper twice claims an implementation of EMA and Welford's
algorithm (lines 56 and 212). Neither appears in the code — not in any of the
nine branches, not in any commit in history. No variance is computed anywhere.
Moreover, none of the five existing policies is volatility-adaptive, even though
the paper's entire motivation rests on volatility.

Mechanism. The exponential moving average keeps one state variable and weights
recent observations more heavily:

$$\mu_t = \alpha\,x_t + (1 - \alpha)\,\mu_{t-1}$$

Welford's algorithm updates mean and dispersion together, storing only $n$,
$\mu$, and $M_2$:

$$ \begin{aligned}
n &\leftarrow n + 1 \\
d &\leftarrow x - \mu \\
\mu &\leftarrow \mu + \frac{d}{n} \\
M_2 &\leftarrow M_2 + d\,(x - \mu) \quad \text{(with the updated } \mu) \\
\sigma^2 &= \frac{M_2}{n - 1}
\end{aligned}$$

The fee then scales with the standard deviation:

$$f = \mathrm{clamp}\!\left(f_{\text{base}} + c\,\sigma,\; f_{\min},\; f_{\max}\right)$$

Welford rather than the naive `E[x²] − E[x]²` because the latter suffers
catastrophic cancellation when the mean is large relative to the spread — the
typical case for prices.

Implemented in fixed point at 1e18 scale. Variance is checked against a
reference computed in Python on the same inputs.

## 7. Data and Windows

### 7.1 Fetching

The current `fetch_binance_data.py` sets `limit=1000` with no pagination, so a
requested "month" is in fact the first 16.7 hours. It is rewritten with a loop
over `startTime` and an on-disk cache, so repeated runs neither hit the network
nor depend on what the API returns that day.

Output filenames are no longer hardcoded (they are currently always
`ETHUSDT-1m-latest.csv` regardless of the arguments passed).

### 7.2 Pairs

| Pair      | Feeds                | Regime          |
| --------- | -------------------- | --------------- |
| ETH/SHIB  | ETHUSDT, SHIBUSDT    | high volatility |
| ETH/USDC  | ETHUSDT, USDCUSDT    | major           |
| USDC/USDT | USDCUSDT, constant 1 | stablecoin      |

The third pair is required; without it `PegStabilityHook` enters the table with
an uninterpretable number.

Year: 2024.

### 7.3 Window Selection — Volatility Stratification

Window length is **one day** (1440 candles). Selection is mechanical, with no
manual choice:

1. Partition the year into non-overlapping daily segments.
2. For each, compute realised volatility — the standard deviation of per-minute
   log returns of the `token0/token1` price ratio, scaled by `√1440` to a daily
   basis.
3. Split into terciles: low / medium / high.
4. From each tercile take 8 segments, spaced evenly by index within the tercile
   (every `k`-th when sorted by date) → **24 windows per pair**.

A **tercile** is the same idea as a quartile, but splitting into three parts:
all 366 daily segments are sorted by volatility and cut into three equally sized
groups — the calmest third, the middle third, and the stormiest third.

> **Corrected 2026-08-10 (C7).** This said 365. 2024 is a leap year, so there
> are 366 daily segments and 122 per tercile exactly — which is the number the
> 2026-08-04 pre-registration uses ("122 days available per tercile") and what
> the code reports. The count of windows drawn per tercile is separately
> superseded: this section says 8 (24 per pair), the 2026-08-04
> pre-registration raised it to 24 (72 per pair), and that document governs.

Why stratify rather than take 24 random days: calm days typically outnumber
volatile ones, so a random sample would likely be predominantly calm and we
would simply not observe how the policies behave under stress. That is precisely
what matters — a volatility-adaptive policy is by definition supposed to show
itself under volatility. Stratification guarantees all three regimes enter the
sample and allows reporting each separately, instead of a single average in
which the storm dissolves into the calm.

This satisfies what §V-B of the paper requires ("multiple pairs, volatility
regimes, and repeated windows"). The likely substantive finding is that dynamic
policies win under high volatility and lose to gas overhead under low.

Days rather than months: the year holds only 12 monthly segments and they are
similar in regime, whereas 365 daily segments give something to stratify over. A
daily run also takes ~3 s against ~80 s.

### 7.4 Warm-up

The first hour of each window is executed but excluded from the metrics:
`BAHook`, `ABHook`, and `VolatilityHook` accumulate state, and during the first
minutes the hook operates on initial rather than learned values. Warm-up is
applied identically to every policy, including the static baselines, so the
comparison stays fair.

### 7.5 Absence of Randomness

Order flow is purely arbitrage-driven and trade size is determined by
optimisation, so no randomness remains in the simulation. One trace yields one
result, bit for bit. Dispersion comes only from differences between windows; the
"random seed" element of §V-B is absent because nothing requires it.

## 8. Gas Scenarios

Gas is not reported after the fact — it enters the arbitrageur's entry condition
and therefore changes the flow. Since the interesting question is where the
break-even boundary of a dynamic hook lies, gas price is a run axis rather than
a constant.

Three scenarios, in gwei: **5 (low), 20 (medium), 80 (high).**

Conversion to the numeraire uses the ETH/USDT feed at the time of the swap, so
`ETHUSDT` is loaded for every pair, including `USDC/USDT`, where it serves only
to price gas.

Execution gas is measured in Foundry's EVM. The intrinsic 21,000 gas and the
calldata cost are identical across policies and therefore cancel in the
comparison; they are added analytically as a constant so that the absolute
profitability threshold remains correct.

## 9. Run Matrix

```
11 configurations × 2 address modes × 3 pairs × 24 windows × 3 gas scenarios
= 4752 runs
```

The **address mode** is `persistent` (a single arbitrageur address for the whole
window) versus `fresh` (a new address per trade). This axis exists because of
`MEVChargeHook`, which derives its fee from the history of a specific address
(`_lastBuyToken0/1[payer]`, window `cooldownSeconds = 15`). With 12-second
blocks a persistent address is almost always inside the cooldown, turning the
hook into "expensive for anyone who trades regularly". Running both
configurations gives it an interpretable result instead of a single number of
unclear provenance; for the other policies it doubles as a check that they are
indeed address-insensitive.

Estimated cost: ~3 s per run, roughly 4 hours for the full matrix. Compilation
happens once.

## 10. Run Manifest

Each run writes alongside its results:

- the configured contract and policy parameters (`C_θ`)
- submodule revisions and compiler version (`D`)
- initial pool price (`P₀`) and initial liquidity (`L₀`)
- window boundaries with exact timestamps (`W`)
- arbitrageur parameters and gas scenario (`S`)
- a checksum of the input klines

These are the fields of `E = ⟨C_θ, D, P₀, L₀, W, S⟩` from Eq. (9). The paper
notes that only the project structure is currently recorded and that the full
manifest is a "concrete extension needed for artifact-level reproducibility".

## 11. Architecture

**Solidity executes, Python computes.**

The Forge test runs the swaps and emits events. It derives nothing. Python reads
the events and computes everything else.

Rationale:

- metrics can be changed without touching the contracts or recompiling — which
  matters, since the target metric is not yet fixed;
- no integer arithmetic in the analysis (in the current code, truncation from
  dividing by `10**26` zeroed half the metrics);
- there is exactly one pool implementation — the real one, from Uniswap — so
  divergence between a model and the contract is impossible by construction;
- it closes the weakness the paper itself names at line 318: "console parsing is
  less robust than a structured event-level result format".

### 11.1 Event Schema

Per swap:

```
candle index, block number, timestamp
external price of token0, external price of token1
pool price before and after (sqrtPriceX96)
direction, input size, output size
applied fee, both current hook fees
balance deltas
gas for this swap
sender address
```

One event per window: initial and final pool state, LP position parameters.

## 12. Metrics

Everything is computed; the headline metric is chosen once the first numbers are
in.

- LP position value
- fee income (per token and in the numeraire)
- IL per Eq. (3), net result per Eq. (4)
- LVR
- net outcome against HODL
- retained volume and trade count
- distribution of applied fees
- total and mean gas
- arbitrageur profit

**Numeraire: USDT.** Both tokens are valued from their feeds at the valuation
time, which is the end of the window. The current artifact does not define a
numeraire at all, which is why the aggregates `Q` and `F_j` in the paper carry
no interpretation. Fees are additionally stored per token so the valuation can
be recomputed at a different time without re-running.

Arbitrageur profit matters more than it appears: in an arbitrage-only world,
what the LP loses someone else receives, which closes the balance.

> **Superseded 2026-08-10 (C5), noted so nobody flags it as a silent
> reopening.** "The valuation time, which is the end of the window" is no longer
> the only valuation. `2026-08-09-uu-flow-design.md` §6 declares a **second,
> co-primary** valuation at trade-time prices, and the 2026-08-09
> pre-registration declares it before the data with its post-hoc motivation
> disclosed. That is a superseding amendment done correctly. The two are
> different functionals, not one quantity under two valuations — see the §6
> amendment for the algebra and the naming.

> **§12.1 below is a PRE-REGISTRATION and is FROZEN.** Data exists for it; it is
> not edited, including where it is wrong. The 2026-08-10 review found two
> arithmetic errors in its Bonferroni justification (the family size and the
> number of windows per comparison) whose stated conclusion nevertheless
> survives. Both are recorded, with the corrected values, as items 7–8 of the
> disclosure list in `2026-08-09-uu-flow-design.md` §12.

### 12.1 Pre-Registered Analysis Plan

Recorded 2026-08-02, before any run. Pre-registration only counts when it
precedes the data.

**No single primary hypothesis is designated.** This is a framework evaluation;
privileging one pairing would quietly turn the paper into a paper about that
pairing. The entire family of comparisons is declared instead.

**Family.** Every policy configuration against the static 30 bps baseline
(`MyHook` at 3000 pips), in every stratum: 3 volatility regimes × 3 gas
scenarios × 2 address modes × 3 pairs.

**Quantity.** Per-window paired difference in net LP result against HODL.

**Test.** Two-sided Wilcoxon signed-rank per comparison — non-parametric because
window-level LP P&L is heavy-tailed and a single large price move would dominate
a t-test on 24 observations — followed by the Benjamini–Hochberg procedure across
the whole family at `q = 0.05`.

Benjamini–Hochberg rather than Bonferroni: with roughly 90 comparisons the
Bonferroni threshold is `0.00056`, which a Wilcoxon test on 24 windows cannot
reach even at 24 wins out of 24. Controlling the false discovery rate keeps the
design able to detect anything at all.

**Always reported beside every comparison:** median difference in USDT, the same
figure as % APR on the basket, and the fraction of windows won. A significance
flag is never reported without an effect size.

**Litmus comparison.** `ABHook` against static 30 bps is highlighted in the text
because `K/2 = 30` bps makes the two fee budgets identical by construction,
isolating allocation from level. It carries no statistical privilege.

**Commitment.** The result is published whichever way it comes out. At `n = 24`
per pair the design has modest power, so a null result is reported as "no
difference detected at this sample size", never as "no difference exists".

**Degeneracy note.** Net result against HODL improves monotonically toward zero
as the fee rises under arbitrage-only flow, because a pool nobody trades never
rebalances. The shared fee box bounds this and the static 100 bps configuration
sits at that edge by construction; retained volume is therefore reported beside
every figure so the effect is visible rather than hidden.

## 13. Fixes to Existing Hooks

Arithmetic is repaired and the code is brought into agreement with the paper's
text. Policy logic is not changed — otherwise this ceases to be an evaluation of
the existing framework.

| What                       | Where                                 | Why                                                                                        |
| -------------------------- | ------------------------------------- | ------------------------------------------------------------------------------------------ |
| Add `f_min`                | `BAHook`, `DAHook`, `ABHook`          | clamping to 0 violates `f_min ≤ f ≤ f_max` from Eq. (8)                                    |
| Remove truncation          | `ABHook:126`                          | `A·delta/10000` yields 0 for any √price move below 1%, so the hook sticks at `INITIAL_FEE` |
| Update in both directions  | `ABHook:124`                          | `if (isAToB)` — state never advances after B→A swaps                                       |
| Symmetrise                 | `PegStabilityHook:143`                | `zeroForOne \|\|` makes an entire direction permanently minimal                            |
| Unify the ratio convention | `BAHook:69` vs `PegStabilityHook:116` | `token0/token1` against `token1/token0`                                                    |
| Fix `setFee`               | `PegStabilityHook:81`                 | assigns `MAX_FEE_BPS` rather than the fee, and ignores `key`                               |

Each fix is a separate commit referencing either a line of the paper or a
reproducing test. The paper gains a paragraph on divergences from the original
artifact.

### 13.1 Fee-Unit Names That Lie — Documented, Deliberately Not Renamed

Added 2026-08-10. Fee units are the named hazard of this project (§4.5), and two
identifiers in the shipped hooks are wrong about them. **In both cases the
values are correct and every use is correct**; only the names and one comment
mislead. They are recorded here rather than repaired, because the artifact the
paper exports for readers is the shipped source and a reader will read the name
before the value.

| Where                        | Text                                                            | The truth                                                                                    |
| ---------------------------- | --------------------------------------------------------------- | -------------------------------------------------------------------------------------------- |
| `PegStabilityHook.sol:72-73` | `uint24 public MAX_FEE_BPS = 10000;` / `MIN_FEE_BPS = 100;`      | These hold **pips**, not bps: 10000 pips = 100 bps = §4.5's ceiling, 100 pips = 1 bp = its floor |
| `DAHook.sol:24`              | `uint24 private FSTEP = 100; // 5 bps, 0.01%`                    | 100 pips is **1 bp**. The "5 bps" is wrong and has been since 2026-08-03. `BAHook.sol:35`'s `FSTEP = 500; // 5 bps` is correct |

- **The `_BPS` names are not renamed** because they are `public`, so renaming
  them changes the ABI, and the run manifest and the bound tests read them from
  outside. The percent comments beside them (`1%`, `0.01%`) are correct and are
  the reliable reading. The hazard is sharpened by the fact that in this same
  repository `MEVChargeHook.config.feeMax` genuinely **is** in bps: two fields
  whose names differ by one word and whose units differ by 100×.
- **`DAHook.FSTEP`'s comment** costs nothing numerically — the constant is used
  as pips throughout — but it is a fee-unit comment in exported source, and it
  is the third occurrence of this class of error in the project (the first being
  Fig. 5's axis, §15). Correcting the comment is safe whenever the matrix is not
  running; it is left alone for now because no source file may be touched while
  a run is in flight.

## 14. Verification

### 14.1 Balance Closure — the Primary Invariant

```
LP loss  =  arbitrageur profit net of gas  +  gas
```

$$\underbrace{IL - R_f}_{\text{LP loss}} \;=\; \underbrace{\Pi_{\text{arb}}^{\text{net}}}_{\text{kept by the arbitrageur}} \;+\; \underbrace{G}_{\text{burnt}}$$

Read it as a closed system from which gas leaves. Writing
$\Delta_{\text{LP}} = R_f - IL$ for the LP's change in value and
$\Delta_{\text{arb}} = \Pi_{\text{arb}}^{\text{net}}$ for the arbitrageur's
profit **after** paying gas,

$$\Delta_{\text{LP}} + \Delta_{\text{arb}} + G = 0
\qquad\Longrightarrow\qquad
IL - R_f = \Pi_{\text{arb}}^{\text{net}} + G$$

The LP's fee income $R_f$ appears once, on the left, inside the definition of LP
loss. It is not subtracted again on the right.

> **Corrected 2026-08-10 (D7).** The identity previously printed was
> `IL − R_f = (Π_arb + G) − R_f`, with the prose "LP loss = arbitrageur profit +
> gas − LP fees". That bracketed form cancels `R_f` on both sides and reduces to
> `IL = Π_arb + G`, so the prose's "− LP fees" did nothing, and neither reading
> holds under either sign convention used elsewhere in this document: with
> `Π_arb` net of the fee (the §A.4 convention, where the fee is inside `Π*` via
> γ) the identity is off by `G`; with `Π_arb` gross of fee and gas (the old §4.2
> convention) it is off by `R_f`. The implementation was never wrong —
> conservation closes at 1e-16 — so no number moves. This section says "This is
> the only substantive invariant" and is the equation most likely to be typeset
> into the methodology as-is, which is why it is corrected in place rather than
> annotated.

If it closes to within rounding, the metrics are right. If it does not, there is
an error. This catches a mixed-up numeraire, a dropped factor, a wrong-sided
delta. The absence of such a check is what allowed the current code to print
`Final Total USD: 1` unnoticed.

### 14.2 Per-Policy Unit Tests

Fee direction, bound compliance, update granularity (for `BAHook`, at most once
per block — checked with two swaps in one block), and edge values. For
`VolatilityHook`, additionally, agreement of the variance with the reference.

### 14.3 Differential Check

Fixes change behaviour only where intended. For `f_min`: with fees above the
bound, results must match the original version bit for bit.

### 14.4 Golden Test

A short trace with pinned expected output.

## 15. Implications for the Paper

- Line 135, "Anvil provides the local EVM" — incorrect as applied to the replay;
  `Simulation.t.sol` is a Forge test and never touches Anvil. Replace with
  Foundry's EVM.
- Lines 56 and 212, the EMA/Welford claim, becomes true once `VolatilityHook`
  lands.
- Fig. 5 and its caption (line 297): the axis is labelled "basis points" with
  values of 3000–3200, whereas Uniswap v4's `uint24` counts hundredths of a bp
  (3000 = 30 bps). Either relabel or divide by 100.
- §IV-B (line 301): the list of what is missing shrinks — baseline, repeated
  windows, intervals, and gas all arrive.
- The project README promises "savings of $1,000 to $10,000 per month", a claim
  the paper explicitly declines to make. Bring into agreement.

## 16. Risks

- **The stable pair may produce no flow.** USDC/USDT held tight through 2024, so
  after gas there may be almost no arbitrage opportunities. It is run on the
  same terms as every other pair regardless: an empty result is itself a
  reportable finding about where dynamic fees are and are not applicable, and it
  will be plainly visible in the retained-volume column.
- **The second feed of the stable pair is a constant 1.** Formally this is not a
  market observation and requires a caveat.
- **`MEVChargeHook` operates outside its intended setting.** An arbitrage-only
  trace contains neither sandwiches nor JIT liquidity, so two of its three
  mechanisms never activate. Its result is interpretable only as behaviour under
  regular flow.
- **Optimal trade sizing assumes unconstrained capital** and immediate execution
  without competition. This is an upper bound on arbitrage pressure.

## 17. Decisions Taken

All items previously open were resolved on 2026-08-02, before implementation
began:

- Negative results are published as findings (§12.1).
- No new policy is invented; a policy is built only where the paper already
  claims it. This is why `VolatilityHook` is in scope and an oracle-informed
  constant-sum hook is not.
- `PegStabilityHook` ships in both readings (§5).
- The analysis plan is pre-registered as a family with FDR control, not as a
  single hypothesis (§12.1).

---

## Appendix A. Optimal Arbitrage Trade Size

This is the only substantive formula in the methodology, so it is derived here
in full rather than left implicit in `ArbMath.sol`.

### A.1 Setup

A constant-product pool holds reserves $x$ of token0 and $y$ of token1 under
$x \cdot y = k$. The pool price of token0 denominated in token1 is $p = y/x$,
and the external price in the same units is $P$. The fee $f$ is taken from the
input, so only $\gamma \Delta x$ reaches the invariant, where $\gamma = 1 - f$.

Throughout §A.2–§A.7 the fee is treated as a constant with respect to trade
size. §A.8 establishes when that is justified and what to do when it is not.

### A.2 Derivation, Selling token0

The output for an input $\Delta x$ is

$$\Delta y \;=\; y - \frac{k}{x + \gamma \Delta x} \;=\; \frac{y\,\gamma\,\Delta x}{x + \gamma \Delta x}$$

The arbitrageur surrenders $\Delta x$ of token0, worth $P \Delta x$ externally,
and receives $\Delta y$. Profit denominated in token1:

$$\Pi(\Delta x) \;=\; \frac{y\,\gamma\,\Delta x}{x + \gamma \Delta x} \;-\; P\,\Delta x$$

Setting the derivative to zero,

$$\frac{d\Pi}{d\Delta x} \;=\; \frac{\gamma\,x\,y}{(x + \gamma \Delta x)^2} - P \;=\; 0$$

gives

$$(x + \gamma \Delta x)^2 = \frac{\gamma\,x\,y}{P}
\qquad\Longrightarrow\qquad
\Delta x^{*} = \frac{1}{\gamma}\left(\sqrt{\frac{\gamma\,x\,y}{P}} - x\right)$$

which is positive if and only if $\gamma y / x > P$, that is $p > P/\gamma$.

### A.3 The Target Price

Substituting $\Delta x^{*}$ back, the post-trade reserves are
$x' = \sqrt{\gamma x y / P}$ and $y' = k / x'$, so

$$p' \;=\; \frac{y'}{x'} \;=\; \frac{x y}{x'^2} \;=\; \frac{x y}{\gamma x y / P} \;=\; \frac{P}{\gamma}$$

The pool lands **exactly** at $P/\gamma$. Buying token0 is the mirror image: it
pays only when $p < P\gamma$, and the pool lands exactly at $P\gamma$. The
no-arbitrage band is therefore

$$\left[\, P\gamma,\; \frac{P}{\gamma} \,\right]$$

Inside the band there is no trade; outside it the optimal trade moves the pool
precisely to the near edge. **The optimisation collapses to a single target
price**, so no numerical search is required.

### A.4 Closed-Form Profit

Substituting $\Delta x^{*}$ into $\Pi$ and simplifying:

$$\Pi^{*}_{0\to1} = \left(\sqrt{y} - \sqrt{\frac{P x}{\gamma}}\right)^{2}
\qquad
\Pi^{*}_{1\to0} = \left(\sqrt{P x} - \sqrt{\frac{y}{\gamma}}\right)^{2}$$

Sanity check at $\gamma = 1$: $\Pi^{*} = (\sqrt{y} - \sqrt{Px})^{2}$, which is
zero exactly at $p = P$.

Numerical check with $x = y = 1$, $P = 0.81$, $\gamma = 1$: the formula gives
$(1 - 0.9)^2 = 0.01$. Direct computation gives
$\Delta x^{*} = \sqrt{1/0.81} - 1 = 0.1111$, $\Delta y = 1 - 1/1.1111 = 0.1$,
and $\Pi = 0.1 - 0.81 \cdot 0.1111 = 0.01$. They agree.

Execution requires $\Pi^{*} > \text{gas cost}$ expressed in the numeraire.

### A.5 In Uniswap Coordinates

For a full-range position the virtual reserves follow from liquidity $L$ and the
square-root price $s = \sqrt{p}$:

$$x = \frac{L}{s}, \qquad y = L\,s, \qquad x y = L^{2}$$

**Selling token0** ($s > t$), with target square-root price
$t = \sqrt{P/\gamma}$:

$$\gamma\,\Delta x^{*} \;=\; L\left(\frac{1}{t} - \frac{1}{s}\right)
\qquad\qquad
\Pi^{*}_{0\to1} \;=\; \frac{L\,(s - t)^{2}}{s}$$

**Buying token0** ($s < t$) is _not_ the mirror image. Its target is
$t = \sqrt{P\gamma}$ and §A.4's $\Pi^{*}_{1\to0} = (\sqrt{Px} - \sqrt{y/\gamma})^{2}$
maps, in the same coordinates, to

$$\Pi^{*}_{1\to0} \;=\; \frac{L\,(t - s)^{2}}{\gamma\,s}$$

— larger by $1/\gamma$. The fee is paid in token1, which is the token the profit
is denominated in, so nothing cancels; on the sell side the fee is paid in
token0 and the grossing-up cancels against that input's external valuation.
**Both branches are needed. One formula does not cover both.**

The quantity $L(1/t - 1/s)$ is exactly `getAmount0Delta(t, s, L)`, Uniswap's
standard amount for moving between two square-root prices. The whole computation
therefore reduces to:

1. read the current $s$ from `slot0`;
2. compute $t = \sqrt{P/\gamma}$ when selling token0, $t = \sqrt{P\gamma}$ when
   buying it;
3. take the standard `getAmount0Delta(t, s, L)` (resp. `getAmount1Delta`);
4. gross up by $1/\gamma$, because v4 deducts the fee from the input before the
   swap math;
5. apply the branch's own profit formula — the extra $1/\gamma$ on the buy side
   is **not** optional.

No bespoke swap arithmetic is needed. This is what `ArbMath.targetSqrtPriceX96`
and `ArbMath.grossInput` implement.

> **Corrected 2026-08-10 (D9).** This section previously gave one formula,
> $\Pi^{*} = L(s-t)^{2}/s$, and concluded "the whole computation therefore
> reduces to…" as though it covered both directions. It is the token0-**sell**
> branch only. The omission produced a real bug: the 2026-08-03 audit found
> `ArbMath.profit` applying the sell-side form to both directions, which
> understated buy-side profit by exactly γ and suppressed 23 of 80,243 buys
> whose true profit fell in `[gas, gas/γ]`. The code has been correct since —
> `contracts/src/libraries/ArbMath.sol:96` applies
> `ONE_PIPS/(ONE_PIPS − feePips)` on the buy branch, with the asymmetry
> documented in its NatSpec — but this document did not, and it is the single
> most copy-pasted formula in it.

### A.6 Why a Dynamic Fee Changes Nothing Structurally

Uniswap v4 invokes `beforeSwap` **once per swap**, and the returned fee applies
to that swap in its entirety — there is no intra-swap fee schedule. The
derivation above therefore holds verbatim for a dynamic policy, provided the fee
does not itself depend on the trade size (§A.8). The only difference from a
fixed-fee pool is that $f$ must be read from the hook rather than from the pool
configuration: one call to `getFee` before computing $t$.

### A.7 Consequences

**Directional fees make the band asymmetric.** With
$f_{0\to1} \neq f_{1\to0}$ the band is

$$\left[\, P\,(1 - f_{1\to0}),\; \frac{P}{1 - f_{0\to1}} \,\right]$$

and the two edges move independently. This is precisely the mechanism by which
`ABHook` can win: under the constant-sum constraint it cannot widen the band as a
whole, but it can shift it — widening the side it expects toxic flow from while
narrowing the other. If the forecast is right, arbitrage in the toxic direction
arrives less often and pays more, while the pool stays competitive in the benign
direction. Fees are therefore queried per direction and both edges computed
independently.

**No fixed-point problem arises from price dependence.** `PegStabilityHook`
derives its fee from the pool price, which the trade then moves. The circularity
is broken by the protocol, not by our model: `beforeSwap` evaluates the fee at
the pre-swap state and fixes it for the whole swap.

**Fragmentation is an accepted simplification.** When a fee depends on the pool
price, an arbitrageur has an incentive to split a trade — move the price
slightly, let the hook reprice downward, then take the remainder more cheaply.
Our arbitrageur is single-shot, one trade per candle. Results for price-dependent
policies (`PegStabilityHook`, and to a lesser degree `ABHook`) are therefore an
**upper bound** on their effectiveness; against a fragmenting arbitrageur they
would perform worse. Policies whose fee does not depend on the price within a
swap — `BAHook`, `DAHook`, `VolatilityHook` — are unaffected. This is the subject
of reference [28] in the paper's own bibliography (path-independent fee
structures under transaction fragmentation) and belongs both in the validity
section and in future work.

### A.8 When the Fee Depends on Trade Size

The differentiation in §A.2 treats $\gamma$ as a constant. That is an assumption
about the hook, not a property of Uniswap: `beforeSwap` receives `SwapParams`,
which carries `amountSpecified`, so a policy is free to make the fee a function
of the trade size. Where it does, $\gamma = \gamma(\Delta x)$ and

$$\frac{d\Pi}{d\Delta x}
= \frac{\partial \Pi}{\partial \Delta x}
+ \frac{\partial \Pi}{\partial \gamma}\cdot\frac{d\gamma}{d\Delta x}$$

The second term is dropped by §A.2, so the closed form is valid only when
$d\gamma/d\Delta x = 0$.

Auditing the policies for reads of `params.amountSpecified` inside the fee path:

| Policy             | Reads trade size | Closed form valid |
| ------------------ | ---------------- | ----------------- |
| `MyHook`           | no               | yes               |
| `BAHook`           | no               | yes               |
| `DAHook`           | no               | yes               |
| `ABHook`           | no               | yes               |
| `PegStabilityHook` | no               | yes               |
| `VolatilityHook`   | no, by design    | yes               |
| `MEVChargeHook`    | **yes**          | **no**            |

`MEVChargeHook._calculateImpactFee` computes
$\text{impactBps} = \Delta x \cdot 10^{4} / L$ and, once that exceeds 500,
raises the fee linearly in trade size up to `maliciousFeeMax`. The function is
piecewise:

$$f(\Delta x) = \begin{cases}
f_{\text{time}}, & \Delta x \le 0.05\,L \\[4pt]
f_{\text{static}} + (f_{\max}^{\text{mal}} - f_{\text{static}})\dfrac{\text{impactBps} - 500}{9500}, & \Delta x > 0.05\,L
\end{cases}$$

Below 5% of liquidity the fee is size-independent and the closed form remains
exact. Above it, the size must be found numerically.

**The applied fee is not that piecewise expression.** The branch above is
`_calculateImpactFee` read alone, and read alone it appears to jump
_downward_ at $\Delta x = 0.05L$ whenever $f_{\text{time}} > f_{\text{static}}$
— i.e. whenever the 15-second cooldown is active, which for a persistent address
is nearly always. What the pool charges is the call site
(`contracts/src/MEVChargeHook.sol:403-406`):

$$f(\Delta x) \;=\; \min\!\big(\,\max(f_{\text{impact}}(\Delta x),\; f_{\text{time}}),\; \text{cap}\,\big)$$

and $f_{\text{impact}}$ **starts at exactly $f_{\text{static}}$** at the trigger,
with $f_{\text{static}} \le f_{\text{time}}$ always ( `_calculateTimeFee`
returns $f_{\text{static}}$ or $f_{\text{static}}$ plus a non-negative ramp). So
the maximum is $f_{\text{time}}$ on both sides of the boundary: the applied fee
is **continuous, and non-decreasing in size** — constant at $f_{\text{time}}$,
then rising linearly once the impact term overtakes it, then flat at the cap.

**Treatment.** The harness uses the closed form as the default path and switches
to a ternary search maximising $\Pi(\Delta x)$ directly whenever a policy is
declared size-dependent. Three implementation constraints follow:

- **Unimodality is checked, not argued.**
  `contracts/test/SizeSearchUnimodal.t.sol` samples $\Pi$ on a 400-point grid
  over the real shape above — including the `max` and the cap, not a smooth
  stand-in — swept across the cooldown ramp at $f_{\text{time}} \in$ {3000,
  6000, 10000} pips, and asserts a single turning point. It passes. This is the
  evidence for the ternary search's validity; the previous sentence ("$\Pi$
  stays unimodal because an increasing $f(\Delta x)$ only makes it more
  concave") asserted the conclusion without showing it.
- The search range is $[0,\ \Delta x^{*}(f_{\min})]$. This requires that a
  larger fee reduce the optimal size, which holds **only while
  $\gamma p < 4P$**: differentiating $\Delta x^{*} = A\gamma^{-1/2} - x/\gamma$
  with $A = \sqrt{xy/P}$ gives $d\Delta x^{*}/d\gamma > 0 \iff x' < 2x \iff
  \gamma y/x < 4P$. That is a deviation of the pool from the external price by a
  factor of four; it is satisfied by every deviation observed in this
  experiment, but it is a condition, not a fact.
- `MEVChargeHook._getFee` **writes state** (`_lastBuyToken0/1[payer]`), so
  probing it repeatedly would corrupt the very history the fee depends on. Each
  probe must therefore be wrapped in `vm.snapshotState()` / `vm.revertToState()`.

**One residual discontinuity, and why it is not load-bearing.**
`_computeDynamicFee` returns a zero surcharge when the truncated
$\text{impactBps} = \Delta x \cdot 10^{4}/L$ evaluates to 0, i.e. for
$\Delta x < 10^{-4}L$. Crossing that threshold steps the fee _up_ from
$f_{\text{static}}$ to $f_{\text{time}}$, which is a downward step in $\Pi$ and
therefore a genuine local maximum at $\Delta x \approx 10^{-4}L$. It cannot be
the search's answer in this experiment: a trade of $10^{-4}L$ on a 20M basket
earns profit orders of magnitude below the gas floor at every gas scenario, so
the bracketing never encloses it as an optimum that clears entry. It is recorded
here so nobody rediscovers it as a defect — and it should be re-checked if the
basket or the gas axis ever moves.

> **Corrected 2026-08-10 (D10).** The 2026-08-10 specification review concluded
> that the applied fee jumps downward at the 500 bps trigger, that this creates
> a second local maximum, and that arbitrage pressure against `MEVChargeHook`
> may therefore be understated. **That conclusion is wrong**, for the reason set
> out above: the review read `_calculateImpactFee` without its call site, and
> the `max(impactFee, timeFee)` there removes the jump. Verified numerically and
> now exercised by `SizeSearchUnimodal.t.sol` across the cooldown ramp. The
> review's _premise_ was right and is what this section had wrong — the
> unimodality claim was asserted rather than shown, and the search-range claim
> was stated as a fact when it is a condition. Both are now stated properly.

Size dependence is declared per policy in the run configuration rather than
detected at runtime, so the fast path stays the default and the choice is
recorded in the manifest.
$$
