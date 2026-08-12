# Ảnh cho AURA Mascot (ui/mascot.py)

Thả ảnh nhân vật vào đây để mascot mang gương mặt đó. Hỗ trợ **PNG tĩnh** hoặc **GIF động**.

| File                 | Khi nào hiện              |
|----------------------|---------------------------|
| `idle.png` / `idle.gif` | lúc rảnh (mặc định)     |
| `talk.png` / `talk.gif` | lúc AURA đang nhả chữ   |

- Ưu tiên `.gif` (động); nếu không có thì dùng `.png`/`.webp`/`.jpg`.
- Nền **trong suốt** (PNG/GIF alpha) để khít với cửa sổ tàng hình.
- Ảnh tự co về cạnh tối đa ~170px (giữ tỉ lệ), không cần resize trước.
- Thiếu cả hai file → mascot tự vẽ hình tạm (blob hồng = idle, xanh = talk) để vẫn kéo–thả được.

Mascot cũng tìm trong `assets/avatar/` nếu thư mục này trống.

## Chạy
```
python main.py        # bật não AURA (để hiệu ứng nói hoạt động)
python -m ui.mascot   # bật mascot nổi trên desktop
```
Kéo chuột để di chuyển. Chuột phải → "Thử hiệu ứng nói" hoặc "Thoát mascot".

> Hiệu ứng nói: khi `gemma4:e4b` bắt đầu generate, mascot đổi sang `talk`; xong → `idle`.
