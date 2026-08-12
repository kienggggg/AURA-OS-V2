class Backoff:
    """Giãn cách thử lại.

    Hợp đồng: sau MỘT lần thành công, giãn cách quay về mức đầu (`base`).
    """

    def __init__(self, base: float = 1.0, cap: float = 60.0) -> None:
        self.base = base
        self.cap = cap
        self.failures = 0

    def record_failure(self) -> None:
        self.failures += 1

    def record_success(self) -> None:
        self.failures = 0

    def delay(self) -> float:
        return min(self.cap, self.base * (2 ** self.failures))
