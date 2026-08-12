import requests
import logging
import json
from typing import Any
from brains.base import BrainError, BrainOfflineError, ChatMessage, LLMBackend
from core.config import settings
from core.schemas import RouteTier

logger = logging.getLogger("aura.brains.gemini")

class GeminiBackend(LLMBackend):
    tier = RouteTier.CLOUD

    def __init__(self, model: str | None = None, timeout_s: float = 120.0) -> None:
        self.model = model or "gemini-2.5-flash"
        self.timeout_s = timeout_s
        self.name = f"gemini:{self.model}"

    def is_online(self) -> bool:
        return True

    def chat(self, messages: list[ChatMessage], system_prompt: str | None = None, *,
             temperature: float = 0.7, max_tokens: int = 8000,
             images: list[bytes] | None = None, **kwargs: Any) -> str:
        # images: danh sách PNG bytes gắn vào TIN CUỐI (cho vòng lặp thao tác nhìn
        # màn hình). Không truyền -> hành xử y hệt bản text-only cũ.
        api_key = None
        if getattr(settings, "gemini_api_key", None):
            api_key = settings.gemini_api_key.get_secret_value()
        elif getattr(settings, "google_api_key", None):
            api_key = settings.google_api_key.get_secret_value()
        elif getattr(settings, "openai_api_key", None):
            api_key = settings.openai_api_key.get_secret_value()
        
        if not api_key:
            import os
            for k in ("GEMINI_API_KEY", "GEMINI_KEY_1", "GEMINI_PRO_KEY", "GOOGLE_API_KEY"):
                if os.getenv(k):
                    api_key = os.getenv(k)
                    break

        if not api_key:
            from pathlib import Path
            keys_file = Path(__file__).resolve().parent.parent / "api_keys" / "keys.env"
            if keys_file.exists():
                for line in keys_file.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, _, v = line.partition("=")
                        if k.strip() in ("GEMINI_KEY_1", "GEMINI_PRO_KEY", "GOOGLE_API_KEY", "GEMINI_API_KEY") and v.strip():
                            api_key = v.strip()
                            break

        if not api_key:
            raise BrainOfflineError("Thiếu API KEY cho Gemini.")

        system_combined, conv = LLMBackend.split_system(messages, system_prompt)
        
        contents = []
        system_instruction = None
        if system_combined:
            system_instruction = {"parts": [{"text": system_combined}]}
            
        for m in conv:
            role = "user" if m["role"] in ["user", "system"] else "model"
            contents.append({"role": role, "parts": [{"text": m["content"]}]})

        # Gắn ảnh (nếu có) vào tin CUỐI dạng inline_data base64 — Gemini nhìn được.
        if images and contents:
            import base64
            for img in images:
                if not img:
                    continue
                contents[-1]["parts"].append({
                    "inline_data": {
                        "mime_type": "image/png",
                        "data": base64.b64encode(img).decode("ascii"),
                    }
                })

        # Ép minimum maxOutputTokens = 256 vì Gemini 2.5 thinking tốn token cho suy luận nội bộ
        max_tokens_val = max(256, max_tokens)
        body = {
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens_val,
            }
        }
        
        if system_instruction:
            body["systemInstruction"] = system_instruction
            
        if kwargs.get("response_format", {}).get("type") == "json_object":
            pass # body["generationConfig"]["responseMimeType"] = "application/json"

        logger.debug("[Gemini payload] body=%s", json.dumps(body, ensure_ascii=False))
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={api_key}"
        
        try:
            resp = requests.post(url, json=body, timeout=self.timeout_s)
        except Exception as exc:
            raise BrainError(f"Lỗi request tới Gemini: {exc}") from exc

        if resp.status_code != 200:
            raise BrainError(f"Gemini API lỗi {resp.status_code}: {resp.text[:300]}")

        try:
            data = resp.json()
            logger.debug("[Gemini raw response] %s", json.dumps(data, ensure_ascii=False)[:500])
            if "candidates" not in data or not data["candidates"]:
                raise BrainError(f"Gemini trả về không có candidates: {data}")
            cand = data["candidates"][0]
            if cand.get("finishReason") not in ("STOP", "MAX_TOKENS"):
                logger.debug("[Gemini] finishReason: %s", cand.get('finishReason'))
            parts = cand.get("content", {}).get("parts", [])
            if not parts:
                raise BrainError(f"Gemini cạn token suy luận (finishReason={cand.get('finishReason')}).")
            text = parts[0].get("text", "")
        except Exception as exc:
            raise BrainError(f"Phản hồi Gemini sai định dạng: {resp.text[:300]}") from exc

        return text
