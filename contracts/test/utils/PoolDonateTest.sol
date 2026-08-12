// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.24;

import {console} from "forge-std/console.sol";

import {CurrencyLibrary, Currency} from "@uniswap/v4-core/src/types/Currency.sol";

import {BalanceDelta, BalanceDeltaLibrary} from "@uniswap/v4-core/src/types/BalanceDelta.sol";

import {IHooks} from "@uniswap/v4-core/src/interfaces/IHooks.sol";
import {Hooks} from "@uniswap/v4-core/src/libraries/Hooks.sol";

import {PoolKey} from "@uniswap/v4-core/src/types/PoolKey.sol";

import {MockERC20} from "solmate/src/test/utils/mocks/MockERC20.sol";
import {IERC20Minimal} from "@uniswap/v4-core/src/interfaces/external/IERC20Minimal.sol";

import {Currency} from "@uniswap/v4-core/src/types/Currency.sol";
import {IPoolManager} from "@uniswap/v4-core/src/interfaces/IPoolManager.sol";
import {StateLibrary} from "@uniswap/v4-core/src/libraries/StateLibrary.sol";
import {TransientStateLibrary} from "@uniswap/v4-core/src/libraries/TransientStateLibrary.sol";

import {BalanceDelta} from "@uniswap/v4-core/src/types/BalanceDelta.sol";

contract PoolDonateTest {
    using CurrencyLibrary for Currency;
    using StateLibrary for IPoolManager;
    using TransientStateLibrary for IPoolManager;
    using Hooks for IHooks;

    using BalanceDeltaLibrary for BalanceDelta;

    IPoolManager public immutable manager;

    constructor(IPoolManager _manager) {
        manager = _manager;
    }

    struct CallbackData {
        address sender;
        PoolKey key;
        uint256 amount0;
        uint256 amount1;
        bytes hookData;
    }

    function donate(PoolKey memory key, uint256 amount0, uint256 amount1, bytes memory hookData)
        external
        payable
        returns (BalanceDelta delta)
    {
        console.log("amount0: ", amount0);
        console.log("amount1: ", amount1);
        // require(amount0 <= type(int256).max, "Amount0 too large for int256 cast");
        // require(amount1 <= type(int256).max, "Amount1 too large for int256 cast");

        delta = abi.decode(
            manager.unlock(abi.encode(CallbackData(msg.sender, key, amount0, amount1, hookData))), (BalanceDelta)
        );

        uint256 ethBalance = address(this).balance;
        if (ethBalance > 0) {
            CurrencyLibrary.ADDRESS_ZERO.transfer(msg.sender, ethBalance);
        }
    }

    function unlockCallback(bytes calldata rawData) external returns (bytes memory) {
        require(msg.sender == address(manager));

        CallbackData memory data = abi.decode(rawData, (CallbackData));

        (,, int256 deltaBefore0) = _fetchBalances(data.key.currency0, data.sender, address(this));
        (,, int256 deltaBefore1) = _fetchBalances(data.key.currency1, data.sender, address(this));

        require(deltaBefore0 == 0, "deltaBefore0 is not 0");
        require(deltaBefore1 == 0, "deltaBefore1 is not 0");

        BalanceDelta delta = manager.donate(data.key, data.amount0, data.amount1, data.hookData);

        console.log("Balance delta token0: ", delta.amount0());
        console.log("Balance delta token1: ", delta.amount1());

        (uint256 userBalance0,, int256 deltaAfter0) = _fetchBalances(data.key.currency0, data.sender, address(this));
        (uint256 userBalance1,, int256 deltaAfter1) = _fetchBalances(data.key.currency1, data.sender, address(this));

        require(deltaAfter0 == -int256(data.amount0), "deltaAfter0 is not equal to -int256(data.amount0)");
        require(deltaAfter1 == -int256(data.amount1), "deltaAfter1 is not equal to -int256(data.amount1)");

        console.log("User Balance 0: ", userBalance0);
        console.log("User Balance 1: ", userBalance1);

        if (deltaAfter0 < 0) settle(data.key.currency0, manager, data.sender, uint256(-deltaAfter0), false);
        if (deltaAfter1 < 0) settle(data.key.currency1, manager, data.sender, uint256(-deltaAfter1), false);
        if (deltaAfter0 > 0) take(data.key.currency0, manager, data.sender, uint256(deltaAfter0), false);
        if (deltaAfter1 > 0) take(data.key.currency1, manager, data.sender, uint256(deltaAfter1), false);

        return abi.encode(delta);
    }

    function _fetchBalances(Currency currency, address user, address deltaHolder)
        internal
        view
        returns (uint256 userBalance, uint256 poolBalance, int256 delta)
    {
        userBalance = currency.balanceOf(user);
        poolBalance = currency.balanceOf(address(manager));
        delta = manager.currencyDelta(deltaHolder, currency);
    }

    function settle(Currency currency, IPoolManager manager, address payer, uint256 amount, bool burn) internal {
        // for native currencies or burns, calling sync is not required
        // short circuit for ERC-6909 burns to support ERC-6909-wrapped native tokens
        if (burn) {
            manager.burn(payer, currency.toId(), amount);
        } else if (currency.isAddressZero()) {
            manager.settle{value: amount}();
        } else {
            manager.sync(currency);
            if (payer != address(this)) {
                IERC20Minimal(Currency.unwrap(currency)).transferFrom(payer, address(manager), amount);
            } else {
                IERC20Minimal(Currency.unwrap(currency)).transfer(address(manager), amount);
            }
            manager.settle();
        }
    }

    function take(Currency currency, IPoolManager manager, address recipient, uint256 amount, bool claims) internal {
        claims ? manager.mint(recipient, currency.toId(), amount) : manager.take(currency, recipient, amount);
    }
}
