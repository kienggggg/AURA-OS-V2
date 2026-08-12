"""
core/freelance_ledger.py
========================
SỔ QUẢN LÝ THU NHẬP FREELANCE (INCOME & TASK LEDGER)
=====================================================
Ghi nhận thu nhập dự kiến & doanh thu thật từ các hợp đồng / task
mà AURA đã tự động thực thi và bàn giao cho khách hàng.
Lưu vết tại data/ledger/income.jsonl.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from core.config import settings

logger = logging.getLogger("aura.freelance_ledger")
_LEDGER_FILE = settings.ledger_dir / "income.jsonl"


def record_income(
    job_title: str,
    amount: float,
    currency: str = "VND",
    source: str = "freelance",
    status: str = "completed",
    notes: str = "",
) -> dict[str, Any]:
    """Ghi 1 dòng thu nhập / hợp đồng vào sổ ledger."""
    _LEDGER_FILE.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": int(time.time()),
        "job_title": job_title,
        "amount": amount,
        "currency": currency,
        "source": source,
        "status": status,
        "notes": notes,
    }
    try:
        with _LEDGER_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        logger.info("FreelanceLedger: Đã ghi nhận thu nhập '%s' (%s %s)", job_title, amount, currency)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Ghi sổ thu nhập lỗi: %s", exc)
    return entry


def get_income_summary() -> dict[str, Any]:
    """Tổng hợp doanh thu & thống kê công việc từ sổ ledger."""
    if not _LEDGER_FILE.is_file():
        return {
            "total_income_vnd": 0.0,
            "total_income_usd": 0.0,
            "completed_jobs": 0,
            "pending_jobs": 0,
        }

    total_vnd = 0.0
    total_usd = 0.0
    completed = 0
    pending = 0

    try:
        lines = _LEDGER_FILE.read_text(encoding="utf-8").strip().splitlines()
        for line in lines:
            if not line.strip():
                continue
            item = json.loads(line)
            amt = float(item.get("amount") or 0.0)
            curr = str(item.get("currency") or "VND").upper()
            st = str(item.get("status") or "completed").lower()

            if st in ("completed", "paid"):
                completed += 1
                if curr == "USD":
                    total_usd += amt
                else:
                    total_vnd += amt
            else:
                pending += 1
    except Exception as exc:  # noqa: BLE001
        logger.warning("Đọc sổ thu nhập lỗi: %s", exc)

    return {
        "total_income_vnd": total_vnd,
        "total_income_usd": total_usd,
        "completed_jobs": completed,
        "pending_jobs": pending,
    }
