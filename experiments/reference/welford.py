"""Reference online mean/variance, used to check the Solidity implementation.

Welford's algorithm rather than the naive `E[x²] − E[x]²`: the latter subtracts
two large nearly-equal numbers and loses all precision when the mean is large
relative to the spread, which is the normal case for prices.
"""

from __future__ import annotations


def welford(xs: list[float]) -> tuple[float, float]:
    """Return (mean, sample variance) computed in one pass."""
    n = 0
    mean = 0.0
    m2 = 0.0
    for x in xs:
        n += 1
        d = x - mean
        mean += d / n
        m2 += d * (x - mean)  # note: the UPDATED mean
    variance = m2 / (n - 1) if n > 1 else 0.0
    return mean, variance
