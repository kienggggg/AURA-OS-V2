from module import apply_edits


def test_delete_does_not_shift_later_indices():
    got = apply_edits(["a", "b", "c"], [("delete", 0, ""), ("replace", 2, "C")])
    assert got == ["b", "C"]
