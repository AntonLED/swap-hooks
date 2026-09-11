"""The gas estimate is the arbitrageur's entry threshold, so it must be right.

An earlier placeholder of 180,000 suppressed roughly twice as many trades as
reality. These pin the properties that make the calibrated figures believable.
"""

import json
from pathlib import Path

import pytest

from experiments.policies import ALL, INTRINSIC_GAS

ESTIMATES = Path("experiments/gas_estimates.json")


@pytest.fixture(scope="module")
def estimates():
    if not ESTIMATES.exists():
        pytest.skip("run `uv run python -m experiments.calibrate_gas` first")
    return json.loads(ESTIMATES.read_text())


def test_every_calibrated_name_is_a_known_policy(estimates):
    known = {p.name for p in ALL}
    assert set(estimates) <= known, "an estimate exists for something not under test"


def test_a_constant_fee_is_the_cheapest_hook(estimates):
    """Reading two oracle feeds costs more than returning a stored number. If
    this inverts, the harness is measuring something other than the swap."""
    baseline = min(v for k, v in estimates.items() if k.startswith("MyHook@"))
    for name in ("BAHook", "VolatilityHook", "PegCapture"):
        if name in estimates:
            assert estimates[name] > baseline, (
                f"{name} should cost more than a constant fee"
            )


def test_estimates_include_the_intrinsic_cost(estimates):
    """Execution gas measured inside the EVM excludes the 21,000 every
    transaction pays, but the arbitrageur does not."""
    assert all(v > INTRINSIC_GAS for v in estimates.values())


def test_estimates_are_physically_plausible(estimates):
    for name, gas in estimates.items():
        assert 40_000 < gas < 400_000, f"{name} at {gas} is outside any plausible range"
