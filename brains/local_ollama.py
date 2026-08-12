"""
brains/local_ollama.py
=======================
System 1 — Bộ não phản xạ cục bộ, chạy qua Ollama (mặc định cổng 11434).

Dùng cho intent classification, chat thường, gọi tool local. Ưu tiên tốc độ và
chi phí 0 (không tốn token cloud). Một lần gọi = một lần thử sạch; cơ chế
retry/fallback do BrainRouter lo, backend này chỉ raise lỗi rõ ràng khi hỏng.

API tham chiếu (Ollama):
    GET  {host}/api/tags   -> liệt kê model (dùng cho health check)
    POST {host}/api/chat   -> {"model","messages","stream":false,"options":{...}}
                              trả {"message":{"role","content"}, "done":true, ...}
"""

from __future__ import annotations

import logging
from typing import Any

import requests

from brains.base import BrainError, BrainOfflineError, ChatMessage, LLMBackend
from core.config import settings
from core.schemas import RouteTier

logger = logging.getLogger("aura.brains.ollama")


class OllamaBackend(LLMBackend):
    """Bộ não local nói chuyện với Ollama server qua REST."""

    tier = RouteTier.LOCAL

    def __init__(
        self,
        model: str | None = None,
        host: str | None = None,
        timeout_s: float | None = None,
    ) -> None:
        """
        Args:
            model: tên model Ollama; mặc định lấy settings.ollama_model.
            host: địa chỉ server; mặc định settings.ollama_host.
            timeout_s: timeout mỗi request sinh text; mặc định settings.ollama_timeout_s.
        """
        self.model = model or settings.ollama_model
        self.host = (host or settings.ollama_host).rstrip("/")
        self.timeout_s = timeout_s if timeout_s is not None else settings.ollama_timeout_s
        self.name = f"ollama:{self.model}"

    # ------------------------------------------------------------------ #
    def is_online(self) -> bool:
        """
        Health check nhanh qua /api/tags. KHÔNG ném exception — trả False khi hỏng,
        để router có thể an toàn hỏi trạng thái trước khi định tuyến.
        """
        try:
            resp = requests.get(f"{self.host}/api/tags", timeout=3.0)
            return resp.status_code == 200
        except requests.RequestException as exc:
            logger.warning("Ollama không phản hồi health check: %s", exc)
            return False

    # ------------------------------------------------------------------ #
    def chat(
        self,
        messages: list[ChatMessage],
        system_prompt: str | None = None,
        *,
        temperature: float = 0.7,
        max_tokens: int = 512,
        **kwargs: Any,
    ) -> str:
        """Gọi /api/chat (non-stream) và trả về nội dung message của assistant."""
        # Ollama nhận system như một message role="system" ở đầu danh sách.
        payload_messages: list[ChatMessage] = []
        if system_prompt:
            payload_messages.append({"role": "system", "content": system_prompt})
        payload_messages.extend(messages)

        body: dict[str, Any] = {
            "model": self.model,
            "messages": payload_messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }

        try:
            resp = requests.post(
                f"{self.host}/api/chat", json=body, timeout=self.timeout_s
            )
        except requests.ConnectionError as exc:
            raise BrainOfflineError(
                f"Không kết nối được Ollama tại {self.host}. Đã chạy 'ollama serve' chưa?"
            ) from exc
        except requests.Timeout as exc:
            raise BrainError(
                f"Ollama timeout sau {self.timeout_s}s (model {self.model})."
            ) from exc
        except requests.RequestException as exc:
            raise BrainError(f"Lỗi request tới Ollama: {exc}") from exc

        if resp.status_code != 200:
            raise BrainError(
                f"Ollama trả mã {resp.status_code}: {resp.text[:200]}"
            )

        try:
            data = resp.json()
            content = data["message"]["content"]
        except (ValueError, KeyError, TypeError) as exc:
            raise BrainError(
                f"Phản hồi Ollama sai định dạng: {resp.text[:200]}"
            ) from exc

        if not isinstance(content, str) or not content.strip():
            raise BrainError("Ollama trả về nội dung rỗng.")
        return content


__all__ = ["OllamaBackend"]
