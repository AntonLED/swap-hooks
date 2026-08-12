import json

import numpy as np
import pandas as pd
import pytest

from experiments.figures import (
    NEAR_LIMIT,
    draw_all,
    draw_all_uu,
    fee_distribution,
    figure_note,
    frontier,
    gas_breakeven,
    kappa_response,
    net_result_by_regime,
    operating_points,
    seed_stability,
    uu_flow,
    valuation_comparison,
)


def _frame():
    rng = np.random.default_rng(3)
    rows = []
    policies = [f"MyHook@{f}" for f in (500, 3000, 6000, 10000)] + [
        "ABHook",
        "BAHook",
        "DAHook",
        "PegCapture",
        "PegDefence",
        "MEVChargeHook",
        "VolatilityHook",
    ]
    for policy in policies:
        for regime in ("low", "mid", "high"):
            for gas in (5e9, 20e9, 80e9):
                for w in range(8):
                    rows.append(
                        {
                            "policy": policy,
                            "regime": regime,
                            "gas_price_wei": gas,
                            "window_start_ms": w,
                            "pair": "ETH/SHIB",
                            "address_mode": "persistent",
                            "net_result": float(rng.normal(300, 50)),
                            "retained_volume": float(rng.normal(2e6, 2e5)),
                        }
                    )
    return pd.DataFrame(rows)


@pytest.mark.parametrize("fn", [net_result_by_regime, frontier, gas_breakeven])
def test_each_figure_writes_a_nonempty_pdf(tmp_path, fn):
    out = tmp_path / f"{fn.__name__}.pdf"
    fn(_frame(), out)

    assert out.exists() and out.stat().st_size > 0


@pytest.mark.parametrize("fn", [net_result_by_regime, frontier, gas_breakeven])
def test_each_figure_writes_the_table_view_beside_it(tmp_path, fn):
    """The palette validator raises a contrast warning; a table view is the
    relief, and a reader checking a number needs it regardless."""
    out = tmp_path / f"{fn.__name__}.pdf"
    fn(_frame(), out)

    assert out.with_suffix(".csv").exists()


def test_fee_distribution_reports_pinning_against_each_policys_own_box(tmp_path):
    """The three things the histogram version got wrong.

    A constant must survive as a row rather than a one-pixel spike; every policy
    must be judged against its OWN fee box rather than a shared one; and a policy
    sitting on a bound must be reported as pinned instead of leaving the reader
    to infer it.

    MEVChargeHook's box was 30-1000 bps when this test was written and is 30-100
    since the 2026-08-09 clamp, which is why its expectation flipped: the point
    of the test is that the box is per policy and current, not that any
    particular number is in it.
    """
    rows = (
        [{"policy": "MyHook@3000", "pair": "ETH/SHIB", "fee_bps": 30.0}] * 50
        + [{"policy": "PegDefence", "pair": "ETH/SHIB", "fee_bps": 1.0}] * 50
        # Above the shared 100 bps box. MEVChargeHook was clamped to that box
        # for the UU matrix (2026-08-09 prereg), so a fee that used to sit
        # mid-box now sits at its cap -- which is exactly what the figure has
        # to report.
        + [{"policy": "MEVChargeHook", "pair": "ETH/SHIB", "fee_bps": 300.0}] * 50
    )
    out = tmp_path / "fees.pdf"
    fee_distribution(pd.DataFrame(rows), out)

    assert out.exists() and out.stat().st_size > 0
    table = pd.read_csv(out.with_suffix(".csv")).set_index("policy")
    assert set(table.index) == {"MyHook@3000", "PegDefence", "MEVChargeHook"}
    assert table.loc["MyHook@3000", "median_bps"] == pytest.approx(30.0)
    assert table.loc["PegDefence", "share_at_floor"] == pytest.approx(1.0)
    # Since the clamp its box IS 30-100 bps, so 300 bps reads as at cap. The
    # original assertion documented the pre-clamp 30-1000 box.
    assert table.loc["MEVChargeHook", "share_at_cap"] == pytest.approx(1.0)
    # A constant has no box, so it can never be reported as pinned to one.
    assert table.loc["MyHook@3000", "share_at_cap"] == pytest.approx(0.0)


