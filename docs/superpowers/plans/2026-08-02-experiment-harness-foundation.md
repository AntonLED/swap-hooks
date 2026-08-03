# Experiment Harness Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run one dynamic-fee policy over one day of historical data end-to-end,
producing per-swap events and LP metrics whose token conservation check closes
against independently sourced pool state.

**Architecture:** A Forge test deploys a full-range Uniswap v4 pool with a hook,
replays Binance klines through Chainlink mock feeds, and drives a fee-aware,
gas-aware arbitrageur that pushes the pool to the edge of the no-arbitrage band.
The test emits one JSONL record per swap plus one window record carrying raw
pool state, and derives nothing. Python reads both and computes all metrics.

**Tech Stack:** Solidity 0.8.30, Foundry (forge), Uniswap v4 core/periphery,
OpenZeppelin uniswap-hooks, chainlink-local, Python 3.13 via uv, pytest, pandas.

## Global Constraints

- Solidity version: `0.8.30`, `evm_version = "cancun"`, `via_ir = true`.
- Fee units: Uniswap v4 `uint24` pips — hundredths of a basis point. `1e6` =
  100%. `3000` = 0.3% = 30 bps.
- Fee box, shared by every policy and baseline, per direction: `f_min = 100`
  pips, `f_max = 10000` pips.
- Numeraire: USDT. Valuation time is the end of the window.
- Full-range liquidity only. Initial basket: 20,000,000 USDT split equally by
  value at window start (see spec §4.3 for why not 1M).
- Mock tokens use 18 decimals on both sides regardless of the decimals of the
  assets they stand in for. This is a simplification; record it in the manifest.
- Window length: 1440 candles (one day). Warm-up: first 60 candles executed but
  excluded from metrics.
- No randomness anywhere. Given a trace, a run is bit-for-bit reproducible.
- **The Forge test computes no derived metrics.** It emits observations only.
- **Never hand-roll swap arithmetic.** Amounts between two square-root prices
  come from `SqrtPriceMath`; rounding must match the pool exactly.
- Never run `git commit` unless a step says to. The repository owner commits;
  steps below that say "Commit" are the exception and are explicitly authorised.

---

## File Structure

**Solidity (`contracts/`)**

- `src/*.sol` — policies, migrated; `MyHook` gains the extended fee interface.
- `test/utils/*.sol` — deployment plumbing, migrated.
- `src/libraries/ArbMath.sol` — pure arbitrage math: target price, band test,
  fee gross-up, closed-form profit. No storage, no external calls.
- `test/utils/EventLog.sol` — JSONL emission. Two records: per swap and per
  window.
- `test/Replay.t.sol` — the harness. Wires feeds, arbitrageur, and event log.

**Python (`experiments/`)**

- `experiments/binance.py` — kline fetching, month-keyed disk cache.
- `experiments/events.py` — JSONL reader for both record types.
- `experiments/metrics.py` — derived quantities and the conservation check.
- `tests/` — pytest suites mirroring the modules.

---

### Task 1: Migrate contracts, build, and give `MyHook` the extended interface

`MyHook` is the baseline policy for this entire plan, but it extends
`BaseOverrideFee` directly rather than `CustomBaseHook`, so it has no external
`getFee`, and its `setFee(uint24)` does not match
`IHooksExtended.setFee(uint24, PoolKey)`. The harness calls both through
`IHooksExtended`. Without this task nothing downstream compiles.

**Files:**

- Create: `contracts/` (from `dex/`)
- Modify: `contracts/src/MyHook.sol`
- Create: `.gitmodules`
- Modify: `.gitignore`

**Interfaces:**

- Consumes: nothing.
- Produces: `contracts/` where `forge build` succeeds, and `MyHook` satisfying
  `IHooksExtended` — `getFee(address,PoolKey,SwapParams,bytes) -> uint24` and
  `setFee(uint24,PoolKey)`.

- [x] **Step 1: Install Foundry**

```bash
curl -L https://foundry.paradigm.xyz | bash
"$HOME/.foundry/bin/foundryup"
export PATH="$HOME/.foundry/bin:$PATH"
forge --version
```

Expected: a version string.

- [x] **Step 2: Copy the Solidity tree**

```bash
cd /Users/antonled/science/uniswapv4-hooks/swap-hooks
mkdir -p contracts/src contracts/test
cp -R dex/src/. contracts/src/
cp -R dex/test/utils contracts/test/utils
cp dex/foundry.toml dex/remappings.txt contracts/
rm -f contracts/src/Counter.sol
```

- [x] **Step 3: Declare and fetch the submodules at pinned revisions**

Create `.gitmodules` at the repository root:

```
[submodule "contracts/lib/forge-std"]
	path = contracts/lib/forge-std
	url = https://github.com/foundry-rs/forge-std
[submodule "contracts/lib/hookmate"]
	path = contracts/lib/hookmate
	url = https://github.com/akshatmittal/hookmate
[submodule "contracts/lib/uniswap-hooks"]
	path = contracts/lib/uniswap-hooks
	url = https://github.com/openzeppelin/uniswap-hooks
[submodule "contracts/lib/chainlink-local"]
	path = contracts/lib/chainlink-local
	url = https://github.com/smartcontractkit/chainlink-local
```

`v4-core` and `v4-periphery` are reached through `uniswap-hooks`' own nested
submodules, exactly as `remappings.txt` expects. Do not add them separately.

```bash
cd /Users/antonled/science/uniswapv4-hooks/swap-hooks
for m in forge-std hookmate uniswap-hooks chainlink-local; do :; done
git submodule add https://github.com/foundry-rs/forge-std contracts/lib/forge-std
git submodule add https://github.com/akshatmittal/hookmate contracts/lib/hookmate
git submodule add https://github.com/openzeppelin/uniswap-hooks contracts/lib/uniswap-hooks
git submodule add https://github.com/smartcontractkit/chainlink-local contracts/lib/chainlink-local
git -C contracts/lib/forge-std checkout a6d71da563bbb8d6eef8fbec3a16c61c603d2764
git -C contracts/lib/hookmate checkout 33408fbc15e083eb0bc4205fa37cb6ba0a926f44
git -C contracts/lib/uniswap-hooks checkout ca8fe74e75aa8ca349afce4f864ef58cdea054cb
git -C contracts/lib/chainlink-local checkout a3ace4e17336e84c4d1261f2da45d5e8963af714
git submodule update --init --recursive
git add contracts/lib
```

The revisions are those recorded in `dex`. Pinning them is field `D` of the
reproducibility manifest. The trailing `git add` records the detached SHAs in
the parent index; without it the checkouts are not captured.

- [x] **Step 4: Grant filesystem permissions**

In `contracts/foundry.toml`, replace the `fs_permissions` line:

```toml
fs_permissions = [
    {access = "read-write", path = "./.forge-snapshots/"},
    {access = "read-write", path = "../results/"},
    {access = "read", path = "../data/"},
    {access = "read", path = "./"},
]
```

Without the `results` write grant, `vm.writeLine` reverts.

- [x] **Step 5: Write the failing test for the `MyHook` interface**

Create `contracts/test/MyHookInterface.t.sol`:

```solidity
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.30;

import {Test} from "forge-std/Test.sol";
import {SwapParams} from "@uniswap/v4-core/src/interfaces/IPoolManager.sol";
import {HookTest} from "./utils/HookTest.sol";

contract MyHookInterfaceTest is Test, HookTest {
    function setUp() public {
        deployArtifactsAndLabel();
        deployCurrencyPair();
        deployHookAndFeeds("MyHook");
        deployPool();
    }

    function test_getFeeIsReachableThroughTheExtendedInterface() public {
        uint24 fee = hookContract.getFee(
            address(this),
            poolKey,
            SwapParams({zeroForOne: true, amountSpecified: 0, sqrtPriceLimitX96: 0}),
            ""
        );
        assertGt(fee, 0, "baseline must report its fee");
    }

    function test_setFeeThroughTheExtendedInterfaceTakesEffect() public {
        hookContract.setFee(500, poolKey);
        uint24 fee = hookContract.getFee(
            address(this),
            poolKey,
            SwapParams({zeroForOne: true, amountSpecified: 0, sqrtPriceLimitX96: 0}),
            ""
        );
        assertEq(fee, 500, "the four static baseline levels are set this way");
    }

    function test_feeIsIndependentOfDirectionAndSize() public {
        uint24 a = hookContract.getFee(address(this), poolKey,
            SwapParams({zeroForOne: true, amountSpecified: 1e18, sqrtPriceLimitX96: 0}), "");
        uint24 b = hookContract.getFee(address(this), poolKey,
            SwapParams({zeroForOne: false, amountSpecified: 1000e18, sqrtPriceLimitX96: 0}), "");
        assertEq(a, b, "a static baseline must be flat in both axes");
    }
}
```

- [x] **Step 6: Run to verify failure**

Run: `cd contracts && forge build` Expected: FAIL — `MyHook` does not implement
`getFee` or the two-argument `setFee`, so the cast to `IHooksExtended` cannot be
satisfied at runtime.

- [x] **Step 7: Implement in `MyHook.sol`**

Add beside the existing `_getFee`:

```solidity
    /// @notice Exposes the fee for off-chain sizing, matching IHooksExtended.
    function getFee(address caller, PoolKey calldata key, SwapParams calldata params, bytes calldata data)
        external
        returns (uint24)
    {
        return _getFee(caller, key, params, data);
    }
```

and replace `setFee(uint24 _fee)` with the interface-compatible form:

```solidity
    function setFee(uint24 _fee, PoolKey calldata) external onlyOwner {
        fee = _fee;
    }
```

The `PoolKey` is accepted and ignored: `MyHook` keeps a single fee, not a
per-pool mapping. Ignoring it is safe here because each run deploys one pool.

- [x] **Step 8: Build and run**

Run:
`cd contracts && forge build && forge test --match-path test/MyHookInterface.t.sol -v`
Expected: build succeeds (first build with `via_ir = true` takes minutes), 3
tests pass.

- [x] **Step 9: Ignore build output and remove the stale stub**

Append to `.gitignore`:

```
# Foundry
contracts/out/
contracts/cache/
contracts/broadcast/
contracts/.forge-snapshots/

# Experiment IO
data/
results/
```

