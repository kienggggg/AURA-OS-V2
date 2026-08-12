class TTLCache:
    """Bộ đệm có hạn dùng.  Ghi đè khoá thì hạn dùng ĐẶT LẠI từ đầu."""

    def __init__(self, ttl: float) -> None:
        self.ttl = ttl
        self._value: dict = {}
        self._stamp: dict = {}

    def put(self, key: str, value, now: float) -> None:
        if key not in self._stamp:
            self._stamp[key] = now
        self._value[key] = value

    def get(self, key: str, now: float):
        if key not in self._value:
            return None
        if now - self._stamp[key] > self.ttl:
            del self._value[key]
            del self._stamp[key]
            return None
        return self._value[key]
