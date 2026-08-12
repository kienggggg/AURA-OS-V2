def slot_for(sorted_values: list, value) -> int:
    """Vị trí chèn `value` giữ được thứ tự.  Nếu đã có, chèn TRƯỚC mục bằng nó."""
    low, high = 0, len(sorted_values)
    while low < high:
        mid = (low + high) // 2
        if sorted_values[mid] <= value:
            low = mid + 1
        else:
            high = mid
    return low
