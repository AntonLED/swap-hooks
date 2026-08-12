from pathlib import Path

import pandas as pd

from experiments.matrix import (
    ADDRESS_MODES,
    GAS_SCENARIOS_WEI,
    PAIRS,
    WINDOWS_PER_TERCILE,
    enumerate_runs,
    execute,
    manifest_for,
)
from experiments.policies import ALL


def _windows(n=3 * WINDOWS_PER_TERCILE):
    return {
        p.name: [
            {
                "start_ms": i * 86_400_000,
                "end_ms": (i + 1) * 86_400_000,
                "regime": ("low", "mid", "high")[i % 3],
            }
            for i in range(n)
        ]
        for p in PAIRS
    }


def test_matrix_has_the_expected_cardinality():
    specs = enumerate_runs(_windows())
    per_pair = 3 * WINDOWS_PER_TERCILE  # three terciles
    expected = (
        len(ALL) * len(ADDRESS_MODES) * len(PAIRS) * per_pair * len(GAS_SCENARIOS_WEI)
    )
    # Derived, not hardcoded: pinning the total to 4752 only recorded how many
    # policies existed on the day it was written, and adding one made the test
    # fail for a reason unrelated to what it checks -- that the product of the
    # axes is what the enumeration produces.
    assert len(specs) == expected


def test_every_axis_is_fully_covered():
    specs = enumerate_runs(_windows())
    assert len({s.gas_price_wei for s in specs}) == 3
    # Derived from the constant, not pinned at 2: the address axis was reduced
    # to one mode on 2026-08-10 because `fresh` and `persistent` agreed to the
    # last bit in all 7,776 paired cells of the UU matrix. Pinning the number
    # here would only have recorded how many modes existed the day it was
    # written -- the same mistake the cardinality test above already fixed.
    assert len({s.address_mode for s in specs}) == len(ADDRESS_MODES)
    assert len({s.pair.name for s in specs}) == 3
    assert len({s.policy.name for s in specs}) == len(ALL)
    # Every policy must appear against every pair, or a gap would hide as a
    # smaller-but-still-plausible cell count.
    for policy in ALL:
        pairs = {s.pair.name for s in specs if s.policy.name == policy.name}
        assert len(pairs) == len(PAIRS), f"{policy.name} is missing a pair"


def test_run_keys_are_unique():
    """A collision would silently overwrite one run's results with another's."""
    specs = enumerate_runs(_windows())
    assert len({s.key for s in specs}) == len(specs)


def test_enumeration_is_deterministic():
    a = [s.key for s in enumerate_runs(_windows())]
    b = [s.key for s in enumerate_runs(_windows())]
    assert a == b


def test_completed_runs_are_skipped(tmp_path):
    calls = []

    def runner(spec):
        calls.append(spec)
        return {"trade_count": 1, "conservation_error_token0": 0.0}

    specs = enumerate_runs(_windows())[:3]
    manifest_for = lambda s: {"key": s.key}

    execute(specs, tmp_path, runner, manifest_for=manifest_for)
    first_pass = len(calls)
    execute(specs, tmp_path, runner, manifest_for=manifest_for)

    assert len(calls) == first_pass, "a matching manifest must short-circuit"


def test_a_failing_run_does_not_abort_the_matrix(tmp_path):
    """The stable pair may legitimately produce nothing; one dead cell must not
    take the rest of the sweep with it."""

    def runner(spec):
        if spec.pair.name == "USDC/USDT":
            raise RuntimeError("no flow")
        return {"trade_count": 1, "conservation_error_token0": 0.0}

    # Pick specs by pair rather than slicing the front of the list: the order is
    # policy, mode, pair, window, gas, so a fixed-size prefix stops covering the
    # stable pair as soon as the window count grows, and the test then passes
    # for the wrong reason.
    specs = enumerate_runs(_windows())
    stable = [s for s in specs if s.pair.name == "USDC/USDT"][:5]
    healthy = [s for s in specs if s.pair.name != "USDC/USDT"][:5]

    frame = execute(stable + healthy, tmp_path, runner)

    assert "error" in frame.columns
    assert frame["error"].notna().any(), "failures must be recorded"
    assert frame["error"].isna().any(), "healthy runs must still be recorded"


