# AURA Chat v1 — trình chạy độc lập

Chat v1 không khởi động dashboard, daemon, robot, xưởng việc làm hoặc công cụ
điều khiển máy. Máy chủ chỉ bind vào loopback và chỉ có bốn đường:

- `/` — giao diện chat;
- `/api/status` — trạng thái tức thời;
- `/api/chat` — một lượt ChatRequest/ChatResult;
- `/api/chat/history` — lịch sử đúng actor + phiên hiện tại.

## Cấu hình

Đặt bí mật trong biến môi trường, **không truyền trên dòng lệnh**:

```powershell
$env:AURA_CHAT_BASE_URL = "https://provider.example/v1"
$env:AURA_CHAT_MODEL = "model-name"
$env:AURA_CHAT_API_KEY = "..."
.\venv\Scripts\python.exe .\aura_chat.py
```

Các cờ không bí mật: `--host` (chỉ loopback), `--port`, `--base-url`,
`--model`, `--timeout`, `--transcript-root`. Mặc định mở tại
`http://127.0.0.1:8799/`.

Chat v1 chưa có xác thực nên cố ý từ chối `0.0.0.0`, địa chỉ LAN và địa chỉ
công cộng. Không mở cổng này ra Internet.
