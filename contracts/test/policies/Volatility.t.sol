// SPDX-License-Identifier: MIT
pragma solidity ^0.8.30;

import {Test} from "forge-std/Test.sol";

import {Constants} from "@uniswap/v4-core/test/utils/Constants.sol";
import {SwapParams} from "@uniswap/v4-core/src/interfaces/IPoolManager.sol";
import {PoolIdLibrary} from "@uniswap/v4-core/src/types/PoolId.sol";
import {PoolKey} from "@uniswap/v4-core/src/types/PoolKey.sol";
import {Currency} from "@uniswap/v4-core/src/types/Currency.sol";
import {MockERC20} from "solmate/src/test/utils/mocks/MockERC20.sol";

import {HookTest} from "../utils/HookTest.sol";
import {VolatilityHook} from "../../src/VolatilityHook.sol";

/**
 * @notice The volatility-adaptive policy the paper claims but the artifact
 *         lacked. Fee = base + coefficient * sigma, clamped to the fee box,
 *         with sigma from Welford smoothed by an EMA.
 */
contract VolatilityTest is Test, HookTest {
    using PoolIdLibrary for PoolKey;

    uint24 constant F_MIN = 100;
    uint24 constant F_MAX = 10000;
    uint24 constant F_BASE = 2000; // the contract's recalibrated calm-market base (2026-08-12)

    function setUp() public {
        deployArtifactsAndLabel();
        deployCurrencyPair();
        deployHookAndFeeds("VolatilityHook");
        deployPool();
    }

    function _hook() internal view returns (VolatilityHook) {
        return VolatilityHook(address(hookContract));
    }

    function _fee(bool zeroForOne, int256 amount) internal returns (uint24) {
        return hookContract.getFee(
            address(this),
            poolKey,
            SwapParams({zeroForOne: zeroForOne, amountSpecified: amount, sqrtPriceLimitX96: 0}),
            ""
        );
    }

    function _poke() internal {
        MockERC20(Currency.unwrap(currency0)).mint(address(this), 1e16);
        swapRouter.swapExactTokensForTokens({
            amountIn: 1e16,
            amountOutMin: 0,
            zeroForOne: true,
            poolKey: poolKey,
            hookData: Constants.ZERO_BYTES,
            receiver: address(this),
            deadline: block.timestamp + 1
        });
    }

    /// @dev Advances a block and feeds a new token1 price, then trades.
    function _step(int256 price1) internal {
        vm.roll(block.number + 1);
        priceFeed1.updateAnswer(price1);
        _poke();
    }

    function test_startsAtTheBaseFee() public view {
        assertEq(_hook().fee(poolId), F_BASE);
    }

    function test_calmMarketStaysNearTheFloor() public {
        for (uint256 i = 0; i < 40; i++) {
            _step(30000000); // unchanged ratio
        }
        assertEq(_hook().fee(poolId), F_BASE, "no variance, no premium");
    }

    function test_volatileMarketRaisesTheFee() public {
        for (uint256 i = 0; i < 40; i++) {
            _step(i % 2 == 0 ? int256(33000000) : int256(27000000)); // +-10%
        }
        assertGt(_hook().fee(poolId), F_BASE, "variance must lift the fee");
    }

    function test_feeStaysInsideTheBoxUnderExtremeSwings() public {
        for (uint256 i = 0; i < 60; i++) {
            _step(i % 2 == 0 ? int256(90000000) : int256(10000000));
        }
        uint24 f = _hook().fee(poolId);
        assertGe(f, F_MIN);
        assertLe(f, F_MAX);
    }

    /// Load-bearing: spec §A.8 permits the closed-form arbitrage size only for
    /// policies whose fee ignores `amountSpecified`.
    function test_feeIsIndependentOfTradeSize() public {
        for (uint256 i = 0; i < 10; i++) {
            _step(i % 2 == 0 ? int256(33000000) : int256(27000000));
        }
        assertEq(_fee(true, 1e18), _fee(true, 1000e18));
    }

    function test_feeIsTheSameInBothDirections() public {
        for (uint256 i = 0; i < 10; i++) {
            _step(i % 2 == 0 ? int256(33000000) : int256(27000000));
        }
        assertEq(_fee(true, 0), _fee(false, 0), "this policy sets a level, not an allocation");
    }

    function test_updatesAtMostOncePerBlock() public {
        _step(33000000);
        uint256 n1 = _hook().sampleCount(poolId);
        _poke(); // same block
        assertEq(_hook().sampleCount(poolId), n1, "block-level granularity");
    }

    function test_sigmaGrowsWithTheSizeOfTheSwings() public {
        // Snapshot rather than re-running setUp, which would redeploy the
        // Uniswap artifacts on top of themselves.
        uint256 snap = vm.snapshotState();

        for (uint256 i = 0; i < 20; i++) {
            _step(i % 2 == 0 ? int256(30300000) : int256(29700000)); // +-1%
        }
        uint256 mild = _hook().sigma(poolId);

        vm.revertToState(snap);
        for (uint256 i = 0; i < 20; i++) {
            _step(i % 2 == 0 ? int256(33000000) : int256(27000000)); // +-10%
        }
        assertGt(_hook().sigma(poolId), mild, "wider swings, wider sigma");
    }
}