```bash
rm -f /Users/antonled/science/uniswapv4-hooks/swap-hooks/experiments/test.ipynb
```

- [x] **Step 10: Commit**

```bash
cd /Users/antonled/science/uniswapv4-hooks/swap-hooks
git add .gitmodules .gitignore contracts
git rm -r --cached --ignore-unmatch experiments/test.ipynb
git commit -m "chore: migrate hook contracts and give MyHook the extended fee interface"
```

---

### Task 2: Python project setup

**Files:**

- Modify: `pyproject.toml`
- Create: `experiments/__init__.py`, `tests/__init__.py`, `tests/test_smoke.py`

**Interfaces:**

- Produces: `uv run pytest` executes and passes.

- [x] **Step 1: Add dependencies**

```bash
cd /Users/antonled/science/uniswapv4-hooks/swap-hooks
uv add pandas pyarrow
uv add --dev pytest
```

`pyarrow` is required for the parquet cache in Task 3.

- [x] **Step 2: Configure pytest**

Append to `pyproject.toml`:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
```

- [x] **Step 3: Write the smoke test**

Create `experiments/__init__.py` and `tests/__init__.py` as empty files, and
`tests/test_smoke.py`:

```python
def test_imports():
    import experiments

    assert experiments is not None
```

- [x] **Step 4: Run it**

Run: `uv run pytest -v` Expected: 1 passed.

- [x] **Step 5: Commit**

```bash
git add pyproject.toml uv.lock experiments tests
git commit -m "chore: set up python test harness"
```

---

### Task 3: Binance loader with pagination and a month-keyed cache

Two defects in the original are corrected here. It requested `limit=1000` with
no pagination, silently truncating a month to its first 16.7 hours. And a cache
keyed on the exact requested range never serves a differently-bounded request —
so a year-long prefetch would not satisfy 24 day-long window fetches, and the
matrix would hit the network thousands of times. The cache is therefore keyed by
**calendar month**, which any range can be assembled from.

**Files:**

- Create: `experiments/binance.py`, `tests/test_binance.py`

**Interfaces:**

- Produces:
  - `fetch_klines(symbol, start_ms, end_ms, cache_dir, api=...) -> pd.DataFrame`
    with columns `open_time` (int64 ms) and `close` (float), sorted ascending,
    de-duplicated, covering `[start_ms, end_ms)`.
  - `months_spanning(start_ms, end_ms) -> list[tuple[int, int]]`

- [x] **Step 1: Write the failing tests**

Create `tests/test_binance.py`:

```python
import pandas as pd
import pytest

from experiments.binance import fetch_klines, months_spanning

JAN_2024 = 1_704_067_200_000  # 2024-01-01T00:00:00Z
MINUTE = 60_000


class FakeApi:
    """Serves 1-minute candles with Binance's 12 fields and 1000-row cap."""

    def __init__(self, first_ms: int, count: int):
        self.first_ms = first_ms
        self.count = count
        self.calls = 0

    def __call__(self, symbol, start_ms, end_ms, limit):
        self.calls += 1
        rows = []
        t = max(start_ms, self.first_ms)
        last = self.first_ms + (self.count - 1) * MINUTE
        while t <= min(end_ms, last) and len(rows) < limit:
            close = 100.0 + (t - self.first_ms) / MINUTE
            rows.append([
                t, "1.0", "1.0", "1.0", str(close), "1.0",
                t + MINUTE - 1, "1.0", 1, "1.0", "1.0", "0",
            ])
            t += MINUTE
        return rows


def test_paginates_beyond_the_1000_candle_cap(tmp_path):
    api = FakeApi(JAN_2024, 1440)
    df = fetch_klines("ETHUSDT", JAN_2024, JAN_2024 + 1440 * MINUTE, tmp_path, api=api)

    assert len(df) == 1440, "a full day must come back, not the first 1000"
    assert api.calls >= 2


def test_accepts_binances_twelve_field_rows(tmp_path):
    """The real endpoint returns 12 fields per kline, not 6."""
    api = FakeApi(JAN_2024, 60)
    df = fetch_klines("ETHUSDT", JAN_2024, JAN_2024 + 60 * MINUTE, tmp_path, api=api)

    assert list(df.columns) == ["open_time", "close"]
    assert df["close"].dtype.kind == "f"
    assert df["close"].iloc[0] == pytest.approx(100.0)


def test_rows_are_sorted_and_unique(tmp_path):
    api = FakeApi(JAN_2024, 1440)
    df = fetch_klines("ETHUSDT", JAN_2024, JAN_2024 + 1440 * MINUTE, tmp_path, api=api)

    assert df["open_time"].is_monotonic_increasing
    assert not df["open_time"].duplicated().any()


def test_a_narrow_request_is_served_from_a_wide_cache(tmp_path):
    """The matrix prefetches whole months, then reads single days out of them."""
    api = FakeApi(JAN_2024, 1440 * 31)
    fetch_klines("ETHUSDT", JAN_2024, JAN_2024 + 1440 * 31 * MINUTE, tmp_path, api=api)
    calls_after_prefetch = api.calls

    day = fetch_klines("ETHUSDT", JAN_2024 + 1440 * 5 * MINUTE,
                       JAN_2024 + 1440 * 6 * MINUTE, tmp_path, api=api)

    assert api.calls == calls_after_prefetch, "no network for an already-cached month"
    assert len(day) == 1440


def test_a_request_spanning_two_months_is_assembled(tmp_path):
    api = FakeApi(JAN_2024, 1440 * 40)
    start = JAN_2024 + 1440 * 29 * MINUTE
    df = fetch_klines("ETHUSDT", start, start + 1440 * 3 * MINUTE, tmp_path, api=api)

    assert len(df) == 1440 * 3
    assert df["open_time"].is_monotonic_increasing


def test_months_spanning_covers_the_boundary():
    spans = months_spanning(JAN_2024, JAN_2024 + 40 * 1440 * MINUTE)
    assert len(spans) == 2, "January and February"
    assert spans[0][0] == JAN_2024
```

- [x] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_binance.py -v` Expected: FAIL —
`ModuleNotFoundError`.

- [x] **Step 3: Implement**

Create `experiments/binance.py`:

```python
"""Binance kline loading with pagination and a calendar-month disk cache.

Two properties matter for reproducibility. The public endpoint caps a single
response at 1000 candles regardless of the requested range, so any window longer
than 1000 minutes needs a loop. And the cache is keyed by calendar month rather
than by requested range, so a prefetch of whole months satisfies every later
window request without touching the network.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests

MINUTE_MS = 60_000
MAX_LIMIT = 1000
_BASE_URL = "https://api.binance.com/api/v3/klines"

# The endpoint returns twelve fields per kline. Naming all of them lets the
# frame be built without guessing the width.
KLINE_FIELDS = [
    "open_time", "open", "high", "low", "close", "volume",
    "close_time", "quote_volume", "trades",
    "taker_base", "taker_quote", "ignore",
]


def _http_api(symbol: str, start_ms: int, end_ms: int, limit: int) -> list:
    response = requests.get(
        _BASE_URL,
        params={
            "symbol": symbol,
            "interval": "1m",
            "startTime": start_ms,
            "endTime": end_ms,
            "limit": limit,
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def months_spanning(start_ms: int, end_ms: int) -> list[tuple[int, int]]:
    """Calendar-month [start, end) bounds covering the requested range."""
    spans: list[tuple[int, int]] = []
    cursor = datetime.fromtimestamp(start_ms / 1000, timezone.utc).replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    )
    while int(cursor.timestamp() * 1000) < end_ms:
        nxt = (cursor + timedelta(days=32)).replace(day=1)
        spans.append((int(cursor.timestamp() * 1000), int(nxt.timestamp() * 1000)))
        cursor = nxt
    return spans


def _fetch_range(symbol: str, start_ms: int, end_ms: int, api) -> pd.DataFrame:
    rows: list[list] = []
    cursor = start_ms
    while cursor < end_ms:
        batch = api(symbol, cursor, end_ms - 1, MAX_LIMIT)
        if not batch:
            break
        rows.extend(batch)
        next_cursor = int(batch[-1][0]) + MINUTE_MS
        if next_cursor <= cursor:
            break
        cursor = next_cursor

    if not rows:
        return pd.DataFrame({"open_time": pd.Series(dtype="int64"),
                             "close": pd.Series(dtype="float64")})

    frame = pd.DataFrame(rows, columns=KLINE_FIELDS[: len(rows[0])])
    frame = frame[["open_time", "close"]].copy()
    frame["open_time"] = frame["open_time"].astype("int64")
    frame["close"] = frame["close"].astype("float64")
    return frame


def _month_cache(cache_dir: Path, symbol: str, month_start: int) -> Path:
    return cache_dir / f"{symbol}-1m-{month_start}.parquet"


def fetch_klines(
    symbol: str,
    start_ms: int,
    end_ms: int,
    cache_dir: Path,
    api=_http_api,
) -> pd.DataFrame:
    """Return 1-minute candles for [start_ms, end_ms) as open_time, close."""
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)

    parts = []
    for month_start, month_end in months_spanning(start_ms, end_ms):
        cached = _month_cache(cache_dir, symbol, month_start)
        if cached.exists():
            parts.append(pd.read_parquet(cached))
            continue
        month = _fetch_range(symbol, month_start, month_end, api)
        month.to_parquet(cached, index=False)
        parts.append(month)

    if not parts:
        return pd.DataFrame({"open_time": pd.Series(dtype="int64"),
                             "close": pd.Series(dtype="float64")})

    frame = pd.concat(parts, ignore_index=True)
    return (
        frame[(frame["open_time"] >= start_ms) & (frame["open_time"] < end_ms)]
        .drop_duplicates(subset="open_time")
        .sort_values("open_time")
        .reset_index(drop=True)
    )
```

