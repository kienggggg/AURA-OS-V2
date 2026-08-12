from module import truncate


def test_short_text_untouched():
    assert truncate("abc", 10) == "abc"


def test_ascii_truncation_length():
    got = truncate("abcdefghij", 6)
    assert len(got) == 6
    assert got.endswith("...")


def test_no_replacement_or_mojibake():
    text = "Sếp ơi, xe đã chạy thẳng rồi ạ"
    got = truncate(text, 12)
    assert "\ufffd" not in got
    assert len(got) == 12


def test_exact_boundary_not_truncated():
    assert truncate("Đấu La", 6) == "Đấu La"


def test_all_multibyte():
    got = truncate("ăâêôơư" * 5, 8)
    assert len(got) == 8


def test_never_exceeds_limit_at_any_size():
    text = "Đấu La Đại Lục hồi thứ nhất"
    for limit in (0, 1, 2, 3, 4, 7, 15, 26):
        got = truncate(text, limit)
        assert len(got) <= limit, f"limit={limit} nhung tra ve {len(got)} ky tu: {got!r}"


def test_zero_limit_returns_empty():
    assert truncate("Đấu La", 0) == ""


def test_long_custom_suffix_is_itself_trimmed():
    got = truncate("Đấu La Đại Lục", 4, suffix="[da cat]")
    assert len(got) <= 4


def test_suffix_shorter_than_limit_keeps_content():
    got = truncate("Đấu La Đại Lục", 6)
    assert len(got) == 6
    assert got.endswith("...")
    assert got[0] == "Đ"
