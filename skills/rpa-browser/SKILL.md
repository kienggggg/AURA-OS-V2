---
name: rpa.browser
description: Lướt web TRỰC QUAN bằng cách điều khiển CHUỘT/BÀN PHÍM thật (pyautogui) — mở trình duyệt qua Win+S, focus thanh địa chỉ (Ctrl+L), gõ từ khoá tìm kiếm rồi cuộn trang. Dùng khi Sếp nói "lướt web tìm kiếm…", "mở trình duyệt tìm…", cần thao tác tay-chân thật trên màn hình thay vì cào HTML. RỦI RO CAO (chiếm chuột/bàn phím) — qua VIBE DIFF; Kill Switch: kéo mạnh chuột vào 1 góc màn hình để dừng khẩn cấp.
entrypoint: scripts/rpa_browser.py
function: search_web_physical
version: 1.0.0
tier: local
cost: free
---

# RPA Browser — "Lướt web bằng tay thật"

Biến AURA thành người dùng vật lý: thay vì gọi HTTP (web.scrape) hay trình duyệt ngầm
(web.agent), skill này **trực tiếp giành lấy chuột + bàn phím của Sếp** để mở trình
duyệt và tìm kiếm — đúng nghĩa "lướt web trực quan trên màn hình".

## Khi nào dùng
- Sếp nói: *"Hãy lướt web tìm kiếm <X>"*, *"mở trình duyệt tìm <X>"*, *"tự lên mạng tra <X>"*.
- Cần con người NHÌN THẤY thao tác xảy ra trên màn hình (demo, hiện diện), không phải lấy data ngầm.
- KHÔNG dùng khi chỉ cần nội dung trang (dùng `web.scrape` / `web.agent` rẻ và êm hơn).

## Tham số
- `query` (bắt buộc): từ khoá tìm kiếm. Rỗng -> trả lỗi (CONTEXT §7).
- `browser` (tuỳ chọn, mặc định `chrome`): tên trình duyệt để Win+S mở (vd `chrome`, `edge`).
- `scrolls` (tuỳ chọn, mặc định 3): số nhịp cuộn xuống sau khi trang load.

## An toàn (BẮT BUỘC đọc)
- **Kill Switch:** `pyautogui.FAILSAFE = True` bật ở đầu script. **Kéo mạnh chuột vào 1
  trong 4 góc màn hình để DỪNG KHẨN CẤP** (pyautogui ném FailSafeException -> skill nuốt
  gọn, trả ToolResult.failure, KHÔNG làm sập AURA).
- **Human-in-the-loop:** skill chiếm thiết bị nhập của Sếp = tác dụng phụ rủi ro cao ->
  Orchestrator PHẢI đưa qua **VIBE DIFF** xin duyệt trước khi chạy (CONTEXT §8).
- Trong lúc skill chạy, Sếp nên rời tay khỏi chuột/bàn phím để khỏi tranh chấp con trỏ.
- Skill TIN CẬY (hand-written), được phép chạm thiết bị — khác code TỰ SINH (bị CONTEXT §5 cấm).

## Phụ thuộc
`pip install pyautogui`  (Windows nên có thêm `pip install pillow` cho ảnh chụp; chỉ chạy
khi có phiên đăng nhập đồ hoạ — không chạy được headless).
