// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title Hook Constants library
/// @notice Provides different constants related to Hooks
library HookConstants {
    function getHookNames() external pure returns (string[] memory) {
        string[] memory names = new string[](4);
        names[0] = "BAHook";
        names[1] = "MEVChargeHook";
        names[2] = "DAHook";
        names[3] = "ABHook";

        return names;
    }
}
