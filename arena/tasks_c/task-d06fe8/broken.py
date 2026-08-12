def encode(values: list[str]) -> str:
    """Ghép danh sách thành một dòng; decode phải khôi phục Y NGUYÊN."""
    return ",".join(values)


def decode(line: str) -> list[str]:
    return line.split(",") if line else []
