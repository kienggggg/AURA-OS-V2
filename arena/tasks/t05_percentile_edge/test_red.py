from module import percentile


def test_p100_does_not_crash():
    assert percentile([1.0, 2.0, 3.0], 100) == 3.0
