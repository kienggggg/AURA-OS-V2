def send_batch(items: list, sender) -> tuple[str, list]:
    """Trả ("OK", []) CHỈ KHI gửi được TẤT CẢ; nếu không, liệt kê mục hỏng."""
    failed: list = []
    any_ok = False
    for item in items:
        try:
            sender(item)
            any_ok = True
        except Exception:
            pass
    return ("OK" if any_ok else "FAILED", failed)
