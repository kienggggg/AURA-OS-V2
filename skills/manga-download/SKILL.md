---
name: manga.download
description: Tải toàn bộ ảnh của MỘT chapter truyện từ URL trang đọc về data/downloads/.
entrypoint: scripts/downloader.py
function: tool_download_manga
version: 1.0.0
tier: local
cost: free
permissions: [network]
---

# Manga Download

Tải mọi trang ảnh của một chapter từ một URL trang đọc truyện (HTML có thẻ `<img>`),
lưu về `data/downloads/<title>/<chapter_label>/` và đánh số `01, 02, …`.

## Khi nào DÙNG
- Người dùng muốn **tải / lưu / kéo về** một chapter truyện và đã có link trang đọc.
- Là bước CHUẨN BỊ trước khi gọi `manga.translate` (dịch cần ảnh đã nằm trên đĩa).

## Khi nào KHÔNG dùng
- Chỉ có TÊN truyện mà không có URL chapter → skill này chưa có bộ tra tên→link;
  hãy hỏi người dùng link, hoặc dùng `web.scrape` / `web_agent` để tìm link trước.
- Trang đọc render ảnh bằng JavaScript (lazy-load qua JS thuần) → có thể ra 0 ảnh.

## Tham số
| Tên | Kiểu | Bắt buộc | Ý nghĩa |
|-----|------|----------|---------|
| `title` | str | ✅ | Tên truyện (dùng đặt tên thư mục). |
| `chapter` | float | ✅ | Số chương; hỗ trợ chương lẻ như `10.5`. |
| `source_url` | str | ✅ | URL trang chapter để cào ảnh. |

## Hướng dẫn thực thi (Instructions)
**KHÔNG tự viết vòng lặp tải ảnh.** Logic (xoay User-Agent, proxy, retry backoff,
bóc ảnh lazy-load, lọc logo/banner) đã nằm trong script. Chỉ GỌI:

- Đường chính: `registry.execute_tool("manga.download", {"title": ..., "chapter": ..., "source_url": ...})`.
- Kiểm thử độc lập (Level 4 — procedural script):

  ```bash
  python skills/manga-download/scripts/downloader.py \
      --title "One Piece" --chapter 1095 --source-url "https://.../chap-1095"
  ```

## Đầu ra
`ToolResult.output` là JSON: `title, chapter, chapter_label, source_url,
output_folder, image_count, saved_files`. Đường dẫn ảnh nằm trong `ToolResult.artifacts`.
Nếu `image_count == 0` → trả `failure` (gợi ý trang dùng JS, cần web_agent).
