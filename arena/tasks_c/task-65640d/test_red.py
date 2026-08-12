from module import TTLCache


def test_overwrite_resets_the_clock():
    cache = TTLCache(ttl=6.0)
    cache.put("k", "cu", now=0.0)
    cache.put("k", "moi", now=5.0)
    assert cache.get("k", now=8.0) == "moi", "ghi de roi ma van tinh han tu lan dau"
