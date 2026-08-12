"""
brains/cloud_claude.py
======================
System 2 — Bộ não suy luận sâu, gọi Claude qua REST API của Anthropic.

Dùng cho coding dự án lớn, debug logic phức tạp, phân tích nặng, hoặc làm phao
cứu sinh khi System 1 (Ollama) gục. Tốn token nên router chỉ đẩy lên đây khi
thật sự cần (intent CODING / HEAVY_REASONING) hoặc khi fallback.

Gọi thẳng endpoint /v1/messages bằng `requests` (không cần SDK anthropic), key
đọc từ config (đã bọc SecretStr, không hard-code).
"""

from __future__ import annotations

import logging
from typing import Any

import requests

from brains.base import BrainError, BrainOfflineError, ChatMessage, LLMBackend
from core.config import settings
from core.schemas import RouteTier

logger = logging.getLogger("aura.brains.claude")

_API_URL = "https://api.anthropic.com/v1/messages"
_API_VERSION = "2023-06-01"


class ClaudeBackend(LLMBackend):
    """Bộ não cloud nói chuyện với Anthropic Messages API."""

    tier = RouteTier.CLOUD

    def __init__(self, model: str | None = None, timeout_s: float = 120.0) -> None:
        """
        Args:
            model: model cloud; mặc định settings.cloud_model.
            timeout_s: timeout mỗi request (cloud có thể chậm hơn local).
        """
        self.model = model or settings.cloud_model
        self.timeout_s = timeout_s
        self.name = f"claude:{self.model}"

    # ------------------------------------------------------------------ #
    def is_online(self) -> bool:
        """
        Coi như sẵn sàng nếu có API key cấu hình. Không gọi thử để khỏi tốn token;
        lỗi mạng/quota thực tế sẽ được bắt khi gọi chat().
        """
        return settings.anthropic_api_key is not None

    # ------------------------------------------------------------------ #
    def chat(
        self,
        messages: list[ChatMessage],
        system_prompt: str | None = None,
        *,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        **kwargs: Any,
    ) -> str:
        """
        Gọi Anthropic Messages API. Anthropic yêu cầu system tách riêng khỏi
        messages, nên ta dùng split_system() để gom mọi system về một chỗ.
        """
        if settings.anthropic_api_key is None:
            raise BrainOfflineError(
                "Thiếu ANTHROPIC_API_KEY trong .env — không thể gọi System 2 (Claude)."
            )

        system_combined, conv = LLMBackend.split_system(messages, system_prompt)

        body: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [{"role": m["role"], "content": m["content"]} for m in conv],
        }
        if system_combined:
            body["system"] = system_combined

        headers = {
            "x-api-key": settings.anthropic_api_key.get_secret_value(),
            "anthropic-version": _API_VERSION,
            "content-type": "application/json",
        }

        try:
            resp = requests.post(
                _API_URL, json=body, headers=headers, timeout=self.timeout_s
            )
        except requests.ConnectionError as exc:
            raise BrainOfflineError(f"Không kết nối được Anthropic API: {exc}") from exc
        except requests.Timeout as exc:
            raise BrainError(f"Anthropic API timeout sau {self.timeout_s}s.") from exc
        except requests.RequestException as exc:
            raise BrainError(f"Lỗi request tới Anthropic: {exc}") from exc

        if resp.status_code != 200:
            # 401 key sai, 429 quá quota, 529 quá tải — báo rõ để router/log xử lý.
            raise BrainError(
                f"Anthropic trả mã {resp.status_code}: {resp.text[:300]}"
            )

        try:
            data = resp.json()
            # content là danh sách block; ta nối các block type="text".
            blocks = data["content"]
            text = "".join(
                b.get("text", "") for b in blocks if b.get("type") == "text"
            )
        except (ValueError, KeyError, TypeError) as exc:
            raise BrainError(
                f"Phản hồi Anthropic sai định dạng: {resp.text[:300]}"
            ) from exc

        if not text.strip():
            raise BrainError("Claude trả về nội dung rỗng.")
        return text


__all__ = ["ClaudeBackend"]
