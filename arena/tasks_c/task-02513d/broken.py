def latest_per_key(events: list[dict]) -> dict:
    """Giữ bản ghi MỚI NHẤT theo `ts` cho mỗi `key`.

    Nếu hai bản ghi trùng `ts`, giữ bản ghi ĐẾN SAU trong danh sách.
    """
    out: dict = {}
    for event in events:
        out[event["key"]] = event
    return out
