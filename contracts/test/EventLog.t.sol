// SPDX-License-Identifier: MIT
pragma solidity ^0.8.30;

import {Test} from "forge-std/Test.sol";
import {EventLog} from "./utils/EventLog.sol";

contract EventLogTest is Test {
    /// @dev Each test gets its own file. `setUp` runs once and every test then
    ///      starts from a snapshot of the EVM state, but filesystem writes are
    ///      not EVM state and are never rolled back — so a shared path would
    ///      accumulate every test's records.
    function _path(string memory name) internal returns (string memory p) {
        p = string.concat("../results/_eventlog_", name, ".jsonl");
        if (vm.exists(p)) vm.removeFile(p);
    }

    function test_writesOneLinePerRecord() public {
        string memory PATH = _path("one_line_per_record");
        EventLog.writeSwap(vm, PATH, _swap(1));
        EventLog.writeSwap(vm, PATH, _swap(2));

        string[] memory lines = vm.split(vm.readFile(PATH), "\n");
        assertEq(lines.length, 3, "two records plus empty tail");
    }

    function test_swapRecordIsParseableJson() public {
        string memory PATH = _path("swap_json");
        EventLog.writeSwap(vm, PATH, _swap(7));

        string memory line = vm.split(vm.readFile(PATH), "\n")[0];
        assertEq(vm.parseJsonString(line, ".kind"), "swap");
        assertEq(vm.parseJsonUint(line, ".candle"), 7);
        assertEq(vm.parseJsonUint(line, ".gas"), 21000);
        assertEq(vm.parseJsonUint(line, ".feePips"), 3000);
        assertTrue(vm.parseJsonBool(line, ".zeroForOne"));
        assertEq(vm.parseJsonString(line, ".trader"), "arb");
        assertEq(vm.parseJsonInt(line, ".rWad"), 0);
        assertEq(vm.parseJsonUint(line, ".pWad"), 0);
        assertEq(vm.parseJsonInt(line, ".extPriceGas"), 300000000000);
    }

    /// Everything the LP position is reconstructed from must be present, or the
    /// conservation check downstream has nothing independent to compare against.
    function test_windowRecordCarriesPoolSideState() public {
        string memory PATH = _path("window_state");
        EventLog.writeWindow(vm, PATH, _window());

        string memory line = vm.split(vm.readFile(PATH), "\n")[0];
        assertEq(vm.parseJsonString(line, ".kind"), "window");
        assertEq(vm.parseJsonUint(line, ".liquidity"), 1e21);
        assertEq(vm.parseJsonUint(line, ".feeGrowthInside0X128Initial"), 11);
        assertEq(vm.parseJsonUint(line, ".feeGrowthInside0X128"), 12345);
        assertEq(vm.parseJsonUint(line, ".feeGrowthInside1X128"), 67890);
        assertEq(vm.parseJsonUint(line, ".initialToken0"), 5e18);
        assertEq(vm.parseJsonInt(line, ".tickLower"), -887220);
    }

    function test_bothKindsCoexistInOneFile() public {
        string memory PATH = _path("both_kinds");
        EventLog.writeSwap(vm, PATH, _swap(1));
        EventLog.writeWindow(vm, PATH, _window());

        string[] memory lines = vm.split(vm.readFile(PATH), "\n");
        assertEq(vm.parseJsonString(lines[0], ".kind"), "swap");
        assertEq(vm.parseJsonString(lines[1], ".kind"), "window");
    }

    function _swap(uint256 candle) internal view returns (EventLog.SwapRecord memory) {
        return EventLog.SwapRecord({
            candle: candle,
            blockNumber: block.number,
            timestamp: block.timestamp,
            extPrice0: 300000000000,
            extPrice1: 2000,
            sqrtPriceBeforeX96: 79228162514264337593543950336,
            sqrtPriceAfterX96: 79228162514264337593543950336,
            zeroForOne: true,
            amountIn: 1e18,
            amountOut: 9e17,
            feePips: 3000,
            feeAB: 3000,
            feeBA: 3000,
            delta0: -1e18,
            delta1: 9e17,
            expectedProfit: 1e15,
            gas: 21000,
            sender: address(0xBEEF),
            trader: "arb",
            rWad: 0,
            pWad: 0,
            extPriceGas: 300000000000
        });
    }

    function _window() internal pure returns (EventLog.WindowRecord memory) {
        return EventLog.WindowRecord({
            liquidity: 1e21,
            tickLower: -887220,
            tickUpper: 887220,
            sqrtPriceInitialX96: 79228162514264337593543950336,
            sqrtPriceFinalX96: 79228162514264337593543950336,
            feeGrowthInside0X128Initial: 11,
            feeGrowthInside1X128Initial: 22,
            feeGrowthInside0X128: 12345,
            feeGrowthInside1X128: 67890,
            initialToken0: 5e18,
            initialToken1: 5e18,
            extPrice0Initial: 300000000000,
            extPrice1Initial: 2000,
            extPrice0Final: 310000000000,
            extPrice1Final: 2100,
            warmupCandles: 60,
            candles: 1440
        });
    }
}
