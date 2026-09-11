import pandas as pd

from experiments.aggregate import (
    BASELINE_POLICY,
    by_regime,
    paired_against_baseline,
    summarise_strata,
)


def _frame():
    rows = []
    for policy, net in (("ABHook", 10.0), (BASELINE_POLICY, 8.0)):
        for r, regime in enumerate(("low", "mid", "high")):
            for window in range(4):
                # A window belongs to exactly one regime, so the start must be
                # unique across regimes or the join fans out.
                rows.append(
                    {
                        "policy": policy,
                        "pair": "ETH/SHIB",
                        "regime": regime,
                        "window_start_ms": r * 100 + window,
                        "gas_price_wei": 20_000_000_000,
                        "address_mode": "persistent",
                        "net_result": net,
                        "fee_income": net * 2,
                        "il": 1.0,
                        "retained_volume": 100.0,
                        "trade_count": 5,
                        "gas_cost": 1.0,
                    }
                )
    return pd.DataFrame(rows)


def _uu_frame():
    """The same frame as a UU-flow run produces it.

    The trade-time valuation disagrees with the end-of-window one on purpose:
    the 2026-08-09 audit found the two can differ in sign, and the
    pre-registration declares both as co-primary for exactly that reason.
    """
    frame = _frame()
    is_baseline = frame["policy"] == BASELINE_POLICY
    frame["net_result_tt"] = 5.0
    frame.loc[is_baseline, "net_result_tt"] = 9.0  # baseline wins on this one
    frame["uu_volume"] = 80.0
    frame["arb_volume"] = 20.0
    frame["arb_profit_realized"] = 3.0
    frame["uu_fee_share"] = 0.8
    frame["uu_participation"] = 0.6
    return frame


def test_by_regime_reports_a_standard_error():
    out = by_regime(_frame())
    assert {"net_result_mean", "net_result_sem"} <= set(out.columns)
    assert len(out) == 2 * 3


def test_retained_volume_travels_with_every_metric():
    """Spec §12.1: without it, "charge the maximum and nobody trades" reads as
    a win."""
    assert "retained_volume_mean" in by_regime(_frame()).columns


def test_pairing_is_per_window_not_per_average():
    out = paired_against_baseline(_frame())
    assert len(out) == 12, "one row per policy-window, no fan-out"
    assert out["net_result_delta"].sub(2.0).abs().lt(1e-9).all()


def test_baseline_rows_are_excluded_from_the_comparison():
    out = paired_against_baseline(_frame())
    assert BASELINE_POLICY not in set(out["policy"])


def test_pairing_joins_on_every_axis_but_the_policy():
    """A row must be compared against the baseline run over the SAME data."""
    frame = _frame()
    frame.loc[frame["policy"] == BASELINE_POLICY, "gas_price_wei"] = 5_000_000_000

    assert paired_against_baseline(frame).empty, "mismatched axes must not pair up"


def test_an_absent_baseline_yields_nothing_rather_than_wrong_numbers():
    frame = _frame()
    assert paired_against_baseline(frame[frame["policy"] != BASELINE_POLICY]).empty


def test_pairing_carries_the_trade_time_valuation():
    """`net_result_tt` is co-primary, not a diagnostic.

    The 2026-08-09 pre-registration declares the pair of valuations and requires
    both to be reported side by side. A hardcoded metric list made the second
    one unreachable: `analyse(paired, value="net_result_tt_delta")` raised
    KeyError, which is one keystroke away from quietly reporting only the
    friendlier valuation.
    """
    out = paired_against_baseline(_uu_frame())

    assert "net_result_tt_delta" in out.columns
    assert out["net_result_tt_delta"].sub(-4.0).abs().lt(1e-9).all()


def test_pairing_carries_the_flow_split():
    out = paired_against_baseline(_uu_frame())

    for column in ("uu_volume_delta", "arb_volume_delta", "arb_profit_realized_delta"):
        assert column in out.columns
        assert out[column].abs().lt(1e-9).all(), "both arms carry the same values"


def test_pairing_still_works_on_a_frame_without_the_uu_columns():
    """The arb-only `results/summary.csv` is a frozen artifact and predates
    every UU column. Asking for a column it does not have must not break it."""
    out = paired_against_baseline(_frame())

    assert "net_result_delta" in out.columns
    assert "net_result_tt_delta" not in out.columns
    assert len(out) == 12


def test_by_regime_reports_the_uu_columns_when_they_exist():
    out = by_regime(_uu_frame())

    assert {
        "net_result_tt_mean",
        "uu_volume_mean",
        "arb_volume_mean",
        "uu_participation_mean",
    } <= set(out.columns)


def test_by_regime_omits_the_uu_columns_on_an_arb_only_frame():
    assert "net_result_tt_mean" not in by_regime(_frame()).columns


def _stratum_tests():
    """Per-stratum medians for three policies over the two volatile pairs.

    `DAHook` wins in every stratum, `ABHook` loses in every one, `BAHook` is
    split — which is the case the interval has to separate from the other two.
    """
    rows = []
    for pair in ("ETH/SHIB", "ETH/USDC"):
        for regime in ("low", "mid", "high"):
            for index, gas in enumerate((5e9, 20e9, 80e9)):
                rows.append(
                    {
                        "policy": "DAHook",
                        "pair": pair,
                        "regime": regime,
                        "gas_price_wei": gas,
                        "median": 300.0 + 10 * index,
                    }
                )
                rows.append(
                    {
                        "policy": "ABHook",
                        "pair": pair,
                        "regime": regime,
                        "gas_price_wei": gas,
                        "median": -250.0 - 10 * index,
                    }
                )
                rows.append(
                    {
                        "policy": "BAHook",
                        "pair": pair,
                        "regime": regime,
                        "gas_price_wei": gas,
                        "median": 400.0 if index else -400.0,
                    }
                )
    # The peg, which every headline number holds out: including it would drag
    # each policy's median toward the zeros it contributes.
    for regime in ("low", "mid", "high"):
        for policy in ("DAHook", "ABHook", "BAHook"):
            rows.append(
                {
                    "policy": policy,
                    "pair": "USDC/USDT",
                    "regime": regime,
                    "gas_price_wei": 20e9,
                    "median": 0.0,
                }
            )
    return pd.DataFrame(rows)


def test_summarise_strata_holds_out_the_peg_pair():
    out = summarise_strata(_stratum_tests()).set_index("policy")

    # 2 pairs x 3 regimes x 3 gas; the nine USDC/USDT rows are not in it.
    assert (out["strata"] == 18).all()
    assert out.loc["DAHook", "median"] > 300
    assert out.loc["ABHook", "median"] < -250


def test_summarise_strata_separates_a_consistent_effect_from_a_split_one():
    """The whole reason the interval was added. `BAHook` here has a positive
    median and a sign that flips across a third of its strata; only the interval
    distinguishes it from `DAHook`, which never loses one."""
    out = summarise_strata(_stratum_tests()).set_index("policy")

    assert out.loc["DAHook", "ci_excludes_zero"]
    assert out.loc["ABHook", "ci_excludes_zero"]
    assert not out.loc["BAHook", "ci_excludes_zero"]
    assert out.loc["BAHook", "median"] > 0, "a positive median that means nothing"


def test_summarise_strata_counts_the_strata_a_policy_won():
    out = summarise_strata(_stratum_tests()).set_index("policy")

    assert out.loc["DAHook", "strata_positive"] == 18
    assert out.loc["ABHook", "strata_positive"] == 0
    assert out.loc["BAHook", "strata_positive"] == 12
