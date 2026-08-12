import threading


class Worker:
    """Chạy việc nền, mỗi lệnh một luồng."""

    def __init__(self) -> None:
        self.done: list[int] = []
        self._threads: list[threading.Thread] = []
        self._lock = threading.Lock()

    def _run(self, value: int) -> None:
        with self._lock:
            self.done.append(value)

    def submit(self, value: int) -> None:
        self._threads = [t for t in self._threads if t.is_alive()]
        t = threading.Thread(target=self._run, args=(value,), daemon=True)
        t.start()
        self._threads.append(t)

    def wait(self) -> None:
        for t in self._threads:
            t.join()
        self._threads = [t for t in self._threads if t.is_alive()]
