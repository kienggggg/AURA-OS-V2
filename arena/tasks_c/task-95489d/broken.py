class Quota:
    """Cho tối đa `burst` lượt trong 1 giây VÀ `total` lượt trong 60 giây.

    Lượt bị TỪ CHỐI không được tính vào bất kỳ hạn mức nào.
    """

    def __init__(self, burst: int, total: int) -> None:
        self.burst = burst
        self.total = total
        self.events: list[float] = []

    def allow(self, now: float) -> bool:
        self.events.append(now)
        recent = [t for t in self.events if now - t < 1.0]
        return len(recent) <= self.burst
