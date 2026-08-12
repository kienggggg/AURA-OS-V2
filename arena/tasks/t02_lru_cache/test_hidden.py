from module import LRUCache


def test_basic_put_get():
    c = LRUCache(2)
    c.put("x", 10)
    assert c.get("x") == 10


def test_missing_key_returns_default():
    assert LRUCache(2).get("nope", "d") == "d"


def test_capacity_never_exceeded():
    c = LRUCache(3)
    for i in range(50):
        c.put(f"k{i}", i)
    assert len(c._data) == 3


def test_repeated_reads_keep_key_alive():
    c = LRUCache(2)
    c.put("a", 1)
    c.put("b", 2)
    for _ in range(5):
        c.get("a")
    c.put("c", 3)
    assert c.get("a") == 1


def test_overwrite_refreshes_recency():
    c = LRUCache(2)
    c.put("a", 1)
    c.put("b", 2)
    c.put("a", 9)
    c.put("c", 3)
    assert c.get("a") == 9
    assert c.get("b") is None
