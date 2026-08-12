"""
core/llm.py
===========
Engine LLM thống nhất cho AURA — chạy nội bộ 100% trên CPU khi cần.

Hai engine song song, CÙNG tuân giao diện `brains.base.LLMBackend` (có `is_online()`
và `chat() -> str`) nên thả thẳng vào BrainRouter/AgentBroker mà KHÔNG gãy luồng
Orchestrator hay Tool Registry:

  - `LocalCPUEngine` : gọi Ollama qua REST (`/api/chat` mặc định, hoặc `/api/generate`),
                       chạy hoàn toàn trên CPU — 0 đồng, không cần GPU/CUDA.
  - `CloudEngine`    : System 2 (Claude) — uỷ quyền cho brains.cloud_claude để dùng
                       một nguồn sự thật duy nhất; nạp TRỄ, thiếu key thì báo rõ.

System Prompt (Hiến pháp CONTEXT.md) được giữ NGUYÊN: với /api/chat nó là message
role="system" ở đầu; với /api/generate nó là trường "system" của payload.

`chat()` trả `str` (đúng hợp đồng cũ). Thêm `complete()` trả dict JSON-ready
(`{ok, model, tier, text|error}`) cho ai muốn JSON chuẩn.

Chỉ dùng `requests` + stdlib (+ tái dùng brains.base/core.config) — test được offline.
"""

from __future__ import annotations

import logging
from typing import Any

import requests

from brains.base import BrainError, BrainOfflineError, ChatMessage, LLMBackend
from core.config import settings
from core.schemas import RouteTier

logger = logging.getLogger("aura.core.llm")


# ---------------------------------------------------------------------------
# Hook "đang nhả chữ": báo cho UI (mascot) biết model BẮT ĐẦU / KẾT THÚC generate.
# Listener là fn(active: bool). LocalCPUEngine.chat() gọi True trước, False sau (finally).
# Decoupled: main.py đăng ký listener đẩy tín hiệu vào event_queue -> server broadcast.
# ---------------------------------------------------------------------------
_generation_listeners: list = []


def add_generation_listener(fn) -> None:
    """Đăng ký fn(active: bool) — gọi khi local engine bắt đầu (True)/kết thúc (False) generate."""
    if callable(fn) and fn not in _generation_listeners:
        _generation_listeners.append(fn)


def remove_generation_listener(fn) -> None:
    try:
        _generation_listeners.remove(fn)
    except ValueError:
        pass


def _notify_generation(active: bool) -> None:
    for fn in list(_generation_listeners):
        try:
            fn(active)
        except Exception as exc:  # noqa: BLE001 — listener lỗi không được làm sập generate
            logger.warning("generation listener lỗi: %s", exc)


