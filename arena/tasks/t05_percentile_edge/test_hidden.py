import pytest
from module import percentile


def test_median_odd():
    assert percentile([3.0, 1.0, 2.0], 50) == 2.0


def test_median_even():
    assert percentile([1.0, 2.0, 3.0, 4.0], 50) == 2.5


def test_p0_is_min():
    assert percentile([5.0, 1.0, 9.0], 0) == 1.0


def test_single_element_any_percentile():
    for p in (0, 25, 50, 99, 100):
        assert percentile([7.0], p) == 7.0


def test_p99_interpolates():
    got = percentile([0.0, 100.0], 99)
    assert abs(got - 99.0) < 1e-9


def test_empty_raises():
    with pytest.raises(ValueError):
        percentile([], 50)
