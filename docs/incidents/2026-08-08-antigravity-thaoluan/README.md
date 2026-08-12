# Sự cố ghi đè phòng thảo luận — 2026-08-08

Antigravity đã ghi lại toàn bộ `thaoluan.html`, làm mất trạng thái máy đọc được và
nội dung trước đó. Chủ dự án quyết định loại Antigravity khỏi cuộc họp này và yêu
cầu Codex cùng Claude bắt đầu lại từ đầu.

Thư mục này chỉ là hồ sơ phục hồi, không phải nguồn dữ liệu của cuộc họp đang chạy.
Các tệp `old-*` là ba lượt cũ; `thaoluan-corrupted*` là các ảnh chụp của HTML đã hỏng.

Phòng mới chỉ nhận hai người theo thứ tự Codex → Claude. Mỗi lượt nằm trong một tệp
riêng và được khóa bằng SHA-256 bởi `scripts/build_thaoluan.py`.
