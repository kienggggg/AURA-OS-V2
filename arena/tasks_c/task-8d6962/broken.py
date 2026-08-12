def split(total_cents: int, people: int) -> list[int]:
    """Chia tiền cho `people` người.

    Hợp đồng: tổng phải ĐÚNG BẰNG `total_cents`, và hai người bất kỳ
    không được chênh nhau quá 1 xu.
    """
    if people <= 0:
        raise ValueError("people phai duong")
    share = total_cents // people
    return [share] * people
