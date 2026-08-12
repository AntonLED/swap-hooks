// SPDX-License-Identifier: MIT
pragma solidity ^0.8.30;

import {Test} from "forge-std/Test.sol";
import {Hooks} from "@uniswap/v4-core/src/libraries/Hooks.sol";
import {IHooks} from "@uniswap/v4-core/src/interfaces/IHooks.sol";

import {HookTest} from "./utils/HookTest.sol";

/// @dev IHooksExtended does not expose it, but every policy inherits it.
interface IPermissioned {
    function getHookPermissions() external pure returns (Hooks.Permissions memory);
}

/// @notice The address a hook lives at *is* its permission set in v4 -- the low
///         bits of the address are what PoolManager consults before deciding
///         whether to call a callback. The harness places each hook at a
///         hand-written constant from HookFlags, so a constant that disagrees
///         with the contract's own getHookPermissions() would give a pool that
///         silently skips a callback the policy depends on.
///
///         v4 rejects that at construction, so this is a guard rather than a
///         suspicion -- but nothing here asserted it, and the flags are edited
///         by hand whenever a policy gains a callback.
contract HookPermissionsTest is Test, HookTest {
    function _check(string memory name) internal {
        deployArtifactsAndLabel();
        deployCurrencyPair();
        deployHookAndFeeds(name);

        address addr = address(hookContract);
        Hooks.Permissions memory p = IPermissioned(addr).getHookPermissions();

        assertEq(_bit(addr, Hooks.AFTER_INITIALIZE_FLAG), p.afterInitialize, string.concat(name, ": afterInitialize"));
        assertEq(_bit(addr, Hooks.BEFORE_SWAP_FLAG), p.beforeSwap, string.concat(name, ": beforeSwap"));
        assertEq(_bit(addr, Hooks.AFTER_SWAP_FLAG), p.afterSwap, string.concat(name, ": afterSwap"));
        assertEq(
            _bit(addr, Hooks.BEFORE_SWAP_RETURNS_DELTA_FLAG),
            p.beforeSwapReturnDelta,
            string.concat(name, ": beforeSwapReturnDelta")
        );
        assertEq(
            _bit(addr, Hooks.AFTER_ADD_LIQUIDITY_FLAG), p.afterAddLiquidity, string.concat(name, ": afterAddLiquidity")
        );
    }

    function _bit(address a, uint160 flag) private pure returns (bool) {
        return uint160(a) & flag != 0;
    }

    function test_myHookAddressMatchesItsPermissions() public {
        _check("MyHook");
    }

    function test_bAHookAddressMatchesItsPermissions() public {
        _check("BAHook");
    }

    function test_dAHookAddressMatchesItsPermissions() public {
        _check("DAHook");
    }

    function test_aBHookAddressMatchesItsPermissions() public {
        _check("ABHook");
    }

    function test_volatilityHookAddressMatchesItsPermissions() public {
        _check("VolatilityHook");
    }

    function test_pegDefenceAddressMatchesItsPermissions() public {
        _check("PegDefence");
    }

    function test_pegCaptureAddressMatchesItsPermissions() public {
        _check("PegCapture");
    }

    function test_mEVChargeHookAddressMatchesItsPermissions() public {
        _check("MEVChargeHook");
    }
}
