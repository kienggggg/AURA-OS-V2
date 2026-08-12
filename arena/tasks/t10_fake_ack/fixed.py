class MotorDriver:
    """Phần cứng giả lập: chỉ nó mới biết bánh có quay hay không."""

    def __init__(self) -> None:
        self.position = 0.0
        self.online = True

    def drive(self, direction: str, seconds: float) -> None:
        if not self.online:
            raise RuntimeError("driver offline")
        step = {"forward": 1.0, "backward": -1.0}[direction]
        self.position += step * seconds


class Rover:
    def __init__(self, driver: MotorDriver) -> None:
        self.driver = driver
        self.log: list[str] = []

    def move(self, direction: str, seconds: float) -> str:
        self.driver.drive(direction, seconds)
        self.log.append(f"{direction}:{seconds}")
        return f"ACK:{direction.upper()}"
