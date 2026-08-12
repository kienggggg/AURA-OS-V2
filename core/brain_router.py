"""
core/brain_router.py
====================
BrainRouter — trái tim điều phối của hệ thần kinh đa lõi.

Nhiệm vụ:
  1. Phân loại ý định (intent) của một AgentMessage.
  2. Quyết định giao cho System 1 (Ollama local) hay System 2 (Claude cloud).
  3. Thực thi, và nếu Local lỗi liên tiếp -> BẬT CÒI BÁO ĐỘNG rồi fallback sang Cloud.

Thiết kế để test được: phần "quyết định nhãn/cấp" tách thành hàm thuần
`classify_label()` (chỉ stdlib), không dính LLM hay network.
"""

from __future__ import annotations

import logging
import time

from brains.base import BrainError, BrainOfflineError, ChatMessage, LLMBackend
from core.schemas import (
    AgentMessage,
    Intent,
    IntentLabel,
    RouteTier,
    ToolResult,
)

logger = logging.getLogger("aura.router")

# Số lần thử Local trước khi fallback (theo blueprint: lỗi liên tiếp 2 lần).
DEFAULT_MAX_LOCAL_ATTEMPTS = 2


# ---------------------------------------------------------------------------
# Phân loại intent — HÀM THUẦN (testable offline, không cần LLM)
# ---------------------------------------------------------------------------
# Mỗi nhãn gắn với một bộ từ khoá. Thứ tự kiểm tra có ưu tiên: nhãn "nặng"
# (coding/heavy) xét trước để không bị nuốt bởi từ khoá chung chung.
_KEYWORDS: list[tuple[IntentLabel, tuple[str, ...]]] = [
    (IntentLabel.CODING, ("viết code", "viết tool", "tiến hành code", "sửa code",
                           "debug", "refactor", "code lại", "fix bug")),
    (IntentLabel.HEAVY_REASONING, ("phân tích sâu", "đánh giá", "báo cáo tài chính",
                                   "lập kế hoạch", "so sánh chi tiết")),
    (IntentLabel.MANGA_TRANSLATE, ("dịch truyện", "dịch manga", "dịch chapter",
                                   "dịch chương")),
    (IntentLabel.MANGA_DOWNLOAD, ("tải truyện", "tải manga", "tải chapter",
                                  "tải chương", "download truyện")),
    (IntentLabel.WEB_SCRAPE, ("cào", "scrape", "tìm trên mạng", "tra cứu", "http://",
                              "https://")),
    (IntentLabel.SYSTEM_CONTROL, ("mở ứng dụng", "tắt máy", "dọn ổ", "dọn rác",
                                  "task manager", "mở chrome", "kiểm tra ram",
                                  "kiểm tra ổ")),
    (IntentLabel.MEMORY_QUERY, ("nhớ không", "lần trước", "tôi đã nói", "ghi nhớ",
                                "bạn còn nhớ")),
    (IntentLabel.SYSTEM_TERMINAL, ("chạy lệnh", "mở terminal", "gõ lệnh", "git log",
                                   "cmd", "bash", "powershell", "chạy git")),
]

# Dấu hiệu đáp án LOCAL yếu/né tránh -> đáng 'mượn não' Cloud (thầy).
_WEAK_MARKERS: tuple[str, ...] = (
    "tôi không biết", "không biết", "không chắc", "khong chac", "xin lỗi",
    "không thể", "khong the", "chưa rõ", "không có đủ thông tin", "i don't know",
    "as an ai", "i cannot", "i'm not sure",
)


def _looks_weak(text: str) -> bool:
    """Heuristic: đáp án quá ngắn hoặc chứa lời né tránh -> coi là yếu."""
    t = (text or "").strip()
    if len(t) < 25:
        return True
    low = t.lower()
    return any(m in low for m in _WEAK_MARKERS)


# Những nhãn đẩy lên System 2 (cloud). Còn lại xử lý cục bộ.
_CLOUD_LABELS: frozenset[IntentLabel] = frozenset(
    {IntentLabel.CODING, IntentLabel.HEAVY_REASONING}
)


