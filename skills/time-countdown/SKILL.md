---
name: time.countdown
description: Tính SỐ NGÀY còn lại từ hôm nay tới một ngày mục tiêu (định dạng YYYY-MM-DD). Dùng khi Sếp hỏi "còn bao nhiêu ngày tới ngày X", "đếm ngược tới...", "mấy ngày nữa thì...". Hợp cho việc theo dõi mốc như ngày thi, hạn nộp hồ sơ. Tham số bắt buộc: target_date.
entrypoint: scripts/countdown.py
function: tool_days_to_target
version: 1.0.0
tier: local
cost: free
---

# Time Countdown — "Đếm ngược tới ngày mục tiêu"

Tool do AURA TỰ VIẾT qua Triad Council (Generator chạy trên pool free, qua CodeGate + Sandbox),
sau đó đóng gói thành skill bền vững.

## Dùng
`time.countdown(target_date="YYYY-MM-DD")` → trả số ngày còn lại từ hôm nay tới ngày đó.

- Thiếu `target_date` → `ToolResult.failure`.
- Sai định dạng → báo lỗi rõ.
- Ngày đã qua → báo lỗi.
