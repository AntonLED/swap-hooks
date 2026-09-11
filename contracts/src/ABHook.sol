// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

import {BaseOverrideFee} from "@openzeppelin/uniswap-hooks/src/fee/BaseOverrideFee.sol";
import {Hooks} from "@uniswap/v4-core/src/libraries/Hooks.sol";
import {IPoolManager, SwapParams} from "@uniswap/v4-core/src/interfaces/IPoolManager.sol";
import {PoolKey} from "@uniswap/v4-core/src/types/PoolKey.sol";
import {PoolId, PoolIdLibrary} from "@uniswap/v4-core/src/types/PoolId.sol";
import {BalanceDelta} from "@uniswap/v4-core/src/types/BalanceDelta.sol";
import {StateLibrary} from "@uniswap/v4-core/src/libraries/StateLibrary.sol";
import {FullMath} from "@uniswap/v4-core/src/libraries/FullMath.sol";
import {SafeCast} from "@uniswap/v4-core/src/libraries/SafeCast.sol";
import {Ownable} from "@openzeppelin/contracts/access/Ownable.sol";

import {AggregatorV2V3Interface} from "@chainlink/local/src/data-feeds/interfaces/AggregatorV2V3Interface.sol";

/**
 * @title AMM-Based (AB) Hook
 * @notice A hook implementing AMM-Based dynamic fees.
 * - Adjusts fees based on AMM price changes after swaps in the A→B direction.
 * - Maintains a constant sum AMM for fees: f(A -> B) + f(B -> A) = K.
 */
