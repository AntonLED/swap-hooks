// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

import {BaseHook} from "@openzeppelin/uniswap-hooks/src/base/BaseHook.sol";

import {Hooks} from "@uniswap/v4-core/src/libraries/Hooks.sol";
import {IPoolManager, SwapParams, ModifyLiquidityParams} from "@uniswap/v4-core/src/interfaces/IPoolManager.sol";
import {PoolKey} from "@uniswap/v4-core/src/types/PoolKey.sol";
import {PoolId, PoolIdLibrary} from "@uniswap/v4-core/src/types/PoolId.sol";
import {BalanceDelta} from "@uniswap/v4-core/src/types/BalanceDelta.sol";
import {BeforeSwapDelta, BeforeSwapDeltaLibrary} from "@uniswap/v4-core/src/types/BeforeSwapDelta.sol";

import {BaseOverrideFee} from "@openzeppelin/uniswap-hooks/src/fee/BaseOverrideFee.sol";
import {Ownable} from "@openzeppelin/contracts/access/Ownable.sol";

import {LPFeeLibrary} from "@uniswap/v4-core/src/libraries/LPFeeLibrary.sol";

/**
 * @dev A hook that allows the owner to dynamically update the swap fee.
 */
contract MyHook is BaseOverrideFee, Ownable {
    using PoolIdLibrary for PoolKey;
    using LPFeeLibrary for uint24;

    // NOTE: ---------------------------------------------------------
    // state variables should typically be unique to a pool
    // a single hook contract should be able to service multiple pools
    // ---------------------------------------------------------------

    mapping(PoolId => uint256 count) public beforeSwapCount;
    mapping(PoolId => uint256 count) public afterSwapCount;

    mapping(PoolId => uint256 count) public beforeAddLiquidityCount;
    mapping(PoolId => uint256 count) public beforeRemoveLiquidityCount;

    uint24 public fee;

    IPoolManager private _poolManager;

    function poolManager() public view override returns (IPoolManager) {
        return IPoolManager(_poolManager);
    }

    constructor(IPoolManager poolManager) BaseOverrideFee() Ownable(msg.sender) {
        _poolManager = poolManager;
    }

    /**
     * @inheritdoc BaseOverrideFee
     */
    function _getFee(address, PoolKey calldata, SwapParams calldata, bytes calldata)
        internal
        view
        override
        returns (uint24)
    {
        return fee;
    }

    /**
     * @dev Check that the pool key has a dynamic fee.
     */
    function _afterInitialize(address, PoolKey calldata key, uint160, int24) internal override returns (bytes4) {
        if (!key.fee.isDynamicFee()) revert NotDynamicFee();
        poolManager().updateDynamicLPFee(key, fee);
        return this.afterInitialize.selector;
    }

    /**
     * @notice Exposes the fee for off-chain trade sizing.
     * @dev Required by IHooksExtended, which the replay harness casts to. The
     *      arbitrageur must read the fee before computing its optimal size.
     */
    function getFee(address caller, PoolKey calldata key, SwapParams calldata params, bytes calldata data)
        external
        view
        returns (uint24)
    {
        return _getFee(caller, key, params, data);
    }

    /**
     * @notice Sets the swap fee, denominated in hundredths of a bip.
     * @dev The PoolKey is accepted for IHooksExtended compatibility and ignored:
     *      this hook holds a single fee rather than a per-pool mapping, and each
     *      experiment run deploys exactly one pool. Pushing the value to the
     *      pool keeps the stored LP fee in step with what _getFee returns.
     */
    function setFee(uint24 _fee, PoolKey calldata key) external onlyOwner {
        fee = _fee;
        poolManager().updateDynamicLPFee(key, _fee);
    }

    function poke(address, PoolKey calldata key, SwapParams calldata params, bytes calldata data) internal {
        poolManager().updateDynamicLPFee(key, _getFee(address(0), key, params, data));
    }
}
