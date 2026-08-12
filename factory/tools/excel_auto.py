"""
factory/tools/excel_auto.py
============================
excel.factory — automation Excel/tài liệu (ĐỢT 2, chưa mở).

Slot đã đặt chỗ theo kế hoạch AURA v3: dọn dữ liệu, gộp file, báo cáo tự động
từ xlsx/csv — vừa bán dịch vụ freelance vừa dùng nội bộ. Dashboard hiện form
mờ "sắp có"; enqueue bị chặn tới khi enabled=True.
"""

from __future__ import annotations

from factory.models import FormField, ToolSpec

SPEC = ToolSpec(
    name="excel.factory",
    label_vi="Automation Excel / tài liệu",
    description="Dọn dữ liệu bẩn, gộp nhiều file, xuất báo cáo tự động từ "
                 "Excel/CSV. Đợt 2 — đang xây.",
    product_line="excel",
    form_fields=(
        FormField(key="files", label="Danh sách file Excel/CSV", type="textarea"),
        FormField(key="request", label="Yêu cầu xử lý", type="textarea"),
    ),
    handler=None,
    enabled=False,
)

__all__ = ["SPEC"]
