// SPDX-License-Identifier: MIT
pragma solidity ^0.8.30;

import {FullMath} from "@uniswap/v4-core/src/libraries/FullMath.sol";
import {TickMath} from "@uniswap/v4-core/src/libraries/TickMath.sol";
import {Math} from "@openzeppelin/contracts/utils/math/Math.sol";

/**
 * @title ArbMath
 * @notice Pure arbitrage math for a full-range constant-product pool.
 *
 * With proportional fee f and gamma = 1 - f, the no-arbitrage band on the pool
 * price (token1 per token0) is [P*gamma, P/gamma] for external price P. The
 * profit-maximising trade moves the pool exactly to the near edge. See
 * Appendix A of the experiment design spec for the derivation.
 *
 * Prices are Uniswap Q96 fixed point: `externalPriceX96` is P * 2^96, and
 * returned values are sqrt(price) * 2^96.
 */
library ArbMath {
    uint256 internal constant ONE_PIPS = 1_000_000;
    uint256 internal constant Q96 = 1 << 96;

    error PriceOutOfRange();

    /// @notice The pool price the arbitrageur drives the pool to.
    /// @dev Reverts rather than truncating if the target leaves the range the
    ///      protocol can represent; a silent uint160 cast would produce a
    ///      plausible but wrong target.
    /// @param externalPriceX96 external price of token0 in token1, Q96 scaled
    /// @param feePips fee in hundredths of a bip (1e6 == 100%)
    /// @param zeroForOne true when selling token0 into the pool
    function targetSqrtPriceX96(uint256 externalPriceX96, uint24 feePips, bool zeroForOne)
        internal
        pure
        returns (uint160)
    {
        uint256 gammaPips = ONE_PIPS - uint256(feePips);

        uint256 targetPriceX96 = zeroForOne
            ? FullMath.mulDiv(externalPriceX96, ONE_PIPS, gammaPips)
            : FullMath.mulDiv(externalPriceX96, gammaPips, ONE_PIPS);

        // sqrt(price) * 2^96 == sqrt(priceX96 * 2^96)
        uint256 root = Math.sqrt(FullMath.mulDiv(targetPriceX96, Q96, 1));

        if (root <= uint256(TickMath.MIN_SQRT_PRICE) || root >= uint256(TickMath.MAX_SQRT_PRICE)) {
            revert PriceOutOfRange();
        }
        return uint160(root);
    }

    /// @notice Whether the pool sits outside the band on the given side.
    function shouldTrade(uint160 currentSqrtPriceX96, uint160 targetSqrtPriceX96_, bool zeroForOne)
        internal
        pure
        returns (bool)
    {
        return zeroForOne ? currentSqrtPriceX96 > targetSqrtPriceX96_ : currentSqrtPriceX96 < targetSqrtPriceX96_;
    }

    /// @notice Gross up a post-fee input to the amount to send.
    /// @dev v4 deducts the LP fee from the input before the swap math, so
    ///      moving the price by `netInput` requires sending more than that.
    function grossInput(uint256 netInput, uint24 feePips) internal pure returns (uint256) {
        if (feePips == 0) return netInput;
        return FullMath.mulDivRoundingUp(netInput, ONE_PIPS, ONE_PIPS - uint256(feePips));
    }

    /// @notice Closed-form optimal profit, denominated in token1.
    /// @dev The two directions are NOT symmetric, and treating them as such was
    ///      a defect here.
    ///
    ///      Selling token0: the fee is taken from the token0 input, and the
    ///      grossing-up cancels against the external valuation of that input,
    ///      leaving Pi* = L(s-t)^2 / s.
    ///
    ///      Buying token0: the fee is taken from the token1 input, which is the
    ///      side the profit is denominated in, so nothing cancels and
    ///      Pi* = L(t-s)^2 / (gamma * s) -- larger by 1/gamma.
    ///
    ///      Applying the sell formula to both understated buy-side profit by
    ///      exactly gamma, which biased the gas entry test against buys.
    function profit(uint128 liquidity, uint160 currentSqrtPriceX96, uint160 targetSqrtPriceX96_, uint24 feePips)
        internal
        pure
        returns (uint256)
    {
        uint256 s = uint256(currentSqrtPriceX96);
        uint256 t = uint256(targetSqrtPriceX96_);
        uint256 gap = s > t ? s - t : t - s;
        uint256 base = FullMath.mulDiv(FullMath.mulDiv(liquidity, gap, s), gap, Q96);

        // Selling token0 drives the price down, so t < s.
        if (t < s) return base;
        return FullMath.mulDiv(base, ONE_PIPS, ONE_PIPS - uint256(feePips));
    }
}
