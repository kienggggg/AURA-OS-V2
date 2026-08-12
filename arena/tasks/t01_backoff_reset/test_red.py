from module import Backoff


def test_one_success_returns_to_base_delay():
    b = Backoff(base=1.0, cap=60.0)
    for _ in range(5):
        b.record_failure()
    b.record_success()
    assert b.delay() == 1.0, f"sau 1 lan thanh cong van cho {b.delay()}s"