def _uu_frame():
    """A UU-flow frame whose two valuations disagree in sign for one policy.

    That disagreement is the thing the figures exist to make visible: the
    2026-08-09 audit found four arb-only conclusions flipped between the
    end-of-window and trade-time valuations, and the pre-registration answers
    it by declaring both and reporting them side by side.
    """
    rng = np.random.default_rng(11)
    frame = _frame()
    frame["net_result_tt"] = frame["net_result"] + rng.normal(0, 20, len(frame))
    flipped = frame["policy"] == "ABHook"
    frame.loc[flipped, "net_result_tt"] = -frame.loc[flipped, "net_result"]
    # A high fee keeps less retail volume: the mechanism that removes the
    # arb-only degeneracy, so the figure has to be able to show it.
    level = frame["policy"].str.extract(r"MyHook@(\d+)")[0].astype(float).fillna(3000.0)
    frame["uu_participation"] = (1.0 - level / 20000.0).clip(0.05, 1.0)
    frame["uu_volume"] = frame["retained_volume"] * frame["uu_participation"]
    frame["arb_volume"] = frame["retained_volume"] - frame["uu_volume"]
    frame["uu_fee_share"] = frame["uu_volume"] / frame["retained_volume"]
    return frame


def test_net_result_by_regime_can_draw_the_trade_time_valuation(tmp_path):
    out = tmp_path / "tt.pdf"
    net_result_by_regime(_uu_frame(), out, value="net_result_tt")

    assert out.exists() and out.stat().st_size > 0
    table = pd.read_csv(out.with_suffix(".csv"))
    # The table view must name the valuation it was drawn from. Both figures
    # otherwise write CSVs with identical column names, and a reader checking
    # a number cannot tell which of the two they are holding.
    assert set(table["value"]) == {"net_result_tt"}


def test_frontier_can_draw_the_trade_time_valuation(tmp_path):
    out = tmp_path / "frontier_tt.pdf"
    frontier(_uu_frame(), out, value="net_result_tt")

    assert out.exists() and out.with_suffix(".csv").stat().st_size > 0


def test_valuation_comparison_puts_both_valuations_on_one_axis(tmp_path):
    out = tmp_path / "valuations.pdf"
    valuation_comparison(_uu_frame(), out)

    assert out.exists() and out.stat().st_size > 0
    table = pd.read_csv(out.with_suffix(".csv"))
    assert {"policy", "net_result", "net_result_tt", "disagrees"} <= set(table.columns)
    # ABHook was built with opposite signs; the table must say so rather than
    # leaving the reader to compare two columns by eye.
    assert bool(table.set_index("policy").loc["ABHook", "disagrees"])
    assert not bool(table.set_index("policy").loc["MyHook@3000", "disagrees"])


def test_uu_flow_reports_the_split_and_the_participation(tmp_path):
    out = tmp_path / "uu_flow.pdf"
    uu_flow(_uu_frame(), out)

    assert out.exists() and out.stat().st_size > 0
    table = pd.read_csv(out.with_suffix(".csv")).set_index("policy")
    assert {"uu_share_of_volume", "uu_participation", "uu_fee_share"} <= set(
        table.columns
    )
    # The static levels are the calibration of the whole model: a higher fee
    # must retain strictly less retail flow, or the second blade of the
    # scissors is not cutting and the degeneracy is back.
    assert (
        table.loc["MyHook@500", "uu_participation"]
        > table.loc["MyHook@10000", "uu_participation"]
    )


def test_uu_figures_refuse_a_frame_without_the_columns(tmp_path):
    """An arb-only frame has no UU columns at all. Failing loudly beats
    drawing an empty axis that reads as "the policy did nothing"."""
    for fn in (valuation_comparison, uu_flow):
        with pytest.raises(KeyError):
            fn(_frame(), tmp_path / f"{fn.__name__}.pdf")


def test_a_missing_policy_in_one_regime_does_not_crash(tmp_path):
    frame = _frame()
    frame = frame[~((frame["policy"] == "ABHook") & (frame["regime"] == "high"))]

    out = tmp_path / "gap.pdf"
    net_result_by_regime(frame, out)
    assert out.exists()


