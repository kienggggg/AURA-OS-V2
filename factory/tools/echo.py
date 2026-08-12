"""
factory/tools/echo.py
======================
Tool GIẢ (echo.sleep) — KHÔNG kiếm tiền, chỉ để kiểm chứng khung xưởng ở Phase 0:
hàng đợi sqlite, worker 1-job-1-lúc, progress live trên dashboard, và khả năng
TỰ HỒI PHỤC sau khi AURA khởi động lại giữa chừng một job. Có thể gỡ khỏi
TOOL_REGISTRY khi Phase 1 (video.factory) đã chạy ổn — không xoá file để giữ
làm ví dụ mẫu cho tool mới.
"""

from __future__ import annotations

import time
from typing import Callable

from factory.models import FormField, JobRecord, ToolSpec

ProgressFn = Callable[[int, str], None]


def run(job: JobRecord, progress: ProgressFn) -> None:
    total_steps = max(1, int(job.params.get("steps", 5)))
    # Resume sau restart: job.progress đã được sqlite giữ lại từ trước khi mồ côi.
    start_step = job.progress * total_steps // 100
    for i in range(start_step, total_steps):
        pct = int((i + 1) * 100 / total_steps)
        progress(pct, f"Bước giả {i + 1}/{total_steps}")
        time.sleep(2.0)


SPEC = ToolSpec(
    name="echo.sleep",
    label_vi="[Khung thử] Đếm bước giả",
    description="Tool giả kiểm tra hàng đợi + progress + tự hồi phục sau restart. "
                 "Không tạo ra sản phẩm thật.",
    product_line="_debug",
    form_fields=(
        FormField(key="steps", label="Số bước", type="number", default=5, required=False),
    ),
    handler=run,
)

__all__ = ["SPEC", "run"]
