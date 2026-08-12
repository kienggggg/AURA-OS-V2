---
name: desktop.autopilot
description: Quan sát cửa sổ/màn hình cục bộ, đọc ngữ cảnh mã nguồn AURA và truy hồi bộ nhớ AI trên máy, rồi xếp hàng hoặc chạy các thao tác chuột/bàn phím ít rủi ro. Dùng khi Chủ yêu cầu AURA xem màn hình, đọc chính mình, nhớ ngữ cảnh cũ, bấm/điền/cuộn trên ứng dụng đã cho phép hoặc tự hoàn tất một quy trình giao diện cục bộ.
entrypoint: scripts/desktop_autopilot.py
function: desktop_autopilot
---

# Desktop Autopilot

Sử dụng `desktop_autopilot` như mắt–tay chính thức của AURA.

## Luồng bắt buộc

1. Gọi `action="status"` để kiểm tra công tắc Chủ, tạm dừng và kill switch.
2. Gọi `action="context"` với `query` liên quan để đọc:
   - cửa sổ hiện hành;
   - tài liệu/mã nguồn AURA trong workspace;
   - ký ức ChromaDB cục bộ liên quan.
3. Gọi `action="observe"`; chỉ đặt `include_ocr=true` khi thật sự cần đọc chữ trên màn hình.
4. Tạo một task ngắn bằng `action="queue"`, `title`, `scope` và `actions`.
5. Daemon tự chạy hàng đợi. Chỉ gọi `action="run_next"` khi cần chạy ngay.

## Action schema

- `{"kind":"observe","include_ocr":false}`
- `{"kind":"click_text","target":"Tên nút","label":"mục đích"}`
- `{"kind":"click","x":100,"y":200,"label":"nút cục bộ đã xác định"}`
- `{"kind":"type_text","text":"nội dung không nhạy cảm"}`
- `{"kind":"press","key":"tab"}`
- `{"kind":"hotkey","keys":["ctrl","l"]}`
- `{"kind":"scroll","amount":-500}`
- `{"kind":"wait","seconds":1}`

Dùng `expected_window_keywords` ở task hoặc từng action để khóa đúng ứng dụng.

## Phạm vi

- `local_ui`: dashboard AURA, Codex, editor và tác vụ cục bộ.
- `research`: điều hướng/đọc web, không gửi form.
- `drafting`: nhập bản nháp nhưng không đăng/gửi.
- `external_submit`: mặc định không được cấp. Không tự thêm scope này.

## Luật cứng

- Không OCR hoặc thao tác cửa sổ ngân hàng, mật khẩu, OTP, CAPTCHA, 2FA, thanh toán hay chuyển tiền.
- Không tự đăng, gửi, nộp, mua, xóa hoặc cài đặt khi chưa có scope `external_submit` do Chủ cấp riêng.
- Không ghi screenshot xuống đĩa. OCR chỉ chạy local và ảnh chỉ nằm trong RAM.
- Không log nội dung đã gõ; chặn chuỗi có dạng secret/OTP.
- Giữ PyAutoGUI fail-safe: đưa chuột vào một góc màn hình để dừng khẩn cấp.
- Nếu tiêu đề cửa sổ rỗng, không khớp allowlist hoặc đổi giữa task, dừng task.