def test_every_row_carries_the_axes_needed_to_group_it(tmp_path):
    frame = execute(
        enumerate_runs(_windows())[:5],
        tmp_path,
        lambda s: {"trade_count": 0},
    )
    for column in (
        "policy",
        "pair",
        "regime",
        "gas_price_wei",
        "address_mode",
        "window_start_ms",
    ):
        assert column in frame.columns


# ------------------------------------------------------------------ UU plumbing
# 2026-08-09-uu-flow.md Task 7. `manifest_for`'s "S" field and `run_one`'s
# subprocess env are the resume key and the harness interface respectively;
# both must be inert when UU is off and carry the five new fields when on.


def test_manifest_for_includes_uu_fields_only_when_enabled(monkeypatch):
    from experiments import run_one as run_one_mod

    monkeypatch.setattr(run_one_mod, "kappa_for_pair", lambda s0, s1: 42.0)
    # The synthetic windows here have no market data behind them, and this test
    # is about which UU fields reach the manifest -- not about the fingerprint.
    monkeypatch.setattr(
        run_one_mod, "window_fingerprint", lambda *a: ("deadbeefdeadbeef", 1, 2)
    )

    spec = enumerate_runs(_windows())[0]

    off = manifest_for(spec)
    on = manifest_for(spec, uu_mode="share")

    for key in ("uu_mode", "uu_lambda_wad", "uu_kappa", "uu_seed", "uu_sigma"):
        assert key not in off["S"], f"{key} must be absent when UU is off"
        assert key in on["S"], f"{key} must be present when UU is on"
    assert on["S"]["uu_mode"] == "share"
    assert on["S"]["uu_kappa"] == 42.0


def test_run_one_uu_off_passes_no_uu_trace_env(tmp_path, monkeypatch):
    """Mode "off" must produce byte-identical env to today: no UU_TRACE key at
    all, not even an empty one."""
    from experiments import run_one as run_one_mod

    frame = pd.DataFrame({"open_time": [0, 60_000], "close": [3000.0, 3000.0]})
    monkeypatch.setattr(run_one_mod, "fetch_klines", lambda *a, **kw: frame)
    monkeypatch.setattr(run_one_mod, "read_events", lambda path: (pd.DataFrame(), {}))
    monkeypatch.setattr(run_one_mod, "compute", lambda *a, **kw: {"trade_count": 0})

    captured = {}

    def fake_run(cmd, cwd=None, check=None, capture_output=None, env=None):
        captured["env"] = env

        class Result:
            pass

        return Result()

    monkeypatch.setattr(run_one_mod.subprocess, "run", fake_run)

    run_one_mod.run_one(
        "MyHook",
        "ETHUSDT",
        "SHIBUSDT",
        0,
        60_000,
        work_dir=tmp_path,
        results_dir=tmp_path,
        uu_mode="off",
    )

    assert "UU_TRACE" not in captured["env"]
    assert "UU_MODE" not in captured["env"]
    assert "UU_LAMBDA_WAD" not in captured["env"]


def test_collect_describes_the_whole_matrix_not_only_what_just_ran(tmp_path):
    """`summary.csv` must cover every cell on disk, however little was re-run.

    It was built from the runner's return value, so `--pair ETH/SHIB` -- or any
    other restriction -- truncated the file every notebook reads to the subset,
    while the other two thirds of the matrix sat on disk unmentioned.
    """
    import json

    from experiments.matrix import collect

    specs = enumerate_runs(_windows())[:6]
    for spec in specs[:4]:  # only four of the six have been computed
        (tmp_path / f"{spec.key}.metrics.json").write_text(
            json.dumps({"net_result": 1.0, "trade_count": 2})
        )

    frame = collect(specs, tmp_path)

    assert len(frame) == 4, "a cell without metrics is absent, not invented"
    assert {"policy", "pair", "regime", "gas_price_wei", "address_mode"} <= set(
        frame.columns
    )
    assert set(frame["net_result"]) == {1.0}


def test_collect_ignores_manifests_entirely(tmp_path):
    """Whether a cell is up to date is the runner's question. This one only
    asks what has been computed, so a stale manifest cannot hide a result."""
    import json

    from experiments.matrix import collect

    spec = enumerate_runs(_windows())[0]
    (tmp_path / f"{spec.key}.metrics.json").write_text(json.dumps({"net_result": 3.0}))
    # No manifest written at all.

    assert len(collect([spec], tmp_path)) == 1


