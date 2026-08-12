---
name: web.agent
description: Mở TRÌNH DUYỆT THẬT headless (Playwright/Chromium) để render JavaScript và vượt JS-challenge (vd Cloudflare), chờ DOM load xong rồi lấy HTML/text thật. Dùng cho trang động/SPA mà web.scrape (requests tĩnh) lấy về rỗng.
entrypoint: scripts/browser_agent.py
function: tool_web_agent
version: 1.0.0
tier: local
cost: free
permissions: [network]
---

# Web Agent (Headless Browser)

Khi `web.scrape` (requests tĩnh) thất bại vì trang **render bằng JavaScript** hoặc dính
**JS-challenge của Cloudflare**, `web.agent` mở một **Chromium headless ẩn danh** qua
Playwright, chạy trọn JavaScript, **chờ thông minh** đến khi nội dung chính load xong,
rồi trả HTML/text thật.

Tuân thủ `CONTEXT.md`: bọc try/except (§2), trả `ToolResult`, validate URL (§7),
read-only (§6), không secret. Context trình duyệt **ephemeral** (tạo mới + đóng mỗi
lần, không profile lưu, có timeout). Vẫn đi qua cổng VIBE DIFF ở tầng Orchestrator.

## Khi nào DÙNG
- Trang động/SPA (React, Vue) hoặc có Cloudflare → `web.scrape` ra text rỗng.
- Cần nội dung **sau khi JS chạy** (danh sách job nạp bằng API, lazy render...).

## Khi nào KHÔNG dùng
- Trang HTML tĩnh bình thường → dùng `web.scrape` (nhẹ, nhanh hơn nhiều).
- Cần đăng nhập có MFA / giải CAPTCHA hình ảnh — ngoài phạm vi.

## Tham số
| Tên | Kiểu | Bắt buộc | Ý nghĩa |
|-----|------|----------|---------|
| `url` | str | ✅ | URL http/https cần render. |
| `wait_selector` | str | ✖ | CSS selector của element nội dung chính — chờ đến khi nó hiện. |
| `wait_until` | str | ✖ | `networkidle` (mặc định) / `load` / `domcontentloaded`. |
| `timeout_s` | float | ✖ | Hạn chờ tổng (mặc định 30s). |
| `max_chars` | int | ✖ | Cắt text trả về (mặc định 20000). |

## Cơ chế "Wait" thông minh
1. `goto(url, wait_until="networkidle")` — chờ mạng lắng (cho JS-challenge thời gian giải).
2. Nếu có `wait_selector` → `wait_for_selector(state="visible")`.
3. Nếu không → chờ `document.body.innerText.length > 200` (nội dung thực đã render).
4. Thêm một nhịp ngắn cho chắc, rồi mới `page.content()`.

## Hướng dẫn thực thi (Instructions)
**KHÔNG tự viết Selenium/requests rời.** Gọi script:

- Đường chính: `registry.execute_tool("web.agent", {"url": "...", "wait_selector": ".job-list"})`.
- Chạy độc lập (Level 4):

  ```bash
  python skills/web-agent/scripts/browser_agent.py --url "https://itviec.com/it-jobs/python" --wait-selector ".job"
  ```

Yêu cầu cài đặt một lần (máy thật):
```bash
pip install playwright playwright-stealth
python -m playwright install chromium
```

> `playwright-stealth` là BẮT BUỘC: tiêm tàng hình (`stealth_sync`) để vượt phát hiện headless của Cloudflare. Thiếu nó, `web.agent` trả lỗi kèm lệnh cài.

## Đầu ra
`ToolResult.output` là JSON: `url, final_url, title, text, html_len`. Thiếu Playwright/
Chromium → `ToolResult.failure` kèm lệnh cài (không làm sập hệ).
