"""Pipeline công việc thuê: biến hồ sơ nháp thành kết quả có thể kiểm chứng.

Module này không gửi hồ sơ, ký hợp đồng hay tự nhận tiền. Nó chỉ giữ một sổ
trạng thái bền vững để AURA luôn biết cơ hội nào cần Sếp hành động tiếp theo.
Mọi bước chạm ra ngoài (nộp đơn, xác nhận đã nhận tiền) đều cần cờ xác nhận
từ người dùng và được ghi audit.
"""

from __future__ import annotations

import json
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from core.config import settings


_DEFAULT_PATH = settings.ledger_dir / "work_for_hire.jsonl"

STATUSES = frozenset(
    {
        "needs_source",
        "research_needed",
        "needs_owner_approval",
        "approved_to_submit",
        "submitted",
        "replied",
        "interview",
        "won",
        "delivering",
        "delivered",
        "invoiced",
        "paid",
        "lost",
        "not_pursued",
    }
)

_ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    "needs_source": frozenset({"research_needed", "needs_owner_approval", "not_pursued", "lost"}),
    "research_needed": frozenset({"needs_owner_approval", "not_pursued", "lost"}),
    "needs_owner_approval": frozenset({"approved_to_submit", "not_pursued", "lost"}),
    "approved_to_submit": frozenset({"submitted", "not_pursued", "lost"}),
    "submitted": frozenset({"replied", "interview", "won", "lost"}),
    "replied": frozenset({"interview", "won", "lost"}),
    "interview": frozenset({"won", "lost"}),
    "won": frozenset({"delivering", "delivered", "invoiced", "lost"}),
    "delivering": frozenset({"delivered", "lost"}),
    "delivered": frozenset({"invoiced", "paid", "lost"}),
    "invoiced": frozenset({"paid", "lost"}),
    "paid": frozenset(),
    "lost": frozenset(),
    "not_pursued": frozenset(),
}

_ACTION_PRIORITY = {
    "needs_owner_approval": 0,
    "approved_to_submit": 1,
    "replied": 2,
    "interview": 3,
    "won": 4,
    "delivering": 5,
    "delivered": 6,
    "invoiced": 7,
    "research_needed": 8,
    "needs_source": 9,
}


def is_listing_url(url: str) -> bool:
    """True khi URL có dạng HTTP(S) đủ để Sếp có thể tự mở và nộp hồ sơ."""
    try:
        parsed = urlparse((url or "").strip())
    except ValueError:
        return False
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _path(path: Path | None = None) -> Path:
    return path or _DEFAULT_PATH


def _read(path: Path | None = None) -> dict[str, dict[str, Any]]:
    """Replay sổ event append-only, bỏ qua dòng hỏng thay vì làm sập dashboard."""
    ledger = _path(path)
    if not ledger.is_file():
        return {}
    deals: dict[str, dict[str, Any]] = {}
    try:
        lines = ledger.read_text(encoding="utf-8").splitlines()
    except OSError:
        return {}
    for line in lines:
        try:
            event = json.loads(line)
            deal = event["deal"]
            deal_id = str(deal["id"])
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            continue
        deals[deal_id] = deal
    return deals


def _append(deal: dict[str, Any], event: str, path: Path | None = None) -> dict[str, Any]:
    ledger = _path(path)
    ledger.parent.mkdir(parents=True, exist_ok=True)
    row = {"ts": int(time.time()), "event": event, "deal": deal}
    with ledger.open("a", encoding="utf-8") as file:
        file.write(json.dumps(row, ensure_ascii=False) + "\n")
    return deal


def _norm(value: str) -> str:
    return " ".join((value or "").strip().casefold().split())


def list_deals(limit: int = 200, path: Path | None = None) -> list[dict[str, Any]]:
    deals = list(_read(path).values())
    deals.sort(key=lambda item: int(item.get("updated_at") or 0), reverse=True)
    return deals[:max(1, limit)]


