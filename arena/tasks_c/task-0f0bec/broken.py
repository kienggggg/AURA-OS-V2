class Invoice:
    """Hoá đơn tính bằng đồng; tổng phải khớp tới từng xu."""

    def __init__(self) -> None:
        self.items: list[float] = []

    def add(self, amount: float) -> None:
        self.items.append(amount)

    def total(self) -> float:
        running = 0.0
        for amount in self.items:
            running += amount
        return running
