// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

import {console} from "forge-std/console.sol";

import {BaseOverrideFee} from "@openzeppelin/uniswap-hooks/src/fee/BaseOverrideFee.sol";
import {Hooks} from "@uniswap/v4-core/src/libraries/Hooks.sol";
import {IPoolManager, SwapParams, ModifyLiquidityParams} from "@uniswap/v4-core/src/interfaces/IPoolManager.sol";
import {PoolKey} from "@uniswap/v4-core/src/types/PoolKey.sol";
import {PoolId, PoolIdLibrary} from "@uniswap/v4-core/src/types/PoolId.sol";
import {BalanceDelta} from "@uniswap/v4-core/src/types/BalanceDelta.sol";
import {BeforeSwapDelta, BeforeSwapDeltaLibrary} from "@uniswap/v4-core/src/types/BeforeSwapDelta.sol";
import {StateLibrary} from "@uniswap/v4-core/src/libraries/StateLibrary.sol";
import {LPFeeLibrary} from "@uniswap/v4-core/src/libraries/LPFeeLibrary.sol";

import {AggregatorV2V3Interface} from "@chainlink/local/src/data-feeds/interfaces/AggregatorV2V3Interface.sol";

import {Ownable} from "@openzeppelin/contracts/access/Ownable.sol";

import {Strings} from "@openzeppelin/contracts/utils/Strings.sol";

/**
 * @title Block-Adaptive Hook
 * @notice A hook implementing Block Adaptive (BA) dynamic fees using external CEX prices.
 * - Uses token0/USDT and token1/USDT price feeds to compute token0/token1 ratio.
 * - Adjusts fees based on ratio changes per block.
 */
contract BAHook is BaseOverrideFee, Ownable {
    using PoolIdLibrary for PoolKey;
    using StateLibrary for IPoolManager;
    using LPFeeLibrary for uint24;

    // Constants
    uint24 private INITIAL_FEE = 3000; // 30 bps
    uint24 private FSTEP = 500; // 5 bps
    uint24 private MAX_FEE = 10000; // Cap at 100 bps

    /// @dev Shared fee box. Public because the bound tests and the run manifest
    ///      both read it from outside; a private field would compile but be
    ///      unreachable.
    uint24 public constant F_MIN = 100; // 1 bps

    /// @dev Subtract one step without underflowing; the clamp applies the floor.
    function _stepDown(uint24 fee, uint24 step) private pure returns (uint256) {
        return fee > step ? uint256(fee) - step : 0;
    }

    /// @dev Enforce [F_MIN, MAX_FEE]. Before this the falling side clamped at
    ///      zero, which violates f_min <= f <= f_max from Eq. (8).
    function _clamp(uint256 fee) private view returns (uint24) {
        if (fee < F_MIN) return F_MIN;
        if (fee > MAX_FEE) return MAX_FEE;
        return uint24(fee);
    }

    // Price feeds
    AggregatorV2V3Interface private immutable _token0UsdtFeed;
    AggregatorV2V3Interface private immutable _token1UsdtFeed;

    // State per pool
    mapping(PoolId => uint24) public feeAB; // Fee for A → B (ETH → SHIB)
    mapping(PoolId => uint24) public feeBA; // Fee for B → A (SHIB → ETH)
    mapping(PoolId => uint256) public lastPriceRatio; // Last ETH/SHIB ratio (scaled by 1e18 for precision)
    mapping(PoolId => uint256) public lastBlock;

    IPoolManager private immutable _poolManager;

    constructor(IPoolManager poolManager, AggregatorV2V3Interface ethUsdtFeed, AggregatorV2V3Interface shibUsdtFeed)
        BaseOverrideFee()
        Ownable(msg.sender)
    {
        _poolManager = poolManager;
        _token0UsdtFeed = ethUsdtFeed;
        _token1UsdtFeed = shibUsdtFeed;
    }

    function poolManager() public view override returns (IPoolManager) {
        return _poolManager;
    }

    // Helper to get current token0/token1 price ratio from feeds
    function _getPriceRatio() private view returns (uint256) {
        (, int256 token0Price,,,) = _token0UsdtFeed.latestRoundData();
        (, int256 token1Price,,,) = _token1UsdtFeed.latestRoundData();
        require(token0Price > 0 && token1Price > 0, "Invalid price data");
        // Ratio = (token0/USD) / (token1/USD), scaled by 1e18 for precision
        return uint256(token0Price) * 1e18 / uint256(token1Price);
    }

    /**
     * @dev Initialize fees and price tracking for the pool.
     */
    function _afterInitialize(address, PoolKey calldata key, uint160, int24) internal override returns (bytes4) {
        PoolId poolId = key.toId();
        feeAB[poolId] = INITIAL_FEE;
        feeBA[poolId] = INITIAL_FEE;
        lastPriceRatio[poolId] = _getPriceRatio();
        lastBlock[poolId] = block.number;
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

        feeAB[poolId] = _fee;
        feeBA[poolId] = _fee;
    }

    /**
     * @dev After swap: Check for block end and adjust fees based on external price ratio.
     */
    function _afterSwap(address, PoolKey calldata key, SwapParams calldata, BalanceDelta, bytes calldata)
        internal
        override
        returns (bytes4, int128)
    {
        PoolId poolId = key.toId();
        uint256 currentRatio = _getPriceRatio();

        /*
        console.log(string(
            abi.encodePacked(
                "BAHook. CurrentRation =  ", Strings.toString(currentRatio), " LastPriceRatio =  ", Strings.toString(lastPriceRatio[poolId])
            )
        ));
        */

        // Both feeds were read a second time here into variables used only by
        // commented-out logging. Two dead external calls on every swap, and
        // `gasEstimate` is the arbitrageur's entry threshold -- so the policy
        // was being charged for them in the experiment, not just in gas.
        if (block.number > lastBlock[poolId]) {
            if (currentRatio < lastPriceRatio[poolId]) {
                // Ratio decreased (ETH/SHIB fell): Increase feeAB, decrease feeBA
                feeAB[poolId] = _clamp(uint256(feeAB[poolId]) + FSTEP);
                feeBA[poolId] = _clamp(_stepDown(feeBA[poolId], FSTEP));
            } else if (currentRatio > lastPriceRatio[poolId]) {
                // Ratio increased: Decrease feeAB, increase feeBA
                feeAB[poolId] = _clamp(_stepDown(feeAB[poolId], FSTEP));
                feeBA[poolId] = _clamp(uint256(feeBA[poolId]) + FSTEP);
            }
            lastPriceRatio[poolId] = currentRatio;
            lastBlock[poolId] = block.number;
        }

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
