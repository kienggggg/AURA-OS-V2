"""
factory/
========
Xưởng kiếm tiền — công dân hạng nhất của AURA v3.

Mọi "tool kiếm tiền" (dịch video hàng loạt, dịch truyện chữ, dịch/tạo truyện
tranh, ...) đều là một ToolSpec đăng ký trong factory.tools, chạy qua MỘT hàng
đợi job bền (factory.queue) do MỘT worker duy nhất xử lý (factory.worker) —
để tôn trọng RAM 12GB của máy (1 job nặng/lúc) và tự phục hồi sau khi AURA
khởi động lại (job "running" mồ côi được requeue).

Dashboard web (interface/dashboard.py) và skill chat (skills/factory/) đều
đi qua CÙNG hàng đợi này — không có hai đường thực thi song song.
"""

from __future__ import annotations
