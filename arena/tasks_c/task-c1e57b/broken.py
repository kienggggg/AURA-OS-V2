def deep_merge(base: dict, patch: dict) -> dict:
    """Gộp `patch` vào `base`, trả về dict MỚI.

    Quy ước: giá trị None trong patch nghĩa là XOÁ khoá đó.
    Danh sách thì THAY THẾ hẳn, không nối thêm.
    """
    out = dict(base)
    out.update(patch)
    return out