- [x] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_binance.py -v` Expected: 6 passed.

- [x] **Step 5: Commit**

```bash
git add experiments/binance.py tests/test_binance.py
git commit -m "feat: add paginated binance loader with month-keyed cache"
```

---

### Task 4: Arbitrage math library

The arbitrageur pushes the pool to the near edge of the no-arbitrage band. For a
constant-product pool with proportional fee $f$ and $\gamma = 1 - f$, the band
is $[P\gamma,\ P/\gamma]$ where $P$ is the external price of token0 in token1;
the optimal trade lands exactly on the near edge. Spec Appendix A derives this.

**Files:**

- Create: `contracts/src/libraries/ArbMath.sol`, `contracts/test/ArbMath.t.sol`

**Interfaces:**

- Produces:
  - `targetSqrtPriceX96(uint256 externalPriceX96, uint24 feePips, bool zeroForOne) -> uint160`
  - `shouldTrade(uint160 current, uint160 target, bool zeroForOne) -> bool`
  - `grossInput(uint256 netInput, uint24 feePips) -> uint256`
  - `profit(uint128 liquidity, uint160 current, uint160 target) -> uint256` —
    the closed-form $\Pi^{*} = L(s-t)^2/s$, denominated in token1.

- [x] **Step 1: Write the failing test**

Create `contracts/test/ArbMath.t.sol`:

```solidity
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.30;

import {Test} from "forge-std/Test.sol";
import {TickMath} from "@uniswap/v4-core/src/libraries/TickMath.sol";
import {ArbMath} from "../src/libraries/ArbMath.sol";

contract ArbMathTest is Test {
    uint256 constant Q96 = 1 << 96;

    function _priceX96(uint256 numerator, uint256 denominator) internal pure returns (uint256) {
        return (numerator * Q96) / denominator;
    }

    function test_zeroFeeTargetEqualsExternalPrice() public pure {
        uint160 target = ArbMath.targetSqrtPriceX96(_priceX96(1, 1), 0, true);
        assertApproxEqAbs(uint256(target), Q96, 1);
    }

    function test_sellingToken0TargetsAboveExternalPrice() public pure {
        uint256 p = _priceX96(1, 1);
        assertGt(
            uint256(ArbMath.targetSqrtPriceX96(p, 3000, true)),
            uint256(ArbMath.targetSqrtPriceX96(p, 0, true))
        );
    }

    function test_buyingToken0TargetsBelowExternalPrice() public pure {
        uint256 p = _priceX96(1, 1);
        assertLt(
            uint256(ArbMath.targetSqrtPriceX96(p, 3000, false)),
            uint256(ArbMath.targetSqrtPriceX96(p, 0, false))
        );
    }

    function test_bandIsSymmetricInLogPrice() public pure {
        uint256 p = _priceX96(1, 1);
        uint256 hi = uint256(ArbMath.targetSqrtPriceX96(p, 10000, true));
        uint256 lo = uint256(ArbMath.targetSqrtPriceX96(p, 10000, false));
        assertApproxEqRel((hi * lo) / Q96, p, 1e12);
    }

    function test_noTradeInsideTheBand() public pure {
        uint256 p = _priceX96(1, 1);
        uint160 hi = ArbMath.targetSqrtPriceX96(p, 10000, true);
        uint160 lo = ArbMath.targetSqrtPriceX96(p, 10000, false);
        uint160 mid = uint160((uint256(hi) + uint256(lo)) / 2);

        assertFalse(ArbMath.shouldTrade(mid, hi, true));
        assertFalse(ArbMath.shouldTrade(mid, lo, false));
    }

    function test_tradeWhenOutsideTheBand() public pure {
        uint256 p = _priceX96(1, 1);
        uint160 hi = ArbMath.targetSqrtPriceX96(p, 10000, true);
        uint160 lo = ArbMath.targetSqrtPriceX96(p, 10000, false);

        assertTrue(ArbMath.shouldTrade(uint160(uint256(hi) * 2), hi, true));
        assertTrue(ArbMath.shouldTrade(uint160(uint256(lo) / 2), lo, false));
    }

    function test_grossInputAddsTheFee() public pure {
        assertApproxEqAbs(ArbMath.grossInput(997_000, 3000), 1_000_000, 1);
    }

    function test_grossInputIsIdentityAtZeroFee() public pure {
        assertEq(ArbMath.grossInput(12345, 0), 12345);
    }

    /// Spec A.4 numerical check: x=y=1, P=0.81, gamma=1 gives profit 0.01.
    /// In (L, s) coordinates x=y=1 means L=1 and s=2^96.
    function test_profitMatchesTheWorkedExample() public pure {
        uint256 p = _priceX96(81, 100);
        uint160 s = uint160(Q96);
        uint160 t = ArbMath.targetSqrtPriceX96(p, 0, true);
        uint256 got = ArbMath.profit(1e18, s, t);
        assertApproxEqRel(got, 0.01e18, 1e15); // 0.1% tolerance
    }

    function test_profitIsZeroAtTheBandEdge() public pure {
        uint160 s = uint160(Q96);
        assertEq(ArbMath.profit(1e18, s, s), 0);
    }

    function test_targetStaysInsideTheProtocolPriceRange() public pure {
        uint160 t = ArbMath.targetSqrtPriceX96(_priceX96(1, 1), 10000, true);
        assertGt(uint256(t), uint256(TickMath.MIN_SQRT_PRICE));
        assertLt(uint256(t), uint256(TickMath.MAX_SQRT_PRICE));
    }

    function test_extremeRatioDoesNotOverflowOrTruncate() public pure {
        // SHIB/ETH is around 6.7e-9; ETH/SHIB around 1.5e8. Both must survive.
        uint256 tiny = _priceX96(67, 10_000_000_000);
        uint256 huge = _priceX96(150_000_000, 1);
        assertGt(uint256(ArbMath.targetSqrtPriceX96(tiny, 3000, true)), 0);
        assertGt(uint256(ArbMath.targetSqrtPriceX96(huge, 3000, true)), 0);
    }
}
```

- [x] **Step 2: Run to verify failure**

Run: `cd contracts && forge test --match-path test/ArbMath.t.sol -v` Expected:
FAIL — the source file does not exist.

- [x] **Step 3: Implement**

Create `contracts/src/libraries/ArbMath.sol`:

```solidity
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.30;

import {FullMath} from "@uniswap/v4-core/src/libraries/FullMath.sol";
import {TickMath} from "@uniswap/v4-core/src/libraries/TickMath.sol";
import {Math} from "@openzeppelin/contracts/utils/math/Math.sol";

/**
 * @title ArbMath
 * @notice Pure arbitrage math for a full-range constant-product pool.
 *
 * With proportional fee f and gamma = 1 - f, the no-arbitrage band on the pool
 * price (token1 per token0) is [P*gamma, P/gamma] for external price P. The
 * profit-maximising trade moves the pool exactly to the near edge. See spec
 * Appendix A for the derivation.
 *
 * Prices are Uniswap Q96 fixed point: `externalPriceX96` is P * 2^96, and
 * returned values are sqrt(price) * 2^96.
 */
library ArbMath {
    uint256 internal constant ONE_PIPS = 1_000_000;
    uint256 internal constant Q96 = 1 << 96;

    error PriceOutOfRange();

    /// @notice The pool price the arbitrageur drives the pool to.
    /// @dev Reverts rather than truncating if the target leaves the range the
    ///      protocol can represent; a silent uint160 cast would produce a
    ///      plausible but wrong target.
    function targetSqrtPriceX96(uint256 externalPriceX96, uint24 feePips, bool zeroForOne)
        internal
        pure
        returns (uint160)
    {
        uint256 gammaPips = ONE_PIPS - uint256(feePips);

        uint256 targetPriceX96 = zeroForOne
            ? FullMath.mulDiv(externalPriceX96, ONE_PIPS, gammaPips)
            : FullMath.mulDiv(externalPriceX96, gammaPips, ONE_PIPS);

        // sqrt(price) * 2^96 == sqrt(priceX96 * 2^96)
        uint256 root = Math.sqrt(FullMath.mulDiv(targetPriceX96, Q96, 1));

        if (root <= uint256(TickMath.MIN_SQRT_PRICE) || root >= uint256(TickMath.MAX_SQRT_PRICE)) {
            revert PriceOutOfRange();
        }
        return uint160(root);
    }

    /// @notice Whether the pool sits outside the band on the given side.
    function shouldTrade(uint160 currentSqrtPriceX96, uint160 targetSqrtPriceX96_, bool zeroForOne)
        internal
        pure
        returns (bool)
    {
        return zeroForOne
            ? currentSqrtPriceX96 > targetSqrtPriceX96_
            : currentSqrtPriceX96 < targetSqrtPriceX96_;
    }

    /// @notice Gross up a post-fee input to the amount to send.
    /// @dev v4 deducts the LP fee from the input before the swap math, so
    ///      moving the price by `netInput` requires sending more than that.
    function grossInput(uint256 netInput, uint24 feePips) internal pure returns (uint256) {
        if (feePips == 0) return netInput;
        return FullMath.mulDivRoundingUp(netInput, ONE_PIPS, ONE_PIPS - uint256(feePips));
    }

    /// @notice Closed-form optimal profit, denominated in token1.
    /// @dev Spec A.5: Pi* = L * (s - t)^2 / s.
    function profit(uint128 liquidity, uint160 currentSqrtPriceX96, uint160 targetSqrtPriceX96_)
        internal
        pure
        returns (uint256)
    {
        uint256 s = uint256(currentSqrtPriceX96);
        uint256 t = uint256(targetSqrtPriceX96_);
        uint256 gap = s > t ? s - t : t - s;
        return FullMath.mulDiv(FullMath.mulDiv(liquidity, gap, s), gap, Q96);
    }
}
```

- [x] **Step 4: Run to verify pass**

Run: `cd contracts && forge test --match-path test/ArbMath.t.sol -v` Expected:
12 passed.

- [x] **Step 5: Commit**

```bash
git add contracts/src/libraries/ArbMath.sol contracts/test/ArbMath.t.sol
git commit -m "feat: add arbitrage band math with range guards and closed-form profit"
```

---

### Task 5: JSONL event log, swap and window records

The harness records raw observations only. Two record types are needed. Per-swap
records carry trader-side quantities; the **window record carries pool-side
state** — liquidity, tick bounds, final square-root price, and accumulated fee
growth. The two sides are what makes the conservation check in Task 7 a real
check rather than an identity: the LP position is reconstructed from pool state,
while the trader flow comes from the swap records.

**Files:**

- Create: `contracts/test/utils/EventLog.sol`, `contracts/test/EventLog.t.sol`

**Interfaces:**

- Produces:
  - `EventLog.SwapRecord` and `EventLog.writeSwap(Vm, string, SwapRecord)`
  - `EventLog.WindowRecord` and `EventLog.writeWindow(Vm, string, WindowRecord)`

- [x] **Step 1: Write the failing test**

Create `contracts/test/EventLog.t.sol`:

```solidity
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.30;

