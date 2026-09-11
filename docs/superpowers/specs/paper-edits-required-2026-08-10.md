> **SUPERSEDED 2026-08-12.** Every number in this document comes from runs
> withdrawn by the gas-denomination revision of 2026-08-12 (see
> `docs/reports/2026-08-12-framework-report.md` §11). Do NOT apply these edits
> as written. The current edit list is `paper-edits-required-2026-08-12.md`;
> current citable numbers live in the report and in the CSVs beside each figure
> in `paper/Image/`.

# Paper edits required — work list, 2026-08-10

Target: `paper/main.tex`, IEEE ICBC 2026, deadline 2026-08-18. **This document
changes nothing.** `paper/` was read only; every edit below is for the owner to
apply by hand.

Sources: `paper/main.tex` (330 lines, unmodified since 2026-08-02),
`docs/superpowers/specs/REVIEW-traceability-2026-08-10.md`,
`docs/superpowers/specs/REVIEW-specs-2026-08-10.md`,
`docs/superpowers/plans/PROGRESS.md`, and the five specs. The current model of
record is `2026-08-10-r-correction-preregistration.md`; everything it supersedes
is marked as such below.

**State at the time of writing.** The corrected matrix
(`results-uu/run-corrected-r.log`, 15,552 cells) was at cell 200 of 15,552. No
number it will produce exists yet. Replacement text that needs such a number
carries a `<<placeholder>>`; Section C lists every one of them.

Ordering: **A** claims that are false as printed, **B** claims that are
unsupported, **C** numbers that must be re-checked, **D** wording, units and
notation, **E** the do-not-claim list. Within A and B, heaviest first.

Sections of the paper that need no work: §I paragraphs 1–4 (lines 41–47), §II-A
(lines 66–92), §II-C (lines 124–128), §III-B (lines 167–192), §V-A (lines
306–312), Table I (`tab:relatedwork`) except for the one row noted in D9.

---

## A. False as printed

### A1. `tab:hooks`, the `ABHook` row — both of its claims are wrong

**Where.** `main.tex:227`, inside `tab:hooks`.

**Current text.**

```latex
\texttt{ABHook} & Block-level & External ratio with asymmetric response & Demonstrates distinct fees by swap direction\\
```

**What is wrong.** Two independent errors in one row.

1. **Granularity.** `contracts/src/ABHook.sol` `_afterSwap` (lines 124–165) has
   no `block.number` gate. It updates on **every swap**. Compare
   `BAHook.sol:155` (`if (block.number > lastBlock[poolId])`) and
   `VolatilityHook.sol:159` (`if (block.number <= lastBlock[poolId]) return`),
   which do gate. Verified by grep: `block.number` does not appear anywhere in
   `ABHook.sol`.
2. **Signal.** It reads the **pool** price, not an oracle: `ABHook.sol:132`
   `(uint160 currentSqrtPriceX96,,,) = _poolManager.getSlot0(poolId);`. The
   constructor at line 65 takes two `AggregatorV2V3Interface` parameters and
   **discards them — both are unnamed** and no feed is ever read.

**Replacement text.**

```latex
\texttt{ABHook} & Individual trade & Pool-price change; constant fee sum across the two directions (no external feed) & Demonstrates reallocation of a fixed fee budget between swap directions\\
```

**Why this one matters most.** `ABHook` vs static 30 bps is the litmus
comparison the paper singles out (design §12.1, decision 7). Describing it as
oracle-informed and block-level misstates what the litmus tests: it isolates
**allocation of a fixed fee budget across directions from a pool-price signal**,
with no external data at all. The design spec §5 has it right — "`ABHook` | pool
price change, constant fee sum | reallocation" — so the paper is the only
document that is wrong. `CLAUDE.md` repeats the paper's version and is wrong
too; fix it in the same pass.

**Footnote worth adding.** `ABHook`'s effective per-direction fee box is **[1,
59] bps**, not the shared [1, 100] bps, because the constant sum `K = 6000` pips
binds before the shared ceiling: one side reaches 5900 only by pinning the other
to the 100-pip floor (`ABHook.sol:38-43`).

---

### A2. `tab:hooks` lists five templates; twelve configurations were run

**Where.** `main.tex:216-232`, the whole `tab:hooks` float, and the sentence
introducing it at `main.tex:214`.

**Current text (the table body).** Five rows: `BAHook`, `DAHook`, `ABHook`,
"MEV-charge hook", "Peg-stability hook".

**What is wrong.** Four separate gaps:

- **No volatility row**, although the paper claims a volatility template twice
  (lines 56 and 212). `VolatilityHook` **did not exist in the artifact the paper
  describes**: design §6 records "the paper twice claims an implementation of
  EMA and Welford's algorithm (lines 56 and 212). Neither appears in the code —
  not in any of the nine branches, not in any commit in history." Confirmed: no
  Solidity file under `dex/src/` mentions volatility or Welford;
  `contracts/src/VolatilityHook.sol` and `contracts/src/libraries/Welford.sol`
  were written for this study.
- **The peg-stability template is run in two distinct readings**, `PegDefence`
  and `PegCapture`, which differ in mechanism and not in parameters (design §5).
  One row cannot represent both.
- **`MEVChargeHookFixed` has no row.** It is a corrected variant **authored in
  this work**, not part of the evaluated artifact: it overrides
  `_impactRatioBps` to divide by the reserve of the token actually paid in. That
  is a policy-logic change and no design section authorises it (traceability F3,
  specs C2).
- **The four static baselines have no row**, although they are what makes every
  comparison in the paper possible.

**Replacement text.** Replace the whole table body. Retitle the caption to "Fee
configurations under test" — the table is no longer only an inventory of
templates.

```latex
\begin{table*}[t]
  \caption{Fee configurations under test. Twelve configurations over eight contract templates.}
  \label{tab:hooks}
  \centering
  \footnotesize
  \begin{tabular}{p{2.6cm}p{2.4cm}p{4.6cm}p{5.4cm}}
    \toprule
    \textbf{Configuration} & \textbf{Update granularity} & \textbf{Primary signal or condition} & \textbf{Role in the study}\\
    \midrule
    \texttt{MyHook} at 5, 30, 60, 100~bps & Constant & None & Static baselines; 30~bps is the pre-registered comparator\\
    \texttt{BAHook} & At most once per block & Change in an external token-price ratio (two feeds) & Block-adaptive directional fee\\
    \texttt{DAHook} & Individual trade & Direction of the previous trade; no external feed & Transaction-level adaptation\\
    \texttt{ABHook} & Individual trade & Pool-price change; constant fee sum $K$ (mean 30~bps) & Reallocation of a fixed budget across directions\\
    \texttt{PegDefence} & Individual trade & Deviation from the reference, charged on trades moving the pool away & Peg-defence reading of the peg template\\
    \texttt{PegCapture} & Individual trade & Magnitude of the deviation, scaled by \texttt{captureShare}~$=0.5$ & Capture reading of the same template\\
    \texttt{MEVChargeHook} & Individual trade, size-dependent & Per-address history and trade size & MEV-oriented template as shipped\\
    \texttt{MEVChargeHookFixed} & Individual trade, size-dependent & As above with a dimensionless impact measure & Corrected variant authored here, not part of the evaluated artifact\\
    \texttt{VolatilityHook} & At most once per block & Exponentially weighted variance of the change in the external token-price ratio & Volatility template authored here to instantiate the claim of Sec.~\ref{sec:framework}\\
    \bottomrule
  \end{tabular}
\end{table*}
```

**Sentence to add after the table** (replacing nothing; it goes after the
existing caveat paragraph at `main.tex:214`):

> Two of the twelve configurations were authored for this study rather than
> taken from the evaluated artifact. `VolatilityHook` instantiates the
> volatility template the framework describes but did not implement.
> `MEVChargeHookFixed` corrects a dimensional error in the shipped MEV
> template's impact measure; the shipped template is run unchanged beside it,
> and both are reported.

**Evidence.** `experiments/policies.py:27-49` names all twelve;
`12 × 3 pairs × 72 windows × 3 gas × 2 address modes = 15,552` cells, which is
the matrix size in the log.

---

### A3. "trade volume variance" is wrong, and the paper contradicts itself

**Where.** `main.tex:212`, last clause.

**Current text.**

> The library exposes specific policy templates, including a block-adaptive hook
> (\texttt{BAHook}) that adjusts fees based on external price ratio changes, a
> deal-adaptive hook (\texttt{DAHook}) for transaction-level updates, and
> volatility-based hooks utilizing Exponential Moving Average (EMA) and
> Welford’s online algorithm to react to **trade volume variance**.

