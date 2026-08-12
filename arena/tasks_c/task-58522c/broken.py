_GROUPS = {
    "a": "àáảãạăằắẳẵặâầấẩẫậ",
    "e": "èéẻẽẹêềếểễệ",
    "i": "ìíỉĩị",
    "o": "òóỏõọôồốổỗộơờớởỡợ",
    "u": "ùúủũụưừứửữự",
    "y": "ỳýỷỹỵ",
    "d": "đ",
}
_MAP = {ch: base for base, chars in _GROUPS.items() for ch in chars}
_MAP.update({ch.upper(): base.upper() for ch, base in list(_MAP.items())})


def strip_marks(text: str) -> str:
    """Bỏ dấu để so sánh: 'Ánh' -> 'Anh', 'Đức' -> 'Duc'."""
    return "".join(_MAP.get(ch, ch) for ch in text)


def sort_key(name: str) -> tuple:
    """Khoá sắp xếp BỎ DẤU; chữ có dấu đứng cạnh chữ gốc của nó."""
    return (name.lower(), name)


def sort_names(names: list[str]) -> list[str]:
    return sorted(names, key=sort_key)
