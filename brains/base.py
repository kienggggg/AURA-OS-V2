"""
brains/base.py
==============
Hợp đồng chung (abstract interface) cho mọi "bộ não" của AURA.

Bất kỳ backend nào — Ollama cục bộ (System 1) hay Claude trên cloud (System 2) —
đều phải tuân theo cùng một giao diện `LLMBackend`. Nhờ vậy BrainRouter có thể
hoán đổi/đổ lỗi (fallback) giữa các backend mà không cần biết chi tiết bên trong.

Module này chỉ phụ thuộc core.schemas (leaf) + stdlib, không import backend cụ thể
hay router — tránh phụ thuộc vòng.
"""

from __future__ import annotations

import abc
import logging
from typing import Any, TypedDict

from core.schemas import RouteTier

logger = logging.getLogger("aura.brains")


# ---------------------------------------------------------------------------
# Kiểu dữ liệu & ngoại lệ
# ---------------------------------------------------------------------------
class ChatMessage(TypedDict):
    """Một lượt hội thoại theo chuẩn role/content (tương thích Ollama & Anthropic)."""

    role: str  # "system" | "user" | "assistant"
    content: str


class BrainError(RuntimeError):
    """Lỗi chung khi gọi một LLM backend (HTTP lỗi, parse lỗi, model trả rác...)."""


class BrainOfflineError(BrainError):
    """Backend không sẵn sàng: health check thất bại hoặc không kết nối được."""


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------
class LLMBackend(abc.ABC):
    """
    Giao diện chuẩn cho một bộ não.

    Lớp con BẮT BUỘC cài đặt:
      - `is_online()` : kiểm tra backend có sẵn sàng phục vụ không.
      - `chat()`      : nhận danh sách ChatMessage, trả về text trả lời.

    Lớp con tự đặt `name` (để log/trace) và `tier` (LOCAL/CLOUD).
    `think()` là tiện ích bọc sẵn cho trường hợp một câu hỏi đơn.
    """

    #: Tên hiển thị của backend, ví dụ "ollama:gemma2".
    name: str = "base"
    #: Cấp xử lý mà backend này đại diện.
    tier: RouteTier

    @abc.abstractmethod
    def is_online(self) -> bool:
        """Trả True nếu backend sẵn sàng nhận request. KHÔNG được ném exception."""
        raise NotImplementedError

    @abc.abstractmethod
    def chat(
        self,
        messages: list[ChatMessage],
        system_prompt: str | None = None,
        *,
        temperature: float = 0.7,
        max_tokens: int = 512,
        **kwargs: Any,
    ) -> str:
        """
        Sinh phản hồi cho một chuỗi hội thoại.

        Args:
            messages: lịch sử hội thoại (không gồm system; truyền qua system_prompt).
            system_prompt: chỉ dẫn hệ thống (tùy chọn).
            temperature: độ ngẫu nhiên.
            max_tokens: giới hạn token sinh ra.

        Returns:
            Văn bản trả lời (đã bóc tách sạch).

        Raises:
            BrainOfflineError: backend không kết nối được.
            BrainError: lỗi khác trong quá trình gọi.
        """
        raise NotImplementedError

    def think(
        self,
        prompt: str,
        system_prompt: str | None = None,
        *,
        temperature: float = 0.7,
        max_tokens: int = 512,
        **kwargs: Any,
    ) -> str:
        """Tiện ích: hỏi một câu đơn (bọc thành messages 1 phần tử rồi gọi chat)."""
        return self.chat(
            [{"role": "user", "content": prompt}],
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )

    @staticmethod
    def split_system(
        messages: list[ChatMessage], system_prompt: str | None
    ) -> tuple[str | None, list[ChatMessage]]:
        """
        Tách các message role="system" ra khỏi danh sách và gộp với system_prompt.

        Hữu ích cho các API (như Anthropic) yêu cầu system tách riêng khỏi messages.
        Trả về (system_gộp, messages_không_còn_system).
        """
        system_parts: list[str] = []
        if system_prompt:
            system_parts.append(system_prompt)

        rest: list[ChatMessage] = []
        for m in messages:
            if m.get("role") == "system":
                system_parts.append(m["content"])
            else:
                rest.append(m)

        combined = "\n\n".join(p for p in system_parts if p) or None
        return combined, rest


__all__ = [
    "ChatMessage",
    "BrainError",
    "BrainOfflineError",
    "LLMBackend",
]
