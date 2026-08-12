class Store:
    """Giữ một giá trị; báo cho người nghe SAU KHI đã cập nhật."""

    def __init__(self) -> None:
        self.value = None
        self.listeners: list = []

    def subscribe(self, fn) -> None:
        self.listeners.append(fn)

    def set(self, value) -> None:
        for fn in list(self.listeners):
            fn(value)
        self.value = value