def create_draft(
    *,
    title: str,
    url: str = "",
    fit_score: int = 0,
    artifact: str = "",
    source_verified: bool = False,
    origin: str = "manual",
    notes: str = "",
    path: Path | None = None,
) -> dict[str, Any]:
    """Đăng ký một cơ hội sau khi AURA đã soạn hồ sơ, có chống trùng URL."""
    clean_title = " ".join((title or "").split()) or "Cơ hội chưa đặt tên"
    clean_url = (url or "").strip()
    now = int(time.time())
    for old in _read(path).values():
        if clean_url and clean_url == str(old.get("url") or ""):
            return old
        if not clean_url and _norm(clean_title) == _norm(str(old.get("title") or "")):
            return old

    try:
        score = max(0, min(100, int(fit_score)))
    except (TypeError, ValueError):
        score = 0
    if not is_listing_url(clean_url):
        status = "needs_source"
    elif not source_verified:
        status = "research_needed"
    elif score < int(settings.work_for_hire_min_fit):
        status = "not_pursued"
    else:
        status = "needs_owner_approval"

    deal = {
        "id": uuid.uuid4().hex[:10],
        "title": clean_title,
        "url": clean_url,
        "fit_score": score,
        "artifact": str(artifact or ""),
        "source_verified": bool(source_verified),
        "origin": str(origin or "manual"),
        "status": status,
        "notes": str(notes or ""),
        "amount": 0.0,
        "currency": "VND",
        "created_at": now,
        "updated_at": now,
    }
    return _append(deal, "draft_created", path)


def transition(
    deal_id: str,
    status: str,
    *,
    confirmed_by_owner: bool = False,
    url: str = "",
    amount: float | int | str | None = None,
    currency: str = "VND",
    note: str = "",
    path: Path | None = None,
) -> dict[str, Any]:
    """Ghi một bước thực tế do Sếp xác nhận; không có thao tác mạng nào ở đây."""
    target = (status or "").strip().lower()
    if target not in STATUSES:
        raise ValueError(f"Trạng thái không hợp lệ: {status}")
    current = _read(path).get(str(deal_id))
    if current is None:
        raise KeyError("Không tìm thấy cơ hội.")
    source = str(current.get("status") or "")
    if target not in _ALLOWED_TRANSITIONS.get(source, frozenset()):
        raise ValueError(f"Không thể chuyển từ '{source}' sang '{target}'.")
    if target == "needs_owner_approval" and source in {"needs_source", "research_needed"}:
        candidate_url = (url or str(current.get("url") or "")).strip()
        if not confirmed_by_owner or not is_listing_url(candidate_url):
            raise ValueError("Sếp cần xác minh một URL tin tuyển dụng HTTP(S) thật trước khi duyệt hồ sơ.")
        current["url"] = candidate_url
        current["source_verified"] = True
    if target == "approved_to_submit":
        if not is_listing_url(str(current.get("url") or "")) or not current.get("source_verified"):
            raise ValueError("Cần URL tin thật đã xác minh trước khi duyệt nộp.")
        artifact = Path(str(current.get("artifact") or ""))
        if not artifact.is_file():
            raise ValueError("Không tìm thấy bộ hồ sơ/deliverable để Sếp duyệt.")
    if target == "submitted" and not confirmed_by_owner:
        raise ValueError("Chỉ đánh dấu 'đã nộp' sau khi Sếp tự gửi hồ sơ thật.")
    if target == "paid":
        if not confirmed_by_owner:
            raise ValueError("Chỉ ghi đã nhận tiền khi Sếp xác nhận tiền đã về.")
        try:
            paid_amount = float(amount or 0)
        except (TypeError, ValueError) as exc:
            raise ValueError("Số tiền nhận phải là số hợp lệ.") from exc
        if paid_amount <= 0:
            raise ValueError("Chỉ ghi đã nhận tiền với số tiền lớn hơn 0.")
        current["amount"] = paid_amount
        current["currency"] = (currency or "VND").upper()[:8]

    current["status"] = target
    current["updated_at"] = int(time.time())
    if note.strip():
        old_note = str(current.get("notes") or "").strip()
        current["notes"] = (old_note + "\n" if old_note else "") + note.strip()
    return _append(current, f"status:{target}", path)