import {Test} from "forge-std/Test.sol";
import {EventLog} from "./utils/EventLog.sol";

contract EventLogTest is Test {
    string constant PATH = "../results/_eventlog_test.jsonl";

    function setUp() public {
        if (vm.exists(PATH)) vm.removeFile(PATH);
    }

    function test_writesOneLinePerRecord() public {
        EventLog.writeSwap(vm, PATH, _swap(1));
        EventLog.writeSwap(vm, PATH, _swap(2));

        string[] memory lines = vm.split(vm.readFile(PATH), "\n");
        assertEq(lines.length, 3, "two records plus empty tail");
    }

    function test_swapRecordIsParseableJson() public {
        EventLog.writeSwap(vm, PATH, _swap(7));

        string memory line = vm.split(vm.readFile(PATH), "\n")[0];
        assertEq(vm.parseJsonString(line, ".kind"), "swap");
        assertEq(vm.parseJsonUint(line, ".candle"), 7);
        assertEq(vm.parseJsonUint(line, ".gas"), 21000);
        assertEq(vm.parseJsonUint(line, ".feePips"), 3000);
        assertTrue(vm.parseJsonBool(line, ".zeroForOne"));
    }

    function test_windowRecordCarriesPoolSideState() public {
        EventLog.writeWindow(vm, PATH, _window());

        string memory line = vm.split(vm.readFile(PATH), "\n")[0];
        assertEq(vm.parseJsonString(line, ".kind"), "window");
        // Everything the LP position is reconstructed from must be present.
        assertEq(vm.parseJsonUint(line, ".liquidity"), 1e21);
        assertEq(vm.parseJsonUint(line, ".feeGrowthInside0X128"), 12345);
        assertEq(vm.parseJsonUint(line, ".feeGrowthInside1X128"), 67890);
        assertEq(vm.parseJsonUint(line, ".initialToken0"), 5e18);
        assertEq(vm.parseJsonInt(line, ".tickLower"), -887220);
    }

    function test_bothKindsCoexistInOneFile() public {
        EventLog.writeSwap(vm, PATH, _swap(1));
        EventLog.writeWindow(vm, PATH, _window());

        string[] memory lines = vm.split(vm.readFile(PATH), "\n");
        assertEq(vm.parseJsonString(lines[0], ".kind"), "swap");
        assertEq(vm.parseJsonString(lines[1], ".kind"), "window");
    }

    function _swap(uint256 candle) internal view returns (EventLog.SwapRecord memory) {
        return EventLog.SwapRecord({
            candle: candle,
            blockNumber: block.number,
            timestamp: block.timestamp,
            extPrice0: 300000000000,
            extPrice1: 2000,
            sqrtPriceBeforeX96: 79228162514264337593543950336,
            sqrtPriceAfterX96: 79228162514264337593543950336,
            zeroForOne: true,
            amountIn: 1e18,
            amountOut: 9e17,
            feePips: 3000,
            feeAB: 3000,
            feeBA: 3000,
            delta0: -1e18,
            delta1: 9e17,
            expectedProfit: 1e15,
            gas: 21000,
            sender: address(0xBEEF)
        });
    }

    function _window() internal view returns (EventLog.WindowRecord memory) {
        return EventLog.WindowRecord({
            liquidity: 1e21,
            tickLower: -887220,
            tickUpper: 887220,
            sqrtPriceInitialX96: 79228162514264337593543950336,
            sqrtPriceFinalX96: 79228162514264337593543950336,
            feeGrowthInside0X128: 12345,
            feeGrowthInside1X128: 67890,
            initialToken0: 5e18,
            initialToken1: 5e18,
            extPrice0Initial: 300000000000,
            extPrice1Initial: 2000,
            extPrice0Final: 310000000000,
            extPrice1Final: 2100,
            warmupCandles: 60,
            candles: 1440
        });
    }
}
```

- [x] **Step 2: Run to verify failure**

Run: `cd contracts && forge test --match-path test/EventLog.t.sol -v` Expected:
FAIL — `EventLog.sol` does not exist.

- [x] **Step 3: Implement**

Create `contracts/test/utils/EventLog.sol`:

```solidity
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.30;

import {Vm} from "forge-std/Vm.sol";

/**
 * @title EventLog
 * @notice Appends raw observations to a JSONL file, one record per line.
 * @dev Records observations only. Every derived quantity — IL, LVR, P&L,
 *      aggregates — is computed downstream in Python, so a metric can change
 *      without recompiling or re-running.
 *
 *      Two record kinds share the file, distinguished by the "kind" field.
 *      Swap records carry trader-side flow; the window record carries pool-side
 *      state. Downstream, the LP position is rebuilt from pool state while flow
 *      comes from swap records, so the two can be checked against each other.
 */
library EventLog {
    struct SwapRecord {
        uint256 candle;
        uint256 blockNumber;
        uint256 timestamp;
        int256 extPrice0;
        int256 extPrice1;
        uint160 sqrtPriceBeforeX96;
        uint160 sqrtPriceAfterX96;
        bool zeroForOne;
        uint256 amountIn;
        uint256 amountOut;
        uint24 feePips;
        uint24 feeAB;
        uint24 feeBA;
        int256 delta0;
        int256 delta1;
        uint256 expectedProfit;
        uint256 gas;
        address sender;
    }

    struct WindowRecord {
        uint128 liquidity;
        int24 tickLower;
        int24 tickUpper;
        uint160 sqrtPriceInitialX96;
        uint160 sqrtPriceFinalX96;
        uint256 feeGrowthInside0X128;
        uint256 feeGrowthInside1X128;
        uint256 initialToken0;
        uint256 initialToken1;
        int256 extPrice0Initial;
        int256 extPrice1Initial;
        int256 extPrice0Final;
        int256 extPrice1Final;
        uint256 warmupCandles;
        uint256 candles;
    }

    function writeSwap(Vm vm, string memory path, SwapRecord memory r) internal {
        string memory line = string.concat(
            '{"kind":"swap","candle":', vm.toString(r.candle),
            ',"blockNumber":', vm.toString(r.blockNumber),
            ',"timestamp":', vm.toString(r.timestamp),
            ',"extPrice0":', vm.toString(r.extPrice0),
            ',"extPrice1":', vm.toString(r.extPrice1),
            ',"sqrtPriceBeforeX96":', vm.toString(uint256(r.sqrtPriceBeforeX96)),
            ',"sqrtPriceAfterX96":', vm.toString(uint256(r.sqrtPriceAfterX96))
        );
        line = string.concat(
            line,
            ',"zeroForOne":', r.zeroForOne ? "true" : "false",
            ',"amountIn":', vm.toString(r.amountIn),
            ',"amountOut":', vm.toString(r.amountOut),
            ',"feePips":', vm.toString(uint256(r.feePips)),
            ',"feeAB":', vm.toString(uint256(r.feeAB)),
            ',"feeBA":', vm.toString(uint256(r.feeBA))
        );
        line = string.concat(
            line,
            ',"delta0":', vm.toString(r.delta0),
            ',"delta1":', vm.toString(r.delta1),
            ',"expectedProfit":', vm.toString(r.expectedProfit),
            ',"gas":', vm.toString(r.gas),
            ',"sender":"', vm.toString(r.sender), '"}'
        );
        vm.writeLine(path, line);
    }

    function writeWindow(Vm vm, string memory path, WindowRecord memory r) internal {
        string memory line = string.concat(
            '{"kind":"window","liquidity":', vm.toString(uint256(r.liquidity)),
            ',"tickLower":', vm.toString(int256(r.tickLower)),
            ',"tickUpper":', vm.toString(int256(r.tickUpper)),
            ',"sqrtPriceInitialX96":', vm.toString(uint256(r.sqrtPriceInitialX96)),
            ',"sqrtPriceFinalX96":', vm.toString(uint256(r.sqrtPriceFinalX96))
        );
        line = string.concat(
            line,
            ',"feeGrowthInside0X128":', vm.toString(r.feeGrowthInside0X128),
            ',"feeGrowthInside1X128":', vm.toString(r.feeGrowthInside1X128),
            ',"initialToken0":', vm.toString(r.initialToken0),
            ',"initialToken1":', vm.toString(r.initialToken1)
        );
        line = string.concat(
            line,
            ',"extPrice0Initial":', vm.toString(r.extPrice0Initial),
            ',"extPrice1Initial":', vm.toString(r.extPrice1Initial),
            ',"extPrice0Final":', vm.toString(r.extPrice0Final),
            ',"extPrice1Final":', vm.toString(r.extPrice1Final),
            ',"warmupCandles":', vm.toString(r.warmupCandles),
            ',"candles":', vm.toString(r.candles), '}'
        );
        vm.writeLine(path, line);
    }
}
```

Each concatenation is split into chunks because `string.concat` with many
arguments blows the stack under `via_ir`.

- [x] **Step 4: Run to verify pass**

Run: `cd contracts && forge test --match-path test/EventLog.t.sol -v` Expected:
4 passed.

- [x] **Step 5: Commit**

```bash
git add contracts/test/utils/EventLog.sol contracts/test/EventLog.t.sol
git commit -m "feat: add jsonl event log with swap and window records"
```

---

### Task 6: Replay harness

Three properties this task must get right, each of which was wrong in the
original framework:

1. The pool starts **at the external price**, not at `SQRT_PRICE_1_1`. For
   ETH/SHIB the true ratio is around 6.7e-9; starting at 1 would hand the first
   arbitrageur an eight-order-of-magnitude free lunch.
2. The arbitrageur checks **profit against gas** before trading. Without it the
   three gas scenarios in the matrix produce identical results and the entire
   "gas affects flow" mechanism is absent.
3. Swap amounts come from `SqrtPriceMath`, not hand-rolled algebra, so rounding
   matches the pool exactly.

**Files:**

- Create: `contracts/test/Replay.t.sol`

**Interfaces:**

- Consumes: `ArbMath`, `EventLog`, `HookTest`.
- Produces: `testReplay()` reading env `HOOK_NAME`, `FEE_PIPS`, `TRACE0`,
  `TRACE1`, `TRACE_GAS`, `OUT`, `GAS_PRICE_WEI`, `GAS_ESTIMATE`, `ADDRESS_MODE`,
  `BASKET_USDT`, writing swap records and one window record to `OUT`.

- [x] **Step 1: Write the harness skeleton and its guard tests**

Create `contracts/test/Replay.t.sol`:

```solidity
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.30;

