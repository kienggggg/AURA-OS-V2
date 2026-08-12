from module import LRUCache


def test_recently_read_key_survives_eviction():
    c = LRUCache(capacity=2)
    c.put("a", 1)
    c.put("b", 2)
    assert c.get("a") == 1        # "a" vừa được dùng
    c.put("c", 3)                 # phải loại "b", không phải "a"
    assert c.get("a") == 1
    assert c.get("b") is None