**What is wrong.** No trade volume enters the hook anywhere.
`VolatilityHook.sol` `_getPriceRatio()` (lines 97–102) reads the two
Chainlink-compatible feeds; line 169 forms the relative change of that ratio;
lines 177–178 square it; line 182 feeds the exponentially weighted variance. The
paper says the correct thing 116 lines earlier — `main.tex:96`,
"Volatility-based mechanisms react to price variability" — so this is an
internal contradiction as well as a factual error.

**Replacement text.**

> The library exposes specific policy templates: a block-adaptive hook
> (\texttt{BAHook}) that adjusts fees from changes in an external token-price
> ratio; a deal-adaptive hook (\texttt{DAHook}) that updates per transaction
> from the direction of the previous trade; an asymmetric hook (\texttt{ABHook})
> that reallocates a constant fee budget between swap directions from the pool
> price; and a volatility hook (\texttt{VolatilityHook}) whose fee scales with
> an exponentially weighted variance of the change in the external token-price
> ratio. Welford's online algorithm is implemented and reported as a diagnostic;
> it does not compute the fee.

---

### A4. The contributions bullet overclaims Welford

**Where.** `main.tex:56`, second bullet of the contributions list.

**Current text.**

> \item Configurable templates spanning block- and trade-adaptive behaviors,
> specifically implementing Exponential Moving Average (EMA) and Welford’s
> online algorithm **for variance-based fee calculation**, alongside
> MEV-oriented and peg-stability policies.

**What is wrong.** Welford has not computed the fee since 2026-08-03.
`VolatilityHook.sol:171-175` carries the comment verbatim:

```solidity
// Kept for the reported diagnostic and its own tests; the fee no
// longer depends on it.
Welford.State memory s = _stats[poolId];
```

The fee reads `emaVariance` (lines 180–187). The reason is a measured defect,
not a preference: a cumulative variance moves by `O(1/n)` and freezes — measured
fee range 8 → 5 → 3 → 1 → **0** pips across successive fifths of one window,
total range 0.17 bps. The fixed-horizon EWMA is the correction. Design §6 still
specifies the Welford form and is stale too.

**Replacement text.**

> \item Configurable templates spanning block- and trade-adaptive behaviours,
> including a volatility template whose fee scales with an exponentially
> weighted variance of the external price-ratio change, with Welford's online
> algorithm implemented and reported as a diagnostic, alongside asymmetric,
> MEV-oriented, and peg-stability policies.

**Companion caveat, required wherever the volatility template's behaviour is
reported.** Even after the fix the policy is **not volatility-responsive at the
shipped coefficient**: measured fee spread `<<vol-spread>>` bps around a
`<<vol-median>>` bps median across the matrix. At `coefficient = 20000` the
volatility term contributes about 45 pips of a 545-pip fee; making it
meaningfully responsive would need a coefficient perhaps two orders of magnitude
larger, which is a parameter choice and was deliberately not made. Say this
rather than claim the mechanism works. (The 2026-08-09 measurement was 0.35 bps
around 5.1 bps; it comes from the withdrawn matrix — see C8.)

---

### A5. §IV-B's list of what is missing is now false in five of six items

**Where.** `main.tex:301`.

**Current text.**

> The execution verifies the integration path: configure a hook, deploy local
> contracts, inject observations, execute swaps, collect contract output, and
> render results. It does not establish economic superiority. **The artifact
> provides no same-trace fixed-fee baseline, repeated trials, uncertainty
> intervals, gas measurements, or complete specification of trade sizing and
> data cleaning.** Accordingly, the paper claims feasibility rather than reduced
> LP loss.

**What is wrong.** Everything on that list except one item now exists:

| Claimed missing               | Now on disk                                                                        |
| ----------------------------- | ---------------------------------------------------------------------------------- |
| same-trace fixed-fee baseline | `policies.BASELINE_FEES_PIPS = (500, 3000, 6000, 10000)`, run on identical windows |
| repeated trials               | 72 windows/pair × 3 pairs × 3 gas scenarios × 2 address modes                      |
| gas measurements              | `experiments/gas_estimates.json`, per policy, plus a three-level gas axis          |
| trade-sizing specification    | design Appendix A, `ArbMath`, `_optimalSize`                                       |
| data cleaning                 | window selection and tercile stratification, `experiments/windows.py`              |
| **uncertainty intervals**     | **still missing** — see below                                                      |

**The one item that survives, in corrected form.** No confidence or credible
interval is computed anywhere. `experiments/stats.py` defines exactly three
functions — `wilcoxon_paired`, `benjamini_hochberg`, `analyse` — and no
bootstrap, no interval. What is reported is a paired median, a win rate,
`n_effective`, a two-sided p-value and an FDR verdict. That is not an
uncertainty interval and the paper must not upgrade it into one.

**Replacement text.**

> The execution verifies the integration path and, on that substrate, supports a
> controlled comparison: configure a hook, deploy local contracts, inject
> observations, execute swaps, collect contract output, and analyse the result.
> A same-trace static-fee baseline, repeated windows, per-policy gas
> measurements, and an explicit trade-sizing rule are all present. What remains
> outside the study is: interval estimates of effect size (only paired medians,
> win rates, effective sample sizes and FDR-controlled $p$-values are reported);
> the $\lambda$ and $\kappa$ sensitivity sweeps of the flow model; unbalanced
> uninformed flow; live-oracle timing and fault behaviour; and mempool
> microstructure. Accordingly the paper claims a controlled comparison under a
> declared synthetic flow model, not a general economic ranking.

---

### A6. Three of the five application-layer artifacts the paper claims do not exist

**Where.** `main.tex:256` (§III-D, last paragraph) and `main.tex:260` (§III-E).

**Current text, `main.tex:256`.**

> To ensure strict reproducibility and auditability, the framework's off-chain
> layer utilizes a relational database (e.g., \texttt{PostgreSQL}) to maintain a
> complete history of parameter changes (\texttt{HookParamsHistory}), indexed
> blockchain events (\texttt{ChainEvent}), and pool state snapshots
> (\texttt{PoolStateSnapshot}).

**Current text, `main.tex:260`.**

> Second, backend integration tests (in Go) validate the API layer, database
> state transitions, and historical data ingestion. Finally, end-to-end (e2e)
> tests (e.g., via Playwright) verify the complete user workflow…

**What is wrong.**

- **Go:** no `.go` file anywhere in the tree.
- **Playwright:** no configuration, no test, no dependency in `pyproject.toml`
  or `package.json`.
- **PostgreSQL and the three models:** no match anywhere in code; the only
  occurrences are Russian-language prose in `dex/test.md`.
- What does exist: the Flask app at `dex/web_interface/app.py`, and the export
  path. Both live inside `dex/`, which PROGRESS lists as redundant and proposed
  for deletion.

**Replacement text for `main.tex:256`.**

> Off-chain reproducibility is currently carried by the per-run manifest of
> Eq.~\eqref{eq:manifest} and by immutable result files, not by a database. A
> relational history of parameter changes, indexed chain events, and pool-state
> snapshots is a designed extension of the application layer and is not part of
> the evaluated artifact.

**Replacement text for `main.tex:260` (§III-E).**

> Testing is organised across the layers that exist. Smart-contract tests under
> Foundry verify fee direction, bounds, update granularity, and edge values for
> each hook, together with deployment permissions and the replay path; the
> Python harness is covered by its own unit and golden tests, including a
> differential golden that pins byte-for-byte reproduction of a reference
> window. Integration tests for a persistent API layer and end-to-end browser
> tests of the configurator are designed but not implemented; they are stated
> here as intended work, not as evidence.

**Decide `dex/` first.** Figures 2, 3 and 4 (`hook_configurator.png`,
`parameterized_code.png`, `generated_project.png`) and `Simulation.t.sol` all
live there. Deleting `dex/` removes the artifact behind the two
application-layer claims that are true. `CLAUDE.md` already flags the Go/Flask
inconsistency as something to "resolve against the actual paper sources"; the
answer is that Go does not exist.

---

### A7. "Anvil provides the local EVM" and the `Simulation.t.sol` reference

**Where.** `main.tex:135`, twice in the same paragraph.

**Current text.**

> The \emph{experiment layer} combines Forge tests, \texttt{Simulation.t.sol},
> data utilities, and the result parser to replay observations…
>
> …Foundry supplies Solidity-native compilation, tests, and scripts, while
> **Anvil provides the local EVM}~\cite{foundryBook,anvilBook}.

**What is wrong.** The replay is a Forge test executed in Foundry's own EVM;
Anvil is never started by the experiment path. Flagged in design §15 on
2026-08-02 and unchanged since. `Simulation.t.sol` is the `dex/` prototype's
harness; the harness that produced every number in the paper is
`contracts/test/Replay.t.sol`.

