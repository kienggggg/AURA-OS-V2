---
name: trend.radar
description: Radar chủ đề đang lên — quét nguồn trend miễn phí (Google Trends, Hacker News), dùng công nhân embedding lọc chủ đề hợp GÓC RIÊNG của Sếp, rồi dựng brief (cloud viết hoặc khung mẫu) để Sếp quay video ăn theo nhanh nhưng có góc riêng. Không sinh video, không tự đăng.
entrypoint: radar.py
function: tool_trend_radar
version: 1.0.0
tier: local
cost: free
permissions: [file_write, network]
---

# Trend Radar — radar chủ đề đang lên

Công nhân thứ tư. Bắt trend KHÔNG thắng bằng cách copy trend, mà bằng cách thêm GÓC
RIÊNG của Sếp vào trend đó — thật nhanh. Radar lo phần "phát hiện sớm + gợi góc",
Sếp lo phần quay và mặt/giọng thật.

## Luồng
1. **Quét trend**: RSS miễn phí không cần key — Google Trends theo quốc gia (`geo`,
   kèm lượng tìm kiếm) + Hacker News frontpage (trend công nghệ). Thêm nguồn qua `TREND_SOURCES`.
2. **Lọc theo góc**: công nhân embedding (`core/embedder.py`) chấm mỗi chủ đề hợp
   `angle` của Sếp cỡ nào (mặc định: giáo dục/sư phạm/Python/AI/dựng video) → xếp hạng.
3. **Dựng brief** cho top chủ đề: nếu `use_cloud` → CloudEngine viết brief thật (1 lượt
   gọi cho cả top); không thì khung mẫu (góc gợi ý + cấu trúc 3 phần + hook) để Sếp tự điền.

## Tham số
| Tên | Kiểu | Ý nghĩa |
|-----|------|---------|
| `sources` | list[str]/str | Nguồn RSS trend (mặc định Google Trends + HN). |
| `angle` | str | Góc riêng của Sếp để chấm độ hợp (mặc định config). |
| `geo` | str | Mã quốc gia Google Trends (mặc định VN). |
| `top` | int | Số chủ đề đưa vào brief (mặc định 5, tối đa 10). |
| `use_cloud` | bool | Nhờ cloud viết brief (mặc định config `trend_use_cloud`=False). |
| `as_json` | bool | Trả JSON thay vì markdown. |

## Cấu hình (.env)
`TREND_SOURCES`, `TREND_ANGLE`, `TREND_GEO`, `TREND_TOP`, `TREND_USE_CLOUD`,
`TREND_EMBED_LOW`/`HIGH` (calib điểm hợp góc).

## Hướng dẫn thực thi
- Đường chính: `registry.execute_tool("trend.radar", {"use_cloud": true})`.
- Chạy độc lập: `python skills/trend-radar/radar.py --top 5` (thêm `--cloud` để cloud viết brief).

## Đầu ra
`ToolResult.output`: top chủ đề hợp góc (kèm % hợp, lượng tìm, link) + brief. Báo cáo
máy đọc ở `data/feedback/trend_radar_last.json` (hàng đợi một chiều cho UI/quản gia).
KHÔNG sinh/đăng video — chỉ đưa bản đồ + brief cho Sếp quyết.
