# Dynamic-Fee Hook Framework: Full Project Report

Written 2026-08-12 for collaborators. This is the complete, self-contained
description of what this repository builds, simulates, measures, and can
honestly claim. It assumes no prior contact with the codebase. A glossary at the
end defines every symbol and term of art.

**Status at the time of writing.** The harness was revised on 2026-08-12
([§11](#11-revision-note-2026-08-12)) and every result below comes from matrices
re-run on it the same day: 9 policy configurations (the four hooks the paper
keeps — ABHook, BAHook, DAHook, MEVChargeHook — four static baselines, and a
recalibrated VolatilityHook) × 3 pairs × 72 windows × 3 gas scenarios = 5,832
cells per operating point, 0 errors, worst conservation error ~5·10⁻¹⁶.
[§10](#10-main-results--corrected-matrix-of-2026-08-12) reports the corrected
runs. The headline: **no dynamic policy beats a well-chosen static fee
unconditionally, but a real conditional advantage exists in the high-volatility
× cheap-gas corner** — carried by different policies at different flow mixes —
and is consumed by the policies' own gas premium as gas rises.

---

## 1. What the contribution is

The main contribution is **not** a set of fee-setting contracts, and it is
**not** a claim that dynamic fees are better. It is a **configurable framework
for creating, deploying, testing, and experimentally evaluating dynamic-fee
hooks for Uniswap v4**:

- a contract layer of hook templates with a shared interface and fee box;
- a deterministic replay harness that runs any such hook against real historical
  market data with modelled trader behaviour;
- an experiment layer that turns replays into a factorial experiment with
  pre-registered hypotheses, paired statistics, and reproducibility manifests;
- an analysis layer that computes LP economics from raw event logs and controls
  the false discovery rate across every claim.

The economic performance of dynamic fees is the framework's flagship
_application_: controlled comparisons of adaptive policies against static fee
baselines under identical conditions. Those comparisons are a secondary
contribution, and they are deliberately conditional — the honest headline
([§10](#10-main-results--corrected-matrix-of-2026-08-12)) is that the value of a
dynamic fee depends on the composition of order flow, not that dynamic fees win.

---

## 2. Architecture

Four layers, all present in the repository:

| layer      | where                                                          | role                                           |
| ---------- | -------------------------------------------------------------- | ---------------------------------------------- |
| Contracts  | `contracts/src/`                                               | hook policies + shared math libraries          |
| Harness    | `contracts/test/Replay.t.sol`                                  | deterministic replay of one window vs one hook |
| Experiment | `experiments/` (Python)                                        | matrix runner, trace generation, manifests     |
| Analysis   | `analysis/*.ipynb`, `experiments/{metrics,stats,aggregate}.py` | metrics, tests, figures                        |

### 2.1 Contract layer

Hooks are built on OpenZeppelin's `uniswap-hooks` base contracts
(`BaseOverrideFee`): the hook returns a fee per swap through `_getFee`, and
updates its state in `_afterSwap`/`_afterInitialize`. External signals come from
Chainlink-compatible feed interfaces; in experiments those are mock feeds
replaying historical data. Two pure libraries carry the model math:

- `ArbMath.sol` — no-arbitrage band, optimal-trade targets, closed-form
  arbitrage profit (verified against an independent derivation,
  [§4.1](#41-the-arbitrageur));
- `UUMath.sol` — the retail participation model: normalised disadvantage `r` and
  execution probability `P` ([§4.2](#42-uninformed-users-retail)).

All policies share a **fee box of [1, 100] bps** (fees are `uint24` in _pips_ =
hundredths of a basis point; 30 bps = 3000 pips).

### 2.2 Replay harness

`Replay.t.sol` is a Forge test that replays one **window** (one day, 1,440
one-minute candles) of real market data against one policy configuration. Per
candle it: updates the mock price feeds and clock (60 s, 5 blocks), runs retail
flow in both directions, then gives one arbitrageur a single chance to trade.
Every executed swap is appended to a JSONL event log; the harness **derives no
metrics** — everything downstream is computed in Python from the log, so the
accounting can be independently re-derived.

Three properties the harness enforces:

1. the pool opens at the external market price, not 1:1;
2. the arbitrageur weighs profit against gas, so gas scenarios matter;
3. all swap amounts come from Uniswap's own `SqrtPriceMath`, so rounding matches
   the pool bit-for-bit.

**Gas is measured, not assumed — and Forge is what makes that possible.**
Because every swap executes in a real EVM, the harness meters the actual gas of
each executed swap, and a calibration run measures every policy's median cost
(execution + the 21k intrinsic transaction cost) by running the real contract.
Those measured medians are what the model then feeds back into the economics:
the arbitrageur's entry threshold ($\Pi^* > g \cdot p_{\text{gas}}$) and the
retail participation decision ($G$ inside $r$) both price the specific policy's
real gas, so an oracle-reading hook is automatically more expensive to trade
against than a constant-fee one — by its measured margin, not by a guess. This
is a capability a purely numerical simulator does not have, and the
[§10](#10-main-results--corrected-matrix-of-2026-08-12) gas gradient rests on
it. `paper/Image/uu_gas_cost_per_swap.pdf` shows the measured costs in dollars:
at congested gas (80 gwei) even the static hook's \$19 per swap is ~47 bps of a
typical \$4,000 retail trade, and the heaviest adaptive hook's \$30 is ~75 bps —
rivalling the fee box itself.

### 2.3 Reproducibility: the run identity

A run is identified by
$E = \langle C_{\theta},\, D,\, P_0,\, L_0,\, W,\, S \rangle$ — configured
contract, dependency/compiler revisions, initial price, initial liquidity,
market-data window, and swap-generation config (including the RNG seed). Each
cell writes a **manifest** recording all six; a re-run skips cells whose
manifest matches (hash of `contracts/src/` **and** `contracts/test/`, plus a
fingerprint of the window's own candles). Changing one line of the harness
invalidates and re-runs every cell, which is exactly what happened on
2026-08-12.

---

## 3. The simulated world

One Uniswap v4 pool, one pair, one day at a time.

- **Liquidity**: a basket worth 20,000,000 USDT, split 50/50 by value, minted
  once into a full-range position before trading starts. No LP enters, leaves,
  or rebalances mid-window.
- **Opening price**: the external market price of the first candle.
- **Clock**: 1,440 one-minute candles per window; each advances 60 s and 5
  blocks.
- **Warm-up**: the first 60 candles execute but are not measured; all metrics
  are differences against the state at the warm-up boundary.
- **Pairs**: ETH/SHIB and ETH/USDC (volatile), USDC/USDT (stable). The stable
  pair's second leg has no market series and is pinned at 1.0 — a synthetic
  feed, flagged as such.
- **External price**: a mock Chainlink feed updated to each candle's real close.
  The pool never infers the external price and the feed never reads the pool —
  configured constants, reference-market inputs, and endogenous pool outputs are
  three distinct kinds of value, kept separate by rule.

---

## 4. The mathematical model

Two kinds of trader, modelled asymmetrically on purpose. This is the standard
microstructure framing (Glosten–Milgrom, Kyle): what disciplines a fee is the
ratio of informed to uninformed flow.

|                | arbitrageur (informed)                | uninformed users (retail)                 |
| -------------- | ------------------------------------- | ----------------------------------------- |
| why they trade | the pool disagrees with the market    | they want the other token                 |
| volume         | endogenous: from volatility, fee, gas | exogenous scale, endogenous participation |
| direction      | whichever way profits                 | both, independently                       |
| toxic to LP?   | yes, by construction                  | only via the price impact it leaves       |

### 4.1 The arbitrageur

Once per candle, after retail, the arbitrageur asks: is the pool far enough from
the external price $P$ to profit after the fee and after gas? With fee fraction
$f$ and $\gamma = 1 - f$, the pool price may sit anywhere inside the
**no-arbitrage band**

$$\left[\, P\gamma,\; \frac{P}{\gamma} \,\right]$$

without a trade. In sqrt-price terms ($s$ the pool's $\sqrt{\text{price}}$), the
targets are

$$
t_{0\to1} = \sqrt{\frac{P}{\gamma}} \quad (\text{trade if } s > t)
\qquad\qquad
t_{1\to0} = \sqrt{P\gamma} \quad (\text{trade if } s < t)
$$

Outside the band, the optimal trade pushes the pool exactly to the band edge $t$
— not to $P$; the gap that remains is the fee doing its job — with closed-form
profit for liquidity $L$:

$$
\Pi^{*}_{0\to1} = \frac{L\,(s - t)^{2}}{s}
\qquad\qquad
\Pi^{*}_{1\to0} = \frac{L\,(t - s)^{2}}{\gamma\, s}
$$

The buy side is larger by $1/\gamma$ because the fee is paid in the currency the
profit is denominated in, so nothing cancels. The trade executes only if

$$\Pi^{*} > g \cdot p_{\text{gas}}$$

where $g$ is the **measured median gas per swap for that policy** (an
oracle-reading hook costs ~2× a constant-fee one — that difference is part of
what the gas axis measures) and $p_{\text{gas}}$ is the scenario's gas price,
valued at the ETH price series.

For size-dependent policies (MEVChargeHook), the closed form does not apply; the
optimal size is found by a 24-iteration ternary search, valid because profit is
unimodal in size (tested against the real fee shape).

Both formulas were re-derived independently during the 2026-08-12 audit and
match the implementation.

**$\Pi^*$ is a decision quantity, not an accounting one — it appears in no
metric.** It answers, before the trade, whether to trade and at what size; the
metrics of [§9](#9-metrics) are then computed exclusively from the balance
changes of swaps that actually executed, with the pool's real rounding and fees.
$\Pi^*$ influences results only by deciding which trades exist. (Each arbitrage
swap's trace does log its $\Pi^*$ as `expectedProfit`, so decision and
realisation can be compared as a diagnostic — but nothing downstream computes
with it.)

### 4.2 Uninformed users (retail)

Retail demand is exogenous _by definition_ — someone swapping ETH for USDC wants
USDC for reasons outside the pool. What is endogenous is whether they go through
with it at the price the pool offers. The model, taken from the group's earlier
work:

$$ r = \frac{V_{\text{out}} - V_{\text{in}} - G}{V_{\text{out}} + V_{\text{in}} + G}
\qquad\qquad
P_{\text{exec}} = \begin{cases}
1, & r \ge 0\\[2pt]
e^{-\lambda |r|}, & r < 0
\end{cases}$$

where $V_{\text{in}}$ is the value the user hands over, $V_{\text{out}}$
the value the pool's curve actually pays (both at external prices), and
$G$ the trade's own gas. $r$ is the **normalised disadvantage** of the
trade; $P_{\text{exec}}$ is the probability the user trades anyway
rather than walking away. (The subscript keeps it apart from the
external price $P$ of [§4.1](#41-the-arbitrageur).)

Three properties worth spelling out:

1. **$r$ is normalised**: losing a fraction $\varepsilon$ of value gives

   $$r = -\frac{\varepsilon}{2 - \varepsilon} \approx -\frac{\varepsilon}{2}$$

   — about _half_ the fractional loss.
2. **Slippage is inside $r$** by construction: $V_{\text{out}}$ is what
   the curve pays at the actual trade size (measured contribution:
   1.18 bps median, 7.21 bps p99).
3. **Gas is inside $r$**: for a small trade the gas bill can exceed the
   fee, so gas materially thins retail participation — that is what makes
   the gas axis of the experiment economically live.

$r \ge 0$ happens and matters: a user trading _toward_ the external price
can receive more value than they give, and then trades regardless of the
fee.

### 4.3 λ — the psychology scale

Raw $e^{-|r|}$ at basis-point scale is numerically flat
($P_{\text{exec}}$ between 0.995 and 0.99995 across the whole fee box), which would silently make every fee
equally acceptable. $\lambda$ makes the assumed price sensitivity
explicit:

$$\lambda = \frac{\ln 2}{|r(0.003)|} = \frac{\ln 2}{0.001502253} = 461.404973$$

The number is not arbitrary — it is pinned by one check the reader can
do in a head: a 30 bps total cost gives $r \approx -0.0015$, and
$e^{-461.4 \times 0.0015} = e^{-\ln 2} = \tfrac{1}{2}$ — exactly half
the willing flow walks away.

Read it as one sentence: **half of the willing retail flow walks away when
the total cost of trading reaches 30 bps** — total meaning fee + slippage
+ gas + signed pool deviation, everything $r$ contains. $\lambda$ is an
assumption (a calibration statement, not a measurement) and is swept in
sensitivity analysis.

### 4.4 κ — the retail scale

The model needs to know how much retail demand shows up at the pool's
door. That splits into two questions with two very different answers:

1. **When during the day does retail trade?** This is _measured_. Real
   Binance per-minute volumes over 2024 give each minute of the day an
   activity weight — the Asia/Europe/US sessions, the quiet nights, the
   bursts around news. Call that shape $V_{\text{profile}}(c)$ for
   minute $c$ (it is the geometric mean of the pair's two legs' quote
   volumes; see the glossary).
2. **How much of it, in total?** This _cannot be measured_ from
   anywhere inside the model — how many people want to swap ETH for
   USDC today is a fact about the outside world. So it is a single
   assumed number: $\kappa$.

Normalise the measured shape so it sums to one over an average day,
$\hat{s}(c) = V_{\text{profile}}(c) \,/\, \overline{\sum_{\text{day}}
V_{\text{profile}}}$, and the potential retail demand of minute $c$ is

$$v_{0}(c) = \kappa \,\cdot\, \text{basket} \,\cdot\, \hat{s}(c),
\qquad \text{basket} = 20\text{M USDT}$$

so $\kappa$ is **dimensionless and directly readable: the pool's daily
turnover in baskets per day** — daily potential demand divided by pool
size. $\kappa = 1$: an average day wants to push one pool's worth (20M
USDT, ≈ 13.9k per average minute) through the pool. $\kappa = 0.1$: a
tenth of that. Every "κ = …" label in this document is this number.

_(Implementation note: the code groups the same product differently:
$v_0(c) = (\kappa \cdot n_p) \cdot V_{\text{profile}}(c)$, where
$n_p = \text{basket} \,/\, \overline{\sum_{\text{day}} V_{\text{profile}}}$
is a per-pair normalisation constant ($n_p \approx 0.0552$ for
ETH/SHIB). Substituting $n_p$ shows the two forms are identical:
$n_p \cdot V_{\text{profile}}(c) = \text{basket} \cdot \hat{s}(c)$.
$n_p$ is pure bookkeeping with no independent meaning; the $\kappa$ of
this document is the dimensionless factor beside it. In the code the two
are `kappa_for_pair` and `uu_turnover`.)_

The measured shape itself is drawn in
`paper/Image/uu_volume_profile.pdf` — the quiet Asian night, the
European ramp, the US-session hump between 13:00 and 16:00 UTC, shared
by all three pairs — with the assumed flat κ = 1 mean as a dashed
reference. One glance separates what the data supplies (the curve) from
what the model assumes (the height of the dashed line).

"Potential" matters: this is how much _wants_ to trade; how much
actually trades is decided per minute by the participation model of
[§4.2](#42-uninformed-users-retail), which is exactly where the fee
policy earns or loses its keep.

Why this is **the weakest number in the model**: the calibration rule
("turnover 1×/day") was chosen for being simple and stated, not
measured against real pools. And $\kappa$ silently controls the thing
the whole experiment is about — the **informed share**. Less retail
does not reduce arbitrage; arbitrage is driven by price moves, which
don't care about $\kappa$. So turning $\kappa$ down drains the benign
flow while the toxic flow stays, and the pool's flow mix shifts from
~13% arbitrage at $\kappa = 1$ to ~58% at $\kappa = 0.1$ and ~80% at
$\kappa = 0.03$. A fee policy that looks good at one mix can look bad
at another — which is why no single-$\kappa$ result is trusted:

- **The κ sweep**: the experiment is repeated at
  $\kappa \times \{0.03, 0.1, 0.3, 1.0, 3.0\}$. It answers: _is the
  ranking of policies a property of the policies, or of the retail
  scale we happened to assume?_
- **Full operating points**: the levels of most interest —
  $\kappa = 1.0$ (the calibrated, retail-dominated headline) and
  $\kappa = 0.1$ (the informed-heavy point, arbitrage ≈ half the
  volume) — are run as complete matrices and reported side by side;
  neither replaces the other, and their statistics are never pooled.

#### The operating points, in human terms

$\kappa$ reads as **how much organic daily demand the pool attracts, in
units of its own TVL** (the basket is 20M USDT). Each level of the sweep
is a recognisable kind of pool, and the arbitrage share it produces is
the fingerprint:

| $\kappa$ | organic demand/day | the pool it describes                                                         | arb share (measured) |
| -------- | ------------------ | ----------------------------------------------------------------------------- | -------------------- |
| 3.0      | 60M (300% of TVL)  | a flagship pool of the primary venue in a hot market — retail floods it        | ~10–20%              |
| **1.0**  | 20M (100% of TVL)  | **an active primary-venue pool**: aggregators route here, organic flow strong  | **12–15%**           |
| 0.3      | 6M (30% of TVL)    | a mid-tier pool whose TVL is somewhat oversized for its user base              | ~30%                 |
| **0.1**  | 2M (10% of TVL)    | **a pool that is _not_ the primary venue**                                     | **58%**              |
| 0.03     | 0.6M (3% of TVL)   | an over-provisioned pool with almost no users of its own                       | ~80%                 |

$\kappa = 0.1$ deserves the explicit reading, because it is not an
exotic stress test. Two million USDT of daily potential demand against a
20M pool means retail trades of a few hundred dollars landing a few
times a minute — a quiet but alive pool — while the price is discovered
elsewhere and arbitrageurs carry it in. That is the everyday condition
of a **secondary venue**: an L2 or fork deployment of a pair whose main
volume lives on mainnet or a CEX, a long-tail pair with more LPs than
traders, any pool whose TVL outgrew its organic flow. Empirical
estimates of the informed share for non-primary pools in the LVR /
toxic-flow literature routinely land in the 40–70% range — so the
informed-heavy point is arguably closer to the _median_ DEX pool than
the calibrated one, which describes the rarer, higher-volume
primary-venue pools. The pair of operating points is therefore two real
kinds of pool, not a base case plus a fantasy — and the fact that the
winning policy differs between them ([§10](#10-main-results--corrected-matrix-of-2026-08-12)) reads as a practical
statement: _which fee policy to deploy depends on which kind of pool
you are._

### 4.5 How retail flow is drawn

Each minute, each direction independently draws one candidate trade of a
random size around its share of the minute's demand,

$$\text{size} = \frac{v_0}{2}\,e^{\sigma Z - \sigma^{2}/2},
\qquad Z \sim \mathcal{N}(0,1)$$

(mean-preserving: the average over draws is exactly $v_0/2$;
$\sigma = 1$ gives realistic heavy-tailed trade sizes), and the trade
executes **all-or-nothing** with the participation probability
$P_{\text{exec}}$ of
[§4.2](#42-uninformed-users-retail). Three things this buys:

- **the pool actually gets displaced** — on many minutes only one side
  shows up, so retail flow moves the price and the arbitrageur has work
  to do;
- **gas is expressible** — a trade of a definite size has a definite gas
  bill, which enters its owner's decision through $r$;
- **reproducible randomness** — all draws happen in Python at
  trace-generation time from a recorded seed, so a run is repeatable
  bit-for-bit, and a **seed appendix** (five seeds) checks which
  conclusions survive the particular draw.

**Why this construction.** It is the minimal one that satisfies five
requirements at once, each of which kills a simpler alternative:
smooth fluid flow self-cancels (both directions thin equally, the pool
never moves, and the arbitrageur starves — a failure mode an earlier
revision actually exhibited), so trades must be discrete; a continuum
of infinitesimal users pays no gas, so trades must have a size;
trade sizes in real markets are positive and heavy-tailed, which the
one-parameter lognormal is the simplest way to honour without
distorting the calibrated volume (the draw is mean-preserving); the
participation model of [§4.2](#42-uninformed-users-retail) is an
accept/reject decision — a person trades or walks — so execution is
all-or-nothing rather than "everyone trades a fraction
$P_{\text{exec}}$"; and
independence across directions is the definition of _uninformed_: no
directional information.

Known limit, declared: one draw per direction per minute is the
**lumpiest** reading of the measured volume — all of a minute's demand
arrives as a single trade. Real minutes contain many smaller trades
that partially cancel, so true order-flow imbalance lies below this
assumption; and genuinely correlated demand (news, momentum) is not
modelled at all. This is the one element chosen for simplicity rather
than forced by a requirement, and it is declared as such.

### 4.6 One candle, end to end

    1. update both price feeds and the gas price to this candle's values
    2. advance the clock 60 s / 5 blocks
    3. retail A→B: quote fee at the candle's potential volume → r →
       P_exec → draw, execute all-or-nothing
    4. retail B→A: the same
    5. arbitrageur: target, optimal size, profit; trade if profit > gas
    6. log every executed swap

Retail moves first and the arbitrageur cleans up — that ordering is what
couples the flows: retail displaces the pool, and the displacement is what
arbitrage harvests. The fee for the participation decision is quoted at
the candle's _potential_ volume (known before P), which keeps the
fee → P_exec → size → fee loop broken.

---

## 5. The fee policies

The paper keeps four hook policies; four static levels serve as baselines.

| policy         | rule                                                                                   |
| -------------- | -------------------------------------------------------------------------------------- |
| `MyHook@{500,3000,6000,10000}` | constant 5 / 30 / 60 / 100 bps — the baselines                        |
| `DAHook`       | per-trade directional ratchet: after each swap, +100 pips on the direction just traded, −100 on the other; no external data |
| `BAHook`       | block-level ratchet: ±500 pips per block on the side the external price ratio moved against, via two Chainlink feeds |
| `ABHook`       | constant-sum split: f_AB + f_BA = 6000 pips always, reallocated against the direction the **pool's own price** moved (no oracle; feeds accepted but unused); box [1, 59] bps |
| `MEVChargeHook`| base fee + a size-impact surcharge + a per-sender cooldown; the only size-dependent policy |

Dropped from the paper (still in the repo, with measured reasons):
`MEVChargeHookFixed` collapses to a constant 30 bps in practice;
`VolatilityHook` moves its fee over 0.35 bps — two orders of magnitude too
little to matter; `PegDefence`/`PegCapture` (peg-stability policies)
performed catastrophically in every configuration (up to −82% of the
baseline result).

Why these four are the interesting ones: DAHook and ABHook are the two
_endogenous_ directional designs (no oracle: last-trade direction and
the pool's own price change respectively), BAHook is the oracle-driven
directional design, and MEVChargeHook is the one policy whose fee
depends on trade size. Oracle readers (BAHook, VolatilityHook) pay for
it in gas: 108–124k per swap against 88–95k for the endogenous hooks.

---

## 6. Experimental design

### 6.1 The matrix

A full factorial over:

| axis     | levels                                        |
| -------- | --------------------------------------------- |
| policy   | 4 hooks + 4 statics (rerun; the original had 12) |
| pair     | ETH/SHIB, ETH/USDC, USDC/USDT                 |
| window   | 72 per pair: 24 per volatility tercile        |
| gas      | 5 / 20 / 80 gwei                              |

Windows are one-day slices of 2024, stratified by realised volatility into
terciles (calm / medium / stormy) so that regimes are represented by
design rather than by luck. 24 windows per tercile is what it takes for
the intervals below to be narrow enough to decide anything.

### 6.2 Pairing and statistics

The whole analysis is three steps:

1. **Pair.** Each policy's result on a window is differenced against the
   baseline's result on the _same_ day, same pair, same gas price.
   Day-to-day variation (a calm day vs a stormy one) dwarfs the policy
   effect; pairing removes the noise both arms share.
2. **Bootstrap.** For each group of paired differences, take the median
   and its 95% confidence interval by resampling (percentile bootstrap,
   10,000 resamples, seeded). Read it as: "the typical day's advantage
   is X, and the data is consistent with anything from a to b".
3. **Decide by the interval.** The interval excludes zero on both
   valuations → a win (or a loss). It covers zero → undecided. That is
   the only significance criterion this document uses, on every figure
   and in every table.

Two conservatisms, stated in plain terms:

- **Aggregation**: a headline number is built cell-first — one median
  per (pair × regime × gas) cell, then combined across cells — so three
  gas scenarios of the same day are never counted as three independent
  observations.
- **Baseline**: `MyHook@3000` (static 30 bps), named in advance. A
  _post-hoc_ comparison against the best static in the box (60 bps) is
  also reported, labelled as exploratory.

> Footnote for the statistically inclined: the pipeline also computes
> classical significance tests (Wilcoxon signed-rank per cell, with
> Benjamini–Hochberg multiple-comparison correction across the ~300
> comparisons); they are written into every analysis CSV and agree with
> the intervals in ~96% of comparisons. They are not used in this
> document's prose.

### 6.3 Pre-registration protocol

Every experiment writes its design, hypotheses, and verdict rules to a
dated spec in `docs/superpowers/specs/` **before the first cell runs**.
Specs that data already exists for are frozen; a flawed frozen spec is
not edited but superseded by a new one that discloses the flaw. Failed
predictions are reported as failures ([§10](#10-main-results--corrected-matrix-of-2026-08-12) has one). This protocol is the
reason the results can be trusted: no hypothesis, baseline, or verdict
rule was chosen after seeing the data.

### 6.4 Robustness appendices

- **κ sweep** ([§4.4](#44-κ--the-retail-scale)): does the ranking survive the assumed retail scale?
- **Seed appendix**: five seeds on reference cells; a sign that survives
  all five may be stated as a finding, a sign that flips may not. The
  spread travels with the verdict.
- **Second operating point** (κ = 0.1): the full matrix at an
  informed-heavy mix, its own family of comparisons, never pooled with the
  headline.

---

## 7. Every parameter, and where its value comes from

The most important table in this document. Nothing is fitted to an
outcome; the two constants that were chosen rather than measured are
exactly the ones that get swept.

| parameter               | value                              | status                     |
| ----------------------- | ---------------------------------- | -------------------------- |
| basket                  | 20,000,000 USDT                    | chosen, recorded           |
| window                  | 1 day = 1,440 one-minute candles   | chosen                     |
| warm-up                 | 60 candles                         | chosen                     |
| windows per tercile     | 24 (72 per pair)                   | chosen for power           |
| price series            | Binance 1-minute closes, 2024      | **measured**               |
| retail volume _shape_   | Binance quote volume, geo-mean of legs | **measured**           |
| retail volume _scale_ κ | turnover 1×/day                    | assumed, **swept**         |
| λ                       | 461.404973                         | assumed (calibration statement), **swept** |
| retail imbalance        | 1 trade/direction/candle (k = 1)   | assumed, upper bound, not swept |
| lognormal σ             | 1.0                                | chosen                     |
| gas per swap            | per-policy measured median (`experiments/gas_estimates.json`) | **measured** |
| gas scenarios           | 5 / 20 / 80 gwei                   | chosen to span the range   |
| policy constants        | per contract ([§5](#5-the-fee-policies))                  | as shipped                 |
| UU mode / seed          | `discrete`, seed 0 (+ 5-seed appendix) | chosen, **swept** (seeds) |

### What each value means in the real world

The same table, read as a description of a market rather than a config
file:

- **Basket = 20M USDT, split 50/50, full range.** A solid mid-size
  mainnet pool with a passive, v2-style LP position: minted once, never
  rebalanced. Not a top-3 flagship (those hold hundreds of millions) and
  not long-tail dust.
- **Window = 1 day of 1-minute candles; warm-up = 60 candles.** One
  trading day at the resolution real oracles and real candle feeds
  actually update; the first hour is excluded while the estimators fill
  and the pool settles from its opening state — the same reason a trader
  distrusts indicators in the first bars of a session.
- **24 windows per volatility tercile (72/pair).** Enough days of each
  weather — calm, ordinary, stormy — that a policy's win on one lucky
  Tuesday cannot pass for a result. The number is a power calculation,
  not taste: below ~24 the statistics cannot distinguish anything that
  survives multiple-comparison correction.
- **Price series = Binance 2024.** A year that contains a mania (the
  March meme rally), a crash (August 5), and months of boredom — the
  high-volatility tercile of ETH/SHIB spans 4.3–16% *daily* realised
  volatility, so "storm" means a real storm.
- **Retail volume shape (measured).** The intraday rhythm of real
  trading — Asia/Europe/US sessions, quiet nights — taken from Binance
  per-minute volumes, so the simulated day breathes like a real one.
  Only its **height** (κ) is assumed; see the operating-points table in
  [§4.4](#44-κ--the-retail-scale) for what each κ means.
- **λ = 461.4.** "Half of the willing flow walks away at a 30 bps total
  cost." On a \$1,000 swap, 30 bps is three dollars: the model says
  retail is sensitive enough that an extra \$3 of total friction turns
  half of them away. In a world of aggregators comparing venues
  automatically, that is conservative-to-realistic — and it is swept,
  because it is a psychology, not a measurement.
- **k = 1 (one trade per direction per candle).** All of a minute's
  demand arrives as one lump — the most order-flow-imbalanced reading of
  the measured volume. Real minutes contain many small trades that
  partially cancel; truth lies between this and perfectly smooth flow.
- **Gas per swap (measured medians — by Forge, in a real EVM, [§2.2](#22-replay-harness)).**
  The static hook costs 76k gas per swap; the oracle-reading hooks
  88–124k. In money, at 20 gwei and the mean 2024 ETH price (\$3,044):
  about **\$4.6 vs \$5.4–7.5 per swap** — drawn per policy and per gas
  scenario in `uu_gas_cost_per_swap.pdf`. An adaptive hook is a shop
  with higher rent — it must out-earn a static fee by at least its own
  overhead before it nets anything, and retail sees that overhead in the
  price ($r$) and walks. [§10](#10-main-results--corrected-matrix-of-2026-08-12)'s gas gradient is this line item becoming
  decisive.
- **Gas scenarios 5 / 20 / 80 gwei.** A quiet chain, an ordinary day,
  and congestion (an NFT mint, a liquidation cascade): for the static
  hook roughly **\$1 / \$4 / \$15** per swap. At 80 gwei a \$400 retail
  trade pays ~4% in gas alone — which is why the informed share rises
  with gas: small retail dies first, arbitrageurs (trading thousands)
  stay.
- **Fee box [1, 100] bps.** The span of Uniswap's own standard tiers
  (0.01% to 1%): the floor keeps the LP from ever working for free, the
  ceiling forbids the degenerate "charge so much nobody trades" corner,
  and every policy competes inside the same range — MEVCharge's
  pre-clamp "advantage" of charging above it was an artifact, not
  alpha.
- **Policy constants ([§5](#5-the-fee-policies)).** In market terms: `DAHook` nudges the fee by
  1 bp against the direction of each trade (a micro market-maker
  skewing quotes); `BAHook` moves 5 bps per block in the direction the
  CEX price ran (a dealer widening the side the market is leaving);
  `ABHook` keeps a fixed 60 bps two-way spread and only re-aims it;
  `VolatilityHook` charges 20 bps in calm weather up to 100 bps in a
  storm, tracking a per-minute volatility estimate; `MEVChargeHook`
  adds a size surcharge — big trades pay more per unit.
- **`discrete` mode, seed 0.** Retail arrives as actual lumpy trades,
  not as a smooth fluid — which is what lets "a user pays gas" mean
  anything. The seed is one realisation of that lumpiness; the seed
  appendix exists because one realisation is one draw, not a law.

---

## 8. Datasets

- **Binance 1-minute klines, calendar 2024**: ETHUSDT, SHIBUSDT, USDCUSDT
  close prices (1e8-scaled, the Chainlink convention) and quote volumes.
  ETHUSDT also serves as the gas-valuation series for every pair.
- **USDC/USDT's second leg** is a synthetic constant 1.0 (no market
  series exists for "USDT/USDT"); formally not a market observation.
- Windows are fingerprinted (hash of the window's own aligned candles) in
  the manifest, closing the reproducibility identity.

Replaying this data through mock feeds validates _integration_, not live
oracle behaviour: no aggregation, heartbeat, deviation threshold, or
latency is reproduced.

---

## 9. Metrics

All computed in Python from the JSONL logs (`experiments/metrics.py`).
The LP position is reconstructed **two independent ways** — from pool
state (position formula + `feeGrowthInside`) and from trader flow (initial
deposit minus what traders took) — and the two must agree; this
conservation check closes at ~1e-16 on every shipped run; a cell that
fails it is invalid by definition.

| metric                | meaning                                                        |
| --------------------- | -------------------------------------------------------------- |
| `fee_income`          | fees credited to the position, from the pool's own accounting  |
| `il`                  | impermanent loss vs holding                                    |
| `net_result`          | LP value − HODL value at **end-of-window** prices (primary)    |
| `net_result_tt`       | the same flows valued at **trade-time** prices (co-primary)    |
| `retained_volume`     | volume that actually traded, in USDT — what _remains_ of the potential demand after the policy's total cost (fee + slippage + gas) turned part of the retail away; retail and arbitrage together |
| `uu_volume` / `arb_volume` | the split by trader kind                                  |
| `uu_participation`    | retail retention rate: executed / potential volume, in USDT (unbiased Horvitz–Thompson estimator in discrete mode) |
| `uu_fee_share`        | share of fee income paid by retail                             |
| `arb_profit_realized` | arbitrage P&L net of gas at trade-time prices                  |

The two valuations are different functionals, not one quantity. With
$\Delta^{i}_{t}$ the LP's token-$i$ flow at trade $t$ and $P^{i}_{t}$ the
external price:

$$\text{net\_result} = P^{0}_{T}\sum_t \Delta^{0}_{t} \;+\;
P^{1}_{T}\sum_t \Delta^{1}_{t}
\qquad\qquad
\text{net\_result\_tt} = \sum_t \left( \Delta^{0}_{t}\,P^{0}_{t} +
\Delta^{1}_{t}\,P^{1}_{t} \right)$$

In words: $\Delta^{i}_{t}$ is how many tokens of kind $i$ the LP gained
or lost in trade $t$ (the mirror image of the trader's balance change —
`amountIn`, fee included, minus `amountOut`). `net_result` first sums
all flows of the window per token and marks the two totals at the
**final** prices; `net_result_tt` marks **each trade at the price of
its own moment** and sums. A toy example of the difference: the LP nets
1 ETH at noon at \$2,000 and the day closes at \$3,000 —
`net_result` says +\$3,000, `net_result_tt` says +\$2,000, and the
\$1,000 gap is not fee income but the received token appreciating while
it sat.

The first depends only on the **sum** of the flows (a terminal
mark-to-market against a holder; the valuation date $T$ is its free
parameter); the second is a **path integral** over them (realised
transfer P&L, no valuation date). They answer different pre-registered
questions — _did the LP end up richer than a holder?_ vs _did the LP make
money on the trades it did?_ — and their difference is the
inventory-revaluation term.

**Uniswap v4 fee mechanics are respected exactly.** In v4 a fee never
joins the pool's liquidity — it accrues to the LP position (through
`feeGrowthInside`) and does not compound. The accounting mirrors that:
`fee_income` is read from the pool's own `feeGrowthInside × L`, LP
value is principal **plus** accrued fees as two separate terms, and a
fee received in the morning sits in its own token until the end of the
window, valued like any other inventory. The conservation check above
is precisely the test of this bookkeeping — position-plus-fees (v4's
ledger) must equal deposit-minus-trader-flows (the $\Delta$ ledger),
and it closes at ~$10^{-16}$ on every cell. Disagreements between them (9 of 297
comparisons) are findings, not artifacts.

---

## 10. Main results — corrected matrix of 2026-08-12

Run of record: 9 policies × 3 pairs × 72 windows × 3 gas = 5,832 cells,
0 errors, worst conservation error $5.4 \cdot 10^{-16}$, `discrete` mode,
seed 0, calibrated $\kappa$. Arbitrage share of volume at the baseline:
15.4% (ETH/SHIB), 11.7% (ETH/USDC).

Headline estimand — median across the 18 volatile-pair strata of the
median paired difference vs static 30 bps, 95% bootstrap CI over strata:

| policy          | end-of-window valuation | trade-time valuation |
| --------------- | ----------------------- | -------------------- |
| `MyHook@6000`   | −2 [−186, +266]         | −14 [−95, +346]      |
| `BAHook`        | −100 [−453, +350]       | −39 [−323, +246]     |
| `DAHook`        | **−235 [−381, −104]**   | **−222 [−339, −26]** |
| `ABHook`        | **−460 [−630, −288]**   | −437 [−625, −291]    |
| `MEVChargeHook` | **−913 [−1659, −728]**  | −920 [−1693, −627]   |

The structure of the findings, in order of confidence:

1. **No evaluated dynamic policy beats the pre-registered static 30 bps
   baseline at the calibrated operating point.** `DAHook`, `ABHook`, and
   `MEVChargeHook` lose with intervals excluding zero on **both**
   valuations; `BAHook` is indistinguishable from the baseline (interval
   covers zero) and loses on the stable pair (−542 [−924,
   −226]).
2. **The optimum in this box is a static fee.** The static curve — mean
   `net_result` 1,644 / 11,890 / 11,932 / 7,936 at 5 / 30 / 60 / 100 bps
   — has its interior optimum on the 30–60 bps plateau, consistent with
   the model's
   $\operatorname{argmax}_f\, f\,e^{-\lambda|r(f)|} \approx 2/\lambda
   \approx 43$ bps. 60 vs 30 bps is itself a coin flip (−2 [−186,
   +266]). Note the optimum's location follows from the assumed
   participation function; that must always be said beside it.
3. **Where the losses come from is fee income, not impermanent loss.**
   Median paired decomposition on the volatile pairs: `DAHook` −273 of
   fee income against an IL term of −4; `ABHook` −411 against +1. The IL
   invariance is structural: arbitrage pins the end-of-window pool price
   to the external price under every policy, so a fee policy in this
   model cannot reduce adverse selection — it can only price flow. The
   adaptive policies price it slightly worse than a well-chosen
   constant, and pay their extra gas on top.
4. **`ABHook` — the paper's litmus — loses everywhere**: all three pairs,
   both valuations — every one of its 27 cells' intervals sits below zero.
5. **The informed share rises with gas** — 12.4% → 13.7% across 5 → 80
   gwei — the direction the 2026-08-10 pre-registration predicted:
   expensive gas prices small retail draws out first. (On the
   pre-revision harness this test read flat, because only one retail
   direction was paying gas.) Retail participation falls 0.367 → 0.221
   across the same axis.
6. **Contrast with the pre-revision run, stated openly**: the earlier
   matrix showed `DAHook` at +341 [+264, +672] — the revision flipped it
   to −235 [−381, −104]. The pre-revision advantage is consistent with
   the directional ratchet monetising the artificial one-sided retail
   flow the gas term was creating ([§11](#11-revision-note-2026-08-12)); on the corrected flow the same
   mechanism misprices. This reversal is the strongest argument the
   project has for its own methodology: paired design, conservation
   checks, and archived manifests are what made it detectable and
   attributable.

### The informed-heavy probe: adaptation does not win there either

The single most favourable operating point for the adaptive policies —
$\kappa \times 0.1$, where the pre-revision sweep had shown their largest
advantage — was re-run on the revised harness (ETH/SHIB, 7 policies × 24
windows × 3 gas = 504 cells, 0 errors). Measured arbitrage share of
volume: **63.8%**.

- The static curve is monotone above 30 bps (−300 / 2,447 / 3,190 /
  3,349 at 5/30/60/100 bps): with little retail left to lose, the best
  static fee sits at the **box ceiling** — the boundary regime the
  pre-revision sweep also predicted.
- Against the 30 bps baseline over 72 windows: `MyHook@6000` **+190**
  (end-of-window) / **+126** (trade-time), both intervals above zero —
  the winners at the informed-heavy point are **higher static fees**.
  `DAHook` is indistinguishable from the baseline (−41 / +2, n.s.);
  `ABHook` loses on both valuations; `BAHook` is the one mixed case
  (−67 undecided end-of-window vs +42 above zero trade-time, driven entirely
  by a real high-volatility-regime signal of +461/+633) — but in that
  same stratum a static 100 bps gains +1,938, so even where adaptation
  shows signal, a constant beats it.

The pre-revision sweep's conclusion — "the adaptive advantage is
positive and significant at every $\kappa$" — is therefore withdrawn
along with the runs that produced it.

_(The probe above was the first post-revision look at the informed-heavy
mix; it has since been superseded by the **full** $\kappa = 0.1$ matrix —
5,832 cells, all pairs and policies — whose regime × gas results are
reported below.)_

### Where adaptation does pay: the regime × gas decomposition

Pooled headline numbers hide a real conditional structure. Crossing the
two experimental axes — volatility regime × gas scenario — and pooling
the volatile pairs (48 paired windows per panel, median difference vs
the 30 bps baseline, 95% bootstrap CI over windows;
`paper/Image/uu_regime_gas_grid.pdf`):

| panel (both valuations agree)   | `BAHook` vs 30 bps                              |
| ------------------------------- | ----------------------------------------------- |
| **high volatility × 5 gwei**    | **+1,556 [+894, +2,501]** end / +1,481 tt — wins |
| **mid volatility × 5 gwei**     | **+367 [+115, +571]** end / +461 tt — wins       |
| high volatility × 20 gwei       | +479 [+46, +1,342] end; tt covers zero — mixed  |
| everything at 80 gwei           | every hook loses or ties                        |

`DAHook` adds one mixed panel (high × 5 gwei, trade-time only);
`VolatilityHook` is positive but its interval covers zero in the storm-cheap-gas
corner; `ABHook` and `MEVChargeHook` win nowhere.

The pattern is monotone in both directions and mechanistically coherent:
adaptation earns in storms (where the regime-optimal fee departs from
the baseline) and is taxed by gas everywhere (oracle hooks cost 108–124k
gas per swap against the static hook's 76k, and retail pays that inside
$r$). Cheap gas + high volatility is exactly the corner where the
earnings exceed the tax.

**The same grid at the informed-heavy point** (κ = 0.1 full matrix,
re-run post-revision: 5,832 cells, arb share 57.7%;
`uu_t01_regime_gas_grid.pdf`): the storm-cheap-gas corner strengthens
and changes owners. **`VolatilityHook` (+308 [+32, +742] end / +499
[+358, +734] tt) and `DAHook` (+246 / +296) beat the baseline in the
high-volatility × 5 gwei panel on both valuations.** `BAHook` wins
high-vol at all three gas levels on the trade-time valuation
(+674/+444/+213) but not on end-of-window — a mixed, valuation-dependent
result reported as such. The corner finding therefore replicates across
both operating points, with the winning policy depending on the flow
mix: `BAHook` at the retail-dominated point, `VolatilityHook`/`DAHook`
at the informed-heavy one.

**Read the grid in relative terms, not absolute** (companion figure
`uu_regime_gas_grid_rel.pdf`, normalised by each panel's median baseline
result). High-volatility windows are 2–3× larger in every dollar
quantity (median baseline +22.4k at 5 gwei high vs +9.2k low), so equal
relative losses draw longer bars in storms and the absolute grid can
read as "adaptation does worse in storms" — the opposite of the truth.
Normalised, every one of the five policies improves monotonically with
volatility at every gas level (e.g. `BAHook` at 5 gwei: +5.0% high →
+2.2% mid → +0.1% low; at 80 gwei: −4.8% → −11.1% → −15.8%), and
degrades monotonically with gas in every regime. Two clean monotone
gradients, exactly as the mechanism predicts. Caveats: this decomposition pools the two
volatile pairs (a more liberal estimand than the per-stratum machinery),
is one seed, and the corner-conditional claim was not pre-registered —
it is reported as observed structure, with the CSV beside the figure.

### The full κ range: five matrices, one picture

All five operating points now exist as full matrices (5,832 cells each,
0 errors) and two figures put them side by side:

- **`uu_kappa_trend.pdf`** — the pooled headline estimand per hook
  across κ. **No hook's pooled interval clears zero at any κ**: the
  unconditional verdict is uniform across the entire retail-scale
  range, and the pooled losses shrink as κ falls (there is less
  mispriced retail to lose).
- **`uu_kappa_trend_high.pdf`** — the storm slice of the same range:
  high-volatility windows only, split by gas scenario. This is where the
  blue lives: `BAHook`'s cheap-gas storm wins at the retail-heavy κ,
  `VolatilityHook`'s all-gas storm wins at the arbitrage-dominated
  extreme.
- The per-κ grids (`uu_*regime_gas_grid*`, five sets) — where the full
  conditional structure lives. The storm-corner ownership across the
  range, both valuations agreeing:

| κ (arb share) | high-vol wins (both valuations)                     |
| ------------- | --------------------------------------------------- |
| 3.0 (16%)     | `BAHook` @ 5, 20 gwei (+ mid @ 5)                   |
| 1.0 (13%)     | `BAHook` @ 5 gwei (+ mid @ 5)                       |
| 0.3 (25%)     | `BAHook` @ 5, 20 gwei; `DAHook` @ 5                 |
| 0.1 (58%)     | `VolatilityHook` @ 5; `DAHook` @ 5                  |
| 0.03 (89%)    | `VolatilityHook` @ 5, 20, **80**; `BAHook` @ 5      |

The relay is clean: at retail-dominated mixes the storm corner belongs
to `BAHook`; as the informed share grows it passes to
`VolatilityHook`/`DAHook`, and at the arbitrage-dominated extreme
`VolatilityHook` wins storms at **every** gas level — the retail-gas
tax no longer matters when there is hardly any retail. The practical
reading repeats itself at every scale: _which policy, if any, depends
on what kind of pool you are and what gas costs; none dominates._

The one-sentence summary the corrected evidence supports:

> No evaluated dynamic-fee policy outperforms a well-chosen static fee
> *unconditionally*: pooled across regimes and gas scenarios every hook
> loses or ties, at both flow mixes. Conditioned on the experimental
> axes, a real advantage exists in one corner — `BAHook` beats the
> baseline by ~+1,500 USDT/window in high-volatility windows at cheap
> gas, on both valuations — and is consumed by the policies' own gas
> premium as gas rises. The framework's contribution is that this
> conditional structure is measurable at all — paired, reproducible,
> and decomposed along pre-declared axes.

---

## 11. Revision note (2026-08-12)

The retail gas term of $r$ was corrected to be denominated in token1 for
both trade directions — the valuation currency the participation model
uses. Before the revision, the B→A direction's gas entered $r$ in token0
units, understating it by $p_0/p_1$ on the volatile pairs, so gas thinned
only one side of the retail flow. The correction is pinned by a
regression test (`test_uuHighGasSuppressesBothDirections`); the Solidity
suite passes 110/110.

Consequences: the headline matrix was re-executed on the revised harness
the same day ([§10](#10-main-results--corrected-matrix-of-2026-08-12) reports it; the earlier arbitrage-only experiments are
unaffected). Pre-revision outputs are archived at
`results-uu-gas-unit-defect/` and are not citable — in particular the
pre-revision `DAHook` advantage, which did not survive the correction.
Re-run on the revised harness since: the full operating points
$\kappa \in \{0.03, 0.1, 0.3\}$ (with 3.0 in flight). Still pending:
the seed-robustness appendix.

---

## 12. Limitations and claim boundary

Stated plainly; each bounds a claim:

- No retail strategy (routing, timing, splitting), no correlated demand —
  the mechanism real order-flow imbalance mostly comes from.
- One arbitrageur, once per candle, perfect information; no mempool,
  latency, builder ordering, or competition.
- Liquidity minted once, full-range; no concentrated-liquidity dynamics.
- Mock feeds validate integration, not oracle behaviour.
- The informed/uninformed mix is set by an assumed κ and swept, not
  calibrated to real pools (the obvious improvement: calibrate κ from
  real pool volume/TVL).
- k = 1 retail granularity is the most imbalanced assumption available.
- Results are one year (2024), three pairs, one venue's data.

The paper may claim: a working, reproducible evaluation framework
(primary), and the conditional economic finding of [§10](#10-main-results--corrected-matrix-of-2026-08-12) (secondary), with
fixed-fee baselines under identical conditions, effect sizes with
intervals, and pre-registered protocol. It may not claim: universal
superiority of dynamic fees, adverse-selection protection, or anything
about live oracle behaviour.

---

## 13. Reproducing

```bash
uv sync                                   # Python deps
export PATH="$HOME/.foundry/bin:$PATH"    # Foundry
cd contracts && forge test                # 110 Solidity tests
uv run pytest                             # ~341 Python tests
# full corrected matrix (the run of record for the paper):
caffeinate -is uv run python run_matrix.py --uu \
  --policy ABHook --policy BAHook --policy DAHook --policy MEVChargeHook \
  --policy MyHook@500 --policy MyHook@3000 --policy MyHook@6000 \
  --policy MyHook@10000
```

Completed cells are skipped by manifest; a killed run resumes. Analysis
lives in `analysis/07`, `08` (matrix), `10` (seeds), `11` (operating
points); figures land in `paper/Image/` stamped with the operating point
that drew them.

---

## 14. Glossary

- **pips** — fee unit: hundredths of a basis point; 1e6 = 100%; 30 bps =
  3000 pips.
- **WAD** — fixed-point 1e18 scale used for r, P, λ, and trace sizes.
- **window** — one day of one-minute candles; the unit of observation.
  Every metric labelled "per window" therefore reads "per simulated
  day", and a figure's per-policy point is that policy's **average
  day** unless it says median.
- **cell** — one (policy, pair, window, gas) run of the harness.
- **panel** — one (regime, gas) square of the grid figures, pooling
  the two volatile pairs: 48 paired windows. A coarser slice than a
  stratum (which keeps pairs apart).
- **stratum** — one (policy, pair, regime, gas) group of windows; the
  pre-registered unit of statistical analysis.
- **tercile / regime** — volatility third of 2024 (calm/medium/stormy).
- **$V_{\text{profile}}(c)$** — the measured shape of the trading day:
  the pair's retail activity in minute $c$, taken as the geometric mean
  of the two legs' per-minute traded USDT volume on **Binance's own
  spot markets** (ETHUSDT, SHIBUSDT, …) — not any pool's volume, and
  not a direct measurement of ETH↔SHIB demand (no such market exists
  anywhere liquid; the two legs' joint activity is the proxy). Identity
  for the single-leg stable pair. Only the intraday **shape** is used —
  normalised to sum to one over an average day
  ($\hat{s}(c)$ in [§4.4](#44-κ--the-retail-scale)) — the level is
  $\kappa$'s job:
  $v_0(c) = \kappa \cdot \text{basket} \cdot \hat{s}(c)$. Geometric rather than arithmetic so the
  hundred-times-larger leg (ETHUSDT) cannot drown the smaller one's
  rhythm. Potential retail demand of a minute is
  $v_0(c) = \kappa \cdot V_{\text{profile}}(c)$: the profile supplies
  the _when_ (sessions, quiet nights, bursts), $\kappa$ the _how much_.
  At $\kappa = 1$ the average minute carries ≈ 13.9k USDT of potential
  demand (≈ 7k per direction).
- **$\kappa$ (kappa)** — retail scale: how much potential retail volume
  arrives per day, in units of "baskets per day". $\kappa = 1$
  (calibrated) ⇒ retail potentially trades one pool-worth (20M USDT) per
  day. "$\kappa = 0.1$" / `turnover-0.1` ⇒ ten times less retail ⇒
  arbitrage becomes ~half of all volume. See [§4.4](#44-κ--the-retail-scale) for what each level
  means in pool terms.
- **$\kappa$ sweep** — sensitivity experiment re-running the comparison
  at $\kappa \times \{0.03, 0.1, 0.3, 1, 3\}$ to show the ranking is not
  an artifact of the assumed retail scale.
- **$\lambda$ (lambda)** — retail price-sensitivity: half the willing
  flow walks at a 30 bps total cost.
- **$r$** — normalised disadvantage of a retail trade,
  $r = (V_{\text{out}} - V_{\text{in}} - G)/(V_{\text{out}} +
  V_{\text{in}} + G)$; **$P_{\text{exec}}$** — probability the trade
  executes, $e^{-\lambda|r|}$ for $r < 0$, else $1$. Distinct from the
  external price $P$.
- **informed share / arbitrage share** — fraction of executed volume that
  is arbitrage; the quantity the mechanism actually depends on.
- **`discrete` mode** — how retail flow is drawn
  ([§4.5](#45-how-retail-flow-is-drawn)): one random-size trade per
  direction per minute, executed all-or-nothing with probability
  $P_{\text{exec}}$,
  from a recorded seed.
- **no-arbitrage band** — $[P\gamma,\, P/\gamma]$: pool prices at which
  the fee eats the arbitrage edge ($\gamma = 1 - f$).
- **IL (impermanent loss)** — HODL value minus LP principal at a common
  price; **LVR-adjacent** in this closed system.
- **σ, three of them** — the lognormal shape of retail trade sizes
  (σ = 1, [§4.5](#45-how-retail-flow-is-drawn)); the per-minute
  volatility estimate `VolatilityHook` tracks; and the realised daily
  volatility that defines the regime terciles. Same letter by
  convention, three different quantities — context names which.
- **net_result / net_result_tt** — LP-vs-HODL at end-of-window prices /
  realised P&L at trade-time prices ([§9](#9-metrics)). Sign
  convention: **negative means the LP did worse than simply holding the
  tokens** — an opportunity shortfall, not necessarily an absolute loss
  of principal.
- **Wilcoxon / Benjamini–Hochberg** — classical significance tests the
  pipeline still computes into every CSV (see the [§6.2](#62-pairing-and-statistics) footnote); not
  used in this document's prose, which decides everything by the
  bootstrap interval.
- **bootstrap CI** — percentile interval of the median from 10,000
  seeded resamples; the effect-size instrument that travels with every
  comparison.
- **seed appendix** — the same cells at five RNG seeds; only
  sign-unanimous findings are quotable.
- **manifest /
  $E = \langle C_{\theta}, D, P_0, L_0, W, S \rangle$** — the
  six-component run identity ([§2.3](#23-reproducibility-the-run-identity)) that makes a cell reproducible and
  re-runs skippable.
- **conservation check** — pool-state vs trader-flow reconstruction of LP
  holdings; agreement at ~1e-16 or the cell is invalid.
$$
