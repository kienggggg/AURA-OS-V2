---
name: trash.janitor
description: Công nhân dọn rác — quét file rác theo LUẬT CỨNG (đuôi .tmp/.dmp/.crdownload/.bak/.swp, tên rác Thumbs.db/.DS_Store, file khoá Office, backup ~, file 0 byte, đủ cũ) đưa vào Recycle Bin (hoàn tác được); model embedding local CHỈ ĐỀ XUẤT phân loại file cũ trong Downloads. Mặc định dry-run, an toàn tuyệt đối, hợp chạy ngầm 1 lần/ngày.
entrypoint: janitor.py
function: tool_janitor
version: 1.0.0
tier: local
cost: free
permissions: [file_read, file_write]
---

# Janitor — công nhân dọn rác

Công nhân thứ ba theo mô hình "quản gia giao tool cho thợ": pipeline code cầm tool
(quét thư mục, Recycle Bin), model nhỏ chỉ đóng vai con mắt phán đoán — và ở skill
này model còn bị **tước quyền dọn**: chỉ được đề xuất.

## Phân quyền (thiết kế an toàn 3 tầng)
1. **Luật cứng mới được dọn**: đuôi rác (`.tmp .temp .dmp .crdownload .partial .part
   .download`), file khoá Office (`~$...`), file 0 byte — TẤT CẢ phải cũ hơn
   `janitor_min_age_days` (mặc định 30 ngày). Dọn = `send2trash` vào **Recycle Bin**,
   không bao giờ xoá vĩnh viễn.
2. **Model chỉ đề xuất**: công nhân embedding (`core/embedder.py`) phân loại file cũ
   trong Downloads theo tên (installer/archive/document/media/code) kèm gợi ý
   ("cài xong thì xoá được") — Sếp tự quyết.
3. **Vành đai**: không đụng file trong project AURA, bỏ symlink/junction/file SYSTEM,
   trần `janitor_max_recycle` file/lượt, file >2GB không tự dọn, mặc định `apply=False`.

## Khi nào DÙNG
- Daemon gọi định kỳ (1 lần/ngày) với `apply=true` — dọn temp lặng lẽ, báo cáo một chiều.
- Sếp muốn xem trước: chạy dry-run rồi tự quyết.

## Tham số
| Tên | Kiểu | Bắt buộc | Ý nghĩa |
|-----|------|----------|---------|
| `apply` | bool | ✖ | True = dọn thật (Recycle Bin). Mặc định False = chỉ báo cáo. |
| `min_age_days` | float | ✖ | Chỉ đụng file cũ hơn ngần này ngày (mặc định config, 30). |
| `as_json` | bool | ✖ | Trả JSON thay vì báo cáo markdown. |

## Cấu hình (.env)
`JANITOR_RULE_DIRS` (mặc định %TEMP%), `JANITOR_SUGGEST_DIRS` (mặc định ~/Downloads),
`JANITOR_MIN_AGE_DAYS`, `JANITOR_MAX_RECYCLE`.

## Hướng dẫn thực thi (Instructions)
- Đường chính: `registry.execute_tool("trash.janitor", {"apply": true})`.
- Chạy độc lập: `python skills/janitor/janitor.py` (dry-run) / `--apply` (dọn thật).

## Đầu ra
`ToolResult.output`: số rác theo luật (+ dung lượng), số file đã vào Recycle Bin,
danh sách đề xuất của model. Báo cáo máy đọc ở `data/feedback/janitor_last.json`
(hàng đợi một chiều cho quản gia/UI).
