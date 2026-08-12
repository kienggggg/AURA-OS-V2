from module import Quota


def test_long_window_limit_is_enforced():
    q = Quota(burst=100, total=3)
    allowed = sum(1 for i in range(10) if q.allow(i * 2.0))
    assert allowed == 3, f"cho {allowed} luot trong khi tran la 3"
