import time


class Timeout(Exception):
    pass


def call_with_retry(fn, timeout: float, attempts: int = 5, sleep: float = 0.0):
    """Gọi fn, thử lại tối đa `attempts` lần, TỔNG thời gian không quá `timeout`."""
    deadline = time.monotonic() + timeout
    last_error = None
    for _ in range(attempts):
        if time.monotonic() >= deadline:
            raise Timeout("het han") from last_error
        try:
            return fn()
        except Exception as exc:
            last_error = exc
            if time.monotonic() >= deadline:
                raise Timeout("het han") from exc
            if sleep:
                time.sleep(sleep)
    raise Timeout("het so lan thu") from last_error
