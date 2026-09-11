// SPDX-License-Identifier: MIT
pragma solidity ^0.8.30;

import {Test} from "forge-std/Test.sol";

import {SwapParams} from "@uniswap/v4-core/src/interfaces/IPoolManager.sol";
import {PoolIdLibrary} from "@uniswap/v4-core/src/types/PoolId.sol";
import {PoolKey} from "@uniswap/v4-core/src/types/PoolKey.sol";
import {FullMath} from "@uniswap/v4-core/src/libraries/FullMath.sol";
import {StateLibrary} from "@uniswap/v4-core/src/libraries/StateLibrary.sol";
import {IPoolManager} from "@uniswap/v4-core/src/interfaces/IPoolManager.sol";

import {HookTest} from "./utils/HookTest.sol";
import {ArbMath} from "../src/libraries/ArbMath.sol";

/**
 * @notice The closed-form trade size of spec §A.2 assumes the fee does not
 *         depend on the size. MEVChargeHook breaks that: its impact surcharge
 *         reads `amountSpecified`. This exercises the numerical fallback.
 *
 * Two constraints the search has to respect, both of them traps:
 *   - `MEVChargeHook._getFee` WRITES `_lastBuyToken0/1[payer]`, so probing it
 *     in a loop would advance the history the fee is computed from and the
 *     search would optimise against its own footprints.
 *   - A fee rising with size only shrinks the optimum, so nothing above the
 *     zero-fee closed form can win — that bounds the bracket.
 */
contract SizeSearchTest is Test, HookTest {
    using PoolIdLibrary for PoolKey;
    using StateLibrary for IPoolManager;

    uint256 constant Q96 = 1 << 96;

    function setUp() public {
        deployArtifactsAndLabel();
        deployCurrencyPair();
        deployHookAndFeeds("MEVChargeHook");
        deployPool();
    }

    function _extPriceX96() internal pure returns (uint256) {
        // Pool opens at 1:1; put the fair price 3% above it so arbitrage exists.
        return (103 * Q96) / 100;
    }

    function _rawFee(bool zeroForOne, uint256 amount) internal returns (uint24) {
        return hookContract.getFee(
            address(this),
            poolKey,
            SwapParams({zeroForOne: zeroForOne, amountSpecified: int256(amount), sqrtPriceLimitX96: 0}),
            ""
        );
    }

    /// The fee genuinely varies with size, or the rest of this suite is moot.
    function test_theFeeDependsOnTradeSize() public {
        uint128 liq = poolManager.getLiquidity(poolId);
        uint24 small = _rawFee(true, 1e15);
        uint24 large = _rawFee(true, uint256(liq) / 2);

        assertTrue(small != large, "MEVChargeHook must price by size");
    }

    /// Probing must be invisible. A probe that leaves a mark would change the
    /// answer for every later probe and for the real swap.
    function test_probingDoesNotCorruptHookState() public {
        uint24 before = _rawFee(true, 1e18);

        uint256 snap = vm.snapshotState();
        for (uint256 i = 0; i < 20; i++) {
            _rawFee(true, 1e18 * (i + 1));
        }
        vm.revertToState(snap);

        assertEq(_rawFee(true, 1e18), before, "snapshot/revert must undo every probe");
    }

    /// Without the snapshot the writes leak across directions, which is the
    /// whole reason the wrapper exists. Pin it so nobody "simplifies" it away.
    ///
    /// The leak is asymmetric and easy to miss: a zeroForOne call writes
    /// `_lastBuyToken1`, while the time fee for zeroForOne reads
    /// `_lastBuyToken0`. So same-direction probes do not disturb each other —
    /// but a probe of one direction disturbs the OTHER, and `_step` evaluates
    /// both sides.
    function test_anUnwrappedProbeOfOneDirectionChangesTheOther() public {
        uint128 liq = poolManager.getLiquidity(poolId);
        // Above liq/10000 so the dynamic fee engages, but under liq/20 so the
        // impact surcharge stays in its flat branch and the time fee decides.
        uint256 amount = uint256(liq) / 1000;

        // Within one block the write is invisible: _calculateTimeFee returns
        // early on `nowTs <= ts`. It bites on the NEXT candle, while the
        // 15-second cooldown is still running -- which is exactly the pattern
        // the replay produces, one block per candle.
        uint256 snap = vm.snapshotState();
        vm.warp(block.timestamp + 12);
        uint24 clean = _rawFee(false, amount);
        vm.revertToState(snap);

        _rawFee(true, amount); // unwrapped: writes _lastBuyToken1[payer] = now
        vm.warp(block.timestamp + 12);
        uint24 dirty = _rawFee(false, amount);

        assertTrue(dirty != clean, "the cross-direction write must be visible");
        assertGt(dirty, clean, "a recent counterparty trade must cost more");
    }
}
