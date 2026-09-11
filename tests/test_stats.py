import numpy as np
import pandas as pd
import pytest

from experiments.stats import analyse, benjamini_hochberg, wilcoxon_paired


def test_all_positive_differences_are_detected():
    """Eight wins out of eight. A t-test misses this because the outlier lands
    in its own denominator; see learning/statistics-for-our-experiment.md §8."""
    r = wilcoxon_paired([2, 1, 3, 2, 1, 2, 1, 400])

    assert r["p"] < 0.05
    assert r["win_rate"] == 1.0
    assert r["n"] == 8


def test_the_effect_size_always_travels_with_the_p_value():
    r = wilcoxon_paired([2, 1, 3, 2, 1, 2, 1, 400])
    assert "median" in r, "a significance flag without an effect size is banned"
    assert r["median"] == pytest.approx(2.0)


def test_symmetric_noise_is_not_detected():
    assert wilcoxon_paired([1, -1, 2, -2, 3, -3, 4, -4])["p"] > 0.05


def test_all_zero_differences_report_no_effect():
    r = wilcoxon_paired([0.0] * 10)
    assert r["p"] == 1.0
    assert r["median"] == 0.0


def test_bh_worked_example():
    """Spec §12.1: naive alpha declares 4, Bonferroni 1, BH 2."""
    ps = [0.001, 0.008, 0.02, 0.04, 0.13, 0.21, 0.33, 0.48, 0.62, 0.91]
    flags = benjamini_hochberg(ps, q=0.05)

    assert sum(flags) == 2
    assert flags[0] and flags[1]
    assert sum(p <= 0.05 for p in ps) == 4, "the naive threshold would declare 4"
    assert sum(p <= 0.005 for p in ps) == 1, "Bonferroni would declare 1"


def test_bh_step_up_admits_a_value_that_failed_its_own_threshold():
    ps = [0.001, 0.012, 0.013, 0.019, 0.30, 0.4, 0.5, 0.6, 0.7, 0.8]
    flags = benjamini_hochberg(ps, q=0.05)

    assert sum(flags) == 4
    assert flags[1], "p=0.012 rides in on the largest passing index"


def test_bh_is_stricter_when_the_evidence_is_scattered():
    """One borderline result among many nulls is what BH is meant to reject."""
    ps = [0.04] + [0.5] * 9
    assert sum(benjamini_hochberg(ps, q=0.05)) == 0
    assert sum(p <= 0.05 for p in ps) == 1, "the naive threshold would declare it"


def test_bh_accepts_a_coherent_set_rather_than_punishing_it():
    """Ten p-values all at 0.04 is strong joint evidence, not ten coincidences.
    Expected false discoveries are 10 x 0.04 = 0.4, an FDR of 4%, so accepting
    all of them is exactly what controlling the FDR at 5% means. BH is not
    uniformly stricter than the naive threshold -- it controls a different
    quantity."""
    assert sum(benjamini_hochberg([0.04] * 10, q=0.05)) == 10


def test_bh_on_pure_noise_finds_almost_nothing():
    """Ninety independent tests under the null: the naive threshold fires often,
    BH must not."""
    rng = np.random.default_rng(7)
    ps = rng.uniform(size=90).tolist()

    assert sum(benjamini_hochberg(ps, q=0.05)) == 0
    assert sum(p <= 0.05 for p in ps) >= 1, "the naive threshold does fire on noise"


def test_analyse_returns_one_row_per_comparison_with_an_effect_size():
    rows = []
    for policy in ("ABHook", "VolatilityHook"):
        for regime in ("low", "high"):
            for w in range(24):
                rows.append(
                    {
                        "policy": policy,
                        "pair": "ETH/SHIB",
                        "regime": regime,
                        "gas_price_wei": 20_000_000_000,
                        "address_mode": "persistent",
                        "net_result_delta": 5.0 if policy == "ABHook" else -1.0,
                    }
                )
    out = analyse(pd.DataFrame(rows))

    assert len(out) == 4
    assert {"p", "median", "win_rate", "n", "significant_fdr"} <= set(out.columns)
    assert out["n"].eq(24).all()


def test_bootstrap_ci_brackets_the_median():
    """The interval is the point of the whole exercise: a median without one
    says nothing about how well it is pinned down."""
    from experiments.stats import bootstrap_median_ci

    deltas = [100.0, 120.0, 90.0, 110.0, 105.0, 95.0, 115.0, 108.0] * 3
    low, high = bootstrap_median_ci(deltas)

    assert low < 105 < high
    assert high - low < 40, "a tight sample must give a tight interval"


def test_bootstrap_ci_is_wide_when_the_sample_is_scattered():
    """BAHook's advantage spans +22 to +697 across seeds. An interval that did
    not widen for data like that would be worse than none."""
    from experiments.stats import bootstrap_median_ci

    tight = bootstrap_median_ci([100.0] * 24)
    loose = bootstrap_median_ci([-500.0, 2000.0, 10.0, 700.0, -300.0, 50.0] * 4)

    assert (tight[1] - tight[0]) < (loose[1] - loose[0])


def test_bootstrap_ci_is_deterministic():
    """A seeded resample, so the number in the paper does not move between runs
    of the same notebook."""
    from experiments.stats import bootstrap_median_ci

    values = [3.0, -1.0, 7.0, 2.0, -4.0, 9.0, 1.0, 0.5] * 3
    assert bootstrap_median_ci(values) == bootstrap_median_ci(values)


def test_bootstrap_ci_and_the_test_can_disagree_and_that_is_informative():
    """An interval that excludes zero and a significant p-value answer the same
    question two ways; where they disagree the interval is the more honest
    report, because it shows how much of the effect is pinned down."""
    from experiments.stats import bootstrap_median_ci, wilcoxon_paired

    # Consistently positive but tiny: significance is easy, the interval is
    # narrow and clear of zero.
    small = [6.0, 6.1, 5.9, 6.2, 5.8, 6.05] * 4
    low, high = bootstrap_median_ci(small)
    assert low > 0 and wilcoxon_paired(small)["p"] < 0.05
    assert high - low < 1.0


def test_bootstrap_ci_handles_an_empty_or_degenerate_sample():
    from experiments.stats import bootstrap_median_ci
    import math

    low, high = bootstrap_median_ci([])
    assert math.isnan(low) and math.isnan(high)
    assert bootstrap_median_ci([5.0]) == (5.0, 5.0)
