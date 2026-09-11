// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {console} from "forge-std/console.sol";

import {Currency} from "v4-core/src/types/Currency.sol";
import {FixedPointMathLib} from "solmate/src/utils/FixedPointMathLib.sol";

import {Math} from "@openzeppelin/contracts/utils/math/Math.sol";

import {BaseOverrideFee} from "@openzeppelin/uniswap-hooks/src/fee/BaseOverrideFee.sol";
import {Hooks} from "@uniswap/v4-core/src/libraries/Hooks.sol";
import {IPoolManager, SwapParams, ModifyLiquidityParams} from "@uniswap/v4-core/src/interfaces/IPoolManager.sol";
import {PoolKey} from "@uniswap/v4-core/src/types/PoolKey.sol";
import {PoolId, PoolIdLibrary} from "@uniswap/v4-core/src/types/PoolId.sol";
import {BalanceDelta} from "@uniswap/v4-core/src/types/BalanceDelta.sol";
import {BeforeSwapDelta, BeforeSwapDeltaLibrary} from "@uniswap/v4-core/src/types/BeforeSwapDelta.sol";
import {StateLibrary} from "@uniswap/v4-core/src/libraries/StateLibrary.sol";
import {LPFeeLibrary} from "@uniswap/v4-core/src/libraries/LPFeeLibrary.sol";
import {PoolIdLibrary} from "@uniswap/v4-core/src/types/PoolId.sol";

import {AggregatorV2V3Interface} from "@chainlink/local/src/data-feeds/interfaces/AggregatorV2V3Interface.sol";

import {Ownable} from "@openzeppelin/contracts/access/Ownable.sol";

/**
 * @title PegStabilityHook
 * @notice Idea: if token B is bought from the pool (so its price increases) or DEX price B is already more than CEX price B
 * Then we stimulate swaps by keeping the minimum fee
 * On the other hand, Fee = percentage difference between Pool Price and CEX Price
 */
