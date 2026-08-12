import pandas as pd

from experiments.seed_robustness import (
    BASELINE,
    PAIRS,
    POLICIES,
    SEEDS,
    analyse,
    stability,
)


def _frame(flip_abhook_on_seed=None):
    """Five seeds where DAHook always wins and ABHook always loses -- unless
    `flip_abhook_on_seed` is given, in which case one seed disagrees."""
    rows = []
    for pair, _, _ in PAIRS:
        for seed in SEEDS:
            for policy in POLICIES:
                for w in range(8):
                    if policy == BASELINE:
                        net = 1000.0
                    elif policy == "DAHook":
                        net = 1200.0
                    elif policy == "BAHook":
                        net = 1100.0
                    else:  # ABHook loses, except possibly on one seed
                        net = 1300.0 if seed == flip_abhook_on_seed else 800.0
                    rows.append(
                        {
                            "policy": policy,
                            "pair": pair,
                            "seed": seed,
                            "window_start_ms": w,
                            "regime": ("low", "mid", "high")[w % 3],
                            "gas_price_wei": 20_000_000_000,
                            "net_result": net,
                            "net_result_tt": net + 1.0,
                            "error": None,
                        }
                    )
    return pd.DataFrame(rows)


def test_the_baseline_is_paired_within_a_seed_never_across():
    """Two seeds are two different realisations of the draw. Pairing across
    them would not be a comparison of policies at all."""
    result = analyse(_frame())

    # Every (pair, seed, policy-but-baseline, valuation) combination, once.
    expected = len(PAIRS) * len(SEEDS) * (len(POLICIES) - 1) * 2
    assert len(result) == expected
    assert BASELINE not in set(result["policy"])
    assert set(result["seed"]) == set(SEEDS)


def test_a_policy_that_keeps_its_sign_everywhere_is_unanimous():
    table = stability(analyse(_frame())).set_index(["pair", "policy"])

    for pair, _, _ in PAIRS:
        assert table.loc[(pair, "DAHook"), "unanimous"]
        assert table.loc[(pair, "DAHook"), "seeds_positive"] == len(SEEDS)
        assert table.loc[(pair, "ABHook"), "unanimous"]
        assert table.loc[(pair, "ABHook"), "seeds_positive"] == 0


def test_one_disagreeing_seed_costs_a_policy_its_unanimity():
    """The whole point of the appendix: an advantage that survives four seeds
    and not the fifth is a fact about the draw, not about the policy."""
    table = stability(analyse(_frame(flip_abhook_on_seed=3))).set_index(
        ["pair", "policy"]
    )

    for pair, _, _ in PAIRS:
        assert not table.loc[(pair, "ABHook"), "unanimous"]
        assert table.loc[(pair, "ABHook"), "seeds_positive"] == 1
        # The others are untouched by one policy's instability.
        assert table.loc[(pair, "DAHook"), "unanimous"]


def test_the_spread_across_seeds_is_reported():
    """A unanimous sign with a huge spread is still weak evidence, so the
    range has to travel with the verdict."""
    table = stability(analyse(_frame()))

    assert {"median_min", "median_median", "median_max", "spread"} <= set(
        table.columns
    )
    assert (table["spread"] >= 0).all()


def test_five_seeds_and_the_baseline_are_actually_configured():
    """Spec §2.4 asks for five; a check run on one seed answers nothing."""
    assert len(SEEDS) == 5
    assert BASELINE in POLICIES
    assert len(POLICIES) > 1


def test_the_check_covers_the_pairs_where_a_win_is_claimed():
    """USDC/USDT is deliberately absent: both policies lose there
    significantly, so there is no positive result whose stability is at issue."""
    names = {p[0] for p in PAIRS}
    assert names == {"ETH/SHIB", "ETH/USDC"}


def test_failed_cells_are_dropped_rather_than_silently_zeroed():
    frame = _frame()
    frame.loc[frame.index[:20], "error"] = "boom"
    frame.loc[frame.index[:20], "net_result"] = float("nan")

    result = analyse(frame)
    assert result["median"].notna().all()


def test_analysing_a_fixture_never_touches_the_real_results_file():
    """Found on 2026-08-11: `analyse()` wrote `seed_tests.csv` unconditionally,
    so every run of this very test file overwrote the real appendix with these
    fixture medians -- +200, +100, -200 -- and the file on disk had been fixture
    data for an unknown time. `seeds.csv` is the record and survived, so nothing
    published was wrong, but the derived artifact was destroyed by running the
    tests.
    """
    from experiments.seed_robustness import RESULTS

    target = RESULTS / "seed_tests.csv"
    before = target.read_bytes() if target.exists() else None

    analyse(_frame())

    after = target.read_bytes() if target.exists() else None
    assert after == before, "analysing a fixture must not write into results/"


def test_the_two_operating_points_never_share_a_path():
    """Traces are named from the seven experiment axes and kappa is not one of
    them, so two operating points writing to one directory would overwrite each
    other cell for cell -- and `seeds.csv` carries no kappa column to detect it
    afterwards. This project has already lost a set of traces to exactly that."""
    from experiments.seed_robustness import paths_for

    headline, _ = paths_for(1.0)
    informed, _ = paths_for(0.1)

    assert headline != informed
    # Nested under the headline's parent, not a sibling of `results/`: forge's
    # `fs_permissions` is an allowlist over a subtree, and a sibling is outside
    # it -- the defect that failed all 7,776 cells of the first attempt at the
    # second operating point.
    assert informed.is_relative_to(headline)


def test_the_calibrated_point_still_takes_the_default_kappa_path():
    """1.0x must mean "use the calibrated value", not "multiply it by one".
    A float round-trip through a multiplication is not guaranteed to land on
    the same bits, and the headline matrix is already on disk."""
    from experiments.seed_robustness import TURNOVER_DEFAULT, paths_for

    root, stem = paths_for(TURNOVER_DEFAULT)
    assert (root / f"{stem}.csv").name == "seeds.csv"
    assert root.name == "sensitivity", "the headline keeps its original location"
