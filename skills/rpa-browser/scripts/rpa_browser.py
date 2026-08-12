"""
skills/rpa-browser/scripts/rpa_browser.py
=========================================
RPA Browser — "Lướt web bằng tay thật" (LỚP LOGIC, Level 4).

AURA giành lấy CHUỘT + BÀN PHÍM vật lý (pyautogui) để mở trình duyệt, focus thanh địa
chỉ, gõ từ khoá và cuộn trang — lướt web trực quan ngay trên màn hình của Sếp.

Đây là skill TIN CẬY (hand-written), cố ý được phép điều khiển thiết bị nhập — khác
code TỰ SINH (bị ASTValidator/CONTEXT §5 cấm). Lá chắn: Kill Switch FAILSAFE + cổng
VIBE DIFF duyệt từng lần ở tầng Orchestrator + bọc try/except trả ToolResult (§2, §8).

Tool công khai `search_web_physical(...)` LUÔN trả ToolResult (không ném exception).
"""

from __future__ import annotations

import sys
from pathlib import Path

# skills/rpa-browser/scripts/rpa_browser.py -> parents[3] = gốc dự án (cho `from core...`).
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import logging
import time

from core.schemas import ToolResult

logger = logging.getLogger("aura.skills.rpa_browser")

_TOOL = "rpa.browser"

# AURA-DEPS: pyautogui  # điều khiển chuột/bàn phím vật lý (least-privilege: chỉ nhập liệu)
# ---------------------------------------------------------------------------
# KILL SWITCH — bật ngay khi nạp module.
#   >>> Kéo MẠNH chuột vào 1 TRONG 4 GÓC màn hình để DỪNG KHẨN CẤP <<<
# pyautogui sẽ ném FailSafeException -> skill nuốt gọn, trả ToolResult.failure.
# Import MỀM: thiếu pyautogui (hoặc máy headless) thì module vẫn nạp được, chỉ báo lỗi
# rõ khi thực sự gọi — không làm sập registry/AURA.
# ---------------------------------------------------------------------------
try:
    import pyautogui  # type: ignore

    pyautogui.FAILSAFE = True   # Kill Switch: kéo chuột vào góc màn hình để dừng khẩn cấp
    pyautogui.PAUSE = 0.4       # nghỉ nhẹ giữa mỗi lệnh cho UI kịp phản ứng
    _IMPORT_ERR: Exception | None = None
except Exception as exc:  # noqa: BLE001 — thiếu lib/headless không được làm sập module
    pyautogui = None  # type: ignore[assignment]
    _IMPORT_ERR = exc


import math
import random


def human_type(text: str, base_interval: float = 0.06, variation: float = 0.04) -> None:
    """Gõ phím với nhịp điệu sinh học tự nhiên (chống phát hiện bot bằng keystroke dynamics)."""
    if not pyautogui:
        return
    for char in text:
        pyautogui.write(char)
        # Giữa các từ (dấu cách, câu) có độ trễ nghỉ tư duy nhẹ
        if char in " .,?!":
            time.sleep(random.uniform(0.12, 0.35))
        else:
            time.sleep(max(0.01, base_interval + random.uniform(-variation, variation)))


def human_move(target_x: int, target_y: int, duration: float = 0.6) -> None:
    """Di chuyển chuột theo đường cong Bezier sinh học (chống anti-bot lướt đường thẳng)."""
    if not pyautogui:
        return
    start_x, start_y = pyautogui.position()
    steps = max(10, int(duration * 60))
    # Điểm uốn ngẫu nhiên tạo đường cong tự nhiên
    ctrl_x = (start_x + target_x) / 2 + random.randint(-80, 80)
    ctrl_y = (start_y + target_y) / 2 + random.randint(-80, 80)

    for i in range(steps + 1):
        t = i / steps
        # Đường cong Bezier bậc 2
        x = (1 - t) ** 2 * start_x + 2 * (1 - t) * t * ctrl_x + t**2 * target_x
        y = (1 - t) ** 2 * start_y + 2 * (1 - t) * t * ctrl_y + t**2 * target_y
        pyautogui.moveTo(int(x), int(y))
        time.sleep(duration / steps)


def _press(keys: str) -> None:
    """Bấm tổ hợp phím (vd 'win,s' hoặc 'ctrl,l') hoặc 1 phím đơn ('enter')."""
    parts = [k.strip() for k in keys.split(",") if k.strip()]
    if len(parts) == 1:
        pyautogui.press(parts[0])
    else:
        pyautogui.hotkey(*parts)


