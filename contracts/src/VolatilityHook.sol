// SPDX-License-Identifier: MIT
pragma solidity ^0.8.30;

import {BaseOverrideFee} from "@openzeppelin/uniswap-hooks/src/fee/BaseOverrideFee.sol";
import {Hooks} from "@uniswap/v4-core/src/libraries/Hooks.sol";
import {IPoolManager, SwapParams} from "@uniswap/v4-core/src/interfaces/IPoolManager.sol";
import {PoolKey} from "@uniswap/v4-core/src/types/PoolKey.sol";
import {PoolId, PoolIdLibrary} from "@uniswap/v4-core/src/types/PoolId.sol";
import {BalanceDelta} from "@uniswap/v4-core/src/types/BalanceDelta.sol";

import {AggregatorV2V3Interface} from "@chainlink/local/src/data-feeds/interfaces/AggregatorV2V3Interface.sol";
import {Ownable} from "@openzeppelin/contracts/access/Ownable.sol";
import {Math} from "@openzeppelin/contracts/utils/math/Math.sol";

/**
 * @title VolatilityHook
 * @notice Scales the swap fee with the measured volatility of the external
 *         price ratio: `f = fBase + coefficient * sigma`, clamped to the fee
 *         box, where `sigma` is an exponentially weighted PER-MINUTE standard
 *         deviation of the ratio's relative change.
 *
 * This is the policy the paper claims (contributions list and §III-C); it was
 * built to make the text true, and then twice corrected for units:
 *
 *  - 2026-08-12 (coefficient): the shipped `coefficient = 20_000` was written
 *    against a daily-scale sigma while the estimator measures a minute-scale
 *    one, so the fee moved by ~0.35 bps over a whole window. Recalibrated from
 *    the measured 2024 minute-sigma quantiles: calm (~4e-4) -> ~28 bps, storm
 *    (~2e-3) -> ~60 bps.
 *  - 2026-08-12 (time base): the estimator updates only when a swap lands --
 *    every 3-4 minutes at typical participation -- and a 4-minute move squared
 *    is ~4x a 1-minute one. The squared change is now divided by the elapsed
 *    minutes (Brownian scaling), so the estimator's unit matches the
 *    calibration's.
 *
 * Gas discipline (2026-08-12): the first economic run of the recalibrated
 * policy lost to the static baseline in CALM regimes purely through its own
 * gas -- 127,508 per swap against the static hook's 76,268 -- because retail
 * pays the hook's gas inside `r` and walks. This revision removes every
 * storage write the fee does not need: the cumulative Welford diagnostic is
 * gone from the hot path, the fee and sigma are derived on read instead of
 * stored, and the per-pool bookkeeping (last block, last timestamp, sample
 * count) is packed into one slot. Three warm stores per update remain: the
 * EMA variance, the last ratio, and the packed metadata.
 *
 * Design notes:
 *  - The fee depends on accumulated state only, never on `amountSpecified`.
 *    That is load-bearing: spec §A.8 permits the closed-form arbitrage trade
 *    size only for policies with this property.
 *  - Both directions carry the same fee: this policy is about the level of
 *    the fee, not its allocation.
 *  - Updates at most once per block, so the policy reacts to the reference
 *    observation rather than to how many trades happened to land.
 */
