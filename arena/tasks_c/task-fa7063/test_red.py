from module import TokenBucket


def test_calls_at_the_same_instant_do_not_refill():
    b = TokenBucket(capacity=2.0, rate=1.0)
    b.take(0.0, 2.0)
    allowed = sum(1 for _ in range(10) if b.take(5.0))
    assert allowed <= 2, f"cung mot thoi diem ma cho {allowed} luot"