contract ABHook is BaseOverrideFee, Ownable {
    using PoolIdLibrary for PoolKey;
    using StateLibrary for IPoolManager;

    // Constants
    uint24 private INITIAL_FEE = 3000; // 30 bps
    uint24 private K = 6000; // Constant sum for fees (60 bps)
    uint256 private A = 100; // Constant for sigma
    uint256 private constant DELTA_SCALE = 1e6;

    /// @dev Shared fee box. Public because the bound tests and the run manifest
    ///      both read it from outside.
    uint24 public constant F_MIN = 100; // 1 bps

    /// @notice The highest fee either direction can reach, in pips.
    /// @dev NOT the 100 bps ceiling the other hooks use -- the constant sum
    ///      binds first. With K = 6000 and F_MIN = 100 one side can reach 5900
    ///      only by pushing the other to the floor, so the reachable box is
    ///      [1, 59] bps. A dead `MAX_FEE = 10000` used to sit here suggesting
    ///      otherwise, and the figures drew that wider box.
    uint24 public constant F_MAX = 5900; // 59 bps

    /// @dev Clamp feeAB so that BOTH sides respect the floor under the constant
    ///      sum: with K = 6000 and F_MIN = 100 the reachable range is
    ///      [100, 5900]. The previous code clamped at [0, K], which let one
    ///      direction trade free of charge.
    function _clampAB(int256 fee) private view returns (uint24) {
        int256 lo = int256(uint256(F_MIN));
        int256 hi = int256(uint256(K)) - lo;
        if (fee < lo) return F_MIN;
        if (fee > hi) return uint24(uint256(hi));
        return uint24(uint256(fee));
    }

    // State per pool
    mapping(PoolId => uint24) public feeAB; // Fee for A -> B
    mapping(PoolId => uint24) public feeBA; // Fee for B-> A
    mapping(PoolId => uint160) public lastSqrtPriceX96; // Last AMM price (sqrtPriceX96)

    IPoolManager private immutable _poolManager;

    // Constructor accepts feeds for compatibility but does not use them (AMM-based)
    constructor(IPoolManager poolManager, AggregatorV2V3Interface, AggregatorV2V3Interface)
        BaseOverrideFee()
        Ownable(msg.sender)
    {
        _poolManager = poolManager;
    }

    function poolManager() public view override returns (IPoolManager) {
        return _poolManager;
    }

    /**
     * @dev Initialize fees and last price for the pool.
     */
    function _afterInitialize(address, PoolKey calldata key, uint160 sqrtPriceX96, int24)
        internal
        override
        returns (bytes4)
    {
        PoolId poolId = key.toId();
        feeAB[poolId] = INITIAL_FEE;
        feeBA[poolId] = INITIAL_FEE;
        lastSqrtPriceX96[poolId] = sqrtPriceX96;
        return this.afterInitialize.selector;
    }

    /**
     * @dev Get the fee for the swap based on direction.
     */
    function _getFee(address, PoolKey calldata key, SwapParams calldata params, bytes calldata)
        internal
        view
        override
        returns (uint24)
    {
        PoolId poolId = key.toId();
        return params.zeroForOne ? feeAB[poolId] : feeBA[poolId];
    }

    function getFee(address caller, PoolKey calldata key, SwapParams calldata params, bytes calldata data)
        external
        returns (uint24)
    {
        return _getFee(caller, key, params, data);
    }

    /**
     * @notice Sets the initial fee, denominated in hundredths of a bip.
     */
    function setFee(uint24 _fee, PoolKey calldata key) external onlyOwner {
        PoolId poolId = key.toId();
        require(_fee <= K, "Fee exceeds constant sum K");
        feeAB[poolId] = _fee;
        feeBA[poolId] = K - _fee;
    }

    /**
     * @dev After swap: Adjust fees based on AMM price change if last swap was A -> B
     */
    function _afterSwap(address, PoolKey calldata key, SwapParams calldata params, BalanceDelta, bytes calldata)
        internal
        override
        returns (bytes4, int128)
    {
        PoolId poolId = key.toId();

        // Get current AMM price
        (uint160 currentSqrtPriceX96,,,) = _poolManager.getSlot0(poolId);

        // Relative change of the square-root price, scaled to DELTA_SCALE.
        //
        // This was 10000 (basis points), which made `A * delta / 10000`
        // truncate to zero for any move below 1% of the square-root price. On
        // one-minute data that is essentially always, so the hook never moved.
        // At 1e6 a 10 bps move yields delta = 1000 and an adjustment of 10 pips.
        uint160 lastPrice = lastSqrtPriceX96[poolId];
        if (lastPrice == 0) {
            // Fallback if lastPrice is not set
            lastSqrtPriceX96[poolId] = currentSqrtPriceX96;
            return (this.afterSwap.selector, 0);
        }
        int256 deltaSqrt = int256(uint256(currentSqrtPriceX96)) - int256(uint256(lastPrice));
        int256 delta =
            int256(FullMath.mulDiv(uint256(deltaSqrt < 0 ? -deltaSqrt : deltaSqrt), DELTA_SCALE, uint256(lastPrice)));
        if (deltaSqrt < 0) delta = -delta;

        // Applied unconditionally: the sign of `delta` already encodes the
        // direction, because A->B lowers the price and B->A raises it. The
        // previous `if (isAToB)` guard was redundant AND harmful -- it meant
        // state never advanced after a B->A swap, so the hook only ever saw
        // half the flow.
        int256 feeAdjustment = -int256(A) * delta / int256(DELTA_SCALE / 100);
        feeAB[poolId] = _clampAB(int256(uint256(feeAB[poolId])) + feeAdjustment);
        feeBA[poolId] = K - feeAB[poolId]; // Constant sum

        // Update last price
        lastSqrtPriceX96[poolId] = currentSqrtPriceX96;

        return (this.afterSwap.selector, 0);
    }

    /**
     * @dev Set hook permissions.
     */
    function getHookPermissions() public pure override returns (Hooks.Permissions memory) {
        return Hooks.Permissions({
            beforeInitialize: false,
            afterInitialize: true,
            beforeAddLiquidity: false,
            afterAddLiquidity: false,
            beforeRemoveLiquidity: false,
            afterRemoveLiquidity: false,
            beforeSwap: true,
            afterSwap: true,
            beforeDonate: false,
            afterDonate: false,
            beforeSwapReturnDelta: false,
            afterSwapReturnDelta: false,
            afterAddLiquidityReturnDelta: false,
            afterRemoveLiquidityReturnDelta: false
        });
    }
}
