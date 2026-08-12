from module import wrap


def test_word_longer_than_width_is_split():
    got = wrap("abcdefghij", 4)
    assert all(len(l) <= 4 for l in got), got
    assert "".join(got) == "abcdefghij"
