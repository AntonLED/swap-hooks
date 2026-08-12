// SPDX-License-Identifier: MIT
pragma solidity ^0.8.30;

import {Test} from "forge-std/Test.sol";

import {Constants} from "@uniswap/v4-core/test/utils/Constants.sol";
import {PoolIdLibrary} from "@uniswap/v4-core/src/types/PoolId.sol";
import {PoolKey} from "@uniswap/v4-core/src/types/PoolKey.sol";
import {Currency} from "@uniswap/v4-core/src/types/Currency.sol";
import {MockERC20} from "solmate/src/test/utils/mocks/MockERC20.sol";

import {HookTest} from "../utils/HookTest.sol";
import {ABHook} from "../../src/ABHook.sol";

/**
 * @notice ABHook is the constant-sum policy: feeAB + feeBA = K, so it can only
 *         reallocate the fee between directions, never raise the total. That
 *         property makes it the litmus comparison against a static K/2 fee.
 *
 * Two defects blocked it from doing anything at all:
 *   - `A * delta / 10000` truncated to zero for any square-root price move
 *     under 1%, which on minute data is essentially always. The hook was static.
 *   - The whole adjustment sat behind `if (isAToB)`, so state never advanced
 *     after a B->A swap.
 */
contract ABHookDeltaTest is Test, HookTest {
    using PoolIdLibrary for PoolKey;

    uint24 constant INITIAL_FEE = 3000;
    uint24 constant K = 6000;

    function setUp() public {
        deployArtifactsAndLabel();
        deployCurrencyPair();
        deployHookAndFeeds("ABHook");
        deployPool();
    }

    function _fees() internal view returns (uint24, uint24) {
        ABHook h = ABHook(address(hookContract));
        return (h.feeAB(poolId), h.feeBA(poolId));
    }

    /// @dev A swap of `amount`, sized to move the price by a small amount
    ///      typical of one minute of real data.
    function _swap(bool zeroForOne, uint256 amount) internal {
        Currency c = zeroForOne ? currency0 : currency1;
        MockERC20(Currency.unwrap(c)).mint(address(this), amount);
        swapRouter.swapExactTokensForTokens({
            amountIn: amount,
            amountOutMin: 0,
            zeroForOne: zeroForOne,
            poolKey: poolKey,
            hookData: Constants.ZERO_BYTES,
            receiver: address(this),
            deadline: block.timestamp + 1
        });
    }

    /// The pool holds 100e18 a side, so 1e17 moves the square-root price by
    /// roughly 5 bps -- an ordinary minute. Under the old arithmetic this
    /// produced no fee change whatsoever.
    function test_aSmallPriceMoveChangesTheFee() public {
        (uint24 before,) = _fees();
        _swap(true, 1e17);
        (uint24 afterFee,) = _fees();

        assertTrue(afterFee != before, "a small move must move the fee");
    }

    function test_theConstantSumSurvives() public {
        _swap(true, 1e17);
        (uint24 ab, uint24 ba) = _fees();
        assertEq(uint256(ab) + uint256(ba), K, "constant-sum invariant");
    }

    function test_sellingToken0MakesThatDirectionDearer() public {
        _swap(true, 1e17); // A -> B, price falls
        (uint24 ab,) = _fees();
        assertGt(ab, INITIAL_FEE, "the toxic direction gets dearer");
    }

    /// The `if (isAToB)` guard is redundant: the sign of delta already encodes
    /// direction, because A->B lowers the price and B->A raises it.
    function test_reactsToBothDirections() public {
        _swap(false, 1e17); // B -> A
        (uint24 ab,) = _fees();
        assertTrue(ab != INITIAL_FEE, "state must advance after a B->A swap too");
    }

    function test_oppositeDirectionsMoveTheFeeOppositeWays() public {
        // Snapshot rather than re-running setUp: that would redeploy the
        // Uniswap artifacts on top of themselves.
        uint256 snap = vm.snapshotState();
        _swap(true, 1e17);
        (uint24 afterAtoB,) = _fees();
        vm.revertToState(snap);

        _swap(false, 1e17);
        (uint24 afterBtoA,) = _fees();

        assertGt(afterAtoB, INITIAL_FEE);
        assertLt(afterBtoA, INITIAL_FEE);
    }
}
