// SPDX-License-Identifier: MIT
pragma solidity ^0.8.30;

import {Test} from "forge-std/Test.sol";
import {UUMath} from "../src/libraries/UUMath.sol";

/// Reference table generated with:
///   uv run python - <<'EOF'
///   from mpmath import mp, exp, mpf
///   mp.dps = 30
///   for x in ["-0.0001", "-0.003", "-0.03", "-0.6931471805599453", "-5", "-41"]:
///       print(x, int(exp(mpf(x)) * 10**18))
///   EOF
contract UUMathTest is Test {
    uint256 constant LAMBDA = 231_049_060_186_648_440_000; // ln(2)/0.003 * 1e18
    uint256 constant Q96 = 1 << 96;

    function _priceX96(uint256 numerator, uint256 denominator) internal pure returns (uint256) {
        return (numerator * Q96) / denominator;
    }

    function test_expNegWad_matchesReference() public pure {
        assertApproxEqRel(UUMath.expNegWad(-0.0001e18), 999900004999833337, 1e9);
        assertApproxEqRel(UUMath.expNegWad(-0.003e18), 997004495503372976, 1e9);
        assertApproxEqRel(UUMath.expNegWad(-0.03e18), 970445533548508176, 1e9);
        assertApproxEqRel(UUMath.expNegWad(-0.6931471805599453e18), 500000000000000004, 1e9);
        assertApproxEqRel(UUMath.expNegWad(-5e18), 6737946999085467, 1e9);
        assertApproxEqRel(UUMath.expNegWad(-41e18), 1, 1e9);
        assertEq(UUMath.expNegWad(0), 1e18);
    }

    function test_expNegWad_zeroBelowThreshold() public pure {
        assertEq(UUMath.expNegWad(-41446531673892822314), 0);
        assertEq(UUMath.expNegWad(-100e18), 0);
    }

    function test_expNegWad_revertsOnPositiveInput() public {
        // Internal library calls inline into the caller's frame, so
        // vm.expectRevert needs an external call boundary to attach to.
        vm.expectRevert(UUMath.PositiveInput.selector);
        this._expNegWadExternal(1);
    }

    function _expNegWadExternal(int256 x) external pure returns (uint256) {
        return UUMath.expNegWad(x);
    }

    function test_participation_upperBranchIsOne() public pure {
        assertEq(UUMath.participationWad(0, LAMBDA), 1e18);
        assertEq(UUMath.participationWad(1e15, LAMBDA), 1e18);
    }

    function test_participation_halvesAtThirtyBps() public pure {
        // r = -0.003 => P = 0.5 at the canonical lambda (spec §2.1).
        assertApproxEqRel(UUMath.participationWad(-3e15, LAMBDA), 5e17, 1e6);
    }

    function test_r_isZeroAtFairPriceZeroFee() public pure {
        uint256 p = _priceX96(1, 1);
        uint160 s = uint160(1 << 96); // sqrtPriceX96 for pool price == 1
        assertEq(UUMath.rWadMarginal(s, p, 0, true), 0);
        assertEq(UUMath.rWadMarginal(s, p, 0, false), 0);
    }

    function test_r_feeAlwaysHurts_deviationIsSigned() public pure {
        uint256 fair = _priceX96(1, 1);
        uint160 s = uint160(1 << 96);

        // Fair price, positive fee: both directions hurt (r < 0).
        assertLt(UUMath.rWadMarginal(s, fair, 3000, true), 0);
        assertLt(UUMath.rWadMarginal(s, fair, 3000, false), 0);

        // Pool above external (s corresponds to pool price 1.02, external 1):
        // selling token0 (A->B) benefits from the deviation (r rises versus
        // the fair-price case); the opposite side (B->A) is hurt further.
        uint256 poolAbove = _priceX96(102, 100);
        uint160 sAbove = uint160(Math_sqrtX96(poolAbove));

        int256 rAB_fair = UUMath.rWadMarginal(s, fair, 3000, true);
        int256 rAB_above = UUMath.rWadMarginal(sAbove, fair, 3000, true);
        assertGt(rAB_above, rAB_fair);

        int256 rBA_fair = UUMath.rWadMarginal(s, fair, 3000, false);
        int256 rBA_above = UUMath.rWadMarginal(sAbove, fair, 3000, false);
        assertLt(rBA_above, rBA_fair);
    }

    /// sqrt(priceX96 * 2**96), matching the sqrtPriceX96 convention used by
    /// ArbMath's test helper.
    function Math_sqrtX96(uint256 priceX96) internal pure returns (uint256) {
        return _sqrt(priceX96 * Q96);
    }

    function _sqrt(uint256 x) internal pure returns (uint256 y) {
        if (x == 0) return 0;
        uint256 z = (x + 1) / 2;
        y = x;
        while (z < y) {
            y = z;
            z = (x / z + z) / 2;
        }
    }
}
