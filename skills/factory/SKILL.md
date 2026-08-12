---
name: factory.control
description: Điều khiển XƯỞNG KIẾM TIỀN — đưa việc vào hàng đợi (enqueue), xem trạng thái/tiến độ (status), liệt kê job (list), hoặc hủy job (cancel). Dùng khi Sếp nói qua chat "chạy dịch video này", "xem tiến độ xưởng", "hủy job X" — CÙNG một hàng đợi với dashboard web (localhost:8766), không phải đường thực thi riêng.
entrypoint: scripts/factory_tool.py
function: tool_factory
version: 1.0.0
tier: local
cost: free
permissions: [file_read, file_write]
---

# Factory Control — cổng chat vào Xưởng Kiếm Tiền

Skill mỏng: KHÔNG tự chạy job, chỉ đọc/ghi cùng hàng đợi sqlite mà
`factory/worker.py` (chạy trong daemon) và dashboard web dùng. Bảo đảm chat,
mascot, và dashboard đều điều khiển **một** nguồn sự thật duy nhất.

## Tham số

| Tên | Kiểu | Bắt buộc | Ý nghĩa |
|-----|------|----------|---------|
| `action` | str | ✅ | `enqueue` \| `status` \| `list` \| `cancel` |
| `tool` | str | khi enqueue | Tên ToolSpec, vd `video.factory`, `novel.translate` |
| `params` | dict | khi enqueue | Tham số truyền cho tool (khớp `form_fields` của ToolSpec) |
| `job_id` | str | khi status/cancel | id job (8 ký tự hex) |

## Khi nào DÙNG
- Sếp muốn giao việc kiếm tiền qua chat thay vì mở trình duyệt.
- Cần hỏi nhanh "job đang chạy tới đâu rồi".

## Khi nào KHÔNG dùng
- Muốn xem trực quan hàng đợi/QC/sổ thu nhập → hướng Sếp mở dashboard
  (http://127.0.0.1:8766) thay vì liệt kê dài dòng qua chat.
