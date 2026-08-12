"""
core/redact.py
=============
Bộ lọc che thông tin nhạy cảm — DÙNG CHUNG cho mọi nơi cần đẩy dữ liệu ra ngoài
(SelfDiagnose, AgentBroker...). Một nguồn sự thật duy nhất, không viết lại rải rác.

RÀO BẢO MẬT: che API key, token dài, tên người dùng trong đường dẫn — trước khi
bất kỳ payload nào rời máy đi lên Cloud.

Giới hạn thành thật: đây là lưới chặn các MẪU phổ biến, không phải tường tuyệt
đối. Dữ liệu nhạy cảm dạng lạ vẫn có thể lọt — nên payload càng gọn càng an toàn.
"""

from __future__ import annotations

import re

# (pattern, thay thế). Thứ tự quan trọng: che key cụ thể trước token chung chung.
_REDACT_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"(sk-ant-[A-Za-z0-9_\-]{8,})", "[REDACTED_ANTHROPIC_KEY]"),
    (r"(sk-[A-Za-z0-9_\-]{8,})", "[REDACTED_KEY]"),
    (r"(AIza[A-Za-z0-9_\-]{20,})", "[REDACTED_GOOGLE_KEY]"),
    (r"(ghp_[A-Za-z0-9]{20,})", "[REDACTED_GITHUB_TOKEN]"),
    (r"(hf_[A-Za-z0-9]{20,})", "[REDACTED_HF_TOKEN]"),
    (
        r"(?i)(?:bot)?\d{8,12}:[A-Za-z0-9_\-]{30,}\b",
        "[REDACTED_TELEGRAM_TOKEN]",
    ),
    (
        r"(?i)(authorization\s*[:=]\s*bearer\s+)[A-Za-z0-9._~+/=\-]{8,}",
        r"\1[REDACTED_BEARER_TOKEN]",
    ),
    (
        r"(?i)\b(password|passwd|pwd|m[aậ]t\s*kh[aẩ]u|api[_ -]?key|access[_ -]?token|"
        r"refresh[_ -]?token|bot[_ -]?token|secret)\b(\s*[:=]\s*)"
        r"[\"']?[^\s\"',;]{4,}[\"']?",
        r"\1\2[REDACTED_SECRET]",
    ),
    (
        r"(?i)\b(otp|one[- ]?time[- ]?(?:password|code)|m[aã]\s*x[aá]c\s*nh[aậ]n)"
        r"\b(\s*(?::|=|l[aà]|is)?\s*)\d{4,8}\b",
        r"\1\2[REDACTED_OTP]",
    ),
    (r"(?i)(cookie\s*[:=]\s*)[^\r\n]{8,}", r"\1[REDACTED_COOKIE]"),
    (
        r"(?i)\b[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}\b",
        "[REDACTED_EMAIL]",
    ),
    # Số điện thoại VN (+84xxxxxxxxx / 0xxxxxxxxx) — che TRƯỚC số chung chung.
    (r"(\+?84\d{9})", "[REDACTED_PHONE]"),
    (r"(\b0\d{9}\b)", "[REDACTED_PHONE]"),
    # Số tài khoản / thẻ / dãy số dài 9-19 chữ số.
    (r"(\b\d{9,19}\b)", "[REDACTED_NUMBER]"),
    (r"([A-Za-z0-9_\-]{32,})", "[REDACTED_LONG_TOKEN]"),
    (r"(C:\\Users\\)([^\\]+)", r"\1[USER]"),
    (r"(/home/)([^/]+)", r"\1[USER]"),
    (r"(/Users/)([^/]+)", r"\1[USER]"),
)


def redact(text: str) -> str:
    """Che thông tin nhạy cảm trong một chuỗi."""
    cleaned = text
    for pattern, repl in _REDACT_PATTERNS:
        cleaned = re.sub(pattern, repl, cleaned)
    return cleaned


def redact_messages(messages: list[dict]) -> list[dict]:
    """Che thông tin nhạy cảm trong nội dung của một danh sách message chat."""
    return [
        {**m, "content": redact(m["content"]) if isinstance(m.get("content"), str) else m.get("content")}
        for m in messages
    ]


__all__ = ["redact", "redact_messages"]
