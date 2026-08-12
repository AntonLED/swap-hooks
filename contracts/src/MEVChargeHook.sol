// SPDX-License-Identifier: MIT
pragma solidity ^0.8.30;

/**
 * @title MEVChargeHook
 * @notice Uniswap v4 hook that applies static and dynamic fees with a cooldown and
 *         an LP removal penalty. The dynamic swap fee is returned to the pool as the
 *         official Uniswap fee. There is no separate surcharge settlement/donation,
 *         avoiding double charging.
 *
 * Permissions implemented:
 *   afterInitialize, afterAddLiquidity, afterRemoveLiquidity, beforeSwap
 *   and afterRemoveLiquidityReturnDelta.
 */

// ----------------------------- Imports -----------------------------
import {BaseOverrideFee} from "@openzeppelin/uniswap-hooks/src/fee/BaseOverrideFee.sol";

import {PoolId} from "@uniswap/v4-core/src/types/PoolId.sol";
import {PoolKey} from "@uniswap/v4-core/src/types/PoolKey.sol";
import {Hooks} from "@uniswap/v4-core/src/libraries/Hooks.sol";
import {IHooks} from "@uniswap/v4-core/src/interfaces/IHooks.sol";
import {FullMath} from "@uniswap/v4-core/src/libraries/FullMath.sol";
import {Position} from "@uniswap/v4-core/src/libraries/Position.sol";
import {SafeCast} from "@uniswap/v4-core/src/libraries/SafeCast.sol";
import {StateLibrary} from "@uniswap/v4-core/src/libraries/StateLibrary.sol";
import {IPoolManager} from "@uniswap/v4-core/src/interfaces/IPoolManager.sol";
import {ModifyLiquidityParams, SwapParams} from "@uniswap/v4-core/src/types/PoolOperation.sol";
import {BalanceDelta, BalanceDeltaLibrary, toBalanceDelta} from "@uniswap/v4-core/src/types/BalanceDelta.sol";

import {AggregatorV2V3Interface} from "@chainlink/local/src/data-feeds/interfaces/AggregatorV2V3Interface.sol";

import {Math} from "@openzeppelin/contracts/utils/math/Math.sol";
import {Ownable} from "@openzeppelin/contracts/access/Ownable.sol";
import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {SafeERC20} from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";

