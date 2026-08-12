from module import encode, decode


def test_value_containing_separator_survives():
    values = ["a,b", "c"]
    assert decode(encode(values)) == values