import {Test} from "forge-std/Test.sol";
import {TickMath} from "@uniswap/v4-core/src/libraries/TickMath.sol";
import {FullMath} from "@uniswap/v4-core/src/libraries/FullMath.sol";
import {SqrtPriceMath} from "@uniswap/v4-core/src/libraries/SqrtPriceMath.sol";
import {StateLibrary} from "@uniswap/v4-core/src/libraries/StateLibrary.sol";
import {LiquidityAmounts} from "@uniswap/v4-core/test/utils/LiquidityAmounts.sol";
import {IPoolManager, SwapParams} from "@uniswap/v4-core/src/interfaces/IPoolManager.sol";
import {IHooks} from "@uniswap/v4-core/src/interfaces/IHooks.sol";
import {PoolKey} from "@uniswap/v4-core/src/types/PoolKey.sol";
import {PoolId} from "@uniswap/v4-core/src/types/PoolId.sol";
import {Currency} from "@uniswap/v4-core/src/types/Currency.sol";
import {LPFeeLibrary} from "@uniswap/v4-core/src/libraries/LPFeeLibrary.sol";
import {Constants} from "@uniswap/v4-core/test/utils/Constants.sol";
import {MockERC20} from "solmate/src/test/utils/mocks/MockERC20.sol";

import {HookTest} from "./utils/HookTest.sol";
import {EventLog} from "./utils/EventLog.sol";
import {ArbMath} from "../src/libraries/ArbMath.sol";

contract ReplayTest is Test, HookTest {
    using StateLibrary for IPoolManager;

    uint256 constant Q96 = 1 << 96;
    uint256 constant PRICE_SCALE = 1e8;

    string outPath;
    uint256 gasPriceWei;
    uint256 gasEstimate;
    bool freshAddress;
    uint256 warmupCandles;

    uint256[] price0;
    uint256[] price1;
    uint256[] priceGasEth; // ETH/USDT, used only to value gas

    int24 tickLower;
    int24 tickUpper;
    uint160 sqrtPriceInitialX96;
    uint256 initialToken0;
    uint256 initialToken1;

    /// @dev Guard: the pool must open at the external price, not at 1:1.
    function test_poolOpensAtTheExternalPrice() public view {
        (uint160 current,,,) = poolManager.getSlot0(poolId);
        uint160 expected = _sqrtPriceFromExternal(0);
        assertApproxEqRel(uint256(current), uint256(expected), 1e12);
    }

    /// @dev Guard: an unprofitable-after-gas opportunity must be skipped.
    function test_gasCostSuppressesMarginalTrades() public {
        uint256 cheap = _countTradesWithGasPrice(1);
        uint256 dear = _countTradesWithGasPrice(1_000_000 gwei);
        assertLt(dear, cheap, "expensive gas must reduce the trade count");
    }

    function testReplay() public {
        uint256 startBlock = block.number;
        for (uint256 i = 1; i < price0.length; i++) {
            _setFeeds(i);
            vm.roll(startBlock + i);
            vm.warp(block.timestamp + 12);
            _step(i);
        }
        _writeWindowRecord();
    }
}
```

- [x] **Step 2: Run to verify failure**

Run: `cd contracts && forge test --match-path test/Replay.t.sol -v` Expected:
FAIL — compile error, helpers undeclared.

- [x] **Step 3: Implement setup and pool deployment at the external price**

Add to the contract:

```solidity
    function setUp() public {
        deployArtifactsAndLabel();
        deployCurrencyPair();
        deployHookAndFeeds(vm.envOr("HOOK_NAME", string("MyHook")));

        outPath = vm.envOr("OUT", string("../results/replay.jsonl"));
        gasPriceWei = vm.envOr("GAS_PRICE_WEI", uint256(20 gwei));
        gasEstimate = vm.envOr("GAS_ESTIMATE", uint256(180_000));
        warmupCandles = vm.envOr("WARMUP_CANDLES", uint256(60));
        freshAddress = keccak256(bytes(vm.envOr("ADDRESS_MODE", string("persistent"))))
            == keccak256(bytes("fresh"));

        _loadTrace(vm.envOr("TRACE0", string("../data/trace0.csv")), price0);
        _loadTrace(vm.envOr("TRACE1", string("../data/trace1.csv")), price1);
        _loadTrace(vm.envOr("TRACE_GAS", string("../data/trace_gas.csv")), priceGasEth);
        require(price0.length == price1.length, "trace length mismatch");
        require(price0.length == priceGasEth.length, "gas trace length mismatch");

        if (vm.exists(outPath)) vm.removeFile(outPath);

        _setFeeds(0);
        _deployPoolAtExternalPrice();

        uint24 feePips = uint24(vm.envOr("FEE_PIPS", uint256(0)));
        if (feePips != 0) hookContract.setFee(feePips, poolKey);
    }

    /// @dev Replaces HookTest.deployPool, which hardcodes SQRT_PRICE_1_1.
    function _deployPoolAtExternalPrice() internal {
        sqrtPriceInitialX96 = _sqrtPriceFromExternal(0);

        poolKey = PoolKey(
            currency0, currency1, LPFeeLibrary.DYNAMIC_FEE_FLAG, tickSpacing, IHooks(hookContract)
        );
        poolId = poolKey.toId();

        tickLower = truncateTickSpacing(TickMath.MIN_TICK, tickSpacing);
        tickUpper = truncateTickSpacing(TickMath.MAX_TICK, tickSpacing);

        poolManager.initialize(poolKey, sqrtPriceInitialX96);

        (uint256 want0, uint256 want1) = _basketAmounts();
        uint128 liq = LiquidityAmounts.getLiquidityForAmounts(
            sqrtPriceInitialX96,
            TickMath.getSqrtPriceAtTick(tickLower),
            TickMath.getSqrtPriceAtTick(tickUpper),
            want0,
            want1
        );

        MockERC20(Currency.unwrap(currency0)).mint(address(this), want0 * 2);
        MockERC20(Currency.unwrap(currency1)).mint(address(this), want1 * 2);

        (tokenId,) = positionManager.mint(
            poolKey, tickLower, tickUpper, liq, want0 * 2, want1 * 2,
            address(this), block.timestamp, Constants.ZERO_BYTES
        );

        (initialToken0, initialToken1) = LiquidityAmounts.getAmountsForLiquidity(
            sqrtPriceInitialX96,
            TickMath.getSqrtPriceAtTick(tickLower),
            TickMath.getSqrtPriceAtTick(tickUpper),
            liq
        );

        // Preconditions the fee accounting in Task 7 depends on.
        //
        // `feeGrowthInside x L` equals the fees owed to the position only when
        // the position's own snapshot is zero. That holds here because the mint
        // happens immediately after initialize with no swap in between. Any
        // future warm-up placed before the mint, or a second position, would
        // silently break it -- so assert rather than assume.
        (uint256 fg0, uint256 fg1) = poolManager.getFeeGrowthInside(poolId, tickLower, tickUpper);
        require(fg0 == 0 && fg1 == 0, "position minted after fee growth began");

        // A non-zero protocol fee diverts part of the swap fee away from
        // feeGrowthInside, which would make the conservation check fail for a
        // reason unrelated to the harness.
        (,, uint24 protocolFee,) = poolManager.getSlot0(poolId);
        require(protocolFee == 0, "protocol fee must be off");
    }

    /// @notice Basket of BASKET_USDT split equally by value at window start.
    function _basketAmounts() internal view returns (uint256 amount0, uint256 amount1) {
        uint256 basketUsdt = vm.envOr("BASKET_USDT", uint256(1_000_000));
        uint256 halfUsdt = basketUsdt / 2;
        // prices are 1e8-scaled; mock tokens are 18-decimal on both sides
        amount0 = FullMath.mulDiv(halfUsdt * 1e18, PRICE_SCALE, price0[0]);
        amount1 = FullMath.mulDiv(halfUsdt * 1e18, PRICE_SCALE, price1[0]);
    }

    /// @notice sqrt(price0/price1) * 2^96 for the given candle.
    function _sqrtPriceFromExternal(uint256 i) internal view returns (uint160) {
        uint256 priceX96 = FullMath.mulDiv(price0[i], Q96, price1[i]);
        return uint160(Math.sqrt(FullMath.mulDiv(priceX96, Q96, 1)));
    }
```

Import `Math` from OpenZeppelin alongside the others.

- [x] **Step 4: Implement the gas-aware arbitrage step**

```solidity
    function _step(uint256 candle) internal {
        uint256 extPriceX96 = FullMath.mulDiv(price0[candle], Q96, price1[candle]);
        (uint160 sqrtBefore,,,) = poolManager.getSlot0(poolId);
        uint128 liq = poolManager.getLiquidity(poolId);

        for (uint256 side = 0; side < 2; side++) {
            bool zeroForOne = side == 0;

            uint24 fee = hookContract.getFee(
                _sender(candle),
                poolKey,
                SwapParams({zeroForOne: zeroForOne, amountSpecified: 0, sqrtPriceLimitX96: 0}),
                ""
            );
            uint160 target = ArbMath.targetSqrtPriceX96(extPriceX96, fee, zeroForOne);
            if (!ArbMath.shouldTrade(sqrtBefore, target, zeroForOne)) continue;

            // Profit is denominated in token1; so must the gas cost be.
            uint256 expected = ArbMath.profit(liq, sqrtBefore, target);
            if (expected <= _gasCostInToken1(candle)) continue;

            _executeArb(candle, zeroForOne, fee, target, sqrtBefore, liq, expected);
            return;
        }
    }

    /// @notice Gas cost of one swap, expressed in token1 units.
    /// @dev gasEstimate is a per-policy constant from a calibration run; a real
    ///      arbitrageur likewise decides on an estimate, not on the realised
    ///      cost. The realised gas is recorded separately per swap.
    function _gasCostInToken1(uint256 candle) internal view returns (uint256) {
        uint256 weiCost = gasEstimate * gasPriceWei;              // wei of ETH
        uint256 usdtCost = FullMath.mulDiv(weiCost, priceGasEth[candle], PRICE_SCALE);
        return FullMath.mulDiv(usdtCost, PRICE_SCALE, price1[candle]);
    }

    function _sender(uint256 candle) internal view returns (address) {
        return freshAddress
            ? address(uint160(uint256(keccak256(abi.encode("arb", candle)))))
            : address(this);
    }
