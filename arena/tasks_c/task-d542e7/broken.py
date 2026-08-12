def attempt(fn, attempts: int):
    """Gọi fn TỐI ĐA `attempts` lần; hỏng hết thì ném lỗi cuối cùng."""
    last = None
    for _ in range(attempts + 1):
        try:
            return fn()
        except Exception as exc:
            last = exc
    raise last
