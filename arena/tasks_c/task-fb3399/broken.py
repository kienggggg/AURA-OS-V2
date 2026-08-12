class Budget:
    """Ngân sách thời gian dùng chung cho cả chuỗi bước."""

    def __init__(self, total_s: float) -> None:
        self.total_s = total_s
        self.spent = 0.0

    def remaining(self) -> float:
        return self.total_s - self.spent

    def charge(self, seconds: float) -> None:
        self.spent += seconds


def run_steps(steps: list, budget: Budget) -> list:
    """Chạy tuần tự; dừng khi hết ngân sách."""
    out = []
    for step in steps:
        cost, value = step()
        out.append(value)
        budget.charge(cost)
    return out
