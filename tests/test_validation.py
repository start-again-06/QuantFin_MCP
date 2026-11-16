import math

import pytest

from quant_mcp import validation as v


def test_check_series_rejects_nan_and_short():
    with pytest.raises(v.ValidationError):
        v.check_series([1.0, math.nan], "x")
    with pytest.raises(v.ValidationError):
        v.check_series([1.0], "x", min_length=2)


def test_check_series_rejects_strings():
    with pytest.raises(v.ValidationError):
        v.check_series("abc", "x")


def test_check_series_rejects_nested_lists():
    with pytest.raises(v.ValidationError):
        v.check_series([[1.0, 2.0], [3.0, 4.0]], "x")


def test_check_fraction_bounds():
    assert v.check_fraction(0.0, "f") == 0.0
    with pytest.raises(v.ValidationError):
        v.check_fraction(1.5, "f")
    with pytest.raises(v.ValidationError):
        v.check_fraction(0.0, "f", allow_zero=False)


def test_check_positive_int_rejects_bool_and_float():
    with pytest.raises(v.ValidationError):
        v.check_positive_int(True, "n")
    with pytest.raises(v.ValidationError):
        v.check_positive_int(2.0, "n")


def test_aligned_matrix_requires_equal_lengths():
    with pytest.raises(v.ValidationError):
        v.aligned_matrix({"a": [1.0, 2.0], "b": [1.0, 2.0, 3.0]})


def test_aligned_matrix_asset_limit():
    series = {f"A{i}": [0.1, 0.2] for i in range(v.MAX_ASSETS + 1)}
    with pytest.raises(v.ValidationError):
        v.aligned_matrix(series)
