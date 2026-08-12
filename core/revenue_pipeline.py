"""
core/revenue_pipeline.py
========================
PIPELINE QUẢN LÝ KHÁCH HÀNG & DÒNG TIỀN (§10 - CODEX REVIEW VÒNG 3)
===================================================================
- KHÓA DANH SÁCH TIỀN TỆ HỢP LỆ: ALLOWED_CURRENCIES = {"VND", "USD", "EUR"}. Từ chối tiền rác như 'BANANA'.
- ĐẾM TÍCH LŨY THEO MỐC ĐÃ ĐẠT (CUMULATIVE FUNNEL): Lead tiến từ pitched -> replied vẫn giữ điểm ever_pitched.
- CẤM TỰ KHAI DOANH THU: pilot_paid / retainer CHỈ được tạo từ sự kiện cashflow đã 'confirmed' trong core/cashflow.py.
- Ghi vết experiment_id cho từng bản ghi.
- Doanh thu là bất biến và tách riêng theo từng loại tiền tệ (verified_revenue_by_currency).
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from core.config import settings, PROJECT_ROOT

logger = logging.getLogger("aura.revenue_pipeline")
_PIPELINE_FILE = PROJECT_ROOT / "data" / "ledger" / "revenue_pipeline.jsonl"

ALLOWED_CURRENCIES = frozenset({"VND", "USD", "EUR"})

VALID_STATES = (
    "qualified",
    "pitched",
    "replied",
    "pilot_paid",
    "delivering",
    "retainer",
    "lost",
)

VALID_TRANSITIONS = {
    "qualified": ["pitched", "lost"],
    "pitched": ["replied", "lost"],
    "replied": ["pilot_paid", "lost"],
    "pilot_paid": ["delivering", "lost"],
    "delivering": ["retainer", "lost"],
    "retainer": ["lost"],
    "lost": ["qualified"],
}

# Thứ tự cấp độ funnel để tính điểm tích lũy
STAGE_ORDER = {
    "qualified": 1,
    "pitched": 2,
    "replied": 3,
    "pilot_paid": 4,
    "delivering": 5,
    "retainer": 6,
    "lost": 0,
}


def _read_all_pipeline_events(file_path: Path | None = None) -> list[dict[str, Any]]:
    p = file_path or _PIPELINE_FILE
    if not p.is_file():
        return []
    events: list[dict[str, Any]] = []
    try:
        lines = p.read_text(encoding="utf-8").splitlines()
        for line in lines:
            if not line.strip():
                continue
            events.append(json.loads(line))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Đọc pipeline ledger lỗi: %s", exc)
    return events


def _require_experiment_id(experiment_id: str) -> str:
    clean = str(experiment_id or "").strip()
    if not clean:
        raise ValueError("Pipeline Revenue Operator bắt buộc có experiment_id hiện hành.")
    return clean


def get_current_lead_state(
    lead_id: str,
    experiment_id: str,
    file_path: Path | None = None,
) -> str | None:
    """Lấy trạng thái hiện tại của lead."""
    experiment_id = _require_experiment_id(experiment_id)
    events = _read_all_pipeline_events(file_path)
    current_state = None
    for ev in events:
        if (
            ev.get("lead_id") == lead_id
            and str(ev.get("experiment_id") or "") == experiment_id
        ):
            current_state = ev.get("status")
    return current_state


def get_lead_snapshot(
    lead_id: str,
    experiment_id: str,
    file_path: Path | None = None,
) -> dict[str, Any] | None:
    """Gộp dữ liệu bất biến của lead với event mới nhất trong đúng experiment."""
    experiment_id = _require_experiment_id(experiment_id)
    snapshot: dict[str, Any] | None = None
    for event in _read_all_pipeline_events(file_path):
        if (
            event.get("lead_id") != lead_id
            or str(event.get("experiment_id") or "") != experiment_id
        ):
            continue
        if snapshot is None:
            snapshot = {}
        for key, value in event.items():
            if value not in (None, ""):
                snapshot[key] = value
    return snapshot


def validate_state_transition(current_state: str | None, new_state: str) -> None:
    """Kiểm tra tính hợp lệ của việc chuyển trạng thái theo VALID_TRANSITIONS."""
    new_state = new_state.lower().strip()
    if new_state not in VALID_STATES:
        raise ValueError(f"Trạng thái '{new_state}' không nằm trong VALID_STATES: {VALID_STATES}")

    if current_state is None:
        if new_state != "qualified":
            raise ValueError(f"Lead mới bắt buộc khởi tạo ở trạng thái 'qualified' (không thể vào trực tiếp '{new_state}')")
        return

    allowed = VALID_TRANSITIONS.get(current_state, [])
    if new_state not in allowed:
        raise ValueError(f"Chuyển trạng thái từ '{current_state}' sang '{new_state}' là KHÔNG HỢP LỆ. Cho phép: {allowed}")


def update_pipeline_status(
    lead_id: str,
    title: str,
    status: str,
    notes: str = "",
    experiment_id: str = "",
    url: str = "",
    contact_channel: str = "",
    file_path: Path | None = None,
) -> dict[str, Any]:
    """Cập nhật trạng thái lead trong Pipeline."""
    status = status.lower().strip()
    experiment_id = _require_experiment_id(experiment_id)

    if status in ("pilot_paid", "retainer"):
        raise PermissionError(
            f"Trạng thái '{status}' CHỈ được cập nhật qua hàm confirm_payment_from_cashflow kèm cashflow event_id đã xác nhận."
        )

    current_state = get_current_lead_state(lead_id, experiment_id, file_path)
    validate_state_transition(current_state, status)

    p = file_path or _PIPELINE_FILE
    p.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": int(time.time()),
        "experiment_id": experiment_id,
        "lead_id": lead_id,
        "title": title,
        "url": str(url or "").strip(),
        "contact_channel": str(contact_channel or "").strip(),
        "status": status,
        "cashflow_event_id": "",
        "amount": 0.0,
        "currency": "VND",
        "notes": notes,
    }

    try:
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        logger.info("RevenuePipeline: Lead '%s' (%s) -> trạng thái '%s'", lead_id, title[:30], status)
    except Exception as exc:
        logger.error("Ghi pipeline lỗi: %s", exc)
        raise RuntimeError(f"Ghi file pipeline ledger thất bại: {exc}") from exc

    return entry


def confirm_payment_from_cashflow(
    lead_id: str,
    title: str,
    status: str,
    cashflow_event_id: str,
    notes: str = "",
    experiment_id: str = "",
    file_path: Path | None = None,
    cashflow_path: Path | None = None,
) -> dict[str, Any]:
    """Chuyển lead sang pilot_paid/retainer NẾU có cashflow event đã 'confirmed' từ Chủ và tiền tệ hợp lệ."""
    status = status.lower().strip()
    experiment_id = _require_experiment_id(experiment_id)
    if status not in ("pilot_paid", "retainer"):
        raise ValueError("Hàm confirm_payment_from_cashflow chỉ dùng cho trạng thái 'pilot_paid' hoặc 'retainer'.")

    # 1. Kiểm tra VALID_TRANSITIONS
    current_state = get_current_lead_state(lead_id, experiment_id, file_path)
    validate_state_transition(current_state, status)

    # 2. Đọc API public get_confirmed_cashflow từ core.cashflow
    from core.cashflow import get_confirmed_cashflow
    cashflow_event = get_confirmed_cashflow(cashflow_event_id, path=cashflow_path)
    if cashflow_event is None:
        raise ValueError(f"Xác minh Cashflow thất bại: Cashflow event '{cashflow_event_id}' không tồn tại hoặc chưa được Chủ xác nhận (status!='confirmed')")

    amount = float(cashflow_event.get("amount") or 0.0)
    currency = str(cashflow_event.get("currency") or "VND").upper()

    # 3. Kiểm tra TIỀN TỆ ALLOWLIST
    if currency not in ALLOWED_CURRENCIES:
        raise ValueError(f"Loại tiền tệ '{currency}' KHÔNG HỢP LỆ. Danh sách tiền tệ được hỗ trợ: {sorted(list(ALLOWED_CURRENCIES))}")

    if amount <= 0:
        raise ValueError(f"Số tiền trong cashflow event '{cashflow_event_id}' phải lớn hơn 0 ({amount})")

    # 4. Chống ghi đối soát trùng cashflow_event_id
    events = _read_all_pipeline_events(file_path)
    for ev in events:
        if str(ev.get("cashflow_event_id") or "") == str(cashflow_event_id):
            raise ValueError(f"Cashflow event '{cashflow_event_id}' đã được đối soát trên pipeline trước đó!")

    p = file_path or _PIPELINE_FILE
    p.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": int(time.time()),
        "experiment_id": experiment_id,
        "lead_id": lead_id,
        "title": title,
        "status": status,
        "cashflow_event_id": cashflow_event_id,
        "amount": amount,
        "currency": currency,
        "notes": notes,
    }

    try:
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.error("Ghi confirm payment lỗi: %s", exc)
        raise RuntimeError(f"Ghi confirm payment thất bại: {exc}") from exc

    logger.info("RevenuePipeline: Lead '%s' CHUYỂN SANG '%s' với %s %s (Event: %s)", lead_id, status, amount, currency, cashflow_event_id)
    return entry


def get_pipeline_summary(experiment_id: str = "", file_path: Path | None = None) -> dict[str, Any]:
    """Thống kê Pipeline & Doanh thu thực nhận phân tách theo tiền tệ kèm mốc tích lũy (cumulative funnel)."""
    events = _read_all_pipeline_events(file_path)
    if experiment_id:
        events = [ev for ev in events if str(ev.get("experiment_id") or "") == str(experiment_id)]

    latest_lead_state: dict[str, dict] = {}
    highest_stage_per_lead: dict[str, int] = {}
    verified_payments: set[str] = set()
    verified_revenue_by_currency: dict[str, float] = {}

    for item in events:
        lid = item.get("lead_id")
        st = item.get("status", "qualified")
        if lid:
            latest_lead_state[lid] = item
            stage_val = STAGE_ORDER.get(st, 0)
            highest_stage_per_lead[lid] = max(highest_stage_per_lead.get(lid, 0), stage_val)

        cid = item.get("cashflow_event_id")
        amt = float(item.get("amount") or 0.0)
        curr = str(item.get("currency") or "VND").upper()

        if cid and cid not in verified_payments and amt > 0 and curr in ALLOWED_CURRENCIES:
            verified_payments.add(cid)
            verified_revenue_by_currency[curr] = verified_revenue_by_currency.get(curr, 0.0) + amt

    # Trạng thái hiện tại
    current_counts = {st: 0 for st in VALID_STATES}
    for lid, item in latest_lead_state.items():
        st = item.get("status", "qualified")
        if st in current_counts:
            current_counts[st] += 1

    # Đếm tích lũy (ever reached stage)
    cumulative_counts = {
        "ever_qualified": sum(1 for val in highest_stage_per_lead.values() if val >= 1),
        "ever_pitched": sum(1 for val in highest_stage_per_lead.values() if val >= 2),
        "ever_replied": sum(1 for val in highest_stage_per_lead.values() if val >= 3),
        "ever_pilot_paid": sum(1 for val in highest_stage_per_lead.values() if val >= 4),
        "ever_delivering": sum(1 for val in highest_stage_per_lead.values() if val >= 5),
        "ever_retainer": sum(1 for val in highest_stage_per_lead.values() if val >= 6),
    }

    return current_counts | cumulative_counts | {"verified_revenue_by_currency": verified_revenue_by_currency}
