"""
core/market_test.py
===================
BỘ ĐO LƯỜNG CHỈ SỐ THỊ TRƯỜNG THEO TỪNG EXPERIMENT COHORT & WINDOW (§10 - CODEX REVIEW VÒNG 3)
=============================================================================================
- Quản lý experiment_id, started_at, active_niche.
- GIỚI HẠN THỜI GIAN NGHIÊM NGẶT:
  - Checkpoint 14d CHỈ xét sự kiện trong cửa sổ: started_at <= ts <= started_at + 14 * 86400.
  - Checkpoint 30d CHỈ xét sự kiện trong cửa sổ: started_at <= ts <= started_at + 30 * 86400.
- ĐẾM TÍCH LŨY CUMULATIVE FUNNEL: ever_pitched, ever_replied, ever_pilot_paid.
- Báo rõ trạng thái IN_PROGRESS kèm số ngày còn lại trong cửa sổ 14d / 30d.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from core.config import settings, PROJECT_ROOT
from core.lead_collector import get_current_verified_leads, ACTIVE_NICHE
from core.revenue_pipeline import STAGE_ORDER, ALLOWED_CURRENCIES, _read_all_pipeline_events

logger = logging.getLogger("aura.market_test")
_COHORT_FILE = PROJECT_ROOT / "data" / "ledger" / "experiment_cohort.json"


def get_or_create_experiment_cohort() -> dict[str, Any]:
    """Lấy hoặc khởi tạo experiment cohort thử nghiệm."""
    if _COHORT_FILE.is_file():
        try:
            return json.loads(_COHORT_FILE.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            pass

    now = int(time.time())
    cohort = {
        "experiment_id": f"EXP-AURA-{now}",
        "started_at": now,
        "active_niche": ACTIVE_NICHE,
    }
    _COHORT_FILE.parent.mkdir(parents=True, exist_ok=True)
    _COHORT_FILE.write_text(json.dumps(cohort, ensure_ascii=False, indent=2), encoding="utf-8")
    return cohort


def evaluate_market_metrics(
    file_path: Path | None = None,
    leads_path: Path | None = None,
) -> dict[str, Any]:
    """Đánh giá chỉ số thử nghiệm thị trường lọc theo Cohort timestamp và giới hạn cửa sổ 14d/30d."""
    cohort = get_or_create_experiment_cohort()
    started_at = int(cohort.get("started_at") or 0)
    exp_id = str(cohort.get("experiment_id") or "").strip()
    niche = str(cohort.get("active_niche") or ACTIVE_NICHE)
    if not exp_id:
        raise ValueError("Experiment cohort không có experiment_id hợp lệ.")

    now = int(time.time())
    elapsed_seconds = now - started_at
    elapsed_days = elapsed_seconds / 86400.0

    window_14d_end = started_at + (14 * 86400)
    window_30d_end = started_at + (30 * 86400)

    # Đọc verified leads audit từ current batch
    leads, batch_status = get_current_verified_leads(
        expected_experiment_id=exp_id,
        file_path=leads_path,
    )

    # Lọc leads trong cửa sổ 14d VÀ thuộc experiment_id hiện tại
    leads_14d = [
        l for l in leads
        if str(l.get("experiment_id") or "") == exp_id and
        started_at <= int(l.get("collected_at") or 0) <= window_14d_end and l.get("niche") == niche
    ]
    verified_leads_14d_count = len(leads_14d)

    # Đọc pipeline events
    all_events = _read_all_pipeline_events(file_path)

    # 1. Tính chỉ số cho Cửa sổ 14d (started_at <= ts <= window_14d_end VÀ experiment_id khớp)
    events_14d = [
        ev for ev in all_events
        if str(ev.get("experiment_id") or "") == exp_id and
        started_at <= int(ev.get("ts") or 0) <= window_14d_end
    ]

    highest_stage_14d: dict[str, int] = {}
    verified_payments_14d: set[str] = set()
    rev_14d: dict[str, float] = {}

    for ev in events_14d:
        lid = ev.get("lead_id")
        st = ev.get("status", "qualified")
        if lid:
            stage_val = STAGE_ORDER.get(st, 0)
            highest_stage_14d[lid] = max(highest_stage_14d.get(lid, 0), stage_val)

        cid = ev.get("cashflow_event_id")
        amt = float(ev.get("amount") or 0.0)
        curr = str(ev.get("currency") or "VND").upper()
        if cid and cid not in verified_payments_14d and amt > 0 and curr in ALLOWED_CURRENCIES:
            verified_payments_14d.add(cid)
            rev_14d[curr] = rev_14d.get(curr, 0.0) + amt

    ever_pitched_14d = sum(1 for val in highest_stage_14d.values() if val >= 2)
    ever_replied_14d = sum(1 for val in highest_stage_14d.values() if val >= 3)
    ever_pilot_paid_14d = sum(1 for val in highest_stage_14d.values() if val >= 4)

    req_14d_leads = verified_leads_14d_count >= 20
    req_14d_pitched = ever_pitched_14d >= 10
    req_14d_response = (ever_replied_14d >= 3 or ever_pilot_paid_14d >= 1)

    if now >= window_14d_end:
        status_14d = "PASS" if (req_14d_leads and req_14d_pitched and req_14d_response) else "FAIL"
    else:
        days_left_14 = max(0, 14 - int(elapsed_days))
        status_14d = f"IN_PROGRESS ({days_left_14} ngày còn lại trong cửa sổ 14d)"

    # 2. Tính chỉ số cho Cửa sổ 30d (started_at <= ts <= window_30d_end VÀ experiment_id khớp)
    events_30d = [
        ev for ev in all_events
        if str(ev.get("experiment_id") or "") == exp_id and
        started_at <= int(ev.get("ts") or 0) <= window_30d_end
    ]
    highest_stage_30d: dict[str, int] = {}
    for ev in events_30d:
        lid = ev.get("lead_id")
        st = ev.get("status", "qualified")
        if lid:
            stage_val = STAGE_ORDER.get(st, 0)
            highest_stage_30d[lid] = max(highest_stage_30d.get(lid, 0), stage_val)

    ever_retainer_30d = sum(1 for val in highest_stage_30d.values() if val >= 6)

    if now >= window_30d_end:
        status_30d = "PASS" if ever_retainer_30d >= 3 else "FAIL"
    else:
        days_left_30 = max(0, 30 - int(elapsed_days))
        status_30d = f"IN_PROGRESS ({days_left_30} ngày còn lại trong cửa sổ 30d)"

    return {
        "experiment_id": exp_id,
        "active_niche": niche,
        "started_at": started_at,
        "elapsed_days": round(elapsed_days, 2),
        "batch_status": batch_status,
        "verified_leads_14d_count": verified_leads_14d_count,
        "ever_pitched_14d": ever_pitched_14d,
        "ever_replied_14d": ever_replied_14d,
        "ever_pilot_paid_14d": ever_pilot_paid_14d,
        "ever_retainer_30d": ever_retainer_30d,
        "verified_revenue_14d": rev_14d,
        "checkpoint_14d_status": status_14d,
        "checkpoint_30d_status": status_30d,
        "evaluated_at": now,
    }
