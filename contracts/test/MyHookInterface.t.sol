// SPDX-License-Identifier: MIT
pragma solidity ^0.8.30;

import {Test} from "forge-std/Test.sol";
import {SwapParams} from "@uniswap/v4-core/src/interfaces/IPoolManager.sol";
import {HookTest} from "./utils/HookTest.sol";

/// @notice MyHook is the fixed-fee baseline every policy is compared against.
/// The replay harness reaches it through IHooksExtended, so both entry points
/// must exist and behave. Without them nothing downstream can run.
contract MyHookInterfaceTest is Test, HookTest {
    function setUp() public {
        deployArtifactsAndLabel();
        deployCurrencyPair();
        deployHookAndFeeds("MyHook");
        deployPool();
    }

    function _fee(bool zeroForOne, int256 amount) internal returns (uint24) {
        return hookContract.getFee(
            address(this),
            poolKey,
            SwapParams({zeroForOne: zeroForOne, amountSpecified: amount, sqrtPriceLimitX96: 0}),
            ""
        );
    }

    function test_getFeeIsReachableThroughTheExtendedInterface() public {
        hookContract.setFee(3000, poolKey);
        assertEq(_fee(true, 0), 3000, "baseline must report its fee");
    }

    function test_setFeeThroughTheExtendedInterfaceTakesEffect() public {
        hookContract.setFee(500, poolKey);
        assertEq(_fee(true, 0), 500, "the four static baseline levels are set this way");
    }

    /// A constant fee must be flat in both direction and size. Appendix A.8 only
    /// permits the closed-form arbitrage size for policies with this property.
    function test_feeIsIndependentOfDirectionAndSize() public {
        hookContract.setFee(3000, poolKey);
        assertEq(_fee(true, 1e18), _fee(false, 1000e18));
    }
}