def test_run_spec_writes_traces_beside_the_metrics_it_is_asked_for(monkeypatch):
    """The event traces must land in the same experiment's directory.

    They did not. `run_spec` never passed a `results_dir`, so `run_one` fell
    back to its default `results/` and the UU matrix wrote 15,552 traces over
    the arb-only experiment's, under byte-identical seven-field filenames.
    `results-uu/matrix/` held the metrics; `results/` held somebody else's
    traces. Nothing failed, and the two experiments' trace-level analyses
    silently swapped inputs.
    """
    from experiments import matrix as matrix_mod

    captured = {}

    def fake_run_one(*args, **kwargs):
        captured["results_dir"] = kwargs.get("results_dir")
        return {"trade_count": 0}

    monkeypatch.setattr("experiments.run_one.run_one", fake_run_one)
    spec = enumerate_runs(_windows())[0]

    matrix_mod.run_spec(spec, {}, results_dir=Path("results-uu"))

    assert captured["results_dir"] == Path("results-uu")


def test_run_spec_without_a_results_dir_leaves_the_default_alone(monkeypatch):
    """Not passing one must stay indistinguishable from before, or every
    frozen arb-only path changes meaning at once."""
    from experiments import matrix as matrix_mod

    captured = {}
    monkeypatch.setattr(
        "experiments.run_one.run_one",
        lambda *a, **kw: (
            captured.setdefault("results_dir", kw.get("results_dir"))
            or {"trade_count": 0}
        ),
    )
    spec = enumerate_runs(_windows())[0]

    matrix_mod.run_spec(spec, {})

    assert captured["results_dir"] is None


def test_kappa_for_pair_is_cached_and_differs_across_pairs(monkeypatch):
    from experiments import run_one as run_one_mod

    calls = []

    def fake_fetch(symbol, start_ms, end_ms, data, with_volume=False):
        calls.append(symbol)
        vol = 100.0 if symbol == "ETHUSDT" else 50.0
        n = 10
        return pd.DataFrame(
            {
                "open_time": [i * 60_000 for i in range(n)],
                "close": 1.0,
                "quote_volume": vol,
            }
        )

    monkeypatch.setattr(run_one_mod, "fetch_klines", fake_fetch)
    run_one_mod.kappa_for_pair.cache_clear()

    k1 = run_one_mod.kappa_for_pair("ETHUSDT", "SHIBUSDT")
    calls_after_first = len(calls)
    k2 = run_one_mod.kappa_for_pair("ETHUSDT", "SHIBUSDT")
    assert k1 == k2
    assert len(calls) == calls_after_first, "the second call must be served from cache"

    k3 = run_one_mod.kappa_for_pair("USDCUSDT", "SHIBUSDT")
    assert k3 != k1, "different volume profiles must give different kappa"


def test_turnover_reaches_the_manifest_so_two_configurations_cannot_collide(
    monkeypatch,
):
    """Two operating points differ only in kappa. If the manifest did not record
    it, their cells would share a resume key and the second configuration would
    be skipped as already-done -- silently reporting the first one's numbers."""
    from experiments import matrix as matrix_mod
    from experiments import run_one as run_one_mod

    monkeypatch.setattr(run_one_mod, "kappa_for_pair", lambda s0, s1: 0.05)
    monkeypatch.setattr(
        run_one_mod, "window_fingerprint", lambda *a: ("deadbeefdeadbeef", 1, 2)
    )
    spec = enumerate_runs(_windows())[0]

    headline = matrix_mod.manifest_for(spec, {}, "discrete", 1.0)
    second = matrix_mod.manifest_for(spec, {}, "discrete", 0.1)

    assert headline["S"]["uu_kappa"] != second["S"]["uu_kappa"]
    assert second["S"]["uu_turnover"] == 0.1
    assert headline != second


def test_run_spec_leaves_kappa_alone_at_the_headline_turnover(monkeypatch):
    """1.0x must pass None, not a recomputed product: the headline matrix has
    already run, and a float round-trip that changed kappa by one ulp would
    invalidate all 7,776 of its manifests."""
    from experiments import matrix as matrix_mod

    captured = {}
    monkeypatch.setattr(
        "experiments.run_one.run_one",
        lambda *a, **kw: captured.setdefault("uu_kappa", kw.get("uu_kappa"))
        or {"trade_count": 0},
    )
    matrix_mod.run_spec(enumerate_runs(_windows())[0], {}, uu_mode="discrete")

    assert captured["uu_kappa"] is None
