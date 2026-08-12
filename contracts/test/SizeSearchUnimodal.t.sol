// SPDX-License-Identifier: MIT
pragma solidity ^0.8.30;

import {Test} from "forge-std/Test.sol";
import {SqrtPriceMath} from "@uniswap/v4-core/src/libraries/SqrtPriceMath.sol";
import {FullMath} from "@uniswap/v4-core/src/libraries/FullMath.sol";
import {ArbMath} from "../src/libraries/ArbMath.sol";

/// @notice `_optimalSize` runs a ternary search, which is only correct when the
///         profit curve is unimodal in trade size. The harness asserts that in a
///         comment -- "a fee increasing in size only makes it more concave" --
///         and nothing checked it. A ternary search on a multi-modal function
///         returns a wrong answer silently.
///
///         Sampled here on a dense grid for the size-dependent fee shape:
///         a base fee plus a surcharge growing with the trade's share of
///         liquidity, which is what MEVChargeHook's impact term does.
contract SizeSearchUnimodalTest is Test {
    uint256 constant Q96 = 1 << 96;
    uint256 constant ONE_PIPS = 1e6;

    uint256 constant STATIC_PIPS = 3000; // 30 bps
    uint256 constant CAP_PIPS = 10_000; // the clamped feeMax, 100 bps

    /// @dev MEVChargeHook's ACTUAL size path, not a smooth stand-in.
    ///
    ///      The original version of this test used `3000 + amount*1e5/liq`, a
    ///      continuous linear ramp. The policy does something else:
    ///      `_calculateImpactFee` returns `timeFee` at or below a 500 bps
    ///      impact and `staticFee + range*(impactBps-500)/9500` above it, which
    ///      read alone looks like a DOWNWARD jump whenever `timeFee >
    ///      staticFee` -- and a downward fee jump is an upward jump in profit,
    ///      i.e. a second local maximum the ternary search could converge to
    ///      instead. That is what the 2026-08-10 spec review predicted.
    ///
    ///      It does not happen, because the call site takes
    ///      `max(impactFee, timeFee)` and the impact branch starts at exactly
    ///      `staticFee <= timeFee`. The applied fee is continuous and
    ///      non-decreasing in size. This test now exercises that shape, so the
    ///      claim is checked rather than argued.
    /// @param timeFeePips the cooldown ramp's current value; swept by the caller
    function _feeFor(uint256 amount, uint128 liq, uint256 timeFeePips) internal pure returns (uint24) {
        uint256 impactBps = FullMath.mulDiv(amount, 10_000, uint256(liq));
        if (impactBps > 10_000) impactBps = 10_000;

        uint256 impact = impactBps <= 500
            ? timeFeePips
            : STATIC_PIPS + FullMath.mulDiv(CAP_PIPS - STATIC_PIPS, impactBps - 500, 9500);

        uint256 chosen = impact > timeFeePips ? impact : timeFeePips;
        return uint24(chosen > CAP_PIPS ? CAP_PIPS : chosen);
    }

    function _profit(uint256 grossIn, uint160 s, uint128 liq, uint256 extPriceX96, uint256 timeFeePips)
        internal
        pure
        returns (uint256)
    {
        if (grossIn == 0) return 0;
        uint24 f = _feeFor(grossIn, liq, timeFeePips);
        uint256 netIn = FullMath.mulDiv(grossIn, ONE_PIPS - uint256(f), ONE_PIPS);
        if (netIn == 0) return 0;
        uint160 s2 = SqrtPriceMath.getNextSqrtPriceFromInput(s, liq, netIn, true);
        uint256 out = SqrtPriceMath.getAmount1Delta(s2, s, liq, false);
        uint256 cost = FullMath.mulDiv(grossIn, extPriceX96, Q96);
        return out > cost ? out - cost : 0;
    }

    function test_profitHasASinglePeakOverTradeSize() public pure {
        // Swept across the cooldown ramp, because the jump the review predicted
        // exists only where `timeFee > staticFee`.
        _assertUnimodal(STATIC_PIPS);
        _assertUnimodal(6000);
        _assertUnimodal(CAP_PIPS);
    }

    function _assertUnimodal(uint256 timeFeePips) internal pure {
        uint128 liq = 1e21;
        uint256 P = Q96; // external price 1.0
        uint160 s = uint160(FullMath.mulDiv(uint256(2) ** 96, 1030, 1000)); // pool 6% above

        uint256 hi = SqrtPriceMath.getAmount0Delta(ArbMath.targetSqrtPriceX96(P, 0, true), s, liq, true) * 2;
        uint256 steps = 400;

        uint256 previous = 0;
        bool falling = false;
        uint256 turns = 0;
        for (uint256 i = 1; i <= steps; i++) {
            uint256 p = _profit(hi * i / steps, s, liq, P, timeFeePips);
            if (i > 1) {
                bool nowFalling = p < previous;
                // Count only genuine direction changes, ignoring flat ties.
                if (p != previous && nowFalling != falling) {
                    if (i > 2) turns++;
                    falling = nowFalling;
                }
            }
            previous = p;
        }
        // One turn: rises to the optimum, then falls. More would mean a local
        // maximum the ternary search could converge to instead.
        assertLe(turns, 1, "profit is not unimodal in trade size");
    }
}