# ---------------------------------------------------------------------------
# Base: thêm complete() trả JSON-ready cho cả hai engine
# ---------------------------------------------------------------------------
class _BaseEngine(LLMBackend):
    """Bọc thêm tiện ích JSON quanh hợp đồng LLMBackend. Vẫn trừu tượng."""

    def complete(
        self,
        messages: list[ChatMessage],
        system_prompt: str | None = None,
        *,
        temperature: float = 0.7,
        max_tokens: int = 512,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Gọi model và trả về dict JSON-ready (không ném exception ra ngoài).

        {ok: bool, model: str, tier: "local"|"cloud", text|error: str}
        """
        try:
            text = self.chat(
                messages, system_prompt=system_prompt,
                temperature=temperature, max_tokens=max_tokens, **kwargs,
            )
            return {"ok": True, "model": self.name, "tier": self.tier.value, "text": text}
        except BrainError as exc:
            return {"ok": False, "model": self.name, "tier": self.tier.value, "error": str(exc)}
        except Exception as exc:  # noqa: BLE001 — vành đai cuối, luôn trả JSON
            return {"ok": False, "model": self.name, "tier": self.tier.value,
                    "error": f"Lỗi không xác định: {exc}"}


# ---------------------------------------------------------------------------
# LocalCPUEngine — Ollama REST, chạy trên CPU
# ---------------------------------------------------------------------------
class LocalCPUEngine(_BaseEngine):
    """
    System 1 chạy 100% trên CPU qua Ollama (mặc định http://localhost:11434).

    Hỗ trợ cả hai endpoint:
      - /api/chat     (mặc định): gửi messages + system, nhận message.content.
      - /api/generate (use_generate=True): gộp prompt + trường system, nhận response.
    """

    tier = RouteTier.LOCAL

    def __init__(
        self,
        model: str | None = None,
        host: str | None = None,
        timeout_s: float | None = None,
        use_generate: bool = False,
        keep_alive: str | int | None = None,
    ) -> None:
        self.model = model or settings.ollama_model
        self.host = (host or settings.ollama_host).rstrip("/")
        self.timeout_s = timeout_s if timeout_s is not None else settings.ollama_timeout_s
        self.use_generate = use_generate
        # XẢ RAM THẦN TỐC: gửi keep_alive kèm MỖI request -> Ollama nhả model
        # (mặc định '0' = nhả ngay 9.6GB sau khi trả lời, nhường RAM cho Sếp).
        # Gửi kèm payload nên THẮNG cả OLLAMA_KEEP_ALIVE mức server.
        self.keep_alive = _norm_keep_alive(
            keep_alive if keep_alive is not None else settings.ollama_keep_alive
        )
        self.name = f"local-cpu:{self.model}"

    # ------------------------------------------------------------------ #
    def is_online(self) -> bool:
        """Health check qua /api/tags. KHÔNG ném exception (trả False khi hỏng)."""
        try:
            resp = requests.get(f"{self.host}/api/tags", timeout=3.0)
            return resp.status_code == 200
        except requests.RequestException as exc:
            logger.warning("Ollama (local CPU) không phản hồi health check: %s", exc)
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
        """Sinh phản hồi qua Ollama. Giữ nguyên cấu trúc truyền System Prompt."""
        _notify_generation(True)   # gemma BẮT ĐẦU nhả chữ -> mascot chuyển talk
        try:
            if self.use_generate:
                return self._via_generate(messages, system_prompt, temperature, max_tokens)
            return self._via_chat(messages, system_prompt, temperature, max_tokens)
        finally:
            _notify_generation(False)  # KẾT THÚC -> mascot về idle

    # ------------------------------------------------------------------ #
    def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        """POST tới Ollama, gói lỗi mạng/parse thành BrainError/BrainOfflineError."""
        url = f"{self.host}{path}"
        try:
            resp = requests.post(url, json=body, timeout=self.timeout_s)
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
            raise BrainError(f"Ollama trả mã {resp.status_code}: {resp.text[:200]}")
        try:
            return resp.json()
        except ValueError as exc:
            raise BrainError(f"Phản hồi Ollama không phải JSON: {resp.text[:200]}") from exc

    def _via_chat(
        self, messages: list[ChatMessage], system_prompt: str | None,
        temperature: float, max_tokens: int,
    ) -> str:
        """/api/chat — system là message role='system' ở đầu danh sách."""
        payload_messages: list[ChatMessage] = []
        if system_prompt:
            payload_messages.append({"role": "system", "content": system_prompt})
        payload_messages.extend(messages)

        def ask(budget: int) -> dict[str, Any]:
            return self._post("/api/chat", {
                "model": self.model,
                "messages": payload_messages,
                "stream": False,
                "keep_alive": self.keep_alive,  # nhả RAM theo cấu hình (mặc định ngay)
                "options": {"temperature": temperature, "num_predict": budget},
            })

        data = ask(max_tokens)
        try:
            message = data["message"]
            content = message["content"]
        except (KeyError, TypeError) as exc:
            raise BrainError(f"Phản hồi /api/chat sai định dạng: {str(data)[:200]}") from exc

        # Model biết suy nghĩ (gemma4 trở đi) trả riêng trường `thinking`.  Phần
        # suy nghĩ ăn CHUNG ngân sách `num_predict`, nên câu hỏi dài làm nó tiêu
        # sạch ngân sách trước khi kịp viết câu trả lời -> `content` RỖNG.
        #
        # 08/08/2026: đúng lỗi này khiến AURA im lặng trên Telegram suốt nhiều
        # tháng — log chỉ ghi "Ollama trả về nội dung rỗng", nghe như Ollama hỏng,
        # trong khi gọi thẳng Ollama cùng câu đó lại trả 912 ký tự bình thường.
        thinking = (message.get("thinking") or "") if isinstance(message, dict) else ""
        if not str(content).strip() and thinking.strip():
            wider = min(max_tokens * 4, 4096)
            logger.info(
                "Model tiêu hết %d token cho phần suy nghĩ, chưa kịp trả lời — "
                "hỏi lại với ngân sách %d.", max_tokens, wider,
            )
            data = ask(wider)
            message = data.get("message") or {}
            content = message.get("content") or ""
            if not str(content).strip() and (message.get("thinking") or "").strip():
                raise BrainError(
                    f"Model {self.model} dùng hết cả {wider} token cho phần suy nghĩ "
                    "mà chưa viết được câu trả lời. Hỏi ngắn gọn hơn, hoặc tăng max_tokens."
                )
        return _require_text(content)

    def _via_generate(
        self, messages: list[ChatMessage], system_prompt: str | None,
        temperature: float, max_tokens: int,
    ) -> str:
        """/api/generate — gộp messages thành prompt; system đi trường 'system'."""
        prompt = "\n".join(
            f"{m.get('role', 'user').upper()}: {m.get('content', '')}" for m in messages
        )
        body: dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "keep_alive": self.keep_alive,  # nhả RAM theo cấu hình (mặc định ngay)
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        if system_prompt:  # GIỮ NGUYÊN Hiến pháp qua trường 'system' của Ollama
            body["system"] = system_prompt

        data = self._post("/api/generate", body)
        try:
            content = data["response"]
        except (KeyError, TypeError) as exc:
            raise BrainError(f"Phản hồi /api/generate sai định dạng: {str(data)[:200]}") from exc
        return _require_text(content)


# ---------------------------------------------------------------------------
# CloudEngine — System 2 (Claude), uỷ quyền brains.cloud_claude (nguồn duy nhất)
# ---------------------------------------------------------------------------
class CloudEngine(_BaseEngine):
    """
    Engine cloud (Claude) đặt cạnh LocalCPUEngine cho luồng định tuyến hai cấp.

    Uỷ quyền cho `brains.cloud_claude.ClaudeBackend` (nạp TRỄ) để không lặp logic
    và không kéo SDK cloud khi chỉ chạy local. Thiếu backend/key -> báo lỗi rõ,
    KHÔNG làm sập app.
    """

    tier = RouteTier.CLOUD

    def __init__(self, model: str | None = None) -> None:
        import os
        provider = os.getenv("CLOUD_PROVIDER", getattr(settings, "cloud_provider", "claude")).lower()
        if provider == "router":
            default_model = "router"
        elif provider == "openai":
            default_model = settings.openai_model
        else:
            default_model = settings.cloud_model
        self.name = f"cloud:{model or default_model}"
        self._model = model
        self._backend: LLMBackend | None = None

    def _ensure(self) -> LLMBackend:
        if self._backend is None:
            import os
            provider = os.getenv("CLOUD_PROVIDER", getattr(settings, "cloud_provider", "claude")).lower()
            if provider == "router":
                # Đa nguồn free qua litellm.Router. Nếu không có litellm (trên Windows Python 3.14),
                # chuyển sang GeminiBackend dùng trực tiếp Gemini API.
                try:
                    from brains.cloud_router import LiteLLMRouterBackend
                    router_be = LiteLLMRouterBackend()
                    if router_be.is_online():
                        self._backend = router_be
                    else:
                        logger.warning("Router không online (litellm không có sẵn), chuyển sang GeminiBackend.")
                        from brains.cloud_gemini import GeminiBackend
                        self._backend = GeminiBackend()
                except Exception as exc:  # pragma: no cover
                    logger.warning("Không nạp được LiteLLMRouterBackend: %s, chuyển sang GeminiBackend.", exc)
                    from brains.cloud_gemini import GeminiBackend
                    self._backend = GeminiBackend()
            elif provider == "openai":
                # Não cloud MIỄN PHÍ (Groq/Gemini/OpenRouter) qua API OpenAI-compatible.
                try:
                    from brains.cloud_openai_compat import OpenAICompatBackend
                except ImportError as exc:  # pragma: no cover
                    raise BrainError(f"Không nạp được OpenAICompatBackend: {exc}") from exc
                self._backend = OpenAICompatBackend(model=self._model)
            elif provider == "gemini":
                # Não cloud MIỄN PHÍ qua Native Gemini API
                try:
                    from brains.cloud_gemini import GeminiBackend
                except ImportError as exc:
                    raise BrainError(f"Không nạp được GeminiBackend: {exc}") from exc
                self._backend = GeminiBackend(model=self.name.split(":", 1)[1])
            else:
                try:
                    from brains.cloud_claude import ClaudeBackend
                except ImportError as exc:  # pragma: no cover
                    raise BrainError(f"Không nạp được ClaudeBackend: {exc}") from exc
                self._backend = ClaudeBackend(model=self._model)
        return self._backend

    def is_online(self) -> bool:
        try:
            return self._ensure().is_online()
        except Exception as exc:  # noqa: BLE001 — health check không được ném
            logger.warning("CloudEngine offline: %s", exc)
            return False

    def chat(
        self,
        messages: list[ChatMessage],
        system_prompt: str | None = None,
        *,
        temperature: float = 0.7,
        max_tokens: int = 512,
        **kwargs: Any,
    ) -> str:
        return self._ensure().chat(
            messages, system_prompt=system_prompt,
            temperature=temperature, max_tokens=max_tokens, **kwargs,
        )


# ---------------------------------------------------------------------------
# Tiện ích
# ---------------------------------------------------------------------------
def _norm_keep_alive(value: str | int | float | None) -> int | str:
    """
    Chuẩn hoá keep_alive cho Ollama.

    - Số thuần ('0', 0, 300) -> int giây (Ollama hiểu 0 = nhả model NGAY).
    - Chuỗi thời lượng ('5m', '1h', '-1') -> giữ nguyên cho Ollama tự parse.
    - None/rỗng -> 0 (nhả ngay) để an toàn cho máy RAM thấp.
    """
    if value is None:
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip()
    if not text:
        return 0
    try:
        return int(text)
    except ValueError:
        return text  # vd '5m', '1h', '-1' -> để Ollama tự diễn giải


def _require_text(content: Any) -> str:
    if not isinstance(content, str) or not content.strip():
        raise BrainError("Model trả về nội dung rỗng.")
    return content


def build_engines(
    local_model: str | None = None,
    cloud_model: str | None = None,
    use_generate: bool = False,
) -> tuple[LocalCPUEngine, CloudEngine]:
    """Dựng cặp (local CPU, cloud) — tiện cắm thẳng vào AgentBroker/BrainRouter."""
    return (
        LocalCPUEngine(model=local_model, use_generate=use_generate),
        CloudEngine(model=cloud_model),
    )


__all__ = [
    "LocalCPUEngine", "CloudEngine", "build_engines",
    "add_generation_listener", "remove_generation_listener",
]