def search_web_physical(
    query: str = "",
    browser: str = "chrome",
    scrolls: int = 3,
    **_ignored,
) -> ToolResult:
    """
    Lướt web trực quan: mở `browser` qua Win+S -> Ctrl+L -> gõ `query` -> Enter -> cuộn.

    Tham số:
        query   : từ khoá tìm kiếm (BẮT BUỘC, không rỗng).
        browser : tên trình duyệt để Win+S mở (mặc định 'chrome'; vd 'edge').
        scrolls : số nhịp cuộn xuống sau khi trang load (mặc định 3).

    Trả ToolResult.success kèm tóm tắt thao tác, hoặc .failure nếu thiếu lib / tham số
    sai / Sếp bấm Kill Switch / lỗi runtime. KHÔNG bao giờ ném exception ra ngoài.
    """
    start = time.monotonic()

    # 1) Tiền điều kiện: có pyautogui chưa?
    if pyautogui is None:
        return ToolResult.failure(
            _TOOL,
            f"Thiếu/không nạp được 'pyautogui' ({_IMPORT_ERR}). "
            f"Cài: pip install pyautogui (Windows cần phiên đăng nhập đồ hoạ, không headless).",
        )

    # 2) Validate đầu vào (CONTEXT §7) — không tin tham số do LLM bóc.
    query = (query or "").strip()
    if not query:
        return ToolResult.failure(_TOOL, "Thiếu 'query' — cần từ khoá để tìm kiếm.")
    browser = (browser or "chrome").strip() or "chrome"
    try:
        scrolls = max(0, min(int(scrolls), 10))   # kẹp 0..10 nhịp cho an toàn
    except (TypeError, ValueError):
        scrolls = 3

    # 3) Kịch bản thao tác vật lý. Bọc try/except: Kill Switch hay lỗi gì cũng -> ToolResult.
    try:
        logger.info("RPA: mở '%s' rồi tìm '%s'.", browser, query)

        # (a) Win + S -> ô tìm kiếm Windows; gõ tên trình duyệt; Enter mở nó.
        _press("win,s")
        time.sleep(1.2)                              # chờ Windows Search bật
        human_type(browser)
        time.sleep(0.6)
        _press("enter")
        time.sleep(4.0)                              # ĐỢI trình duyệt thật sự mở ra

        # (b) Ctrl + L -> focus thanh địa chỉ (chuẩn cho Chrome/Edge/Firefox).
        time.sleep(3.0)                              # thêm nhịp đệm cho chắc tab đã sẵn sàng
        _press("ctrl,l")
        time.sleep(0.8)

        # (c) Gõ từ khoá -> Enter (trình duyệt tự tìm qua search engine mặc định).
        human_type(query)
        time.sleep(0.3)
        _press("enter")
        time.sleep(4.0)                              # ĐỢI trang kết quả load xong

        # (d) Cuộn xuống vài nhịp để Sếp thấy nội dung.
        for _ in range(scrolls):
            pyautogui.scroll(-500)                   # số âm = cuộn XUỐNG
            time.sleep(0.6)

    except Exception as exc:  # noqa: BLE001 — gồm cả FailSafeException khi Sếp dừng khẩn cấp
        name = type(exc).__name__
        if "FailSafe" in name:
            return ToolResult.failure(
                _TOOL, "Đã DỪNG KHẨN CẤP (Sếp kéo chuột vào góc màn hình). Huỷ thao tác.",
                int((time.monotonic() - start) * 1000),
            )
        return ToolResult.failure(
            _TOOL, f"Lỗi khi điều khiển chuột/bàn phím: {name}: {exc}",
            int((time.monotonic() - start) * 1000),
        )

    elapsed = int((time.monotonic() - start) * 1000)
    return ToolResult.success(
        _TOOL,
        output=(
            f"Đã lướt web vật lý: mở '{browser}', tìm '{query}', "
            f"cuộn {scrolls} nhịp. (Nếu trình duyệt mở chậm hơn, tăng time.sleep.)"
        ),
        elapsed_ms=elapsed,
    )


# Alias theo quy ước CONTEXT §3 (tool_<tên>) — trỏ về cùng một hàm.
tool_rpa_browser = search_web_physical


__all__ = ["search_web_physical", "tool_rpa_browser"]
