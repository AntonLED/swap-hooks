// SPDX-License-Identifier: MIT
pragma solidity ^0.8.30;

import {Test} from "forge-std/Test.sol";
import {ReplayTest} from "./Replay.t.sol";

/**
 * @notice Verifies the UU flow integration into the replay harness (spec
 *         `docs/superpowers/specs/2026-08-09-uu-flow-design.md` §10.2-10.3):
 *         the off-switch is bit-for-bit inert, UU swaps are tagged and appear
 *         on both sides, the favourable direction always executes, and a
 *         higher fee thins UU volume.
 *
 * Each test deploys its own fresh `ReplayTest` harness (composition, not
 * inheritance -- inheriting would make forge discover `ReplayTest`'s own
 * `testReplay`/`test_gasCostSuppressesMarginalTrades`/
 * `test_poolOpensAtTheExternalPrice` as additional tests of this contract,
 * run against whatever `setUp` this file defines) and drives it via
 * `configureForTest`, a test-only seam on `ReplayTest` that takes the same
 * configuration `setUp` derives from env vars, but as direct parameters.
 *
 * That indirection matters: an earlier version drove the harness through
 * `vm.setEnv` + `ReplayTest.setUp()`, mirroring `run_one.py`'s real
 * subprocess interface exactly -- and failed nondeterministically, because
 * env vars are process-global and forge runs this file's test functions
 * concurrently, so two tests' `vm.setEnv` calls raced and one run silently
 * read another's configuration. A real `run_one.py` subprocess doesn't have
 * this problem; this in-process composition does.
 */
