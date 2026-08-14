// SPDX-License-Identifier: MIT
pragma solidity ^0.8.30;

import {Test} from "forge-std/Test.sol";

import {TickMath} from "@uniswap/v4-core/src/libraries/TickMath.sol";
import {FullMath} from "@uniswap/v4-core/src/libraries/FullMath.sol";
import {SqrtPriceMath} from "@uniswap/v4-core/src/libraries/SqrtPriceMath.sol";
import {StateLibrary} from "@uniswap/v4-core/src/libraries/StateLibrary.sol";
import {LPFeeLibrary} from "@uniswap/v4-core/src/libraries/LPFeeLibrary.sol";
import {LiquidityAmounts} from "@uniswap/v4-core/test/utils/LiquidityAmounts.sol";
import {Constants} from "@uniswap/v4-core/test/utils/Constants.sol";
import {IPoolManager, SwapParams} from "@uniswap/v4-core/src/interfaces/IPoolManager.sol";
import {IHooks} from "@uniswap/v4-core/src/interfaces/IHooks.sol";
import {PoolKey} from "@uniswap/v4-core/src/types/PoolKey.sol";
import {PoolIdLibrary} from "@uniswap/v4-core/src/types/PoolId.sol";
import {Currency} from "@uniswap/v4-core/src/types/Currency.sol";

import {IPositionManager} from "@uniswap/v4-periphery/src/interfaces/IPositionManager.sol";

import {Math} from "@openzeppelin/contracts/utils/math/Math.sol";
import {MockERC20} from "solmate/src/test/utils/mocks/MockERC20.sol";

import {HookTest} from "./utils/HookTest.sol";
import {EventLog} from "./utils/EventLog.sol";
import {EasyPosm} from "./utils/libraries/EasyPosm.sol";
import {ArbMath} from "../src/libraries/ArbMath.sol";
import {UUMath} from "../src/libraries/UUMath.sol";
import {PegStabilityHook} from "../src/PegStabilityHook.sol";

/**
 * @notice Replays a historical window against one policy and records raw
 *         observations. It derives nothing: every metric is computed in Python
 *         from the emitted JSONL.
 *
 * Three properties this harness must hold, each of which the previous framework
 * got wrong:
 *   1. The pool opens at the external price, not at 1:1. For ETH/SHIB the true
 *      ratio is around 6.7e-9; opening at 1 would hand the first arbitrageur an
 *      eight-order-of-magnitude free lunch.
 *   2. The arbitrageur weighs profit against gas. Without that the three gas
 *      scenarios in the matrix produce identical results and "gas affects flow"
 *      is absent from the model.
 *   3. Swap amounts come from SqrtPriceMath, never hand-rolled algebra, so the
 *      rounding matches the pool exactly.
 */