def test_draw_all_produces_every_figure(tmp_path):
    """Covers the path that let `fee_distribution` rot.

    It was imported into run_matrix and never called, so it went a whole matrix
    run without being drawn; later the import went missing while the call site
    survived, which is a NameError that fires only once the other figures are
    already on disk. One call must produce all four.
    """
    results, figures = tmp_path / "results", tmp_path / "figures"
    results.mkdir()
    figures.mkdir()
    swap = {
        "kind": "swap",
        "feePips": 3000,
        "candle": 0,
        "blockNumber": 1,
        "timestamp": 0,
        "zeroForOne": True,
        "amountIn": "1",
        "amountOut": "1",
        "feeAB": 3000,
        "feeBA": 3000,
        "delta0": "1",
        "delta1": "-1",
        "expectedProfit": "0",
        "gas": 1,
        "sender": "0x0",
        "extPrice0": "1",
        "extPrice1": "1",
        "sqrtPriceBeforeX96": "1",
        "sqrtPriceAfterX96": "1",
    }
    name = "MyHook-3000-ETHUSDT-SHIBUSDT-1704067200000-20000000000-persistent.jsonl"
    (results / name).write_text(json.dumps(swap) + "\n")

    draw_all(_frame(), results, figures)

    expected = {
        "net_result_by_regime.pdf",
        "frontier.pdf",
        "gas_breakeven.pdf",
        "fee_distribution.pdf",
    }
    assert expected <= {p.name for p in figures.iterdir()}
    # Every figure writes its table view beside it; a missing one means the
    # figure drew from nothing.
    for pdf in expected:
        assert (figures / pdf).with_suffix(".csv").stat().st_size > 0


def _kappa_tests():
    """Two policies, one holding its advantage at every level and one not."""
    rows = []
    for level in (0.03, 0.1, 0.3, 1.0, 3.0):
        for policy, sign in (("DAHook", +1), ("ABHook", -1), ("MyHook@6000", +1)):
            for regime in ("low", "mid", "high", "ALL"):
                for valuation in ("net_result", "net_result_tt"):
                    rows.append(
                        {
                            "valuation": valuation,
                            "turnover_multiple": level,
                            "policy": policy,
                            "regime": regime,
                            "median": sign
                            * 200
                            * (1 if policy != "MyHook@6000" else level - 0.5),
                            "p": 0.01,
                            "significant_fdr": True,
                        }
                    )
    return pd.DataFrame(rows)


def _kappa_curve():
    return pd.DataFrame(
        {
            0.03: [-543, 1691, 2436, 2741],
            0.1: [-150, 2925, 3646, 3728],
            0.3: [1051, 6564, 7275, 6401],
            1.0: [4504, 17270, 18097, 14010],
            3.0: [10155, 34711, 34988, 24969],
        },
        index=pd.Index([5.0, 30.0, 60.0, 100.0], name="level_bps"),
    )


def test_kappa_response_draws_both_questions(tmp_path):
    """The sweep asks whether the RANKING survives the retail mix and whether
    the static curve's interior optimum does. Both must be on the page, or the
    figure answers half of what it was run for."""
    out = tmp_path / "kappa.pdf"
    kappa_response(_kappa_tests(), _kappa_curve(), out)

    assert out.exists() and out.stat().st_size > 0
    table = pd.read_csv(out.with_suffix(".csv"))
    # Only the pooled rows of the primary valuation are drawn; the regime split
    # is its own table, and drawing both would plot each policy four times.
    assert set(table["regime"]) == {"ALL"}
    assert set(table["valuation"]) == {"net_result"}


def test_seed_stability_shows_the_range_not_just_the_verdict(tmp_path):
    """A unanimous sign with a thirtyfold spread is still weak evidence, so the
    full range across seeds has to be visible beside the point estimate."""
    table = pd.DataFrame(
        [
            {
                "pair": "ETH/SHIB",
                "policy": "BAHook",
                "seeds": 5,
                "seeds_positive": 5,
                "unanimous": True,
                "median_min": 22.3,
                "median_median": 174.4,
                "median_max": 696.5,
                "spread": 674.2,
            },
            {
                "pair": "ETH/SHIB",
                "policy": "ABHook",
                "seeds": 5,
                "seeds_positive": 0,
                "unanimous": True,
                "median_min": -327.5,
                "median_median": -264.8,
                "median_max": -222.1,
                "spread": 105.4,
            },
        ]
    )
    out = tmp_path / "seeds.pdf"
    seed_stability(table, out)

    assert out.exists() and out.stat().st_size > 0
    beside = pd.read_csv(out.with_suffix(".csv"))
    assert {"median_min", "median_max", "seeds_positive"} <= set(beside.columns)


