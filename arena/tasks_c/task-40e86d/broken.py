class Cache:
    """Bộ đệm có phụ thuộc.  invalidate(x) phải xoá mọi mục phụ thuộc x,
    kể cả phụ thuộc GIÁN TIẾP qua nhiều tầng."""

    def __init__(self) -> None:
        self.values: dict[str, object] = {}
        self.deps: dict[str, set[str]] = {}

    def put(self, key: str, value, depends_on=()) -> None:
        self.values[key] = value
        self.deps[key] = set(depends_on)

    def get(self, key: str, default=None):
        return self.values.get(key, default)

    def invalidate(self, key: str) -> None:
        self.values.pop(key, None)
        self.deps.pop(key, None)
