import time
import pytest
from module import call_with_retry, Timeout


def test_total_time_respects_timeout():
    def slow_failure():
        time.sleep(0.05)
        raise ValueError("hong")

    start = time.monotonic()
    with pytest.raises(Timeout):
        call_with_retry(slow_failure, timeout=0.08, attempts=5)
    elapsed = time.monotonic() - start
    assert elapsed < 0.25, f"tong thoi gian {elapsed:.3f}s vuot tran"
