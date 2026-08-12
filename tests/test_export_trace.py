import pandas as pd
import pytest

from experiments.export_trace import align_traces, export_trace


def test_writes_headerless_scaled_integers(tmp_path):
    df = pd.DataFrame({"open_time": [1, 2], "close": [3000.5, 0.00002]})
    path = tmp_path / "t.csv"
    export_trace(df, path)

    text = path.read_text()
    lines = text.strip().split("\n")
    assert lines[0] == "1,300050000000"
    assert lines[1] == "2,2000"
    assert "open_time" not in text, "no header"


def test_alignment_keeps_only_shared_timestamps():
    """A gap in one symbol must not shift the other's prices."""
    a = pd.DataFrame({"open_time": [1, 2, 3], "close": [10.0, 11.0, 12.0]})
    b = pd.DataFrame({"open_time": [1, 3], "close": [1.0, 3.0]})

    aa, bb = align_traces(a, b)

    assert list(aa["open_time"]) == [1, 3]
    assert list(bb["open_time"]) == [1, 3]
    assert list(aa["close"]) == [10.0, 12.0]


def test_alignment_rejects_an_empty_intersection():
    a = pd.DataFrame({"open_time": [1, 2], "close": [1.0, 2.0]})
    b = pd.DataFrame({"open_time": [8, 9], "close": [1.0, 2.0]})

    with pytest.raises(ValueError):
        align_traces(a, b)


def test_a_price_below_one_unit_of_scale_is_rejected():
    """SHIB at 1e-9 would round to 0 and make the pool price undefined."""
    df = pd.DataFrame({"open_time": [1], "close": [1e-9]})

    with pytest.raises(ValueError, match="underflow"):
        export_trace(df, "unused.csv")


def test_align_traces_survives_a_duplicated_timestamp():
    """A repeated minute must not shift the frames against each other.

    `isin` keeps every copy, so one duplicate left the frames at different
    lengths and mispaired every later price -- the precise failure this function
    exists to prevent, and it went unguarded.
    """
    left = pd.DataFrame({"open_time": [1, 2, 2, 3], "close": [1.0, 2.0, 2.5, 3.0]})
    right = pd.DataFrame({"open_time": [1, 2, 3], "close": [1.0, 2.0, 3.0]})

    a, b = align_traces(left, right)

    assert len(a) == len(b) == 3
    assert list(a["open_time"]) == list(b["open_time"]) == [1, 2, 3]
