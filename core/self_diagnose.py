"""
core/self_diagnose.py
====================
SelfDiagnose — "Mắt chẩn lỗi" của AURA.

Khi một tool/luồng của AURA chạy lỗi, dịch vụ này:
  1. Gói gọn TRACEBACK + ngữ cảnh (tool nào, tham số gì) — CHỈ dạng text.
  2. Gửi gói đó lên System 2 (Claude) qua BrainRouter để phân tích nguyên nhân.
  3. Bắn đề xuất cách sửa ra khung chat (event_queue -> broadcast) để Sếp DUYỆT.

RÀO BẢO MẬT (theo lệnh):
  - TẠM THỜI chỉ đọc traceback dạng text. KHÔNG chụp màn hình (tránh lộ dữ liệu).
  - Trước khi gửi lên cloud, lọc bớt thông tin nhạy cảm hiển nhiên (key, token,
    đường dẫn chứa tên người dùng) trong traceback.
  - SelfDiagnose chỉ ĐỀ XUẤT. Không tự sửa, không tự chạy lại. Sếp quyết.
"""

from __future__ import annotations

import logging
import traceback as tb_module
from dataclasses import dataclass

from brains.base import ChatMessage
from core.brain_router import BrainRouter
from core.redact import redact as _shared_redact
from core.schemas import Intent, IntentLabel, RouteTier, ToolResult

logger = logging.getLogger("aura.self_diagnose")

_SYSTEM_PROMPT = (
    "Bạn là kỹ sư Python cấp cao, chuyên chẩn đoán lỗi runtime. Sẽ nhận một "
    "traceback kèm ngữ cảnh. Hãy trả lời NGẮN GỌN, đúng trọng tâm, bằng tiếng Việt:\n"
    "1. NGUYÊN NHÂN: lỗi gốc là gì (1-2 câu).\n"
    "2. CÁCH SỬA: bước sửa cụ thể, hoặc đoạn code thay thế nếu rõ ràng.\n"
    "3. PHÒNG NGỪA: 1 câu để tránh lặp lại.\n"
    "Không dài dòng. Nếu thiếu thông tin, nói cần xem thêm gì."
)


@dataclass
class Diagnosis:
    """Kết quả chẩn đoán một lỗi."""

    ok: bool
    tool_name: str
    error_summary: str
    suggestion: str  # đề xuất từ Claude (hoặc thông báo nếu không lấy được)


class SelfDiagnose:
    """Dịch vụ chẩn lỗi: traceback -> hỏi đàn anh -> đề xuất ra UI."""

    def __init__(
        self,
        router: BrainRouter,
        event_queue=None,
    ) -> None:
        """
        Args:
            router: để gọi System 2 (Claude) phân tích.
            event_queue: hàng đợi broadcast ra UI (chia sẻ với server). Có thể None
                khi dùng độc lập (vd trong CLI) — khi đó chỉ trả Diagnosis.
        """
        self.router = router
        self.event_queue = event_queue

    # ------------------------------------------------------------------ #
    @staticmethod
    def redact(text: str) -> str:
        """Che thông tin nhạy cảm trong text trước khi gửi đi (dùng module chung)."""
        return _shared_redact(text)

    @staticmethod
    def capture_traceback(exc: BaseException) -> str:
        """Lấy traceback dạng text từ một exception đã bắt."""
        return "".join(
            tb_module.format_exception(type(exc), exc, exc.__traceback__)
        )

    # ------------------------------------------------------------------ #
    def _build_package(self, tool_name: str, traceback_text: str, context: str) -> str:
        """Gói traceback + ngữ cảnh thành prompt (đã che thông tin nhạy cảm)."""
        safe_tb = self.redact(traceback_text.strip())
        safe_ctx = self.redact(context.strip()) if context else "(không có)"
        return (
            f"[TOOL LỖI] {tool_name}\n"
            f"[NGỮ CẢNH] {safe_ctx}\n"
            f"[TRACEBACK]\n{safe_tb}"
        )

    def _ask_senior(self, package: str) -> ToolResult:
        """Hỏi System 2 (Claude). Ép tier CLOUD vì đây là việc suy luận sâu."""
        intent = Intent(
            label=IntentLabel.HEAVY_REASONING,
            tier=RouteTier.CLOUD,
            confidence=1.0,
            reason="self-diagnose forced cloud",
            raw_text=package,
        )
        messages: list[ChatMessage] = [{"role": "user", "content": package}]
        return self.router.run(messages, intent, system_prompt=_SYSTEM_PROMPT)

    # ------------------------------------------------------------------ #
    def diagnose(
        self, tool_name: str, traceback_text: str, context: str = ""
    ) -> Diagnosis:
        """
        Chẩn một lỗi từ traceback dạng text. KHÔNG ném exception.

        Trả Diagnosis; nếu có event_queue thì cũng bắn đề xuất ra UI để Sếp duyệt.
        """
        package = self._build_package(tool_name, traceback_text, context)
        result = self._ask_senior(package)

        if not result.ok:
            diag = Diagnosis(
                ok=False,
                tool_name=tool_name,
                error_summary=traceback_text.strip().splitlines()[-1][:200]
                if traceback_text.strip() else "(rỗng)",
                suggestion=(
                    "Chưa hỏi được đàn anh (Claude). Kiểm tra ANTHROPIC_API_KEY / mạng. "
                    f"Chi tiết: {result.error}"
                ),
            )
        else:
            last_line = (
                traceback_text.strip().splitlines()[-1][:200]
                if traceback_text.strip() else "(rỗng)"
            )
            diag = Diagnosis(
                ok=True,
                tool_name=tool_name,
                error_summary=last_line,
                suggestion=result.output,
            )

        self._maybe_emit(diag)
        return diag

    def diagnose_exception(
        self, tool_name: str, exc: BaseException, context: str = ""
    ) -> Diagnosis:
        """Tiện ích: chẩn trực tiếp từ một exception đã bắt."""
        return self.diagnose(tool_name, self.capture_traceback(exc), context)

    def diagnose_tool_result(self, result: ToolResult, context: str = "") -> Diagnosis:
        """
        Tiện ích: chẩn từ một ToolResult thất bại (tool đã nuốt exception, chỉ còn
        chuỗi error). Hữu ích để Orchestrator gọi ở nhánh OBSERVE khi tool fail.
        """
        return self.diagnose(result.tool_name, result.error or "(không có error)", context)

    # ------------------------------------------------------------------ #
    def _maybe_emit(self, diag: Diagnosis) -> None:
        """Bắn đề xuất ra UI qua event_queue (nếu có) để Sếp duyệt."""
        if self.event_queue is None:
            return
        text = (
            f"⚠️ Tool '{diag.tool_name}' gặp lỗi.\n"
            f"Lỗi: {diag.error_summary}\n\n"
            f"🩺 Đề xuất của đàn anh:\n{diag.suggestion}\n\n"
            f"Sếp muốn áp dụng cách sửa này không?"
        )
        try:
            self.event_queue.put_nowait({"type": "proactive", "text": text})
        except Exception as exc:  # noqa: BLE001 — queue đầy/đóng không nên làm sập
            logger.warning("Không đẩy được chẩn đoán ra UI: %s", exc)


__all__ = ["SelfDiagnose", "Diagnosis"]