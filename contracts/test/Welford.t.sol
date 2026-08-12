// SPDX-License-Identifier: MIT
pragma solidity ^0.8.30;

import {Test} from "forge-std/Test.sol";
import {Welford} from "../src/libraries/Welford.sol";

/**
 * @notice Checked against `experiments/reference/welford.py`, which is in turn
 *         checked against Python's `statistics` module. Two independent
 *         implementations agreeing is the point; a Solidity-only test would
 *         only prove the code matches itself.
 */
contract WelfordTest is Test {
    using Welford for Welford.State;

    /// Reference vector and expectations produced by the Python reference:
    ///   inputs  1e15, -2e15, 3e15, -1e15, 2e15, 0, -3e15, 1e15   (1e18-scaled)
    ///   mean      125000000000000
    ///   variance    4125000000000
    ///   stddev   2031009601158990
    function _vector() internal pure returns (int256[8] memory v) {
        v = [
            int256(1e15),
            int256(-2e15),
            int256(3e15),
            int256(-1e15),
            int256(2e15),
            int256(0),
            int256(-3e15),
            int256(1e15)
        ];
    }

    function _run(int256[8] memory v) internal pure returns (Welford.State memory s) {
        for (uint256 i = 0; i < v.length; i++) {
            s = Welford.update(s, v[i]);
        }
    }

    function test_meanMatchesThePythonReference() public pure {
        Welford.State memory s = _run(_vector());
        assertApproxEqAbs(uint256(s.mean), 125000000000000, 1000);
    }

    function test_varianceMatchesThePythonReference() public pure {
        Welford.State memory s = _run(_vector());
        assertApproxEqRel(Welford.variance(s), 4125000000000, 1e12); // 1e-6 relative
    }

    function test_stddevMatchesThePythonReference() public pure {
        Welford.State memory s = _run(_vector());
        assertApproxEqRel(Welford.stddev(s), 2031009601158990, 1e12);
    }

    function test_countTracksTheSamplesSeen() public pure {
        Welford.State memory s = _run(_vector());
        assertEq(s.n, 8);
    }

    function test_constantSeriesHasZeroVariance() public pure {
        Welford.State memory s;
        for (uint256 i = 0; i < 10; i++) {
            s = Welford.update(s, 7e18);
        }
        assertEq(Welford.variance(s), 0);
        assertEq(uint256(s.mean), 7e18);
    }

    function test_oneSampleHasNoVariance() public pure {
        Welford.State memory s;
        s = Welford.update(s, 5e18);
        assertEq(Welford.variance(s), 0, "sample variance needs two points");
        assertEq(Welford.stddev(s), 0);
    }

    function test_emptyStateIsZero() public pure {
        Welford.State memory s;
        assertEq(Welford.variance(s), 0);
        assertEq(s.n, 0);
    }

    /// Variance is translation-invariant. This is the integer analogue of the
    /// cancellation test in the Python reference: shifting every sample by a
    /// large constant must not disturb the spread.
    function test_varianceIsUnchangedByALargeOffset() public pure {
        int256[8] memory plain = _vector();
        int256[8] memory shifted;
        for (uint256 i = 0; i < plain.length; i++) {
            shifted[i] = plain[i] + 1e21; // a level 1e6 times the spread
        }

        uint256 a = Welford.variance(_run(plain));
        uint256 b = Welford.variance(_run(shifted));

        assertApproxEqRel(b, a, 1e12, "a large level must not move the variance");
    }

    function test_largerSpreadGivesLargerVariance() public pure {
        int256[8] memory tight = _vector();
        int256[8] memory wide;
        for (uint256 i = 0; i < tight.length; i++) {
            wide[i] = tight[i] * 10;
        }

        assertGt(Welford.variance(_run(wide)), Welford.variance(_run(tight)));
    }
}
