import time
import pytest
from module import call_with_retry, Timeout


def test_success_returns_immediately():
    assert call_with_retry(lambda: 7, timeout=1.0) == 7


def test_recovers_on_second_attempt():
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 2:
            raise ValueError("chua on")
        return "ok"

    assert call_with_retry(flaky, timeout=1.0, attempts=3) == "ok"
    assert calls["n"] == 2


def test_attempts_exhausted_raises_timeout():
    with pytest.raises(Timeout):
        call_with_retry(lambda: (_ for _ in ()).throw(ValueError("x")),
                        timeout=5.0, attempts=2)


def test_deadline_is_total_not_per_attempt():
    def slow_failure():
        time.sleep(0.04)
        raise ValueError("hong")

    start = time.monotonic()
    with pytest.raises(Timeout):
        call_with_retry(slow_failure, timeout=0.06, attempts=10)
    assert time.monotonic() - start < 0.30


def test_no_call_after_deadline_passed():
    calls = {"n": 0}

    def counter():
        calls["n"] += 1
        time.sleep(0.03)
        raise ValueError("x")

    with pytest.raises(Timeout):
        call_with_retry(counter, timeout=0.05, attempts=20)
    assert calls["n"] <= 3
