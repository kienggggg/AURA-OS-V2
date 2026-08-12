def load_plugins(loaders: list) -> tuple[list, list]:
    """Trả (đã nạp, hỏng).  Loader nào ném lỗi phải nằm ở danh sách HỎNG."""
    loaded: list[str] = []
    broken: list[str] = []
    for name, fn in loaders:
        try:
            fn()
        except Exception:
            pass
        loaded.append(name)
    return loaded, broken
