// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.20;

import {Hooks} from "@uniswap/v4-core/src/libraries/Hooks.sol";

/// @title Hook Flags Library
/// @notice a library with specifig flags for different hooks
library HookFlags {
    uint160 public constant BA_HOOK_FLAGS =
        uint160(Hooks.AFTER_INITIALIZE_FLAG | Hooks.BEFORE_SWAP_FLAG | Hooks.AFTER_SWAP_FLAG) ^ (0x4444 << 144);

    uint160 public constant MEV_CHARGE_HOOK_FLAGS = uint160(
        Hooks.AFTER_INITIALIZE_FLAG | Hooks.AFTER_ADD_LIQUIDITY_FLAG | Hooks.AFTER_REMOVE_LIQUIDITY_FLAG
            | Hooks.AFTER_REMOVE_LIQUIDITY_RETURNS_DELTA_FLAG | Hooks.BEFORE_SWAP_FLAG
    ) ^ (0x4444 << 144);

    /// @notice Same permissions as MEV_CHARGE_HOOK_FLAGS, different address.
    /// @dev The permission bits must match, because the two contracts declare
    ///      the same callbacks; only the salt differs so both can be deployed
    ///      in one run.
    uint160 public constant MEV_CHARGE_FIXED_HOOK_FLAGS = uint160(
        Hooks.AFTER_INITIALIZE_FLAG | Hooks.AFTER_ADD_LIQUIDITY_FLAG | Hooks.AFTER_REMOVE_LIQUIDITY_FLAG
            | Hooks.AFTER_REMOVE_LIQUIDITY_RETURNS_DELTA_FLAG | Hooks.BEFORE_SWAP_FLAG
    ) ^ (0x4455 << 144);

    uint160 public constant PEG_STABILITY_HOOK_FLAGS =
        uint160(Hooks.AFTER_INITIALIZE_FLAG | Hooks.BEFORE_SWAP_FLAG) ^ (0x4444 << 144);

    uint160 public constant DA_HOOK_FLAGS =
        uint160(Hooks.AFTER_INITIALIZE_FLAG | Hooks.BEFORE_SWAP_FLAG | Hooks.AFTER_SWAP_FLAG) ^ (0x4444 << 144);

    uint160 public constant AB_HOOK_FLAGS =
        uint160(Hooks.AFTER_INITIALIZE_FLAG | Hooks.BEFORE_SWAP_FLAG | Hooks.AFTER_SWAP_FLAG) ^ (0x4444 << 144);

    /// @dev Same permission set as BAHook: reads the feeds after each block and
    ///      overrides the fee on the way in.
    uint160 public constant VOLATILITY_HOOK_FLAGS =
        uint160(Hooks.AFTER_INITIALIZE_FLAG | Hooks.BEFORE_SWAP_FLAG | Hooks.AFTER_SWAP_FLAG) ^ (0x4444 << 144);

    /// @dev MyHook is the fixed-fee baseline. It overrides _afterInitialize to
    ///      push the configured fee, and BaseOverrideFee supplies beforeSwap.
    ///      No afterSwap: a constant fee has no state to advance.
    uint160 public constant MY_HOOK_FLAGS =
        uint160(Hooks.AFTER_INITIALIZE_FLAG | Hooks.BEFORE_SWAP_FLAG) ^ (0x4444 << 144);
}
