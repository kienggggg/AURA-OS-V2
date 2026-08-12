# AURA MB Bridge

Ứng dụng Android này là cầu nối cục bộ giữa thông báo báo có của MB Bank và AURA.

Nó chỉ làm bốn việc:

1. Lắng nghe thông báo từ ứng dụng MB Bank sau khi chủ máy cho phép.
2. Chỉ nhận diện thông báo báo có và lấy số tiền VND.
3. Gửi số tiền, thời điểm và mã đối chiếu một chiều sang AURA qua kết nối USB cục bộ.
4. AURA gửi thông báo Telegram; tiền vẫn ở trạng thái chờ chủ xác nhận.

Ứng dụng không thu thập mật khẩu, OTP, số tài khoản hoặc nội dung thô của thông báo. Nó không kết nối trực tiếp vào tài khoản ngân hàng và không thể chuyển tiền.

Kết nối cục bộ cần được thiết lập một lần từ máy tính qua ADB. Sau khi cài, người dùng chỉ cần bật quyền **Truy cập thông báo** cho AURA MB Bridge trên Android.

Mặc định an toàn dùng cáp USB. AURA cũng có thể chuyển endpoint của app sang một cổng Wi-Fi nội bộ riêng có token ghép cặp: điện thoại và máy AURA phải cùng Wi-Fi, dashboard AURA vẫn không mở ra mạng. Máy AURA phải đang chạy để nhận báo có và gửi Telegram.
