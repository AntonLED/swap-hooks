import statistics

import pytest

from experiments.reference.welford import welford


def test_matches_the_statistics_module():
    xs = [3000.1, 3000.4, 2999.7, 3001.2, 2998.9]
    mean, var = welford(xs)

    assert mean == pytest.approx(statistics.fmean(xs))
    assert var == pytest.approx(statistics.variance(xs))


def _naive_variance(xs: list[float]) -> float:
    """The textbook E[x²] − E[x]² form, for contrast."""
    n = len(xs)
    mean = sum(xs) / n
    mean_sq = sum(x * x for x in xs) / n
    return (mean_sq - mean * mean) * n / (n - 1)


def test_beats_the_naive_formula_on_offset_data():
    """This is the property Welford actually has.

    With values near 1e9 and a spread of 0.1, `E[x²] − E[x]²` subtracts two huge
    nearly-equal numbers and the answer is destroyed. Welford never forms those
    quantities. Note float64 cannot represent 1e9 + 0.1 exactly either, so
    neither method is exact -- the point is the size of the error.
    """
    xs = [1e9 + d for d in (0.1, 0.2, 0.3, 0.4)]
    truth = float(statistics.variance(xs))  # CPython computes this exactly

    _, welford_var = welford(xs)
    naive_var = _naive_variance(xs)

    welford_err = abs(welford_var - truth) / truth
    naive_err = abs(naive_var - truth) / truth

    assert welford_err < naive_err / 100, (
        f"welford {welford_err:.2e} should be far below naive {naive_err:.2e}"
    )
    assert welford_err < 1e-5


def test_single_sample_has_zero_variance():
    assert welford([42.0]) == (42.0, 0.0)


def test_constant_series_has_zero_variance():
    _, var = welford([7.0] * 10)
    assert var == pytest.approx(0.0)