contract VolatilityHook is BaseOverrideFee, Ownable {
    using PoolIdLibrary for PoolKey;

    uint256 private constant WAD = 1e18;

    /// @notice Fee floor and ceiling: the shared fee box from spec §4.5.
    uint24 public constant F_MIN = 100; // 1 bps
    uint24 public constant MAX_FEE = 10000; // 100 bps

    /// @notice Fee charged when the market is perfectly calm.
    uint24 public fBase = 2000; // 20 bps

    /// @notice Pips of fee added per unit of per-minute standard deviation.
    /// @dev Calibrated 2026-08-12 against the 2024 minute-sigma quantiles of
    ///      the volatile pairs (see the contract banner). f = 2000 + 2e6*sigma:
    ///      calm ~28 bps, storm ~60 bps, p99 minutes reach the ceiling, the
    ///      stable pair sits flat near 21 bps.
    uint256 public coefficient = 2_000_000;

    /// @notice Weight on the newest observation, 1e18-scaled.
    /// @dev The whole memory of the estimator: the horizon is about 1/alpha
    ///      observations, so 0.1e18 remembers roughly the last ten.
    uint256 public alpha = 0.1e18;

    AggregatorV2V3Interface private immutable _token0UsdtFeed;
    AggregatorV2V3Interface private immutable _token1UsdtFeed;
    IPoolManager private immutable _poolManager;

    /// @dev One slot: everything the update path needs besides the estimator
    ///      state itself. `n` is the observation counter the old cumulative
    ///      Welford diagnostic provided; the diagnostic's variance is gone
    ///      from the hot path (it cost three storage slots per update and the
    ///      fee never read it).
    struct Meta {
        uint64 lastBlock;
        uint64 lastUpdateTs;
        uint32 n;
    }

    mapping(PoolId => Meta) private _meta;
    mapping(PoolId => uint256) public lastPriceRatio;

    /// @notice Exponentially weighted PER-MINUTE variance of the ratio's
    ///         relative change, 1e18-scaled. The single number the fee reads;
    ///         sigma and the fee itself are derived views, not state.
    mapping(PoolId => uint256) public emaVariance;

    constructor(IPoolManager poolManager_, AggregatorV2V3Interface token0Feed, AggregatorV2V3Interface token1Feed)
        BaseOverrideFee()
        Ownable(msg.sender)
    {
        _poolManager = poolManager_;
        _token0UsdtFeed = token0Feed;
        _token1UsdtFeed = token1Feed;
    }

    function poolManager() public view override returns (IPoolManager) {
        return _poolManager;
    }

    /// @dev token0 per token1, matching BAHook:69 and the Uniswap convention
    ///      that the pool price is token1 per token0.
    function _getPriceRatio() private view returns (uint256) {
        (, int256 token0Price,,,) = _token0UsdtFeed.latestRoundData();
        (, int256 token1Price,,,) = _token1UsdtFeed.latestRoundData();
        require(token0Price > 0 && token1Price > 0, "Invalid price data");
        return uint256(token0Price) * WAD / uint256(token1Price);
    }

    function _afterInitialize(address, PoolKey calldata key, uint160, int24) internal override returns (bytes4) {
        PoolId poolId = key.toId();
        lastPriceRatio[poolId] = _getPriceRatio();
        _meta[poolId] = Meta({lastBlock: uint64(block.number), lastUpdateTs: uint64(block.timestamp), n: 0});
        return this.afterInitialize.selector;
    }

    /// @notice Current per-minute standard deviation estimate, 1e18-scaled.
    /// @dev Derived from the stored variance on read; nothing extra is stored.
    function sigma(PoolId poolId) public view returns (uint256) {
        return Math.sqrt(emaVariance[poolId] * WAD);
    }

    /// @notice The fee the policy currently charges, pips. Derived on read:
    ///         a square root costs a few hundred gas where a storage write
    ///         costs thousands, and the write was pure overhead retail paid.
    function fee(PoolId poolId) public view returns (uint24) {
        uint256 raw = uint256(fBase) + coefficient * sigma(poolId) / WAD;
        return raw < F_MIN ? F_MIN : (raw > MAX_FEE ? MAX_FEE : uint24(raw));
    }

    function sampleCount(PoolId poolId) external view returns (uint256) {
        return _meta[poolId].n;
    }

    function _getFee(address, PoolKey calldata key, SwapParams calldata, bytes calldata)
        internal
        view
        override
        returns (uint24)
    {
        return fee(key.toId());
    }

    function getFee(address caller, PoolKey calldata key, SwapParams calldata params, bytes calldata data)
        external
        view
        returns (uint24)
    {
        return _getFee(caller, key, params, data);
    }

    /// @notice Sets the calm-market base fee, in hundredths of a bip.
    function setFee(uint24 _fee, PoolKey calldata) external onlyOwner {
        require(_fee >= F_MIN && _fee <= MAX_FEE, "outside the fee box");
        fBase = _fee;
    }

    function setCoefficient(uint256 c) external onlyOwner {
        coefficient = c;
    }

    function setAlpha(uint256 a) external onlyOwner {
        require(a <= WAD, "alpha is a weight");
        alpha = a;
    }

    function _afterSwap(address, PoolKey calldata key, SwapParams calldata, BalanceDelta, bytes calldata)
        internal
        override
        returns (bytes4, int128)
    {
        PoolId poolId = key.toId();
        Meta memory meta = _meta[poolId];
        if (block.number <= meta.lastBlock) return (this.afterSwap.selector, 0);

        uint256 ratio = _getPriceRatio();
        uint256 previous = lastPriceRatio[poolId];

        if (previous != 0) {
            // Relative change stands in for the log return. They agree to
            // second order, and over a few minutes the move is small enough
            // that the difference is far below the fee's resolution.
            int256 change = (int256(ratio) - int256(previous)) * int256(WAD) / int256(previous);

            uint256 squared = uint256(change < 0 ? -change : change);
            squared = squared * squared / WAD; // 1e18-scaled square

            // Brownian scaling to PER-MINUTE variance: a move accumulated
            // over `dt` minutes has dt times the one-minute variance. Clamped
            // to one minute: within-candle repeats share a timestamp, and a
            // zero dt is a same-observation artifact, not an infinitely
            // volatile market.
            uint256 elapsed = block.timestamp - meta.lastUpdateTs;
            uint256 dtMinutes = elapsed < 60 ? 1 : elapsed / 60;
            squared = squared / dtMinutes;

            uint256 previousVar = emaVariance[poolId];
            // Seed on the first sample rather than dragging up from zero.
            emaVariance[poolId] = previousVar == 0 ? squared : (alpha * squared + (WAD - alpha) * previousVar) / WAD;
        }

        lastPriceRatio[poolId] = ratio;
        _meta[poolId] = Meta({lastBlock: uint64(block.number), lastUpdateTs: uint64(block.timestamp), n: meta.n + 1});

        return (this.afterSwap.selector, 0);
    }

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
