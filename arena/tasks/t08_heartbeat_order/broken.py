class Watchdog:
    """Ngắt nếu quá `timeout` giây không có nhịp tim."""

    def __init__(self, timeout: float) -> None:
        self.timeout = timeout
        self.last_seen: float | None = None
        self.stopped = False

    def ping(self, now: float) -> None:
        if self.last_seen is not None and now - self.last_seen > self.timeout:
            self.stopped = True
        if not self.stopped:
            self.last_seen = now

    def tick(self, now: float) -> bool:
        if self.last_seen is not None and now - self.last_seen > self.timeout:
            self.stopped = True
        return not self.stopped
