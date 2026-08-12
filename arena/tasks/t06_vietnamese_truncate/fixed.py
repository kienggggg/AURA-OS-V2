def truncate(text: str, max_chars: int, suffix: str = "...") -> str:
    """Cắt còn tối đa `max_chars` KÝ TỰ, thêm hậu tố nếu bị cắt.

    Kết quả KHÔNG BAO GIỜ dài quá `max_chars`, kể cả khi hậu tố dài hơn
    giới hạn — lúc đó chính hậu tố bị cắt.
    """
    if len(text) <= max_chars:
        return text
    if max_chars <= 0:
        return ""
    if len(suffix) >= max_chars:
        return suffix[:max_chars]
    return text[: max_chars - len(suffix)] + suffix
