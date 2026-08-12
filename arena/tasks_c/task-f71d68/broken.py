class Journal:
    """Ghi việc vào sổ; chỉ đánh dấu xong khi ghi đĩa thành công."""

    def __init__(self, sink) -> None:
        self.sink = sink
        self.committed: list[str] = []

    def write(self, entry: str) -> None:
        self.committed.append(entry)
        self.sink(entry)
