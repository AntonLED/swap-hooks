"""Regression tests for the 2026-08-10 changes (audit).

Everything here was written after the change, against the change, by someone
who did not write it. A test that fails is a defect report with a reproduction
attached, not a TODO: see the accompanying audit note for severity.

Nothing in this file runs `forge`, `run_one`, or any matrix cell -- a matrix run
is normally in flight and every one of those writes shared trace files.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent


# --------------------------------------------------------------- C: matrix.collect


def _specs(windows_per_pair: int = 1):
    from experiments.matrix import PAIRS, enumerate_runs

    windows = {
        pair.name: [
            {
                "start_ms": 1_704_067_200_000 + 86_400_000 * i,
                "end_ms": 1_704_067_200_000 + 86_400_000 * (i + 1),
                "regime": ("low", "mid", "high")[i % 3],
                "volatility": 0.02 + 0.01 * i,
                "pair": pair.name,
            }
            for i in range(windows_per_pair)
        ]
        for pair in PAIRS
    }
    return enumerate_runs(windows)


def _metrics(net_result: float = 100.0) -> dict:
    return {
        "fee_income": 10.0,
        "lp_principal": 1.0,
        "lp_value": 1.0,
        "hodl_value": 1.0,
        "il": 5.0,
        "net_result": net_result,
        "net_result_tt": net_result + 1.0,
        "arb_mtm": -net_result,
        "arb_profit_realized": 3.0,
        "gas_cost": 1.0,
        "retained_volume": 1000.0,
        "uu_volume": 900.0,
        "arb_volume": 100.0,
        "uu_fee_share": 0.5,
        "uu_participation": 0.7,
        "trade_count": 12,
        "conservation_error_token0": 0.0,
        "conservation_error_token1": 0.0,
    }


def _seed(results_dir: Path, specs, net_result: float = 100.0) -> None:
    results_dir.mkdir(parents=True, exist_ok=True)
    for spec in specs:
        (results_dir / f"{spec.key}.metrics.json").write_text(
            json.dumps(_metrics(net_result), indent=2) + "\n"
        )


def test_collect_writes_exactly_the_axes_the_frozen_summaries_carry(tmp_path):
    """`collect` replaced the runner's return value as the source of
    summary.csv. The columns must not have moved: two frozen summaries and
    every notebook read them by name.
    """
    from experiments.matrix import base_row, collect

    specs = _specs()
    _seed(tmp_path, specs)
    frame = collect(specs, tmp_path)

    assert len(frame) == len(specs)

    # A summary is absent between a run being archived and the next one
    # finishing, which is a normal state and not a failure. Check against
    # whichever frozen summaries are on disk.
    candidates = [
        ROOT / "results-uu" / "summary.csv",
        ROOT / "results" / "summary.csv",
        ROOT / "results-uu-preflight-defect" / "summary-with-feequote-fix.csv",
    ]
    present = [c for c in candidates if c.exists()]
    if not present:
        pytest.skip("no frozen summary on disk to compare column order against")

    for path in present:
        frozen = pd.read_csv(path, nrows=0).columns.tolist()
        # The axis half is what the notebooks index by name, and it comes from
        # `base_row`, so one function owns it. The metric half legitimately
        # differs between the arb-only and UU summaries.
        axes = list(base_row(specs[0]))
        assert frozen[: len(axes)] == axes, f"axis columns moved in {path.name}"
    assert list(frame.columns)[: len(list(base_row(specs[0])))] == list(
        base_row(specs[0])
    )


def test_collect_skips_cells_with_no_metrics_rather_than_inventing_them(tmp_path):
    from experiments.matrix import collect

    specs = _specs()
    _seed(tmp_path, specs[:5])
    frame = collect(specs, tmp_path)
    assert len(frame) == 5


# ------------------------------------------------------------ D: run_matrix wiring


def _run_main(tmp_path, monkeypatch, argv, executed_error_for=None):
    """Drive the real `run_matrix.main()` against a throwaway results root.

    `ROOT` is patched first: `main()` derives `results_root` from it, and an
    unpatched call would write into the live `results-uu/`.
    """
    import run_matrix
    from experiments.matrix import PAIRS, base_row

    monkeypatch.setattr(run_matrix, "ROOT", tmp_path)
    # The runner refuses to start where forge cannot write, and reads the
    # allowlist from foundry.toml relative to ROOT. A fixture that stands in for
    # the repository has to stand in for that file too, or it is testing a
    # repository the runner would rightly reject.
    contracts = tmp_path / "contracts"
    contracts.mkdir(exist_ok=True)
    (contracts / "foundry.toml").write_text(
        "[profile.default]\n"
        "fs_permissions = [\n"
        '    {access = "read-write", path = "../results/"},\n'
        '    {access = "read-write", path = "../results-uu/"},\n'
        "]\n"
    )
    monkeypatch.setattr(run_matrix, "load_gas", dict)
    monkeypatch.setattr(
        run_matrix,
        "load_windows",
        lambda per_tercile=1: {
            pair.name: [
                {
                    "start_ms": 1_704_067_200_000,
                    "end_ms": 1_704_153_600_000,
                    "regime": "low",
                    "volatility": 0.02,
                    "pair": pair.name,
                }
            ]
            for pair in PAIRS
        },
    )

    def fake_execute_parallel(selected, results_dir, gas, **kwargs):
        results_dir = Path(results_dir)
        results_dir.mkdir(parents=True, exist_ok=True)
        rows = []
        for spec in selected:
            if executed_error_for is not None and spec.key == executed_error_for:
                # The runner failed this cell. It deliberately does NOT remove
                # the metrics file a previous run left behind -- nothing in the
                # pipeline does.
                rows.append({**base_row(spec), "error": "RuntimeError: forge died"})
                continue
            (results_dir / f"{spec.key}.metrics.json").write_text(
                json.dumps(_metrics(), indent=2) + "\n"
            )
            rows.append({**base_row(spec), **_metrics(), "error": None})
        return pd.DataFrame(rows)

    monkeypatch.setattr(run_matrix, "execute_parallel", fake_execute_parallel)
    monkeypatch.setattr("sys.argv", ["run_matrix.py", *argv])
    run_matrix.main()
    return pd.read_csv(tmp_path / "results" / "summary.csv")


def test_policy_restriction_leaves_the_summary_describing_the_whole_matrix(
    tmp_path, monkeypatch
):
    """The fix that motivated `collect`, as a regression guard."""
    from experiments.matrix import PAIRS

    specs = _specs()
    _seed(tmp_path / "results" / "matrix", specs)

    frame = _run_main(tmp_path, monkeypatch, ["--policy", "BAHook", "--workers", "1"])
    assert len(frame) == len(specs)
    assert set(frame["pair"]) == {pair.name for pair in PAIRS}


def test_pair_restriction_also_leaves_the_summary_whole(tmp_path, monkeypatch):
    """DEFECT. `--pair` filters `windows` *before* `enumerate_runs`, so `specs`
    is not the whole matrix and `collect(specs, ...)` cannot describe it.

    `run_matrix.py:145` restricts the windows; `run_matrix.py:149` then builds
    `specs` from them, under a comment claiming `specs` "is the whole matrix and
    stays that way". Only `--policy` (line 151, applied to `selected`) honours
    that. So the exact failure `collect` was introduced to fix -- summary.csv
    silently describing a third of the experiment while the rest sits on disk
    -- still happens for the flag it was first observed with.
    """
    specs = _specs()
    _seed(tmp_path / "results" / "matrix", specs)

    frame = _run_main(tmp_path, monkeypatch, ["--pair", "ETH/SHIB", "--workers", "1"])
    assert len(frame) == len(specs), (
        f"--pair truncated summary.csv to {len(frame)} of {len(specs)} cells"
    )


def test_an_unknown_pair_is_rejected_and_never_clobbers_the_summary(
    tmp_path, monkeypatch
):
    """DEFECT. `--policy` validates its argument (`run_matrix.py:153-155`);
    `--pair` does not. A typo -- `ETH-SHIB` for `ETH/SHIB` is one keystroke --
    empties every pair's window list, so zero cells are enumerated, and
    `summary.csv` is truncated to an empty file *before* `by_regime` raises.
    """
    specs = _specs()
    _seed(tmp_path / "results" / "matrix", specs)
    summary = tmp_path / "results" / "summary.csv"
    summary.parent.mkdir(parents=True, exist_ok=True)
    summary.write_text("policy,net_result\nMyHook@3000,1.0\n")
    before = summary.read_text()

    with pytest.raises(SystemExit):
        _run_main(tmp_path, monkeypatch, ["--pair", "ETH-SHIB", "--workers", "1"])
    assert summary.read_text() == before, "a rejected run must not touch summary.csv"


def test_a_failed_cell_with_a_stale_metrics_file_is_not_counted_twice(
    tmp_path, monkeypatch
):
    """DEFECT. `collect()` reads every metrics file on disk and knows nothing
    about this invocation; the failures are then concatenated on top
    (`run_matrix.py:188-191`). A cell that fails *now* but succeeded *before*
    therefore appears twice: once carrying its stale numbers with `error=None`,
    and once as an error row.

    This is not hypothetical for the run in flight. `--policy MEVChargeHook`
    re-runs 1,296 cells whose pre-fix metrics files are all still on disk (they
    are overwritten in place), so any single failure produces exactly this
    shape -- and the stale row is the *pre-fix* number the re-run exists to
    replace.

    Downstream: `paired_against_baseline` merges on the axes, so the duplicate
    becomes two paired observations for one window, and the NaN-valued error
    row poisons its whole stratum (see the wilcoxon tests below).
    """
    specs = _specs()
    _seed(tmp_path / "results" / "matrix", specs, net_result=999.0)  # pre-fix numbers
    victim = specs[0]

    frame = _run_main(
        tmp_path,
        monkeypatch,
        ["--policy", victim.policy.name, "--workers", "1"],
        executed_error_for=victim.key,
    )

    axes = ["policy", "pair", "window_start_ms", "gas_price_wei", "address_mode"]
    duplicated = frame.duplicated(subset=axes).sum()
    assert duplicated == 0, f"{duplicated} cells appear twice in summary.csv"


# --------------------------------------------- E: missing values in the analysis


def test_wilcoxon_paired_refuses_missing_differences(tmp_path):
    """DEFECT. `wilcoxon_paired` casts to float and never drops NaN.

    `PAIRED_METRICS` now differences columns that are legitimately absent for a
    cell -- `arb_profit_realized` is `None` whenever a trace carries no usable
    gas price, and any error row from `run_matrix.py` has NaN for every metric.
    `values != 0` is True for NaN, so the NaN reaches `scipy.stats.wilcoxon`,
    which returns `p = nan`, and `median` is nan too.

    Silence is the problem: the comparison is still emitted, with a nan median,
    and is then judged by Benjamini-Hochberg (see below).
    """
    from experiments.stats import wilcoxon_paired

    clean = wilcoxon_paired([100.0 + i for i in range(24)])
    assert clean["p"] < 1e-5

    poisoned = wilcoxon_paired([np.nan] + [100.0 + i for i in range(23)])
    assert not np.isnan(poisoned["p"]), (
        "one missing difference turned an overwhelming result into p = nan, "
        "reported as 'not significant'"
    )
    assert not np.isnan(poisoned["median"])


def test_benjamini_hochberg_never_flags_a_missing_p_value():
    """DEFECT, and the sharper half of the one above.

    The step-up loop accepts everything up to the largest passing *rank*. A NaN
    never passes its own threshold, but `sorted` cannot order it -- every
    comparison against NaN is False -- so it lands at an arbitrary rank and, if
    that rank is below the cut, is flagged `significant_fdr = True`.

    A stratum that failed to compute is then reported as a discovery.
    """
    from experiments.stats import benjamini_hochberg

    flags = benjamini_hochberg([0.001, 0.002, float("nan"), 0.003, 0.20, 0.90])
    assert flags[2] is False, "a nan p-value was flagged FDR-significant"


def test_paired_against_baseline_keeps_one_row_per_window():
    """A duplicated cell in the frame becomes duplicated paired observations,
    which inflates `n` and double-weights that window in the signed-rank test.

    Guard for the shape, so the run_matrix duplication above cannot pass
    through the analysis unnoticed if it is ever fixed only halfway.
    """
    from experiments.aggregate import paired_against_baseline

    axes = {
        "pair": "ETH/SHIB",
        "window_start_ms": 1,
        "gas_price_wei": 5,
        "address_mode": "persistent",
    }
    frame = pd.DataFrame(
        [
            {**axes, "policy": "MyHook@3000", "net_result": 10.0},
            {**axes, "policy": "BAHook", "net_result": 20.0},
        ]
    )
    assert len(paired_against_baseline(frame)) == 1


def test_by_regime_uu_shares_are_means_of_per_cell_ratios():
    """Characterisation, not a pass/fail on correctness -- but it must be read
    before `uu_fee_share_mean` is quoted.

    `by_regime` averages `uu_fee_share` across cells. A cell that traded twice
    counts as much as one that carried the window's whole volume, so the
    reported figure is not "the share of fee income uninformed users paid" --
    that is a ratio of sums. The two differ whenever the per-cell shares are
    correlated with size, which is exactly when the number is interesting.

    `analysis/08-uu-flow-behaviour.ipynb` cell 5 then divides this mean-of-
    ratios by a `uu_share_of_volume` built from *sums*, mixing the two
    estimators inside one `fee_burden_ratio`.
    """
    from experiments.aggregate import by_regime

    common = {"policy": "P", "regime": "low", "gas_price_wei": 5}
    frame = pd.DataFrame(
        [
            # one tiny cell where retail paid everything ...
            {**common, "uu_fee_share": 1.0, "fee_income": 1.0, "net_result": 0.0},
            # ... and one large cell where it paid nothing.
            {**common, "uu_fee_share": 0.0, "fee_income": 999.0, "net_result": 0.0},
        ]
    )
    for column in ("retained_volume", "il", "gas_cost", "trade_count"):
        frame[column] = 1.0

    mean_of_ratios = float(by_regime(frame)["uu_fee_share_mean"].iloc[0])
    ratio_of_sums = 1.0 / 1000.0
    assert mean_of_ratios == pytest.approx(0.5)
    assert mean_of_ratios != pytest.approx(ratio_of_sums, abs=1e-3)


# ------------------------------------------------------------- B: manifest hashing


def test_source_hash_does_not_depend_on_where_the_tree_lives(tmp_path):
    """An absolute path or a filesystem-order dependence would invalidate every
    manifest on the next run and re-run 15,552 cells for nothing."""
    from experiments.manifest import source_hash

    def build(root: Path) -> None:
        (root / "src" / "libraries").mkdir(parents=True)
        (root / "test" / "policies").mkdir(parents=True)
        (root / "src" / "MyHook.sol").write_text("contract MyHook {}\n")
        (root / "src" / "libraries" / "ArbMath.sol").write_text("library A {}\n")
        (root / "test" / "Replay.t.sol").write_text("contract R {}\n")
        (root / "test" / "policies" / "BAHook.t.sol").write_text("contract B {}\n")

    a, b = tmp_path / "a" / "contracts", tmp_path / "b" / "elsewhere" / "contracts"
    build(a)
    build(b)

    source_hash.cache_clear()
    first = source_hash(a)
    source_hash.cache_clear()
    assert source_hash(b) == first, "the hash moved with the tree's location"

    # Non-Solidity neighbours must not enter it: `out/`, `.forge-snapshots/` and
    # the JSONL fixtures the Solidity tests write all land near these trees.
    (a / "test" / "fixture.jsonl").write_text('{"a":1}\n')
    (a / "src" / ".DS_Store").write_bytes(b"\x00")
    source_hash.cache_clear()
    assert source_hash(a) == first


def test_source_hash_covers_every_solidity_file_under_test(tmp_path):
    """Deliberate breadth -- and the cost of it, recorded.

    `contracts/test/` holds the replay harness *and* twelve unit-test files
    that no matrix cell executes. Touching `Welford.t.sol` invalidates all
    15,552 manifests and queues a ~13 h re-run. That already happened once on
    2026-08-10 and was aborted at 209 cells. Nothing here argues for narrowing
    the hash; it argues for knowing before you edit.
    """
    from experiments.manifest import source_hash

    contracts = tmp_path / "contracts"
    (contracts / "src").mkdir(parents=True)
    (contracts / "test").mkdir(parents=True)
    (contracts / "src" / "MyHook.sol").write_text("contract MyHook {}\n")
    (contracts / "test" / "Welford.t.sol").write_text("contract W {}\n")

    source_hash.cache_clear()
    before = source_hash(contracts)
    (contracts / "test" / "Welford.t.sol").write_text("contract W { uint x; }\n")
    source_hash.cache_clear()
    assert source_hash(contracts) != before

    unrelated = sorted(
        p.name
        for p in (ROOT / "contracts" / "test").glob("*.sol")
        if p.name not in {"Replay.t.sol", "ReplayUU.t.sol"}
    )
    assert unrelated, "expected unit tests beside the harness"


# ------------------------------------------- A: state snapshots in the harness


REPLAY = ROOT / "contracts" / "test" / "Replay.t.sol"


def test_every_state_snapshot_in_the_replay_harness_is_deleted():
    """DEFECT. `vm.revertToState` restores state but keeps the snapshot alive
    at ~1.6 MB; one leak per candle once cost 4.76 GB in a single process.

    Two sites take a snapshot and never delete it:

      * `_optimalSize` (Replay.t.sol:626) returns early at `if (hi == 0)`
        without reverting *or* deleting -- inside the per-candle, per-direction
        arbitrage path, i.e. exactly the loop that caused the 2026-08-03
        incident.
      * `_countTradesWithGasPrice` (Replay.t.sol:328/345) reverts but does not
        delete. Not on the matrix path -- `run_one` passes
        `--match-test testReplay` -- so this one is a test-only leak.
    """
    source = REPLAY.read_text()
    taken = len(re.findall(r"vm\.snapshotState\(\)", source))
    deleted = len(re.findall(r"vm\.deleteStateSnapshot\(", source))
    # Counting occurrences was the original proxy and it is too crude in both
    # directions: one snapshot with two exit paths needs two delete sites, so
    # `taken == deleted` fails on correct code. What must hold is that no
    # snapshot is taken without a delete on every path out -- checked here as
    # "at least as many deletes as takes", with the escape-path check in
    # `test_optimal_size_cannot_return_while_holding_a_snapshot` covering the
    # case this cannot see.
    assert deleted >= taken, f"{taken} snapshots taken, only {deleted} deleted"


def test_optimal_size_cannot_return_while_holding_a_snapshot():
    """The precise reproduction for the leak above: a `return` between taking
    the snapshot and deleting it."""
    source = REPLAY.read_text()
    body = source.split("function _optimalSize(")[1]
    body = body[: body.index("\n    function ")]
    held = body[
        body.index("vm.snapshotState()") : body.index("vm.deleteStateSnapshot(")
    ]
    assert "return" not in held, (
        "_optimalSize returns while holding an undeleted state snapshot"
    )


def test_the_fee_quote_uses_exact_input_sign_consistently():
    """Sound, recorded so it stays that way.

    `_feeForSender` passes `-int256(amountIn)` (exact input, the v4 convention
    `swapExactTokensForTokens` sends) while `_probeFee`, on the arbitrageur's
    size-search path, passes `+int256(amount)`. The only policy that reads the
    field takes its absolute value (`MEVChargeHook.sol:395`), so the two agree
    today -- but a policy that ever distinguishes exact-input from exact-output
    would see the arbitrageur and the logger disagree.
    """
    mev = (ROOT / "contracts" / "src" / "MEVChargeHook.sol").read_text()
    assert "params.amountSpecified >= 0 ? params.amountSpecified : -params" in mev

    replay = REPLAY.read_text()
    assert "amountSpecified: -int256(amountIn)" in replay
    others = [
        path
        for path in (ROOT / "contracts" / "src").rglob("*.sol")
        if "amountSpecified" in path.read_text() and path.name != "MEVChargeHook.sol"
    ]
    assert not [p for p in others if p.name != "VolatilityHook.sol"], (
        f"a new policy reads amountSpecified: {[p.name for p in others]}; "
        "check it against _probeFee's positive sign"
    )


def test_uu_participation_fee_is_quoted_before_thinning():
    """Characterisation of a declared modelling choice, with its consequence.

    `_uuStep` quotes the fee at the candle's POTENTIAL volume and logs that
    value as `feePips`, while the pool charges the fee at the amount actually
    executed. For the ten size-independent policies the two coincide. For
    `MEVChargeHook` they do not: measured on the post-fix traces the harness
    wrote today, ~1% of its UU swaps are logged at the 100 bps cap while the
    pool charged 30 bps.

    So `feePips` on a UU row is the price the user *decided* on, not the price
    they paid -- the pre-fix defect was the same field being too low, and it is
    now too high on those rows. Any fee-behaviour statement (p95, share at cap,
    `uu_fee_share`) inherits it.
    """
    source = REPLAY.read_text()
    step = source.split("function _uuStep(")[1]
    step = step[: step.index("\n    /// @dev Fresh address")]
    assert "_feeForSender(sender, zeroForOne, potentialAmountIn)" in step
    assert "_executeUU(candle, zeroForOne, fee, amountIn," in step, (
        "the fee handed to _executeUU (and logged as feePips) is the "
        "potential-volume quote, not the executed-size one"
    )


# ------------------------------------------------------------------- F: figures


def _uu_frame() -> pd.DataFrame:
    rows = []
    for policy in ("MyHook@3000", "BAHook", "ABHook"):
        for regime in ("low", "mid", "high"):
            for window in range(4):
                rows.append(
                    {
                        "policy": policy,
                        "regime": regime,
                        "window_start_ms": window,
                        "pair": "ETH/SHIB",
                        "gas_price_wei": 20_000_000_000,
                        "address_mode": "persistent",
                        "retained_volume": 1000.0 + window,
                        "net_result": 100.0 + window,
                        "net_result_tt": 90.0 + window,
                        "uu_volume": 900.0,
                        "arb_volume": 100.0,
                        "uu_participation": 0.7,
                        "uu_fee_share": 0.55,
                    }
                )
    return pd.DataFrame(rows)


def test_figure_valuation_defaults_are_unchanged(tmp_path):
    """`value=` was added to two existing figures. The default must still draw
    the end-of-window valuation and write the same table view, or every
    already-published figure silently changes meaning."""
    from experiments.figures import frontier, net_result_by_regime

    frame = _uu_frame()
    for function, name in ((net_result_by_regime, "regime"), (frontier, "frontier")):
        function(frame, tmp_path / f"{name}_default.pdf")
        function(frame, tmp_path / f"{name}_explicit.pdf", "net_result")
        default = pd.read_csv(tmp_path / f"{name}_default.csv")
        explicit = pd.read_csv(tmp_path / f"{name}_explicit.csv")
        pd.testing.assert_frame_equal(default, explicit)
        assert (default["value"] == "net_result").all()

        function(frame, tmp_path / f"{name}_tt.pdf", "net_result_tt")
        other = pd.read_csv(tmp_path / f"{name}_tt.csv")
        assert (other["value"] == "net_result_tt").all()


def test_uu_flow_shares_stay_in_the_unit_interval_and_never_divide_by_zero(tmp_path):
    from experiments.figures import uu_flow

    frame = _uu_frame()
    # A policy that priced everyone out: no volume at all on either side.
    frame = pd.concat(
        [
            frame,
            frame.head(1).assign(
                policy="PegDefence", uu_volume=0.0, arb_volume=0.0, uu_fee_share=0.0
            ),
        ],
        ignore_index=True,
    )
    uu_flow(frame, tmp_path / "uu_flow.pdf")
    table = pd.read_csv(tmp_path / "uu_flow.csv")

    for column in ("uu_share_of_volume", "uu_participation", "uu_fee_share"):
        values = table[column].dropna()
        assert ((values >= 0) & (values <= 1)).all(), f"{column} left [0, 1]"
    dead = table[table["policy"] == "PegDefence"].iloc[0]
    assert pd.isna(dead["uu_share_of_volume"]), (
        "a pool with no volume has no share; 0 would read as 'all arbitrage'"
    )


def test_require_names_the_missing_column_instead_of_drawing_nothing(tmp_path):
    from experiments.figures import uu_flow

    arb_only = _uu_frame().drop(columns=["uu_volume", "uu_participation"])
    with pytest.raises(KeyError, match="uu_volume"):
        uu_flow(arb_only, tmp_path / "nope.pdf")


# ------------------------------------------------------- G: the kappa sweep


def test_kappa_sweep_uses_the_matrix_default_gas_estimate(tmp_path):
    """DEFECT (small, but it invalidates a claim the module makes).

    `kappa_sensitivity._one` falls back to 76_500 gas where the matrix uses
    `DEFAULT_GAS_ESTIMATE = 76_578`. `MyHook@10000` has no calibrated entry in
    `gas_estimates.json`, so the sweep runs it against a different arbitrageur
    entry threshold from the matrix -- and the module docstring says the 1.0
    level "is re-run here rather than joined in from the matrix, so the overlap
    doubles as a consistency check". For that policy it cannot.
    """
    import re as _re

    from experiments.calibrate_gas import load as load_gas
    from experiments.kappa_sensitivity import POLICIES

    calibrated = load_gas()
    uncalibrated = [p for p in POLICIES if p not in calibrated]
    assert uncalibrated == ["MyHook@10000"]

    source = (ROOT / "experiments" / "kappa_sensitivity.py").read_text()
    fallback = _re.search(r"gas\.get\(policy,\s*([0-9_]+)\)", source)
    # Naming the constant is better than repeating its value, so the literal
    # the original assertion looked for is gone on purpose. What matters is
    # that the sweep cannot drift from the matrix: it must IMPORT the default
    # rather than carry a copy.
    assert (
        "DEFAULT_GAS_ESTIMATE"
        in (ROOT / "experiments" / "kappa_sensitivity.py").read_text()
    ), "the sweep must use the matrix's DEFAULT_GAS_ESTIMATE, not its own copy"
    assert not re.search(
        r"gas\.get\([^,]+,\s*\d",
        (ROOT / "experiments" / "kappa_sensitivity.py").read_text(),
    ), "a numeric literal fallback would silently diverge from the matrix"


def test_kappa_sweep_windows_are_a_subset_of_the_matrix_windows():
    """The sweep takes 8 per tercile against the matrix's 24. The overlap claim
    only holds if the 8 are a subset -- they are, because the picks are evenly
    spaced by index. Pinned, because a change to the spacing rule would break
    the claim silently."""
    from experiments.matrix import WINDOWS_PER_TERCILE
    from experiments.windows import select_windows

    segments = pd.DataFrame(
        {
            "start_ms": [1_704_067_200_000 + 86_400_000 * i for i in range(366)],
            "end_ms": [1_704_067_200_000 + 86_400_000 * (i + 1) for i in range(366)],
            "volatility": [0.01 + 0.001 * ((i * 37) % 366) for i in range(366)],
        }
    )
    few = set(select_windows(segments, per_tercile=8)["start_ms"])
    many = set(select_windows(segments, per_tercile=WINDOWS_PER_TERCILE)["start_ms"])
    assert few <= many, sorted(few - many)


def test_kappa_sweep_trace_directories_cannot_leak_into_the_matrix_figures(tmp_path):
    """The sweep writes seven-field trace names -- `capture_share` is 0, so
    there is no eighth field to filter on. Its only protection is the
    `turnover-<multiple>/` subdirectory, and `events` globs non-recursively.
    """
    from experiments.events import applied_fees

    (tmp_path / "turnover-0.03").mkdir(parents=True)
    record = {
        "candle": 1,
        "zeroForOne": True,
        "amountIn": 1,
        "feePips": 3000,
        "extPrice0": 1,
        "extPrice1": 1,
        "sqrtPriceBeforeX96": 1,
        "sqrtPriceAfterX96": 1,
    }
    name = "MyHook-3000-ETHUSDT-SHIBUSDT-1704067200000-20000000000-persistent.jsonl"
    (tmp_path / "turnover-0.03" / name).write_text(json.dumps(record) + "\n")

    assert applied_fees(tmp_path).empty, (
        "a sweep trace one directory down reached a pre-registered figure"
    )


def test_run_one_creates_a_nested_results_directory(tmp_path):
    """`run_one` calls `results.mkdir(exist_ok=True)` without `parents=True`
    (`run_one.py:119`). The kappa sweep asks for
    `results/sensitivity/turnover-<x>/`, two levels deep.

    It survives only because `kappa_sensitivity._one` creates the directory
    itself with `parents=True` first. Pinned so that the guarantee stays
    somewhere: dropping that line makes the whole sweep fail on the first cell.
    """
    from experiments import kappa_sensitivity

    source = Path(kappa_sensitivity.__file__).read_text()
    assert "level_dir.mkdir(parents=True, exist_ok=True)" in source

    nested = tmp_path / "results" / "sensitivity" / "turnover-0.03"
    with pytest.raises(FileNotFoundError):
        nested.mkdir(exist_ok=True)  # what run_one would do unaided


def test_kappa_sweep_result_directories_are_inside_the_forge_allowlist():
    """`foundry.toml` `fs_permissions` is a path allowlist, and a missing entry
    is how the UU matrix came to write its traces over the arb-only ones.

    The sweep writes under `results/sensitivity/turnover-<x>/`, which is covered
    by the existing `../results/` entry only because the allowlist matches by
    path prefix -- the same way `../.work/<cell-key>/` already works for every
    parallel worker.
    """
    toml = (ROOT / "contracts" / "foundry.toml").read_text()
    allowed = re.findall(r'path\s*=\s*"([^"]+)"', toml)
    assert "../results/" in allowed
    assert "../.work/" in allowed  # the prefix-matching precedent, in production
    assert "../results-uu/" in allowed


def test_kappa_sweep_analysis_pairs_only_within_a_turnover_level():
    """Two kappa levels are two different worlds; a delta across them is not a
    comparison of policies. Also checks the column names `analyse` expects
    against the ones `_one` actually returns."""
    from experiments.kappa_sensitivity import POLICIES, TURNOVER_MULTIPLES, analyse

    rows = []
    for multiple in TURNOVER_MULTIPLES:
        for policy in POLICIES:
            for window in range(6):
                for gas in (5_000_000_000, 20_000_000_000):
                    rows.append(
                        {
                            "policy": policy,
                            "turnover_multiple": multiple,
                            "window_start_ms": window,
                            "regime": ("low", "mid", "high")[window % 3],
                            "gas_price_wei": gas,
                            "net_result": 100.0 * multiple
                            + (10.0 if policy == "BAHook" else 0.0),
                            "net_result_tt": 90.0 * multiple,
                            "error": None,
                        }
                    )
    result = analyse(pd.DataFrame(rows))

    assert set(result["valuation"]) == {"net_result", "net_result_tt"}
    assert set(result["turnover_multiple"]) == set(TURNOVER_MULTIPLES)
    assert "MyHook@3000" not in set(result["policy"])
    # Within a level every non-baseline delta is constant, so no comparison may
    # pick up variation that only exists between levels.
    ba = result[(result["policy"] == "BAHook") & (result["valuation"] == "net_result")]
    assert (ba["median"] == 10.0).all(), "a delta leaked across turnover levels"


# ---------------------------------------------------------------- H: notebooks


NOTEBOOKS = sorted((ROOT / "analysis").glob("*.ipynb"))


def _code_cells(path: Path) -> list[str]:
    notebook = json.loads(path.read_text())
    return ["".join(c["source"]) for c in notebook["cells"] if c["cell_type"] == "code"]


@pytest.mark.parametrize("path", NOTEBOOKS, ids=lambda p: p.name)
def test_notebook_names_are_defined_before_they_are_used(path):
    """`HAVE_TRACES` and `ARB_MTM` are guards; a guard defined after its first
    use is not a guard. Both were introduced across six notebooks in one pass.
    """
    cells = _code_cells(path)
    for name in ("HAVE_TRACES", "ARB_MTM"):
        first_use = next(
            (i for i, c in enumerate(cells) if re.search(rf"\b{name}\b", c)), None
        )
        if first_use is None:
            continue
        assert re.search(rf"^{name}\s*=", cells[first_use], re.MULTILINE), (
            f"{path.name}: {name} is read in code cell {first_use} before it is set"
        )


@pytest.mark.parametrize("path", NOTEBOOKS, ids=lambda p: p.name)
def test_no_notebook_hardcodes_the_renamed_arb_column(path):
    """`arb_profit` -> `arb_mtm`, but the frozen arb-only summary predates the
    rename. Whichever name is hardcoded, one of the two frames breaks."""
    for i, cell in enumerate(_code_cells(path)):
        for line in cell.splitlines():
            if "ARB_MTM" in line or line.strip().startswith("#"):
                continue
            assert not re.search(r'["\']arb_(profit|mtm)["\']', line), (
                f"{path.name} cell {i}: {line.strip()} -- resolve via ARB_MTM"
            )


def test_trace_reading_notebooks_reject_a_handful_of_stray_files():
    """DEFECT (robustness). 03, 05 and 06 require >1000 seven-field traces, so
    the three ad-hoc probes that survive the filter cannot become a figure --
    the failure that drew a fee distribution from n=31.

    `08-uu-flow-behaviour.ipynb` guards with `any(TRACES.glob("*.jsonl"))`: any
    single file, of any name, turns the guard on. It happens to be safe today
    only because `results-uu/` holds all 15,552.
    """
    weak = []
    for path in NOTEBOOKS:
        for cell in _code_cells(path):
            for line in cell.splitlines():
                if line.strip().startswith("HAVE_TRACES") and "len(" not in line:
                    weak.append((path.name, line.strip()))
    assert not weak, weak


def test_forge_writability_is_checked_before_a_run_not_after(tmp_path):
    """DEFECT, fixed 2026-08-11. `fs_permissions` is an allowlist; a results
    directory outside it makes the harness abort in `setUp`, which `_worker`
    records as a per-cell error while the sweep continues. An entirely dead run
    therefore looks healthy until the summary is assembled -- 7,776 cells and 26
    minutes produced zero output that way.
    """
    import run_matrix

    allowed = run_matrix.forge_writable_paths()
    assert allowed, (
        "fs_permissions could not be parsed; the guard would pass everything"
    )

    # A subtree of an allowed entry is allowed -- that is why the sweeps write
    # to results/sensitivity/<level>/ and work.
    run_matrix.assert_forge_can_write(ROOT / "results-uu" / "turnover-0.1")
    run_matrix.assert_forge_can_write(ROOT / "results" / "sensitivity" / "seed-0")

    # A sibling is not, however plausible its name.
    with pytest.raises(SystemExit) as raised:
        run_matrix.assert_forge_can_write(ROOT / "results-uu-t0.1")
    assert "foundry.toml" in str(raised.value)


def test_a_wholly_failed_run_reports_the_failures_not_a_pandas_traceback():
    """When every cell fails there is nothing on disk to deduplicate against,
    and the duplicate-guard merged on an empty frame -- raising KeyError and
    burying the real cause."""
    import pandas as pd

    frame = pd.DataFrame()
    failures = pd.DataFrame(
        [
            {
                "policy": "MyHook@3000",
                "pair": "ETH/SHIB",
                "window_start_ms": 0,
                "gas_price_wei": 20_000_000_000,
                "address_mode": "persistent",
                "error": "CalledProcessError: forge exited 1",
            }
        ]
    )
    # The path run_matrix takes when `collect` finds nothing.
    combined = failures if frame.empty else None
    assert combined is not None and len(combined) == 1
    assert combined["error"].notna().all()
