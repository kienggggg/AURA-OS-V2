from module import Store, normalize_key


def test_lowercase_still_works():
    s = Store()
    s.save("abc", 1)
    assert s.load("abc") == 1


def test_whitespace_ignored_both_sides():
    s = Store()
    s.save("  k  ", 5)
    assert s.load("k") == 5
    assert s.load("   k ") == 5


def test_mixed_case_lookup():
    s = Store()
    s.save("AURA", "x")
    assert s.load("aura") == "x"
    assert s.load("AuRa") == "x"


def test_missing_returns_default():
    assert Store().load("zzz", "def") == "def"


def test_normalize_key_contract_unchanged():
    assert normalize_key("  Ab ") == "ab"
