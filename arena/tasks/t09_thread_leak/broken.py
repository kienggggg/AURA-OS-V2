import threading


class Worker:
    """Chạy việc nền, mỗi lệnh một luồng."""

    def __init__(self) -> None:
        self.done: list[int] = []
        self._threads: list[threading.Thread] = []

    def submit(self, value: int) -> None:
        t = threading.Thread(target=self.done.append, args=(value,), daemon=True)
        t.start()
        self._threads.append(t)

    def wait(self) -> None:
        for t in self._threads:
            t.join()