/// @title MEVChargeHook
/// @notice Uniswap v4 hook that enforces
/// dynamic MEV-aware fees with cooldowns and LP donations.
contract MEVChargeHook is BaseOverrideFee, Ownable {
    using StateLibrary for IPoolManager;
    using SafeERC20 for IERC20;

    uint256 private constant MALICIOUS_FEE_MAX_DEFAULT = 2500; // 25%
    uint256 private constant FIXED_LP_FEE_DEFAULT = 30; // 0.3%
    uint256 private constant MAX_COOLDOWN_SECONDS = 600;
    /// @dev `internal` so `MEVChargeHookFixed` can reuse it; the value and
    ///      every use of it are unchanged.
    uint256 internal constant FEE_DENOMINATOR = 10000;
    uint8 private constant MAX_BLOCK_OFFSET = 3;
    uint8 private constant MAX_LINK_DEPTH = 3;
    uint8 private constant FLAG_IS_FEE_ADDRESS = 1 << 0;

    struct Config {
        uint16 feeMax; // upper bound for base+time+impact
        uint16 flaggedFeeAdditional; // extra bps for flagged addresses
        uint16 cooldownSeconds; // decay horizon in seconds
        uint8 blockNumberOffset; // blocks to avoid LP churn
    }

    Config public config = Config({feeMax: 1000, flaggedFeeAdditional: 400, cooldownSeconds: 15, blockNumberOffset: 2});

    uint256 public maliciousFeeMax = MALICIOUS_FEE_MAX_DEFAULT;
    uint256 public fixedLpFee = FIXED_LP_FEE_DEFAULT;
    uint16 public effectiveFeeMax; // cached min(feeMax, maliciousFeeMax)

    // ----------------------------- Errors ------------------------------------------
    error NotMarked();
    error ZeroAddress();
    error NoLiquidity();
    error FeeAboveMax();
    error FeeRangeZero();
    error AlreadyMarked();
    error AlreadyLinked();
    error SelfLink();
    error FeeMaxTooHigh();
    error ETHNotAccepted();
    error CooldownTooHigh();
    error FeeBelowStaticFee();
    error BlockOffsetTooHigh();
    error NoPrimaryRegistered();
    error LinkDepthExceeded();
    error BlockNumberOffsetTooLow();
    error InvalidPoolManagerAddress();
    error CycleDetected();
    error DonationFailed();
    error PoolAlreadyRegistered();
    error Reentrant();
    error FeeMaxBelowStaticFee();
    error NativeWithdrawFailed();
    error InvalidSignedPayer();
    error RouterNotTrusted();

    // ----------------------------- Events ------------------------------------------
    event FeeAddressAdded(address indexed account);
    event FeeAddressRemoved(address indexed account);
    event LinkedAddressUnregistered(address indexed secondary);
    event CooldownSecondsUpdated(address indexed owner, uint256 indexed newCooldownSeconds);
    event LinkedAddressRegistered(address indexed secondary, address indexed primary);
    event BlockNumberOffsetUpdated(address indexed owner, uint256 indexed newBlockNumberOffset);
    event FeeMaxUpdated(uint16 indexed newFeeMax);
    event FlaggedFeeAdditionalUpdated(uint16 indexed oldFee, uint16 indexed newFee);
    event MaliciousFeeMaxUpdated(uint256 indexed newMax);
    event FixedLpFeeUpdated(uint256 indexed newFee);

    event LiquidityAdded(address indexed user, PoolId indexed poolId, bytes32 positionKey);
    event LiquidityRemoved(address indexed user, PoolId indexed poolId, bytes32 positionKey);

    event PoolRegistered(PoolId indexed poolId);
    event EmergencyWithdraw(address indexed token, address indexed to, uint256 indexed amount);
    event TrustedRouterUpdated(
        address indexed router, address indexed signer, bool indexed trusted, string metadataURI
    );

    struct UserInfo {
        uint8 flags; // bit flags, e.g., FLAG_IS_FEE_ADDRESS
        address primary; // optional linked primary
    }

    // ----------------------------- Storage -----------------------------------------
    mapping(address account => UserInfo info) public userInfo;

    // Per-identity last buys by token side
    mapping(address account => uint256 lastBuyTimestamp) private _lastBuyToken0;
    mapping(address account => uint256 lastBuyTimestamp) private _lastBuyToken1;
    mapping(address account => uint48 lastActivity) private _lastActivity;

    // LP churn tracking
    mapping(PoolId poolId => mapping(bytes32 bucket => uint256 lastTimestamp)) public lastAddedLiquidity;

    function getHookPermissions() public pure override returns (Hooks.Permissions memory) {
        return Hooks.Permissions({
            beforeInitialize: false,
            afterInitialize: true,
            beforeAddLiquidity: false,
            afterAddLiquidity: true,
            beforeRemoveLiquidity: false,
            afterRemoveLiquidity: true,
            beforeSwap: true,
            afterSwap: false,
            beforeDonate: false,
            afterDonate: false,
            beforeSwapReturnDelta: false,
            afterSwapReturnDelta: false,
            afterAddLiquidityReturnDelta: false,
            afterRemoveLiquidityReturnDelta: true
        });
    }

    IPoolManager private immutable _poolManager;

    constructor(IPoolManager poolManager, AggregatorV2V3Interface a, AggregatorV2V3Interface b)
        BaseOverrideFee()
        Ownable(msg.sender)
    {
        _poolManager = poolManager;
        if (address(_poolManager) == address(0)) revert InvalidPoolManagerAddress();
        _updateEffectiveFeeMax();
    }

    function poolManager() public view override returns (IPoolManager) {
        return _poolManager;
    }

    // ----------------------------- Admin: Params -----------------------------------
    /// @notice Updates the cooldown horizon used when computing time-based surcharges.
    function setCooldownSeconds(uint256 newCooldownSeconds) external onlyOwner {
        // forge-lint: disable-next-line(unsafe-typecast)
        config.cooldownSeconds = uint16(Math.min(uint256(MAX_COOLDOWN_SECONDS), newCooldownSeconds));
    }

    /// @notice Sets the minimum block distance enforced between LP add/remove cycles.
    function setBlockNumberOffset(uint256 newOffset) external onlyOwner {
        // forge-lint: disable-next-line(unsafe-typecast)
        config.blockNumberOffset = uint8(Math.min(newOffset, uint256(config.blockNumberOffset)));
    }

    /// @notice Caps the combined static + dynamic fee in basis points.
    function setFeeMax(uint16 newFeeMax) external onlyOwner {
        if (newFeeMax > 1000) revert FeeMaxTooHigh();
        uint16 flagged = config.flaggedFeeAdditional;
        if (newFeeMax < fixedLpFee + flagged) revert FeeMaxBelowStaticFee();
        config.feeMax = newFeeMax;
        effectiveFeeMax = uint16(Math.min(uint256(config.feeMax), maliciousFeeMax));
    }

    /// @notice Updates the emergency cap for malicious pair overrides.
    function setMaliciousFeeMax(uint256 newMax) external onlyOwner {
        if (newMax < fixedLpFee + config.flaggedFeeAdditional) revert FeeMaxBelowStaticFee();
        if (newMax > MALICIOUS_FEE_MAX_DEFAULT) revert FeeMaxTooHigh();
        maliciousFeeMax = newMax;
        effectiveFeeMax = uint16(Math.min(uint256(config.feeMax), maliciousFeeMax));
    }

    /// @notice Updates the static LP fee floor (basis points).
    function setFixedLpFee(uint256 newFee) external onlyOwner {
        if (newFee + config.flaggedFeeAdditional > effectiveFeeMax) revert FeeMaxTooHigh();
        fixedLpFee = newFee;
    }

    /// @notice Adjusts the additional surcharge applied to flagged traders.
    function setFlaggedFeeAdditional(uint16 newValue) external onlyOwner {
        if (fixedLpFee + newValue > effectiveFeeMax) revert FeeMaxTooHigh();
        config.flaggedFeeAdditional = newValue;
    }

    function setFee(uint24 _fee, PoolKey calldata key) external onlyOwner {
        fixedLpFee = Math.ceilDiv(_fee, 100);
    }

    // ----------------------------- Inspectors --------------------------------------
    /// @notice Current configured maximum LP fee (basis points).
    function feeMax() public view returns (uint16) {
        return config.feeMax;
    }

    /// @notice Additional fee applied to flagged addresses (basis points).
    function flaggedFeeAdditional() public view returns (uint16) {
        return config.flaggedFeeAdditional;
    }

    /// @notice Cooldown window used when computing time-based fees.
    function cooldownSeconds() public view returns (uint16) {
        return config.cooldownSeconds;
    }

    /// @notice Block-number offset applied when enforcing LP cooldowns.
    function blockNumberOffset() public view returns (uint8) {
        return config.blockNumberOffset;
    }

    /// @notice Returns the minimum static fee and the current effective cap.
    function getFeeBounds() external view returns (uint256 lowerBound, uint256 upperBound) {
        lowerBound = fixedLpFee;
        upperBound = effectiveFeeMax;
    }

    /// @notice Validates that `hookAddress` exposes the hook permissions required by this contract.
    function validateHookAddress(address hookAddress) external pure returns (bool) {
        if (hookAddress == address(0)) revert ZeroAddress();
        validateHookAddressInternal(hookAddress);
        return true;
    }

    /// @notice Returns true if `hookAddress` passes `validateHookAddressInternal`.
    function isValidHookAddress(address hookAddress) external view returns (bool ok) {
        if (hookAddress == address(0)) return false;
        bytes memory data = abi.encodeCall(this.validateHookAddressInternal, (hookAddress));
        (bool success,) = address(this).staticcall(data);
        return success;
    }

    /// @dev Reverts if `hookAddress` does not expose the required hook permissions.
    function validateHookAddressInternal(address hookAddress) public pure {
        Hooks.validateHookPermissions(IHooks(hookAddress), getHookPermissions());
    }

    // ----------------------------- Hook Overrides ----------------------------------

    function _afterAddLiquidity(
        address sender,
        PoolKey calldata key,
        ModifyLiquidityParams calldata params,
        BalanceDelta,
        BalanceDelta,
        bytes calldata
    ) internal virtual override returns (bytes4, BalanceDelta) {
        _lastActivity[sender] = uint48(block.timestamp);
        bytes32 positionKey = Position.calculatePositionKey(sender, params.tickLower, params.tickUpper, params.salt);
        PoolId poolId = key.toId();
        lastAddedLiquidity[poolId][positionKey] = block.number;
        return (this.afterAddLiquidity.selector, BalanceDeltaLibrary.ZERO_DELTA);
    }

    function _afterRemoveLiquidityInner(
        address sender,
        PoolKey calldata key,
        ModifyLiquidityParams calldata params,
        BalanceDelta feeDelta
    ) private returns (bool donated, BalanceDelta deltaSender) {
        donated = false;
        deltaSender = BalanceDeltaLibrary.ZERO_DELTA;

        PoolId poolId = key.toId();
        bytes32 positionKey = Position.calculatePositionKey(sender, params.tickLower, params.tickUpper, params.salt);
        uint128 liquidity = _getPoolLiquidity(key);
        uint256 lastLiquidityBlock = lastAddedLiquidity[poolId][positionKey];

        if (liquidity != 0 && lastLiquidityBlock != 0) {
            uint256 blocksElapsed = block.number - lastLiquidityBlock;
            if (blocksElapsed < config.blockNumberOffset) {
                // clamp negatives to zero
                int128 eff0 = feeDelta.amount0() < 0 ? int128(0) : feeDelta.amount0();
                int128 eff1 = feeDelta.amount1() < 0 ? int128(0) : feeDelta.amount1();
                BalanceDelta adjusted = toBalanceDelta(eff0, eff1);

                BalanceDelta penalty = _calculateLiquidityPenalty(adjusted, poolId, positionKey);

                // make sure donation amounts are non-negative before casting to uint
                int256 p0 = int256(penalty.amount0());
                int256 p1 = int256(penalty.amount1());
                uint256 donation0 = p0 < 0 ? uint256(-p0) : uint256(p0);
                uint256 donation1 = p1 < 0 ? uint256(-p1) : uint256(p1);

                // donate to LPs proportional to active liquidity
                BalanceDelta deltaHook = _donate(key, donation0, donation1);
                donated = true;
                // return negated hook delta to the position owner
                deltaSender = toBalanceDelta(-deltaHook.amount0(), -deltaHook.amount1());
            }
        }
        return (donated, deltaSender);
    }

    function _donate(PoolKey calldata key, uint256 donation0, uint256 donation1)
        private
        returns (BalanceDelta deltaHook)
    {
        try _poolManager.donate(key, donation0, donation1, "") returns (BalanceDelta returnedDelta) {
            deltaHook = returnedDelta;
        } catch {
            revert DonationFailed();
        }
    }

    function _afterRemoveLiquidity(
        address sender,
        PoolKey calldata key,
        ModifyLiquidityParams calldata params,
        BalanceDelta,
        BalanceDelta feeDelta,
        bytes calldata
    ) internal virtual override returns (bytes4, BalanceDelta) {
        _updateUserActivityTimestamp(sender);
        bytes32 positionKey = Position.calculatePositionKey(sender, params.tickLower, params.tickUpper, params.salt);
        emit LiquidityRemoved(sender, key.toId(), positionKey);
        (bool donated, BalanceDelta deltaSender) = _afterRemoveLiquidityInner(sender, key, params, feeDelta);
        return (this.afterRemoveLiquidity.selector, donated ? deltaSender : BalanceDeltaLibrary.ZERO_DELTA);
    }

    /// @dev Core dynamic fee. Returns official Uniswap fee in bps.
    function _getFee(address sender, PoolKey calldata key, SwapParams calldata params, bytes calldata hookData)
        internal
        override
        returns (uint24 fee)
    {
        address payer = sender;

        // Record last "buy" per token side based on direction
        if (params.zeroForOne) _lastBuyToken1[payer] = block.timestamp;
        else _lastBuyToken0[payer] = block.timestamp;

        // Base fee and flagged bump
        uint256 base = fixedLpFee;
        if ((userInfo[payer].flags & FLAG_IS_FEE_ADDRESS) != 0) {
            base = fixedLpFee + config.flaggedFeeAdditional;
        }
        if (base > effectiveFeeMax) base = effectiveFeeMax;

        // Additional fees
        uint24 addl = _computeDynamicFee(key, params, base, payer);

        // Enforce final cap (values are in basis points)
        uint256 candidateBps = base + addl;
        if (candidateBps > effectiveFeeMax) candidateBps = effectiveFeeMax;

        // Uniswap v4 expects fees in hundredths of a bip (1e-6 scale)
        // forge-lint: disable-next-line(unsafe-typecast)
        fee = uint24(candidateBps * 100);
        return fee;
    }

    function getFee(address caller, PoolKey calldata key, SwapParams calldata params, bytes calldata data)
        external
        returns (uint24)
    {
        return _getFee(caller, key, params, data);
    }

    // ----------------------------- Fee Math ----------------------------------------
    // slither-disable-start timestamp
    function _computeDynamicFee(PoolKey calldata key, SwapParams calldata params, uint256 staticFee, address payer)
        private
        view
        returns (uint24 additionalFee)
    {
        uint16 cool = config.cooldownSeconds;
        if (cool == 0) return 0;

        bool isSellToken0 = params.zeroForOne; // selling token0 means zeroForOne
        uint128 liq = _poolManager.getLiquidity(key.toId());

        // solhint-disable-next-line gas-strict-inequalities
        uint256 absAmount = uint256(params.amountSpecified >= 0 ? params.amountSpecified : -params.amountSpecified);

        // ignore tiny trades relative to liquidity
        uint256 ratioBps = _impactRatioBps(key, isSellToken0, absAmount, liq);
        if (ratioBps == 0) return 0;

        uint16 cap = effectiveFeeMax;
        uint256 timeFee = _calculateTimeFee(staticFee, cap, isSellToken0, payer, cool);
        uint256 impactFee = _calculateImpactFee(liq, ratioBps, timeFee, staticFee);

        uint256 chosen = impactFee > timeFee ? impactFee : timeFee;
        if (chosen > cap) chosen = cap;
        // solhint-disable-next-line gas-strict-inequalities
        if (chosen <= staticFee) return 0;
        // forge-lint: disable-next-line(unsafe-typecast)
        additionalFee = uint24(chosen - staticFee);
    }

    function _calculateTimeFee(uint256 staticFee, uint256 feeMaxLocal, bool isSellToken0, address payer, uint256 cool)
        private
        view
        returns (uint256 feeOut)
    {
        uint48 ts = _getEffectiveActivityTimestamp(payer, isSellToken0);
        if (ts == 0) return staticFee;

        uint256 nowTs = block.timestamp;
        // solhint-disable-next-line gas-strict-inequalities
        if (nowTs <= ts) return staticFee;
        uint256 elapsed = nowTs - ts;
        // solhint-disable-next-line gas-strict-inequalities
        if (elapsed >= cool) return staticFee;

        uint256 cap = feeMaxLocal < staticFee ? staticFee : feeMaxLocal;

        uint256 reversed = 1e18 - Math.mulDiv(elapsed, 1e18, cool);
        feeOut = staticFee + Math.mulDiv(cap - staticFee, reversed, 1e18);

        if (feeOut < staticFee) revert FeeBelowStaticFee();
        if (feeOut > feeMaxLocal) revert FeeAboveMax();
    }

    // slither-disable-end timestamp

    /// @notice How large this trade is, in basis points, for the impact surcharge.
    /// @dev The base implementation divides the input amount by the pool's
    ///      liquidity `L`. Those are not the same kind of quantity: `L` is
    ///      sqrt-price-scaled, while `amountSpecified` is denominated in
    ///      whichever token is being paid in. On ETH/SHIB that makes the ratio
    ///      about eight orders of magnitude larger when the input is SHIB, so
    ///      measured over the matrix every buy of token0 cleared the 500 bp
    ///      trigger and no sale of token0 ever did -- a median fee of 354 bps
    ///      one way against 30 bps the other. The surcharge tracks which token
    ///      the input is denominated in, not price impact.
    ///
    ///      Kept as shipped, and overridden in `MEVChargeHookFixed`, so the
    ///      experiment can report both. `virtual` is the only change to the
    ///      original behaviour, and it is not one.
    function _impactRatioBps(PoolKey calldata, bool, uint256 absAmount, uint128 liq)
        internal
        view
        virtual
        returns (uint256)
    {
        if (liq == 0) return 0;
        return FullMath.mulDiv(absAmount, FEE_DENOMINATOR, uint256(liq));
    }

    function _calculateImpactFee(uint128 liq, uint256 impactBps_, uint256 timeFee, uint256 staticFee)
        private
        view
        returns (uint256 impactFee)
    {
        if (liq < 100) return timeFee;

        uint256 impactBps = impactBps_;
        if (impactBps > FEE_DENOMINATOR) impactBps = FEE_DENOMINATOR;
        // solhint-disable-next-line gas-strict-inequalities
        if (impactBps <= 500) return timeFee;

        uint256 maxMal = maliciousFeeMax;
        // No headroom for an impact surcharge; keep the time fee (avoid revert/DoS)
        // solhint-disable-next-line gas-strict-inequalities
        if (maxMal <= staticFee) return timeFee;

        uint256 range = maxMal - staticFee;
        // range > 0 guaranteed by the condition above

        impactFee = staticFee + Math.mulDiv(range, impactBps - 500, 9500);
        if (impactFee < staticFee) revert FeeBelowStaticFee();
        if (impactFee > maxMal) revert FeeAboveMax();
        return impactFee;
    }

    // ----------------------------- Helpers -----------------------------------------
    function _calculateLiquidityPenalty(BalanceDelta feeDelta, PoolId poolId, bytes32 positionKey)
        private
        view
        returns (BalanceDelta liquidityPenalty)
    {
        int128 a0 = feeDelta.amount0();
        int128 a1 = feeDelta.amount1();
        uint256 blocksElapsed = block.number - lastAddedLiquidity[poolId][positionKey];
        uint8 blockOff = config.blockNumberOffset;

        if (blocksElapsed + 1 > blockOff) {
            return BalanceDeltaLibrary.ZERO_DELTA;
        }

        uint256 remainingBlocks = uint256(blockOff) - blocksElapsed;
        uint256 p0 = FullMath.mulDiv(SafeCast.toUint128(a0), remainingBlocks, blockOff);
        uint256 p1 = FullMath.mulDiv(SafeCast.toUint128(a1), remainingBlocks, blockOff);

        liquidityPenalty = toBalanceDelta(SafeCast.toInt128(p0), SafeCast.toInt128(p1));
    }

    function _getEffectiveActivityTimestamp(address sender, bool isSellToken0) private view returns (uint48 ts) {
        // If selling token0, penalize based on last buy of token0.
        // If selling token1, penalize based on last buy of token1.
        uint256 lastBuy = isSellToken0 ? _lastBuyToken0[sender] : _lastBuyToken1[sender];
        if (lastBuy != 0) {
            // forge-lint: disable-next-line(unsafe-typecast)
            return uint48(lastBuy);
        }
        return _lastActivity[sender];
    }

    function _updateUserActivityTimestamp(address userAddr) private {
        if (userAddr != address(0)) {
            _lastActivity[userAddr] = uint48(block.timestamp);
        }
    }

    // `_getCollusionPairId` lived here: a linked-account resolver that walked
    // `userInfo[].primary` up to MAX_LINK_DEPTH. Nothing ever called it, so the
    // collusion feature it implies does not exist in this contract.

    function _getPoolLiquidity(PoolKey calldata key) private view returns (uint128 liquidity) {
        PoolId pid = _computePoolId(key);
        liquidity = _poolManager.getLiquidity(pid);
    }

    function _computePoolId(PoolKey calldata poolKey) private pure returns (PoolId poolId) {
        poolId = poolKey.toId();
    }

    function _updateEffectiveFeeMax() private {
        effectiveFeeMax = uint16(Math.min(uint256(config.feeMax), maliciousFeeMax));
    }

    function _poolKeyHash(PoolKey calldata key) private pure returns (bytes32) {
        return _keccak(abi.encode(key));
    }

    function _keccak(bytes memory data) private pure returns (bytes32 hash) {
        // solhint-disable-next-line no-inline-assembly
        assembly {
            hash := keccak256(add(data, 0x20), mload(data))
        }
    }
}
