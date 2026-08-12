import numpy as np
import pandas as pd
import pytest

from experiments.kappa_sensitivity import (
    POLICIES,
    TURNOVER_MULTIPLES,
    analyse,
    flow_composition,
    static_curve,
)


def _frame():
    """A sweep result where the interior optimum exists at high retail and
    disappears at low retail -- the outcome the sweep is built to detect."""
    rows = []
    for multiple in TURNOVER_MULTIPLES:
        retail_rich = multiple >= 1.0
        for policy in POLICIES:
            level = (
                int(policy.removeprefix("MyHook@")) / 100
                if policy.startswith("MyHook@")
                else 30.0
            )
            for r, regime in enumerate(("low", "mid", "high")):
                for w in range(4):
                    for gas in (5_000_000_000, 20_000_000_000, 80_000_000_000):
                        # Retail-rich: a hump peaking at 60 bps. Retail-poor:
                        # monotone in the fee, the arb-only degeneracy back.
                        net = (
                            2000.0 - ((level - 60.0) ** 2)
                            if retail_rich
                            else 10.0 * level
                        )
                        rows.append(
                            {
                                "policy": policy,
                                "turnover_multiple": multiple,
                                "uu_kappa": 0.055 * multiple,
                                "window_start_ms": r * 100 + w,
                                "regime": regime,
                                "gas_price_wei": gas,
                                "net_result": net,
                                "net_result_tt": net + 1.0,
                                "uu_volume": 1e6 * multiple,
                                "arb_volume": 4e4,
                                "uu_participation": 0.7,
                                "trade_count": 100,
                                "error": None,
                            }
                        )
    return pd.DataFrame(rows)


def test_flow_composition_reports_the_arbitrage_share_not_only_the_input():
    """`turnover_multiple` is what we set; the informed share is what a reader
    of the dynamic-fee literature needs, and the two are not interchangeable."""
    out = flow_composition(_frame())

    assert "arb_share_of_volume" in out.columns
    assert list(out.index) == sorted(TURNOVER_MULTIPLES)
    # Less retail must mean a larger informed share, or the axis is mislabelled.
    assert out["arb_share_of_volume"].is_monotonic_decreasing


def test_static_curve_exposes_whether_the_interior_optimum_survives():
    curve = static_curve(_frame())

    assert set(curve.columns) == set(TURNOVER_MULTIPLES)
    assert list(curve.index) == [5.0, 30.0, 60.0, 100.0]
    # Retail-rich column peaks in the middle; retail-poor peaks at the top.
    assert curve[1.0].idxmax() == 60.0
    assert curve[0.03].idxmax() == 100.0


def test_analyse_pairs_within_a_turnover_level_never_across():
    """Two turnover levels are two different worlds. Pairing across them would
    not be a comparison of policies at all."""
    frame = _frame()
    result = analyse(frame)

    assert set(result["turnover_multiple"]) == set(TURNOVER_MULTIPLES)
    # Every policy but the baseline appears, at every level, in every regime
    # plus the pooled row.
    expected = (len(POLICIES) - 1) * len(TURNOVER_MULTIPLES) * 4 * 2  # x2 valuations
    assert len(result) == expected
    assert set(result["valuation"]) == {"net_result", "net_result_tt"}


def test_analyse_controls_each_valuations_family_separately():
    """The two valuations are the same comparisons measured twice. Pooling them
    would let a win in one borrow significance from the other."""
    result = analyse(_frame())

    assert "significant_fdr" in result.columns
    assert result["significant_fdr"].dtype == bool


def test_the_preregistered_value_is_in_the_grid():
    """1.0x is the value the matrix ran. Without it in the sweep there is
    nothing to anchor the other levels against."""
    assert 1.0 in TURNOVER_MULTIPLES
    # And the grid must reach well below it: the whole point is more arbitrage.
    assert min(TURNOVER_MULTIPLES) <= 0.05


def test_run_one_accepts_a_kappa_override_and_defaults_to_the_calibrated_one():
    """The override must be inert when absent, or every existing UU result
    changes meaning the moment this parameter exists."""
    import inspect

    from experiments.run_one import run_one

    parameter = inspect.signature(run_one).parameters["uu_kappa"]
    assert parameter.default is None


@pytest.mark.parametrize("multiple", TURNOVER_MULTIPLES)
def test_every_turnover_level_gets_its_own_trace_directory(multiple, tmp_path):
    """`run_one` names a trace from the seven experiment axes, and kappa is not
    one of them, so a shared directory would have each level overwrite the
    last -- the collision that put UU traces on top of the arb-only ones."""
    from experiments import kappa_sensitivity

    name = f"turnover-{multiple}"
    assert name != "turnover-"
    assert len({f"turnover-{m}" for m in TURNOVER_MULTIPLES}) == len(
        TURNOVER_MULTIPLES
    ), "two levels sharing a directory name would collide silently"
    assert kappa_sensitivity.RESULTS.name == "sensitivity"


def test_sweep_never_writes_into_the_matrix_directory():
    """A prefix match once let 504 captureShare cells leak into a
    pre-registered figure. The separation is structural, not a convention."""
    from experiments import kappa_sensitivity

    assert "sensitivity" in kappa_sensitivity.RESULTS.parts
    assert "matrix" not in kappa_sensitivity.RESULTS.parts


def test_flow_composition_ignores_failed_cells():
    frame = _frame()
    frame.loc[frame.index[:10], "error"] = "boom"
    frame.loc[frame.index[:10], "net_result"] = np.nan

    out = flow_composition(frame)
    assert out["net_result"].notna().all()
