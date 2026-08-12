"""
core/agent_broker.py
===================
AgentBroker — "Nhà thầu chính" (A2A orchestration).

Nâng cấp BrainRouter: ngoài định tuyến Local/Cloud, AURA có thể GIAO VIỆC cho các
"đàn anh" (model/dịch vụ AI chuyên dụng) khi task vượt khả năng local — qua MỘT
cổng chuẩn hoá duy nhất `delegate()`, không wrapper chắp vá cho từng API.

Hai lớp rào bắt buộc trước khi dữ liệu rời máy:
  Lớp 1 — Ngân sách (BudgetGuard): đếm request/token. Việc trả phí phải bắn thông
          báo ra UI (event_queue) cho Sếp DUYỆT trước khi chạy.
  Lớp 2 — Redact (core/redact): che API key, token, tên user trong payload.

AgentBroker kế thừa BrainRouter nên giữ nguyên route_intent()/run() cũ; phần giao
việc cho đàn anh là năng lực CỘNG THÊM.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field

from brains.base import ChatMessage, LLMBackend
from core.brain_router import BrainRouter
from core.redact import redact_messages
from core.schemas import Intent, IntentLabel, RouteTier, ToolResult

logger = logging.getLogger("aura.agent_broker")


# ---------------------------------------------------------------------------
# Hồ sơ một "đàn anh" — chuẩn hoá để mọi backend nhìn giống nhau
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class SeniorSpec:
    """
    Mô tả chuẩn hoá một đàn anh (model/dịch vụ AI) AURA có thể giao việc.

    Mọi đàn anh đều là một LLMBackend (cùng giao diện chat/think) — đây chính là
    "một cổng chuẩn hoá" tránh wrapper riêng lẻ. Thêm metadata để Broker chọn đúng
    đàn anh cho đúng việc và tính phí.
    """

    name: str
    backend: LLMBackend
    skills: frozenset[str]      # vd {"translate", "vision", "reasoning", "code"}
    is_paid: bool               # True nếu gọi tốn tiền -> cần Sếp duyệt
    cost_per_call: float = 0.0  # ước lượng chi phí mỗi call (để cảnh báo ngân sách)


# ---------------------------------------------------------------------------
# Lớp 1 — Quản lý ngân sách
# ---------------------------------------------------------------------------
@dataclass
class BudgetGuard:
    """
    Đếm số request/token đã dùng và chặn khi vượt hạn mức.

    Thread-safe (Broker có thể bị gọi từ nhiều luồng qua asyncio.to_thread).
    """

    max_requests: int = 100
    max_tokens: int = 200_000
    used_requests: int = 0
    used_tokens: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def can_afford(self, est_tokens: int = 0) -> tuple[bool, str]:
        """Kiểm còn hạn mức không. Trả (được/không, lý do nếu không)."""
        with self._lock:
            if self.used_requests >= self.max_requests:
                return False, f"Hết hạn mức request ({self.max_requests})."
            if self.used_tokens + est_tokens > self.max_tokens:
                return False, f"Vượt hạn mức token ({self.max_tokens})."
            return True, ""

    def charge(self, tokens: int = 0) -> None:
        """Ghi nhận một lần dùng."""
        with self._lock:
            self.used_requests += 1
            self.used_tokens += tokens

    def snapshot(self) -> str:
        with self._lock:
            return (f"{self.used_requests}/{self.max_requests} req, "
                    f"{self.used_tokens}/{self.max_tokens} tok")


# ---------------------------------------------------------------------------
# Hàm phê duyệt việc trả phí (mặc định: bắn UI, chờ Sếp). Có thể inject để test.
# ---------------------------------------------------------------------------
def _estimate_tokens(messages: list[ChatMessage], system_prompt: str | None) -> int:
    """Ước lượng thô số token (≈ ký tự / 4). Đủ để cảnh báo ngân sách."""
    total = sum(len(m.get("content", "")) for m in messages)
    total += len(system_prompt or "")
    return total // 4


# ---------------------------------------------------------------------------
# AgentBroker
# ---------------------------------------------------------------------------
class AgentBroker(BrainRouter):
    """Nhà thầu chính: định tuyến + giao việc cho đàn anh, có ngân sách & redact."""

    def __init__(
        self,
        local: LLMBackend,
        cloud: LLMBackend | None = None,
        seniors: list[SeniorSpec] | None = None,
        budget: BudgetGuard | None = None,
        event_queue=None,
        approve_paid_fn=None,
        max_local_attempts: int = 2,
    ) -> None:
        super().__init__(local, cloud, max_local_attempts)
        # Sổ đàn anh: tra theo tên.
        self._seniors: dict[str, SeniorSpec] = {
            s.name: s for s in (seniors or [])
        }
        self.budget = budget or BudgetGuard()
        self.event_queue = event_queue
        # Cổng duyệt việc trả phí: (mô tả) -> True/False. Mặc định CHẶN (an toàn):
        # nếu không cấp cơ chế duyệt, việc trả phí không tự chạy.
        self._approve_paid = approve_paid_fn or self._default_paid_gate

    # ------------------------------------------------------------------ #
    def register_senior(self, spec: SeniorSpec) -> None:
        """Thêm một đàn anh vào sổ (tech_scout có thể gọi để cập nhật)."""
        self._seniors[spec.name] = spec
        logger.info("Đăng ký đàn anh '%s' (skills=%s, paid=%s).",
                    spec.name, sorted(spec.skills), spec.is_paid)

    def find_senior(self, skill: str) -> SeniorSpec | None:
        """Tìm đàn anh có kỹ năng yêu cầu; ưu tiên đàn anh MIỄN PHÍ trước."""
        candidates = [s for s in self._seniors.values() if skill in s.skills]
        if not candidates:
            return None
        candidates.sort(key=lambda s: (s.is_paid, s.cost_per_call))
        return candidates[0]

    # ------------------------------------------------------------------ #
    def _default_paid_gate(self, description: str) -> bool:
        """
        Cổng duyệt trả phí mặc định: bắn thông báo ra UI rồi... CHẶN.

        AURA không tự ý tiêu tiền. Nếu chưa có cơ chế nhận lại cái gật của Sếp,
        mặc định là KHÔNG chạy việc trả phí. (Phiên bản có UI tương tác sẽ thay
        hàm này bằng cổng chờ Sếp bấm.)
        """
        if self.event_queue is not None:
            try:
                self.event_queue.put_nowait({
                    "type": "proactive",
                    "text": (f"💰 Việc này cần giao cho đàn anh TRẢ PHÍ: {description}\n"
                             f"Ngân sách hiện tại: {self.budget.snapshot()}\n"
                             f"Sếp duyệt thì nhắn 'duyệt' để em chạy."),
                })
            except Exception as exc:  # noqa: BLE001
                logger.warning("Không bắn được thông báo ngân sách: %s", exc)
        logger.info("Việc trả phí chờ Sếp duyệt — mặc định CHẶN: %s", description)
        return False

    # ================================================================== #
    # CỔNG DUY NHẤT: giao việc cho đàn anh
    # ================================================================== #
    def delegate(
        self,
        skill: str,
        messages: list[ChatMessage],
        system_prompt: str | None = None,
        *,
        max_tokens: int = 2048,
    ) -> ToolResult:
        """
        Giao một task cho đàn anh phù hợp với `skill`, qua MỘT cổng chuẩn hoá.

        Luồng bắt buộc:
          1. Tìm đàn anh có skill (không có -> fallback đàn anh cloud mặc định).
          2. LỚP 2 — Redact: che thông tin nhạy cảm trong payload TRƯỚC khi gửi.
          3. LỚP 1 — Budget: kiểm hạn mức; nếu đàn anh trả phí -> Sếp duyệt.
          4. Gọi đàn anh qua giao diện LLMBackend chung; ghi nhận chi phí.

        Trả ToolResult — không ném exception.
        """
        senior = self.find_senior(skill)

        # --- LỚP 2: REDACT (làm SỚM, trước mọi quyết định gửi đi) ---
        safe_messages = redact_messages(messages)
        safe_system = None
        if system_prompt:
            from core.redact import redact
            safe_system = redact(system_prompt)

        # Không có đàn anh chuyên -> dùng cloud mặc định của Router (nếu có).
        if senior is None:
            if self.cloud is None:
                return ToolResult.failure(
                    "agent_broker",
                    f"Không có đàn anh nào cho kỹ năng '{skill}', và Cloud chưa cấu hình.",
                )
            logger.info("Không có đàn anh chuyên '%s' — dùng Cloud mặc định.", skill)
            intent = Intent(
                label=IntentLabel.HEAVY_REASONING, tier=RouteTier.CLOUD,
                confidence=1.0, reason=f"broker default cloud for {skill}",
                raw_text=skill,
            )
            return self.run(safe_messages, intent, system_prompt=safe_system)

        # --- LỚP 1: BUDGET ---
        est = _estimate_tokens(safe_messages, safe_system)
        affordable, reason = self.budget.can_afford(est)
        if not affordable:
            return ToolResult.failure(
                f"senior:{senior.name}", f"Chặn bởi ngân sách: {reason}"
            )

        if senior.is_paid:
            desc = f"{senior.name} cho '{skill}' (~{est} token, ~{senior.cost_per_call}$)"
            if not self._approve_paid(desc):
                return ToolResult.failure(
                    f"senior:{senior.name}",
                    "Việc trả phí chưa được Sếp duyệt — tạm dừng.",
                )

        # --- GỌI ĐÀN ANH qua giao diện chung ---
        try:
            output = senior.backend.chat(
                safe_messages, system_prompt=safe_system, max_tokens=max_tokens
            )
        except Exception as exc:  # noqa: BLE001 — không để broker nổ ra ngoài
            logger.exception("Đàn anh '%s' lỗi.", senior.name)
            return ToolResult.failure(f"senior:{senior.name}", f"Đàn anh lỗi: {exc}")

        self.budget.charge(est)
        return ToolResult.success(
            tool_name=f"senior:{senior.name}", output=output, elapsed_ms=0
        )


__all__ = ["AgentBroker", "SeniorSpec", "BudgetGuard"]