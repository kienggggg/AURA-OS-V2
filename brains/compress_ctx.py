"""Nén ngữ cảnh TO trước khi gửi cloud LLM — keo quanh `headroom-ai`.

Đo thật (2026-07-19): headroom chỉ nén mạnh dạng TOOL-OUTPUT (role=tool):
JSON 45K chars -> 4.3K (91% tiết kiệm). Nén user-message thường thì VÔ ÍCH
(-2%), và TUYỆT ĐỐI không nén ngữ cảnh viết truyện (hỏng văn).

Dùng khi một công nhân phải đưa cục dữ liệu lớn (JSON tin cào, log, file)
cho cloud phân tích:

    from brains.compress_ctx import squeeze_payload
    msgs = squeeze_payload("Chọn 3 tin tốt nhất", big_json_str)
    reply = backend.complete(msgs, tier="bulk")

Nếu headroom chưa cài / lỗi -> trả nguyên payload (không bao giờ chặn việc).
"""

from __future__ import annotations

import json
import logging

logger = logging.getLogger("aura.brains.compress")

_MIN_CHARS = 8_000   # dưới ngưỡng này nén không bõ (overhead ngược)


def squeeze_payload(instruction: str, payload: str,
                    model: str = "gemini-2.5-flash") -> list[dict]:
    """Gói (chỉ dẫn + dữ liệu to) thành messages đã nén kiểu tool-output.

    Trả về list messages sẵn sàng đưa cho backend.complete(). Payload nhỏ
    hoặc headroom lỗi -> messages thường, không nén.
    """
    plain = [{"role": "user", "content": f"{instruction}\n\nDỮ LIỆU:\n{payload}"}]
    if len(payload) < _MIN_CHARS:
        return plain
    try:
        from headroom import compress
        msgs = [
            {"role": "user", "content": instruction},
            {"role": "assistant", "content": None, "tool_calls": [{
                "id": "ctx1", "type": "function",
                "function": {"name": "load_data", "arguments": "{}"}}]},
            {"role": "tool", "tool_call_id": "ctx1", "content": payload},
        ]
        out = compress(msgs, model=model)
        squeezed = getattr(out, "messages", out)
        before = len(payload)
        after = len(json.dumps(squeezed, ensure_ascii=False, default=str))
        if after >= before:                       # nén ngược -> bỏ
            return plain
        logger.info("compress_ctx: %s -> %s chars (%d%% tiết kiệm)",
                    f"{before:,}", f"{after:,}", 100 - 100 * after // before)
        return squeezed
    except Exception as exc:                      # noqa: BLE001 — không chặn việc
        logger.warning("compress_ctx bỏ qua (headroom lỗi: %s)", exc)
        return plain
