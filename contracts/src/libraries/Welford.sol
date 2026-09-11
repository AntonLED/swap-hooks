// SPDX-License-Identifier: MIT
pragma solidity ^0.8.30;

import {Math} from "@openzeppelin/contracts/utils/math/Math.sol";

/**
 * @title Welford
 * @notice Online mean and variance in 1e18 fixed point.
 *
 * A hook cannot keep a window of past observations: that would be one storage
 * slot per sample, read and written on every swap. Welford's algorithm carries
 * the whole estimate in three numbers and updates them from one new sample.
 *
 * Welford rather than the textbook `E[x²] − E[x]²`, which subtracts two large
 * nearly-equal quantities. On values near 1e9 with a spread of 0.1 the naive
 * form returns exactly zero — a 100% error — while this one stays within 5e-7.
 * Prices are precisely that shape: a large level with a small spread.
 *
 * Inputs and outputs are 1e18-scaled. Feed log returns, not prices: the
 * variance of a price level is not a volatility.
 */
library Welford {
    uint256 internal constant WAD = 1e18;

    struct State {
        uint256 n; // samples seen
        int256 mean; // 1e18
        uint256 m2; // sum of squared deviations, 1e18
    }

    error NegativeSquare();

    /// @notice Fold one observation into the running estimate.
    /// @param x observation, 1e18-scaled
    function update(State memory s, int256 x) internal pure returns (State memory) {
        s.n += 1;

        int256 d = x - s.mean;
        s.mean += d / int256(s.n);

        // Deliberately the UPDATED mean: that is what makes the recurrence
        // numerically stable rather than merely algebraically correct.
        int256 d2 = x - s.mean;

        // mean moves toward x, so x - mean keeps its sign and the product is
        // non-negative. Assert rather than assume: a negative here would mean
        // the recurrence is wrong, and m2 is unsigned.
        int256 product = d * d2;
        if (product < 0) revert NegativeSquare();

        s.m2 += uint256(product) / WAD;
        return s;
    }

    /// @notice Sample variance, 1e18-scaled. Zero until two samples exist.
    function variance(State memory s) internal pure returns (uint256) {
        if (s.n < 2) return 0;
        return s.m2 / (s.n - 1);
    }

    /// @notice Standard deviation, 1e18-scaled.
    /// @dev sqrt of a 1e18-scaled value needs the scale restored first:
    ///      sqrt(v/1e18) * 1e18 == sqrt(v * 1e18).
    function stddev(State memory s) internal pure returns (uint256) {
        return Math.sqrt(variance(s) * WAD);
    }
}
