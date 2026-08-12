class Transport:
    """Đường truyền thật — chỉ nó biết gói tin có đi hay không."""

    def __init__(self) -> None:
        self.delivered: list[str] = []
        self.up = True

    def deliver(self, payload: str) -> None:
        if not self.up:
            raise ConnectionError("duong truyen dut")
        self.delivered.append(payload)


class Sender:
    def __init__(self, transport: Transport) -> None:
        self.transport = transport
        self.outbox: list[str] = []

    def send(self, payload: str) -> str:
        self.outbox.append(payload)
        return "SENT"

    def flush(self) -> int:
        sent = 0
        for payload in self.outbox:
            self.transport.deliver(payload)
            sent += 1
        return sent