contract ReplayUUTest is Test {
    uint256 constant CANDLES = 200;
    uint256 constant JUMP_AT = 150;
    uint256 constant BASE_PRICE0 = 3000e8; // $3000, ETH-scale
    uint256 constant BASE_PRICE1 = 1e8; // $1
    uint256 constant JUMP_PRICE0 = 4500e8; // +50%, big enough to dominate any fee
    uint256 constant GAS_PRICE_ETH = 3000e8;
    uint256 constant UU_SIZE_WAD = 1000e18; // 1000 USDT-wad per side per candle

    string constant WORK_DIR = "../.work/replayuu_test/";
    string constant FLAT_TRACE0_PATH = "../.work/replayuu_test/flat_trace0.csv";
    string constant JUMP_TRACE0_PATH = "../.work/replayuu_test/jump_trace0.csv";
    string constant TRACE1_PATH = "../.work/replayuu_test/trace1.csv";
    string constant GAS_TRACE_PATH = "../.work/replayuu_test/trace_gas.csv";
    string constant UU_TRACE_PATH = "../.work/replayuu_test/uu_trace.csv";

    function setUp() public {
        if (!vm.exists(WORK_DIR)) vm.createDir(WORK_DIR, true);
        _writeConstantTrace(FLAT_TRACE0_PATH, BASE_PRICE0);
        _writeJumpTrace(JUMP_TRACE0_PATH, BASE_PRICE0, JUMP_PRICE0, JUMP_AT);
        _writeConstantTrace(TRACE1_PATH, BASE_PRICE1);
        _writeConstantTrace(GAS_TRACE_PATH, GAS_PRICE_ETH);
        _writeUuTrace(UU_TRACE_PATH, UU_SIZE_WAD);
    }

    // ------------------------------------------------------------ fixtures

    function _writeConstantTrace(string memory path, uint256 price) internal {
        if (vm.exists(path)) vm.removeFile(path);
        for (uint256 i = 0; i < CANDLES; i++) {
            vm.writeLine(path, string.concat(vm.toString(i * 60_000), ",", vm.toString(price)));
        }
    }

    function _writeJumpTrace(string memory path, uint256 before_, uint256 after_, uint256 jumpAt) internal {
        if (vm.exists(path)) vm.removeFile(path);
        for (uint256 i = 0; i < CANDLES; i++) {
            uint256 price = i < jumpAt ? before_ : after_;
            vm.writeLine(path, string.concat(vm.toString(i * 60_000), ",", vm.toString(price)));
        }
    }

    /// @dev Share mode, constant nonzero size both directions, u=0 (unused in
    ///      share mode). Matches `experiments.uu.export_uu_trace`'s format.
    function _writeUuTrace(string memory path, uint256 sizeWad) internal {
        if (vm.exists(path)) vm.removeFile(path);
        for (uint256 i = 0; i < CANDLES; i++) {
            vm.writeLine(
                path,
                string.concat(vm.toString(i * 60_000), ",", vm.toString(sizeWad), ",0,", vm.toString(sizeWad), ",0")
            );
        }
    }

    function _outPath(string memory name) internal returns (string memory p) {
        p = string.concat("../results/_replayuu_", name, ".jsonl");
        if (vm.exists(p)) vm.removeFile(p);
    }

    function _run(string memory trace0Path, bool withUu, string memory outPath, uint256 feePips, uint256 gasPriceWei)
        internal
        returns (ReplayTest harness)
    {
        harness = new ReplayTest();
        harness.configureForTest(
            trace0Path, TRACE1_PATH, GAS_TRACE_PATH, outPath, gasPriceWei, 60, feePips, withUu, UU_TRACE_PATH
        );
        harness.testReplay();
    }

    // ---------------------------------------------------------------- tests

    /// @dev Differential golden precursor (spec §10.2): UU off must produce
    ///      byte-identical output across independent runs -- the UU code
    ///      path is inert when off.
    function test_uuOffIsBitForBitIdentical() public {
        string memory outA = _outPath("off_a");
        string memory outB = _outPath("off_b");

        _run(FLAT_TRACE0_PATH, false, outA, 3000, 20 gwei);
        _run(FLAT_TRACE0_PATH, false, outB, 3000, 20 gwei);

        assertEq(vm.readFile(outA), vm.readFile(outB), "two off-runs must be byte-identical");
    }

    /// @dev Spec §10.3: UU swaps are tagged and both directions appear.
    function test_uuSwapsAppearTaggedAndBothDirections() public {
        string memory out = _outPath("tagged");
        _run(FLAT_TRACE0_PATH, true, out, 3000, 20 gwei);

        string[] memory lines = vm.split(vm.readFile(out), "\n");
        bool sawTrue;
        bool sawFalse;
        for (uint256 i = 0; i < lines.length; i++) {
            if (bytes(lines[i]).length == 0) continue;
            if (keccak256(bytes(vm.parseJsonString(lines[i], ".kind"))) != keccak256(bytes("swap"))) continue;
            if (keccak256(bytes(vm.parseJsonString(lines[i], ".trader"))) != keccak256(bytes("uu"))) continue;

            uint256 p = vm.parseJsonUint(lines[i], ".pWad");
            assertGt(p, 0, "a logged UU swap must have cleared P > 0");
            assertLe(p, 1e18, "P is a probability, at most 1e18");

            if (vm.parseJsonBool(lines[i], ".zeroForOne")) sawTrue = true;
            else sawFalse = true;
        }
        assertTrue(sawTrue, "no A->B uu swap logged");
        assertTrue(sawFalse, "no B->A uu swap logged");
    }

    /// @dev Spec §10.3: with the pool pinned off-price by one large arb-free
    ///      move (gas suppresses the arbitrageur, see
    ///      `test_gasCostSuppressesMarginalTrades`), the direction that
    ///      benefits from the deviation must clear at P == 1e18 exactly (the
    ///      upper branch, `r >= 0`).
    function test_uuFavorableDirectionAlwaysExecutes() public {
        string memory out = _outPath("favorable");
        // A normal gas price. Silencing the arbitrageur with an astronomical
        // one no longer works, because retail pays the same gas and would be
        // annihilated with it -- and P would never reach 1 for anyone.
        //
        // It is not needed either: the candle order is feeds -> UU A->B ->
        // UU B->A -> arbitrage (spec §4), so on the jump candle itself the UU
        // side sees the pool still displaced, before the arbitrageur touches
        // it. Hence the check below is pinned to JUMP_AT exactly.
        _run(JUMP_TRACE0_PATH, true, out, 3000, 20 gwei);

        // price0 jumped up with the pool unmoved: token0 got relatively more
        // expensive externally, so buying it (B->A, zeroForOne == false) is
        // the favourable side.
        string[] memory lines = vm.split(vm.readFile(out), "\n");
        bool sawFavorableAtOne;
        for (uint256 i = 0; i < lines.length; i++) {
            if (bytes(lines[i]).length == 0) continue;
            if (keccak256(bytes(vm.parseJsonString(lines[i], ".kind"))) != keccak256(bytes("swap"))) continue;
            if (keccak256(bytes(vm.parseJsonString(lines[i], ".trader"))) != keccak256(bytes("uu"))) continue;
            if (vm.parseJsonUint(lines[i], ".candle") != JUMP_AT) continue;
            if (vm.parseJsonBool(lines[i], ".zeroForOne")) continue; // want B->A

            if (vm.parseJsonUint(lines[i], ".pWad") == 1e18) {
                sawFavorableAtOne = true;
                break;
            }
        }
        assertTrue(sawFavorableAtOne, "the favourable side must clear at P == 1 after the pin");
    }

    /// @dev Spec §2.1: gamma enters r directly, so a higher fee thins UU
    ///      participation and, with everything else held fixed, total UU
    ///      volume falls. A FLAT external price is what isolates the fee's
    ///      direct effect here: with no external deviation the arbitrageur has
    ///      nothing to correct, so it stays out on its own. The previous
    ///      version used an astronomical gas price for that, which now wipes
    ///      out retail too -- both sides pay the same gas.
    function test_higherFeeThinsUuVolume() public {
        string memory outLow = _outPath("fee_low");
        string memory outHigh = _outPath("fee_high");

        _run(FLAT_TRACE0_PATH, true, outLow, 500, 20 gwei);
        _run(FLAT_TRACE0_PATH, true, outHigh, 6000, 20 gwei);

        assertGt(_sumUuAmountIn(outLow), _sumUuAmountIn(outHigh), "a higher fee must thin UU volume");
    }

    /// @dev Regression pin for the 2026-08-12 gas-denomination defect: gas
    ///      enters `r` in token1 units for BOTH directions, because that is
    ///      the currency `UUMath.rWad` values both legs in. The defect
    ///      converted the B->A gas through `price0` instead of `price1`,
    ///      understating it by price0/price1 -- 3000x on this fixture pair --
    ///      so a gas price high enough to price out every A->B user left the
    ///      B->A side trading as if gas were free.
    ///
    ///      At 2000 gwei with the fixture's $3000 ETH, one swap's gas is
    ///      ~$459 against a $1000 potential trade: `r` is dominated by gas in
    ///      both directions, `P` underflows to zero, and no UU swap of EITHER
    ///      direction may execute. Under the defect this fails: B->A sees
    ///      ~$0.15 of gas and keeps trading at P ~ 0.5.
    function test_uuHighGasSuppressesBothDirections() public {
        string memory out = _outPath("high_gas_both");
        _run(FLAT_TRACE0_PATH, true, out, 3000, 2000 gwei);

        string[] memory lines = vm.split(vm.readFile(out), "\n");
        for (uint256 i = 0; i < lines.length; i++) {
            if (bytes(lines[i]).length == 0) continue;
            if (keccak256(bytes(vm.parseJsonString(lines[i], ".kind"))) != keccak256(bytes("swap"))) continue;
            if (keccak256(bytes(vm.parseJsonString(lines[i], ".trader"))) != keccak256(bytes("uu"))) continue;
            assertTrue(
                false,
                string.concat(
                    "no UU swap may clear at prohibitive gas; found zeroForOne=",
                    vm.parseJsonBool(lines[i], ".zeroForOne") ? "true" : "false"
                )
            );
        }
    }

    function _sumUuAmountIn(string memory path) internal returns (uint256 total) {
        string[] memory lines = vm.split(vm.readFile(path), "\n");
        for (uint256 i = 0; i < lines.length; i++) {
            if (bytes(lines[i]).length == 0) continue;
            if (keccak256(bytes(vm.parseJsonString(lines[i], ".kind"))) != keccak256(bytes("swap"))) continue;
            if (keccak256(bytes(vm.parseJsonString(lines[i], ".trader"))) != keccak256(bytes("uu"))) continue;
            total += vm.parseJsonUint(lines[i], ".amountIn");
        }
    }
}
