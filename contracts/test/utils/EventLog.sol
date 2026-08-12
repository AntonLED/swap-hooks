// SPDX-License-Identifier: MIT
pragma solidity ^0.8.30;

import {Vm} from "forge-std/Vm.sol";

/**
 * @title EventLog
 * @notice Appends raw observations to a JSONL file, one record per line.
 * @dev Records observations only. Every derived quantity - IL, LVR, P&L,
 *      aggregates - is computed downstream in Python, so a metric can change
 *      without recompiling or re-running.
 *
 *      Two record kinds share the file, distinguished by the "kind" field.
 *      Swap records carry trader-side flow; the window record carries pool-side
 *      state. Downstream, the LP position is rebuilt from pool state while flow
 *      comes from swap records, so the two can be checked against each other.
 *      That check is only meaningful because the two sides never share a source.
 */
library EventLog {
    struct SwapRecord {
        uint256 candle;
        uint256 blockNumber;
        uint256 timestamp;
        int256 extPrice0;
        int256 extPrice1;
        uint160 sqrtPriceBeforeX96;
        uint160 sqrtPriceAfterX96;
        bool zeroForOne;
        uint256 amountIn;
        uint256 amountOut;
        uint24 feePips;
        uint24 feeAB;
        uint24 feeBA;
        int256 delta0;
        int256 delta1;
        uint256 expectedProfit;
        uint256 gas;
        address sender;
        // UU flow (spec 2026-08-09-uu-flow-design.md §5). `trader` is
        // "arb" or "uu"; `rWad`/`pWad` are the UU disadvantage/participation
        // diagnostics (zero for arb records); `extPriceGas` is that candle's
        // ETH/USDT feed, carried on every record so gas can be valued
        // trade-time downstream without a second join.
        string trader;
        int256 rWad;
        uint256 pWad;
        int256 extPriceGas;
    }

    struct WindowRecord {
        uint128 liquidity;
        int24 tickLower;
        int24 tickUpper;
        uint160 sqrtPriceInitialX96;
        uint160 sqrtPriceFinalX96;
        // Baseline is the state at the END of warm-up, not at candle 0: swaps
        // during warm-up move the pool but are not logged, so a candle-0
        // baseline would not reconcile against the logged flow.
        uint256 feeGrowthInside0X128Initial;
        uint256 feeGrowthInside1X128Initial;
        uint256 feeGrowthInside0X128;
        uint256 feeGrowthInside1X128;
        uint256 initialToken0;
        uint256 initialToken1;
        int256 extPrice0Initial;
        int256 extPrice1Initial;
        int256 extPrice0Final;
        int256 extPrice1Final;
        uint256 warmupCandles;
        uint256 candles;
    }

    function writeSwap(Vm vm, string memory path, SwapRecord memory r) internal {
        // Split into chunks: string.concat with many arguments blows the stack
        // under via_ir.
        string memory line = string.concat(
            '{"kind":"swap","candle":',
            vm.toString(r.candle),
            ',"blockNumber":',
            vm.toString(r.blockNumber),
            ',"timestamp":',
            vm.toString(r.timestamp),
            ',"extPrice0":',
            vm.toString(r.extPrice0),
            ',"extPrice1":',
            vm.toString(r.extPrice1),
            ',"sqrtPriceBeforeX96":',
            vm.toString(uint256(r.sqrtPriceBeforeX96)),
            ',"sqrtPriceAfterX96":',
            vm.toString(uint256(r.sqrtPriceAfterX96))
        );
        line = string.concat(
            line,
            ',"zeroForOne":',
            r.zeroForOne ? "true" : "false",
            ',"amountIn":',
            vm.toString(r.amountIn),
            ',"amountOut":',
            vm.toString(r.amountOut),
            ',"feePips":',
            vm.toString(uint256(r.feePips)),
            ',"feeAB":',
            vm.toString(uint256(r.feeAB)),
            ',"feeBA":',
            vm.toString(uint256(r.feeBA))
        );
        line = string.concat(
            line,
            ',"delta0":',
            vm.toString(r.delta0),
            ',"delta1":',
            vm.toString(r.delta1),
            ',"expectedProfit":',
            vm.toString(r.expectedProfit),
            ',"gas":',
            vm.toString(r.gas),
            ',"sender":"',
            vm.toString(r.sender),
            '"'
        );
        line = string.concat(
            line,
            ',"trader":"',
            r.trader,
            '","rWad":',
            vm.toString(r.rWad),
            ',"pWad":',
            vm.toString(r.pWad),
            ',"extPriceGas":',
            vm.toString(r.extPriceGas),
            "}"
        );
        vm.writeLine(path, line);
    }

    function writeWindow(Vm vm, string memory path, WindowRecord memory r) internal {
        string memory line = string.concat(
            '{"kind":"window","liquidity":',
            vm.toString(uint256(r.liquidity)),
            ',"tickLower":',
            vm.toString(int256(r.tickLower)),
            ',"tickUpper":',
            vm.toString(int256(r.tickUpper)),
            ',"sqrtPriceInitialX96":',
            vm.toString(uint256(r.sqrtPriceInitialX96)),
            ',"sqrtPriceFinalX96":',
            vm.toString(uint256(r.sqrtPriceFinalX96))
        );
        line = string.concat(
            line,
            ',"feeGrowthInside0X128Initial":',
            vm.toString(r.feeGrowthInside0X128Initial),
            ',"feeGrowthInside1X128Initial":',
            vm.toString(r.feeGrowthInside1X128Initial),
            ',"feeGrowthInside0X128":',
            vm.toString(r.feeGrowthInside0X128),
            ',"feeGrowthInside1X128":',
            vm.toString(r.feeGrowthInside1X128),
            ',"initialToken0":',
            vm.toString(r.initialToken0),
            ',"initialToken1":',
            vm.toString(r.initialToken1)
        );
        line = string.concat(
            line,
            ',"extPrice0Initial":',
            vm.toString(r.extPrice0Initial),
            ',"extPrice1Initial":',
            vm.toString(r.extPrice1Initial),
            ',"extPrice0Final":',
            vm.toString(r.extPrice0Final),
            ',"extPrice1Final":',
            vm.toString(r.extPrice1Final),
            ',"warmupCandles":',
            vm.toString(r.warmupCandles),
            ',"candles":',
            vm.toString(r.candles),
            "}"
        );
        vm.writeLine(path, line);
    }
}