contract PegStabilityHook is BaseOverrideFee, Ownable {
    using StateLibrary for IPoolManager;
    using LPFeeLibrary for uint24;
    using PoolIdLibrary for PoolKey;

    IPoolManager private immutable _poolManager;

    // Price feeds
    AggregatorV2V3Interface private immutable _token0UsdtFeed;
    AggregatorV2V3Interface private immutable _token1UsdtFeed;

    /// @notice Which reading of "peg stability" this instance implements.
    /// @dev Defence taxes moves away from the reference and is faithful to the
    ///      name. Capture taxes the deviation on whichever trade occurs, which
    ///      is what recaptures LVR from the arbitrageur. They are different
    ///      policies, so both are run and compared rather than one being
    ///      chosen by assumption (spec §5).
    enum PegMode {
        Defence,
        Capture
    }

    PegMode public immutable mode;

    // token B / token A exchange rate
    uint256 private exchangeRate = 0;

    // Constants
    /// @notice Share of the observed deviation charged in Capture mode, in
    ///         millionths. 1e6 would charge the whole deviation.
    /// @dev Must be below 1e6 or the policy is provably inert. Charging the
    ///      full deviation makes the no-arbitrage band exactly wide enough to
    ///      contain the current pool price: with p = P(1+d) and f = d, the band
    ///      edge sits at P/(1-d), and (1+d)(1-d) < 1, so the pool is always
    ///      just inside it. The arbitrageur is left nothing and never trades —
    ///      measured as zero trades under every gas price and pool depth. The
    ///      spec says "proportional to |deviation|", and this is the constant of
    ///      proportionality.
    uint256 public captureShare = 500_000; // 50%

    uint24 public MAX_FEE_BPS = 10000; // 1% max fee allowed, 1% = 10_000
    uint24 public MIN_FEE_BPS = 100; // 0.01% mix fee allowed

    // Errors
    // @dev error when Invalid zero input params
    error InvalidZeroInput();

    /// @dev Error when custom max fee overflow
    error InvalidMaxFee();

    /// @dev Error when min fee overflow
    error InvalidMinFee();

    /// @dev Error when Invalid Currency in Pool
    error InvalidPoolCurrency();

    constructor(
        IPoolManager poolManager,
        AggregatorV2V3Interface token0UsdtFeed,
        AggregatorV2V3Interface token1UsdtFeed,
        PegMode mode_
    ) BaseOverrideFee() Ownable(msg.sender) {
        _poolManager = poolManager;
        _token0UsdtFeed = token0UsdtFeed;
        _token1UsdtFeed = token1UsdtFeed;
        mode = mode_;
    }

    /// @notice The fair square-root price implied by the two feeds.
    /// @dev Exposed so the ratio convention can be checked against BAHook's.
    function referenceSqrtPriceX96() external view returns (uint160) {
        return _getSqrtPriceRatioX96();
    }

    function poolManager() public view override returns (IPoolManager) {
        return _poolManager;
    }

    function setExchangeRate(uint256 rate) external onlyOwner {
        exchangeRate = rate;
    }

    /// @notice Sets the floor this policy falls back to when the pool is at
    ///         parity, denominated in hundredths of a bip.
    /// @dev This previously assigned MAX_FEE_BPS, so calling it moved the
    ///      ceiling instead of the fee and left no trace. There is no single
    ///      "the fee" for a deviation-driven policy; the floor is the closest
    ///      analogue and is what the shared fee box constrains.
    function setFee(uint24 _fee, PoolKey calldata) external onlyOwner {
        if (_fee > MAX_FEE_BPS) revert InvalidMinFee();
        MIN_FEE_BPS = _fee;
    }

    /// @notice Sets the share of the deviation charged in Capture mode.
    function setCaptureShare(uint256 share) external onlyOwner {
        require(share < 1e6, "share of 1e6 leaves the arbitrageur nothing");
        captureShare = share;
    }

    function setMaxFee(uint24 _fee) external onlyOwner {
        if (_fee < MIN_FEE_BPS) revert InvalidMaxFee();
        MAX_FEE_BPS = _fee;
    }

    function getFee(address caller, PoolKey calldata key, SwapParams calldata params, bytes calldata data)
        external
        returns (uint24)
    {
        return _getFee(caller, key, params, data);
    }

    function _getFee(address, PoolKey calldata key, SwapParams calldata params, bytes calldata)
        internal
        virtual
        override
        returns (uint24)
    {
        (uint160 sqrtPriceX96,,,) = _poolManager.getSlot0(key.toId());
        return _calculateFee(key.currency0, key.currency1, params.zeroForOne, sqrtPriceX96, _getSqrtPriceRatioX96());
    }

    // Helper to get current token0/token1 price ratio from feeds
    function _getSqrtPriceRatioX96() private view returns (uint160) {
        if (exchangeRate != 0) {
            return uint160(FixedPointMathLib.sqrt(exchangeRate) * (2 ** 96) / 1e9);
        }

        (, int256 token0Price,,,) = _token0UsdtFeed.latestRoundData();
        (, int256 token1Price,,,) = _token1UsdtFeed.latestRoundData();
        require(token0Price > 0 && token1Price > 0, "Invalid price data");

        // Uniswap prices token1 per token0, so the fair price is
        // token0Price / token1Price. This was inverted, which made the hook
        // read the market backwards and disagree with BAHook:69 on the same
        // feeds.
        uint256 ratioWad = uint256(token0Price) * 1e18 / uint256(token1Price);

        // No console.log here: _getFee runs on every swap, and logging in that
        // path both costs gas and distorts the gas measurements the experiment
        // depends on.
        return uint160(FixedPointMathLib.sqrt(ratioWad) * uint256(2 ** 96) / uint256(1e9));
    }

    /// @dev

    /**
     * @notice  Calculates the price for a swap
     * @dev     Fee = percentage difference between pool price and reference price
     *          i.e. if pool price is off by 0.05% the fee is 0.05%
     * @param   zeroForOne  True if buying token B, false if selling token B
     * @param   poolSqrtPriceX96  Current pool price
     * @param   referenceSqrtPriceX96  Reference price obtained from the rate provider
     * @return  uint24  Fee charged to the user - fee in pips, i.e. 3000 = 0.3%
     */
    function _calculateFee(Currency, Currency, bool zeroForOne, uint160 poolSqrtPriceX96, uint160 referenceSqrtPriceX96)
        internal
        view
        returns (uint24)
    {
        // Defence charges only the trade that pushes the pool further from the
        // reference. Selling token0 lowers the pool price, so it moves away
        // when the pool already sits below the reference; buying token0 is the
        // mirror image. Capture charges on whichever trade occurs.
        //
        // The former condition was `zeroForOne || pool < reference`, which gave
        // the whole zeroForOne direction the floor unconditionally and left
        // only one side defended.
        if (mode == PegMode.Defence) {
            bool movingAway =
                zeroForOne ? poolSqrtPriceX96 <= referenceSqrtPriceX96 : poolSqrtPriceX96 >= referenceSqrtPriceX96;
            if (!movingAway) return MIN_FEE_BPS;
        }

        // computes the absolute percentage difference between the pool price and the reference price
        // i.e. 0.005e18 = 0.50% difference between pool price and reference price
        uint256 absPercentageDiffWad = absPercentageDifferenceWad(uint160(poolSqrtPriceX96), referenceSqrtPriceX96);

        // console.log("PegStabilityHook. absPercentageDiffWad: ", absPercentageDiffWad);

        // convert percentage WAD to pips, i.e. 0.05e18 = 5% = 50_000
        uint256 charged = absPercentageDiffWad;
        if (mode == PegMode.Capture) {
            charged = charged * captureShare / 1e6;
        }
        uint24 fee = uint24(charged / 1e12);
        if (fee < MIN_FEE_BPS) {
            // if % depeg is less than min fee %. charge minFee
            fee = MIN_FEE_BPS;
        } else if (fee > MAX_FEE_BPS) {
            // if % depeg is more than max fee %. charge maxFee
            fee = MAX_FEE_BPS;
        }
        return fee;
    }

    /// @notice Calculates the absolute percentage difference between two sqrt prices in WAD units
    /// @dev 0.05e18 = 5%, for 95 vs 100 or 105 vs 100
    /// @param sqrtPriceX96 sqrt(p) * 2 ^ 96
    /// @param denominatorX96 sqrt(d) * 2 ^ 96
    /// @return The percentage difference in WAD units
    function absPercentageDifferenceWad(uint160 sqrtPriceX96, uint160 denominatorX96) internal pure returns (uint256) {
        uint160 Q96 = 2 ** 96;
        uint256 Q192 = 2 ** 192;
        // Calculate sqrt(p / d) * 2 ^ 96
        uint256 _divX96 = (uint256(sqrtPriceX96) * uint256(Q96)) / uint256(denominatorX96);

        // console.log("PegStabilityHook. _divX96 = ", _divX96);

        // convert to WAD
        uint256 _percentageDiffWad = Math.mulDiv(_divX96 ** 2, 1e18, Q192);
        // console.log("PegStabilityHook. _percentageDiffWad = ", _percentageDiffWad);
        return (1e18 < _percentageDiffWad) ? _percentageDiffWad - 1e18 : 1e18 - _percentageDiffWad;
    }
}