contract ReplayTest is Test, HookTest {
    using StateLibrary for IPoolManager;
    using PoolIdLibrary for PoolKey;
    // `using` is contract-scoped in Solidity, so HookTest's directive for
    // EasyPosm does not reach here and must be repeated.
    using EasyPosm for IPositionManager;

    uint256 constant Q96 = 1 << 96;
    uint256 constant PRICE_SCALE = 1e8;
    uint256 constant ONE_PIPS = 1e6;

    /// @dev (2/3)^24 shrinks the bracket to about 6e-5 of its width, well below
    ///      anything the fee can act on. Each iteration costs two external
    ///      calls, so this is the term that decides run time.
    uint256 constant TERNARY_ITERATIONS = 24;

    /// @dev One candle is one minute of market data, so the clock must advance
    ///      by 60 seconds. It advanced by 12 -- Ethereum's block time -- which
    ///      compressed the simulated timeline five-fold against the data and
    ///      made MEVChargeHook's 15-second cooldown span more than a candle
    ///      when it should span a quarter of one. Blocks advance at the real
    ///      cadence for the same reason; policies that gate on block.number see
    ///      one swap per candle either way.
    uint256 constant SECONDS_PER_CANDLE = 60;
    uint256 constant BLOCKS_PER_CANDLE = 5;

    string outPath;
    uint256 gasPriceWei;
    uint256 gasEstimate;
    uint256 warmupCandles;
    bool freshAddress;
    bool logging = true;

    /// @dev Declared per run rather than detected: the closed form stays the
    ///      default and the choice is recorded in the manifest. Only
    ///      MEVChargeHook needs this — its impact surcharge reads
    ///      `amountSpecified`, so the fee is a function of the trade size and
    ///      the closed form of spec §A.2 no longer applies.
    bool sizeDependent;

    uint256[] price0;
    uint256[] price1;
    uint256[] priceGasEth; // ETH/USDT, used only to value gas

    /// @dev UU flow (spec 2026-08-09-uu-flow-design.md). `UU_TRACE` unset or
    ///      empty leaves `uuEnabled` false and every candle's `_uuStep` a
    ///      no-op -- exact old behaviour (spec §10.2 differential golden).
    bool uuEnabled;
    bool uuDiscrete;
    uint256 uuLambdaWad;
    uint256[] uuSizeAB;
    uint256[] uuUAB;
    uint256[] uuSizeBA;
    uint256[] uuUBA;

    int24 tickLower;
    int24 tickUpper;
    uint160 sqrtPriceInitialX96;
    uint256 initialToken0;
    uint256 initialToken1;
    uint256 feeGrowth0Initial;
    uint256 feeGrowth1Initial;
    /// @dev Recorded with the rest of the baseline. These used to be written
    ///      from candle 0 while the holdings beside them came from the warm-up
    ///      boundary, so anything valuing those holdings at these prices was
    ///      off by the warm-up's price movement.
    uint256 baselinePrice0;
    uint256 baselinePrice1;
    uint256 tradeCount;

    // ------------------------------------------------------------------ setup

    function setUp() public {
        deployArtifactsAndLabel();
        deployCurrencyPair();
        deployHookAndFeeds(vm.envOr("HOOK_NAME", string("MyHook")));

        outPath = vm.envOr("OUT", string("../results/replay.jsonl"));
        gasPriceWei = vm.envOr("GAS_PRICE_WEI", uint256(20 gwei));
        gasEstimate = vm.envOr("GAS_ESTIMATE", uint256(76_578));
        warmupCandles = vm.envOr("WARMUP_CANDLES", uint256(60));
        freshAddress = keccak256(bytes(vm.envOr("ADDRESS_MODE", string("persistent")))) == keccak256(bytes("fresh"));
        sizeDependent = vm.envOr("SIZE_DEPENDENT", false);

        _loadTrace(vm.envOr("TRACE0", string("../data/trace0.csv")), price0);
        _loadTrace(vm.envOr("TRACE1", string("../data/trace1.csv")), price1);
        _loadTrace(vm.envOr("TRACE_GAS", string("../data/trace_gas.csv")), priceGasEth);
        require(price0.length == price1.length, "trace length mismatch");
        require(price0.length == priceGasEth.length, "gas trace length mismatch");
        require(price0.length > warmupCandles + 1, "trace shorter than the warm-up");

        string memory uuTracePath = vm.envOr("UU_TRACE", string(""));
        uuEnabled = bytes(uuTracePath).length != 0;
        if (uuEnabled) {
            string memory uuMode = vm.envOr("UU_MODE", string("share"));
            uuDiscrete = keccak256(bytes(uuMode)) == keccak256(bytes("discrete"));
            uuLambdaWad = vm.envOr("UU_LAMBDA_WAD", uint256(461_404_973_192_736_927_635));
            _loadUuTrace(uuTracePath);
            require(uuSizeAB.length == price0.length, "uu trace length mismatch");
        }

        if (vm.exists(outPath)) vm.removeFile(outPath);

        _setFeeds(0);
        _deployPoolAtExternalPrice();

        uint24 feePips = uint24(vm.envOr("FEE_PIPS", uint256(0)));
        if (feePips != 0) hookContract.setFee(feePips, poolKey);

        // Sensitivity axis, not part of the pre-registered matrix: PegCapture's
        // headline advantage rests on this constant, so it has to be swept and
        // reported rather than asserted. Zero leaves the contract default.
        uint256 share = vm.envOr("CAPTURE_SHARE", uint256(0));
        if (share != 0) PegStabilityHook(address(hookContract)).setCaptureShare(share);
    }

    /// @notice Test-only configuration seam for composed harnesses (see
    ///         `ReplayUUTest`): repeats `setUp`'s deployment path, but by
    ///         direct parameter rather than env var.
    /// @dev Env vars are process-global, and forge runs a file's test
    ///      functions concurrently; a composed test that drives several
    ///      isolated `ReplayTest` instances via `vm.setEnv` races across
    ///      those concurrent functions and silently cross-wires which run
    ///      reads which configuration. This function exists so that call
    ///      site can configure a freshly-`new`'d instance directly instead.
    ///      Intended for exactly one call on a fresh instance -- unlike
    ///      `setUp`, it does not reset the trace arrays first.
    function configureForTest(
        string memory trace0Path,
        string memory trace1Path,
        string memory traceGasPath,
        string memory outPath_,
        uint256 gasPriceWei_,
        uint256 warmupCandles_,
        uint256 feePips,
        bool withUu,
        string memory uuTracePath
    ) public {
        deployArtifactsAndLabel();
        deployCurrencyPair();
        deployHookAndFeeds("MyHook");

        outPath = outPath_;
        gasPriceWei = gasPriceWei_;
        gasEstimate = 76_578;
        warmupCandles = warmupCandles_;
        freshAddress = false;
        sizeDependent = false;

        _loadTrace(trace0Path, price0);
        _loadTrace(trace1Path, price1);
        _loadTrace(traceGasPath, priceGasEth);
        require(price0.length == price1.length, "trace length mismatch");
        require(price0.length == priceGasEth.length, "gas trace length mismatch");
        require(price0.length > warmupCandles + 1, "trace shorter than the warm-up");

        uuEnabled = withUu;
        if (withUu) {
            uuDiscrete = false;
            uuLambdaWad = 461_404_973_192_736_927_635;
            _loadUuTrace(uuTracePath);
            require(uuSizeAB.length == price0.length, "uu trace length mismatch");
        }

        if (vm.exists(outPath)) vm.removeFile(outPath);

        _setFeeds(0);
        _deployPoolAtExternalPrice();

        if (feePips != 0) hookContract.setFee(uint24(feePips), poolKey);
    }

    /// @dev Replaces HookTest.deployPool, which hardcodes SQRT_PRICE_1_1.
    function _deployPoolAtExternalPrice() internal {
        sqrtPriceInitialX96 = _sqrtPriceFromExternal(0);

        poolKey = PoolKey(currency0, currency1, LPFeeLibrary.DYNAMIC_FEE_FLAG, tickSpacing, IHooks(hookContract));
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
            poolKey,
            tickLower,
            tickUpper,
            liq,
            want0 * 2,
            want1 * 2,
            address(this),
            block.timestamp,
            Constants.ZERO_BYTES
        );

        _captureBaseline(0);

        // Preconditions the fee accounting in the Python metrics depends on.
        //
        // `feeGrowthInside * L` equals the fees owed to the position only when
        // the position's own snapshot is zero. That holds because the mint
        // happens immediately after initialize with no swap in between. A
        // warm-up placed before the mint, or a second position, would break it
        // silently -- so assert rather than assume.
        (uint256 fg0, uint256 fg1) = poolManager.getFeeGrowthInside(poolId, tickLower, tickUpper);
        require(fg0 == 0 && fg1 == 0, "position minted after fee growth began");

        // A non-zero protocol fee diverts part of the swap fee away from
        // feeGrowthInside, which would fail the conservation check for a reason
        // unrelated to this harness.
        (,, uint24 protocolFee,) = poolManager.getSlot0(poolId);
        require(protocolFee == 0, "protocol fee must be off");
    }

    /// @notice Snapshots the reference point the metrics measure from.
    /// @dev Taken at the end of warm-up, not at candle 0. Warm-up swaps execute
    ///      but are not logged, so a candle-0 baseline cannot be reconciled
    ///      against the logged flow -- the token conservation check fails by
    ///      exactly the warm-up's trading.
    function _captureBaseline(uint256 candle) internal {
        (sqrtPriceInitialX96,,,) = poolManager.getSlot0(poolId);
        baselinePrice0 = price0[candle];
        baselinePrice1 = price1[candle];
        (initialToken0, initialToken1) = LiquidityAmounts.getAmountsForLiquidity(
            sqrtPriceInitialX96,
            TickMath.getSqrtPriceAtTick(tickLower),
            TickMath.getSqrtPriceAtTick(tickUpper),
            poolManager.getLiquidity(poolId)
        );
        (feeGrowth0Initial, feeGrowth1Initial) = poolManager.getFeeGrowthInside(poolId, tickLower, tickUpper);
    }

    /// @notice Basket of BASKET_USDT split equally by value at window start.
    /// @dev Mock tokens are 18-decimal on both sides; prices are 1e8-scaled.
    function _basketAmounts() internal view returns (uint256 amount0, uint256 amount1) {
        uint256 halfUsdt = vm.envOr("BASKET_USDT", uint256(20_000_000)) / 2;
        amount0 = FullMath.mulDiv(halfUsdt * 1e18, PRICE_SCALE, price0[0]);
        amount1 = FullMath.mulDiv(halfUsdt * 1e18, PRICE_SCALE, price1[0]);
    }

    /// @notice sqrt(price0/price1) * 2^96 for the given candle.
    function _sqrtPriceFromExternal(uint256 i) internal view returns (uint160) {
        uint256 priceX96 = FullMath.mulDiv(price0[i], Q96, price1[i]);
        return uint160(Math.sqrt(FullMath.mulDiv(priceX96, Q96, 1)));
    }

    // ------------------------------------------------------------------ guards

    /// @dev Guard: the pool must open at the external price, not at 1:1.
    function test_poolOpensAtTheExternalPrice() public view {
        (uint160 current,,,) = poolManager.getSlot0(poolId);
        assertApproxEqRel(uint256(current), uint256(_sqrtPriceFromExternal(0)), 1e12);
    }

    /// @dev Guard: expensive gas must widen the entry threshold and suppress
    ///      marginal trades. Without this the gas axis of the matrix is inert.
    function test_gasCostSuppressesMarginalTrades() public {
        uint256 cheap = _countTradesWithGasPrice(1);
        uint256 dear = _countTradesWithGasPrice(1_000_000 gwei);
        assertGt(cheap, 0, "cheap gas must permit some arbitrage");
        assertLt(dear, cheap, "expensive gas must reduce the trade count");
    }

    /// @dev Runs a prefix of the trace at the given gas price and counts
    ///      executed swaps. State is snapshotted and restored so the two calls
    ///      are independent, and logging is off so the runs leave no file
    ///      behind -- forge never rolls back filesystem writes.
    function _countTradesWithGasPrice(uint256 price) internal returns (uint256 count) {
        uint256 snap = vm.snapshotState();

        gasPriceWei = price;
        logging = false;
        tradeCount = 0;

        uint256 startBlock = block.number;
        uint256 limit = price0.length < 120 ? price0.length : 120;
        for (uint256 i = 1; i < limit; i++) {
            _setFeeds(i);
            vm.roll(startBlock + i * BLOCKS_PER_CANDLE);
            vm.warp(block.timestamp + SECONDS_PER_CANDLE);
            _uuStep(i);
            _step(i);
        }
        count = tradeCount;

        // Deleted, not merely reverted: `revertToState` restores the state and
        // keeps the snapshot alive at ~1.6 MB. Same rule as `_optimalSize`.
        vm.revertToState(snap);
        vm.deleteStateSnapshot(snap);
    }

    // ------------------------------------------------------------------ replay

    function testReplay() public {
        uint256 startBlock = block.number;
        for (uint256 i = 1; i < price0.length; i++) {
            _setFeeds(i);
            vm.roll(startBlock + i * BLOCKS_PER_CANDLE);
            vm.warp(block.timestamp + SECONDS_PER_CANDLE);
            if (i == warmupCandles) _captureBaseline(i);
            _uuStep(i);
            _step(i);
        }
        _writeWindowRecord();
    }

    function _step(uint256 candle) internal {
        uint256 extPriceX96 = FullMath.mulDiv(price0[candle], Q96, price1[candle]);
        (uint160 sqrtBefore,,,) = poolManager.getSlot0(poolId);
        uint128 liq = poolManager.getLiquidity(poolId);
        if (liq == 0) return;

        for (uint256 side = 0; side < 2; side++) {
            bool zeroForOne = side == 0;
            address sender = _sender(candle);

            uint256 amountIn;
            uint24 fee;
            uint256 expected;

            if (sizeDependent) {
                (amountIn, fee, expected) = _optimalSize(zeroForOne, extPriceX96, sqrtBefore, liq, sender);
                if (amountIn == 0) continue;
            } else {
                fee = _feeFor(zeroForOne);
                uint160 target = ArbMath.targetSqrtPriceX96(extPriceX96, fee, zeroForOne);
                if (!ArbMath.shouldTrade(sqrtBefore, target, zeroForOne)) continue;

                // Library amounts, not hand-rolled algebra: the rounding must
                // match the pool.
                uint256 netIn = zeroForOne
                    ? SqrtPriceMath.getAmount0Delta(target, sqrtBefore, liq, true)
                    : SqrtPriceMath.getAmount1Delta(sqrtBefore, target, liq, true);
                if (netIn == 0) continue;
                amountIn = ArbMath.grossInput(netIn, fee);
                expected = ArbMath.profit(liq, sqrtBefore, target, fee);
            }

            // Profit is denominated in token1; so is the gas cost it faces.
            if (expected <= _gasCostInToken1(candle)) continue;

            _executeArb(candle, zeroForOne, fee, amountIn, sqrtBefore, expected);
            return;
        }
    }

    // ------------------------------------------------------------------ UU flow

    /// @notice Runs the deterministic-share UU flow for one candle, both
    ///         directions, before the arbitrageur (spec §4): update feeds ->
    ///         UU A->B -> UU B->A -> arbitrage check.
    function _uuStep(uint256 candle) internal {
        if (!uuEnabled) return;

        for (uint256 side = 0; side < 2; side++) {
            bool zeroForOne = side == 0;
            uint256 sizeWad = zeroForOne ? uuSizeAB[candle] : uuSizeBA[candle];
            uint256 uWad = zeroForOne ? uuUAB[candle] : uuUBA[candle];
            if (sizeWad == 0) continue;

            (uint160 s,,,) = poolManager.getSlot0(poolId);
            uint256 extPriceX96 = FullMath.mulDiv(price0[candle], Q96, price1[candle]);
            address sender = _uuSender(candle, zeroForOne);
            uint256 priceIn = zeroForOne ? price0[candle] : price1[candle];

            // The fee is quoted on the candle's POTENTIAL volume, before
            // thinning. A size-dependent policy makes the fee a function of the
            // trade size, and the size is a function of P, which is a function
            // of the fee -- a loop. Spec §2.2 already dropped slippage to break
            // the identical loop through P -> size -> slippage -> P, and the
            // same reasoning applies here: quote at a size that is known before
            // P, so the computation stays closed-form and deterministic.
            //
            // The alternative, quoting at zero size, is what this replaces: it
            // let a size-dependent policy advertise its base rate and charge
            // the surcharge, i.e. users decided on a price they were not given.
            uint256 potentialAmountIn = FullMath.mulDiv(sizeWad, PRICE_SCALE, priceIn);

            // Critical detail (spec §4, plan Task 4): the fee used for r must
            // be read via a state snapshot too. MEVChargeHook's _getFee
            // writes _lastBuyToken0/1[payer] even on a read-only call -- see
            // the identical hazard documented at _executeArb's logging read.
            uint256 snap = vm.snapshotState();
            uint24 fee = _feeForSender(sender, zeroForOne, potentialAmountIn);
            vm.revertToState(snap);
            vm.deleteStateSnapshot(snap);

            // `r` is the source model's normalised, realised disadvantage --
            // it needs the liquidity and the size, because slippage is inside
            // it by construction. Evaluated at the POTENTIAL slice, which is
            // known before P, so the fee -> P -> size -> fee loop stays broken.
            int256 r = UUMath.rWad(
                s, poolManager.getLiquidity(poolId), extPriceX96, fee, zeroForOne, potentialAmountIn, _uuGasCost(candle)
            );
            uint256 p = UUMath.participationWad(r, uuLambdaWad);

            // share mode: multiplicative thinning. discrete mode: all-or-
            // nothing against the pre-drawn uniform (spec §2.3-2.4).
            uint256 usdtWad = uuDiscrete ? (uWad <= p ? sizeWad : 0) : FullMath.mulDiv(sizeWad, p, 1e18);
            if (usdtWad == 0) continue;

            // USDT-wad -> input token units at the candle's external price.
            uint256 amountIn = FullMath.mulDiv(usdtWad, PRICE_SCALE, priceIn);
            if (amountIn == 0) continue;

            _executeUU(candle, zeroForOne, fee, amountIn, s, r, p);
        }
    }

    /// @dev Fresh address per candle and direction: UU flow is a continuum of
    ///      small users, not a persistent trader (spec §4).
    function _uuSender(uint256 candle, bool zeroForOne) internal pure returns (address) {
        return address(uint160(uint256(keccak256(abi.encode("uu", candle, zeroForOne)))));
    }

    function _executeUU(
        uint256 candle,
        bool zeroForOne,
        uint24 fee,
        uint256 amountIn,
        uint160 sqrtBefore,
        int256 rWad_,
        uint256 pWad_
    ) internal {
        address sender = _uuSender(candle, zeroForOne);
        if (amountIn == 0) return;

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

        tradeCount++;

        if (!logging || candle < warmupCandles) return;

        int256 delta0 = int256(currency0.balanceOf(sender)) - int256(bal0Before);
        int256 delta1 = int256(currency1.balanceOf(sender)) - int256(bal1Before);
        (uint160 sqrtAfter,,,) = poolManager.getSlot0(poolId);

        // Same hazard as _executeArb's logging read: wrap in a snapshot.
        // Quoted at the amount actually swapped, so the logged fee is the fee
        // the pool charged. At zero size a size-dependent policy reports its
        // base rate and the surcharge never reaches the log.
        uint256 snap = vm.snapshotState();
        uint24 recordedFeeAB = _feeForSender(sender, true, amountIn);
        uint24 recordedFeeBA = _feeForSender(sender, false, amountIn);
        vm.revertToState(snap);
        vm.deleteStateSnapshot(snap);

        EventLog.writeSwap(
            vm,
            outPath,
            EventLog.SwapRecord({
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
                feeAB: recordedFeeAB,
                feeBA: recordedFeeBA,
                delta0: delta0,
                delta1: delta1,
                expectedProfit: 0,
                gas: gasUsed,
                sender: sender,
                trader: "uu",
                rWad: rWad_,
                pWad: pWad_,
                extPriceGas: int256(priceGasEth[candle])
            })
        );
    }

    /// @notice Gas cost of one swap, expressed in token1 units.
    /// @dev gasEstimate is a per-policy constant from a calibration run; a real
    ///      arbitrageur likewise decides on an estimate rather than the realised
    ///      cost. The realised gas is recorded per swap for reporting.
    ///
    ///      The default 76_578 is the measured median for MyHook (55_578 of
    ///      execution gas) plus the 21_000 intrinsic cost of a transaction.
    ///      Plan 2 Task 9 replaces it per policy. It is not a free parameter:
    ///      an earlier placeholder of 180_000 suppressed roughly twice as many
    ///      trades as reality.
    /// @dev The same gas bill as `_gasCostInToken1`, denominated in token1 for
    ///      BOTH directions -- `UUMath.rWad` values both of its legs in token1
    ///      in both branches (`valueOut` for B->A is amount0 times the
    ///      token1-per-token0 external price, i.e. token1), so the gas term
    ///      must be token1 too. Retail pays gas like anyone else; leaving it
    ///      out is what made the gas axis inert.
    ///
    ///      HISTORY (2026-08-12): this used to convert through `price0` for
    ///      the B->A direction, following a comment that claimed `rWad` values
    ///      that direction in token0 -- it does not. On the volatile pairs
    ///      that understated B->A retail gas by price0/price1 (~2,300x on
    ///      ETH/USDC, ~2e8x on ETH/SHIB), so only A->B retail was priced out
    ///      by gas and the retail flow acquired an artificial directional
    ///      imbalance that grew with the gas scenario. Every UU run before
    ///      this date carries that defect. Pinned by
    ///      `test_uuHighGasSuppressesBothDirections`.
    function _uuGasCost(uint256 candle) internal view returns (uint256) {
        uint256 weiCost = gasEstimate * gasPriceWei;
        uint256 usdtCost = FullMath.mulDiv(weiCost, priceGasEth[candle], PRICE_SCALE);
        if (price1[candle] == 0) return 0;
        return FullMath.mulDiv(usdtCost, PRICE_SCALE, price1[candle]);
    }

    function _gasCostInToken1(uint256 candle) internal view returns (uint256) {
        uint256 weiCost = gasEstimate * gasPriceWei; // wei of ETH
        uint256 usdtCost = FullMath.mulDiv(weiCost, priceGasEth[candle], PRICE_SCALE);
        return FullMath.mulDiv(usdtCost, PRICE_SCALE, price1[candle]);
    }

    function _sender(uint256 candle) internal view returns (address) {
        return freshAddress ? address(uint160(uint256(keccak256(abi.encode("arb", candle))))) : address(this);
    }

    /// @notice Reads the fee for a candidate size.
    /// @dev MEVChargeHook's `_getFee` writes `_lastBuyToken0/1[payer]`, so this
    ///      is NOT free of side effects. The whole search is wrapped in one
    ///      snapshot instead of one per probe: within a block the write is
    ///      invisible to later reads of the same direction, because
    ///      `_calculateTimeFee` returns early on `nowTs <= ts`. It only leaks
    ///      into the NEXT candle, and the outer revert removes it. Snapshotting
    ///      per probe costs two orders of magnitude more and exhausts the gas
    ///      limit on a full window.
    function _probeFee(address sender, bool zeroForOne, uint256 amount) internal returns (uint24) {
        return hookContract.getFee(
            sender,
            poolKey,
            SwapParams({zeroForOne: zeroForOne, amountSpecified: int256(amount), sqrtPriceLimitX96: 0}),
            ""
        );
    }

    /// @notice Arbitrage profit in token1 for a candidate gross input.
    function _profitAt(bool zeroForOne, uint256 grossIn, uint160 s, uint128 liq, uint256 extPriceX96, address sender)
        internal
        returns (uint256 profit, uint24 f)
    {
        if (grossIn == 0) return (0, 0);
        f = _probeFee(sender, zeroForOne, grossIn);

        uint256 netIn = FullMath.mulDiv(grossIn, ONE_PIPS - uint256(f), ONE_PIPS);
        if (netIn == 0) return (0, f);

        uint160 s2 = SqrtPriceMath.getNextSqrtPriceFromInput(s, liq, netIn, zeroForOne);
        if (zeroForOne) {
            uint256 out = SqrtPriceMath.getAmount1Delta(s2, s, liq, false);
            uint256 cost = FullMath.mulDiv(grossIn, extPriceX96, Q96);
            profit = out > cost ? out - cost : 0;
        } else {
            uint256 out = SqrtPriceMath.getAmount0Delta(s, s2, liq, false);
            uint256 value = FullMath.mulDiv(out, extPriceX96, Q96);
            profit = value > grossIn ? value - grossIn : 0;
        }
    }

    /// @notice Maximises profit over trade size when the fee depends on it.
    /// @dev Profit stays unimodal because a fee increasing in size only makes
    ///      it more concave, so a ternary search converges.
    function _optimalSize(bool zeroForOne, uint256 extPriceX96, uint160 s, uint128 liq, address sender)
        internal
        returns (uint256 amountIn, uint24 f, uint256 profit)
    {
        // Nothing above the zero-fee optimum can win, because a larger fee only
        // shrinks the optimal size. This also prunes candles with no trade.
        uint160 freeTarget = ArbMath.targetSqrtPriceX96(extPriceX96, 0, zeroForOne);
        if (!ArbMath.shouldTrade(s, freeTarget, zeroForOne)) return (0, 0, 0);

        // One snapshot for the whole search: the probes write hook state and
        // must leave no trace behind them. See _probeFee for why one is enough.
        //
        // It MUST be deleted after reverting. `revertToState` restores the
        // state but keeps the snapshot itself alive, at roughly 1.6 MB each.
        // Over a 1440-candle window that is 2880 snapshots and 4.6 GB of
        // retained memory for one process -- enough to exhaust a machine once
        // several run in parallel.
        uint256 snap = vm.snapshotState();

        uint256 hi = zeroForOne
            ? SqrtPriceMath.getAmount0Delta(freeTarget, s, liq, true)
            : SqrtPriceMath.getAmount1Delta(s, freeTarget, liq, true);
        if (hi == 0) {
            // Returning here used to leak the snapshot taken above -- the one
            // failure mode this whole comment block exists to prevent. Rare on
            // the shipped matrix, but `hi == 0` is the degenerate-size branch,
            // and the kappa sweep's low-retail levels are exactly where
            // degenerate sizes become common.
            vm.revertToState(snap);
            vm.deleteStateSnapshot(snap);
            return (0, 0, 0);
        }
        hi = hi * 2; // the gross input exceeds the net by the fee

        uint256 lo = 0;
        for (uint256 i = 0; i < TERNARY_ITERATIONS; i++) {
            uint256 third = (hi - lo) / 3;
            if (third == 0) break;
            (uint256 p1,) = _profitAt(zeroForOne, lo + third, s, liq, extPriceX96, sender);
            (uint256 p2,) = _profitAt(zeroForOne, hi - third, s, liq, extPriceX96, sender);
            if (p1 < p2) lo = lo + third;
            else hi = hi - third;
        }

        amountIn = (lo + hi) / 2;
        (profit, f) = _profitAt(zeroForOne, amountIn, s, liq, extPriceX96, sender);

        vm.revertToState(snap);
        vm.deleteStateSnapshot(snap);
    }

    function _executeArb(
        uint256 candle,
        bool zeroForOne,
        uint24 fee,
        uint256 amountIn,
        uint160 sqrtBefore,
        uint256 expectedProfit
    ) internal {
        address sender = _sender(candle);
        if (amountIn == 0) return;

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

        tradeCount++;

        if (!logging || candle < warmupCandles) return;

        int256 delta0 = int256(currency0.balanceOf(sender)) - int256(bal0Before);
        int256 delta1 = int256(currency1.balanceOf(sender)) - int256(bal1Before);
        (uint160 sqrtAfter,,,) = poolManager.getSlot0(poolId);

        // Measured gas is sensitive to what the harness touched just before the
        // swap, because warm storage slots are cheaper to read: this snapshot
        // moves the golden window's realised gas by 6e-5 relative. That is far
        // below the granularity of `gasEstimate`, the per-policy median that
        // actually gates entry, so correctness of hook state wins over it.
        //
        // Reading the two directional fees is NOT free of side effects:
        // MEVChargeHook's _getFee stamps _lastBuyToken0/1[payer] on every call,
        // including read-only ones. Unwrapped, these two logging reads stamped
        // BOTH directions after every swap and fed a fee the policy never
        // charged into the next candle. It is dormant today only because that
        // policy trades far more rarely than its 15-second cooldown -- adding
        // uninformed order flow would wake it up. The snapshot is deleted, not
        // merely reverted; see _optimalSize.
        // Quoted at the amount actually swapped, so the logged fee is the fee
        // the pool charged. At zero size a size-dependent policy reports its
        // base rate and the surcharge never reaches the log.
        uint256 snap = vm.snapshotState();
        uint24 recordedFeeAB = _feeForSender(sender, true, amountIn);
        uint24 recordedFeeBA = _feeForSender(sender, false, amountIn);
        vm.revertToState(snap);
        vm.deleteStateSnapshot(snap);

        EventLog.writeSwap(
            vm,
            outPath,
            EventLog.SwapRecord({
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
                feeAB: recordedFeeAB,
                feeBA: recordedFeeBA,
                delta0: delta0,
                delta1: delta1,
                expectedProfit: expectedProfit,
                gas: gasUsed,
                sender: sender,
                trader: "arb",
                rWad: 0,
                pWad: 0,
                extPriceGas: int256(priceGasEth[candle])
            })
        );
    }

    /// @dev Reads the fee for one direction. Policies whose _getFee writes state
    ///      -- only MEVChargeHook, addressed in Plan 2 -- must have this call
    ///      wrapped in a state snapshot; MyHook is pure in this respect.
    function _feeFor(bool zeroForOne) internal returns (uint24) {
        return _feeForSender(_sender(0), zeroForOne, 0);
    }

    /// @dev The sender matters: MEVChargeHook derives its fee from that
    ///      address's history, so reading the fee for a different one reports a
    ///      number the pool would never charge.
    ///
    ///      So does `amountIn`, and leaving it at zero was a defect. A
    ///      `size_dependent` policy reads `amountSpecified`; asking it for the
    ///      fee on a zero-size trade returns the base rate with no size
    ///      surcharge. Measured on the 2026-08-10 UU matrix: MEVChargeHook
    ///      logged a flat 30 bps on every swap while the pool credited fees
    ///      worth about 65 bps, and the same understated number decided whether
    ///      uninformed users traded at all. Pass the amount actually being
    ///      swapped. Policies that ignore `amountSpecified` -- the other ten --
    ///      return exactly what they returned before, which is asserted by
    ///      differential test rather than assumed.
    ///
    ///      `amountIn` is the exact-input amount, so it enters as a negative
    ///      `amountSpecified`, matching what `swapExactTokensForTokens` sends.
    function _feeForSender(address who, bool zeroForOne, uint256 amountIn) internal returns (uint24) {
        return hookContract.getFee(
            who,
            poolKey,
            SwapParams({zeroForOne: zeroForOne, amountSpecified: -int256(amountIn), sqrtPriceLimitX96: 0}),
            ""
        );
    }

    function _fund(address who, bool zeroForOne, uint256 amount) internal {
        Currency c = zeroForOne ? currency0 : currency1;
        MockERC20(Currency.unwrap(c)).mint(who, amount);
        vm.prank(who);
        MockERC20(Currency.unwrap(c)).approve(address(swapRouter), type(uint256).max);
    }

    // ------------------------------------------------------------------ output

    function _writeWindowRecord() internal {
        if (!logging) return;

        (uint160 sqrtFinal,,,) = poolManager.getSlot0(poolId);
        (uint256 fg0, uint256 fg1) = poolManager.getFeeGrowthInside(poolId, tickLower, tickUpper);
        uint256 last = price0.length - 1;

        EventLog.writeWindow(
            vm,
            outPath,
            EventLog.WindowRecord({
                liquidity: poolManager.getLiquidity(poolId),
                tickLower: tickLower,
                tickUpper: tickUpper,
                sqrtPriceInitialX96: sqrtPriceInitialX96,
                sqrtPriceFinalX96: sqrtFinal,
                feeGrowthInside0X128Initial: feeGrowth0Initial,
                feeGrowthInside1X128Initial: feeGrowth1Initial,
                feeGrowthInside0X128: fg0,
                feeGrowthInside1X128: fg1,
                initialToken0: initialToken0,
                initialToken1: initialToken1,
                extPrice0Initial: int256(baselinePrice0),
                extPrice1Initial: int256(baselinePrice1),
                extPrice0Final: int256(price0[last]),
                extPrice1Final: int256(price1[last]),
                warmupCandles: warmupCandles,
                candles: price0.length
            })
        );
    }

    function _setFeeds(uint256 i) internal {
        priceFeed0.updateAnswer(int256(price0[i]));
        priceFeed1.updateAnswer(int256(price1[i]));
    }

    /// @dev Trace format: `open_time,price_1e8`, no header.
    function _loadTrace(string memory path, uint256[] storage into) internal {
        string[] memory lines = vm.split(vm.readFile(path), "\n");
        for (uint256 i = 0; i < lines.length; i++) {
            if (bytes(lines[i]).length == 0) continue;
            string[] memory f = vm.split(lines[i], ",");
            into.push(vm.parseUint(f[1]));
        }
    }

    /// @dev UU trace format (experiments/uu.py `export_uu_trace`):
    ///      `open_time,size_ab_wad,u_ab_wad,size_ba_wad,u_ba_wad`, no header.
    ///      Rows are assumed aligned 1:1 with price0/price1 by candle index;
    ///      open_time itself is not consumed here (the length check that
    ///      follows is the actual alignment guard).
    function _loadUuTrace(string memory path) internal {
        string[] memory lines = vm.split(vm.readFile(path), "\n");
        for (uint256 i = 0; i < lines.length; i++) {
            if (bytes(lines[i]).length == 0) continue;
            string[] memory f = vm.split(lines[i], ",");
            uuSizeAB.push(vm.parseUint(f[1]));
            uuUAB.push(vm.parseUint(f[2]));
            uuSizeBA.push(vm.parseUint(f[3]));
            uuUBA.push(vm.parseUint(f[4]));
        }
    }
}
