---
name: web.scrape
description: Cào text + URL ảnh từ MỘT trang web tĩnh chung (requests + BeautifulSoup). KHÔNG SỬ DỤNG tool này khi người dùng yêu cầu tải truyện tranh (manga). Hãy dùng manga.download thay thế.
entrypoint: scripts/scraper.py
function: tool_web_scrape
version: 1.0.0
tier: local
cost: free
permissions: [file_write, network]
---

# Web Scrape

Lấy **text sạch** và **danh sách URL ảnh** từ một trang web tĩnh (HTML server-render).
Đây là tool con nền tảng — các skill khác (vd `manga.download`) gọi lại nó.

## Khi nào DÙNG
- Cần đọc nội dung chữ của một bài viết / trang tài liệu để tóm tắt hoặc trích dẫn.
- Cần liệt kê các ảnh trên một trang (tuyệt đối hoá URL, đã lọc logo/banner/icon).
- Trang trả HTML đầy đủ ngay trong response (không phụ thuộc JavaScript).

## Khi nào KHÔNG dùng
- ⛔ **KHÔNG SỬ DỤNG khi người dùng yêu cầu tải truyện tranh (manga/truyện/chapter).**
  Đó là việc của `manga.download` (tải đúng cấu trúc thư mục, đặt tên trang, lazy-load).
  Dùng `web.scrape` cho manga là SAI tool — hãy gọi `manga.download` thay thế.
- Trang render hoàn toàn bằng JS / SPA (React, Vue...) → text rỗng. Khi đó dùng
  `web_agent` (browser-use) ở phase sau, KHÔNG cố cào bằng skill này.
- Cần đăng nhập, vượt captcha, hoặc tải file nhị phân lớn.

## Tham số
| Tên | Kiểu | Mặc định | Ý nghĩa |
|-----|------|----------|---------|
| `url` | str (bắt buộc) | — | URL http/https cần cào. |
| `max_chars` | int | 20000 | Cắt bớt text để tránh tràn context (Context Rot). |
| `include_images` | bool | true | Có bóc danh sách URL ảnh không. |
| `save` | bool | false | Ghi text ra `data/outputs/` và đính vào `artifacts`. |

## Hướng dẫn thực thi (Instructions)
**KHÔNG tự suy luận / tự viết lại logic cào.** Logic đã nằm trong script. Chỉ cần GỌI:

- Trong hệ thống (đường chính): để Orchestrator dispatch qua registry —
  `registry.execute_tool("web.scrape", {"url": "<URL>", "max_chars": 8000})`.
- Chạy độc lập để kiểm thử (Level 4 — procedural script):

  ```bash
  python skills/web-scrape/scripts/scraper.py --url "https://example.com" --max-chars 8000
  ```

Script tự lo: xoay User-Agent, proxy (`settings.manga_proxy`), timeout + retry backoff,
gỡ thẻ nhiễu (`script/style/nav/footer`), tuyệt đối hoá & lọc ảnh rác.

## Đầu ra
`ToolResult.output` là JSON string với các khoá:
`url, final_url, title, text, char_count, truncated, images, image_count`.
Khi `save=true`, đường dẫn file `.txt` nằm trong `ToolResult.artifacts`.

## Ví dụ
```text
Input : {"url": "https://example.com", "max_chars": 400}
Output: {"title": "Example Domain", "char_count": 230, "image_count": 0, ...}
```
