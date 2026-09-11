// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

import {IHooks} from "@uniswap/v4-core/src/interfaces/IHooks.sol";

import {PoolKey} from "@uniswap/v4-core/src/types/PoolKey.sol";
import {SwapParams} from "@uniswap/v4-core/src/interfaces/IPoolManager.sol";

interface IHooksExtended is IHooks {
    function getFee(address a, PoolKey calldata key, SwapParams calldata params, bytes calldata data)
        external
        returns (uint24);

    function setFee(uint24 _fee, PoolKey calldata key) external;

    function cooldownSeconds() external view returns (uint16);
}
