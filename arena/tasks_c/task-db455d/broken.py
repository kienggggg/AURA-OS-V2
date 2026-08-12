class Config:
    """Nạp cấu hình một lần, lười.  Nạp lỗi thì lần sau phải THỬ LẠI."""

    def __init__(self, loader) -> None:
        self.loader = loader
        self._data: dict = {}
        self._loaded = False

    def get(self, key: str, default=None):
        if not self._loaded:
            self._loaded = True
            self._data = self.loader()
        return self._data.get(key, default)
