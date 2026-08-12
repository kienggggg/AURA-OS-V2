from module import Cache


def test_direct_dependent_is_dropped():
    c = Cache()
    c.put("raw", 1)
    c.put("view", 2, depends_on=["raw"])
    c.invalidate("raw")
    assert c.get("view") is None