**Replacement text.**

> The \emph{experiment layer} combines Forge tests, the replay harness
> \texttt{Replay.t.sol}, data utilities, and the result parser to replay
> observations and record price, volume, fees, holdings, and LP metrics.
>
> …Foundry supplies Solidity-native compilation, tests, and scripts and executes
> the replay in its own EVM; Anvil provides the local node used by the
> deployment and export path~\cite{foundryBook,anvilBook}.

---

### A8. Fig. 5's axis is mislabelled by a factor of 100, and the figure's causal claim is not supported

**Where.** `main.tex:292` (the paragraph) and `main.tex:297` (the caption).

**Current text, caption.**

> \textbf{(Bottom)} The resulting dynamic fee parameter (in **basis points**),
> demonstrating how the policy scales the fee in response to underlying market
> volatility.

**Current text, paragraph (the load-bearing sentence).**

> …as the price ratio exhibits higher variance, the hook scales the fee upward
> from the base rate, directly reflecting the calculated market volatility while
> respecting the configured bounds.

**What is wrong.** Two things.

1. **Units.** Design §15 records the axis as carrying values of 3000–3200.
   Uniswap v4's `uint24` counts hundredths of a basis point, so 3000 is 30 bps.
   The axis is in pips and is labelled bps — a factor of 100, in a paper whose
   §III-B (`main.tex:183`) states the unit correctly.
2. **The claim.** "The hook scales the fee upward … directly reflecting the
   calculated market volatility" is the exact statement the measured behaviour
   contradicts: at the shipped coefficient the volatility template moves the fee
   by a fraction of a basis point (A4). The figure is also unreproducible — it
   has no CSV table view and no notebook that draws it, unlike all 25 figures
   the current pipeline produces (mtime 2026-08-02 14:43).

**Recommendation.** Drop `dynamic_fee_reaction.pdf` and replace it with a figure
drawn by the current pipeline from the corrected matrix. If it is kept, it needs
a notebook, a CSV, a relabelled axis, and a caption that claims only that the
fee moves with the signal — not that the movement is economically meaningful.

**Replacement caption, if kept.**

> Core mechanism of the dynamic-fee hook. \textbf{(Top)} External price ratio
> (SHIB/ETH). \textbf{(Bottom)} The resulting LP fee, in hundredths of a basis
> point as Uniswap v4 encodes it. The panel shows that the policy responds to
> the signal within its configured bounds; the magnitude of the response is
> reported in Sec.~\ref{sec:evaluation} and is small at the shipped coefficient.

---

### A9. The Eq. (9) paragraph is wrong in both directions

**Where.** `main.tex:247`, and the related sentence at `main.tex:270`.

**Current text, `main.tex:247`.**

> The current archive contains the executable project structure; recording all
> elements of $E$ is a concrete extension needed for artifact-level
> reproducibility.

**What is wrong.** It under-claims and, if repaired naively, would over-claim.
`experiments/manifest.py` records five of six fields plus two checksums — but
until 2026-08-10 two of those were dead:

- **`P0` was literally `null`** in every manifest of both earlier matrices.
  `experiments/matrix.py:264` passed `p0_sqrt_price_x96=None` and
  `manifest.py:138` wrote it through. Verified on disk: `"P0": null` in every
  manifest sampled from `results/matrix/` and `results-uu/matrix/`.
- **`input_checksum` was the same value for all 15,552 cells and described none
  of them.** `matrix.py:234` hashed `<root>/data/`, while each cell writes its
  candles to `.work/<key>/`. 400 sampled UU manifests all carried
  `"input_checksum": "d3b98a44090795fd"`. The field could not detect the silent
  data change it exists to detect. `uu_trace_checksum` had the same defect
  (`bb88b1f75c40122b` across all 400).

Both were fixed on 2026-08-10 — `run_one.window_fingerprint` now hashes the
window's own aligned candles and returns the opening external prices with them —
so **only the currently running corrected matrix carries closed manifests.** The
two frozen arb-only experiments and the withdrawn UU matrix do not.

Additionally, **neither sensitivity driver writes a manifest at all**:
`experiments/sensitivity.py` (`captureShare`, 504 cells) and
`experiments/kappa_sensitivity.py` (2,160 cells) call `run_one` directly and
never touch `build_manifest`. `paper/Image/capture_share_sensitivity.pdf` is
therefore a published figure with no recorded `E`.

**Replacement text for `main.tex:247`.**

> Every run of the comparison in Sec.~~\ref{sec:evaluation} writes this manifest
> alongside its results: the configured contract and a hash of the framework's
> own Solidity sources, the pinned submodule and compiler revisions, the initial
> pool price and liquidity, a fingerprint of the exact market-data window, and
> the swap-generation configuration. The manifest is what the resume logic
> compares, so a change to any recorded element forces re-execution rather than
> silently mixing two experiments. Two caveats belong with it, and are stated in
> Sec.~~\ref{sec:discussion}: the initial price and the input fingerprint were
> only added late in the study, so results produced before that point close five
> of six fields rather than six; and the sensitivity sweeps reported as
> robustness analyses are driven by a separate path that writes no manifest.

**Related, `main.tex:270`** — "The manifest in Eq.~\eqref{eq:manifest} provides
the core identifier, while an input checksum and event-level output would make
exact comparison practical." Both now exist (the window fingerprint, and the
per-swap JSONL event log). Rewrite to say so, and keep the caveat above.

---

## B. Unsupported as printed

### B1. The headline "1,492 simulated swaps" is not reproducible and is superseded

**Where.** Four places: `main.tex:31` (abstract), `main.tex:290`,
`main.tex:292`, `main.tex:326` (conclusion).

**Current text, abstract.**

> A prototype execution over an ETH/SHIB trace processes 1,492 simulated swaps
> and produces external-price, price-ratio, pool-price, volume, fee, and
> liquidity-provider metrics. The evidence establishes end-to-end implementation
> feasibility, not economic superiority over static fees.

**Current text, `main.tex:290`.**

> The supplied execution contains 1,492 simulated swaps. Because the report does
> not identify a volume numeraire, no USD interpretation is assigned to the
> aggregate volume or token-denominated fee income.

**Current text, `main.tex:326`.**

> A 1,492-swap ETH/SHIB trace demonstrates that the integrated workflow
> operates.

**What is wrong.** "1,492" appears **nowhere on disk**. No script, notebook,
spec, result file or figure CSV produces it; the only occurrences in the
repository are `paper/main.tex` (four times) and `CLAUDE.md` quoting the paper.
Its figure has no CSV and no notebook (A8). The number cannot be regenerated,
checked, or defended if a referee asks. Independently of that, three experiments
have now run and one prototype trace is no longer the evidence base.

**Replacement text, abstract (last three sentences).**

> On this substrate we run a pre-registered comparison of twelve fee
> configurations across three token pairs, 72 one-day windows per pair, three
> gas scenarios and two arbitrageur address models, under two order-flow models:
> arbitrage-only, and a synthetic two-flow model that adds a deterministic
> uninformed-user component. Every configuration is compared against a static
> 30~bps baseline on identical windows using paired Wilcoxon signed-rank tests
> under Benjamini--Hochberg control at $q=0.05$, in two co-primary valuations.
> The results are conditional on the assumed participation model and its
> calibrated parameters and are not evidence that a dynamic fee dominates a
> static fee in a live market.

**Replacement text, `main.tex:290`.**

> The comparison comprises `<<n-cells>>` executed cells: twelve fee
> configurations $\times$ three pairs $\times$ 72 one-day windows $\times$ three
> gas scenarios $\times$ two arbitrageur address models. Volumes and fee income
> are reported in USDT at a declared valuation time; token-denominated fee
> amounts are never summed across tokens without one.

**Replacement text, `main.tex:326` (conclusion sentence).**

> A pre-registered comparison over three token pairs and 216 one-day windows,
> under two order-flow models, shows `<<headline>>`.

---

### B2. The claim boundary must move — and its new position must be stated precisely

**Where.** `main.tex:61` (§I closing), `main.tex:98` and `main.tex:100` (§II-B
closing), `main.tex:31` (abstract, covered in B1), `main.tex:326`.

**Current text, `main.tex:61`.**

> The current artifact is evaluated as an engineering prototype. The available
> trace demonstrates that the full workflow executes, but lacks the fixed-fee
> baselines and repeated trials required to claim improved LP performance. This
> boundary is maintained throughout the paper.

**Current text, `main.tex:98`.**

> Our contribution is complementary: a common implementation substrate for
> configuring, deploying, and replaying multiple fee rules as Uniswap v4 hooks.
> **It enables a later controlled economic comparison** while keeping the
> surrounding software path fixed.

