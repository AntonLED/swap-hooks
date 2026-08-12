// SPDX-License-Identifier: MIT
pragma solidity ^0.8.30;

import {Test} from "forge-std/Test.sol";
import {SqrtPriceMath} from "@uniswap/v4-core/src/libraries/SqrtPriceMath.sol";
import {FullMath} from "@uniswap/v4-core/src/libraries/FullMath.sol";
import {ArbMath} from "../src/libraries/ArbMath.sol";

/// Compares ArbMath.profit against profit reconstructed from the pool's own
/// swap math, in both directions.
contract ArbProfitTest is Test {
    uint256 constant Q96 = 1 << 96;
    uint256 constant ONE_PIPS = 1e6;

    function _actual(bool zeroForOne, uint160 s, uint128 liq, uint256 extPriceX96, uint24 fee)
        internal
        pure
        returns (uint256)
    {
        uint160 t = ArbMath.targetSqrtPriceX96(extPriceX96, fee, zeroForOne);
        if (!ArbMath.shouldTrade(s, t, zeroForOne)) return 0;
        uint256 netIn = zeroForOne
            ? SqrtPriceMath.getAmount0Delta(t, s, liq, true)
            : SqrtPriceMath.getAmount1Delta(s, t, liq, true);
        uint256 grossIn = ArbMath.grossInput(netIn, fee);
        uint160 s2 = SqrtPriceMath.getNextSqrtPriceFromInput(s, liq, netIn, zeroForOne);
        if (zeroForOne) {
            uint256 out = SqrtPriceMath.getAmount1Delta(s2, s, liq, false);
            uint256 cost = FullMath.mulDiv(grossIn, extPriceX96, Q96);
            return out > cost ? out - cost : 0;
        }
        uint256 o = SqrtPriceMath.getAmount0Delta(s, s2, liq, false);
        uint256 v = FullMath.mulDiv(o, extPriceX96, Q96);
        return v > grossIn ? v - grossIn : 0;
    }

    /// @notice The closed form must agree with the pool in BOTH directions.
    ///
    /// It did not: the sell-side formula Pi* = L(s-t)^2/s was applied to buys
    /// too, understating them by exactly gamma, because on a buy the fee comes
    /// out of the token1 input -- the same unit the profit is denominated in --
    /// so the grossing-up does not cancel. Since `expected` gates entry against
    /// gas, the defect suppressed buy-side trades whose true profit fell in
    /// [gasCost, gasCost/gamma].
    function test_closedFormMatchesThePoolInBothDirections() public pure {
        uint128 liq = 1e21;
        uint256 P = Q96; // external price 1.0
        uint24[3] memory fees = [uint24(3000), uint24(10000), uint24(100000)];
        for (uint256 k = 0; k < 3; k++) {
            uint24 f = fees[k];
            // pool 3% above external -> sell token0; 3% below -> buy token0
            uint160 sHigh = uint160(FullMath.mulDiv(uint256(2) ** 96, 1015, 1000));
            uint160 sLow = uint160(FullMath.mulDiv(uint256(2) ** 96, 985, 1000));

            uint160 tS = ArbMath.targetSqrtPriceX96(P, f, true);
            uint160 tB = ArbMath.targetSqrtPriceX96(P, f, false);
            if (f >= ONE_PIPS / 20) continue; // band wider than the deviation

            assertApproxEqRel(ArbMath.profit(liq, sHigh, tS, f), _actual(true, sHigh, liq, P, f), 1e12);
            assertApproxEqRel(ArbMath.profit(liq, sLow, tB, f), _actual(false, sLow, liq, P, f), 1e12);
        }
    }
}
