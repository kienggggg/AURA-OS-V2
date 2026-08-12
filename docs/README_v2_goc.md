# AURA OS v2 — Autonomous Multi-Agent System

> Quản gia AI cá nhân chạy local. Codename: **Quintessa**.
> Một model local (phản xạ) + Claude cloud (việc nặng), điều phối qua state
> machine, tự mọc tool trong sandbox, tự chẩn lỗi, tự trinh sát công nghệ.

---

## 1. Khởi động nhanh

```bat
start_aura.bat
```

File `.bat` này:
- Mở **cửa sổ chính** chạy `main.py` → Server (WebSocket) + Daemon (sensor ngầm), hiện log để debug.
- Mở **ẩn** Pet UI Avatar (`pythonw -m interface.avatar`) — không kẹt console.
- Đóng cửa sổ chính = tắt toàn bộ AURA.

Chạy thủ công (nếu cần tách riêng để debug):

```bash
# Cửa sổ 1 — bộ não + server + daemon:
python main.py
# Cửa sổ 2 — giao diện:
python -m interface.avatar
```

Thử "tự mở lời": kéo một file `.pdf` vào thư mục `Downloads` → sau ~5 giây Avatar tự nhắn gợi ý xử lý.

---

## 2. Chuẩn bị trước khi đóng điện

### 2.1. Cài đặt

```bash
python -m venv .venv
.venv\Scripts\activate
pip install pydantic pydantic-settings chromadb requests websockets PyQt6
# Tool manga (tùy chọn): pip install beautifulsoup4 easyocr deep-translator Pillow
```

Cài và chạy Ollama, kéo model local (xem khuyến nghị phần cứng ở mục 4):

```bash
ollama serve
ollama pull qwen2.5-coder:3b
```

### 2.2. Biến môi trường (`.env`)

Copy `.env.example` thành `.env` rồi điền. Toàn bộ key đọc tập trung qua `core/config.py` — không hard-code ở đâu khác.

| Biến | Bắt buộc? | Mặc định | Công dụng |
|------|-----------|----------|-----------|
| `OLLAMA_HOST` | không | `http://localhost:11434` | Địa chỉ Ollama local |
| `OLLAMA_MODEL` | không | `gemma2:latest` | Model System 1 (đổi sang `qwen2.5-coder:3b`) |
| `OLLAMA_TIMEOUT_S` | không | `120` | Timeout mỗi request local |
| `ANTHROPIC_API_KEY` | **có** (cho việc nặng) | — | Gọi Claude (System 2): coding, tiến hóa, tự chẩn lỗi |
| `CLOUD_MODEL` | không | `claude-sonnet-4-6` | Model cloud |
| `GOOGLE_API_KEY` | không | — | Dịch vụ phụ trợ (nếu dùng). **Dùng key MỚI sau khi thu hồi key cũ đã lộ** |
| `MANGA_PROXY` | không | — | Proxy cho scraper |
| `CHROMA_COLLECTION` | không | `quangia_memory` | Tên collection ký ức |
| `MEMORY_RECALL_K` | không | `5` | Số ký ức recall mỗi lần |
| `SENSOR_INTERVAL_S` | không | `5` | Chu kỳ quét Downloads (giây) |
| `WS_HOST` / `WS_PORT` | không | `localhost` / `8765` | Cổng WebSocket UI ↔ AURA |
| `LOG_LEVEL` | không | `INFO` | `DEBUG`/`INFO`/`WARNING`/`ERROR` |
| `GITHUB_TOKEN` | không | — | Nâng rate-limit cho `tech_scout` (GitHub) |
| `HF_TOKEN` | không | — | Nâng rate-limit cho `tech_scout` (HuggingFace) |

**An toàn:** không commit `.env`. Key luôn bọc `SecretStr`, in `settings` ra log không lộ. Mọi payload lên cloud đi qua `core/redact.py` (che key/token/tên user).

---

## 3. Bản đồ hệ thống

Sơ đồ kiến trúc đầy đủ ở `docs/agents.mmd` (mở bằng trình xem Mermaid hoặc dán vào mermaid.live).

Luồng theo mô hình **Nhà máy AI**:

