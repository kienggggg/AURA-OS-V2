"""
skills/time-countdown/scripts/countdown.py
Tool do AURA tự sinh (Triad Council) — đếm ngược số ngày tới một ngày mục tiêu.
Hợp đồng: tool_days_to_target(**params) -> ToolResult.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Cho phép `from core...` chạy dù file được nạp qua importlib (chèn project root).
_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from datetime import datetime

from core.schemas import ToolResult


def tool_days_to_target(**params) -> ToolResult:
    try:
        target_date_str = params.get('target_date')
        if not target_date_str:
            return ToolResult.failure('time.days_to_target', 'Thiếu tham số target_date')
        try:
            target_date = datetime.strptime(target_date_str, '%Y-%m-%d')
        except ValueError:
            return ToolResult.failure('time.days_to_target', 'Định dạng target_date không đúng. Sử dụng YYYY-MM-DD')
        today = datetime.today()
        if target_date < today:
            return ToolResult.failure('time.days_to_target', 'Ngày mục tiêu không thể trước ngày hôm nay')
        days_left = (target_date - today).days
        return ToolResult.success('time.days_to_target', f'Còn {days_left} ngày đến {target_date_str}')
    except Exception as exc:
        return ToolResult.failure('time.days_to_target', str(exc))
