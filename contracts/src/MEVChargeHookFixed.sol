// SPDX-License-Identifier: MIT
pragma solidity ^0.8.30;

import {IPoolManager, SwapParams} from "@uniswap/v4-core/src/interfaces/IPoolManager.sol";
import {PoolKey} from "@uniswap/v4-core/src/types/PoolKey.sol";
import {PoolIdLibrary} from "@uniswap/v4-core/src/types/PoolId.sol";
import {StateLibrary} from "@uniswap/v4-core/src/libraries/StateLibrary.sol";
import {FullMath} from "@uniswap/v4-core/src/libraries/FullMath.sol";

import {AggregatorV2V3Interface} from "@chainlink/local/src/data-feeds/interfaces/AggregatorV2V3Interface.sol";

import {MEVChargeHook} from "./MEVChargeHook.sol";

/**
 * @title MEVChargeHook with a dimensionless impact measure
 * @notice Identical to `MEVChargeHook` except for how it sizes a trade.
 *
 * The shipped template divides the input amount by the pool's liquidity `L`.
 * Those are different kinds of quantity -- `L` is sqrt-price-scaled, the amount
 * is denominated in whichever token is paid in -- so the ratio is eight orders
 * of magnitude larger on ETH/SHIB when the input is SHIB. Measured across the
 * matrix, every purchase of token0 cleared the 500 bp trigger and no sale of
 * token0 ever did: a median fee of 354 bps one way against 30 bps the other.
 * The surcharge tracked the input's denomination, not price impact.
 *
 * Here the amount is divided by the reserve of the token actually being paid
 * in, which is dimensionless and symmetric between directions:
 *
 *   reserve0 = L / sqrt(P),  reserve1 = L * sqrt(P)
 *
 * Both versions are run, so the paper can report the template as shipped and
 * show what the policy does once the term measures what it claims to.
 */
contract MEVChargeHookFixed is MEVChargeHook {
    using PoolIdLibrary for PoolKey;
    using StateLibrary for IPoolManager;

    uint256 private constant Q96 = 1 << 96;

    constructor(IPoolManager poolManager_, AggregatorV2V3Interface a, AggregatorV2V3Interface b)
        MEVChargeHook(poolManager_, a, b)
    {}

    /// @inheritdoc MEVChargeHook
    function _impactRatioBps(PoolKey calldata key, bool zeroForOne, uint256 absAmount, uint128 liq)
        internal
        view
        override
        returns (uint256)
    {
        if (liq == 0) return 0;
        (uint160 sqrtPriceX96,,,) = poolManager().getSlot0(key.toId());
        if (sqrtPriceX96 == 0) return 0;

        // The reserve of the token being paid in. Full-range position, so the
        // usual v3 amounts collapse to these.
        uint256 reserve = zeroForOne
            ? FullMath.mulDiv(uint256(liq), Q96, uint256(sqrtPriceX96))
            : FullMath.mulDiv(uint256(liq), uint256(sqrtPriceX96), Q96);

        if (reserve == 0) return 0;
        return FullMath.mulDiv(absAmount, FEE_DENOMINATOR, reserve);
    }
}
