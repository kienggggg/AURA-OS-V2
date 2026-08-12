from module import split


def test_total_is_preserved():
    assert sum(split(100, 3)) == 100
