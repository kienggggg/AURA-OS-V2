"""
factory/ledger.py
==================
Sổ thu nhập của xưởng — JSONL append-only (pattern giống applications.jsonl):
mỗi dòng 1 giao dịch {ts, product_line, item, amount, currency, direction, note,
job_id}. direction: "in" = tiền về (bán truyện, gig...), "out" = chi phí.

Sổ sách KHÔNG mutate — chỉ append — nên JSONL là đúng bài (khác jobs.db sqlite).
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path

from core.config import settings

_LEDGER_PATH = settings.ledger_dir / "income.jsonl"


def record(product_line: str, item: str, amount: float, direction: str = "in",
           note: str = "", job_id: str = "", currency: str | None = None) -> dict:
    row = {
        "ts": int(time.time()),
        "product_line": str(product_line),
        "item": str(item),
        "amount": float(amount),
        "currency": currency or settings.income_currency,
        "direction": "out" if str(direction).lower() == "out" else "in",
        "note": str(note),
        "job_id": str(job_id),
    }
    _LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _LEDGER_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


def entries(limit: int = 200) -> list[dict]:
    if not _LEDGER_PATH.exists():
        return []
    rows = []
    for line in _LEDGER_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows[-limit:][::-1]   # mới nhất lên đầu


def monthly_summary(month: str | None = None) -> dict:
    """Tổng theo dòng sản phẩm của 1 tháng ('YYYY-MM', mặc định tháng này)."""
    month = month or datetime.now().strftime("%Y-%m")
    by_line: dict[str, float] = {}
    total_in = total_out = 0.0
    for r in entries(limit=100000):
        if datetime.fromtimestamp(r["ts"]).strftime("%Y-%m") != month:
            continue
        amt = float(r.get("amount") or 0)
        if r.get("direction") == "out":
            total_out += amt
        else:
            total_in += amt
            key = str(r.get("product_line") or "khac")
            by_line[key] = by_line.get(key, 0) + amt
    return {
        "month": month,
        "total_in": total_in,
        "total_out": total_out,
        "net": total_in - total_out,
        "by_product_line": by_line,
        "currency": settings.income_currency,
    }


__all__ = ["record", "entries", "monthly_summary"]
