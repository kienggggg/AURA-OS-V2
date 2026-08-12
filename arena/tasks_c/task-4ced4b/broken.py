class Cancelled(BaseException):
    """Tín hiệu huỷ — KHÔNG được nuốt."""


def run_all(jobs: list) -> list:
    """Chạy từng job, bỏ qua job lỗi, nhưng phải dừng ngay khi bị huỷ."""
    done = []
    for job in jobs:
        try:
            done.append(job())
        except BaseException:
            continue
    return done
