"""The policy configurations under test.

One place that names every configuration, so the calibration, the matrix and
the analysis cannot drift apart on what "the policies" are.
"""

from __future__ import annotations

from dataclasses import dataclass

# Intrinsic cost of any Ethereum transaction. Execution gas measured inside the
# EVM excludes it, but the arbitrageur pays it, so the entry threshold must.
INTRINSIC_GAS = 21_000


@dataclass(frozen=True)
class Policy:
    """A row of the experiment matrix."""

    name: str  # run name, also the results filename prefix
    hook: str  # HOOK_NAME passed to the harness
    fee_pips: int = 0  # non-zero only for the static baselines
    size_dependent: bool = False  # fee reads amountSpecified (spec §A.8)


# The six hooks. PegStabilityHook ships in both readings (spec §5).
HOOKS: tuple[Policy, ...] = (
    Policy("BAHook", "BAHook"),
    Policy("DAHook", "DAHook"),
    Policy("ABHook", "ABHook"),
    Policy("PegDefence", "PegDefence"),
    Policy("PegCapture", "PegCapture"),
    Policy("MEVChargeHook", "MEVChargeHook", size_dependent=True),
    # The same template with a dimensionless impact measure. Both are run: the
    # shipped one sizes a trade by amount/L, which is not a ratio, and charges
    # 354 bps one way against 30 bps the other purely from the input's
    # denomination. See MEVChargeHookFixed.
    Policy("MEVChargeHookFixed", "MEVChargeHookFixed", size_dependent=True),
    Policy("VolatilityHook", "VolatilityHook"),
)

# Static baselines: 5, 30, 60, 100 bps. 30 bps is the one ABHook's constant sum
# K/2 coincides with, which makes that pair exactly budget-matched.
BASELINE_FEES_PIPS: tuple[int, ...] = (500, 3000, 6000, 10000)

BASELINES: tuple[Policy, ...] = tuple(
    Policy(f"MyHook@{f}", "MyHook", fee_pips=f) for f in BASELINE_FEES_PIPS
)

ALL: tuple[Policy, ...] = HOOKS + BASELINES


def by_name(name: str) -> Policy:
    for p in ALL:
        if p.name == name:
            return p
    raise KeyError(f"unknown policy {name!r}; known: {[p.name for p in ALL]}")
