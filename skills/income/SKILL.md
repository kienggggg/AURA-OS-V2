---
name: income.ledger
description: SỔ THU NHẬP của xưởng kiếm tiền — ghi một khoản tiền về/chi ra (record) hoặc xem tổng kết tháng (summary). Dùng khi Sếp nói qua chat "bán được truyện X 200k", "ghi sổ 50 đô gig Fiverr", "tháng này kiếm được bao nhiêu". Cùng một sổ với dashboard (data/ledger/income.jsonl).
entrypoint: scripts/income_tool.py
function: tool_income
version: 1.0.0
tier: local
cost: free
permissions: [file_read, file_write]
---

# Income Ledger — sổ thu nhập qua chat

## Tham số

| Tên | Kiểu | Bắt buộc | Ý nghĩa |
|-----|------|----------|---------|
| `action` | str | ✅ | `record` \| `summary` |
| `item` | str | khi record | Khoản gì (vd "bán PDF Tây Du Ký ch1-10") |
| `amount` | float | khi record | Số tiền; ÂM = chi ra |
| `product_line` | str | ✗ | video/novel/comic/cv/khac (mặc định khac) |
| `note` | str | ✗ | Ghi chú |
| `month` | str | ✗ | 'YYYY-MM' cho summary (mặc định tháng này) |
