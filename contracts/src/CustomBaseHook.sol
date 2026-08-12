// SPDX-License-Identifier: MIT

pragma solidity ^0.8.26;

// External imports
import {Hooks} from "@uniswap/v4-core/src/libraries/Hooks.sol";
import {PoolKey} from "@uniswap/v4-core/src/types/PoolKey.sol";
import {BeforeSwapDelta, BeforeSwapDeltaLibrary} from "@uniswap/v4-core/src/types/BeforeSwapDelta.sol";
import {LPFeeLibrary} from "@uniswap/v4-core/src/libraries/LPFeeLibrary.sol";
import {SwapParams} from "@uniswap/v4-core/src/types/PoolOperation.sol";

import {BaseOverrideFee} from "@openzeppelin/uniswap-hooks/src/fee/BaseOverrideFee.sol";

import {BaseHook} from "@openzeppelin/uniswap-hooks/src/base/BaseHook.sol";

/// @title A base Hook contract with custom logic
abstract contract CustomBaseHook is BaseOverrideFee {
    using LPFeeLibrary for uint24;

    function getFee(address caller, PoolKey calldata key, SwapParams calldata params, bytes calldata data)
        external
        virtual
        returns (uint24)
    {
        return _getFee(caller, key, params, data);
    }

    function setFee(uint24 _fee, PoolKey calldata key) external virtual {}

    function cooldownSeconds() external view returns (uint16) {
        return 15;
    }
}
