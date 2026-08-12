def truncate(text: str, max_chars: int, suffix: str = "...") -> str:
    """Cắt còn tối đa `max_chars` KÝ TỰ, thêm hậu tố nếu bị cắt."""
    if len(text) <= max_chars:
        return text
    raw = text.encode("utf-8")[: max_chars - len(suffix)]
    return raw.decode("utf-8", errors="ignore") + suffix
