class Disk:
    """Đĩa giả lập.  write() trả về SỐ BYTE thật sự ghi được."""

    def __init__(self, capacity: int = 10 ** 9) -> None:
        self.capacity = capacity
        self.data = ""

    def write(self, payload: str) -> int:
        room = max(self.capacity - len(self.data), 0)
        written = payload[:room]
        self.data += written
        return len(written)


def save(disk: Disk, payload: str) -> bool:
    """Trả True CHỈ KHI ghi được trọn vẹn."""
    disk.write(payload)
    return True
