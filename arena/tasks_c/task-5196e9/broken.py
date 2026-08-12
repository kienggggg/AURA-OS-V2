def wrap(text: str, width: int) -> list[str]:
    """Ngắt dòng theo `width` ký tự, không cắt giữa từ.

    Từ dài hơn `width` thì buộc phải cắt.
    Xuống dòng có sẵn trong `text` phải được GIỮ NGUYÊN, kể cả dòng trống.
    """
    out: list[str] = []
    line = ""
    for word in text.split():
        if line and len(line) + 1 + len(word) > width:
            out.append(line)
            line = word
        else:
            line = f"{line} {word}" if line else word
    if line:
        out.append(line)
    return out
