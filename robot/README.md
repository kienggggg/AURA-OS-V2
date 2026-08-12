# AURA Rover — sơ đồ lắp đúng bộ linh kiện thực tế

Phiên bản này dùng:

- ESP32-WROOM-32 DevKit 30 chân, cổng USB-C;
- TB6612FNG điều khiển hai động cơ TT;
- US-100 có jumper đen, chạy UART 9600;
- khay 4 pin AA chỉ cấp nguồn cho động cơ;
- Vivo chạy ứng dụng AURA Avatar và nối ESP32 bằng Bluetooth BLE.

## 1. Luật nguồn bắt buộc

1. Tháo toàn bộ pin AA và rút USB trong lúc đấu dây.
2. ESP32 được cấp nguồn bằng cổng USB-C từ laptop hoặc pin dự phòng 5 V.
3. Khay 4 pin AA chỉ nối vào `VM` của TB6612FNG.
4. Không nối dây đỏ của khay pin vào `3V3`, `VCC` hay bất kỳ GPIO nào.
5. Ba khối phải chung mass: `GND ESP32` ↔ `GND TB6612` ↔ dây đen khay pin.
6. Lần chạy đầu phải kê xe để hai bánh chủ động không chạm mặt bàn.

## 2. ESP32 ↔ TB6612FNG

Luôn nhìn **tên in trên bo**, không gọi trái/phải vì chỉ cần xoay bo là đảo vị
trí. Thứ tự hai cột mà Sếp đã đọc được dùng để nhận diện, còn việc nối là từng
cặp tên tuyệt đối dưới đây (`ANI1` nhìn trên bo chính là `AIN1`).

| TB6612FNG | ESP32 |
|---|---|
| `VCC` | `3V3` — nguồn logic |
| `GND` (bất kỳ) | `GND` |
| `STBY` | `D13` / GPIO13 |
| `PWMA` | `D27` / GPIO27 |
| `AIN1` | `D25` / GPIO25 |
| `AIN2` | `D26` / GPIO26 |
| `PWMB` | `D14` / GPIO14 |
| `BIN1` | `D32` / GPIO32 |
| `BIN2` | `D33` / GPIO33 |
| `AO1`, `AO2` | hai dây động cơ bên trái |
| `BO1`, `BO2` | hai dây động cơ bên phải |
| `VM` | dây đỏ khay 4 pin AA, qua công tắc nếu đã đấu công tắc — nguồn động cơ |
| `GND` | dây đen khay 4 pin AA |

Không nối tắt `STBY` lên nguồn; firmware dùng chân D13 để ngắt cứng driver khi dừng.

## 3. ESP32 ↔ US-100

Giữ nguyên jumper đen phía sau cảm biến như ảnh.

| US-100, đọc từ chữ in trên mặt trước | ESP32 |
|---|---|
| `UCC/VCC` (chân đầu; một số bo in giống `UCC`) | `VIN/5V` của ESP32 khi ESP32 được cấp bằng USB |
| `Trig/TX` | `D17` / GPIO17 (TX2) |
| `Echo/RX` | `D16` / GPIO16 (RX2) |
| một trong hai `GND` | `GND` |

US-100 nhận được nguồn 3–5 V. Dùng `VIN/5V` ở đây để dành chân `3V3`
riêng cho logic TB6612, không phải chập hai jumper vào một chân. US-100 còn là
ngoại lệ: ở UART mode, tài liệu nhà sản xuất yêu cầu TX nối TX và RX nối RX,
không đấu chéo như UART thông thường.

## 3A. Kiểm tra jumper trước khi cấp điện

- Ba bo đều có chân đực nên dây tín hiệu bo-với-bo phải là jumper cái-cái 2,54 mm.
- Khi cắm hết chiều dài, kéo rất nhẹ từng đầu: đầu dây không được tuột hoặc mất
  tiếp xúc chỉ vì lay nhẹ.
- Nếu một đầu lỏng, đổi sang một sợi khác trong bó. Không dùng keo để chữa tiếp
  xúc điện kém.
- Chỉ sau khi mạch đã chạy đúng mới dùng keo nóng hoặc dây rút giữ **phần vỏ
  nhựa/dây**, không phủ keo lên nút BOOT/EN hay chân kim loại hở.
- Với dây động cơ và dây pin, mối nối phải được hàn/đầu cos rồi cách điện; không
  xoắn hờ vào đầu jumper trên xe chạy.

## 4. Thứ tự lắp để không cháy mạch

1. Bắt US-100 ở đầu xe, hai mắt hướng thẳng về phía trước.
2. Đặt TB6612 và ESP32 ở tầng trên; tránh để chân kim loại chạm khung/ốc.
3. Đấu dây tín hiệu theo hai bảng trên khi chưa có nguồn.
4. Chụp rõ toàn bộ mặt chữ của TB6612 và ESP32 để kiểm tra chéo.
5. Chỉ cắm USB-C cho ESP32; chưa lắp pin AA. Nạp firmware và kiểm tra BLE + khoảng cách.
6. Kê hai bánh lên khỏi mặt bàn, lắp 4 pin AA đúng chiều, rồi bật nguồn động cơ.
7. Trong AURA Avatar, chạm **Bluetooth: kết nối ESP32**, sau đó thử từng nút chưa đến nửa giây.
8. Nếu chỉ một bánh quay ngược, rút nguồn rồi đảo hai dây của đúng động cơ đó.
9. Đặt vật phẳng trước cảm biến khoảng 10–15 cm: lệnh tiến và tự tuần tra phải dừng.
10. Chỉ đặt xe xuống sàn sau khi nút **DỪNG**, thả-tay-dừng, mất Bluetooth-dừng và chặn-vật-cản-dừng đều đã đạt.

## 5. Cơ chế an toàn đã nằm trong firmware

- khởi động luôn ở trạng thái dừng và kéo `STBY` xuống thấp;
- giữ nút trên Vivo mới tiếp tục nhận heartbeat để chạy;
- quá 1,1 giây không có heartbeat thì dừng;
- mất BLE thì dừng;
- mất dữ liệu US-100 thì không cho tiến/tự chạy;
- vật cản ở 150 mm hoặc gần hơn thì dừng cục bộ;
- tự tuần tra chỉ chạy khi Vivo vẫn kết nối và gửi heartbeat.

Firmware: `robot/esp32_aura_rover/esp32_aura_rover.ino`.

## 6. Bộ build/nạp đã chuẩn bị

Arduino CLI nằm riêng tại `C:\tmp\aura_robot_toolchain`; core được khóa ở
`esp32:esp32@1.0.6`, vừa đủ và ổn định cho ESP32-WROOM-32 cổ điển. Không cần mở
Arduino IDE. FQBN của bo là `esp32:esp32:esp32`.

Quy trình của AURA khi bảo trì là: compile trước, tìm đúng một cổng COM có chip
CH340C, dừng motor, upload, rồi đọc Serial 115200 để tìm `AURA_ROVER:READY`.
Không upload nếu có nhiều bo không phân biệt được hoặc nếu bánh đang chạm sàn.

## 7. Nguồn khi tháo laptop

Dùng pin dự phòng 5 V cắm thẳng vào USB-C của ESP32. Khay 4 pin AA vẫn chỉ nuôi động cơ qua `VM`. Vivo dùng pin của chính nó. Không lấy nguồn 4 pin AA cắm thẳng vào cổng hoặc chân nguồn của ESP32.