def _two_points():
    """Two configurations, spanning both sides of the row split."""
    rows = []
    for configuration, scale in (("kappa 1.0", 1.0), ("kappa 0.1", 0.2)):
        for policy, median in (
            ("DAHook", 341.0),
            ("BAHook", 114.0),
            ("ABHook", -254.0),
            ("PegDefence", -10880.0),
        ):
            value = median * scale
            rows.append(
                {
                    "configuration": configuration,
                    "policy": policy,
                    "median": value,
                    # BAHook is the one whose interval covers zero, at both.
                    "ci_low": value - (400.0 if policy == "BAHook" else 80.0) * scale,
                    "ci_high": value + (400.0 if policy == "BAHook" else 80.0) * scale,
                    "subtitle": f"baseline {configuration}",
                }
            )
    return pd.DataFrame(rows)


def test_operating_points_draws_one_column_per_configuration(tmp_path):
    out = tmp_path / "points.pdf"
    operating_points(_two_points(), out)

    assert out.exists() and out.stat().st_size > 0
    beside = pd.read_csv(out.with_suffix(".csv"))
    assert set(beside["configuration"]) == {"kappa 1.0", "kappa 0.1"}
    # Every policy survives to the table view: the two-row split is a change of
    # zoom, and a policy quietly dropped out of the far row would read as a
    # policy that was never run.
    assert set(beside["policy"]) == {"DAHook", "BAHook", "ABHook", "PegDefence"}


def test_operating_points_splits_rows_by_the_widest_reach_not_the_median(tmp_path):
    """A small median with a huge interval must not set the zoomed row's scale.

    Grouping on the median alone puts such a policy in the near row, where its
    whisker then stretches the axis by an order of magnitude and undoes the
    entire point of splitting.
    """
    table = _two_points()
    wide = table["policy"] == "ABHook"
    table.loc[wide, "ci_low"] = -5 * NEAR_LIMIT

    out = tmp_path / "reach.pdf"
    operating_points(table, out)

    assert out.exists() and out.stat().st_size > 0


def test_operating_points_survives_a_single_configuration(tmp_path):
    """Before the second matrix finishes there is only one, and the notebook
    still has to run rather than raising on a one-column subplot grid."""
    table = _two_points()
    out = tmp_path / "one.pdf"
    operating_points(table[table["configuration"] == "kappa 1.0"], out)

    assert out.exists() and out.stat().st_size > 0


def test_figure_note_stamps_only_inside_the_block(tmp_path):
    """The note names the run. A figure drawn outside the block must not carry
    the previous block's label -- a wrong provenance stamp is worse than none.
    """
    inside, outside = tmp_path / "inside.pdf", tmp_path / "outside.pdf"
    with figure_note("kappa = 0.1"):
        net_result_by_regime(_frame(), inside)
    net_result_by_regime(_frame(), outside)

    assert inside.stat().st_size > outside.stat().st_size


def test_draw_all_uu_returns_what_it_wrote_rather_than_a_glob(tmp_path):
    """`uu_*` also matches `uu_t01_*`, so a notebook globbing for the figures it
    had just drawn listed the other operating point's as its own."""
    results, figures = tmp_path / "results", tmp_path / "figures"
    results.mkdir()
    figures.mkdir()
    swap = {
        "kind": "swap", "feePips": 3000, "candle": 0, "blockNumber": 1,
        "timestamp": 0, "zeroForOne": True, "amountIn": "1", "amountOut": "1",
        "feeAB": 3000, "feeBA": 3000, "delta0": "1", "delta1": "-1",
        "expectedProfit": "0", "gas": 1, "sender": "0x0", "extPrice0": "1",
        "extPrice1": "1", "sqrtPriceBeforeX96": "1", "sqrtPriceAfterX96": "1",
    }
    name = "MyHook-3000-ETHUSDT-SHIBUSDT-1704067200000-20000000000-persistent.jsonl"
    (results / name).write_text(json.dumps(swap) + "\n")

    headline = draw_all_uu(_uu_frame(), results, figures, prefix="uu_")
    informed = draw_all_uu(_uu_frame(), results, figures, prefix="uu_t01_")

    assert len(headline) == len(informed) == 8
    # Disjoint, and neither list contains a name from the other run.
    assert not {p.name for p in headline} & {p.name for p in informed}
    assert all("t01" not in p.name for p in headline)
    # The glob that used to be used would have caught the second run's files.
    assert len(list(figures.glob("uu_*.pdf"))) == 16