def next_actions(limit: int = 20, path: Path | None = None) -> list[dict[str, Any]]:
    """Danh sách việc con người cần làm tiếp, không chứa job AURA có thể tự làm."""
    labels = {
        "needs_source": "Bổ sung URL tin tuyển dụng thật hoặc bỏ cơ hội này.",
        "research_needed": "Mở URL, xác minh tin còn tuyển rồi mới yêu cầu AURA soạn lại.",
        "needs_owner_approval": "Đọc pitch/demo, điền chỗ trống và quyết định có nộp không.",
        "approved_to_submit": "Tự gửi hồ sơ trên nền tảng; xong bấm ‘Đã nộp’ để ghi sổ.",
        "submitted": "Theo dõi phản hồi khách; không tạo hồ sơ mới thay cho việc follow-up.",
        "replied": "Trả lời khách hoặc chốt lịch phỏng vấn trong ngày.",
        "interview": "Chuẩn bị demo và chốt phạm vi/giá trước khi nhận việc.",
        "won": "Chốt brief, mốc bàn giao và điều kiện thanh toán bằng văn bản.",
        "delivering": "Làm đúng phạm vi đã chốt; báo tiến độ cho khách.",
        "delivered": "Gửi bàn giao/invoice và xin xác nhận đã nhận.",
        "invoiced": "Theo dõi thanh toán; chỉ đánh dấu paid khi tiền đã về.",
    }
    rows = []
    for deal in list_deals(limit=500, path=path):
        action = labels.get(str(deal.get("status") or ""))
        if action:
            rows.append({**deal, "next_action": action})
    rows.sort(
        key=lambda item: (
            _ACTION_PRIORITY.get(str(item.get("status")), 99),
            -int(item.get("fit_score") or 0),
            -int(item.get("updated_at") or 0),
        )
    )
    return rows[:max(1, limit)]


def auto_draft_slots(path: Path | None = None) -> int:
    """Số hồ sơ scout còn được phép tự soạn trong ngày local hiện tại."""
    now = datetime.now()
    day_start = int(now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp())
    used = sum(
        1
        for deal in list_deals(limit=5000, path=path)
        if deal.get("origin") == "scout" and int(deal.get("created_at") or 0) >= day_start
    )
    cap = int(getattr(settings, "work_for_hire_daily_draft_cap", 3))
    return max(0, cap - used)


def summary(path: Path | None = None) -> dict[str, Any]:
    rows = list_deals(limit=5000, path=path)
    by_status: dict[str, int] = {}
    paid_by_currency: dict[str, float] = {}
    for row in rows:
        status = str(row.get("status") or "")
        by_status[status] = by_status.get(status, 0) + 1
        if status == "paid":
            currency = str(row.get("currency") or "VND").upper()
            paid_by_currency[currency] = paid_by_currency.get(currency, 0.0) + float(row.get("amount") or 0)
    open_count = sum(1 for row in rows if row.get("status") not in {"paid", "lost", "not_pursued"})
    return {
        "total": len(rows),
        "open": open_count,
        "needs_owner": by_status.get("needs_owner_approval", 0),
        "ready_to_submit": by_status.get("approved_to_submit", 0),
        "submitted": by_status.get("submitted", 0),
        "won": by_status.get("won", 0),
        "paid_by_currency": paid_by_currency,
        "by_status": by_status,
    }


def dashboard_data(path: Path | None = None) -> dict[str, Any]:
    return {"summary": summary(path), "deals": list_deals(path=path), "actions": next_actions(path=path)}


__all__ = [
    "auto_draft_slots", "create_draft", "dashboard_data", "is_listing_url", "list_deals", "next_actions",
    "summary", "transition",
]
