---
name: security.stride
description: Phân tích ý tưởng tính năng MỚI theo mô hình STRIDE (6 nhóm mối đe doạ) để tìm rủi ro bảo mật TRƯỚC khi viết code (Shift-Left). Dùng khi lên kế hoạch/đề xuất tính năng, KHÔNG dùng để cào web hay tải truyện.
entrypoint: scripts/analyzer.py
function: tool_stride_analyze
version: 1.0.0
tier: local
cost: free
permissions: [shell]
---

# Security STRIDE

Mô hình hoá mối đe doạ (threat modeling) theo **STRIDE** cho một ý tưởng tính năng,
TRƯỚC khi viết một dòng code. Đây là bước Shift-Left: phơi bày rủi ro sớm để thiết kế
phòng thủ ngay từ đầu, thay vì vá lỗi về sau.

STRIDE = **S**poofing · **T**ampering · **R**epudiation · **I**nformation Disclosure ·
**D**enial of Service · **E**levation of Privilege.

## Khi nào DÙNG
- Sắp thêm/đổi một tính năng, tool, endpoint, hoặc luồng xử lý dữ liệu mới.
- Cần một checklist rủi ro + biện pháp giảm thiểu để đưa vào thiết kế/PR.
- Review nhanh an ninh cho một ý tưởng trước khi giao CoderAgent sinh code.

## Khi nào KHÔNG dùng
- KHÔNG phải tool tải truyện (`manga.download`) hay cào web (`web.scrape`).
- Không thay thế pentest/đánh giá an ninh chuyên sâu — đây là bước sàng lọc sớm.

## Tham số
| Tên | Kiểu | Bắt buộc | Ý nghĩa |
|-----|------|----------|---------|
| `feature` | str | ✅ | Mô tả ý tưởng tính năng cần soi (càng rõ càng tốt). |
| `context` | str | ✖ | Bối cảnh thêm (ai dùng, dữ liệu gì, chạy ở đâu). |
| `as_json` | bool | ✖ | Trả JSON có cấu trúc thay vì báo cáo markdown (mặc định false). |

## Hướng dẫn thực thi (Instructions)
**KHÔNG tự bịa phân tích an ninh trong đầu.** Gọi script — nó áp bộ luật STRIDE nhất
quán (câu hỏi nền + rủi ro kích theo từ khoá + biện pháp giảm thiểu):

- Đường chính: `registry.execute_tool("security.stride", {"feature": "..."})`.
- Chạy độc lập (Level 4):

  ```bash
  python skills/security-stride/scripts/analyzer.py --feature "Cho phép user upload avatar"
  ```

## Đầu ra
`ToolResult.output`: báo cáo theo 6 nhóm STRIDE — mỗi nhóm gồm rủi ro phát hiện
(theo từ khoá) + biện pháp giảm thiểu + câu hỏi nền bắt buộc trả lời. Kèm tổng số
rủi ro và mức ưu tiên. Tham chiếu `CONTEXT.md` mục 9.