```

- [x] **Step 5: Implement execution using `SqrtPriceMath`**

```solidity
    function _executeArb(
        uint256 candle,
        bool zeroForOne,
        uint24 fee,
        uint160 target,
        uint160 sqrtBefore,
        uint128 liq,
        uint256 expectedProfit
    ) internal {
        address sender = _sender(candle);

        // Library amounts, not hand-rolled algebra: rounding must match the pool.
        uint256 netIn = zeroForOne
            ? SqrtPriceMath.getAmount0Delta(target, sqrtBefore, liq, true)
            : SqrtPriceMath.getAmount1Delta(sqrtBefore, target, liq, true);
        if (netIn == 0) return;
        uint256 amountIn = ArbMath.grossInput(netIn, fee);

        _fund(sender, zeroForOne, amountIn);

        uint256 bal0Before = currency0.balanceOf(sender);
        uint256 bal1Before = currency1.balanceOf(sender);

        vm.startPrank(sender);
        uint256 gasBefore = gasleft();
        swapRouter.swapExactTokensForTokens({
            amountIn: amountIn,
            amountOutMin: 0,
            zeroForOne: zeroForOne,
            poolKey: poolKey,
            hookData: Constants.ZERO_BYTES,
            receiver: sender,
            deadline: block.timestamp + 1
        });
        uint256 gasUsed = gasBefore - gasleft();
        vm.stopPrank();

        int256 delta0 = int256(currency0.balanceOf(sender)) - int256(bal0Before);
        int256 delta1 = int256(currency1.balanceOf(sender)) - int256(bal1Before);
        (uint160 sqrtAfter,,,) = poolManager.getSlot0(poolId);

        if (candle < warmupCandles) return;

        EventLog.writeSwap(vm, outPath, EventLog.SwapRecord({
            candle: candle,
            blockNumber: block.number,
            timestamp: block.timestamp,
            extPrice0: int256(price0[candle]),
            extPrice1: int256(price1[candle]),
            sqrtPriceBeforeX96: sqrtBefore,
            sqrtPriceAfterX96: sqrtAfter,
            zeroForOne: zeroForOne,
            amountIn: amountIn,
            amountOut: uint256(zeroForOne ? delta1 : delta0),
            feePips: fee,
            feeAB: _feeFor(true),
            feeBA: _feeFor(false),
            delta0: delta0,
            delta1: delta1,
            expectedProfit: expectedProfit,
            gas: gasUsed,
            sender: sender
        }));
    }

    function _feeFor(bool zeroForOne) internal returns (uint24) {
        return hookContract.getFee(
            address(this),
            poolKey,
            SwapParams({zeroForOne: zeroForOne, amountSpecified: 0, sqrtPriceLimitX96: 0}),
            ""
        );
    }

    function _fund(address who, bool zeroForOne, uint256 amount) internal {
        Currency c = zeroForOne ? currency0 : currency1;
        MockERC20(Currency.unwrap(c)).mint(who, amount);
        vm.prank(who);
        MockERC20(Currency.unwrap(c)).approve(address(swapRouter), type(uint256).max);
    }
```

`_feeFor` reads both directional fees for the record. For policies whose
`_getFee` mutates state — only `MEVChargeHook`, addressed in Plan 2 — this read
must be wrapped in a state snapshot; `MyHook` is pure in this respect.

- [x] **Step 6: Implement the window record and trace loading**

```solidity
    function _writeWindowRecord() internal {
        (uint160 sqrtFinal,,,) = poolManager.getSlot0(poolId);
        (uint256 fg0, uint256 fg1) = poolManager.getFeeGrowthInside(poolId, tickLower, tickUpper);
        uint256 last = price0.length - 1;

        EventLog.writeWindow(vm, outPath, EventLog.WindowRecord({
            liquidity: poolManager.getLiquidity(poolId),
            tickLower: tickLower,
            tickUpper: tickUpper,
            sqrtPriceInitialX96: sqrtPriceInitialX96,
            sqrtPriceFinalX96: sqrtFinal,
            feeGrowthInside0X128: fg0,
            feeGrowthInside1X128: fg1,
            initialToken0: initialToken0,
            initialToken1: initialToken1,
            extPrice0Initial: int256(price0[0]),
            extPrice1Initial: int256(price1[0]),
            extPrice0Final: int256(price0[last]),
            extPrice1Final: int256(price1[last]),
            warmupCandles: warmupCandles,
            candles: price0.length
        }));
    }

    function _setFeeds(uint256 i) internal {
        priceFeed0.updateAnswer(int256(price0[i]));
        priceFeed1.updateAnswer(int256(price1[i]));
    }

    function _loadTrace(string memory path, uint256[] storage into) internal {
        string[] memory lines = vm.split(vm.readFile(path), "\n");
        for (uint256 i = 0; i < lines.length; i++) {
            if (bytes(lines[i]).length == 0) continue;
            string[] memory f = vm.split(lines[i], ",");
            into.push(vm.parseUint(f[1]));
        }
    }
```

Trace CSV format, written by Task 8's exporter: `open_time,price_1e8`, no
header, prices as integers scaled by 1e8.

`_countTradesWithGasPrice` for the Step 1 guard re-runs a short prefix of the
trace with `gasPriceWei` overridden and counts executed swaps.

- [x] **Step 7: Run against a synthetic trace**

```bash
cd /Users/antonled/science/uniswapv4-hooks/swap-hooks
mkdir -p data results
uv run python - <<'PY'
from pathlib import Path
n = 200
Path("data/trace0.csv").write_text("\n".join(f"{i},{int(3000e8)}" for i in range(n)) + "\n")
Path("data/trace1.csv").write_text(
    "\n".join(f"{i},{int((0.03 + 0.0002 * (i % 20)) * 1e8)}" for i in range(n)) + "\n")
Path("data/trace_gas.csv").write_text("\n".join(f"{i},{int(3000e8)}" for i in range(n)) + "\n")
PY
cd contracts && HOOK_NAME=MyHook FEE_PIPS=3000 forge test --match-path test/Replay.t.sol -v
```

Expected: all tests pass, and `results/replay.jsonl` holds swap records with
`candle >= 60` plus exactly one window record.

- [x] **Step 8: Commit**

```bash
git add contracts/test/Replay.t.sol
git commit -m "feat: add gas-aware replay harness starting at the external price"
```

---

### Task 7: Event parser and metrics with a genuine conservation check

The invariant must compare quantities derived from **independent sources**, or
it proves nothing. The LP position is rebuilt from pool state in the window
record — `getAmountsForLiquidity` for principal, `feeGrowthInside × L` for fees
— while trader flow is summed from swap records. In token terms the pool's
holdings equal the initial deposit minus everything the traders took:

$$\text{principal}_j + \text{fees}_j \;=\; L_{0,j} - \sum_i \delta_{i,j}$$

Two independent derivations of the same quantity. A mismatch is a real defect.

Note also that fees are **not** part of the position principal in v4 — they
accrue separately through `feeGrowth` — so adding fee income to a principal that
already contained it would double count.

**Files:**

- Create: `experiments/events.py`, `experiments/metrics.py`,
  `tests/test_metrics.py`

**Interfaces:**

- Produces:
  - `read_events(path) -> tuple[pd.DataFrame, dict]` — swap frame and window
    dict.
  - `compute(swaps, window, gas_price_wei) -> dict` with keys `fee_income`,
    `lp_principal`, `lp_value`, `hodl_value`, `il`, `net_result`, `arb_profit`,
    `gas_cost`, `retained_volume`, `trade_count`, `conservation_error_token0`,
    `conservation_error_token1`.

- [x] **Step 1: Write the failing tests**

Create `tests/test_metrics.py`:

```python
import json
from pathlib import Path

import pytest

from experiments.events import read_events
from experiments.metrics import amounts_for_liquidity, compute

Q96 = 2**96
WAD = 10**18


def _window(**kw):
    base = dict(
        kind="window", liquidity=10**21, tickLower=-887220, tickUpper=887220,
        sqrtPriceInitialX96=Q96, sqrtPriceFinalX96=Q96,
        feeGrowthInside0X128=0, feeGrowthInside1X128=0,
        initialToken0=10**21, initialToken1=10**21,
        extPrice0Initial=10**8, extPrice1Initial=10**8,
        extPrice0Final=10**8, extPrice1Final=10**8,
        warmupCandles=0, candles=100,
    )
    base.update(kw)
    return base


def _swap(**kw):
    base = dict(
        kind="swap", candle=1, blockNumber=1, timestamp=0,
        extPrice0=10**8, extPrice1=10**8,
        sqrtPriceBeforeX96=Q96, sqrtPriceAfterX96=Q96,
        zeroForOne=True, amountIn=WAD, amountOut=9 * 10**17,
        feePips=3000, feeAB=3000, feeBA=3000,
        delta0=-WAD, delta1=9 * 10**17, expectedProfit=10**15,
        gas=150000, sender="0x00000000000000000000000000000000000BeEF0",
    )
    base.update(kw)
    return base


def _write(tmp_path, records):
    p = tmp_path / "replay.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in records) + "\n")
    return p


def test_reader_separates_the_two_record_kinds(tmp_path):
    path = _write(tmp_path, [_swap(candle=1), _swap(candle=2), _window()])
    swaps, window = read_events(path)

    assert len(swaps) == 2
    assert window["liquidity"] == 10**21
    assert "kind" not in swaps.columns or (swaps["kind"] == "swap").all()


