def percentile(values: list[float], p: float) -> float:
    """Phân vị thứ p (0..100) theo phép nội suy tuyến tính."""
    if not values:
        raise ValueError("danh sach rong")
    ordered = sorted(values)
    pos = (len(ordered) - 1) * (p / 100.0)
    lower = int(pos)
    upper = min(lower + 1, len(ordered) - 1)
    frac = pos - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * frac
