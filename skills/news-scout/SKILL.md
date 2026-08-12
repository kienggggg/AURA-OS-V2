---
name: news.scout
description: Nhịp tim đọc tin — kéo tiêu đề từ RSS/trang tin, chấm điểm hữu ích bằng công nhân embedding local (fallback LLM/heuristic) theo mục tiêu của Sếp, CHỈ kéo chi tiết bài điểm cao, và tự whitelist nguồn tốt. Nhẹ CPU, hợp chạy ngầm 2-3 lần/ngày.
entrypoint: scout.py
function: tool_news_scout
version: 1.0.0
tier: local
cost: free
permissions: [file_read, file_write, network]
---

# News Scout — "Nhịp tim đọc tin"

Tự động đọc tin định kỳ: kéo **tiêu đề** từ vài nguồn RSS/trang tin → **chấm điểm**
mức hữu ích theo mục tiêu cốt lõi của Sếp → **chỉ kéo nội dung chi tiết** cho bài điểm
cao (tiết kiệm CPU/mạng) → **đếm bài hữu ích theo domain** và tự ghi nguồn tốt vào
`data/whitelist_sources.json` để tăng tần suất quét.

Tuân thủ `CONTEXT.md`: bọc try/except (§2), trả `ToolResult`, read-only mạng + timeout
(§6), validate URL (§7), không secret (§1). Thiết kế **nhẹ**: parse RSS bằng stdlib,
chấm điểm 1 lần/cụm (batched), giới hạn số bài kéo chi tiết.

## Khi nào DÙNG
- Daemon gọi định kỳ (2-3 lần/ngày) để AURA "tự đọc báo" và đề xuất tin đáng chú ý.
- Người dùng muốn quét nhanh tin theo mục tiêu đã đặt (Python/AI,
  dựng video/CapCut, công nghệ, việc làm).

## Tham số
| Tên | Kiểu | Bắt buộc | Ý nghĩa |
|-----|------|----------|---------|
| `sources` | list[str]/str | ✖ | URL RSS/trang tin (mặc định bộ nguồn + whitelist đã học). |
| `goal` | str | ✖ | Mô tả mục tiêu để LLM chấm điểm (mặc định mục tiêu của Sếp). |
| `threshold` | float | ✖ | Ngưỡng điểm coi là "hữu ích" (mặc định 0.4). |
| `max_detail` | int | ✖ | Số bài điểm cao nhất được kéo chi tiết (mặc định 3 — giữ nhẹ). |
| `use_llm` | bool | ✖ | Dùng LLM local chấm điểm (mặc định True; offline → tự fallback heuristic). |
| `persist` | bool | ✖ | Cập nhật whitelist_sources.json (mặc định True). |
| `as_json` | bool | ✖ | Trả JSON có cấu trúc thay vì báo cáo markdown. |

## Cơ chế (nhẹ CPU)
1. **Kéo tiêu đề**: parse RSS bằng `xml.etree` (stdlib, không phụ thuộc); giới hạn N bài/nguồn.
2. **AI Judgment**: gom toàn bộ tiêu đề → **công nhân embedding** (`core/embedder.py`,
   MiniLM ~118M ONNX, chấm cả cụm trong ~0.3s, xong ca tự nhả RAM) so tiêu đề với các cụm
   trong `goal`, điểm cuối = max(embedding, heuristic). Công nhân hỏng → fallback **1 lần
   gọi LLM** (LocalCPUEngine) → heuristic từ khoá (không sập, không tốn CPU).
3. **Kéo chi tiết có chọn lọc**: chỉ `max_detail` bài điểm ≥ `threshold` mới tải nội dung.
4. **Auto-Subscribe**: cộng dồn số bài hữu ích theo domain vào `whitelist_sources.json`;
   domain vượt ngưỡng → đánh dấu `whitelisted=true` (lần sau quét được ưu tiên/tăng tần suất).

## Hướng dẫn thực thi (Instructions)
- Đường chính: `registry.execute_tool("news.scout", {"use_llm": true})`.
- Chạy độc lập (Level 4): `python skills/news-scout/scout.py --max-detail 3`.

## Đầu ra
`ToolResult.output`: báo cáo tin hữu ích (tiêu đề, điểm, nguồn, link, tóm tắt nếu kéo
chi tiết) + danh sách domain vừa được whitelist. Trạng thái học lưu ở
`data/whitelist_sources.json`.