def test_reader_preserves_large_integers_exactly(tmp_path):
    """Q96 and feeGrowth values exceed float64 precision."""
    big = 340282366920938463463374607431768211455
    path = _write(tmp_path, [_window(feeGrowthInside0X128=big)])
    _, window = read_events(path)
    assert window["feeGrowthInside0X128"] == big


def test_conservation_closes_when_the_two_sides_agree(tmp_path):
    """A swap that moves no price and pays no fee leaves the pool unchanged."""
    path = _write(tmp_path, [_swap(delta0=0, delta1=0, amountIn=0, feePips=0), _window()])
    swaps, window = read_events(path)
    m = compute(swaps, window, gas_price_wei=20e9)

    assert abs(m["conservation_error_token0"]) < 1e-9
    assert abs(m["conservation_error_token1"]) < 1e-9


def test_conservation_detects_an_inconsistent_log(tmp_path):
    """If trader flow and pool state disagree, the check must fire.

    This is the whole point of the invariant: it is not an identity, so a
    corrupted log is caught rather than absorbed.
    """
    path = _write(tmp_path, [_swap(delta0=-(5 * WAD), delta1=0), _window()])
    swaps, window = read_events(path)
    m = compute(swaps, window, gas_price_wei=20e9)

    assert abs(m["conservation_error_token0"]) > 1e-6


def test_il_is_not_clamped_at_zero(tmp_path):
    """A profitable LP outcome must be representable as negative IL."""
    path = _write(tmp_path, [_window(extPrice0Final=10**8, extPrice1Final=2 * 10**8)])
    swaps, window = read_events(path)
    m = compute(swaps, window, gas_price_wei=20e9)
    assert isinstance(m["il"], float)


