class TokenBucket:
    """Cho `capacity` lượt, nạp lại `rate` lượt mỗi giây, không vượt sức chứa."""

    def __init__(self, capacity: float, rate: float) -> None:
        self.capacity = capacity
        self.rate = rate
        self.tokens = capacity
        self.last = 0.0

    def take(self, now: float, amount: float = 1.0) -> bool:
        self.tokens = min(self.capacity, self.tokens + (now - self.last) * self.rate)
        if self.tokens >= amount:
            self.tokens -= amount
            return True
        return False
