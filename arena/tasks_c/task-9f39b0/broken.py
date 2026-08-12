class Registry:
    """Sổ đăng ký người nghe; huỷ đăng ký phải giải phóng hoàn toàn."""

    def __init__(self) -> None:
        self.listeners: dict[str, object] = {}
        self.history: list[tuple[str, object]] = []

    def register(self, name: str, listener) -> None:
        self.listeners[name] = listener
        self.history.append((name, listener))

    def unregister(self, name: str) -> None:
        self.listeners.pop(name, None)

    def emit(self, value) -> None:
        for listener in list(self.listeners.values()):
            listener(value)
