// SPDX-License-Identifier: MIT
pragma solidity ^0.8.30;

import {Test} from "forge-std/Test.sol";

import {SwapParams} from "@uniswap/v4-core/src/interfaces/IPoolManager.sol";
import {PoolIdLibrary} from "@uniswap/v4-core/src/types/PoolId.sol";
import {PoolKey} from "@uniswap/v4-core/src/types/PoolKey.sol";

import {HookTest} from "../utils/HookTest.sol";
import {BAHook} from "../../src/BAHook.sol";
import {PegStabilityHook} from "../../src/PegStabilityHook.sol";

/**
 * @notice PegStabilityHook ships in two readings, decided 2026-08-02 and
 *         recorded in spec §5, because they are different policies and the
 *         comparison between them is evidence rather than an assumption.
 *
 *   PegDefence — charge the deviation-proportional fee on trades pushing the
 *                pool AWAY from the reference. Faithful to the name.
 *   PegCapture — charge proportional to |deviation| on whichever trade occurs,
 *                taxing the arbitrageur for correcting the pool.
 *
 * The distinction matters because under arbitrage-only flow every trade is
 * restoring by construction, so Defence is expected to sit at its floor
 * throughout. That is a finding about applicability, not a failure.
 */
contract PegStabilityTest is Test, HookTest {
    using PoolIdLibrary for PoolKey;

    uint24 constant MIN_FEE = 100;
    uint24 constant MAX_FEE = 10000;

    function setUp() public {
        deployArtifactsAndLabel();
        deployCurrencyPair();
    }

    function _hook() internal view returns (PegStabilityHook) {
        return PegStabilityHook(address(hookContract));
    }

    function _fee(bool zeroForOne) internal returns (uint24) {
        return hookContract.getFee(
            address(this), poolKey, SwapParams({zeroForOne: zeroForOne, amountSpecified: 0, sqrtPriceLimitX96: 0}), ""
        );
    }

    /// @dev Pool opens at 1:1. Setting token0 dearer than token1 puts the fair
    ///      price above the pool price, i.e. the pool underprices token0.
    function _setReferenceAbovePool() internal {
        priceFeed0.updateAnswer(110000000); // 1.10
        priceFeed1.updateAnswer(100000000); // 1.00
    }

    function _setReferenceBelowPool() internal {
        priceFeed0.updateAnswer(90000000); // 0.90
        priceFeed1.updateAnswer(100000000); // 1.00
    }

    // ------------------------------------------------------------- convention

    /// Both oracle-reading hooks must express token0/token1 the same way, or one
    /// of them is reading the market backwards.
    function test_ratioConventionMatchesBAHook() public {
        // The feeds are created inside deployHookAndFeeds, so they can only be
        // set afterwards.
        deployHookAndFeeds("PegCapture");
        deployPool();

        priceFeed0.updateAnswer(400000000); // token0 = 4.00
        priceFeed1.updateAnswer(100000000); // token1 = 1.00
        // Pool price is token1 per token0, so the fair price here is 4 and the
        // fair square-root price is 2 * 2^96.
        uint256 expected = 2 * (uint256(1) << 96);
        assertApproxEqRel(uint256(_hook().referenceSqrtPriceX96()), expected, 1e15);
    }

    // ------------------------------------------------------------- PegDefence

    function test_defenceChargesTheMoveAwayFromReference() public {
        deployHookAndFeeds("PegDefence");
        deployPool();
        _setReferenceAbovePool();

        // Reference above pool: selling token0 pushes the pool further below
        // the reference, so that is the move away.
        assertGt(_fee(true), MIN_FEE, "moving away must cost");
        assertEq(_fee(false), MIN_FEE, "restoring must be cheap");
    }

    function test_defenceIsSymmetricInTheOtherDirection() public {
        deployHookAndFeeds("PegDefence");
        deployPool();
        _setReferenceBelowPool();

        assertEq(_fee(true), MIN_FEE, "restoring must be cheap");
        assertGt(_fee(false), MIN_FEE, "moving away must cost");
    }

    // ------------------------------------------------------------- PegCapture

    function test_captureChargesBothDirectionsOnDeviation() public {
        deployHookAndFeeds("PegCapture");
        deployPool();
        _setReferenceAbovePool();

        assertGt(_fee(true), MIN_FEE);
        assertGt(_fee(false), MIN_FEE);
        assertEq(_fee(true), _fee(false), "capture is direction-blind");
    }

    function test_captureFeeGrowsWithDeviation() public {
        deployHookAndFeeds("PegCapture");
        deployPool();

        priceFeed0.updateAnswer(101000000); // 1% off
        priceFeed1.updateAnswer(100000000);
        uint24 small = _fee(true);

        priceFeed0.updateAnswer(105000000); // 5% off
        uint24 large = _fee(true);

        assertGt(large, small, "a wider depeg must cost more");
    }

    function test_atParityBothModesSitAtTheFloor() public {
        deployHookAndFeeds("PegCapture");
        deployPool();
        priceFeed0.updateAnswer(100000000);
        priceFeed1.updateAnswer(100000000);

        assertEq(_fee(true), MIN_FEE);
        assertEq(_fee(false), MIN_FEE);
    }

    // ------------------------------------------------------------- the box

    function test_feeStaysInsideTheBoxUnderAnExtremeDepeg() public {
        deployHookAndFeeds("PegCapture");
        deployPool();
        priceFeed0.updateAnswer(500000000); // 5x
        priceFeed1.updateAnswer(100000000);

        uint24 f = _fee(true);
        assertGe(f, MIN_FEE);
        assertLe(f, MAX_FEE);
    }

    // ------------------------------------------------------------- setFee

    /// `setFee` used to assign MAX_FEE_BPS, so calling it silently moved the
    /// ceiling instead of the fee and left no trace.
    function test_setFeeDoesNotSilentlyChangeTheCeiling() public {
        deployHookAndFeeds("PegCapture");
        deployPool();

        uint24 ceilingBefore = _hook().MAX_FEE_BPS();
        _hook().setFee(500, poolKey);

        assertEq(_hook().MAX_FEE_BPS(), ceilingBefore, "setFee must not touch the ceiling");
        assertEq(_hook().MIN_FEE_BPS(), 500, "setFee sets the floor this policy falls back to");
    }

    function test_setMaxFeeMovesTheCeiling() public {
        deployHookAndFeeds("PegCapture");
        deployPool();

        _hook().setMaxFee(8000);
        assertEq(_hook().MAX_FEE_BPS(), 8000);
    }

    /// Charging the whole deviation is provably inert: it makes the
    /// no-arbitrage band exactly wide enough to contain the current pool price,
    /// so nothing is left for the arbitrageur and no trade ever happens. This
    /// was measured as zero trades under every gas price and pool depth tried.
    function test_captureShareMustLeaveTheArbitrageurSomething() public {
        deployHookAndFeeds("PegCapture");
        deployPool();

        vm.expectRevert();
        _hook().setCaptureShare(1e6);
    }

    function test_aSmallerCaptureShareChargesLess() public {
        deployHookAndFeeds("PegCapture");
        deployPool();
        priceFeed0.updateAnswer(103000000); // 3% off
        priceFeed1.updateAnswer(100000000);

        uint24 half = _fee(true);
        _hook().setCaptureShare(100_000); // 10%
        uint24 tenth = _fee(true);

        assertLt(tenth, half, "a smaller share must charge less");
    }

    function test_theFloorCannotExceedTheCeiling() public {
        deployHookAndFeeds("PegCapture");
        deployPool();

        vm.expectRevert();
        _hook().setFee(20000, poolKey); // above MAX_FEE_BPS
    }
}