```
Sếp → Avatar (WebSocket) → Server → Orchestrator (state machine)
                                          │
        ┌─────────────────────────────────┼───────────────────────────┐
   INTENT/PLAN                          ACT                          OBSERVE
        │                          (dispatch tool)              (tool lỗi → SelfDiagnose)
        ▼                                 ▼                              ▼
   AgentBroker ──→ Ollama (nhẹ)      ToolRegistry              hỏi Claude (đã redact)
        └───────→ Claude (nặng)      ├─ manga                  → đề xuất sửa ra UI
        (Lớp1: budget+duyệt phí       ├─ tech_scout → ChromaDB
         Lớp2: redact)               └─ EvolutionEngine (sinh→validate→sandbox→duyệt→hot-load)
```

Các collection ChromaDB: `conversation` (lịch sử chat), `user_preferences` (gu của Sếp), `system_rules` (bài học lỗi + ứng viên tech_scout).

---

## 4. Khuyến nghị phần cứng (may-001: i5-1135G7, 12GB, CPU-only)

- Model local nên là 3–4B Q4: `qwen2.5-coder:3b`, `phi4-mini`, hoặc `gemma3:4b`.
- **Hạ context window** (n_ctx ~2048) cho nhanh; đóng browser khi chạy.
- **Tắt "thinking mode"** nếu model có (trên CPU dễ nghĩ mãi không xuất kết quả).
- Việc nặng (coding, tiến hóa, chẩn lỗi) **đẩy lên Claude** — đừng bắt model local viết tool.

---

## 5. Xử lý sự cố

### Ollama không kết nối (`BrainOfflineError`, "Không kết nối được Ollama")
- Kiểm tra đã chạy `ollama serve` ở cửa sổ khác chưa.
- Thử `curl http://localhost:11434/api/tags` — phải trả về danh sách model.
- Đúng tên model trong `.env` (`ollama list` để xem tên thật).
- Nếu local gục, AURA tự **fallback sang Claude** (cần `ANTHROPIC_API_KEY`).

### ChromaDB lỗi khi khởi tạo
- Lần đầu chạy sẽ tải model embedding (~80MB) — cần mạng một lần.
- Lỗi "lệch chiều vector": do đổi `embedding_backend` giữa chừng. Chốt `default`, hoặc gọi `reset_collection()`.
- Kiểm quyền ghi thư mục `data/chroma/`.

### PyQt6 / Avatar không hiện
- `pip install PyQt6`.
- Avatar là **client** — phải bật `main.py` (server) trước. Nếu chưa, UI hiện "offline" và tự thử lại mỗi 2 giây.
- Sai cổng: `WS_HOST`/`WS_PORT` trong `.env` phải khớp giữa server và UI.

### websockets lỗi
- `pip install websockets`. UI và server phải cùng host/port.

### Claude (System 2) không phản hồi
- Thiếu/sai `ANTHROPIC_API_KEY` → các việc coding/tiến hóa/tự-chẩn sẽ báo lỗi rõ.
- Hết quota/429 → AURA báo lỗi gọn, không crash luồng chính.

### Tool tự sinh bị chặn khi nạp
- Đây là **đúng thiết kế**: validator chặn code có mẫu nguy hiểm, hoặc sandbox báo lỗi/timeout, hoặc Sếp chưa duyệt. Đọc báo cáo ở bước phê duyệt rồi quyết.

---

## 6. Ranh giới an toàn (Luật sắt)

AURA **tự do trong sandbox** (đọc, nghĩ, đề xuất, tìm kiếm). Mọi hành động **chạm ra ngoài** đều qua cổng Sếp:
- Sửa hệ thống / nạp tool mới → Approval Gate (Evolution).
- Tiêu tiền (gọi đàn anh trả phí) → duyệt ngân sách; mặc định **chặn**.
- Gửi dữ liệu lên cloud → **redact** trước.
- Không lách CAPTCHA, không giả người mở trình duyệt — mọi kết nối qua **API chính thức**.
- Đăng nội dung → qua API chính thức + Sếp duyệt; nội dung phải hợp pháp (không vi phạm bản quyền).

---

## 7. Cấu trúc thư mục

```
aura/
├── main.py                 start_aura.bat       .env(.example)
├── core/    config schemas redact memory brain_router agent_broker
│            orchestrator self_diagnose daemon
├── brains/  base local_ollama cloud_claude
├── tools/   registry tech_scout  manga/(scraper translator)
├── evolution/ validator sandbox installer loader engine
├── agents/  coder_agent
├── interface/ server avatar
├── docs/    agents.mmd
└── data/    chroma/ downloads/ outputs/ tools_generated/
```

Chi tiết kiến trúc & bản phân tích lỗi hệ cũ: xem `ARCHITECTURE_v2.md`.