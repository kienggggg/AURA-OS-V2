class RingLog:
    """Nhật ký chỉ giữ `limit` dòng gần nhất."""

    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.lines: list[str] = []

    def add(self, line: str) -> None:
        self.lines.append(line)
        if len(self.lines) > self.limit:
            self.lines.pop(0)

    def add_many(self, lines: list[str]) -> None:
        self.lines.extend(lines)
