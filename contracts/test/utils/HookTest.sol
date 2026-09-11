// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.26;

import {console} from "forge-std/console.sol";

import {Test} from "forge-std/Test.sol";
import {Currency} from "@uniswap/v4-core/src/types/Currency.sol";

import {BaseTest} from "./BaseTest.sol";
import {EasyPosm} from "./libraries/EasyPosm.sol";
import {HookFlags} from "./libraries/HookFlags.sol";
import {IHooksExtended} from "./../../src/interfaces/IHooksExtended.sol";
import {MEVChargeHook} from "./../../src/MEVChargeHook.sol";

import {IHooks} from "@uniswap/v4-core/src/interfaces/IHooks.sol";
import {Hooks} from "@uniswap/v4-core/src/libraries/Hooks.sol";
import {PoolKey} from "@uniswap/v4-core/src/types/PoolKey.sol";
import {LPFeeLibrary} from "@uniswap/v4-core/src/libraries/LPFeeLibrary.sol";
import {IPoolManager, SwapParams, ModifyLiquidityParams} from "@uniswap/v4-core/src/interfaces/IPoolManager.sol";
import {IPositionManager} from "@uniswap/v4-periphery/src/interfaces/IPositionManager.sol";
import {PoolId, PoolIdLibrary} from "@uniswap/v4-core/src/types/PoolId.sol";
import {TickMath} from "v4-core/src/libraries/TickMath.sol";

import {LiquidityAmounts} from "v4-core/test/utils/LiquidityAmounts.sol";

import {MockV3Aggregator} from "@chainlink/local/src/data-feeds/MockV3Aggregator.sol";
import {AggregatorV2V3Interface} from "@chainlink/local/src/data-feeds/interfaces/AggregatorV2V3Interface.sol";

import {Constants} from "@uniswap/v4-core/test/utils/Constants.sol";

