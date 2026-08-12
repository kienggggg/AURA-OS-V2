"""
skills/connectors/email_reader.py
=================================
Email Connector (CHỈ ĐỌC) — đọc TIÊU ĐỀ + TRÍCH LƯỢC của vài email CHƯA ĐỌC gần
nhất qua IMAP (Gmail + App Password). KHÔNG có hàm gửi/sửa/xoá — chỉ đọc.

Hai lớp đảm bảo read-only:
  1) select(INBOX, readonly=True)  -> không đổi cờ trên server.
  2) BODY.PEEK[] khi fetch          -> KHÔNG đánh dấu \\Seen (email vẫn "chưa đọc").

Mật khẩu là APP PASSWORD lưu trong .env (SecretStr), KHÔNG hard-code. Nội dung trả
về sẽ qua core.redact trước khi ghép vào prompt (xem format_emails).
"""

from __future__ import annotations

import email
import imaplib
import logging
import sys
from email.header import decode_header
from pathlib import Path

# skills/connectors/email_reader.py -> parents[2] = gốc dự án (cho `from core...`).
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

logger = logging.getLogger("aura.connectors.email")


def _decode_hdr(raw: str | None) -> str:
    if not raw:
        return ""
    out = []
    for txt, enc in decode_header(raw):
        if isinstance(txt, bytes):
            try:
                out.append(txt.decode(enc or "utf-8", errors="replace"))
            except Exception:  # noqa: BLE001
                out.append(txt.decode("utf-8", errors="replace"))
        else:
            out.append(txt)
    return "".join(out)


def _snippet(msg, limit: int = 160) -> str:
    """Lấy đoạn text/plain đầu tiên làm trích lược (không tải attachment)."""
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            disp = str(part.get("Content-Disposition", ""))
            if part.get_content_type() == "text/plain" and "attachment" not in disp:
                try:
                    body = part.get_payload(decode=True).decode(
                        part.get_content_charset() or "utf-8", errors="replace"
                    )
                    break
                except Exception:  # noqa: BLE001
                    continue
    else:
        try:
            body = msg.get_payload(decode=True).decode(
                msg.get_content_charset() or "utf-8", errors="replace"
            )
        except Exception:  # noqa: BLE001
            body = ""
    return " ".join(body.split())[:limit]


def fetch_unread(user: str | None = None, app_password: str | None = None,
                 host: str | None = None, limit: int | None = None) -> list[dict]:
    """
    Kéo về [{subject, from, snippet}] của tối đa `limit` email CHƯA ĐỌC gần nhất.
    Thiếu cấu hình hoặc lỗi -> []. KHÔNG làm thay đổi trạng thái hộp thư.
    """
    if user is None or app_password is None or host is None or limit is None:
        try:
            from core.config import settings
            user = user or settings.gmail_user
            host = host or settings.imap_host
            limit = limit or settings.email_unread_limit
            if app_password is None and settings.gmail_app_password is not None:
                app_password = settings.gmail_app_password.get_secret_value()
        except Exception:  # noqa: BLE001
            pass
    if not user or not app_password:
        return []
    host = host or "imap.gmail.com"
    limit = int(limit or 7)

    out: list[dict] = []
    try:
        box = imaplib.IMAP4_SSL(host, timeout=15)
    except Exception as exc:  # noqa: BLE001 — không nối được IMAP
        logger.warning("Kết nối IMAP lỗi (bỏ qua): %s", exc)
        return []
    try:
        box.login(user, app_password)
        box.select("INBOX", readonly=True)        # READ-ONLY: không đổi cờ trên server
        typ, data = box.search(None, "UNSEEN")
        ids = data[0].split() if (data and data[0]) else []
        for mid in reversed(ids[-limit:]):         # mới nhất trước
            # BODY.PEEK[] -> tải nguyên thư mà KHÔNG đánh dấu đã đọc.
            typ, msgdata = box.fetch(mid, "(BODY.PEEK[])")
            if not msgdata or not msgdata[0]:
                continue
            msg = email.message_from_bytes(msgdata[0][1])
            out.append({
                "subject": _decode_hdr(msg.get("Subject")),
                "from": _decode_hdr(msg.get("From")),
                "snippet": _snippet(msg),
            })
    except Exception as exc:  # noqa: BLE001 — lỗi đọc thư không được làm sập briefing
        logger.warning("Đọc email lỗi (bỏ qua): %s", exc)
    finally:
        try:
            box.logout()
        except Exception:  # noqa: BLE001
            pass
    return out


def format_emails(emails: list[dict]) -> str:
    """
    Ghép email thành text cho briefing — REDACT bắt buộc (SĐT/STK/key) TRƯỚC khi
    nội dung có cơ hội rời máy lên Cloud (Shift-Left, core/redact.py).
    """
    from core.redact import redact
    lines = []
    for e in emails:
        sender = redact(e.get("from", "")).split("<")[0].strip()[:40]
        subj = redact(e.get("subject", ""))[:120]
        snip = redact(e.get("snippet", ""))[:160]
        lines.append(f"- {subj} (từ {sender}): {snip}")
    return "\n".join(lines)


def unread_brief(user: str | None = None, app_password: str | None = None,
                 host: str | None = None, limit: int | None = None) -> str:
    """Tóm tắt email chưa đọc (đã redact) cho briefing; '' nếu không có/không cấu hình."""
    emails = fetch_unread(user, app_password, host, limit)
    return format_emails(emails) if emails else ""


__all__ = ["fetch_unread", "format_emails", "unread_brief"]
