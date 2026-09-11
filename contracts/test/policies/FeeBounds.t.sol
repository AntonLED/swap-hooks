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
import {BAHook} from "../../src/BAHook.sol";
import {DAHook} from "../../src/DAHook.sol";

/**
 * @notice The shared fee box: every policy must stay within
 *         [F_MIN, MAX_FEE] = [100, 10000] pips on every direction.
 *
 * Before this change the falling side clamped at zero, which violates
 * `f_min <= f <= f_max` from Eq. (8) of the paper and permits a direction to
 * trade free of charge.
 */
contract FeeBoundsTest is Test, HookTest {
    using PoolIdLibrary for PoolKey;

    uint24 constant F_MIN = 100;
    uint24 constant F_MAX = 10000;
    uint24 constant K = 6000; // ABHook's constant sum

    function setUp() public {
        deployArtifactsAndLabel();
        deployCurrencyPair();
    }

    function _poke(bool zeroForOne) internal {
        Currency c = zeroForOne ? currency0 : currency1;
        MockERC20(Currency.unwrap(c)).mint(address(this), 1e17);
        swapRouter.swapExactTokensForTokens({
            amountIn: 1e17,
            amountOutMin: 0,
            zeroForOne: zeroForOne,
            poolKey: poolKey,
            hookData: Constants.ZERO_BYTES,
            receiver: address(this),
            deadline: block.timestamp + 1
        });
    }

    function test_BAHook_neverLeavesTheBox() public {
        deployHookAndFeeds("BAHook");
        deployPool();

        // 20 consecutive ratio rises drive feeAB down past where zero was.
        for (uint256 i = 0; i < 20; i++) {
            vm.roll(block.number + 1);
            priceFeed1.updateAnswer(int256(30000000 - int256(i + 1) * 1000000));
            _poke(true);
        }

        BAHook h = BAHook(address(hookContract));
        assertGe(h.feeAB(poolId), F_MIN, "feeAB respects the floor");
        assertLe(h.feeBA(poolId), F_MAX, "feeBA respects the ceiling");
        assertEq(h.F_MIN(), F_MIN, "the floor must be readable from outside");
    }

    function test_DAHook_neverLeavesTheBox() public {
        deployHookAndFeeds("DAHook");
        deployPool();

        for (uint256 i = 0; i < 40; i++) {
            _poke(true);
        }

        DAHook h = DAHook(address(hookContract));
        assertLe(h.feeAB(poolId), F_MAX);
        assertGe(h.feeBA(poolId), F_MIN, "the drained side stops at the floor");
    }

    /// ABHook's constant sum must survive the floor: with K = 6000 and
    /// F_MIN = 100 the reachable range for either side is [100, 5900].
    function test_ABHook_keepsTheConstantSumInsideTheBox() public {
        deployHookAndFeeds("ABHook");
        deployPool();

        for (uint256 i = 0; i < 30; i++) {
            _poke(i % 2 == 0);
        }

        ABHook h = ABHook(address(hookContract));
        uint24 ab = h.feeAB(poolId);
        uint24 ba = h.feeBA(poolId);

        assertEq(uint256(ab) + uint256(ba), K, "constant-sum invariant");
        assertGe(ab, F_MIN);
        assertGe(ba, F_MIN);
        assertLe(ab, K - F_MIN);
        assertLe(ba, K - F_MIN);
    }
}
