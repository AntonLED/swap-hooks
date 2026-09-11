# Traceability review: specs vs code vs paper

Date: 2026-08-10. Reviewer pass over the three artifacts that must agree — the
specifications under `docs/superpowers/specs/`, the code (`experiments/*.py`,
`contracts/src/*.sol`, `contracts/test/Replay.t.sol`, `run_matrix.py`,
`analysis/*.ipynb`), and `paper/main.tex`.

Nothing was executed that writes to `data/`, `results/`, `results-uu/` or
`results-uu-preflight-defect/`; no forge, no `pytest -m slow`, no sweep module.
Manifests and CSVs on disk were read, not regenerated. Pre-registrations are
reported on, never edited.

Findings are grouped by the artifact that is wrong. Each gives the spec text,
the code line, the paper text where relevant, the verdict, and whether it
touches a published number, a published claim, or neither.

---

## A. The reproducibility identity `E = <C_θ, D, P₀, L₀, W, S>`

### A1. `P₀` is `null` in every manifest on disk — the field is never filled

**Spec.** `2026-08-02-dynamic-fee-experiments-design.md` §10: "Each run writes
alongside its results: … initial pool price (`P₀`) and initial liquidity
(`L₀`)". Paper Eq. (9) (main.tex:244) names `P_0` as one of six fields.

**Code.** `experiments/matrix.py:264`

```python
p0_sqrt_price_x96 = (None,)  # set by the harness from the window's first candle
```

`experiments/manifest.py:138` writes it straight through. Verified on disk:
`"P0": null` in every manifest sampled from both `results/matrix/` and
`results-uu/matrix/`.

**Verdict: the code is wrong.** The comment is true — `Replay.t.sol:221` derives
`sqrtPriceInitialX96` from candle 0 of the window, so `P₀` is a function of `W`
— but "derivable" is not "recorded", and Eq. (9) is the paper's own answer to
the question "why do two runs on the same nominal month diverge?". Five of six
fields plus a checksum are recorded; one is a literal `null`.

**Impact: a published claim, not a number.** No result is unreproducible. But
the paper cannot claim the manifest closes Eq. (9) while one field is empty. The
cheap fix is to record the value the harness computed (it is already in the
window record as `sqrtPriceInitialX96`).

### A2. `input_checksum` is the same value for all 15,552 cells and describes none of them

**Spec.** §10: "a checksum of the input klines". `manifest.py:109-114`
docstring: "Hash of the exact input candles, so a silent data change is
detectable."

**Code.** `experiments/matrix.py:234`

```python
inputs = [p for p in (data / "trace0.csv", data / "trace1.csv") if p.exists()]
```

reads `<root>/data/`. But a matrix cell writes its candles to its **worker**
directory: `run_one.py:124` `traces = Path(work_dir) if work_dir else data`, and
`matrix._worker:323` always passes `work = ROOT / ".work" / spec.key`. So
`data/trace0.csv` is whatever a previous ad-hoc `run_one` left behind.

Verified: 400 sampled UU manifests all carry
`"input_checksum": "d3b98a44090795fd"`.

**Verdict: the code is wrong.** The field is not a checksum of the run's inputs;
it is a checksum of an unrelated scratch file, identical across every cell of
both matrices.

**Impact: a published claim.** Nothing computed today is wrong, but the field
cannot detect the silent data change it exists to detect, and the paper's
reproducibility paragraph must not claim it can.

### A3. `uu_trace_checksum` has the same defect

`matrix.py:255-257` hashes `data/uu_trace.csv`; the cell's UU trace is written
to `.work/<key>/uu_trace.csv` (`run_one.py:151`). All 400 sampled manifests
carry `"uu_trace_checksum": "bb88b1f75c40122b"`.

**Impact: neither**, because `uu_kappa`, `uu_lambda_wad`, `uu_mode`, `uu_seed`
and `uu_sigma` are recorded separately and correctly (§A5, and κ verified in
§CONSISTENT below), so nothing that would change the trace goes unrecorded. Same
fix as A2.

### A4. `manifest_for` records constants, not the values used

`matrix.py:246-253` hardcodes

```python
"uu_lambda_wad": UU_LAMBDA_WAD,
"uu_seed": 0,
"uu_sigma": 1.0,
```

rather than the arguments actually threaded into `run_one`. Inert today —
`run_matrix.py` never overrides them — and it becomes silently wrong the moment
the λ sweep of design §2.1 is driven through the matrix (see B6). `uu_kappa` is
the exception and _is_ computed per pair (line 250).

**Verdict: latent code defect.** **Impact: neither, today.**

### A5. Field `D` is three generations deep on disk — correct behaviour, but the paper must say so

- `results/matrix/` (arb-only, frozen): `contracts_src = 9a580b2b8d40bd23` —
  hashed `src/` only, before the `test/` extension and before the
  `MEVChargeHook` fee-box clamp existed.
