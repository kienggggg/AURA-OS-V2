"""
factory/tools/content_create.py
================================
content.factory — tạo content bán/đăng kênh (ĐỢT 2, chưa mở).

Slot đặt chỗ: kịch bản video, bài viết, caption theo trend — nối với công nhân
trend.radar (đã chạy trong crew) làm nguồn đề tài. Dashboard hiện form mờ
"sắp có"; enqueue bị chặn tới khi enabled=True.
"""

from __future__ import annotations

from factory.models import FormField, ToolSpec

SPEC = ToolSpec(
    name="content.factory",
    label_vi="Tạo content (kịch bản / bài viết)",
    description="Viết kịch bản video, bài viết, caption theo trend từ radar. "
                 "Đợt 2 — đang xây.",
    product_line="content",
    form_fields=(
        FormField(key="topic", label="Chủ đề / trend", type="textarea"),
        FormField(key="format", label="Định dạng", type="select",
                  choices=("kịch bản video", "bài viết", "caption"), required=False),
    ),
    handler=None,
    enabled=False,
)

__all__ = ["SPEC"]
