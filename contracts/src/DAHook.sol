// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

import {BaseOverrideFee} from "@openzeppelin/uniswap-hooks/src/fee/BaseOverrideFee.sol";
import {Hooks} from "@uniswap/v4-core/src/libraries/Hooks.sol";
import {IPoolManager, SwapParams} from "@uniswap/v4-core/src/interfaces/IPoolManager.sol";
import {PoolKey} from "@uniswap/v4-core/src/types/PoolKey.sol";
import {PoolId, PoolIdLibrary} from "@uniswap/v4-core/src/types/PoolId.sol";
import {BalanceDelta} from "@uniswap/v4-core/src/types/BalanceDelta.sol";
import {Ownable} from "@openzeppelin/contracts/access/Ownable.sol";

import {AggregatorV2V3Interface} from "@chainlink/local/src/data-feeds/interfaces/AggregatorV2V3Interface.sol";

/**
 * @title Deal-Adaptive Hook
 * @notice A hook implementing Deal-Adaptive (DA) dynamic fees.
 * - Adjusts fees based on the direction of the last swap.
 */
contract DAHook is BaseOverrideFee, Ownable {
    using PoolIdLibrary for PoolKey;

    // Constants
    uint24 private INITIAL_FEE = 3000; // 30 bps, 0.3%
    uint24 private FSTEP = 100; // 5 bps, 0.01% - very little
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

    // State per pool
    mapping(PoolId => uint24) public feeAB; // Fee for A → B
    mapping(PoolId => uint24) public feeBA; // Fee for B → A

    IPoolManager private immutable _poolManager;

    // This contract doesn't use price feeds
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
     * @dev Initialize fees for the pool.
     */
    function _afterInitialize(address, PoolKey calldata key, uint160, int24) internal override returns (bytes4) {
        PoolId poolId = key.toId();
        feeAB[poolId] = INITIAL_FEE;
        feeBA[poolId] = INITIAL_FEE;
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
     * @dev After swap: Adjust fees based on the direction of the swap.
     */
    function _afterSwap(address, PoolKey calldata key, SwapParams calldata params, BalanceDelta, bytes calldata)
        internal
        override
        returns (bytes4, int128)
    {
        PoolId poolId = key.toId();
        bool isAToB = params.zeroForOne;

        if (isAToB) {
            // Last swap was A → B: Increase feeAB, decrease feeBA
            feeAB[poolId] = _clamp(uint256(feeAB[poolId]) + FSTEP);
            feeBA[poolId] = _clamp(_stepDown(feeBA[poolId], FSTEP));
        } else {
            // Last swap was B → A: Increase feeBA, decrease feeAB
            feeBA[poolId] = _clamp(uint256(feeBA[poolId]) + FSTEP);
            feeAB[poolId] = _clamp(_stepDown(feeAB[poolId], FSTEP));
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
