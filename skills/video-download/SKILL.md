---
name: video.download
description: Tải file video/file lớn từ URL trực tiếp về data/downloads/ (stream theo chunk, kiểm RAM trống trước khi tải). Dùng khi Sếp nói "tải video này về", "download file ở link...". Tham số: url (bắt buộc), output_path (tuỳ chọn). CHỈ tải link http/https trực tiếp — trang YouTube/streaming cần công cụ khác. Có GHI FILE ra đĩa — đi qua Vibe Diff.
entrypoint: scripts/download.py
function: tool_download_video
version: 1.0.0
tier: local
cost: free
permissions: [network]
---

# Video Download — "Tải video về nhà"

Tool do **AURA TỰ VIẾT** qua Triad Council (task #52385, Sếp duyệt 02/07/2026),
sau đó được gia cố thêm 2 chỗ Council bỏ lọt:

1. **`timeout=(10, 60)`** cho request — không có nó, server "đen" làm tool đơ vô hạn
   (đúng họ lỗi từng làm Council treo).
2. **Đường dẫn neo vào gốc dự án** — mặc định luôn là `D:\AURA_OS_v2\data\downloads\`,
   không phụ thuộc thư mục hiện hành.

## Dùng
`video.download(url="https://...", output_path="tuỳ chọn")` → tải stream theo chunk 8KB,
kiểm RAM trống ≥500MB trước khi tải. Trả đường dẫn file khi xong.
