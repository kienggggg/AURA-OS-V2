def normalize_key(raw: str) -> str:
    """Chuẩn hoá khoá trước khi LƯU."""
    return raw.strip().lower()


class Store:
    def __init__(self) -> None:
        self._data: dict[str, object] = {}

    def save(self, raw_key: str, value) -> None:
        self._data[normalize_key(raw_key)] = value

    def load(self, raw_key: str, default=None):
        return self._data.get(normalize_key(raw_key), default)
