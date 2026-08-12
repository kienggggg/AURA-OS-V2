class MovingAverage:
    """Trung bình của `size` mẫu GẦN NHẤT."""

    def __init__(self, size: int) -> None:
        self.size = size
        self.samples: list[float] = []
        self.total = 0.0

    def add(self, value: float) -> None:
        self.samples.append(value)
        self.total += value
        if len(self.samples) > self.size:
            self.samples.pop(0)

    def value(self) -> float:
        if not self.samples:
            return 0.0
        return self.total / len(self.samples)