**What is wrong.** The boundary is now in the wrong place in both directions.
The fixed-fee baselines and repeated trials exist, so the stated limitation is
false. But the new position is narrower than "economic comparison": UU design §9
fixes it as "a controlled comparison under a synthetic two-flow model", and
`2026-08-10-r-correction-preregistration.md` makes the conditionality sharper —
λ and κ are **calibration choices**, not measurements, and the participation
function is assumed.

**Replacement text, `main.tex:61`.**

> The artifact is evaluated in two ways. As engineering, the workflow executes
> end to end. As an experimental substrate, it supports a controlled comparison
> in which the trace, initial reserves, liquidity, valuation convention, and
> window set are held fixed and only the fee policy varies. That comparison is
> run under a synthetic two-flow order model. Its participation function is
> assumed rather than estimated, and its two scale parameters --- the
> participation sensitivity $\lambda$ and the retail-volume scale $\kappa$ ---
> are calibration choices fixed by declared rules, not quantities measured from
> data. Every economic statement in this paper is conditional on that model and
> those choices, and none of them is a claim about live-market performance. This
> boundary is maintained throughout.

**Replacement text, `main.tex:98` (second sentence).**

> It also carries a controlled comparison of those rules with the surrounding
> software path held fixed, under an order-flow model declared in advance.

**Related, `main.tex:100`** — "a framework without controlled baselines cannot
demonstrate economic benefit" now describes a state the paper has left. Rewrite
so the sentence describes the general principle rather than this artifact's
limitation.

---

### B3. The interior static optimum must not be presented as a finding

**Where.** New text for §IV, wherever the static-fee curve is reported. Nothing
in the current `main.tex` says this yet — this is an edit that must land
**before** any results text is written, because the natural way to write that
text is the indefensible way.