- `results-uu/matrix/`: **14,975 cells at `c5dff798da6e0bff`** and **577 at
  `8c1df17765c45825`** (the MEVChargeHook re-run, in flight at review time).
- Working tree now: `8c1df17765c45825`.

This is the resume protection working exactly as `manifest.py:83-106` describes.
It is not a defect. But `results-uu/summary.csv` will, when the re-run lands,
describe one matrix executed under **two** harness revisions, and
`results/matrix/`'s field `D` does not pin the harness at all (the clamp lives
in `contracts/test/utils/HookTest.sol:152-158`, one directory outside the hash
that manifest generation used at the time).

**Impact: a published claim** — the reproducibility note must state both facts.
PROGRESS already licenses the mixed UU matrix via the differential; the arb-only
gap is not yet written down anywhere.

### A6. Neither sensitivity driver writes a manifest at all

`experiments/sensitivity.py` (`captureShare`, 504 cells) and
`experiments/kappa_sensitivity.py` (κ, 2,160 cells) call `run_one` directly and
never touch `build_manifest`. Spec §10 says "Each run writes alongside its
results" the manifest.

**Verdict: code wrong.** **Impact: a published figure** —
`paper/Image/capture_share_sensitivity.pdf` and its CSV are reported in the
paper's planned text and have no recorded `E`.

---

## B. UU flow: spec vs code

### B1. §2.2 says the fee in `r` is quoted at zero size; the code quotes it at the candle's potential volume

**Spec.** `2026-08-09-uu-flow-design.md` §2.2: "Per direction, evaluated at the
pre-swap pool state, **marginal (zero-size) execution price** against the
external price."

**Code.** `Replay.t.sol:433-440`

```solidity
uint256 potentialAmountIn = FullMath.mulDiv(sizeWad, PRICE_SCALE, priceIn);
...
uint24 fee = _feeForSender(sender, zeroForOne, potentialAmountIn);
```

The _price_ is still marginal (`UUMath.rWad` takes only `sqrtPriceX96`, no size
term) — only the **fee quote** moved off zero.

**Verdict: the code is right, the spec is stale.** A zero-size quote let a
`size_dependent` policy advertise its base rate and charge a surcharge:
MEVChargeHook's log said 30 bps while the pool credited ~65, and retail decided
to trade on the advertised number. The code comment at `Replay.t.sol:422-433`
argues it correctly — quoting at the _actual_ amount would reintroduce the fee →
P → size → fee loop that §2.2 already broke for slippage.

**Impact: a published number, for MEVChargeHook only** (1,296 cells, re-run in
flight; the other eleven policies are provably unaffected). The design spec —
which is not a pre-registration and may be amended — needs a §2.2 amendment
paragraph, and the paper must carry it as a declared modelling choice.

### B2. `feeMax` "10000 pips" (design §7) vs "100 bps" (prereg): the same number, applied correctly

Asked directly in the brief, so stated directly: **1 bp = 100 pips, so 100 bps =
10000 pips. The two documents agree.**

- Design §7: "Its config `feeMax` is set to **10000 pips**".
- `2026-08-09-uu-matrix-preregistration.md`: "`feeMax`: 1000 → **100 bps**".
- Code: `contracts/test/utils/HookTest.sol:156-157`

  ```solidity
  MEVChargeHook(flags).setFlaggedFeeAdditional(40);
  MEVChargeHook(flags).setFeeMax(100);
  ```

  against a contract whose field genuinely is in bps (`MEVChargeHook.sol:56`
  `uint16 feeMax; // upper bound…`, default `1000` at line 62, and `_getFee:369`
  converts with `fee = uint24(candidateBps * 100)`).

The ordering constraint the prereg describes is also honoured: 40 is set first
because `setFeeMax` enforces `fixedLpFee + flaggedFeeAdditional ≤ feeMax`
(`MEVChargeHook.sol:183`) and 30 + 400 > 100.

**Verdict: no disagreement.** One request: design §7 is the only place in the
project that states this constant in pips. Given that fee units are the named
hazard, normalise it to bps or state both.

### B3. `events.FEE_BOXES_BPS` was not updated for the clamp — and a notebook measures "at cap" against it

**Spec/prereg.** The clamp above puts MEVChargeHook's box at **[30, 100] bps**
under the UU harness.

**Code.** `experiments/events.py:136-139`

```python
"MEVChargeHook": (30.0, 1000.0),
"MEVChargeHookFixed": (30.0, 1000.0),
```

and the comment above it at line 123 still reads "MEVChargeHook
`fixedLpFee=30, config.feeMax=1000`".

`analysis/08-uu-flow-behaviour.ipynb` cell 8 computes
`at_cap = (values >= high).mean()` from this table over the **UU** traces.

