---
name: tech.scout
description: Trinh sát model/tool mới trên GitHub + HuggingFace qua API công khai, chấm điểm, lưu ChromaDB và đề xuất.
entrypoint: scripts/scout.py
function: tool_tech_scout
version: 1.0.0
tier: local
cost: free
permissions: [env, network]
---

# Tech Scout

"Đặc vụ trinh sát công nghệ": lang thang GitHub & Hugging Face **qua API công khai**
(không cào lén) để tìm model/tool mới. Mỗi ứng viên được chấm điểm (sao/lượt tải +
độ mới + khớp từ khoá), lưu vào ChromaDB làm bộ nhớ dài hạn, kèm hạn đánh giá lại.

## Khi nào DÙNG
- Người dùng muốn **tìm / khảo sát / cập nhật** công nghệ mới (model dịch, vision...).
- Muốn xem có "đàn anh" tiềm năng nào để cân nhắc đăng ký sau.

## Khi nào KHÔNG dùng
- Yêu cầu **kích hoạt / chạy** một model — đó là việc `register_senior` + Sếp duyệt.
  Scout chỉ TÌM + CHẤM + LƯU + ĐỀ XUẤT, không tự bật model thành đàn anh.

## Tham số
| Tên | Kiểu | Bắt buộc | Ý nghĩa |
|-----|------|----------|---------|
| `query` | str | ✅ | Từ khoá tìm, vd `"vietnamese translation model"`. |
| `keywords` | str | ✖ | Từ khoá chấm điểm, phân tách bằng dấu phẩy (mặc định = tách `query`). |
| `limit` | int | ✖ | Số kết quả mỗi nguồn (mặc định 5). |

Token `GITHUB_TOKEN` / `HF_TOKEN` (nếu có trong env) được dùng để nâng rate-limit —
KHÔNG hard-code.

## Hướng dẫn thực thi (Instructions)
**KHÔNG tự gọi API GitHub/HF hay tự chấm điểm.** Logic (gọi API, scoring heuristic,
lưu ChromaDB) đã nằm trong script. Chỉ GỌI:

- Đường chính: `registry.execute_tool("tech.scout", {"query": "...", "limit": 5})`.
- Kiểm thử độc lập (Level 4):

  ```bash
  python skills/tech-scout/scripts/scout.py --query "vietnamese OCR" --limit 5
  ```

## Đầu ra
`ToolResult.output`: tóm tắt số ứng viên tìm được, số đã lưu vào bộ nhớ dài hạn, và
Top N (kèm điểm, độ phổ biến, URL). Kết quả đã được lưu ChromaDB để lần sau khỏi đề
xuất trùng (`recall_known`).
