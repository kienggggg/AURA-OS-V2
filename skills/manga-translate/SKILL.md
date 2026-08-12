---
name: manga.translate
description: Dịch một chapter ĐÃ TẢI sang Tiếng Việt bằng OCR local (easyocr) + deep-translator, in chữ Việt đè lên ảnh.
entrypoint: scripts/translator.py
function: tool_translate_manga
version: 1.0.0
tier: local
cost: free
depends_on: manga.download
---

# Manga Translate

Pipeline chạy **local hoàn toàn**: OCR (easyocr) → dịch (deep-translator, Google free)
→ vẽ chữ Việt word-wrap/auto-fit đè lên ảnh gốc. Đầu ra lưu ở
`data/downloads/<title>_Translated/<chapter_label>/`.

## Khi nào DÙNG
- Người dùng muốn **dịch / Việt hoá** một chapter đã có ảnh trên đĩa.
- Sau khi `manga.download` đã tải chapter về (xem `depends_on`).

## Khi nào KHÔNG dùng
- Chapter CHƯA tải mà cũng KHÔNG có `source_url` để tự tải → trả lỗi, xin link.
- Máy chưa cài `easyocr` / `deep-translator` / `Pillow` → skill báo lệnh cài rõ ràng.

## Tham số
| Tên | Kiểu | Bắt buộc | Ý nghĩa |
|-----|------|----------|---------|
| `title` | str | ✅ | Tên truyện (khớp thư mục đã tải). |
| `chapter` | float | ✅ | Số chương; hỗ trợ `10.5`. |
| `source_url` | str | ✖ | Nếu chapter chưa tải, đưa link để tự tải trước (xem dưới). |
| `auto_download` | bool | ✖ | Mặc định `true`: tự gọi `manga.download` khi thiếu ảnh nguồn. |

## Liên kết nội bộ (gọi chéo skill — ĐÚNG chuẩn Lazy-load)
Khi thư mục nguồn chưa tồn tại và có `source_url`, skill **KHÔNG import** script của
`manga.download`. Thay vào đó nó gọi qua registry:

```python
from tools.registry import call_skill
call_skill("manga.download", {"title": title, "chapter": chapter, "source_url": source_url})
```

Nhờ vậy code của `manga.download` vẫn chỉ được nạp (importlib) khi THỰC SỰ chạy, đúng
triết lý Tiết lộ Lũy tiến, và hai skill dùng chung cache hàm của registry mặc định.

## Hướng dẫn thực thi (Instructions)
**KHÔNG tự OCR / tự dịch / tự vẽ chữ.** Logic đã nằm trong script. Chỉ GỌI:

- Đường chính: `registry.execute_tool("manga.translate", {"title": ..., "chapter": ...})`.
- Kiểm thử độc lập (Level 4):

  ```bash
  python skills/manga-translate/scripts/translator.py --title "One Piece" --chapter 1095
  ```

## Đầu ra
`ToolResult.output`: tóm tắt `Đã dịch N trang (lỗi M) → <thư mục đích>`. Ảnh đã dịch
nằm trong `ToolResult.artifacts`.
