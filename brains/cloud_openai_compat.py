"""
brains/cloud_openai_compat.py
=============================
System 2 (MIỄN PHÍ) — gọi BẤT KỲ endpoint OpenAI-compatible `/chat/completions`.

Một backend phục vụ cả Groq, Gemini (OpenAI-compat), OpenRouter, Together...; cấu hình
qua `.env`: `cloud_provider=openai` + `openai_base_url` / `openai_api_key` / `openai_model`.
Cùng hợp đồng `LLMBackend` như `ClaudeBackend` nên `CloudEngine` thả vào KHÔNG gãy luồng
BrainRouter / Triad Council / briefing.

Điểm lợi cốt lõi cho AURA: API này hỗ trợ JSON mode (`response_format={"type":"json_object"}`)
mà Council cần để Generator đẻ JSON SẠCH — thứ model local hay làm hỏng (SANDBOX_FAIL).

Chỉ dùng `requests` + stdlib + core.config — không kéo SDK nặng, test được offline.
"""

from __future__ import annotations

import logging
from typing import Any

import requests

from brains.base import BrainError, BrainOfflineError, ChatMessage, LLMBackend
from core.config import settings
from core.schemas import RouteTier

logger = logging.getLogger("aura.brains.openai")


class OpenAICompatBackend(LLMBackend):
    """Bộ não cloud nói chuyện với API OpenAI-compatible (Groq/Gemini/OpenRouter...)."""

    tier = RouteTier.CLOUD

    def __init__(
        self,
        model: str | None = None,
        base_url: str | None = None,
        timeout_s: float = 120.0,
    ) -> None:
        """
        Args:
            model: model trên endpoint (mặc định settings.openai_model).
            base_url: base URL OpenAI-compatible (mặc định settings.openai_base_url).
            timeout_s: timeout mỗi request (cloud có thể chậm hơn local).
        """
        self.model = model or settings.openai_model
        self.base_url = (base_url or settings.openai_base_url).rstrip("/")
        self.timeout_s = timeout_s
        self.name = f"openai-compat:{self.model}"

    # ------------------------------------------------------------------ #
    def is_online(self) -> bool:
        """Sẵn sàng nếu có API key. Không gọi thử để khỏi tốn quota; lỗi thật bắt khi chat()."""
        return settings.openai_api_key is not None

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
        Gọi `/chat/completions`. Khác Anthropic: system đi như message role='system'
        ở đầu danh sách (không tách riêng). Chuyển tiếp `response_format` khi có (JSON mode).
        """
        if settings.openai_api_key is None:
            raise BrainOfflineError(
                "Thiếu OPENAI_API_KEY trong .env — không gọi được CloudEngine (OpenAI-compatible)."
            )

        # Gom mọi system về một chỗ rồi đặt lại thành message role='system' ở đầu.
        system_combined, conv = LLMBackend.split_system(messages, system_prompt)
        payload_messages: list[dict[str, str]] = []
        if system_combined:
            payload_messages.append({"role": "system", "content": system_combined})
        payload_messages.extend(
            {"role": m["role"], "content": m["content"]} for m in conv
        )

        body: dict[str, Any] = {
            "model": self.model,
            "messages": payload_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        # JSON mode: Council truyền response_format={"type":"json_object"} để ép JSON sạch.
        response_format = kwargs.get("response_format")
        if response_format:
            body["response_format"] = response_format

        headers = {
            "Authorization": f"Bearer {settings.openai_api_key.get_secret_value()}",
            "Content-Type": "application/json",
        }
        url = f"{self.base_url}/chat/completions"
        print(f"[DEBUG openai body] max_tokens={body.get('max_tokens')}, keys={list(body.keys())}")

        try:
            resp = requests.post(url, json=body, headers=headers, timeout=self.timeout_s)
        except requests.ConnectionError as exc:
            raise BrainOfflineError(f"Không kết nối được {self.base_url}: {exc}") from exc
        except requests.Timeout as exc:
            raise BrainError(f"{self.name} timeout sau {self.timeout_s}s.") from exc
        except requests.RequestException as exc:
            raise BrainError(f"Lỗi request tới {self.base_url}: {exc}") from exc

        if resp.status_code != 200:
            # 401 key sai, 429 quá quota, 400 model/định dạng sai — báo rõ để router/log xử lý.
            raise BrainError(f"{self.base_url} trả mã {resp.status_code}: {resp.text[:300]}")

        try:
            data = resp.json()
            choice = data["choices"][0]
            if choice.get("finish_reason") != "stop":
                print(f"[DEBUG] finish_reason: {choice.get('finish_reason')}")
            text = choice["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise BrainError(
                f"Phản hồi OpenAI-compat sai định dạng: {resp.text[:300]}"
            ) from exc

        if not isinstance(text, str) or not text.strip():
            raise BrainError("Cloud (OpenAI-compat) trả về nội dung rỗng.")
        return text


__all__ = ["OpenAICompatBackend"]
