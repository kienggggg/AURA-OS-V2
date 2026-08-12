"""
brains/cloud_router.py
======================
System 2 (MIỄN PHÍ, ĐA NGUỒN) — gom nhiều LLM API free vào MỘT backend bằng
`litellm.Router` (dùng như THƯ VIỆN, không cần proxy server — hợp Python 3.14
nơi litellm[proxy]/orjson không build được).

Ba TẦNG (model_name của Router):
  - smart : việc khó (GitHub Models GPT-4.1/4o, Gemini Pro) — frontier free, quota chặt.
  - fast  : việc thường (NVIDIA llama-70b, Cerebras, Mistral, Cohere) — nhanh, quota rộng.
  - bulk  : số lượng (tới 6 acc Gemini Flash gộp) — quota cộng dồn.

Router tự RẢI key trong một tầng + FALLBACK sang tầng khác khi 429/lỗi. AURA chỉ
gọi tên tầng; không thấy provider nào. Tất cả provider đều OpenAI-compatible nên
litellm nói chuyện được hết.

Key đọc từ `litellm/keys.env` (gitignored) hoặc biến môi trường. Deployment nào
THIẾU key thì bỏ qua — chạy được với 1 key hay 13 key đều ổn.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from brains.base import BrainError, BrainOfflineError, ChatMessage, LLMBackend
from core.schemas import RouteTier

logger = logging.getLogger("aura.brains.router")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
_KEYS_FILE = PROJECT_ROOT / "api_keys" / "keys.env"

# Tầng -> danh sách (model litellm, tên biến key). Nhiều key/nhà = nhiều deployment.
# Deployment nào THIẾU key trong keys.env thì bị bỏ qua (chạy với key nào có).
_TIERS: dict[str, list[tuple[str, str]]] = {
    # 🧠 smart: việc KHÓ (frontier) — GitHub GPT-4o ×3, Mistral Large, Gemini Pro, OpenRouter code.
    # + Cerebras gpt-oss-120b (120B, ~2000 tok/s): viết truyện NHANH+CHẤT, quota Cerebras rộng.
    "smart": (
        [("cerebras/gpt-oss-120b", f"CEREBRAS_API_KEY_{i}") for i in range(1, 3)]
        + [("github/gpt-4o", f"GITHUB_API_KEY_{i}") for i in range(1, 4)]
        + [("mistral/mistral-large-latest", f"MISTRAL_API_KEY_{i}") for i in range(1, 4)]
        + [("gemini/gemini-2.5-pro", "GEMINI_PRO_KEY")]
        + [("openrouter/qwen/qwen3-coder:free", f"OPENROUTER_API_KEY_{i}") for i in range(1, 3)]
    ),
    # ⚡ fast: việc THƯỜNG, non-thinking nhanh + RỘNG. Nhiều nhà thay phiên, cạn nhà này -> nhà kia.
    # (Bỏ Groq: cả 6 tài khoản Google của Sếp bị hạn chế, không tạo được key mới — 2026-07-10.)
    "fast": (
        [("nvidia_nim/meta/llama-3.3-70b-instruct", "NVIDIA_API_KEY")]
        + [("mistral/mistral-small-latest", f"MISTRAL_API_KEY_{i}") for i in range(1, 4)]
        + [("cohere/command-r-plus-08-2024", f"COHERE_API_KEY_{i}") for i in range(1, 4)]
        + [("cerebras/gemma-4-31b", f"CEREBRAS_API_KEY_{i}") for i in range(1, 3)]
        + [("openrouter/meta-llama/llama-3.3-70b-instruct:free", f"OPENROUTER_API_KEY_{i}")
           for i in range(1, 3)]
        + [("huggingface/meta-llama/Llama-3.3-70B-Instruct", "HUGGINGFACE_API_KEY")]
    ),
    # 🌊 bulk: SỐ LƯỢNG — 6 acc Gemini Flash gộp.
    "bulk": [("gemini/gemini-2.5-flash", f"GEMINI_KEY_{i}") for i in range(1, 7)],
}
_TIER_ORDER = ["smart", "fast", "bulk"]   # ưu tiên chọn default + chuỗi fallback


def _load_keys() -> dict[str, str]:
    """Đọc key từ litellm/keys.env (KEY=VALUE, bỏ comment) + chồng os.environ."""
    import os
    keys: dict[str, str] = {}
    if _KEYS_FILE.exists():
        for line in _KEYS_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            v = v.strip()
            if v:
                keys[k.strip()] = v
    for k in set(v for tier in _TIERS.values() for _, v in tier):
        if os.environ.get(k):           # biến môi trường thắng file
            keys[k] = os.environ[k]
    return keys


class LiteLLMRouterBackend(LLMBackend):
    """Backend đa nguồn qua litellm.Router (in-process). Hợp đồng LLMBackend chuẩn."""

    tier = RouteTier.CLOUD

    def __init__(self, default_tier: str | None = None) -> None:
        self.name = "router"
        self._router = None
        self._available: list[str] = []
        self._default_tier = default_tier
        self._build()

    # ------------------------------------------------------------------ #
    def _build(self) -> None:
        keys = _load_keys()
        model_list: list[dict[str, Any]] = []
        available: list[str] = []
        for tier in _TIER_ORDER:
            deployments = [
                # timeout TƯỜNG MINH mỗi deployment: thiếu cái này, 1 nhà "treo mạng" (không
                # lỗi, không phản hồi) làm asyncio.to_thread CHỜ VÔ HẠN — im lặng, không log,
                # không timeout — đúng triệu chứng Council bị "treo" từng gặp. 45s là đủ rộng
                # cho LLM chậm nhất, đủ hẹp để không giữ Sếp chờ hàng chục phút.
                {"model_name": tier,
                 "litellm_params": {"model": model, "api_key": keys[var], "timeout": 45}}
                for model, var in _TIERS[tier] if keys.get(var)
            ]
            if deployments:
                model_list.extend(deployments)
                available.append(tier)

        self._available = available
        if not model_list:
            logger.warning("Router: chưa có key free nào trong api_keys/keys.env.")
            return

        # Fallback: tụt sang tầng khác khi cạn/lỗi. smart (quota GitHub HẸP) để CUỐI cùng
        # -> khỏi đốt GPT-4o cho việc thường.
        _fb = {"smart": ["bulk", "fast"], "fast": ["bulk", "smart"], "bulk": ["fast", "smart"]}
        fallbacks = [
            {t: [o for o in _fb.get(t, []) if o in available]}
            for t in available if len(available) > 1
        ]
        try:
            import litellm
            from litellm import Router
            litellm.suppress_debug_info = True
            litellm.telemetry = False          # KHÔNG gửi dữ liệu dùng ra ngoài
            self._router = Router(
                model_list=model_list,
                routing_strategy="simple-shuffle",
                num_retries=3,
                allowed_fails=2,
                cooldown_time=60,
                fallbacks=fallbacks or None,
                timeout=45,          # trần thời gian toàn cục — cùng lý do timeout/deployment ở trên
            )
            if self._default_tier is None:
                # Default việc THƯỜNG: ưu tiên fast (NVIDIA/Mistral non-thinking, nhanh+rộng);
                # rồi bulk (Gemini), rồi smart (GitHub hẹp -> để dành việc khó).
                for pref in ("fast", "bulk", "smart"):
                    if pref in available:
                        self._default_tier = pref
                        break
            logger.info("Router sẵn sàng: tầng=%s, default=%s, %d deployment.",
                        available, self._default_tier, len(model_list))
        except Exception as exc:  # noqa: BLE001 — dựng Router lỗi không làm sập app
            logger.warning("Dựng litellm.Router lỗi: %s", exc)
            self._router = None

    # ------------------------------------------------------------------ #
    def is_online(self) -> bool:
        return self._router is not None and bool(self._available)

    # Tín hiệu "việc KHÓ" -> đáng dùng tầng smart (GPT-4o/GPT-5). Giữ CHẶT để khỏi
    # đốt quota smart (GitHub Models rất hẹp) vào việc thường.
    _HARD_SIGNALS = (
        "```", "def ", "class ", "import ", "def tool_", "code_payload",
        "viết code", "viết tool", "viết hàm", "sửa code", "review code",
        "debug", "refactor", "traceback", "stack trace", "regex", "sql",
        "thuật toán", "json schema",
    )

    def _auto_tier(self, messages, system_prompt):
        """Không chỉ định tier -> tự đoán: có tín hiệu CODE/khó -> 'smart'; còn lại -> default (fast)."""
        if "smart" not in self._available:
            return self._default_tier
        blob = (" ".join(str(m.get("content", "")) for m in messages)
                + " " + (system_prompt or "")).lower()
        if any(s in blob for s in self._HARD_SIGNALS):
            return "smart"
        return self._default_tier

    def chat(
        self,
        messages: list[ChatMessage],
        system_prompt: str | None = None,
        *,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        tier: str | None = None,
        **kwargs: Any,
    ) -> str:
        if self._router is None:
            raise BrainOfflineError(
                "Router chưa có key free nào. Điền key vào api_keys/keys.env."
            )
        model = tier or self._auto_tier(messages, system_prompt)
        if model not in self._available:               # tầng không có key -> dùng default
            model = self._default_tier
        if model != self._default_tier:
            logger.info("Router: định tuyến -> tầng '%s'", model)
        if model == "bulk" and max_tokens < 2048:
            max_tokens = 2048        # Gemini (bulk) là thinking-model -> cần budget khỏi cụt

        payload: list[dict[str, str]] = []
        if system_prompt:
            payload.append({"role": "system", "content": system_prompt})
        payload.extend({"role": m["role"], "content": m["content"]} for m in messages)

        # Một số provider không nhận response_format -> drop_params lo, nhưng vẫn chuyển nếu có.
        extra: dict[str, Any] = {}
        if kwargs.get("response_format"):
            extra["response_format"] = kwargs["response_format"]

        # Thử tầng yêu cầu TRƯỚC, rồi TỰ tụt các tầng còn lại nếu lỗi HOẶC TRẢ RỖNG.
        # litellm Router chỉ fallback khi 429/exception — provider free hay trả 200-RỖNG
        # (soft-fail lúc rate limit) mà litellm coi là thành công -> ta phải tự bắt rỗng
        # và nhảy nhà, nếu không cả bước tự-biên-tập/viết sẽ âm thầm no-op khi tải nặng.
        # THỨ TỰ TỤT TẦNG THEO CHẤT LƯỢNG (không theo _TIER_ORDER cứng): fast
        # (NVIDIA/Mistral/Cohere) YẾU tiếng Việt -> để CUỐI. bulk = Gemini giỏi đa
        # ngữ nên đỡ smart tốt. Né vụ viết truyện tụt xuống fast ra văn lủng củng.
        _fb_pref = {"smart": ["smart", "bulk", "fast"],
                    "bulk": ["bulk", "smart", "fast"],
                    "fast": ["fast", "bulk", "smart"]}
        tiers_to_try = [t for t in _fb_pref.get(model, [model])
                        if t in self._available] or [model]
        last_err = "?"
        for t in tiers_to_try:
            mt = t if t in self._available else self._default_tier
            mtoks = max(max_tokens, 2048) if mt == "bulk" else max_tokens
            try:
                resp = self._router.completion(
                    model=mt, messages=payload, temperature=temperature,
                    max_tokens=mtoks, drop_params=True, **extra,
                )
                text = resp["choices"][0]["message"]["content"]
                if isinstance(text, str) and text.strip():
                    if t != model:
                        logger.info("Router: tầng '%s' rỗng/lỗi -> tụt sang '%s'", model, t)
                    return text
                last_err = "nội dung rỗng"
            except Exception as exc:  # noqa: BLE001 — thử tầng kế
                last_err = str(exc)
        raise BrainError(f"Router: mọi tầng đều fail/rỗng ({last_err}).")


__all__ = ["LiteLLMRouterBackend"]
