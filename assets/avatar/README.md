# Gương mặt của AURA — thả ảnh nhân vật vào đây

Mặc định AURA tự **vẽ** một bé chibi bằng code (đủ dùng, nhưng không đẹp bằng tranh).
Muốn AURA mang gương mặt đẹp như ý, chỉ cần **thả file ảnh** vào thư mục này.

## Cách nhanh nhất (1 ảnh)
Bỏ vào đây một file tên **`aura.png`** (PNG nền trong suốt, vuông, ví dụ 512×512).
Mở lại Avatar (`python -m interface.avatar`) là thấy.

## Có biểu cảm (nhiều ảnh) — khuyên dùng
Đặt các file theo đúng tên trạng thái, AURA sẽ tự đổi mặt theo lúc:

| File           | Khi nào hiện                         |
|----------------|--------------------------------------|
| `idle.png`     | rảnh (mặc định)                      |
| `listening.png`| vừa nhận lệnh / đang lắng nghe       |
| `thinking.png` | đang suy nghĩ / chờ trả lời          |
| `talking.png`  | đang trả lời                         |
| `alert.png`    | có lỗi / cảnh báo                    |
| `offline.png`  | mất kết nối tới não AURA             |

Thiếu file nào thì dùng `aura.png`; thiếu cả `aura.png` thì quay về chibi vẽ tay.

## Định dạng
- Hỗ trợ: `.png` (khuyên dùng, có nền trong suốt), `.webp`, `.jpg`.
- Nên vuông và nền trong suốt để khít với vầng sáng tròn phía sau.
- Ảnh tự co về kích thước avatar (giữ tỉ lệ), không cần resize trước.

## Lấy ảnh ở đâu
- Tranh/nhân vật **Sếp tự sở hữu** hoặc tự tạo (Stable Diffusion, đặt vẽ, v.v.).
- Nếu sau này muốn **Live2D động** (nhép miệng, chớp mắt theo rig như các app VTuber),
  đó là bước nâng cấp lớn hơn (cần Live2D Cubism runtime) — nói AURA khi sẵn sàng.

> Lưu ý bản quyền: tránh dùng nhân vật có bản quyền (vd Hatsune Miku) cho mục đích
> công khai. Dùng tranh của Sếp hoặc nhân vật gốc thì thoải mái.