**What is wrong.** Under the model, retail fee revenue per direction is
`f·P(f)`. With `P = exp(−λ|r|)` and `r ≈ −ε/2` at a fair-priced pool (the
corrected, normalised `r`), `argmax_f f·exp(−λf/2) = 2/λ`. At the current λ =
461.404973 that is **43.3 bps**. The existence and approximate location of an
interior optimum are therefore a first-order condition of the functional form
the model assumes and the λ that was chosen — not something the experiment
discovered. The λ-sweep `{58, 116, 231, 462, 924}` moves `2/λ` across and out of
the [1, 100] bps fee box, so it is a sweep **of** the result, not a robustness
check **on** it. Worse for a referee: UU design §10, verification item 5
explicitly licensed retuning λ until the interior optimum appeared ("If it is
still monotone at λ = 231, λ is recalibrated before the matrix runs"). In the
event no retuning was needed, but the rule was written down.

**Replacement text (add to §IV, immediately before the static-fee results).**

> The static-fee curve has an interior optimum, and its existence is a property
> of the model rather than a result. Retail fee revenue per direction is
> $f\,P(f)$; with the assumed participation function $P=\exp(-\lambda|r|)$ and
> $r \approx -f/2$ at a pool sitting on the external price,
> $\arg\max_f f\exp(-\lambda f/2) = 2/\lambda$, which at the calibrated
> $\lambda = 461.40$ is $43.3$~~bps. Table~~\ref{tab:static} prints $2/\lambda$
> beside the measured optimum for this reason. We do not claim that the
> experiment shows an interior optimum to exist; what it contributes here is the
> ranking of policies at a fixed $\lambda$. The $\lambda$-sweep moves
> $2/\lambda$ across and beyond the $[1,100]$~bps fee box, so it varies this
> result rather than testing its robustness, and is reported in those terms.

**Requirement, not optional.** `2/λ` must be printed in the same table as any
measured optimum. Pre-registered in
`2026-08-10-r-correction-preregistration.md`, "Declared in advance", bullet 2.

---

### B4. `net_result` and `net_result_tt` are different functionals, not one quantity under two valuations

**Where.** New text for §IV-A, next to Eq. (10) (`main.tex:280-284`). The
existing IL/`L_net` pair at Eqs. (3)–(4) is not affected.

**What is wrong.** Both the 2026-08-09 pre-registration ("the same quantity
valued at trade-time external prices") and UU design §6 describe them as one
quantity under two valuations. That is false, and
`2026-08-10-r-correction-preregistration.md` records the correction under
"Limitations this does not remove": "the paper must define both algebraically
and name them 'terminal mark-to-market' and 'realised' P&L."

The first depends on the per-swap deltas **only through their sum** and has an
explicit valuation date. The second is a **path integral** — it depends on the
order and timing of the trades and has no valuation date, so it cannot be
obtained from the first by re-dating anything. Their difference is exactly the
inventory-revaluation term, and that term's existence is what makes them
different functionals. Sharper still: the second is not a comparison against
HODL at all, since HODL is only defined at a valuation date; under arb-only flow
it is identically `−Π_arb^gross`, which is why it is negative by construction
there.

**Replacement text.**

> Write $\Delta_t=(\Delta_{0,t},\Delta_{1,t})$ for the pool-side balance change
> of swap $t$, $P_{j,t}$ for the external price of token $j$ at $t$, and $T$ for
> the end of the window. We report two LP outcome measures:
>
> \begin{align} \Pi^{\mathrm{mtm}} &= P_{0,T}\sum_t \Delta_{0,t} + P_{1,T}\sum_t
> \Delta_{1,t},\label{eq:mtm}\\ \Pi^{\mathrm{real}} &=
> \sum_t\bigl(\Delta_{0,t}P_{0,t} + \Delta_{1,t}P_{1,t}\bigr).\label{eq:real}
> \end{align}
>
> These are different functionals, not one quantity under two valuations.
> $\Pi^{\mathrm{mtm}}$ is a terminal mark-to-market of the LP position against
> holding: it depends on the trades only through their sum, and a valuation date
> is the free parameter in it. $\Pi^{\mathrm{real}}$ is a path integral of
> realised transfers: it depends on the order and timing of trades and has no
> valuation date, so it cannot be recovered from $\Pi^{\mathrm{mtm}}$ by
> re-dating a valuation. Their difference, \[
> \Pi^{\mathrm{mtm}}-\Pi^{\mathrm{real}} =
> \sum_t\bigl[\Delta_{0,t}(P_{0,T}-P_{0,t}) +
> \Delta_{1,t}(P_{1,T}-P_{1,t})\bigr], \] is the inventory-revaluation term. We
> call them \emph{terminal mark-to-market} and \emph{realised} P\&L. They answer
> different questions --- whether the LP ended richer than a holder, and whether
> the LP made money on the trades it did --- so $\Pi^{\mathrm{real}}$ carries no
> inventory risk while $\Pi^{\mathrm{mtm}}$ does, and a preference between them
> is a modelling stance rather than a convention. Both are co-primary: both are
> reported for every comparison, neither is designated the headline, and a
> disagreement between them is reported as a finding rather than resolved by
> choosing the friendlier number.

**Sign convention.** `experiments/metrics.py:91-106, 247` implements
`net_result_tt = −Σ(Δ0·P0_t + Δ1·P1_t)` — i.e. the sign depends on whether the
deltas are stored pool-side or trade-side. Verify the convention against
`metrics.py` when typesetting so Eqs. (11)–(12) match the printed numbers.

---

### B5. The slippage limitation, with the measured figures

**Where.** §V-B (`main.tex:316`), the validity paragraph.

**Current text (relevant clause).**

> Results also depend on initial price and liquidity, token decimals,
> observation frequency, trade sizes, valuation time, and the share of informed
> flow.

**What is wrong.** Nothing false, but the paper must not import the design
spec's justification for dropping slippage — "at the 20M basket a per-minute
retail slice (~14k USDT) moves the price ~0.03 bps, two orders below the
smallest fee". That figure is wrong by roughly thirty times, and the model has
since changed: with the corrected `r`, slippage is **inside** `r`, computed from
the realised trade via `SqrtPriceMath`. What remains is a narrower, measured set
of limitations.

**Use these numbers and no others.** From
`2026-08-10-r-correction-preregistration.md`, measured by differencing the
recorded `r` against the same `r` evaluated at zero size over the **2,760 UU
swaps of one real ETH/SHIB day**: **1.18 bps median, 1.59 mean, 3.20 p90, 7.21
p99, 15.7 maximum.** The earlier review's 3.2 / 6.9 / 57.7 bps figures assumed a
full-range pool; the harness mints a concentrated position, so the true impact
is about a third of those, and they are superseded.

**Replacement text (add to §V-B).**

> The participation decision is evaluated on a disadvantage measure computed
> from the realised trade, so finite-size execution cost is inside it. That cost
> is not negligible: measured over the 2{,}760 uninformed swaps of one ETH/SHIB
> day by differencing the recorded measure against the same measure evaluated at
> zero size, it is 1.18~~bps at the median, 1.59~~bps at the mean, 3.20~~bps at
> the 90th percentile, 7.21~~bps at the 99th and 15.7~~bps at the maximum ---
> above the 1~~bps floor of the fee box and inside its 100~~bps ceiling. Three
> consequences are stated as limitations. First, the measure is evaluated at the
> candle's potential slice rather than at the executed size; evaluating it at
> the executed size would reintroduce a fee--participation--size--fee fixed
> point, so this is a declared modelling choice and not a neutral implementation
> detail. Second, the uninformed continuum is evaluated at one point in the
> candle, so users arriving sequentially through the minute --- each facing the
> pool their predecessors moved --- are not modelled; the realised average cost
> across such a continuum is roughly half the aggregate move, which makes the
> reported participation an upper bound. Third, the two uninformed swaps within
> a candle are ordered $A\!\to\!B$ then $B\!\to\!A$, and the first moves the
> pool before the second's measure is evaluated; that displacement is worth
> about 1.2~~bps of cost at the median candle and 7.2~bps at the 99th percentile
> --- small against the fee at the median, not negligible on the tail. Retail
> gas remains outside the measure entirely.

---

### B6. A reproducibility note is required, and does not exist

**Where.** New subsection in §V, or an appendix. Nothing in `main.tex` covers
any of this.

**What it must contain**, each item with its evidence:

1. **The withdrawn matrix.** A full 15,552-cell matrix completed on 2026-08-10
   under a mis-specified disadvantage measure and was **withdrawn as a result**.
   It is retained at `results-uu-preflight-defect/` as evidence for the
   correction and is cited nowhere else; no number from it appears in the paper.
   Disclosing this is cheaper than being asked about it.
2. **The corrected model of record.** The implemented `r` was `γ·p/P_ext − 1` —
   twice the source model's normalised magnitude, and marginal, so it excluded
   slippage. The source model is
   `r = δP(Δx,Δy)/δP(|Δx|,|Δy|) = (V_out − V_in)/(V_out + V_in)`. λ moved from
   231.049060 to **461.404973** so that the calibration statement — half the
   willing flow walks at a 30 bps total transaction cost — is preserved.
3. **The manifest gap** (A9): `P0` and the input checksum were dead fields until
   2026-08-10. State which results carry closed manifests and which do not.
4. **Field `D` is three generations deep on disk.** `results/matrix/` (arb-only,
   frozen) hashed `contracts/src/` only, so it does not pin the harness at all —
   the MEVChargeHook fee-box clamp lives in `contracts/test/utils/HookTest.sol`,
   one directory outside the hash used at the time. `results-uu/` at review time
   held 14,975 cells at one revision and 577 at another.
5. **The MEVChargeHook clamp.** `feeMax` 1000 → 100 bps and
   `flaggedFeeAdditional` 400 → 40 bps (forced by the contract's own invariant,
   since 30 + 400 > 100). **MEVChargeHook rows are not comparable between the
   arb-only and the UU matrices.** Say so in the text, not only in a caption.
6. **The fee-quote modelling choice.** The fee offered to a size-dependent
   policy is quoted at the size being traded rather than at zero. Before the fix
   MEVChargeHook advertised 30 bps and the pool credited about 65, and retail
   decided to trade on the advertised number; on one measured cell its fee
   income falls 15,720 → 6,925. Its earlier second-place ranking was an
   artifact.
7. **The trade-time valuation's post-hoc motivation.** It was chosen after
   inspecting arb-only results (the 2026-08-09 audit found the end-of-window
   valuation carries an inventory-revaluation term that flipped several arb-only
   conclusions), and declared before any UU data existed. The UU
   pre-registration requires the paper to say this.
8. **The trace-directory collision.** The UU matrix wrote its per-swap traces
   into the arb-only experiment's directory under identical filenames,
   destroying 10,363 arb-only traces. `results/summary.csv`,
   `results/analysis.csv` and every published arb-only figure survive, so **no
   published arb-only aggregate is affected**; what is lost is the ability to
   re-derive trace-level arb-only claims. One figure, the arb-only fee
   distribution, was overwritten and cannot be regenerated (see C2).
9. **The sensitivity sweeps write no manifest** and are not pre-registered (B9).
10. **Disclosed peeking, restated accurately.** The UU pre-registration's own
    summary sentence is self-contradictory: it says the peeking was "confined to
    ETH/SHIB, window 2024-01-01, `MyHook`" and then lists three MEVChargeHook
    probes including one high-volatility window, which by construction is not
    2024-01-01. The accurate statement is: `MyHook` on 2024-01-01 at four static
    levels plus the goldens, and three MEVChargeHook probes of which one is a
    high-volatility window, on which only the fee-box bound was inspected — not
    the outcome metric.

**What is worth saying positively in the same note.** The analysis plan was
pre-registered before any run (design §12.1), amended before the power extension
(2026-08-04), before the UU matrix (2026-08-09), and before the corrected re-run
(2026-08-10); each amendment discloses what it changes and why. That is a
genuine strength and no other paper in this space in the citation list does it.

---

### B7. Significance counts and valuations must be reported correctly

**Where.** Wherever §IV reports "N of M significant". Nothing in the current
`main.tex` does yet.

**Three defects to avoid.**

1. **The count is address-duplicated.** `stats.analyse:102-108` includes
   `address_mode` in the strata, so `analysis.csv` carries 594 rows (11
   non-baseline configurations × 3 pairs × 3 regimes × 3 gas × 2 modes). On the
   arb-only matrix, 266 of 270 comparisons were bit-identical across the address
   axis; re-running BH on the deduplicated family of 274 produced **zero verdict
   changes**, but the honest headline was **"56 significant of 274, not 112 of
   540"**. BH is invariant to exact duplication, so no verdict is wrong — every
   _count_ is doubled. Report the distinct count.
2. **The runner reports one of two co-primary valuations, unlabelled.**
   `run_matrix.py:224` calls `analyse(paired)`, whose default is
   `value="net_result_delta"`. The single `analysis.csv` has no column naming
   the valuation and `net_result_tt` appears nowhere in it; the trade-time
   family exists only inside `analysis/07-uu-main-results.ipynb`. Any number
   quoted from `analysis.csv` is one valuation and does not say which.
3. **FDR is controlled per valuation, and that must be stated.** The κ
   pre-registration fixes separate families per valuation, correctly (pooling
   would let a win in one borrow significance from the other), but that choice
   was made after the UU data existed and the UU pre-registration left it open.
   Neither pre-registration gives a decision rule mapping (result under
   valuation 1, result under valuation 2) to a conclusion, so a claim satisfied
   by a win in _either_ is an unadjusted union with roughly double the error
   rate.

**Replacement text (methodology).**

> Each configuration is compared with the static 30~bps baseline on identical
> windows, stratified by volatility regime, gas scenario, pair and arbitrageur
> address model. Comparisons that are bit-identical across the address axis are
> counted once: the declared family contains 540 raw comparisons and 297
> distinct ones, and all counts below are over the distinct family.
> Benjamini--Hochberg is applied at $q=0.05$ **within each valuation
> separately**, since the two valuations are the same comparisons measured
> twice. Every claim is reported under both valuations, and no claim in this
> paper rests on significance in one valuation alone. Each comparison is a
> two-sided Wilcoxon signed-rank test; exact ties are discarded and the
> effective sample size is reported beside every $p$-value, together with the
> paired median difference in USDT and the win rate. No confidence intervals are
> computed.

**One sentence defining the deduplication rule** is required somewhere, because
"the deduplicated family" is not countable in advance from any pre-registered
text — the rule is documented only in `PROGRESS.md`. Suggested: "Two comparisons
are treated as one when their per-window paired differences are identical, which
occurs when a policy's behaviour does not depend on the arbitrageur's address."

---

### B8. The flow model's assumptions are uncited and must be listed as assumptions

**Where.** §V-B, and wherever the flow model is introduced in §IV-A.

**What is wrong.** Four load-bearing statements have no citation, no empirical
anchor and no derivation:

- **The participation model itself.** "Carried over from the group's previous
  work: a psychological parameter `r` … and an execution probability
  `P = exp(−λ|r|)`". No reference, and no justification for the exponential form
  over any other decreasing function. Since B3 shows the functional form
  _determines_ the optimum at `2/λ`, this is the single most load-bearing
  uncited assumption in the study. The paper needs either a citation to the
  prior work or an explicit statement that the form is assumed and results are
  conditional on it.
- **λ's calibration statement does not match λ's domain.** The design says "at a
  **total transaction cost** of 30 bps, half of the willing flow executes", but
  `r` contains the fee and the signed pool deviation, and gas is excluded
  entirely. The exactly-true narrower statement should replace it: at a pool
  sitting on the external price, `r = −f/2` under the corrected normalisation,
  so `P(f = 30 bps) = 0.5` by construction of λ. Away from the external price
  the 30 bps reading does not hold.
- **"Turnover 1×/day, mid-range for real major pools"** — asserted, uncited. The
  κ pre-registration already concedes this; the concession must reach the paper.
- **"UU users see the external price (anyone with a price app does)."** This
  assumption is what makes the pool-deviation term enter `r` signed, and thereby
  produces the effect that users trading toward the reference execute regardless
  of fee. List it as a modelling assumption, not as an aside.

**The sharpest one, which belongs in limitations in the authors' own words.**
Under `share` mode both directions are thinned deterministically from the same
`v₀`, so when the pool sits near the external price with a symmetric fee,
`P_AB = P_BA` and the retail flows **cancel**: net displacement per candle is
`v₀/2·(P_AB − P_BA) ≈ 0`. Uninformed flow therefore delivers fee income with
almost no inventory cost to the LP, **by construction**. The consequence is that
the channel through which a policy can win in this matrix is fee-revenue
optimisation against the participation curve, plus one genuinely directional
channel (a policy setting `f_AB ≠ f_BA` induces `P_AB ≠ P_BA` and does move the
pool — which is the `ABHook` litmus). It is **not** "discriminating between
toxic and benign flow", because there is very little toxicity in the benign flow
to discriminate against. Discrete mode is what would restore order-flow
imbalance, and it is implemented but unrun.

**Replacement text (limitations).**

> The uninformed-flow model is assumed, not estimated. Its participation
> function $P=\exp(-\lambda|r|)$ is taken from prior work in this group; no
> alternative functional form is tested, and Sec.~~\ref{sec:evaluation} shows
> that this form fixes the location of the static optimum at $2/\lambda$. Its
> two scale parameters are calibration choices: $\lambda$ is set so that half
> the willing flow walks at a 30~~bps fee against a pool sitting on the external
> price, and $\kappa$ so that mean daily potential uninformed volume over 2024
> equals one basket; the latter target is not sourced from measurements of live
> pools. $\kappa$ normalises \emph{potential} volume --- realised turnover is
> $\kappa\,\mathbb{E}[P]$ baskets per day and is endogenous to the fee, varying
> by a factor of several across the static levels, so an axis labelled ``daily
> turnover'' must be read as potential turnover. Uninformed users are assumed to
> observe the external price, which is what makes the pool-deviation term enter
> signed. Finally, in the mode used for the main results both directions are
> thinned symmetrically from the same potential volume, so with a symmetric fee
> at a fair-priced pool the uninformed flows cancel and impose almost no
> inventory cost on the LP. Uninformed flow in this model is therefore unusually
> benign, the surviving channel by which a policy can win is fee-revenue
> optimisation against the participation curve together with directional
> reallocation, and the robustness of the ranking to \emph{unbalanced}
> uninformed flow is untested.

---

### B9. The sensitivity sweeps must not be described as pre-registered, and one of them has never run

**Where.** Wherever §IV or §V reports the `captureShare` sweep (the figure
`capture_share_sensitivity.pdf` is already in `paper/Image/`) or the κ sweep.

**What is wrong.**

- **Neither sweep is pre-registered.** The κ pre-registration originally claimed
  the `captureShare` sweep played its role "in the same role §12.1's
  `captureShare` sweep plays for `PegCapture`". §12.1 contains no such sweep;
  the only pre-registered statement about that constant is the opposite
  commitment in the 2026-08-04 amendment — "`captureShare` stays at its single
  configured value" — and the sweep was run afterwards, on 2026-08-03. The κ
  pre-registration has since been corrected to say both are exploratory. The
  paper must not describe either as pre-registered.
- **`captureShare = 0.5` was never pinned by value.** §12.1 pins it by reference
  ("its single configured value") and design §5 names a different value (κ = 1)
  that was never used and is provably inert — with p = P(1+d) and f = d the
  no-arbitrage band exactly contains the pool price, measured as zero trades.
  The sweep then found this parameter **flips the sign of the result**: at 0.10
  `PegCapture` significantly loses in every regime, at 0.75 it significantly
  wins. The mitigating fact belongs in the paper: **0.5 is the weakest winning
  setting**, so the choice is conservative rather than tuned.
- **The λ sweep has never been run.** Design §2.1 and the UU pre-registration
  both declare it; no sweep driver exists. UU design §9's sentence "the UU model
  is synthetic and its λ, κ are swept, not asserted" is currently **false for λ
  and unexecuted for κ**. Either both sweeps run before 2026-08-18, or the paper
  states plainly that λ was fixed at its calibrated value and not varied.

**Replacement text (robustness subsection).**

> Two parameters were varied after the main analysis, and both are reported as
> exploratory rather than pre-registered. \texttt{PegCapture}'s
> \texttt{captureShare} was swept over seven values: it flips the sign of that
> policy's result, losing significantly in every regime at 0.10 and winning at
> 0.75, so the policy is not robust to its own parameter. The configured value
> 0.5 is the weakest of the winning settings, which makes the pre-registered
> choice conservative rather than favourable. The retail-scale parameter
> $\kappa$ was swept over `<<kappa-levels>>`. The participation-sensitivity
> parameter $\lambda$ was **not** varied; it is fixed at its calibrated value
> throughout, and since the static optimum sits at $2/\lambda$ a $\lambda$-sweep
> would vary the result rather than test it.

---

### B10. §V-B's "controlled economic study" paragraph describes work now done

**Where.** `main.tex:320`.

**Current text.**

> A controlled economic study within such a framework should hold the trace,
> initial reserves, liquidity range, valuation convention, and random seed
> constant while varying only the policy. It should compare all hooks with
> static-fee baselines and report LP value, fee income, IL or LVR, net outcome,
> retained volume, mean and distribution of fees, gas overhead, and runtime.
> Multiple pairs, volatility regimes, and repeated windows are required for
> uncertainty estimates. **These additions are future evaluation work, not
> evidence inferred from the current trace.**

**What is wrong.** The paragraph is a specification of the study this paper now
contains. Leaving it as future work is the single clearest signal to a referee
that the text predates the experiments. Keep the specification — it is good —
and convert it into a statement of what was done, with the two genuine gaps
named: interval estimates, and LVR (the paper lists "IL or LVR"; only IL and net
result are computed).

---

## C. Numbers that must be re-checked before submission

Every entry is currently drawn from superseded or unreproducible data. **Nothing
in this list may be typeset from its present source.**

### C1. Every `paper/Image/uu_*` figure comes from the withdrawn matrix

Twenty files, eight figures:

`uu_fee_distribution.{csv,pdf}`, `uu_flow.{csv,pdf,png}`,
`uu_frontier.{csv,pdf,png}`, `uu_frontier_tt.{csv,pdf,png}`,
`uu_gas_breakeven.{csv,pdf}`, `uu_net_result_by_regime.{csv,pdf,png}`,
`uu_net_result_by_regime_tt.{csv,pdf,png}`,
`uu_valuation_comparison.{csv,pdf,png}`.

All were drawn from the matrix withdrawn by
`2026-08-10-r-correction-preregistration.md`. **None may enter the paper until
redrawn from the corrected run.** (PROGRESS states this explicitly.)

> **Resolved 2026-08-11.** All eight were redrawn from the corrected headline
> matrix (`results-uu/`, κ = 1.0, 7,776 cells, 0 errors) and each now carries
> the operating point that produced it printed on the figure itself. **The
> `uu_*` names are clear to typeset.**
>
> They are now **half** the set. The same eight exist as `uu_t01_*` from the
> second operating point (`results-uu/turnover-0.1/`, κ = 0.1), and the
> pre-registration `2026-08-11-informed-share-preregistration.md` requires both
> configurations be reported. A `uu_*` figure printed alone, without its
> `uu_t01_*` counterpart or at minimum the second point's numbers in the text,
> **violates that pre-registration.**

### C1a. New figure: `uu_operating_points.pdf` — required, not optional

The two operating points compared directly: median difference against the static
30 bps baseline per policy, with 95% bootstrap intervals, at both κ. Two columns
(configuration) × two rows (effect size); a filled marker means the interval
excludes zero. Drawn by `analysis/11-operating-points.ipynb`; its numbers are in
`uu_operating_points.csv` beside it.

This is the figure that carries the paper's actual claim, which is conditional:

> the value of a dynamic fee scales with the share of informed flow

It is also the figure that shows **`DAHook` is the only policy whose interval
clears zero at both points**, and that **`BAHook`'s covers zero at both**
despite being significant in 10 of 18 strata at each — the concrete case for
leading with effect sizes rather than p-values (item 4 of PROGRESS's open list).

Two things about it must survive into the caption:

1. **Every panel has its own x-scale.** Compare sign and rank across panels, not
   distance. The two runs differ by 10× in retail flow, so every USDT quantity
   is smaller at κ = 0.1 for reasons that have nothing to do with policy skill.
2. **The interval is a bootstrap over the 18 volatile-pair strata**, not over
   the 432 windows. Pooling windows would narrow it about threefold by treating
   three gas scenarios of one window as independent.

### C2. `fee_distribution` is gone and cannot be regenerated

The arb-only fee-distribution figure was overwritten on 2026-08-10 by a notebook
run that drew from three stray traces — 11 swaps of `MyHook@3000` and 893 of
`PegDefence`, two policies, against the 147,880 swaps across ten policies the
real figure carried. The valid version was destroyed and **the arb-only per-swap
traces no longer exist**, so it cannot be redrawn. The three files were moved to
`results-uu-preflight-defect/clobbered-figures/`; `paper/Image/` correctly holds
no `fee_distribution` figure at all.

**What survives in prose, and may be cited as prose:** `PegDefence` pinned at
its 1 bps floor on 100% of swaps on both pairs; `MEVChargeHook` regime-split at
98% at its floor on ETH/USDC against a 236 bps median on ETH/SHIB. Do not
present either as a figure.

### C3. Arb-only trace-derived figures are usable but not regenerable

`fee_detail_*` (2026-08-04, ten policies) and `fee_response` (2026-08-09) were
verified untouched by the incident, so the files on disk are valid. But the
traces behind them are gone, so no number in them can be re-derived or
corrected. Two consequences: (a) if a reviewer questions one, there is no
recourse; (b) the fee box drawn on them is the arb-only box, and
`MEVChargeHook`'s box differs between experiments (**[30, 1000] bps arb-only,
[30, 100] bps under UU**), so a single figure cannot serve both and any "at cap"
fraction must name its experiment.

### C4. `dynamic_fee_reaction.pdf` and the `dex/` prototype images

`dynamic_fee_reaction.pdf` (mtime 2026-08-02 14:43) has no CSV table view and no
notebook that draws it — unlike all 25 figures the current pipeline produces.
Its axis is in pips and labelled bps (A8). The same provenance question applies
to `eth_price_trace.png`, `shib_price_trace.png`, `price_ratio_trace.png`,
`pool_price_trace.png` and `simulation_summary.png`, which come from the `dex/`
prototype run associated with "1,492". Decide their fate together with `dex/`.

### C5. "1,492 simulated swaps"

Unreproducible; four occurrences (B1). Retire.

### C6. λ = 231.05 is superseded

Correct value: **λ = 461.404973**, WAD `461_404_973_192_736_927_635`. The
calibration _statement_ is unchanged. Any text, figure caption or table carrying
231.05 (or `231_049_060_186_648_440_000`) is stale.

### C7. Participation figures

- Superseded: 0.966 / 0.720 / 0.434 / 0.183 at 5 / 30 / 60 / 100 bps (withdrawn
  matrix, old `r`, old λ, and computed by an estimator since replaced).
- The estimator changed too: `uu_participation` was a mean of `P` weighted by
  raw `amountIn`, which mixes token0 and token1 wei (one direction carried ~5e-9
  of the weight on ETH/SHIB) and weights by a quantity proportional to `P`
  itself, returning `E[P²]/E[P]`. It is now the USDT retention rate.
- Model reference values under the corrected `r` and λ, fee alone at a
  fair-priced pool: **0.891 / 0.500 / 0.250 / 0.098**.
- The r-correction pre-registration also prints 0.760 / 0.426 / 0.213 / 0.084
  "with the mean 6.9 bps of slippage added" — that 6.9 is the **superseded
  full-range** estimate. If the paper prints a slippage-adjusted participation
  curve, re-derive it with the measured **1.59 bps** mean.

### C8. Every headline result from the withdrawn matrix

All of the following are from `results-uu-preflight-defect/` and must be
re-measured from the corrected run before use:

- Static net result 5,749 / 37,675 / 41,089 / 22,354 and "interior optimum at 60
  bps".
- The ledger: `BAHook` 21–1 / 21–0; `MEVChargeHook` 18–9 / 18–9; `DAHook` 3–17 /
  3–17; `ABHook`, `MEVChargeHookFixed`, `PegCapture`, `PegDefence`,
  `VolatilityHook` zero wins and 22–27 losses each.
- `ABHook` litmus: median −185, significant in 27/27 (end-of-window) and 25/27
  (trade-time).
- `MEVChargeHookFixed`: 22/27 significant losses, median −6.17 USDT, −0.016% of
  the baseline result. (The framing — "detectable because 72 windows are a lot,
  and economically nil; report both numbers or neither" — is correct and should
  survive; the numbers must be redone.)
- `PegDefence`: 68.7% at its floor on its worst pair, p95 15.3 bps, mean net
  −313 end-of-window / +254 trade-time.
- `VolatilityHook`: fee spread 0.35 bps around a 5.1 bps median.
- Valuation agreement: 285 of 297 distinct comparisons agree, no paired median
  changes sign, 12 borderline disagreements.
- "Arbitrage share of volume 1–6%".
- Worst conservation error 6.4e-16.

### C9. `MEVChargeHook`'s fee-income collapse

15,720 → 6,925 (−56%) is a **single-cell differential** (ETH/SHIB, 2024-01-01,
20 gwei), measured before the `r` correction. Either re-measure it across the
corrected matrix or label it explicitly as a one-cell differential.

### C10. Per-policy gas

Quote `experiments/gas_estimates.json`, which is what the matrix reads
(`matrix.manifest_for:238`, `run_spec:300`) and is post-recalibration. The gas
table in `PROGRESS.md` is pre-recalibration and disagrees on every policy.
Correct values, including the 21,000 intrinsic:

| Policy               |                                                                                      Gas per swap |
| -------------------- | ------------------------------------------------------------------------------------------------: |
| `VolatilityHook`     |                                                                                           127,508 |
| `BAHook`             |                                                                                           107,847 |
| `PegCapture`         |                                                                                           104,335 |
| `PegDefence`         |                                                                                           100,713 |
| `MEVChargeHookFixed` |                                                                                            98,824 |
| `MEVChargeHook`      |                                                                                            94,739 |
| `ABHook`             |                                                                                            93,842 |
| `DAHook`             |                                                                                            87,970 |
| `MyHook@500`         |                                                                                            76,786 |
| `MyHook@6000`        |                                                                                            76,705 |
| `MyHook@3000`        |                                                                                            76,268 |
| `MyHook@10000`       | 76,578 (harness default; no calibration cell, since it produces no trades on the calibration day) |

### C11. Slippage

Use 1.18 / 1.59 / 3.20 / 7.21 / 15.7 bps (median / mean / p90 / p99 / max). The
figures 3.2 / 6.9 / 16.1 / 57.7 / 606 bps and the design spec's "~0.03 bps" are
both superseded (B5).

### C12. Significance counts

- Arb-only: **56 significant of 274 distinct**, not 112 of 540.
- UU: any count must come from the corrected run, over the distinct family, per
  valuation, with the valuation named. `results-uu/analysis.csv` currently has
  594 address-duplicated rows for one unnamed valuation (B7).

### C13. Numbers verified sound — safe to quote

Stated here so they are not needlessly re-derived: κ(ETH/SHIB) =
0.05517408261312724 (reproduced to 17 digits from the cached 2024 volumes),
κ(USDC/USDT) = 0.02392190008355103, κ(ETH/USDC) = 0.025528390566767624; the
basket of 20,000,000 USDT; 366 daily segments per pair, 122 days per tercile, 24
windows per tercile, 72 per pair; gas scenarios 5 / 20 / 80 gwei; static levels
5 / 30 / 60 / 100 bps = 500 / 3000 / 6000 / 10000 pips; the shared fee box [1,
100] bps; the matrix size 15,552 = 12 × 3 × 72 × 3 × 2; `2/λ` = 43.3 bps; and
the exact Wilcoxon floor at n = 8, `p_min = 2/2⁸ = 0.0078125`.

---

## D. Wording, units, notation

### D1. The κ notation collides with itself

`κ` means `captureShare` in design §5 and the retail-volume scale in every UU
document — two different κ, one of them in a document titled "the κ sensitivity
sweep". Rename one before typesetting. Suggestion: keep κ for the retail scale
(it appears in far more places) and write `captureShare` in full.

### D2. Fee units in the exported artifact

The paper's §III-B correctly states that Uniswap v4 encodes LP fees as `uint24`
in hundredths of a basis point, and §III-B is the paper's own warning about this
hazard. Two live counterexamples sit in the artifact the paper offers readers:
`PegStabilityHook.sol:72-73` names its bounds `MAX_FEE_BPS = 10000` and
`MIN_FEE_BPS = 100` while the values are pips (correct values, lying names), and
`DAHook.sol:24` `uint24 private FSTEP = 100; // 5 bps` — 100 pips is 1 bp. In
the same repository `MEVChargeHook.config.feeMax` genuinely _is_ in bps. **Do
not claim the configurator or the templates validate units.** The paper's
existing three-level validation paragraph (`main.tex:185`) is correctly hedged;
keep it hedged.

### D3. "365 daily segments"

Design §7.3 says 365; 2024 is a leap year and the code, PROGRESS and the
2026-08-04 pre-registration all say **366** (hence 122 days per tercile
exactly). Fix if typeset.

### D4. "No randomness"

Design §7.5's "no randomness remains" is true for everything reported. It stops
being true if the discrete-mode appendix lands, which uses a seeded PRNG at
trace-generation time with the seed as manifest field `S`. Do not print "no
randomness" unconditionally.

### D5. The conservation identity, if typeset

Design §14.1 prints `LP loss = arbitrageur profit + gas − LP fees` and
`IL − R_f = (Π_arb + G) − R_f`. Both are algebraically wrong: the bracketed form
reduces to `IL = Π_arb + G` and the "− LP fees" does nothing. The correct
identity, with `Π_arb` net of gas, is

```
IL − R_f = Π_arb^net + G      (equivalently  IL = R_f + Π_arb^net + G)
```

The implementation is right — conservation closes at ~1e-16 — but §14.1 calls
this "the only substantive invariant", so it is the equation most likely to be
copied into the methodology as-is.

### D6. The arbitrageur entry condition, if typeset

Design §4.2 writes `Π(Δ) − fee(Δ) − gas > 0`; §A.4 writes `Π* > gas cost`. `Π*`
is derived with `γ = 1 − f` inside it, so the fee is already subtracted and §4.2
subtracts it twice. **§A.4 is the correct one and is what the harness
implements.** §4.2 is the version a reader meets first.

### D7. The buy-side arbitrage closed form, if the appendix is typeset

Design §A.5's "the whole computation reduces to…" gives `Π* = L(s−t)²/s` with
`t = √(P/γ)`. That is the token0-**sell** branch only. The buy branch is

```
Π*_{1→0} = L (t − s)² / (γ s),     t = √(Pγ)
```

larger by `1/γ`, because the fee is paid in the token the profit is denominated
in and nothing cancels. This omission produced a real bug (23 of 80,243 buys
suppressed), fixed in `ArbMath` but not in the spec.

### D8. §12.1's Bonferroni arithmetic, if the reasoning is reproduced

§12.1 justifies BH over Bonferroni with "roughly 90 comparisons … which a
Wilcoxon test on 24 windows cannot reach". Both numbers are wrong: the declared
family is 540 raw / 297 distinct, and each comparison runs on **8** windows, not
24 (the family is stratified by regime, 8 windows per tercile at the time it was
written). The **conclusion survives** — at n = 8 the exact two-sided floor is
0.0078, above Bonferroni at either family size — but the stated reasoning does
not support it. The 2026-08-04 amendment derives the same conclusion correctly;
cite that arithmetic, not §12.1's.

### D9. `tab:relatedwork`, the "This work" row

`main.tex:119` reads "Configurable contracts, deployment, replay, project
export, and visualization / Supplies shared Uniswap v4 experimentation
infrastructure". That is now half the contribution. Extend to name the
controlled comparison, or the table understates the paper against its own §IV.

### D10. §IV-A's metric list describes the prototype, not the harness

`main.tex:277` — "The experiment form accepts a hook, year, month, and token
pair… The application extracts swap count, volume, directional fees, fee income,
holdings, LP value, impermanent loss, and net loss, then generates the market
and pool plots." That is the `dex/` web path. The harness that produced the
results is driven by `run_matrix.py` over a declared window set, and its metric
set includes terminal mark-to-market and realised P&L, arbitrageur inventory
mark-to-market, realised arbitrage profit, the uninformed/arbitrage volume
split, the uninformed fee share, retention, and gas cost. Describe both paths
and say which produced the numbers.

### D11. The README contradicts the paper's claim boundary

`dex/README.md` promises "savings of \$1,000 to \$10,000 per month", a claim the
paper explicitly declines to make. If the artifact ships with the submission,
bring them into agreement. (Design §15 has flagged this since 2026-08-02.)

---

## E. Do not claim

Sentences that would be indefensible given what is now known. Each is either
present in `main.tex` today or is the natural sentence to write next.

1. **"`ABHook` is an oracle-informed, block-level policy."** It is per-trade and
   reads the pool price; its two feed arguments are discarded. (A1)
2. **"The volatility templates react to trade volume variance."** No trade
   volume enters the hook. (A3)
3. **"Welford's algorithm computes the fee."** It has not since 2026-08-03. (A4)
4. **"The volatility hook scales the fee in response to market volatility."** At
   the shipped coefficient the response is a fraction of a basis point. (A4, A8)
5. **"The experiment shows that an interior static optimum exists."** It follows
   from `argmax_f f·exp(−λf/2) = 2/λ` given the assumed participation function
   and the chosen λ. (B3)
6. **"`net_result` and `net_result_tt` are the same quantity under two
   valuations."** They are different functionals; the second is not a comparison
   against HODL at all. (B4)
7. **"Slippage is negligible relative to the fee."** Measured at 1.18 bps median
   and 7.21 bps p99, above the fee box's 1 bps floor. (B5)
8. **"The framework includes Go integration tests, Playwright e2e tests, and a
   PostgreSQL history of parameters, events and pool snapshots."** None exists.
   (A6)
9. **"Anvil provides the EVM for the replay."** The replay is a Forge test. (A7)
10. **"The manifest records all six elements of `E`."** True only for the
    corrected run; `P0` was `null` and the input checksum constant in everything
    earlier, and the sweeps write no manifest at all. (A9)
11. **"The input checksum detects a silent change in the input data."** For the
    frozen matrices it cannot: one value, `d3b98a44090795fd`, for all 15,552
    cells of both. (A9)
12. **"The `captureShare` and κ sweeps are pre-registered."** Both are
    exploratory; the only pre-registered statement about `captureShare` is the
    opposite commitment. (B9)
13. **"λ and κ are swept, not asserted."** The λ sweep has never been run and
    the κ sweep is written but unrun. (B9)
14. **"`MEVChargeHook`'s results are comparable across the two matrices."** The
    fee-box clamp (1000 → 100 bps, surcharge 400 → 40 bps) makes them
    incomparable. (B6.5)
15. **"`MEVChargeHook` is the second-ranked policy."** That ranking was an
    artifact of quoting retail a zero-size fee it would not be charged; on the
    measured cell its fee income falls 56% once corrected. (B6.6)
16. **"Uncertainty intervals are reported."** No interval is computed anywhere.
    (A5)
17. **"A dynamic fee can discriminate between toxic and benign flow, and this
    experiment demonstrates it."** In the mode used for the main results,
    uninformed flow is balanced by construction and imposes almost no inventory
    cost; the surviving channels are fee-revenue optimisation and directional
    reallocation. (B8)
18. **"1×/day turnover is mid-range for real major pools."** Uncited. (B8)
19. **"The sweep axis is daily turnover in baskets."** κ normalises _potential_
    volume; realised turnover is `κ·E[P]` and varies by a factor of several
    across fee levels. Label it potential turnover, or report both. (B8)
20. **"A prototype execution over an ETH/SHIB trace processes 1,492 simulated
    swaps."** Unreproducible from this repository. (B1)
21. **"The fee distribution across policies shows…"** as a figure reference. The
    figure is gone and cannot be regenerated; the two surviving facts may be
    stated as prose only. (C2)
22. **Any "N of M significant" without naming the valuation and using the
    distinct family.** (B7)

---

## Appendix: placeholders introduced above

| Placeholder        | What fills it                                                            |
| ------------------ | ------------------------------------------------------------------------ |
| `<<n-cells>>`      | executed cell count of the corrected run (15,552 if it completes)        |
| `<<headline>>`     | the one-sentence result of the corrected run                             |
| `<<vol-spread>>`   | `VolatilityHook` fee spread, corrected run                               |
| `<<vol-median>>`   | `VolatilityHook` median fee, corrected run                               |
| `<<kappa-levels>>` | the κ grid, if the sweep runs: `{0.03, 0.1, 0.3, 1.0, 3.0}` × calibrated |
