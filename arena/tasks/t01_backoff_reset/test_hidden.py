from module import Backoff


def test_fresh_backoff_is_base():
    assert Backoff(base=2.0).delay() == 2.0


def test_single_failure_doubles():
    b = Backoff(base=1.0)
    b.record_failure()
    assert b.delay() == 2.0


def test_cap_is_respected():
    b = Backoff(base=1.0, cap=8.0)
    for _ in range(20):
        b.record_failure()
    assert b.delay() == 8.0


def test_success_after_long_outage_resets_fully():
    b = Backoff(base=0.5, cap=100.0)
    for _ in range(10):
        b.record_failure()
    b.record_success()
    assert b.delay() == 0.5
    assert b.failures == 0


def test_alternating_failure_success_does_not_creep():
    b = Backoff(base=1.0, cap=60.0)
    for _ in range(30):
        b.record_failure()
        b.record_failure()
        b.record_success()
    assert b.delay() == 1.0


def test_success_on_healthy_backoff_is_harmless():
    b = Backoff(base=1.0)
    b.record_success()
    assert b.delay() == 1.0
