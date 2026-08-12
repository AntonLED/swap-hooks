// SPDX-License-Identifier: MIT
pragma solidity ^0.8.30;

import {Test} from "forge-std/Test.sol";
import {TickMath} from "@uniswap/v4-core/src/libraries/TickMath.sol";
import {ArbMath} from "../src/libraries/ArbMath.sol";

contract ArbMathTest is Test {
    uint256 constant Q96 = 1 << 96;

    function _priceX96(uint256 numerator, uint256 denominator) internal pure returns (uint256) {
        return (numerator * Q96) / denominator;
    }

    function test_zeroFeeTargetEqualsExternalPrice() public pure {
        uint160 target = ArbMath.targetSqrtPriceX96(_priceX96(1, 1), 0, true);
        assertApproxEqAbs(uint256(target), Q96, 1);
    }

    function test_sellingToken0TargetsAboveExternalPrice() public pure {
        uint256 p = _priceX96(1, 1);
        assertGt(uint256(ArbMath.targetSqrtPriceX96(p, 3000, true)), uint256(ArbMath.targetSqrtPriceX96(p, 0, true)));
    }

    function test_buyingToken0TargetsBelowExternalPrice() public pure {
        uint256 p = _priceX96(1, 1);
        assertLt(uint256(ArbMath.targetSqrtPriceX96(p, 3000, false)), uint256(ArbMath.targetSqrtPriceX96(p, 0, false)));
    }

    /// sqrt(P/g) * sqrt(P*g) == P, so the band is symmetric in log price.
    function test_bandIsSymmetricInLogPrice() public pure {
        uint256 p = _priceX96(1, 1);
        uint256 hi = uint256(ArbMath.targetSqrtPriceX96(p, 10000, true));
        uint256 lo = uint256(ArbMath.targetSqrtPriceX96(p, 10000, false));
        assertApproxEqRel((hi * lo) / Q96, p, 1e12);
    }

    function test_noTradeInsideTheBand() public pure {
        uint256 p = _priceX96(1, 1);
        uint160 hi = ArbMath.targetSqrtPriceX96(p, 10000, true);
        uint160 lo = ArbMath.targetSqrtPriceX96(p, 10000, false);
        uint160 mid = uint160((uint256(hi) + uint256(lo)) / 2);

        assertFalse(ArbMath.shouldTrade(mid, hi, true));
        assertFalse(ArbMath.shouldTrade(mid, lo, false));
    }

    function test_tradeWhenOutsideTheBand() public pure {
        uint256 p = _priceX96(1, 1);
        uint160 hi = ArbMath.targetSqrtPriceX96(p, 10000, true);
        uint160 lo = ArbMath.targetSqrtPriceX96(p, 10000, false);

        assertTrue(ArbMath.shouldTrade(uint160(uint256(hi) * 2), hi, true));
        assertTrue(ArbMath.shouldTrade(uint160(uint256(lo) / 2), lo, false));
    }

    function test_grossInputAddsTheFee() public pure {
        assertApproxEqAbs(ArbMath.grossInput(997_000, 3000), 1_000_000, 1);
    }

    function test_grossInputIsIdentityAtZeroFee() public pure {
        assertEq(ArbMath.grossInput(12345, 0), 12345);
    }

    /// Appendix A.4 worked example: x=y=1, P=0.81, gamma=1 gives profit 0.01.
    /// In (L, s) coordinates x=y=1 means L=1 and s=2^96.
    function test_profitMatchesTheWorkedExample() public pure {
        uint256 p = _priceX96(81, 100);
        uint160 s = uint160(Q96);
        uint160 t = ArbMath.targetSqrtPriceX96(p, 0, true);
        uint256 got = ArbMath.profit(1e18, s, t, 3000);
        assertApproxEqRel(got, 0.01e18, 1e15); // 0.1% tolerance
    }

    function test_profitIsZeroAtTheBandEdge() public pure {
        uint160 s = uint160(Q96);
        assertEq(ArbMath.profit(1e18, s, s, 3000), 0);
    }

    function test_targetStaysInsideTheProtocolPriceRange() public pure {
        uint160 t = ArbMath.targetSqrtPriceX96(_priceX96(1, 1), 10000, true);
        assertGt(uint256(t), uint256(TickMath.MIN_SQRT_PRICE));
        assertLt(uint256(t), uint256(TickMath.MAX_SQRT_PRICE));
    }

    /// SHIB/ETH is around 6.7e-9; ETH/SHIB around 1.5e8. Both must survive.
    function test_extremeRatioDoesNotOverflowOrTruncate() public pure {
        uint256 tiny = _priceX96(67, 10_000_000_000);
        uint256 huge = _priceX96(150_000_000, 1);
        assertGt(uint256(ArbMath.targetSqrtPriceX96(tiny, 3000, true)), 0);
        assertGt(uint256(ArbMath.targetSqrtPriceX96(huge, 3000, true)), 0);
    }
}
