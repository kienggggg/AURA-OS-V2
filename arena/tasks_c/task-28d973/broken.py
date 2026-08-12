class Pool:
    """Kho tài nguyên dùng lại.  release() phải trả về đúng trạng thái rảnh."""

    def __init__(self, size: int) -> None:
        self.free = list(range(size))
        self.in_use: list[int] = []

    def acquire(self) -> int:
        if not self.free:
            raise RuntimeError("het tai nguyen")
        item = self.free.pop()
        self.in_use.append(item)
        return item

    def release(self, item: int) -> None:
        self.free.append(item)