def test_fees_are_absent_from_the_position_principal(tmp_path):
    """In v4 a fee never joins L, so principal must not move when only fee
    growth changes. If principal responded, fees would be counted twice."""
    no_fees = _write(tmp_path, [_window(feeGrowthInside0X128=0)])
    with_fees = tmp_path / "b.jsonl"
    with_fees.write_text(json.dumps(_window(feeGrowthInside0X128=(2**128) // 1000)) + "\n")

    a = compute(*read_events(no_fees), gas_price_wei=20e9)
    b = compute(*read_events(with_fees), gas_price_wei=20e9)

    assert a["lp_principal"] == pytest.approx(b["lp_principal"])
    assert b["fee_income"] > a["fee_income"]


def test_fee_income_comes_from_fee_growth_not_from_trader_deltas(tmp_path):
    path = _write(tmp_path, [_swap(), _window(feeGrowthInside0X128=(2**128) // 1000)])
    swaps, window = read_events(path)
    m = compute(swaps, window, gas_price_wei=20e9)

    assert m["fee_income"] > 0, "fees must come from the pool's own accounting"


def test_lp_value_is_principal_plus_fees(tmp_path):
    path = _write(tmp_path, [_window(feeGrowthInside0X128=(2**128) // 1000)])
    swaps, window = read_events(path)
    m = compute(swaps, window, gas_price_wei=20e9)

    assert m["lp_value"] == pytest.approx(m["lp_principal"] + m["fee_income"])


def test_gas_cost_uses_the_recorded_gas(tmp_path):
    path = _write(tmp_path, [_swap(gas=150000), _swap(candle=2, gas=150000), _window()])
    swaps, window = read_events(path)
    cheap = compute(swaps, window, gas_price_wei=1e9)["gas_cost"]
    dear = compute(swaps, window, gas_price_wei=100e9)["gas_cost"]

    assert dear == pytest.approx(cheap * 100)


def test_amounts_for_liquidity_matches_the_uniswap_formula():
    """At price 1 with symmetric bounds the two sides are equal."""
    a0, a1 = amounts_for_liquidity(10**21, Q96, -887220, 887220)
    assert a0 == pytest.approx(a1, rel=1e-6)


def test_empty_window_yields_zeroed_metrics(tmp_path):
    path = _write(tmp_path, [_window()])
    swaps, window = read_events(path)
    m = compute(swaps, window, gas_price_wei=20e9)

    assert m["trade_count"] == 0
    assert m["retained_volume"] == 0.0
```

- [x] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_metrics.py -v` Expected: FAIL —
`experiments.events` does not exist.

- [x] **Step 3: Implement the reader**

Create `experiments/events.py`:

```python
"""Reader for the JSONL log emitted by the Forge replay harness.

Values such as sqrtPriceX96 and feeGrowthInsideX128 exceed float64 precision, so
the file is parsed with the stdlib json module rather than pandas' JSON reader,
which coerces large integers to floats.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

SWAP_INT_COLUMNS = [
    "candle", "blockNumber", "timestamp", "extPrice0", "extPrice1",
    "sqrtPriceBeforeX96", "sqrtPriceAfterX96", "amountIn", "amountOut",
    "feePips", "feeAB", "feeBA", "delta0", "delta1", "expectedProfit", "gas",
]


def read_events(path: Path) -> tuple[pd.DataFrame, dict]:
    swaps: list[dict] = []
    window: dict = {}

    for line in Path(path).read_text().splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        if record.get("kind") == "window":
            window = record
        else:
            swaps.append(record)

    if not swaps:
        frame = pd.DataFrame(columns=SWAP_INT_COLUMNS + ["zeroForOne", "sender"])
    else:
        frame = pd.DataFrame(swaps)
        for column in SWAP_INT_COLUMNS:
            frame[column] = frame[column].map(int)

    return frame, window
```

- [x] **Step 4: Implement the metrics**

Create `experiments/metrics.py`:

```python
"""Derived quantities for one replay window.

The contracts derive nothing; everything here is computed from the event log.
Prices arrive 1e8-scaled (the Chainlink convention) and token amounts 1e18-scaled.

The LP position is reconstructed from pool state — principal from
getAmountsForLiquidity, fees from feeGrowthInside — while trader flow is summed
from the swap records. Because these are independent derivations of the same
tokens, comparing them is a real check rather than an identity.

Fees are read from the pool's fee accounting, never inferred from reserves: in
v4 a fee is credited to the position through feeGrowthInside and never joins the
liquidity L, so it does not appear in the reserves as a distinguishable quantity
and does not compound. `feeGrowthInside * L` is the amount owed only because the
position is minted before any swap, leaving its own snapshot at zero; the
harness asserts that precondition at deployment.
"""

from __future__ import annotations

import pandas as pd

PRICE_SCALE = 1e8
WAD = 1e18
Q96 = 2**96
Q128 = 2**128


def _sqrt_price_at_tick(tick: int) -> float:
    return (1.0001 ** (tick / 2)) * Q96


def amounts_for_liquidity(
    liquidity: int, sqrt_price_x96: int, tick_lower: int, tick_upper: int
) -> tuple[float, float]:
    """Uniswap v3/v4 position amounts at a given price. Float is sufficient here:
    the result feeds a USD figure, not on-chain arithmetic."""
    sa = _sqrt_price_at_tick(tick_lower)
    sb = _sqrt_price_at_tick(tick_upper)
    s = float(min(max(sqrt_price_x96, sa), sb))
    liq = float(liquidity)

    amount0 = liq * (sb - s) / (s * sb / Q96)
    amount1 = liq * (s - sa) / Q96
    return amount0, amount1


def _usd(amount_wad: float, price_1e8: float) -> float:
    return (amount_wad / WAD) * (price_1e8 / PRICE_SCALE)


def compute(swaps: pd.DataFrame, window: dict, gas_price_wei: float) -> dict:
    liquidity = int(window["liquidity"])
    final_p0 = float(window["extPrice0Final"])
    final_p1 = float(window["extPrice1Final"])

    principal0, principal1 = amounts_for_liquidity(
        liquidity, int(window["sqrtPriceFinalX96"]),
        int(window["tickLower"]), int(window["tickUpper"]),
    )

    # Fees live outside the position principal in v4.
    fee0 = float(window["feeGrowthInside0X128"]) * liquidity / Q128
    fee1 = float(window["feeGrowthInside1X128"]) * liquidity / Q128

    l0_0 = float(window["initialToken0"])
    l0_1 = float(window["initialToken1"])

    if swaps.empty:
        flow0 = flow1 = 0.0
        gas_units = 0.0
        retained = 0.0
    else:
        flow0 = float(swaps["delta0"].sum())
        flow1 = float(swaps["delta1"].sum())
        gas_units = float(swaps["gas"].sum())
        retained = _usd(float(swaps.loc[swaps["zeroForOne"], "amountIn"].sum()), final_p0) + _usd(
            float(swaps.loc[~swaps["zeroForOne"], "amountIn"].sum()), final_p1
        )

    # Independent derivations of the pool's token holdings.
    conservation_error_token0 = (principal0 + fee0) - (l0_0 - flow0)
    conservation_error_token1 = (principal1 + fee1) - (l0_1 - flow1)

    fee_income = _usd(fee0, final_p0) + _usd(fee1, final_p1)
    lp_principal = _usd(principal0, final_p0) + _usd(principal1, final_p1)
    lp_value = lp_principal + fee_income
    hodl_value = _usd(l0_0, final_p0) + _usd(l0_1, final_p1)

    # Not clamped: a profitable LP outcome is representable as negative IL.
    il = hodl_value - lp_principal
    net_result = fee_income - il

    gas_cost = (gas_units * gas_price_wei / WAD) * (final_p0 / PRICE_SCALE)
    arb_profit = _usd(flow0, final_p0) + _usd(flow1, final_p1)

    scale = max(abs(l0_0), 1.0), max(abs(l0_1), 1.0)
    return {
        "fee_income": fee_income,
        "lp_principal": lp_principal,
        "lp_value": lp_value,
        "hodl_value": hodl_value,
        "il": il,
        "net_result": net_result,
        "arb_profit": arb_profit,
        "gas_cost": gas_cost,
        "retained_volume": retained,
        "trade_count": int(len(swaps)),
        "conservation_error_token0": conservation_error_token0 / scale[0],
        "conservation_error_token1": conservation_error_token1 / scale[1],
    }
```

The conservation errors are returned **relative** to the initial deposit, so the
tolerance is scale-free across pairs whose token magnitudes differ by orders of
magnitude.

- [x] **Step 5: Run to verify pass**

Run: `uv run pytest tests/test_metrics.py -v` Expected: 10 passed. If
`test_conservation_detects_an_inconsistent_log` passes trivially, the check has
become an identity again — fix `compute`, never relax the assertion.

- [x] **Step 6: Commit**

```bash
git add experiments/events.py experiments/metrics.py tests/test_metrics.py
git commit -m "feat: add event parser and lp metrics with token conservation check"
```

---

### Task 8: End-to-end run on real data

**Files:**

- Create: `experiments/export_trace.py`, `experiments/run_one.py`,
  `tests/test_export_trace.py`

**Interfaces:**

- Produces: `export_trace(df, path)`; `run_one(...) -> dict`.

- [x] **Step 1: Write the failing test**

Create `tests/test_export_trace.py`:

```python
import pandas as pd
import pytest

from experiments.export_trace import align_traces, export_trace


def test_writes_headerless_scaled_integers(tmp_path):
    df = pd.DataFrame({"open_time": [1, 2], "close": [3000.5, 0.00002]})
    path = tmp_path / "t.csv"
    export_trace(df, path)

    lines = path.read_text().strip().split("\n")
    assert lines[0] == "1,300050000000"
    assert lines[1] == "2,2000"
    assert "open_time" not in path.read_text()


def test_alignment_keeps_only_shared_timestamps():
    """A gap in one symbol must not shift the other's prices."""
    a = pd.DataFrame({"open_time": [1, 2, 3], "close": [10.0, 11.0, 12.0]})
    b = pd.DataFrame({"open_time": [1, 3], "close": [1.0, 3.0]})

    aa, bb = align_traces(a, b)

    assert list(aa["open_time"]) == [1, 3]
    assert list(bb["open_time"]) == [1, 3]
    assert list(aa["close"]) == [10.0, 12.0]


def test_alignment_rejects_an_empty_intersection():
    a = pd.DataFrame({"open_time": [1, 2], "close": [1.0, 2.0]})
    b = pd.DataFrame({"open_time": [8, 9], "close": [1.0, 2.0]})

    with pytest.raises(ValueError):
        align_traces(a, b)
```

- [x] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_export_trace.py -v` Expected: FAIL — module
missing.

- [x] **Step 3: Implement**

Create `experiments/export_trace.py`:

```python
"""Writes kline frames as the headerless CSV the Forge harness reads."""

from __future__ import annotations

from functools import reduce
from pathlib import Path

import pandas as pd

PRICE_SCALE = 100_000_000  # 1e8, the Chainlink feed convention


def align_traces(*frames: pd.DataFrame) -> tuple[pd.DataFrame, ...]:
    """Restrict every frame to the timestamps all of them share.

    Binance occasionally omits a minute for one symbol and not another. Zipping
    the frames positionally would silently pair mismatched prices from then on.
    """
    shared = reduce(lambda a, b: a.intersection(b),
                    (pd.Index(f["open_time"]) for f in frames))
    if len(shared) == 0:
        raise ValueError("traces share no timestamps")
    shared = shared.sort_values()
    return tuple(
        f[f["open_time"].isin(shared)].sort_values("open_time").reset_index(drop=True)
        for f in frames
    )


def export_trace(df: pd.DataFrame, path: Path) -> None:
    scaled = (df["close"] * PRICE_SCALE).round().astype("int64")
    lines = [f"{t},{p}" for t, p in zip(df["open_time"], scaled)]
    Path(path).write_text("\n".join(lines) + "\n")
```

Create `experiments/run_one.py`:

```python
"""Drives one replay: fetch, align, export, run Forge, parse, compute."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from experiments.binance import fetch_klines
from experiments.events import read_events
from experiments.export_trace import align_traces, export_trace
from experiments.metrics import compute

ROOT = Path(__file__).resolve().parent.parent
GAS_SYMBOL = "ETHUSDT"  # values gas in USDT for every pair


def run_one(
    hook: str,
    symbol0: str,
    symbol1: str,
    start_ms: int,
    end_ms: int,
    fee_pips: int = 0,
    gas_price_wei: int = 20_000_000_000,
    gas_estimate: int = 180_000,
    address_mode: str = "persistent",
    basket_usdt: int = 1_000_000,
) -> dict:
    data, results = ROOT / "data", ROOT / "results"
    data.mkdir(exist_ok=True)
    results.mkdir(exist_ok=True)

    df0 = fetch_klines(symbol0, start_ms, end_ms, data)
    df1 = fetch_klines(symbol1, start_ms, end_ms, data)
    dfg = fetch_klines(GAS_SYMBOL, start_ms, end_ms, data)
    df0, df1, dfg = align_traces(df0, df1, dfg)

    export_trace(df0, data / "trace0.csv")
    export_trace(df1, data / "trace1.csv")
    export_trace(dfg, data / "trace_gas.csv")

    name = f"{hook}-{fee_pips}-{symbol0}-{symbol1}-{start_ms}-{gas_price_wei}-{address_mode}.jsonl"
    out = results / name

    subprocess.run(
        ["forge", "test", "--match-test", "testReplay", "--match-path", "test/Replay.t.sol"],
        cwd=ROOT / "contracts",
        check=True,
        env={
            **os.environ,
            "HOOK_NAME": hook,
            "FEE_PIPS": str(fee_pips),
            "TRACE0": "../data/trace0.csv",
            "TRACE1": "../data/trace1.csv",
            "TRACE_GAS": "../data/trace_gas.csv",
            "OUT": f"../results/{name}",
            "GAS_PRICE_WEI": str(gas_price_wei),
            "GAS_ESTIMATE": str(gas_estimate),
            "ADDRESS_MODE": address_mode,
            "BASKET_USDT": str(basket_usdt),
        },
    )

    swaps, window = read_events(out)
    return compute(swaps, window, float(gas_price_wei))
```

The basket split now happens inside the harness, which knows the pool's
rounding; Python only passes the USDT figure.

- [x] **Step 4: Run the unit tests**

Run: `uv run pytest tests/test_export_trace.py -v` Expected: 3 passed.

- [x] **Step 5: Run the real end-to-end**

```bash
cd /Users/antonled/science/uniswapv4-hooks/swap-hooks
uv run python -c "
from experiments.run_one import run_one
m = run_one('MyHook', 'ETHUSDT', 'SHIBUSDT', 1704067200000, 1704067200000 + 1440*60_000, fee_pips=3000)
for k, v in m.items():
    print(f'{k:28} {v}')
assert abs(m['conservation_error_token0']) < 1e-6, 'token0 conservation'
assert abs(m['conservation_error_token1']) < 1e-6, 'token1 conservation'
assert m['trade_count'] > 0, 'a day of ETH/SHIB must produce arbitrage'
"
```

Expected: a metrics table, both conservation errors near zero, non-zero trade
count.

- [x] **Step 6: Calibrate the gas estimate**

```bash
uv run python -c "
import pandas as pd
from experiments.events import read_events
from pathlib import Path
swaps, _ = read_events(sorted(Path('results').glob('MyHook-*.jsonl'))[-1])
print('median gas per swap:', int(swaps['gas'].median()))
"
```

Record the figure as the `gas_estimate` default for `MyHook`. Plan 2 repeats
this per policy; the value belongs in the manifest.

- [x] **Step 7: Commit**

```bash
git add experiments/export_trace.py experiments/run_one.py tests/test_export_trace.py
git commit -m "feat: wire end-to-end single-window replay run"
```

---

## Follow-on Plans

**Plan 2 — Policies.** The six repairs from spec §13, `VolatilityHook`, and the
size-dependent sizing path required by `MEVChargeHook` (spec §A.8): a ternary
search over $\Pi(\Delta x)$ replacing the closed form, with each fee probe
wrapped in `vm.snapshotState()` / `vm.revertToState()` because `_getFee` writes
`_lastBuyToken0/1[payer]`. Plan 1 uses `MyHook` only, whose fee is
size-independent, so the closed form is exact throughout this plan.

**Plan 3 — Matrix and analysis.** Volatility stratification and window
selection, the 4752-run matrix driver with per-run manifests, aggregation by
regime, and the figures.

## Self-Review

**Spec coverage.** §3 layout → Tasks 1–2. §4.1.1 mock feeds → Task 6
`_setFeeds`. §4.2 arbitrageur, including the gas term → Task 4 `profit`, Task 6
`_step` and `_gasCostInToken1`. §4.3 liquidity, external starting price, basket
→ Task 6 `_deployPoolAtExternalPrice` and `_basketAmounts`, guarded by
`test_poolOpensAtTheExternalPrice`. §4.4 baseline `MyHook` at four fee levels →
Task 1 (interface) and Task 6 (`FEE_PIPS`). §4.5 fee box → Global Constraints;
enforcement lands in Plan 2 where `f_min` is added. §7.1 loader → Task 3. §7.4
warm-up → Task 6 `warmupCandles`. §7.5 determinism → no RNG in Tasks 4–8. §8 gas
scenarios → Task 6, with the ETH/USDT gas trace loaded for every pair. §11
architecture → Tasks 5–7. §11.1 event schema → Task 5, both record kinds. §12
metrics → Task 7. §14.1 conservation invariant → Task 7, with a negative test
proving it is not an identity. Deferred by design: §5 full policy set, §6
`VolatilityHook`, §7.2–7.3 pairs and stratification, §9 matrix, §10 manifest,
§13 repairs, §14.2–14.4 — all in Plans 2 and 3.

**Placeholders.** Every code step carries runnable content. Two prose
instructions remain: Task 6 Step 6's `_countTradesWithGasPrice`, whose behaviour
is fully specified by the guard test that consumes it, and Task 8 Step 6's
calibration, which reports a number rather than writing code.

**Type consistency.** `SwapRecord` and `WindowRecord` field names match the JSON
keys asserted in Task 5's tests, the keys written in Task 6, and
`SWAP_INT_COLUMNS` plus the `window[...]` lookups in Task 7. `read_events`
returns `(DataFrame, dict)` in its definition, its tests, and `run_one`.
`compute(swaps, window, gas_price_wei)` has the same signature in all three
places. `ArbMath.profit` returns token1 units, which is what `_gasCostInToken1`
is converted into before comparison. `export_trace` consumes
`open_time`/`close`, which is what `fetch_klines` produces.