**Verdict: the code is wrong.** The ceiling is off by 10×, so MEVChargeHook's
"at cap" fraction under UU flow reads ~0 whatever the policy did. This is
precisely the defect fixed on 2026-08-03 for `fee_distribution` ("measured
against the drawn box, MEVChargeHook was 90.7% at cap … against its real box it
is 0.8%"), reintroduced by the clamp landing in the harness rather than the
table.

**Impact: a published figure and table.** Must be fixed before the MEVChargeHook
re-run's fee behaviour is reported. Note the box differs between the two
experiments — 1000 bps in `results/`, 100 bps in `results-uu/` — so a single
constant cannot serve both; the table needs to be parameterised by experiment or
the arb-only fee figures redrawn under a labelled caveat.

### B4. §6 calls `uu_volume`/`arb_volume` "retained_volume splits"; they use a different valuation

`metrics.py:279-280` values both at **trade-time** prices
(`_volume_trade_time_usdt`); `retained_volume` at `metrics.py:203-207` uses
**end-of-window** prices. They are therefore not splits of it.

Measured across all 15,552 UU cells: median
`(uu_volume + arb_volume) / retained_volume = 1.0000050`. `figures.uu_flow:754`
forms the share from the two new columns, never from `retained_volume`.

**Verdict: spec wording is loose; the code is fine.** **Impact: neither**
(5e-6). One clause in §6.

### B5. §8 names the wrong output directory

Design §8: "the new matrix writes to `results/matrix-uu/`". Code:
`run_matrix.py:137-138` writes `results-uu/matrix/`, which is also what the
later pre-registration says. Spec §8 is stale. **Impact: neither.**

### B6. The λ sweep is declared in two documents and implemented nowhere

**Spec.** Design §2.1: "λ is a swept sensitivity axis (like `captureShare`),
values `{58, 116, 231, 462, 924}`". UU prereg: "The λ-sweep {58, 116, 231, 462,
924} is a sensitivity axis, stored under `results/sensitivity/`, never merged."
Design §9: "the UU model is synthetic and its λ, κ are swept, not asserted."

**Code.** No sweep driver exists. `run_one` accepts `uu_lambda_wad`
(`run_one.py:102`) and `Replay.t.sol:143` reads it, so the plumbing is there,
but there is no analogue of `sensitivity.py` / `kappa_sensitivity.py`. κ's sweep
module exists but has not been run either.

**Verdict: orphan — spec requires, code does not implement.**

**Impact: a published claim.** As things stand, design §9's sentence "its λ, κ
are swept, not asserted" is false for λ and unexecuted for κ. Either the sweeps
run before 2026-08-18 or the paper says plainly that λ was fixed at ln(2)/0.003
and not varied.

---

## C. The pre-registered analysis plan vs what is computed

### C1. `run_matrix.py` reports one of two co-primary valuations, unlabelled

**Prereg.** `2026-08-09-uu-matrix-preregistration.md`: "in **two valuations,
both co-primary and always reported side by side**".

**Code.** `run_matrix.py:224`

```python
result = analyse(paired)
```

`stats.analyse`'s default is `value="net_result_delta"`. The single file written
to `results-uu/analysis.csv` is 594 rows with columns
`policy,pair,regime,gas_price_wei,address_mode,p,median,win_rate,n,n_effective,significant_fdr`
— no column names the valuation, and `net_result_tt` appears nowhere. The
trade-time family exists only inside `analysis/07-uu-main-results.ipynb`.

**Verdict: the runner is wrong against the prereg.** The pattern already exists
in the codebase and is correct one file over: `kappa_sensitivity.analyse:226`
loops both valuations, emits a `valuation` column, and applies BH **per
valuation family**. `run_matrix.py` has not adopted it.

**Impact: a published number.** The artifact a reader picks up reports one
co-primary quantity and does not say which. Fix: two files
(`analysis-net_result.csv`, `analysis-net_result_tt.csv`) or one with a
`valuation` column and separate BH families.

### C2. BH is still run over the address-duplicated family

**Code.** `stats.analyse:102-108` includes `address_mode` in `strata`. Family
size on disk: 594 rows in both `results/analysis.csv` and
`results-uu/analysis.csv` (11 policies × 3 pairs × 3 regimes × 3 gas × 2 modes).

**Finding already recorded** (PROGRESS, 2026-08-03 audit): 266 of 270 arb-only
comparisons are bit-identical across the address axis; on the deduplicated
family of 274 there were **zero verdict changes**, but the headline is "56
significant of 274, not 112 of 540".

**Verdict: no deduplication is implemented anywhere.** BH is invariant to exact
duplication, so no verdict is wrong — but every _count_ read off `analysis.csv`
is doubled, and the UU experiment inherits this unchanged.

**Impact: a published number** (the headline "N of M significant"). Either
deduplicate before BH or make the runner print the distinct count beside the raw
one.

### C3. The κ sweep's family contains nested tests

`kappa_sensitivity.analyse:232`

```python
for regime, subset in list(group.groupby("regime")) + [("ALL", group)]:
```

adds an `ALL` stratum that is the union of the three regime strata, so each
policy contributes four tests of which one is a superset of the other three. The
κ pre-registration says "Same machinery as the pre-registered analysis and **no
more**", and §12.1's strata are per-regime.

**Verdict: minor code deviation from the prereg it was written against.**
Inflates the family 4/3× with non-independent tests. **Impact: a number that
does not exist yet** (the sweep has not run). Drop the `ALL` row, or declare it
and exclude it from the BH family.

---

## D. Paper vs specs and code

The paper has not been touched since before the first experiment. Everything
below is the paper being wrong, except where noted.

### D1. `tab:hooks` lists five templates; twelve configurations are run

Missing rows: a volatility hook (claimed in prose at main.tex:56 and 212, absent
from the table), `MEVChargeHookFixed`, `PegDefence` and `PegCapture` as two
distinct readings of the peg template (design §5 requires both be shown as
such), and the four static baselines.

**Impact: a published claim.** The table is the paper's inventory of what the
framework provides.

### D2. The `ABHook` row is wrong on both of its claims

**Paper.** main.tex:227 — granularity "Block-level", primary signal "External
ratio with asymmetric response".

**Code.** `contracts/src/ABHook.sol`:

- `_afterSwap` (lines 124-165) has **no `block.number` gate**. It updates on
  every swap. (Compare `BAHook.sol:155` `if (block.number > lastBlock[poolId])`
  and `VolatilityHook.sol:159`, which do gate.)
- It reads the **pool** price, not an oracle: line 131
  `(uint160 currentSqrtPriceX96,,,) = _poolManager.getSlot0(poolId);`. The
  constructor at line 65 takes two `AggregatorV2V3Interface` parameters and
  **discards them — both are unnamed** and no feed is ever read.

**Spec.** Design §5 has it right: "`ABHook` | pool price change, constant fee
sum | reallocation".

**Verdict: the paper is wrong; the spec and code agree.** `CLAUDE.md` repeats
the paper's version and is wrong too.

**Impact: a published claim, on the comparison the paper singles out.** ABHook
vs static 30 bps is the litmus (design §12.1, decision 7). Describing it as
oracle-informed and block-level misstates what the litmus tests: it isolates
**allocation of a fixed fee budget across directions from a pool-price signal**,
with no external data at all.

### D3. "trade volume variance" is wrong; it is price variability

**Paper.** main.tex:212: "volatility-based hooks utilizing Exponential Moving
Average (EMA) and Welford's online algorithm to react to **trade volume
variance**."

**Code.** `VolatilityHook.sol:161-187`: `_getPriceRatio()` (lines 97-102) reads
the two Chainlink-compatible feeds, line 169 forms the relative change of that
ratio, line 177-178 squares it, line 182 feeds the exponentially weighted
variance. **No trade volume enters the hook anywhere.**

**The paper contradicts itself**: main.tex:96 says "Volatility-based mechanisms
react to price variability", which is correct.

**Verdict: main.tex:212 is wrong.** Correct text: variance of the change in the
external token-price ratio.

### D4. Welford no longer computes the fee — the contributions bullet overclaims, and design §6 is stale too

**Paper.** main.tex:56: "specifically implementing Exponential Moving Average
(EMA) and Welford's online algorithm **for variance-based fee calculation**".

**Code.** `VolatilityHook.sol:171-175`:

```solidity
// Kept for the reported diagnostic and its own tests; the fee no
// longer depends on it.
Welford.State memory s = _stats[poolId];
```

The fee reads `emaVariance` (lines 180-187), an exponentially weighted variance
of the squared ratio change.

**Spec.** Design §6 still specifies Welford feeding the fee: `σ² = M₂/(n−1)`
then `f = clamp(f_base + c·σ, f_min, f_max)`.

**Verdict: the paper _and_ design §6 are wrong; the code is right.** The
2026-08-03 audit found the cumulative estimator freezes — measured fee range 8 →
5 → 3 → 1 → **0** pips across successive fifths of one window, total range 0.17
bps — because a cumulative variance moves by O(1/n). The fixed-horizon EWMA is
the correction.

**Impact: a published claim.** Honest replacement: "an exponentially weighted
variance of the external price-ratio change, with Welford's algorithm retained
as the reported diagnostic". Note the standing caveat that even after the fix
the policy is **not volatility-responsive at the shipped coefficient** — fee
spread 0.35 bps around a 5.1 bps median across the whole UU matrix — which the
paper must state rather than claim the mechanism works.

### D5. The paper describes one experiment; three have run, and its headline number is unreproducible

**Paper.** main.tex:31 (abstract), 290, 292, 326 all rest on "1,492 simulated
swaps" over one ETH/SHIB trace. main.tex:301: "The artifact provides no
same-trace fixed-fee baseline, repeated trials, uncertainty intervals, gas
measurements, or complete specification of trade sizing and data cleaning."

**Code and results.** Every item on that list now exists:

| main.tex:301 says missing     | now on disk                                                                        |
| ----------------------------- | ---------------------------------------------------------------------------------- |
| same-trace fixed-fee baseline | `policies.BASELINE_FEES_PIPS = (500, 3000, 6000, 10000)`, run on identical windows |
| repeated trials               | 72 windows/pair × 3 pairs × 3 gas × 2 address modes                                |
| uncertainty intervals         | `stats.analyse`, Wilcoxon + BH, medians and win rates per comparison               |
| gas measurements              | `experiments/gas_estimates.json`, per-policy, plus a three-level gas axis          |
| trade sizing spec             | design Appendix A, `ArbMath`, `_optimalSize`                                       |

**"1,492" appears nowhere on disk.** No script, notebook, spec, result file or
figure CSV produces it — the only occurrences in the repository are
`paper/main.tex` (four times) and `CLAUDE.md` quoting the paper. Its figure,
`paper/Image/dynamic_fee_reaction.pdf` (mtime 2026-08-02 14:43), has no CSV
table view and no notebook that draws it, unlike all 25 figures the current
pipeline produces.

**Verdict: the paper is stale.** **Impact: every published number in it.**

### D6. Three of the five application-layer artifacts the paper claims do not exist

**Paper.** §III-A (main.tex:135) and §III-D/§III-E (256, 260) claim: a Flask
configurator and browser code; `Simulation.t.sol`; backend integration tests
**in Go**; **Playwright** e2e tests; and a **PostgreSQL** history with
`HookParamsHistory`, `ChainEvent`, `PoolStateSnapshot`.

**Repository.**

- Flask app: `dex/web_interface/app.py`. Exists — inside `dex/`, which PROGRESS
  lists as "now redundant … Deleting it is proposed but not done".
- `Simulation.t.sol`: `dex/test/Simulation.t.sol`. Same caveat. The current
  replay harness is `contracts/test/Replay.t.sol`.
- Go: **no `.go` file anywhere in the tree.**
- Playwright: **no configuration, no test, no dependency** in `pyproject.toml`
  or `package.json`.
- PostgreSQL / the three models: **no match anywhere** except Russian-language
  prose in `dex/test.md`.

`CLAUDE.md` already flags the Go/Flask inconsistency as something to "resolve
against the actual paper sources"; the sources are here and the answer is that
Go does not exist.

**Verdict: the paper overclaims.** **Impact: published claims, three of them.**
Additional risk: deleting `dex/` removes the artifact behind the two that _do_
exist and behind Figures 2, 3 and 4.

### D7. Two items from design §15 are still outstanding verbatim

- main.tex:135 "Anvil provides the local EVM" — the replay is a Forge test and
  Anvil is never started. Flagged 2026-08-02, unchanged.
- main.tex:297, Fig. 5 caption: "dynamic fee parameter (in basis points)" over
  an axis design §15 records as carrying values of 3000–3200, i.e. pips
  mislabelled as bps — a factor of 100 on the paper's one results figure, in a
  paper whose §III-B (main.tex:183) correctly states the unit.

### D8. The Eq. (9) sentence is now nearly false in the other direction

main.tex:247: "The current archive contains the executable project structure;
recording all elements of `E` is a concrete extension needed for artifact-level
reproducibility."

`experiments/manifest.py` records five of six fields plus two checksums. The
sentence should claim what is true and disclose the `P₀` gap (A1) and the
checksum defects (A2, A3) rather than under-claim the whole thing.

---

## E. Named constants

### E1. `PegStabilityHook`'s fee bounds are named `_BPS` and hold pips

`contracts/src/PegStabilityHook.sol:72-73`

```solidity
uint24 public MAX_FEE_BPS = 10000; // 1% max fee allowed, 1% = 10_000
uint24 public MIN_FEE_BPS = 100;   // 0.01% mix fee allowed
```

The **values are correct** — 10000 pips = 100 bps = design §4.5's ceiling, 100
pips = 1 bp = its floor — and the percent comments are correct. Only the
identifiers lie. In the same repository `MEVChargeHook.config.feeMax` genuinely
_is_ in bps (§B2). Two fields whose names differ by one word and whose units
differ by 100× is exactly the hazard `CLAUDE.md` names. **Impact: neither today;
rename or comment before someone reads the name and not the value.**

### E2. `DAHook.FSTEP`'s comment is wrong, and has been since 2026-08-03

`contracts/src/DAHook.sol:24` `uint24 private FSTEP = 100; // 5 bps, 0.01%` —
100 pips is **1 bp**. Recorded in PROGRESS as known; still wrong in the source.
`BAHook.sol:35` `FSTEP = 500; // 5 bps` is correct. **Impact: neither**, but it
is a fee-unit comment in the artifact the paper exports for readers.

### E3. Design §5 says PegStability runs at κ = 1; the code runs 0.5, and κ = 1 is provably inert

**Spec.** Design §5 table: "`PegStabilityHook` | pool deviation from the
external price | capture (κ=1)".

**Code.** `PegStabilityHook.sol:70`
`uint256 public captureShare = 500_000; // 50%`, with a proof at lines 59-68
that κ = 1 makes the no-arbitrage band exactly contain the pool price ("with p =
P(1+d) and f = d … (1+d)(1-d) < 1 … measured as zero trades under every gas
price and pool depth").

**Verdict: the spec is wrong; the code is right.** Corroborated by the
`captureShare` sweep: at 0.90 one probe traded zero times and the level loses
significantly in low volatility. **Impact: a published number** — the sweep
figure is in `paper/Image/`.

### E4. `gas_estimates.json` and PROGRESS's gas table disagree on every policy

| policy           | `experiments/gas_estimates.json` | PROGRESS table |
| ---------------- | -------------------------------: | -------------: |
| `BAHook`         |                          107,847 |        124,312 |
| `VolatilityHook` |                          127,508 |        126,502 |
| `PegCapture`     |                          104,335 |        104,368 |
| `PegDefence`     |                          100,713 |        100,861 |
| `MEVChargeHook`  |                           94,739 |         93,006 |
| `ABHook`         |                           93,842 |         93,838 |
| `DAHook`         |                           87,970 |         88,561 |
| `MyHook@*`       |         76,268 / 76,705 / 76,786 |        ~76,500 |

The JSON is what the matrix reads (`matrix.manifest_for:238`, `run_spec:300`)
and is post-recalibration; the table is pre-. `MyHook@10000` is absent from the
JSON and correctly falls back to `DEFAULT_GAS_ESTIMATE = 76_578`.

**Verdict: PROGRESS is stale; the code is right.** **Impact: a published
number** if anyone quotes the table — gas overhead per policy is on the paper's
own list of what a controlled study must report (main.tex:320).

### E5. Constants that are consistent everywhere

- **Basket, 20,000,000 USDT**: `matrix.py:24`, `run_one.py:33` and `:95`,
  `Replay.t.sol:295`, UU design §3, UU prereg, κ prereg. Three independent
  literals, no single source, but all agree.
- **Window counts, 24/tercile = 72/pair**: `matrix.py:37`, 2026-08-04 prereg, UU
  prereg, notebooks 01 and 02 (both now say 72; the apparent stale hits in the
  `.ipynb` files are the substring "2024 per pair"). Stale only at
  `RUNNING.md:142` ("the 24 windows per pair") and design §7.3, the latter
  correctly superseded by the prereg rather than edited.
- **Gas scenarios, 5/20/80 gwei**: design §8 ↔ `matrix.py:64`.
- **Calibration year, 2024**: design §7.2 ↔ `run_one.py:31-32`
  (1704067200000–1735689600000 = 2024-01-01T00:00Z to 2025-01-01T00:00Z), and
  `matrix.load_segments:175` uses the same two literals (duplicated, not
  shared).
- **λ**: design §2.1's ln(2)/0.003 ≈ 231.05 ↔ prereg's
  `231_049_060_186_648_440_000` WAD ↔ `uu.py:24` ↔ `Replay.t.sol:143` default.
- **κ(ETH/SHIB)**: prereg's `0.05517408261312724` reproduced **exactly** in the
  manifests on disk. κ(USDC/USDT) = 0.02392190008355103 and κ(ETH/USDC) =
  0.025528390566767624, both computed by the same rule at run time as the prereg
  says.
- **Static levels**: design §4.4's 5/30/60/100 bps ↔
  `policies.BASELINE_FEES_PIPS = (500, 3000, 6000, 10000)`.
- **Fee box [1, 100] bps**: design §4.5 ↔ `F_MIN = 100` / `MAX_FEE = 10000` on
  BAHook, DAHook and VolatilityHook; ABHook's narrower `[100, 5900]` is correct
  and documented (`ABHook.sol:38-43`) because the constant sum `K = 6000` binds
  before any ceiling.

---

## F. Orphans in both directions

**Spec requires, no code implements**

1. The λ sweep (B6). The only one.
2. Discrete-mode robustness (design §2.4) is implemented (`uu.py:110-125`,
   `Replay.t.sol:449`) and unrun — which §2.4 explicitly permits ("Implemented
   and tested now; executed later, time permitting").

**Code does, no spec authorises**

3. `MEVChargeHookFixed`. Design §13: "Policy logic is not changed — otherwise
   this ceases to be an evaluation of the existing framework", and decision 3:
   "No policy is invented; a policy is built only where the paper already claims
   it." `MEVChargeHookFixed` overrides `_impactRatioBps` to divide by the
   reserve of the token actually paid in — a policy-logic change. It is
   defensible: the shipped template runs unchanged beside it, and the fix
   corrects a dimensional error rather than tuning a parameter. But **no spec
   section authorises it** and the paper has no row for it. Needs a paragraph in
   the design spec and a row in `tab:hooks`.

**Every other policy traces to a paper claim.** `BAHook`, `DAHook`, `ABHook`,
the MEV-charge template and the peg-stability template are `tab:hooks` rows.
`VolatilityHook` traces to main.tex:56 and 212 via design §6, which was written
for exactly that reason. The four `MyHook@*` static levels answer the paper's
own main.tex:301 ("no same-trace fixed-fee baseline"). **No unauthorised policy
was found in `experiments/policies.py`.**

---

## Traced end-to-end and found CONSISTENT

Each of these was followed from the spec sentence to the line that implements
it. No disagreement.

**UU flow design, §2 through §7**

- §2 two-branch model `P = 1 if r ≥ 0 else exp(−λ|r|)` →
  `UUMath.participationWad:129-135`.
- §2.2 `r` per direction, γ = 1 − f → `UUMath.rWad:95-122`. The direction swap
  is the `(num, den)` tuple at line 119; γ is folded as `gammaPips * 1e12`
  before a single `mulDiv`, which is the exact scaling the 2026-08-09
  adversarial review demanded.
- §2.2 slippage dropped (marginal price) → `rWad` takes no size argument.
- §2.3 deterministic thinning `v_d = v₀/2 · P(r_d)` → `uu.py:101`
  (`v_half = v * kappa / 2`) and `Replay.t.sol:449`
  (`FullMath.mulDiv(sizeWad, p, 1e18)`).
- §3 κ rule (mean daily UU volume over 2024 = one basket) → `uu.kappa:63-67`,
  `run_one.kappa_for_pair:56-82`, cached per pair, calibration year pinned as a
  constant and explicitly _not_ the window's own candles. The one-leg profile
  for USDC/USDT is the identity branch at `uu.py:48-50`, matching §3's
  parenthetical. κ recorded in every manifest, values verified above.
- §3 input amounts `v_AB/P0`, `v_BA/P1` → `Replay.t.sol:420` and `:453`.
- §4 candle order **update feeds → UU A→B → UU B→A → arbitrage** →
  `Replay.t.sol:353-358`: `_setFeeds(i)`, then `_uuStep(i)` whose loop runs
  `side == 0` (zeroForOne, A→B) before `side == 1`, then `_step(i)`. Correct, in
  that order, and the same order in the gas-guard path at lines 337-341.
- §4 UU swaps from fresh addresses, persistent/fresh axis arbitrageur-only →
  `_uuSender:462-464` (keyed on candle **and** direction) vs `_sender:561-563`.
- §4 UU runs during warm-up, metrics start at the boundary →
  `_captureBaseline(i)` at line 356 executes before `_uuStep`, and both
  `_executeUU:499` and `_executeArb:683` skip logging while
  `candle < warmupCandles`.
- §4 a UU swap rounding to zero is skipped, not logged → three guards, lines
  415, 450, 454.
- §4.1 `expNegWad` restricted to x ≤ 0, solady port with attribution and the
  dropped overflow branch documented → `UUMath.sol:30-86`.
- §5 event schema: `trader` plus WAD-scaled `r`/`P` → `Replay.t.sol:537-540` and
  `events.py:46-56`. Named `rWad`/`pWad`; pre-UU traces parse with `"arb"`/0
  defaults (`events.py:79-80, 103-116`), which is what lets the frozen arb-only
  traces keep working.
- §6 every metric: `net_result` unchanged (`metrics.py:228`);
  `net_result_tt = −Σ(Δ0·P0_t + Δ1·P1_t)` in exact integer arithmetic
  (`metrics.py:91-106, 247`); `arb_profit` → `arb_mtm` (line 241);
  `arb_profit_realized` with the all-zero-`extPriceGas` missing-data sentinel
  scoped to arb rows (267-277); `uu_fee_share` (285-287); `uu_participation` as
  a volume-weighted mean P (292-297); conservation unchanged in form and still
  summing over both trader kinds (200-219).
- §7 the clamp itself (see B2).

**2026-08-02 design**

- §4.4 four static levels; §4.5 the shared fee box; §7.2 the three pairs and
  their feeds including `CONSTANT_ONE`; §7.3 one-day windows and tercile
  stratification; §7.4 the 60-candle warm-up (`run_one.py:96`,
  `Replay.t.sol:127`); §8 the three gas scenarios and the 21,000 intrinsic gas
  added analytically (`policies.INTRINSIC_GAS`).
- §12.1 test machinery, all of it: two-sided Wilcoxon with tie discard and
  `n_effective` reported (`stats.py:47-67`); Benjamini–Hochberg as a step-up
  with everything below the largest passing rank accepted (`stats.py:71-96`);
  the baseline named rather than inferred (`aggregate.py:18`); pairing per
  window on all four non-policy axes (`aggregate.py:20, 118-123`); an effect
  size beside every significance flag. The two defects in §12.1's _application_
  are C1 and C2 above — the machinery itself is right.
- §11 "Solidity executes, Python computes" — `Replay.t.sol` derives nothing;
  every metric is computed in `metrics.py` from the JSONL.

**2026-08-04 power extension**

- "Only the number of windows" changes: `matrix.WINDOWS_PER_TERCILE = 24`, the
  selection rule (`windows.select_windows`) untouched, `per_tercile` the only
  moving argument. Family, test, baseline and quantity unchanged in the code.

**2026-08-10 κ sensitivity**

`kappa_sensitivity.py` matches its pre-registration on every checkable point:
grid `{0.03, 0.1, 0.3, 1.0, 3.0}` (line 51); the six named configurations
(57-64); 8 windows per tercile (69); ETH/SHIB only (42); λ, basket, gas
scenarios and `MyHook@3000` baseline held fixed; `address_mode` left at
`run_one`'s `persistent` default; per-level trace subdirectories (85-86) for the
reason the prereg gives; both valuations with a **separate BH family each**
(226, 250-253); outputs to `results/sensitivity/kappa.csv` and
`kappa_tests.csv`; 1.0 re-run inside the sweep rather than joined in. Cell count
6 × 5 × 24 × 3 = 2,160 matches. One deviation, C3.

**The 2026-08-10 trace-directory fix, both halves**

`results_dir` is threaded `execute_parallel:432-434` → `_worker:322-334` →
`run_spec:306` → `run_one`, **and** `contracts/foundry.toml:10-13` allowlists
`../results-uu/`. Both were needed; one alone fails.

**Manifest resume semantics**

`source_hash` covers `src/` **and** `test/` (`manifest.py:101-106`), and
`manifest_for` omits the five UU fields entirely when `uu_mode == "off"`
(`matrix.py:242`), so an arb-only manifest can never match a UU one. The
`@cache` on `_submodule_revisions_cached` returns an immutable tuple for the
documented reason.

---

## What the paper needs — a work list

Ordered by how much of the paper each one moves. Nobody has written any of this.

1. **Rewrite §IV and the abstract around three experiments, not one prototype
   trace.** The arb-only 8-per-tercile run, the arb-only 72-window matrix, and
   the UU matrix. Retire "1,492 simulated swaps" from the abstract (line 31),
   §IV-B (290, 292) and the conclusion (326) — the number is unreproducible from
   this repository. Decide whether `paper/Image/dynamic_fee_reaction.pdf`
   survives; if it does, it needs a notebook and a CSV like every other figure,
   and its axis relabelled from bps to pips (D7).
2. **Move the claim boundary, in the words the UU prereg already fixed:** from
   "engineering feasibility" to "a controlled comparison under a synthetic
   two-flow model". Keep the negative results — ABHook loses its own litmus,
   `PegDefence` is a de-facto static 1 bps under arbitrage-only flow,
   `VolatilityHook` is not volatility-responsive at the shipped coefficient.
3. **Rewrite the §IV-B "what is missing" list (line 301).** Baseline, repeated
   windows, uncertainty intervals and gas all now exist (D5). What genuinely
   remains missing: the λ sweep (B6), the κ sweep (unrun), the discrete-mode
   appendix, live-oracle behaviour, and mempool microstructure.
4. **Rebuild `tab:hooks`** with a volatility row, `MEVChargeHookFixed`,
   `PegDefence`/`PegCapture` as two readings, and the static baselines (D1).
   **Fix the `ABHook` row: per-trade, pool-price signal, no oracle** (D2).
5. **Fix the volatility text in two places.** Line 212: "price variability", not
   "trade volume variance" (D3). Line 56: EWMA of the price-ratio change
   computes the fee; Welford is retained as the reported diagnostic (D4). Add
   the coefficient caveat.
6. **Cut or downgrade the unimplemented application-layer claims** (D6): Go
   integration tests, Playwright e2e, and the PostgreSQL history have no code.
   Say what exists (`dex/web_interface/app.py`, the export path) and mark the
   rest as intended work. Decide the fate of `dex/` first — Figures 2, 3, 4 and
   `Simulation.t.sol` live there.
7. **Rewrite the Eq. (9) paragraph (line 247)** to claim what `manifest.py`
   actually records, and disclose the `P₀` gap and the two constant checksums
   (A1–A3) — or fix them first, which is cheaper than writing the caveat.
8. **Add a reproducibility note** covering: the mixed field-`D` state of
   `results-uu/` (A5); the MEVChargeHook clamp and that its rows are **not**
   comparable across the arb-only and UU matrices; the `_feeForSender` modelling
   choice (B1); the trade-time valuation's post-hoc motivation, which the UU
   prereg requires be stated.
9. **Report the distinct comparison count, not the address-duplicated one**
   (C2), and report both co-primary valuations side by side wherever a
   significance count appears (C1).
10. **Correct §III-A's "Anvil provides the local EVM"** and the
    `Simulation.t.sol` reference — the replay is `contracts/test/Replay.t.sol`
    under Foundry's EVM (D7).

Two non-paper items that gate the above: **B3** (`FEE_BOXES_BPS` must be
corrected before any UU fee-behaviour number is quoted) and **C1** (the runner
must emit both valuations). Neither is a paper edit, but both change numbers the
paper would print.