contract HookTest is BaseTest {
    using EasyPosm for IPositionManager;

    MockV3Aggregator priceFeed0;
    MockV3Aggregator priceFeed1;

    IHooksExtended hookContract;

    Currency currency0;
    Currency currency1;

    /////////////////////////////////////
    // --- Configure These ---
    /////////////////////////////////////

    int24 tickSpacing = 60;
    uint160 startingPrice = Constants.SQRT_PRICE_1_1;
    uint24 internal constant _BASE_FEE = 3_000; // 0.3%

    // --- liquidity position configuration --- //
    uint256 public token0Amount = 100e18;
    uint256 public token1Amount = 100e18;

    PoolKey poolKey;
    uint256 tokenId;
    PoolId poolId;

    PoolKey noHookKey;
    uint256 noHookTokenId;
    PoolId noHookPoolId;

    // Used as void
    function deployCurrencyPair() internal override returns (Currency, Currency) {
        (currency0, currency1) = super.deployCurrencyPair();
    }

    function deployHookAndFeeds(string memory hookName) internal {
        priceFeed0 = new MockV3Aggregator(8, 300000000000); // $3000 ETH
        priceFeed1 = new MockV3Aggregator(8, 30000000); // $0.03 SHIB

        address flags = address(0);

        // The hook address
        if (keccak256(bytes(hookName)) == keccak256(bytes("BAHook"))) {
            flags = address(HookFlags.BA_HOOK_FLAGS);
        } else if (keccak256(bytes(hookName)) == keccak256(bytes("MEVChargeHookFixed"))) {
            flags = address(HookFlags.MEV_CHARGE_FIXED_HOOK_FLAGS);
        } else if (keccak256(bytes(hookName)) == keccak256(bytes("MEVChargeHook"))) {
            flags = address(HookFlags.MEV_CHARGE_HOOK_FLAGS);
        } else if (
            keccak256(bytes(hookName)) == keccak256(bytes("PegDefence"))
                || keccak256(bytes(hookName)) == keccak256(bytes("PegCapture"))
        ) {
            flags = address(HookFlags.PEG_STABILITY_HOOK_FLAGS);
        } else if (keccak256(bytes(hookName)) == keccak256(bytes("DAHook"))) {
            flags = address(HookFlags.DA_HOOK_FLAGS);
        } else if (keccak256(bytes(hookName)) == keccak256(bytes("ABHook"))) {
            flags = address(HookFlags.AB_HOOK_FLAGS);
        } else if (keccak256(bytes(hookName)) == keccak256(bytes("VolatilityHook"))) {
            flags = address(HookFlags.VOLATILITY_HOOK_FLAGS);
        } else if (keccak256(bytes(hookName)) == keccak256(bytes("MyHook"))) {
            flags = address(HookFlags.MY_HOOK_FLAGS);
        }

        // A zero address means the name fell through every branch. Hook
        // permissions live in the low bits of the address, so deploying at
        // address(0) yields a hook with no permissions and pool initialisation
        // fails later with an unrelated-looking error. Fail here instead.
        require(flags != address(0), "unknown hook name");

        console.log("Flag address: ", vm.toString(flags));

        bytes memory constructorArgs = abi.encode(
            poolManager, AggregatorV2V3Interface(address(priceFeed0)), AggregatorV2V3Interface(address(priceFeed1))
        );

        // PegStabilityHook ships in two readings behind one contract, selected
        // by a constructor flag. The run name picks the mode; the artifact path
        // is the same for both.
        string memory artifact = hookName;
        if (keccak256(bytes(hookName)) == keccak256(bytes("PegDefence"))) {
            artifact = "PegStabilityHook";
            constructorArgs = abi.encode(
                poolManager,
                AggregatorV2V3Interface(address(priceFeed0)),
                AggregatorV2V3Interface(address(priceFeed1)),
                uint8(0) // PegMode.Defence
            );
        } else if (keccak256(bytes(hookName)) == keccak256(bytes("PegCapture"))) {
            artifact = "PegStabilityHook";
            constructorArgs = abi.encode(
                poolManager,
                AggregatorV2V3Interface(address(priceFeed0)),
                AggregatorV2V3Interface(address(priceFeed1)),
                uint8(1) // PegMode.Capture
            );
        }

        bytes memory path = abi.encodePacked(artifact, ".sol:", artifact);

        console.log(string(path));

        deployCodeTo(string(path), constructorArgs, flags);
        hookContract = IHooksExtended(flags);

        // Fee-box compliance fix (2026-08-09-uu-flow-design.md §7): the
        // 2026-08-09 audit found MEVChargeHook charging up to 1000 pips
        // against the shared box every other policy respects (100 pips..
        // 10000 pips, spec §4.5) on 49% of its swaps, because its default
        // `feeMax` is 1000 BASIS POINTS (100000 pips), an order of magnitude
        // wider. Clamp it here, in the harness deploy path -- a config
        // change via the contract's own setter, not a policy-logic change.
        // `MEVChargeHookFixed` inherits the same clamp path (it IS a
        // MEVChargeHook; only its impact measure differs).
        //
        // `flaggedFeeAdditional` must shrink first: the contract's own
        // `setFeeMax` invariant (`fixedLpFee + flaggedFeeAdditional <=
        // feeMax`) rejects 100 bps while the flagged surcharge is still its
        // 400bp default (30 + 400 > 100). 40 keeps the flagged surcharge at
        // roughly its original ~40% share of the box, now 100 bps instead of
        // 1000.
        if (
            keccak256(bytes(hookName)) == keccak256(bytes("MEVChargeHook"))
                || keccak256(bytes(hookName)) == keccak256(bytes("MEVChargeHookFixed"))
        ) {
            MEVChargeHook(flags).setFlaggedFeeAdditional(40);
            MEVChargeHook(flags).setFeeMax(100);
        }
    }

    function deployPool() internal virtual {
        // Create the pool with DYNAMIC FEE
        poolKey = PoolKey(currency0, currency1, LPFeeLibrary.DYNAMIC_FEE_FLAG, tickSpacing, IHooks(hookContract));
        poolId = poolKey.toId();

        // Create the basic pool
        noHookKey = PoolKey(currency0, currency1, _BASE_FEE, tickSpacing, IHooks(address(0)));
        noHookPoolId = noHookKey.toId();

        startingPrice = Constants.SQRT_PRICE_1_1; // Starting price, sqrtPriceX96; floor(sqrt(1) * 2^96)

        int24 currentTick = TickMath.getTickAtSqrtPrice(startingPrice);

        int24 tickLower = truncateTickSpacing((currentTick - 750 * tickSpacing), tickSpacing);
        int24 tickUpper = truncateTickSpacing((currentTick + 750 * tickSpacing), tickSpacing);

        // Use full-range ticks, aligned to tickSpacing
        int24 minTick = truncateTickSpacing(TickMath.MIN_TICK, tickSpacing);
        int24 maxTick = truncateTickSpacing(TickMath.MAX_TICK, tickSpacing);

        // Initialize the pool - this will trigger afterInitialize and set the dynamic fee
        poolManager.initialize(poolKey, startingPrice);
        poolManager.initialize(noHookKey, startingPrice);

        // Converts token amounts to liquidity units
        // i.e. "This is my liquidity pool with this range, I have this amounts of money"
        // "And I want the initial price to be this"
        // "What should be the liquidity?"
        uint128 liquidity = LiquidityAmounts.getLiquidityForAmounts(
            startingPrice,
            TickMath.getSqrtPriceAtTick(minTick), // if the price is below the tick, you don't earn fees
            TickMath.getSqrtPriceAtTick(maxTick), // if the price is above the tick, you don't earn fees
            token0Amount,
            token1Amount
        );

        console.log("Liquidity added: ", liquidity);

        // slippage limits
        uint256 amount0Max = token0Amount + 1; // If at the time of the deposit this is higher, you won't mint
        uint256 amount1Max = token1Amount + 1; // If at the time of the deposit this is higher, you won't mint

        (tokenId,) = positionManager.mint(
            poolKey,
            minTick,
            maxTick,
            liquidity,
            amount0Max,
            amount1Max,
            address(this),
            block.timestamp,
            Constants.ZERO_BYTES
        );

        (noHookTokenId,) = positionManager.mint(
            noHookKey,
            minTick,
            maxTick,
            liquidity,
            amount0Max,
            amount1Max,
            address(this),
            block.timestamp,
            Constants.ZERO_BYTES
        );
    }

    function truncateTickSpacing(int24 tick, int24 tickSpacing) internal pure returns (int24) {
        /// forge-lint: disable-next-line(divide-before-multiply)
        return ((tick / tickSpacing) * tickSpacing);
    }
}
