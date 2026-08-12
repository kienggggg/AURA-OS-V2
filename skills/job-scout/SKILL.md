---
name: job.scout
description: Cào tin tuyển dụng từ vài URL, chấm Match Score theo từ khoá nghề/địa điểm đã đặt trong cấu hình rồi lập báo cáo cơ hội phù hợp nhất. KHÔNG dùng để tải truyện hay cào trang chung.
entrypoint: scripts/scout_jobs.py
function: tool_scout_jobs
version: 1.0.0
tier: local
cost: free
permissions: [network, shell]
---

# Job Scout

"Đặc vụ săn việc": cào nội dung vài trang tuyển dụng (giáo dục / IT / freelance),
đọc mô tả công việc, chấm **Match Score** theo từ khoá ưu tiên của Sếp, rồi xếp hạng
và lập báo cáo các cơ hội phù hợp nhất.

Cùng họ với `web.scrape` (requests + BeautifulSoup) và `tech.scout` (chấm điểm + tóm
tắt). Tuân thủ `CONTEXT.md`: validate input, bọc try/except, trả `ToolResult`, không
secret hardcode, chỉ đọc (read-only) — và **vẫn qua cổng VIBE DIFF** xin Sếp duyệt
trước khi cào.

## Khi nào DÙNG
- Sếp muốn **tìm việc / săn cơ hội** theo nghề & địa điểm đã đặt trong
  `SCOUT_KEYWORDS` / `SCOUT_PRIORITY_TERMS`.
- Đã có sẵn vài URL trang tuyển dụng để soi, hoặc muốn dùng danh sách URL mẫu.

## Khi nào KHÔNG dùng
- KHÔNG phải tải truyện (`manga.download`) hay cào trang chung (`web.scrape`).
- Trang tuyển dụng render bằng JS thuần (danh sách job nạp bằng API) → text rỗng;
  khi đó cần `web_agent` (browser) ở phase sau.

## Tham số
| Tên | Kiểu | Bắt buộc | Ý nghĩa |
|-----|------|----------|---------|
| `urls` | list[str] hoặc str | ✖ | Các URL tuyển dụng cần cào (mặc định dùng URL mẫu). |
| `keywords` | str | ✖ | Từ khoá chấm điểm, dạng `"kw:trọng_số, kw"`. Mặc định bộ ưu tiên của Sếp. |
| `top_k` | int | ✖ | Số cơ hội tốt nhất đưa vào báo cáo (mặc định 5). |
| `jobs` | list[dict] | ✖ | Dữ liệu việc có sẵn `[{title, description, url}]` — bỏ qua bước cào (test/offline). |
| `as_json` | bool | ✖ | Trả JSON có cấu trúc thay vì báo cáo markdown. |

## Hướng dẫn thực thi (Instructions)
**KHÔNG tự bịa kết quả săn việc.** Gọi script — nó lo cào (xoay User-Agent, timeout,
retry), chấm Match Score nhất quán, và tóm tắt mô tả:

- Đường chính: `registry.execute_tool("job.scout", {"urls": [...], "top_k": 5})`.
- Chạy độc lập (Level 4):

  ```bash
  python skills/job-scout/scripts/scout_jobs.py --url "https://..." --top-k 5
  ```

### Match Score
Điểm 0..1 = tổng trọng số từ khoá khớp / tổng trọng số. Bộ mặc định (trọng số):
ví dụ `<địa phương>`(3), `<ngành>`(3), `Video Editor`(2), `Python`(2), `AI`(1).
Mức: ≥0.6 CAO · ≥0.3 TRUNG BÌNH · >0 THẤP.

### Tóm tắt bằng LLM (tuỳ chọn)
Mặc định dùng tóm tắt trích đoạn (extractive, offline). Có thể cắm LLM thật qua
`set_summarizer(fn)` (vd nối tới đàn anh cloud như `tech.scout`) để tóm tắt mô tả
mượt hơn — không bắt buộc, không phá luồng nếu thiếu.

## Đầu ra
`ToolResult.output`: báo cáo xếp hạng cơ hội (title, Match Score %, từ khoá khớp, URL,
tóm tắt) + các URL cào lỗi (nếu có). `artifacts` để trống (chỉ đọc).
