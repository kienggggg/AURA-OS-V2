"""
skills/system-power/scripts/power.py
====================================
System Power — CẤP 2: Ngủ đông PHẦN CỨNG (PC Hibernate). LỚP LOGIC (Level 4).

Cho cả laptop vào trạng thái ngủ của Windows qua rundll32 powrprof. Skill TIN CẬY
(hand-written), cố ý được phép gọi lệnh hệ thống — khác code TỰ SINH (bị CONTEXT §5
cấm os.system). Chốt chặn: chỉ chạy trên Windows + bọc try/except + luôn trả ToolResult.

Lưu ý: việc CHỜ SẾP GÕ 'Y' do Orchestrator gánh (Vibe Diff); tới khi gọi được hàm này
nghĩa là Sếp đã xác nhận.
"""

from __future__ import annotations

import sys
from pathlib import Path

# skills/system-power/scripts/power.py -> parents[3] = gốc dự án (cho `from core...`).
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import logging
import os

from core.schemas import ToolResult

logger = logging.getLogger("aura.skills.system_power")

_TOOL = "system.power"
# Lệnh Windows đưa máy vào trạng thái ngủ (SetSuspendState Hibernate,Force,WakeEvent).
_HIBERNATE_CMD = "rundll32.exe powrprof.dll,SetSuspendState 0,1,0"


def hibernate_laptop(**_ignored) -> ToolResult:
    """
    Cho LAPTOP ngủ đông (Sleep/Suspend) qua lệnh Windows powrprof.

    Trả ToolResult.success nếu phát lệnh được; .failure nếu không phải Windows hoặc
    lệnh trả mã lỗi. KHÔNG bao giờ ném exception ra ngoài.
    """
    if os.name != "nt":
        return ToolResult.failure(
            _TOOL,
            f"Chỉ chạy trên Windows (máy hiện tại os.name={os.name!r}). "
            "Bỏ qua để tránh lệnh nguy hiểm trên nền tảng khác.",
        )
    try:
        logger.info("PC HIBERNATE: phát lệnh ngủ phần cứng -> %s", _HIBERNATE_CMD)
        code = os.system(_HIBERNATE_CMD)   # noqa: S605 — skill tin cậy, lệnh cố định
    except Exception as exc:  # noqa: BLE001 — lỗi gọi lệnh không được làm sập AURA
        return ToolResult.failure(_TOOL, f"Không phát được lệnh ngủ: {exc}")

    if code != 0:
        return ToolResult.failure(
            _TOOL, f"Lệnh ngủ trả mã khác 0 ({code}). Kiểm tra quyền/cấu hình nguồn Windows.",
        )
    return ToolResult.success(
        _TOOL,
        output="💤 Đã phát lệnh cho laptop ngủ. Hẹn gặp lại Sếp khi bật máy!",
    )


# Alias theo quy ước CONTEXT §3 (tool_<tên>).
tool_system_power = hibernate_laptop


__all__ = ["hibernate_laptop", "tool_system_power"]
