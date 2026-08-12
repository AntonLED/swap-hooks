// SPDX-License-Identifier: MIT
pragma solidity ^0.8.30;

import {Test} from "forge-std/Test.sol";

import {SwapParams} from "@uniswap/v4-core/src/interfaces/IPoolManager.sol";
import {IPoolManager} from "@uniswap/v4-core/src/interfaces/IPoolManager.sol";
import {StateLibrary} from "@uniswap/v4-core/src/libraries/StateLibrary.sol";
import {PoolIdLibrary} from "@uniswap/v4-core/src/types/PoolId.sol";
import {PoolKey} from "@uniswap/v4-core/src/types/PoolKey.sol";

import {HookTest} from "../utils/HookTest.sol";
import {MEVChargeHook} from "../../src/MEVChargeHook.sol";

/**
 * @notice Pins the fee-box compliance fix (2026-08-09-uu-flow-design.md §7):
 *         every harness deployment of MEVChargeHook (and MEVChargeHookFixed,
 *         which inherits the same clamp path) must stay inside the shared
 *         box every other policy respects, [1, 100] bps (spec §4.5).
 *
 * There was no MEVCharge characterisation test file in this repo before this
 * change (contracts/test/policies/ had ABHookDelta, FeeBounds, PegStability,
 * Ratchet, Volatility, but nothing for MEVCharge) -- the plan's step assumed
 * one existed to extend. This file is new, not extended, following the same
 * `Test, HookTest` + `deployHookAndFeeds`/`deployPool` pattern as its
 * siblings in this directory.
 *
 * The 2026-08-09 audit found MEVChargeHook charging up to 1000 pips on 49% of
 * its swaps against the shared box, because its default `feeMax` is 1000
 * BASIS POINTS (100000 pips) -- an order of magnitude wider than every other
 * policy's box, and a unit confusion rather than a deliberately wider box.
 */
contract MEVChargeTest is Test, HookTest {
    using PoolIdLibrary for PoolKey;
    using StateLibrary for IPoolManager;

    uint24 constant BOX_MAX_PIPS = 10000; // 100 bps, spec §4.5

    function setUp() public {
        deployArtifactsAndLabel();
        deployCurrencyPair();
    }

    /// @dev A swap sized to comfortably clear the 500bp impact trigger (the
    ///      surcharge is flat below it, see `_calculateImpactFee`), same
    ///      sizing SizeSearch.t.sol uses to force the surcharge to engage.
    function _feeAboveImpactTrigger(bool zeroForOne) internal returns (uint24) {
        uint128 liq = poolManager.getLiquidity(poolId);
        return hookContract.getFee(
            address(this),
            poolKey,
            SwapParams({zeroForOne: zeroForOne, amountSpecified: int256(uint256(liq) / 2), sqrtPriceLimitX96: 0}),
            ""
        );
    }

    function test_MEVChargeHook_stayInsideTheSharedBoxAboveTheImpactTrigger() public {
        deployHookAndFeeds("MEVChargeHook");
        deployPool();

        assertLe(_feeAboveImpactTrigger(true), BOX_MAX_PIPS, "A->B must stay inside the shared 100bps box");
        assertLe(_feeAboveImpactTrigger(false), BOX_MAX_PIPS, "B->A must stay inside the shared 100bps box");
    }

    function test_MEVChargeHookFixed_staysInsideTheSharedBoxAboveTheImpactTrigger() public {
        deployHookAndFeeds("MEVChargeHookFixed");
        deployPool();

        assertLe(_feeAboveImpactTrigger(true), BOX_MAX_PIPS, "A->B must stay inside the shared 100bps box");
        assertLe(_feeAboveImpactTrigger(false), BOX_MAX_PIPS, "B->A must stay inside the shared 100bps box");
    }

    /// @notice The harness clamp is applied via the contract's own setter,
    ///         reachable from outside -- pin the resulting config, not just
    ///         its effect, so a future edit that silently drops the clamp
    ///         call is caught here even on a swap too small to engage the
    ///         surcharge.
    function test_MEVChargeHook_effectiveFeeMaxIsClampedToTheSharedBox() public {
        deployHookAndFeeds("MEVChargeHook");
        deployPool();

        MEVChargeHook h = MEVChargeHook(address(hookContract));
        (, uint256 upperBound) = h.getFeeBounds();
        assertEq(upperBound, 100, "effectiveFeeMax must be clamped to 100 bps");
    }
}
