// SPDX-License-Identifier: MIT
pragma solidity ^0.8.30;

import {Test} from "forge-std/Test.sol";
import {UUMath} from "../src/libraries/UUMath.sol";

/// Adversarial, independent property tests for UUMath, written WITHOUT
/// reading contracts/src/libraries/UUMath.sol or contracts/test/UUMath.t.sol.
/// All expected values are computed independently in Python (mpmath / plain
/// arithmetic) from the formulas in
/// docs/superpowers/specs/2026-08-09-uu-flow-design.md §2, and re-derived in
/// the comment above each assertion so the numbers can be checked by hand.
contract UUAdversarialTest is Test {
    uint256 constant Q96 = 1 << 96; // 79228162514264337593543950336
    uint256 constant WAD = 1e18;
    uint256 constant LAMBDA = 231_049_060_186_648_440_000; // canonical, from the plan

    // ===================== Property 1: P = exp(-lambda*|r|) =====================

    /// mpmath reference (mp.dps=50): exp(x)*1e18 for x in the table below.
    function test_expNegWad_matchesIndependentMpmathTable() public pure {
        assertEq(UUMath.expNegWad(0), WAD);
        assertApproxEqRel(UUMath.expNegWad(-0.0001e18), 999900004999833337, 1e9);
        assertApproxEqRel(UUMath.expNegWad(-0.003e18), 997004495503372976, 1e9);
        assertApproxEqRel(UUMath.expNegWad(-0.03e18), 970445533548508176, 1e9);
        assertApproxEqRel(UUMath.expNegWad(-0.1e18), 904837418035959573, 1e9);
        assertApproxEqRel(UUMath.expNegWad(-1e18), 367879441171442321, 1e9);
        assertApproxEqRel(UUMath.expNegWad(-5e18), 6737946999085467, 1e9);
        assertApproxEqRel(UUMath.expNegWad(-20e18), 2061153622, 1e9);
    }

    function test_expNegWad_deepUnderflowReturnsZero() public pure {
        // exp(-45) * 1e18 underflows to 0 well past the documented -41.45e18
        // cutoff.
        assertEq(UUMath.expNegWad(-45e18), 0);
        assertEq(UUMath.expNegWad(-100e18), 0);
    }

    function test_expNegWad_isMonotoneDecreasing() public pure {
        uint256 a = UUMath.expNegWad(-1e15);
        uint256 b = UUMath.expNegWad(-1e16);
        uint256 c = UUMath.expNegWad(-1e17);
        uint256 d = UUMath.expNegWad(-1e18);
        assertGt(a, b);
        assertGt(b, c);
        assertGt(c, d);
    }

    function test_participation_upperBranchIsAlwaysOne_rNonNegative() public pure {
        assertEq(UUMath.participationWad(0, LAMBDA), WAD);
        assertEq(UUMath.participationWad(1, LAMBDA), WAD);
        assertEq(UUMath.participationWad(int256(WAD), LAMBDA), WAD);
        assertEq(UUMath.participationWad(int256(1000 * WAD), 924e18), WAD);
    }

    /// Independent mpmath: exp(-231.049060186648440000 * 0.003) =
    /// 0.49999999999999999470... => P = 0.5 to within 1e-6 relative, per the
    /// spec's own worked example (§2.1).
    function test_participation_halvesAtCanonicalLambdaAndThirtyBps() public pure {
        uint256 p = UUMath.participationWad(-3e15, LAMBDA);
        assertApproxEqRel(p, 5e17, 1e6);
    }

    /// Independent mpmath sweep at r=-0.003 across the spec's declared
    /// lambda values {58,116,231,462,924} (§2.1): P(30bps) in
    /// {0.84, 0.71, 0.50, 0.25, 0.0625} approximately, computed here to full
    /// precision rather than the spec's rounded headline figures.
    function test_participation_lambdaSweepMatchesIndependentReference() public pure {
        assertApproxEqRel(UUMath.participationWad(-3e15, 58e18), 840296897658431400, 1e9);
        assertApproxEqRel(UUMath.participationWad(-3e15, 116e18), 706098876214384400, 1e9);
        assertApproxEqRel(UUMath.participationWad(-3e15, 231e18), 500073595695767700, 1e9);
        assertApproxEqRel(UUMath.participationWad(-3e15, 462e18), 250073601112094100, 1e9);
        assertApproxEqRel(UUMath.participationWad(-3e15, 924e18), 62536805973170750, 1e9);
    }

    function test_participation_monotoneDecreasingInAbsR() public pure {
        uint256 p1 = UUMath.participationWad(-1e15, LAMBDA);
        uint256 p2 = UUMath.participationWad(-3e15, LAMBDA);
        uint256 p3 = UUMath.participationWad(-1e16, LAMBDA);
        uint256 p4 = UUMath.participationWad(-1e17, LAMBDA);
        assertGt(p1, p2);
        assertGt(p2, p3);
        assertGt(p3, p4);
    }

    function test_participation_monotoneDecreasingInLambda() public pure {
        int256 r = -3e15;
        uint256 p58 = UUMath.participationWad(r, 58e18);
        uint256 p116 = UUMath.participationWad(r, 116e18);
        uint256 p231 = UUMath.participationWad(r, 231e18);
        uint256 p462 = UUMath.participationWad(r, 462e18);
        uint256 p924 = UUMath.participationWad(r, 924e18);
        assertGt(p58, p116);
        assertGt(p116, p231);
        assertGt(p231, p462);
        assertGt(p462, p924);
    }

    // ============ Property 2: r = gamma*p/P - 1 (or gamma*P/p - 1) ============

    /// s = Q96 (sqrtPrice = 1, pool price X96 = Q96), ext = Q96 (external
    /// ratio = 1): fee = 0 => r = 0 exactly, both directions.
    function test_r_isExactlyZeroAtFairPriceZeroFee_bothDirections() public pure {
        int256 rAB = UUMath.rWadMarginal(uint160(Q96), Q96, 0, true);
        int256 rBA = UUMath.rWadMarginal(uint160(Q96), Q96, 0, false);
        assertApproxEqAbs(rAB, int256(0), 1e6); // << 1e-18 relative to WAD
        assertApproxEqAbs(rBA, int256(0), 1e6);
    }

    /// At p == P exactly, gamma = 1 - fee/1e6 directly gives r = -fee/1e6
    /// with no rounding from the price ratio: feePips=3000 => r = -0.003e18
    /// exactly, both directions, and both must be strictly negative (fee
    /// always hurts).
    function test_r_feeAlwaysHurts_bothDirections_atFairPrice() public pure {
        int256 rAB = UUMath.rWadMarginal(uint160(Q96), Q96, 3000, true);
        int256 rBA = UUMath.rWadMarginal(uint160(Q96), Q96, 3000, false);
        assertApproxEqAbs(rAB, int256(-3e15), 1e6);
        assertApproxEqAbs(rBA, int256(-3e15), 1e6);
        assertLt(rAB, int256(0));
        assertLt(rBA, int256(0));
    }

    /// Fee monotonically hurts more as it rises, at fair price, both sides.
    function test_r_isMonotoneDecreasingInFee_atFairPrice() public pure {
        int256 rLow = UUMath.rWadMarginal(uint160(Q96), Q96, 100, true);
        int256 rMid = UUMath.rWadMarginal(uint160(Q96), Q96, 3000, true);
        int256 rHigh = UUMath.rWadMarginal(uint160(Q96), Q96, 10000, true);
        assertGt(rLow, rMid);
        assertGt(rMid, rHigh);
    }

    /// s = Q96 fixed (pool price ratio = 1 exactly). ext_above =
    /// floor(Q96*100/101) so p/ext_above = 1.01 (pool 1% ABOVE external, to
    /// ~1e-29 relative rounding, computed independently in Python):
    ///   p/P = 1.01000000000000000... => r_AB (selling token0) = +0.01
    ///   P/p = 0.99009900990099...    => r_BA (buying token0)  = -0.00990099...
    function test_r_deviationIsSigned_poolAboveExternal_sellingGainsBuyingLoses() public pure {
        uint256 extAbove = 78443725261647859003508861718; // floor(Q96*100/101)
        int256 rAB = UUMath.rWadMarginal(uint160(Q96), extAbove, 0, true); // selling token0 (A->B)
        int256 rBA = UUMath.rWadMarginal(uint160(Q96), extAbove, 0, false); // buying token0 (B->A)

        assertGt(rAB, int256(0));
        assertLt(rBA, int256(0));
        // NOTE: tolerance is 1% relative (1e16), not tight -- see
        // test_r_reciprocal_hasLargeErrorAtSmallDeviation below, which pins
        // an exact reproduction showing the reciprocal-direction (B->A) value
        // is NOT always close to the spec's literal P/p-1 at tight tolerance.
        assertApproxEqRel(rAB, int256(10000000000000009), 1e16); // ~+0.01e18
        assertApproxEqRel(rBA, int256(-9900990099009910), 1e16); // ~-0.0099009901e18
    }

    /// Mirror of the case above: ext_below = ceil-ish Q96*101/100 so
    /// p/ext_below = 1/1.01 (pool 1% BELOW external). Selling into a
    /// below-external pool must now lose, buying must gain -- an exact sign
    /// flip of the previous test, confirming symmetry.
    function test_r_mirrorDirection_poolBelowExternal_isSignFlipped() public pure {
        uint256 extBelow = 80020444139406980969479389839; // floor(Q96*101/100)
        int256 rAB = UUMath.rWadMarginal(uint160(Q96), extBelow, 0, true); // selling token0
        int256 rBA = UUMath.rWadMarginal(uint160(Q96), extBelow, 0, false); // buying token0

        assertLt(rAB, int256(0));
        assertGt(rBA, int256(0));
        assertApproxEqRel(rAB, int256(-9900990099009910), 1e16);
        assertApproxEqRel(rBA, int256(10000000000000009), 1e16);
    }

    /// ADVERSARIAL FINDING (documented, not fixed): black-box probing found
    /// rWad's reciprocal-direction value does not track the spec's literal
    /// formula uniformly across scales. Minimal reproduction: sqrtPriceX96 =
    /// Q96 (p = Q96 exactly), extPriceX96 = floor(Q96*1000/1001) so that
    /// p/P = 1.001 exactly (up to ~1e-30 relative floor-rounding noise,
    /// verified independently in Python).
    ///
    /// Spec §2.2: "UU selling token1 (B→A): r = γ_BA · P/p − 1". With
    /// gamma=1 (feePips=0): P/p = 1/1.001 = 0.999000999000999...,
    /// so r_BA should be -0.0009990009990009652 (WAD: -999000999000965).
    ///
    /// Observed (this harness, this run): rBA = -1000000000000000 exactly
    /// (-0.001 exactly to 18dp), i.e. exactly the negative of rAB
    /// (rAB = p/P - 1 = +0.001 exactly, which DOES match the spec formula
    /// for A->B here). -0.001 is the first-order/linear approximation of
    /// the true reciprocal (1/(1+x) ~= 1-x for small x), not the exact
    /// reciprocal -- a ~0.1% relative error, three orders of magnitude
    /// looser than the ~1e-6 relative agreement seen at a 1% deviation
    /// (test_r_deviationIsSigned_poolAboveExternal_sellingGainsBuyingLoses)
    /// or the ~1e-5 relative agreement seen at a 10% deviation. The error
    /// does not shrink monotonically with |r| as an honest fixed-point
    /// rounding error would; it is largest in the 0.01%-0.1% deviation band.
    /// This assertion is deliberately tight (1e-4 relative) and is EXPECTED
    /// TO FAIL -- it exists to pin the exact reproduction for review, not to
    /// pass. Do not loosen it to make it green; if the underlying behavior
    /// is intentional, update this comment to say why and relax explicitly.
    function test_r_reciprocal_hasLargeErrorAtSmallDeviation() public pure {
        uint256 ext = (Q96 * 1000) / 1001; // p/P = 1.001 exactly
        int256 rBA = UUMath.rWadMarginal(uint160(Q96), ext, 0, false);
        // independent Python reference: P/p - 1 = -999000999000965 (WAD)
        assertApproxEqRel(rBA, int256(-999000999000965), 1e14); // 0.01% relative
    }

    // ================= Composition: participation over r's range =================

    function test_participation_composedWithR_isOneOnFavorableSide() public pure {
        uint256 extAbove = 78443725261647859003508861718;
        int256 rAB = UUMath.rWadMarginal(uint160(Q96), extAbove, 0, true); // favorable, r > 0
        assertEq(UUMath.participationWad(rAB, LAMBDA), WAD);
    }

    function test_participation_composedWithR_isLessThanOneOnUnfavorableSide() public pure {
        uint256 extAbove = 78443725261647859003508861718;
        int256 rBA = UUMath.rWadMarginal(uint160(Q96), extAbove, 0, false); // unfavorable, r < 0
        uint256 p = UUMath.participationWad(rBA, LAMBDA);
        assertLt(p, WAD);
        assertGt(p, 0);
    }
}
