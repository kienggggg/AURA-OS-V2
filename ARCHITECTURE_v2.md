# AURA 2.0 — Autonomous Multi-Agent OS

**Codename:** Quintessa
**Owner:** Sếp
**Status:** Tái cấu trúc (rewrite from linear-script → daemon-based agent OS)

---

## 0. Quyết định kiến trúc đã chốt

| # | Quyết định | Lựa chọn | Lý do |
|---|-----------|----------|-------|
| a | Local LLM backend | **Ollama** (bỏ llama-cpp) | Khớp code hiện có, đổi model 1 dòng, không quản GGUF thủ công |
| b | Memory store | **ChromaDB** (bỏ mem0) | Một nguồn sự thật duy nhất, toàn bộ PLAN.md xoay quanh nó |
| c | Concurrency interface | **WebSocket** tách VTuber ↔ Daemon | Không để 3 event loop (asyncio/Qt/threading) đánh nhau |
| d | Tiến hóa (evolution) | **Sandbox → Phê duyệt người → Hot-reload** | Tự sinh tool nhưng không tự gây hại hệ thống |

---

## 1. Bản phân tích lỗi của hệ thống cũ

### 1.1. Lỗi kiến trúc nền (nghiêm trọng nhất)

- **Ba backend LLM cùng tồn tại.** `AURA_ARCHITECTURE.md` và `main_new.py` dùng Ollama (`BrainGateway`); `PLAN.md` lại đặc tả `llama-cpp-python` (GGUF). Hai con đường khác nhau hoàn toàn về API → orchestrator không có hợp đồng ổn định để gọi.
- **Hai hệ memory cùng tồn tại.** `memory_manager.py` dùng `mem0`; `PLAN.md` + `main_new.py` dùng ChromaDB (`quangia_memory`). Không có nguồn sự thật duy nhất → ký ức không bao giờ đồng bộ.
- **Khớp nối giả.** `main_new.py` import `BrainGateway, AURA_Orchestrator, AURA_Memory` nhưng định nghĩa thực tế không khớp đặc tả trong `PLAN.md`. Đây là gốc của cảm giác "đứt gãy".

### 1.2. Lỗi bóc tách chapter manga

- RL log trong `PLAN.md` đã tự ghi nhận: `int()` chết với số chương lẻ (10.5, 25.5). Giải pháp đúng là parse số thực, không phải số nguyên.
- Orchestrator bóc tham số bằng **regex trên text tự do** do model local sinh ra → cực kỳ giòn, sai một dấu là hỏng cả luồng.

### 1.3. Lỗi "dính khiên bản quyền"

- Nguyên nhân là **sai công cụ**, không phải sai code. `manga_translator.py` nhờ một chat model frontier (Gemini Vision) đọc nguyên trang truyện có bản quyền rồi tái tạo — loại tác vụ model frontier hay từ chối/chèn caveat.
- Hướng đúng: manga đi đường **OCR + máy dịch chuyên dụng chạy local** (`ComicTranslator`: easyocr + deep-translator). Model frontier chỉ dùng cho code & suy luận. Vừa hết "dính khiên", vừa ổn định, vừa không tốn token cloud.

### 1.4. Lỗi state máy & vòng đời

- Orchestrator chạy multi-pass ad-hoc (`PASS 1 → 2.7 → 2.8`) nhưng **không có state tường minh**. Luồng intent → plan → act → observe nằm rải rác trong if/else → không debug, không resume được.
- Toàn bộ hiện tại là **đồng bộ** (`input()`, `subprocess.run` chặn), nhưng tầm nhìn đòi asyncio daemon + Qt + threading sensors. Bài toán concurrency này chưa được giải.

### 1.5. Lỗi an toàn trong `agent_coder.py` (chặn trước khi mở rộng)

- **Command injection:** `f'npx gitnexus query "{search_term}"'` với `shell=True`. `search_term` chứa `"` hoặc `$(...)` là chạy lệnh tùy ý.
- **Self-modify không kiểm soát:** agent lấy đường dẫn từ comment `# FILE:` trong output LLM rồi ghi vào đường dẫn tùy ý (path traversal, ghi đè cả `core/`). `ast.parse()` chỉ kiểm cú pháp, **không** kiểm an toàn. Đây là quả mìn lớn nhất.

---

## 2. Sơ đồ kiến trúc thư mục AURA 2.0

