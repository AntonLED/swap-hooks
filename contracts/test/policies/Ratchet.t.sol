// SPDX-License-Identifier: MIT
pragma solidity ^0.8.30;

import {Test} from "forge-std/Test.sol";

import {Constants} from "@uniswap/v4-core/test/utils/Constants.sol";
import {IPoolManager} from "@uniswap/v4-core/src/interfaces/IPoolManager.sol";
import {PoolIdLibrary} from "@uniswap/v4-core/src/types/PoolId.sol";
import {PoolKey} from "@uniswap/v4-core/src/types/PoolKey.sol";
import {Currency} from "@uniswap/v4-core/src/types/Currency.sol";
import {MockERC20} from "solmate/src/test/utils/mocks/MockERC20.sol";

import {HookTest} from "../utils/HookTest.sol";
import {BAHook} from "../../src/BAHook.sol";
import {DAHook} from "../../src/DAHook.sol";

/**
 * @notice Pins the ratchet behaviour of BAHook and DAHook as it stands BEFORE
 *         any repair, away from the fee bounds. These assertions must still
 *         hold after `F_MIN` is introduced: the floor may only change behaviour
 *         at the floor.
 *
 * Constants are private on the hooks, so the expected steps are written out
 * here. Note DAHook's FSTEP is 100 (1 bp) and BAHook's is 500 (5 bps); DAHook's
 * source comment claiming "5 bps" is wrong.
 */
contract RatchetTest is Test, HookTest {
    using PoolIdLibrary for PoolKey;

    uint24 constant INITIAL_FEE = 3000;
    uint24 constant BA_FSTEP = 500;
    uint24 constant DA_FSTEP = 100;

    function setUp() public {
        deployArtifactsAndLabel();
        deployCurrencyPair();
    }

    // ------------------------------------------------------------- helpers

    function _feesBA() internal view returns (uint24, uint24) {
        BAHook h = BAHook(address(hookContract));
        return (h.feeAB(poolId), h.feeBA(poolId));
    }

    function _feesDA() internal view returns (uint24, uint24) {
        DAHook h = DAHook(address(hookContract));
        return (h.feeAB(poolId), h.feeBA(poolId));
    }

    /// @dev Sets both feeds so their ratio takes the requested direction.
    function _setRatio(int256 price0, int256 price1) internal {
        priceFeed0.updateAnswer(price0);
        priceFeed1.updateAnswer(price1);
    }

    /// @dev A swap small enough not to disturb the pool, purely to fire the
    ///      hook's afterSwap callback.
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

    // ------------------------------------------------------------- BAHook

    function test_BAHook_startsAtTheInitialFeeOnBothSides() public {
        deployHookAndFeeds("BAHook");
        deployPool();

        (uint24 ab, uint24 ba) = _feesBA();
        assertEq(ab, INITIAL_FEE);
        assertEq(ba, INITIAL_FEE);
    }

    function test_BAHook_ratioFallMakesTheSellSideDearer() public {
        deployHookAndFeeds("BAHook");
        deployPool();

        // ratio = price0/price1; lower it so feeAB rises.
        vm.roll(block.number + 1);
        _setRatio(300000000000, 40000000);
        _poke(true);

        (uint24 ab, uint24 ba) = _feesBA();
        assertEq(ab, INITIAL_FEE + BA_FSTEP, "feeAB rises one FSTEP");
        assertEq(ba, INITIAL_FEE - BA_FSTEP, "feeBA falls one FSTEP");
    }

    function test_BAHook_ratioRiseMovesTheOtherWay() public {
        deployHookAndFeeds("BAHook");
        deployPool();

        vm.roll(block.number + 1);
        _setRatio(300000000000, 20000000);
        _poke(true);

        (uint24 ab, uint24 ba) = _feesBA();
        assertEq(ab, INITIAL_FEE - BA_FSTEP);
        assertEq(ba, INITIAL_FEE + BA_FSTEP);
    }

    /// Block-level granularity: a second swap in the same block must not move
    /// the fee again, or the policy would react repeatedly to one observation.
    function test_BAHook_doesNotStepTwiceInOneBlock() public {
        deployHookAndFeeds("BAHook");
        deployPool();

        vm.roll(block.number + 1);
        _setRatio(300000000000, 40000000);
        _poke(true);
        (uint24 afterFirst,) = _feesBA();

        _poke(true); // same block
        (uint24 afterSecond,) = _feesBA();

        assertEq(afterSecond, afterFirst, "block-level granularity");
    }

    function test_BAHook_stepsAgainInTheNextBlock() public {
        deployHookAndFeeds("BAHook");
        deployPool();

        vm.roll(block.number + 1);
        _setRatio(300000000000, 40000000);
        _poke(true);

        vm.roll(block.number + 1);
        _setRatio(300000000000, 50000000);
        _poke(true);

        (uint24 ab,) = _feesBA();
        assertEq(ab, INITIAL_FEE + 2 * BA_FSTEP);
    }

    // ------------------------------------------------------------- DAHook

    function test_DAHook_stepsOnEverySwapWithNoBlockGate() public {
        deployHookAndFeeds("DAHook");
        deployPool();

        (uint24 ab0,) = _feesDA();
        _poke(true);
        (uint24 ab1,) = _feesDA();
        _poke(true); // same block, must still move
        (uint24 ab2,) = _feesDA();

        assertEq(ab1, ab0 + DA_FSTEP, "trade-level granularity");
        assertEq(ab2, ab1 + DA_FSTEP, "no block gate");
    }

    function test_DAHook_directionOfTheTradeSetsWhichSideRises() public {
        deployHookAndFeeds("DAHook");
        deployPool();

        _poke(false); // B -> A
        (uint24 ab, uint24 ba) = _feesDA();

        assertEq(ba, INITIAL_FEE + DA_FSTEP, "the traded side gets dearer");
        assertEq(ab, INITIAL_FEE - DA_FSTEP);
    }
}
