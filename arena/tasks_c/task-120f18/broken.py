def merge(intervals: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Gộp các khoảng chồng lấn HOẶC chạm nhau, trả về danh sách đã sắp xếp.

    (1, 3) và (3, 5) là CHẠM NHAU, phải gộp thành (1, 5).
    """
    out: list[tuple[int, int]] = []
    for start, end in intervals:
        if out and start < out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], end))
        else:
            out.append((start, end))
    return out