```text
aura/
├── main.py                 # siêu mỏng: parse args → khởi động Daemon
├── config.py               # cấu hình tập trung, đọc .env (pydantic-settings)
├── .env                    # API keys — KHÔNG commit
│
├── core/
│   ├── daemon.py           # AuraDaemon: asyncio event loop, lifecycle, lịch sensors
│   ├── brain_router.py     # BrainRouter: phân luồng System1 (local) / System2 (cloud)
│   ├── orchestrator.py     # AgentLoop: state machine intent→plan→act→observe
│   ├── memory.py           # MemoryStore: ChromaDB — NGUỒN SỰ THẬT DUY NHẤT
│   ├── events.py           # bus nội bộ asyncio.Queue (thay regex tag surgery)
│   └── schemas.py          # pydantic: Intent, Task, AgentMessage, ToolResult
│
├── brains/
│   ├── base.py             # interface LLMBackend (1 hợp đồng: think/stream/chat)
│   ├── local_ollama.py     # Gemma/Phi-3 qua Ollama
│   └── cloud_claude.py     # Claude qua API (System 2)
│
├── agents/
│   ├── base.py             # BaseAgent: AgentMessage(JSON) → AgentMessage
│   ├── system_agent.py     # OS control (PyAutoGUI/subprocess) — có guardrail
│   ├── coder_agent.py      # sinh code → ĐẨY vào evolution sandbox, không tự ghi/chạy
│   └── web_agent.py        # crawl4ai / browser-use
│
├── tools/
│   ├── registry.py         # ToolRegistry: đăng ký + dispatch (function-calling)
│   ├── filesystem.py
│   └── manga/
│       ├── scraper.py      # MangaDownloader (xoay UA, proxy, retry)
│       ├── translator.py   # ComicTranslator — MỘT bản duy nhất
│       └── packager.py     # PDF/CBZ
│
├── evolution/
│   ├── validator.py        # AST allowlist + chặn import nguy hiểm + chặn path traversal
│   ├── sandbox.py          # chạy thử code mới trong subprocess cô lập, có timeout
│   ├── installer.py        # pip install có allowlist + cổng xác nhận
│   ├── approval.py         # human-in-the-loop trước khi nạp tool
│   └── loader.py           # hot-reload importlib CHỈ với tool đã duyệt
│
├── interface/
│   ├── avatar.py           # cầu nối Open-LLM-VTuber (WebSocket client)
│   ├── tts.py              # Supertonic ONNX wrapper
│   └── cli.py              # chế độ dòng lệnh để debug nhanh
│
├── data/
│   ├── chroma/             # ChromaDB persistent
│   ├── downloads/  outputs/
│   └── tools_generated/    # tool tự sinh (chỉ sau khi duyệt)
└── tests/
```

### Nguyên tắc xương sống

1. **Hướng phụ thuộc một chiều:** `interface → core → brains/tools`. Không bao giờ ngược lại.
2. **Giao tiếp bằng pydantic schema, không bằng regex tag.** Mọi agent nói chuyện qua `AgentMessage`. JSON sai cấu trúc → validate fail → loop tự sửa. Xoá toàn bộ `detect_/process_/remove_..._tags`.
3. **Memory một nguồn** (ChromaDB), **brain một backend mỗi cấp** (Ollama / Claude), **interface tách hẳn** qua WebSocket.

---

## 3. Hệ thần kinh đa lõi (Hybrid Neural Routing)

| Cấp | Engine | Tác vụ | Tiêu chuẩn |
|-----|--------|--------|-----------|
| System 1 (phản xạ) | Ollama — Gemma 4 E4B / Phi-3 | intent, chat thường, gọi tool local | nhanh, rẻ, offline |
| System 2 (suy luận sâu) | Claude qua API | code lớn, debug logic, phân tích nặng | chính xác, đắt hơn |

**Routing:** System 1 phân loại intent trước. Nếu intent là coding/heavy-reasoning → đẩy lên System 2. Nếu một tool local lỗi runtime 2 lần liên tiếp → tự fallback, chuyển toàn bộ ngữ cảnh + log lỗi lên System 2.

---

## 4. Cơ chế tiến hóa an toàn

> "Tự ghi code + auto pip install + hot-reload vào daemon đang chạy" và "production-ready" loại trừ nhau nếu thiếu sandbox. Ta giữ giấc mơ tự tiến hóa, nhưng làm nó **sống sót được**.

```text
Coder Agent sinh code
   → validator   (AST allowlist; chặn os.system/eval/exec/__import__; chặn path traversal)
   → sandbox     (subprocess cô lập, timeout, không network mặc định)
   → approval    (Sếp gật 1 cái — human-in-the-loop)
   → loader      (importlib hot-reload CHỈ tool đã duyệt)
```

AURA vẫn "mọc thêm tay", nhưng không tự chặt tay mình.

---

## 5. Thứ tự triển khai

1. `core/schemas.py` + `config.py` — nền tảng ✅ (phiên này)
2. `core/memory.py` — ChromaDB store
3. `core/brain_router.py` + `brains/*` — routing
4. `core/orchestrator.py` — state machine
5. Dọn `tools/manga/*` — gộp về một translator
6. `evolution/*` — sandbox + approval
7. `interface/avatar.py` — WebSocket VTuber + TTS

Mỗi file viết hoàn chỉnh, có test, không `pass` / `TODO`.
