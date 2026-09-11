"""A pinned full window.

The run is deterministic by design (spec §7.5): arbitrage-only flow with sizes
fixed by optimisation leaves no randomness anywhere. So any drift here is a real
change in behaviour, not noise, and the tolerance is floating-point only.

Marked slow: it drives 1440 candles through Forge.
"""

import json
from pathlib import Path

import pytest

from experiments.run_one import run_one

GOLDEN = Path("tests/golden/eth-shib-2024-01-01-myhook-3000.json")
# UU flow (2026-08-09-uu-flow-design.md), share mode, canonical
# lambda = ln(2)/0.003 * 1e18 = 231_049_060_186_648_440_000 (experiments.uu.UU_LAMBDA_WAD),
# kappa = kappa_for_pair("ETHUSDT", "SHIBUSDT") over the 2024 calibration year
# (spec §3) -- both fixed inputs to this pin, not asserted by the test itself
# since they are covered independently by tests/test_uu.py and the
# kappa_for_pair cache test in tests/test_matrix.py.
UU_GOLDEN = Path("tests/golden/eth-shib-2024-01-01-myhook-3000-uu.json")
DAY_MS = 1440 * 60_000
JAN_2024 = 1_704_067_200_000


@pytest.mark.slow
def test_a_full_window_reproduces_the_golden_result():
    expected = json.loads(GOLDEN.read_text())
    actual = run_one(
        "MyHook", "ETHUSDT", "SHIBUSDT", JAN_2024, JAN_2024 + DAY_MS, fee_pips=3000
    )

    assert set(actual) == set(expected), "the metric set itself changed"
    for key, value in expected.items():
        assert actual[key] == pytest.approx(value, rel=1e-9, abs=1e-12), (
            f"{key} drifted"
        )


@pytest.mark.slow
def test_uu_off_reproduces_the_golden_result_bit_for_bit():
    """Spec §10.2, the differential golden: `uu_mode="off"` explicitly passed
    must be exactly as inert as never passing it at all -- the UU code path
    added to the harness is a no-op when off."""
    expected = json.loads(GOLDEN.read_text())
    actual = run_one(
        "MyHook",
        "ETHUSDT",
        "SHIBUSDT",
        JAN_2024,
        JAN_2024 + DAY_MS,
        fee_pips=3000,
        uu_mode="off",
    )

    assert set(actual) == set(expected), "the metric set itself changed"
    for key, value in expected.items():
        assert actual[key] == pytest.approx(value, rel=1e-9, abs=1e-12), (
            f"{key} drifted"
        )


@pytest.mark.slow
def test_uu_share_mode_reproduces_the_uu_golden_result():
    """Spec §10.6: a new golden with UU flow pinned, same window and policy as
    the arb-only golden above, so the two are directly comparable."""
    expected = json.loads(UU_GOLDEN.read_text())
    actual = run_one(
        "MyHook",
        "ETHUSDT",
        "SHIBUSDT",
        JAN_2024,
        JAN_2024 + DAY_MS,
        fee_pips=3000,
        uu_mode="share",
    )

    assert set(actual) == set(expected), "the metric set itself changed"
    for key, value in expected.items():
        assert actual[key] == pytest.approx(value, rel=1e-9, abs=1e-12), (
            f"{key} drifted"
        )


@pytest.mark.slow
def test_the_same_window_run_twice_is_identical():
    """Determinism is a property of the design, not an accident. If this fails,
    something in the path is reading a clock or a random source."""
    first = run_one(
        "MyHook", "ETHUSDT", "SHIBUSDT", JAN_2024, JAN_2024 + DAY_MS, fee_pips=3000
    )
    second = run_one(
        "MyHook", "ETHUSDT", "SHIBUSDT", JAN_2024, JAN_2024 + DAY_MS, fee_pips=3000
    )

    assert first == second
