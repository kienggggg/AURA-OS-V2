from module import truncate


def test_vietnamese_keeps_characters_not_bytes():
    text = "Đấu La Đại Lục hồi thứ nhất"
    got = truncate(text, 15)
    assert len(got) == 15, f"dai {len(got)} thay vi 15: {got!r}"
    assert got.endswith("...")