def classify_label(text: str) -> tuple[IntentLabel, RouteTier, float]:
    """
    Phân loại nhãn intent + cấp xử lý bằng từ khoá. Hàm thuần, dễ test.

    Returns:
        (label, tier, confidence). confidence 0.9 khi trúng từ khoá,
        0.4 cho chitchat mặc định (đủ để router biết đây là phỏng đoán yếu).
    """
    lowered = text.lower()
    for label, keywords in _KEYWORDS:
        if any(kw in lowered for kw in keywords):
            tier = RouteTier.CLOUD if label in _CLOUD_LABELS else RouteTier.LOCAL
            return label, tier, 0.9

    # Không trúng từ khoá nào -> tán gẫu, xử lý cục bộ, độ tự tin thấp.
    return IntentLabel.CHITCHAT, RouteTier.LOCAL, 0.4


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------
class BrainRouter:
    """
    Điều phối request tới đúng bộ não, có cơ chế retry + fallback.

    Cách dùng:
        router = BrainRouter(local=OllamaBackend(), cloud=ClaudeBackend())
        msg = AgentMessage(sender=AgentRole.USER, receiver=AgentRole.ROUTER,
                           action="ask", payload="Viết tool nén video")
        result = router.route_intent(msg)   # -> ToolResult
    """

    def __init__(
        self,
        local: LLMBackend,
        cloud: LLMBackend | None = None,
        max_local_attempts: int = DEFAULT_MAX_LOCAL_ATTEMPTS,
        escalate_on_weak: bool = True,
        escalate_min_chars: int = 40,
    ) -> None:
        self.local = local
        self.cloud = cloud
        self.max_local_attempts = max(1, max_local_attempts)
        # ESCALATION thông minh: Local trả lời YẾU + câu hỏi đáng giá -> mượn Cloud.
        self.escalate_on_weak = escalate_on_weak
        self.escalate_min_chars = escalate_min_chars

    # ------------------------------------------------------------------ #
    def classify(self, text: str) -> Intent:
        """Bọc classify_label() thành đối tượng Intent có cấu trúc."""
        label, tier, confidence = classify_label(text)
        return Intent(
            label=label,
            tier=tier,
            confidence=confidence,
            reason=f"keyword-match -> {label.value}",
            raw_text=text,
        )

    # ------------------------------------------------------------------ #
    def run(
        self,
        messages: list[ChatMessage],
        intent: Intent,
        system_prompt: str | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        """
        LÕI THỰC THI: chạy một chuỗi messages đã dựng sẵn theo cấp của intent,
        có cơ chế retry + fallback. Dùng bởi Orchestrator (cần bơm system_prompt
        chứa ngữ cảnh ký ức) và bởi route_intent().

        tier == CLOUD -> chạy thẳng Cloud (degrade về Local nếu thiếu Cloud).
        tier == LOCAL -> chạy Local; lỗi quá số lần cho phép -> fallback Cloud.
        """
        if intent.tier == RouteTier.CLOUD:
            return self._route_to_cloud(messages, system_prompt, **kwargs)
        return self._route_to_local_with_fallback(messages, system_prompt, intent, **kwargs)

    def route_intent(self, message: AgentMessage, **kwargs: Any) -> ToolResult:
        """
        Tiện ích đứng-một-mình: phân loại payload rồi thực thi.

        Giữ nguyên hành vi cũ — classify trên payload thô, gọi brain bằng đúng
        câu đó (không ngữ cảnh). Orchestrator KHÔNG dùng hàm này mà dùng run()
        để còn bơm system_prompt.
        """
        text = message.payload.strip()
        if not text:
            return ToolResult.failure("router", "AgentMessage.payload rỗng.")

        intent = self.classify(text)
        logger.info(
            "Intent=%s tier=%s conf=%.2f", intent.label.value, intent.tier.value,
            intent.confidence,
        )
        return self.run([{"role": "user", "content": text}], intent, **kwargs)

    # ------------------------------------------------------------------ #
    def _route_to_local_with_fallback(
        self, messages: list[ChatMessage], system_prompt: str | None = None,
        intent: Intent | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        """Chạy Local, thử tối đa max_local_attempts lần; thất bại thì fallback Cloud."""
        last_error = ""
        for attempt in range(1, self.max_local_attempts + 1):
            start = time.monotonic()
            try:
                output = self.local.chat(messages, system_prompt=system_prompt, **kwargs)
                elapsed = int((time.monotonic() - start) * 1000)
                # ESCALATION: Local OK nhưng đáp án YẾU + câu hỏi đáng giá -> mượn Cloud.
                if self._should_escalate(intent, messages, output):
                    esc = self._try_escalate(messages, system_prompt, **kwargs)
                    if esc is not None:
                        return esc
                return ToolResult.success(
                    tool_name=f"brain:{self.local.name}",
                    output=output,
                    elapsed_ms=elapsed,
                )
            except (BrainError, BrainOfflineError) as exc:
                last_error = str(exc)
                logger.warning(
                    "Local thất bại lần %d/%d: %s",
                    attempt, self.max_local_attempts, last_error,
                )

        # === BẬT CÒI BÁO ĐỘNG: Local gục, chuyển sang Cloud ===
        logger.error(
            "🚨 LOCAL GỤC sau %d lần. Kích hoạt FALLBACK -> Cloud. Lỗi cuối: %s",
            self.max_local_attempts, last_error,
        )
        return self._route_to_cloud(
            messages, system_prompt, fallback_reason=last_error, **kwargs
        )

    # ------------------------------------------------------------------ #
    def _should_escalate(
        self, intent: Intent | None, messages: list[ChatMessage], output: str
    ) -> bool:
        """Có nên mượn Cloud không: bật cờ + có Cloud + câu hỏi đáng giá + đáp án yếu."""
        if not self.escalate_on_weak or self.cloud is None:
            return False
        user_text = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                user_text = m.get("content", "") or ""
                break
        if len(user_text.strip()) < self.escalate_min_chars:
            return False
        return _looks_weak(output)

    def _try_escalate(
        self, messages: list[ChatMessage], system_prompt: str | None,
        **kwargs: Any,
    ) -> ToolResult | None:
        """Gọi Cloud khi đáp án local yếu. None nếu Cloud không sẵn/lỗi (giữ local)."""
        try:
            if not self.cloud.is_online():
                return None
        except Exception:  # noqa: BLE001
            return None
        logger.info("🎓 Đáp án local yếu -> ESCALATE lên Cloud (thầy).")
        res = self._route_to_cloud(messages, system_prompt, note_tag="escalated", **kwargs)
        return res if res.ok else None

    # ------------------------------------------------------------------ #
    def _route_to_cloud(
        self,
        messages: list[ChatMessage],
        system_prompt: str | None = None,
        fallback_reason: str = "",
        note_tag: str = "",
        **kwargs: Any,
    ) -> ToolResult:
        """Chạy Cloud. Nếu không có Cloud (chưa cấu hình), degrade về Local một lần."""
        if self.cloud is None or not self.cloud.is_online():
            # Không có phao cứu sinh. Nếu đang fallback từ Local thì coi như thua hẳn.
            if fallback_reason:
                return ToolResult.failure(
                    tool_name="router",
                    error=(
                        f"Local lỗi ({fallback_reason}) và Cloud không khả dụng. "
                        "Kiểm tra ANTHROPIC_API_KEY."
                    ),
                )
            # Intent vốn là cloud nhưng không có cloud -> thử local như phương án chót.
            logger.warning("Intent cần Cloud nhưng Cloud không khả dụng — thử Local.")
            try:
                output = self.local.chat(messages, system_prompt=system_prompt, **kwargs)
                return ToolResult.success(
                    tool_name=f"brain:{self.local.name} (degraded)",
                    output=output,
                )
            except (BrainError, BrainOfflineError) as exc:
                return ToolResult.failure("router", f"Cả Cloud lẫn Local đều hỏng: {exc}")

        start = time.monotonic()
        try:
            output = self.cloud.chat(messages, system_prompt=system_prompt, **kwargs)
            elapsed = int((time.monotonic() - start) * 1000)
            note = " (fallback)" if fallback_reason else (f" ({note_tag})" if note_tag else "")
            return ToolResult.success(
                tool_name=f"brain:{self.cloud.name}{note}",
                output=output,
                elapsed_ms=elapsed,
            )
        except (BrainError, BrainOfflineError) as exc:
            return ToolResult.failure(
                tool_name=f"brain:{self.cloud.name}",
                error=f"Cloud cũng lỗi: {exc}",
            )


# Lưu ý: `run()` là lõi thực thi (Orchestrator dùng để bơm system_prompt);
# `route_intent()` là tiện ích đứng-một-mình giữ nguyên hành vi cũ.
__all__ = ["BrainRouter", "classify_label", "DEFAULT_MAX_LOCAL_ATTEMPTS", "_looks_weak"]
