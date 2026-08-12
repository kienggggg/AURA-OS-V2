from module import merge


def test_unsorted_input_is_handled():
    assert merge([(5, 7), (1, 3), (2, 4)]) == [(1, 4), (5, 7)]
