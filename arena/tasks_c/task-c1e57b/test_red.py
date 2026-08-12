from module import deep_merge


def test_nested_dict_is_merged_not_replaced():
    got = deep_merge({"a": {"x": 1, "y": 2}}, {"a": {"y": 9}})
    assert got == {"a": {"x": 1, "y": 9}}
