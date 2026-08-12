// SPDX-License-Identifier: MIT
pragma solidity ^0.8.30;

import {FullMath} from "@uniswap/v4-core/src/libraries/FullMath.sol";
import {SqrtPriceMath} from "@uniswap/v4-core/src/libraries/SqrtPriceMath.sol";

/**
 * @title UUMath
 * @notice Harness math for the uninformed-user (UU) flow model: spec
 *         `docs/superpowers/specs/2026-08-09-uu-flow-design.md` §2. Like
 *         `ArbMath`, this is harness math computed at runtime from pool
 *         state -- policy contracts under `contracts/src/*.sol` are
 *         untouched by this file.
 *
 * A UU user "sees" the external price and either trades or walks away with
 * probability `P = 1` if `r >= 0` else `exp(-lambda*|r|)`, where `r` is the
 * marginal, zero-size disadvantage of trading in that direction against that
 * fee (§2.2). Both `Q96`/`FullMath` conventions below are identical to
 * `ArbMath`: `priceX96` values are token1-per-token0, scaled by `2**96`.
 */
library UUMath {
    uint256 internal constant ONE_PIPS = 1_000_000;
    uint256 internal constant Q96 = 1 << 96;
    uint256 internal constant WAD = 1e18;

    /// @notice `expNegWad` is defined only for `x <= 0`; the caller (this
    ///         library) never produces a positive exponent, so a positive
    ///         input means a caller bug, not a domain edge to paper over.
    error PositiveInput();

    /// @notice `e^x`, denominated in WAD, restricted to `x <= 0`.
    /// @dev Ported from Solady's `FixedPointMathLib.expWad`
    ///      (https://github.com/Vectorized/solady/blob/main/src/utils/FixedPointMathLib.sol),
    ///      MIT licensed there, credit to Remco Bloemen under MIT license
    ///      (https://2π.com/22/exp-ln). The upstream function also handles
    ///      large positive `x` (an `ExpOverflow` branch); that branch is
    ///      dropped here because the participation formula (`participationWad`
    ///      below) only ever evaluates `exp` at `x <= 0` -- everything else is
    ///      the original rational-approximation algorithm, unmodified.
    function expNegWad(int256 x) internal pure returns (uint256) {
        if (x > 0) revert PositiveInput();
        // Below this point exp(x) < 0.5 wei and rounds to zero; same
        // threshold as upstream (~ -41.446531673892822313).
        if (x <= -41446531673892822313) return 0;

        int256 r;
        unchecked {
            // `x` is in `(-42, 0] * 1e18`. Convert to `(-42, 0] * 2**96` for
            // more intermediate precision and a binary basis -- a
            // multiplication by `1e18 / 2**96 = 5**18 / 2**78`.
            x = (x << 78) / 5 ** 18;

            // Reduce range of x to (-1/2 ln 2, 1/2 ln 2) * 2**96 by factoring
            // out powers of two such that exp(x) = exp(x') * 2**k, k integer:
            // k = round(x / log(2)), x' = x - k * log(2).
            int256 k = ((x << 96) / 54916777467707473351141471128 + 2 ** 95) >> 96;
            x = x - k * 54916777467707473351141471128;

            // Evaluate using a (6, 7)-term rational approximation. `p` is
            // made monic; the scale factor is folded in below.
            int256 y = x + 1346386616545796478920950773328;
            y = ((y * x) >> 96) + 57155421227552351082224309758442;
            int256 p = y + x - 94201549194550492254356042504812;
            p = ((p * y) >> 96) + 28719021644029726153956944680412240;
            p = p * x + (4385272521454847904659076985693276 << 96);

            int256 q = x - 2855989394907223263936484059900;
            q = ((q * x) >> 96) + 50020603652535783019961831881945;
            q = ((q * x) >> 96) - 533845033583426703283633433725380;
            q = ((q * x) >> 96) + 3604857256930695427073651918091429;
            q = ((q * x) >> 96) - 14423608567350463180887372962807573;
            q = ((q * x) >> 96) + 26449188498355588339934803723976023;

            /// @solidity memory-safe-assembly
            assembly {
                // Div in assembly because solidity adds a zero check despite
                // the unchecked block. q has no zeros in this domain (all
                // its roots are complex).
                r := sdiv(p, q)
            }

            // Multiply by the scale factor, the 2**k range-reduction factor,
            // and the 1e18/2**96 base-conversion factor, all at once.
            r = int256((uint256(r) * 3822833074963236453042738258902158003155416615667) >> uint256(195 - k));
        }
        return uint256(r);
    }

    /// @notice Marginal, zero-size UU disadvantage `r` at the pre-swap pool
    ///         state (spec §2.2). Pool price X96 = `sqrtPriceX96^2 / 2**96`,
    ///         same convention as `ArbMath.targetSqrtPriceX96`.
    /// @param sqrtPriceX96 pre-swap pool sqrt price, Q96
    /// @param extPriceX96 external price of token0 in token1, Q96 scaled
    /// @param feePips the direction's applied fee, pips (1e6 == 100%)
    /// @param zeroForOne true for a UU user selling token0 (A->B)
    /// @notice The source model's `r`, from the realised outcome of the trade.
    ///
    /// @dev `r = dP(dx, dy) / dP(|dx|, |dy|)` -- the signed change in the
    ///      user's portfolio value over the gross value moved. Writing `V_in`
    ///      and `V_out` for the two legs valued at the EXTERNAL price:
    ///
    ///          r = (V_out - V_in) / (V_out + V_in)
    ///
    ///      Three properties this buys, none of which the previous form had:
    ///
    ///      1. **Slippage is inside it.** `V_out` is what the constant-product
    ///         curve actually pays for `grossIn`, so the finite-size execution
    ///         cost enters `r` by construction. The previous implementation
    ///         evaluated a marginal (zero-size) price and therefore omitted a
    ///         term measured at 3.2 bps on the median 2024 candle and 6.9 bps
    ///         on the mean -- above the 1 bp floor of the fee box, not two
    ///         orders below it as the design spec claimed.
    ///      2. **It is normalised**, so `|r| <= 1` and `r` is scale-free. The
    ///         denominator makes `r` approximately HALF the fractional
    ///         disadvantage (`r = -eps/(2-eps)`), which is why lambda is
    ///         calibrated at 461.404973 rather than 231.049060 for the same
    ///         "half the willing flow walks at a 30 bps total cost".
    ///      3. **The pool deviation still enters signed**: a user trading
    ///         toward the external price can have `V_out > V_in`, giving
    ///         `r > 0` and `P = 1`.
    ///
    ///      Amounts come from `SqrtPriceMath`, never hand-rolled algebra, so
    ///      the rounding matches what the pool will actually pay.
    ///
    /// @param sqrtPriceX96 pre-swap pool sqrt price
    /// @param liquidity    pool liquidity in range
    /// @param extPriceX96  external price, token1 per token0, X96-scaled
    /// @param feePips      the fee this direction would be charged
    /// @param zeroForOne   true when the user sells token0
    /// @param grossIn      the input amount the decision is evaluated at
    /// @param gasCost the trade's own gas, in token1 units -- the valuation
    ///        currency BOTH branches below use (`valueOut` for B->A is amount0
    ///        times the token1-per-token0 external price, i.e. token1). An
    ///        earlier caller comment claimed the B->A branch was valued in
    ///        token0 and converted gas accordingly; that mismatch understated
    ///        B->A retail gas by price0/price1 on every UU run before
    ///        2026-08-12. Zero disables it.
    ///
    /// @dev Gas is a third outflow, so it enters both halves of the source
    ///      ratio: `r = (V_out − V_in − G)/(V_out + V_in + G)`.
    ///
    ///      Excluding it made the gas axis inert. Measured on the superseded
    ///      matrix: raising gas 5 → 80 gwei multiplied the arbitrageur's gas
    ///      bill by 16 and left `uu_participation` at 0.7238 → 0.7200, because
    ///      retail could not see gas at all. Real retail sees little else — a
    ///      small swap at 80 gwei pays more in gas than in fee.
    ///
    ///      This is expressible only because the trade has a size. Under the
    ///      deterministic-share mode the UU side is a continuum of
    ///      infinitesimal users and "gas per user" is undefined; under
    ///      `discrete` each draw is a trade of a definite size, and its gas is
    ///      an ordinary cost. That is the substantive reason the matrix runs in
    ///      discrete mode.
    function rWad(
        uint160 sqrtPriceX96,
        uint128 liquidity,
        uint256 extPriceX96,
        uint24 feePips,
        bool zeroForOne,
        uint256 grossIn,
        uint256 gasCost
    ) internal pure returns (int256) {
        if (grossIn == 0 || liquidity == 0) return 0;

        uint256 netIn = FullMath.mulDiv(grossIn, ONE_PIPS - uint256(feePips), ONE_PIPS);
        if (netIn == 0) return -int256(WAD); // the fee ate the whole trade

        uint160 s2 = SqrtPriceMath.getNextSqrtPriceFromInput(sqrtPriceX96, liquidity, netIn, zeroForOne);

        // Both legs in a common currency: token1 units, in BOTH branches --
        // selling token0 values the input at the token1-per-token0 external
        // price, and buying token0 values the output at it.
        uint256 valueIn;
        uint256 valueOut;
        if (zeroForOne) {
            valueOut = SqrtPriceMath.getAmount1Delta(s2, sqrtPriceX96, liquidity, false);
            valueIn = FullMath.mulDiv(grossIn, extPriceX96, Q96);
        } else {
            valueOut = FullMath.mulDiv(
                SqrtPriceMath.getAmount0Delta(sqrtPriceX96, s2, liquidity, false), extPriceX96, Q96
            );
            valueIn = grossIn;
        }

        // Gas joins the outflow side of the numerator and the gross of the
        // denominator: the user pays it, and it is part of what they moved.
        uint256 outflow = valueIn + gasCost;
        uint256 total = outflow + valueOut;
        if (total == 0) return 0;

        // (out - in - gas)/(out + in + gas), WAD-scaled, computed on the
        // unsigned parts so the single mulDiv truncation is the only rounding.
        if (valueOut >= outflow) {
            return int256(FullMath.mulDiv(valueOut - outflow, WAD, total));
        }
        return -int256(FullMath.mulDiv(outflow - valueOut, WAD, total));
    }

    /// @notice SUPERSEDED marginal-price form, kept only so the differential
    ///         test can show what changed. Do not use for new work: it omits
    ///         slippage and is twice the source model's `r`.
    function rWadMarginal(uint160 sqrtPriceX96, uint256 extPriceX96, uint24 feePips, bool zeroForOne)
        internal
        pure
        returns (int256)
    {
        uint256 poolPriceX96 = FullMath.mulDiv(sqrtPriceX96, sqrtPriceX96, Q96);
        uint256 gammaPips = ONE_PIPS - uint256(feePips);

        // gammaPips -> WAD is an EXACT scaling (WAD/ONE_PIPS = 1e12, an
        // integer), so folding it in before the mulDiv leaves exactly one
        // truncation, at 1e-18 relative -- not two. Previously this computed
        // `mulDiv(mulDiv(num, gammaPips, den), WAD, ONE_PIPS)`: the inner
        // mulDiv rounds down to 1e-6 relative (pips) granularity BEFORE the
        // WAD scaling, so r was quantized in 0.1bp steps. At p/P = 1.001,
        // fee = 0, the correct r is -0.000999000999..., but the pips-first
        // path computed floor(999000.999...) = 999000 pips exactly,
        // producing r = -0.001 exactly -- a ~0.1% relative error three
        // orders of magnitude looser than the precision the WAD scale
        // implies (2026-08-09 adversarial review,
        // test_r_reciprocal_hasLargeErrorAtSmallDeviation).
        uint256 gammaWad = gammaPips * 1e12;

        // A->B (selling token0): r = gamma * p/P - 1.
        // B->A (selling token1): r = gamma * P/p - 1.
        (uint256 num, uint256 den) = zeroForOne ? (poolPriceX96, extPriceX96) : (extPriceX96, poolPriceX96);
        uint256 scaledWad = FullMath.mulDiv(num, gammaWad, den);
        return int256(scaledWad) - int256(WAD);
    }

    /// @notice Execution probability, the two-branch model of spec §2:
    ///         `P = 1` if `r >= 0`, else `exp(-lambda*|r|)`.
    /// @param r WAD-scaled disadvantage from `rWad`
    /// @param lambdaWad WAD-scaled scale parameter (canonical default in
    ///        `UU_LAMBDA_WAD`, swept in the sensitivity axis)
    function participationWad(int256 r, uint256 lambdaWad) internal pure returns (uint256) {
        if (r >= 0) return WAD;
        // r < 0 and lambdaWad >= 0, so this product is already <= 0 --
        // exactly the `-lambda*|r|` exponent expNegWad expects.
        int256 exponent = (int256(lambdaWad) * r) / int256(WAD);
        return expNegWad(exponent);
    }
}
