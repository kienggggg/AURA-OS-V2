"""
skills/income/scripts/income_tool.py
=====================================
Cổng chat vào sổ thu nhập (factory/ledger.py) — xem SKILL.md.
"""

from __future__ import annotations

from core.schemas import ToolResult
from factory import ledger


def tool_income(
    action: str,
    item: str = "",
    amount: float = 0.0,
    product_line: str = "khac",
    note: str = "",
    month: str | None = None,
) -> ToolResult:
    action = (action or "").strip().lower()

    if action == "record":
        if not item or not amount:
            return ToolResult.failure("income.ledger", "Thiếu 'item' hoặc 'amount'.")
        row = ledger.record(
            product_line=product_line, item=item, amount=abs(float(amount)),
            direction="out" if float(amount) < 0 else "in", note=note,
        )
        chieu = "chi ra" if row["direction"] == "out" else "tiền về"
        return ToolResult.success(
            "income.ledger",
            output=f"Đã ghi sổ: {row['item']} — {chieu} {row['amount']:,.0f} {row['currency']}.",
        )

    if action == "summary":
        s = ledger.monthly_summary(month)
        by = ", ".join(f"{k}: {v:,.0f}" for k, v in s["by_product_line"].items()) or "chưa có"
        return ToolResult.success(
            "income.ledger",
            output=(f"Tháng {s['month']}: về {s['total_in']:,.0f} {s['currency']}, "
                     f"chi {s['total_out']:,.0f}, ròng {s['net']:,.0f}. Theo dòng: {by}."),
        )

    return ToolResult.failure("income.ledger", f"action lạ: {action!r} (record/summary).")
