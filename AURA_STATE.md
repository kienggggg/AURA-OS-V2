# AURA_STATE.md — Trạng thái bàn giao (Session Handoff)

> **Cách dùng:** Mở New Chat mới, dán nội dung `CONTEXT.md` (hiến pháp an toàn) +
> file này (`AURA_STATE.md`). Hai file này đủ để phiên mới hiểu AURA là gì, đã làm
> tới đâu, và phải làm gì tiếp — không cần đọc lại toàn bộ lịch sử.

- **Dự án:** AURA OS v2 — trợ lý AI cá nhân *local-first, CPU-only*. Ví laptop là
  "ngôi nhà thông minh" thì AURA là "trợ lý" điều khiển căn nhà đó, và tự hoàn thiện.
- **Đường dẫn:** `D:\AURA_OS_v2`
- **Máy (may-001):** Intel i5-1135G7, 12GB RAM, Intel Iris Xe (KHÔNG GPU rời).
- **Tiến độ:** ~70% tầm nhìn (xong *bộ khung + linh hồn*; còn *cơ bắp + da đẹp + trần phần cứng*).
- **Não local:** Ollama, model `gemma4:e4b` (~9.6GB → cần `OLLAMA_TIMEOUT_S` lớn, ~1000).
- **Não cloud (thầy):** Claude qua `ANTHROPIC_API_KEY` (tuỳ chọn; escalation khi bí).

---

## 1. Kiến trúc tổng thể (7 lớp)

```
Giác quan : web.scrape · web.agent(headed+stealth) · news.scout · job.scout · tech.scout
Tay chân  : system.control · manga.download/translate · knowledge.ingest
Trí nhớ   : ChromaDB (conversation·user_preferences·system_rules·KNOWLEDGE)
            + reflection(tag core_lesson) + metrics(data/metrics.json)
Tư duy    : core/deliberate.py (kế hoạch → tự phản biện) ; brain_router Local↔Cloud
Tự lớn    : reflection → self_improve → EvolutionEngine (tự viết tool, Sếp DUYỆT)
An toàn   : CONTEXT.md · Vibe Diff (vô hại làm ngay / rủi ro xin phép) · Sandbox · CodeGate
Hiện diện : main.py (server+daemon) + interface/avatar.py (AURA-chan) + autostart
```

---

## 2. Kỹ năng đã hoàn thành (10 skills — Progressive Disclosure)

Mỗi skill nằm trong `skills/<tên>/` gồm `SKILL.md` (Level 1 metadata) + `scripts/` (Level 4 code),
được `tools/registry.py` tự quét và nạp lười (lazy import). Hợp đồng: `fn(**params) -> ToolResult`.

| Skill | Việc | Ghi chú quan trọng |
|---|---|---|
| `web.scrape` | Cào HTML tĩnh (requests+bs4) | KHÔNG dùng để tải truyện (đã ghi trong SKILL.md) |
| `web.agent` | Trình duyệt thật render JS, vượt Cloudflare | Playwright **headed** (headless=False) + playwright-stealth; `wait_until=domcontentloaded` |
| `news.scout` | Đọc tin + AI phán đoán + auto-subscribe | nhịp tim 3×/ngày qua daemon |
| `job.scout` | Săn việc + chấm Match Score | Accept-Encoding **không br**; 403→fallback web.agent |
| `tech.scout` | Quét tin công nghệ / đàn anh cloud | đăng ký senior qua broker |
| `system.control` | Tay chân: xem/xoá(Thùng rác)/thông tin máy | đi qua cổng Vibe Diff |
| `manga.download` | Tải truyện (gọi web.scrape nội bộ) | bóc `source_url` |
| `manga.translate` | OCR + dịch (gọi manga.download) | cần easyocr + deep-translator |
| `knowledge.ingest` | Tự đọc URL/PDF/text → nhớ (RAG) | lưu collection `knowledge` |
| `security.stride` | Phân tích mối đe doạ STRIDE | Shift-Left security |

## 3. Module lõi đã hoàn thành (`core/`)

- `orchestrator.py` — máy trạng thái trung tâm: Iron Rule (hard-routing từ khoá),
  Vibe Diff gate + duyệt/huỷ xuyên lượt, recall core_lesson + knowledge, metrics, deliberation.
- `vibe_diff.py` — dịch ý định + cổng phê duyệt; `assess_harm()` (vô hại→làm ngay, rủi ro→xin phép); `DEFAULT_AUTO_APPROVE=frozenset()`.
- `reflection.py` — `analyze_daily_logs()` → bài học (tag `core_lesson`); `configure_file_logging()`.
- `self_improve.py` — phát hiện thiếu năng lực → đề xuất → (Sếp duyệt) → EvolutionEngine.evolve.
- `metrics.py` — record / scorecard / trend / render (persist `data/metrics.json`).
- `deliberate.py` — `deliberate()` kế hoạch→nháp→tự phản biện→viết lại (dừng sớm khi "OK").
- `llm.py` — `LocalCPUEngine` (Ollama REST) + `CloudEngine` (Claude) + `build_engines()`.
- `brain_router.py` — định tuyến Local↔Cloud; `_looks_weak()` → escalate lên Cloud khi câu trả lời local yếu.
- `daemon.py` — nhịp tim asyncio: tin tức 3×/ngày + trưởng thành 1×/ngày.
- `memory.py` — ChromaDB; thêm `CollectionName.KNOWLEDGE` + remember/recall_knowledge.
- Khác: `agent_broker.py`, `computer_use.py` (Mắt thần vision senior), `config.py`, `schemas.py`
  (`ToolResult`, IntentLabel + JOB_SCOUT/KNOWLEDGE_INGEST), `mcp_client.py`, `redact.py`, `self_diagnose.py`.

## 4. Hiện diện / khởi động

- `main.py` — đánh thức server WebSocket + daemon + orchestrator (đã bật file logging).
- `interface/server.py` — WebSocket server cho Avatar.
- `interface/avatar.py` — **AURA-chan**: chibi vẽ bằng QPainter, biểu cảm theo trạng thái
  (idle/listening/thinking/talking/alert/offline), tự chớp mắt + lơ lửng, khung chat **tự né viền**.
  **Nạp ảnh:** thả PNG vào `assets/avatar/` (`idle.png`…`talking.png` hoặc `aura.png`) → AURA mang mặt đó.
- `aura_boot.py` — "boot doctor": kiểm Python/thư viện/.env/Ollama/registry/import trước khi chạy.
- `aura_autostart.py` — đăng ký tự khởi động khi đăng nhập Windows (Task Scheduler; **tự rớt sang
  Startup folder nếu Access denied** — không cần Admin). `--install / --status / --uninstall`.
- `aura_run.pyw` — bật CẢ não (main.py) lẫn mặt (avatar), chạy nền ẩn (pythonw, không console).

---

## 5. Cấu trúc thư mục hiện hành

```
D:\AURA_OS_v2\
├─ CONTEXT.md              # Hiến pháp an toàn (DÁN VÀO CHAT MỚI)
├─ AURA_STATE.md          # File này (DÁN VÀO CHAT MỚI)
├─ AURA_README.md         # Bản đồ hệ thống đầy đủ
├─ ARCHITECTURE_v2.md     # Thiết kế gốc
├─ .env.example           # OLLAMA_MODEL=gemma4:e4b, OLLAMA_TIMEOUT_S=1000
├─ main.py                # đánh thức server+daemon
├─ aura_boot.py           # tiền-kiểm trước khi chạy
├─ aura_autostart.py      # tự khởi động cùng Windows
├─ aura_run.pyw           # bật não + mặt, nền ẩn
├─ core/                  # 17 module lõi (xem mục 3)
├─ skills/                # 10 skill (xem mục 2)
├─ interface/             # avatar.py (AURA-chan) + server.py
├─ assets/avatar/         # khe cắm ảnh nhân vật (README hướng dẫn)
├─ brains/                # backend LLM (cloud_claude…)
├─ evolution/             # CoderAgent + CodeGate + Sandbox (tự tiến hoá)
├─ tools/                 # registry.py (tự quét skills)
├─ agents/ · data/        # phụ trợ + ChromaDB/metrics/logs
└─ (venv/ .venv/ Eagle/   # KHÔNG đụng — môi trường & model phụ)
```

## 6. Cách đánh thức (trên máy Sếp)

```powershell
pip install -r requirements.txt   # lõi + UI + psutil (cảm biến nhường đường) + skill tuỳ chọn
# (gọn tay:) pip install requests beautifulsoup4 pydantic pydantic-settings chromadb websockets PyQt5 PyQt6 psutil
ollama pull gemma4:e4b
copy .env.example .env      # điền ANTHROPIC_API_KEY nếu muốn mượn thầy; OLLAMA_KEEP_ALIVE=0 để nhả RAM ngay
python aura_boot.py         # phải thấy "✅ SẴN SÀNG"
python aura_autostart.py --install   # để AURA thường trú (tuỳ chọn)
python aura_run.pyw         # hoặc: python main.py + python -m interface.avatar
```

> **psutil** = cảm biến "nhường đường": RAM hệ thống > 85% thì tác vụ ngầm (điểm báo,
> tự phản tỉnh) ngủ đông nhường máy cho Sếp. Thiếu psutil → AURA vẫn chạy, chỉ tắt cơ chế này.
> **PyQt5** cho Desktop Mascot mới (`python -m ui.mascot`); **PyQt6** cho AURA-chan cũ.

---

## 7. Nguyên tắc BẤT BIẾN (đừng phá khi code tiếp)

1. **ToolResult contract:** mọi tool `fn(**params) -> ToolResult`, **không bao giờ raise**
   (bọc try/except, trả `ToolResult.failure`).
2. **Vibe Diff:** việc vô hại → làm ngay; rủi ro (xoá/đổi tên/di chuyển/lạ) → **xin phép Sếp**.
   `DEFAULT_AUTO_APPROVE` phải rỗng.
3. **Progressive Disclosure:** thêm skill = thêm `skills/<tên>/SKILL.md` + `scripts/`; registry tự quét.
4. **CONTEXT.md là luật:** không hardcode secret, least privilege, không os.system/eval/subprocess
   trong code *tự sinh*, TDD trước khi hot-load.
5. **Import từ skill scripts:** chèn project root vào `sys.path` (parents[3]) để `from core...` chạy.

## 8. Bài học đã ghi (tránh lặp lỗi)

- `gemma4:e4b` LÀ model hợp lệ (đừng cảnh báo sai).
- web.agent: **headed** + stealth + `domcontentloaded` (đừng networkidle → treo).
- job.scout: Accept-Encoding **bỏ `br`** (tránh mojibake); 403/401/429/503 → fallback web.agent.
- Iron Rule: từ khoá phải cụ thể ("xoá file" chứ không phải mỗi "xoá") để khỏi bắt nhầm.
- **Cẩn thận lỗi cắt file khi Edit file lớn:** đã gặp truncation; nếu thấy file cụt giữa chừng,
  vá bằng shell heredoc (`cat >`/`>>`) rồi `py_compile` lại.

---

## 9. 30% CÒN LẠI (việc cho phiên sau)

### A. Test thực chiến (ưu tiên cao nhất)
- Chạy thật trên Windows nhiều ngày: bắt lỗi đời thực (Ollama timeout, ChromaDB, Playwright,
  WebSocket rớt, daemon nhịp tim, autostart thực sự bật khi đăng nhập).
- Gửi log `data/logs/aura.log` về để chẩn đoán; nghiệm thu từng skill end-to-end.
- Viết thêm test cho các skill chưa có (smoke_test_skills.py mở rộng).

### B. Computer-Use "tay chân" sâu hơn
- Mở rộng `core/computer_use.py`: điều khiển chuột/bàn phím/cửa sổ/mở app tinh vi hơn
  (hiện mới có "Mắt thần" vision + system.control mức cơ bản).
- BẮT BUỘC đi qua Vibe Diff cho mọi hành động ghi/đổi trạng thái máy.

### C. Gương mặt sống — Live2D (lớp da đẹp)
- Hiện ở mức **PNGTuber** (đổi ảnh tĩnh theo trạng thái). Nâng lên **Live2D động** cần:
  model `.moc3` + `.model3.json` + texture (do người vẽ/rig trong Cubism — AURA không tự vẽ được),
- Việc lập trình runtime AURA làm được; việc *vẽ tách lớp + rig* là của người/công cụ ngoài.

### D. Trần phần cứng (xa, ngoài máy này)
- Fine-tune trọng số (nâng trí thông minh gốc của gemma) chỉ khả thi trên **GPU rời, offline**,
  sau khi đã thu đủ dữ liệu hội thoại/bài học. Trên may-001 thì KHÔNG — chỉ tự lớn bằng
  RAG + scaffolding + tool + memory + mượn thầy cloud.

---

## 10. HỆ NĂNG LƯỢNG & SỨC KHOẺ (bổ sung)

**Quản lý năng lượng 2 cấp** (trigger qua chat, đều CHỜ Sếp gõ `Y` — Vibe Diff):
- *Cấp 1 — AURA Sleep* (`core/daemon.py`: `aura_frozen`, `freeze_aura/unfreeze_aura`):
  "aura ngủ đông" / "aura thức dậy" → đóng/mở băng news+growth+sensor (nhường CPU/RAM);
  WebSocket/chat luôn mở. Định tuyến ở `core/orchestrator._detect_control` (chặn trước Iron Rule).
- *Cấp 2 — PC Hibernate* (`skills/system-power/`, hàm `hibernate_laptop`): "laptop ngủ đông" /
  "sleep máy" → `rundll32 powrprof SetSuspendState`. (Lưu ý: `0,1,0` = Sleep, không phải hibernate-đĩa.)

**Health Guard — ép nghỉ kỷ luật** (ĐÃ NGHIỆM THU):
- `core/daemon._health_heartbeat`: đếm giờ ngồi; tới `health_work_limit_min` (mặc định 50') thì
  phát event `health_break`. Cấu hình ở `core/config` (`health_*`). Đóng băng Cấp 1 thì ngừng đếm.
- *Context-Aware* `_heavy_process_running`: HOÃN 30' (`health_busy_delay_min`) nếu đang chạy app bận —
  render (`_RENDER_PROCS`: CapCut/ffmpeg/Premiere/Blender...) hoặc họp/trình chiếu (`_MEETING_PROCS`:
  Zoom/Teams/PowerPoint/OBS/Webex/Slack...), hoặc **trình duyệt đang bật CAMERA** (dò `cmdline` chứa
  `VideoCaptureService`/`video_capture`).
  - ⛔ **QUYẾT ĐỊNH BẤT BIẾN:** KHÔNG bắt `AudioService` (Chromium chạy nó cho mọi âm thanh kể cả
    nghe nhạc) — bắt nó sẽ làm tính năng ép kỷ luật vô tác dụng. Họp chỉ-tiếng đã bắt qua app native.
- `ui/health_guard.py` (tiến trình PyQt5 RIÊNG, nghe `health_break`): bong bóng cảnh báo → auto-save
  `Ctrl+S` (pyautogui) → sau 10s phủ **KHIÊN ĐEN** toàn màn hình + đồng hồ đếm ngược 05:00→00:00,
  chặn click/phím cơ bản (`grabKeyboard`), về 0 tự `.close()`. Thử: `python -m ui.health_guard --demo 10`.
  Autostart đã spawn kèm trong `aura_run.pyw`.

**Kỹ năng mới:** `rpa.browser` (lướt web vật lý qua pyautogui, Kill Switch FAILSAFE),
`system.power` (PC Hibernate). Cả hai qua Vibe Diff. Phụ thuộc thêm: `psutil` (BẮT BUỘC), `pyautogui`.

---

*Đóng gói an toàn. Mọi file Python trong dự án đã compile sạch (không file dở dang).*

---

## 11. BÀN GIAO PHIÊN (Cowork → Claude Code) — cập nhật mới nhất

> Phiên Cowork này đã xây thêm rất nhiều. Code nằm hết trên đĩa; mục này + `CONTEXT.md`
> đủ để phiên Claude Code tiếp quản. Đọc kỹ phần "Lỗi/giới hạn thật" trước khi tin.

### A. Đã thêm trong phiên này (đều compile sạch; test HEADLESS bằng fake)
- **Năng lượng/RAM:** `OLLAMA_KEEP_ALIVE=0` (gửi kèm mỗi request, `core/llm.py`); cảm biến RAM
  `psutil` + `_await_ram_headroom` (nhường đường khi RAM>85%); **AURA Sleep** —
  `aura_frozen`/`freeze_aura`/`unfreeze_aura` (lệnh chat "aura ngủ đông"/"thức dậy", Vibe Diff Y).
- **Health Guard** (`core/daemon._health_heartbeat` + `ui/health_guard.py`): đếm giờ ngồi → ép
  nghỉ; KHIÊN ĐEN đếm ngược chặn input + tự mở; auto-save Ctrl+S; **né app bận** (CapCut/render,
  Zoom/Teams/PowerPoint/OBS..., và trình duyệt đang bật camera qua `VideoCaptureService`).
  ⛔ **BẤT BIẾN: KHÔNG bao giờ thêm `AudioService` vào danh sách bận** (nghe nhạc cũng hoãn → vô dụng).
- **PC Hibernate** (`skills/system-power/`) + lệnh chat "laptop ngủ đông" (Vibe Diff Y).
- **Hạ model:** mặc định `gemma4:e2b` (nhẹ). 
- **Mascot mới** (`ui/mascot.py`): placeholder phẳng + bong bóng thoại + khung gõ + gửi WS.
  *Lưu ý:* autostart ĐÃ quay về `interface.avatar` (Chat Window), KHÔNG dùng mascot.
- **Chống chen ngang** (`interface/server.py`): tin `proactive` bị HOÃN khi đang trả lời chat
  (`_deferred`), xả sau — không cắt ngang câu trả lời.
- **Skill mới:** `rpa.browser` (lướt web vật lý pyautogui, FAILSAFE), `system.power`,
  `skills/connectors/` (calendar `.ics` + email IMAP — CHỈ ĐỌC, BODY.PEEK), `skills/scouts/job_scout.py`
  (RSS/HTML + lọc AI e2b + heuristic fallback + tầng Jina Reader).
- **RỄ "Quản gia" (4 bước):** `core/profile.py` (Chân dung Sếp: JSON nguồn-sự-thật + đồng bộ
  `CollectionName.PROFILE` ChromaDB, id ổn định) → bơm `get_summary()` vào system prompt +
  cập nhật qua chat (Vibe Diff Y) → **briefing sáng/tối nhận biết giờ thực** (catch-up, state file,
  né ngủ đông) → **báo cáo Cloud→Local→Template** + redact + trần ngân sách + công tắc giọng
  `BRIEFING_PERSONA=alpha|gentle`. Briefing sáng còn nhồi lịch + email + cơ hội việc làm.
- **Triad Council** (`core/triad_council.py`): Generator/Validator(Sandbox)/Master + retry JSON;
  `generator_tier` (mặc định `local`); **học từ Sếp**: bác → ghi `system_rules` (ChromaDB, RAG recall)
  → nhồi lại Generator; **Human Gate qua chat** (`CouncilChatBridge` + `make_event_reviewer`, KHÔNG
  `input()`). Trigger chat: `hội đồng: <yêu cầu>`. Đã nối vào `orchestrator` + `main.py`.
- **Khác:** `core/redact.py` thêm mẫu SĐT + số tài khoản; `requirements.txt`; `don_rac.py`
  (dọn Downloads AN TOÀN: send2trash + dry-run); `.env.example` cập nhật đầy đủ.

### B. Lỗi / giới hạn THẬT (chưa xử lý — ưu tiên cho phiên sau)
1. ~~**e2b quá yếu làm Generator** → Hội đồng codegen FAIL (trượt JSON 3 vòng).~~
   ✅ **ĐÃ CẮM NÃO CLOUD FREE (phiên Claude Code):** thêm `brains/cloud_openai_compat.py`
   (`OpenAICompatBackend` — 1 backend cho Groq/Gemini/OpenRouter, bật JSON mode), config
   `cloud_provider`/`openai_*`/`council_generator_tier`, `CloudEngine` chọn backend theo provider,
   `main.py` đọc tier từ config. **Nghiệm thu LIVE:** Gemini `gemini-2.5-flash` qua OpenAI-compat,
   JSON mode trả `{task_id, code_payload}` sạch (test 14/14 PASS). Cấu hình ở `.env`
   (CLOUD_PROVIDER=openai, OPENAI_MODEL=gemini-2.5-flash, COUNCIL_GENERATOR_TIER=cloud).
   *(2.0-flash free hay 429 hết quota → dùng 2.5-flash.)*
   **VÁ TIẾP — nút thắt dịch sang PROMPT:** với Gemini, JSON sạch nhưng code_payload là hàm TRẦN
   (thiếu `tool_*`/`ToolResult`) → vẫn SANDBOX_FAIL. Đã viết lại `_GENERATOR_SYSTEM` (core/triad_council.py)
   ép đúng hợp đồng + khung mẫu (`from core.schemas import ToolResult`, `def tool_<tên>(**params) -> ToolResult`,
   `success/failure`, cấm os.system/eval...). **VÁ TIẾP 2 — model thinking ngốn token:** `gemini-2.5-flash`
   tiêu nhiều token reasoning → `max_tokens=1500` chật làm JSON code_payload bị CẮT CỤT → GEN_BADJSON.
   Nâng `_GEN_MAX_TOKENS=8192`. **Nghiệm thu LIVE:** Generator(Gemini)→CodeGate→Sandbox THẬT = PASS, 3/3 ổn định.
   **ĐÃ restart AURA** (1 instance thật trên 8765, log sạch, nạp prompt mới + `.env` cloud).
   **⚠️ CÒN BUG LIVE (chưa xong, ĐÃ GÁC LẠI):** trên GUI, `hội đồng: ...` vẫn KHÔNG ra bong bóng;
   task KHÔNG ghi NỔI MỘT DÒNG log `Council task=<id> vòng N` (im hẳn >19') → `master_deliberate`
   **treo ngay vòng 1 trên event loop server** (chạy `pythonw.exe`), DÙ cùng code offline (bằng
   `python.exe`) PASS 3/3. Đã loại: quota Gemini (HTTP 200, <2s), `approval_request` KHÔNG thuộc
   `_DEFERRABLE_TYPES` (không bị chống-chen-ngang nuốt), WS server còn phản hồi. Nghi điểm treo:
   bước `await asyncio.to_thread(_cloud_json)` / Sandbox subprocess dưới `pythonw`. **HƯỚNG DEBUG phiên sau:**
   gắn log vào/ra từng bước trong `master_deliberate` + `asyncio.wait_for` timeout mỗi vòng, rồi
   trigger lại để bắt đúng điểm. Codegen LOGIC đã ổn; chỉ vướng runtime async/pythonw.
   *Ghi chú vận hành:* venv pythonw (Py3.14) là stub-relaunch → cây tiến trình hiện CẶP stub+real;
   đếm instance THẬT = PID listening trên 8765 (luôn 1). Đừng "dọn bản trùng".
2. **Chưa chạy test thật:** mọi test ở phiên này là HEADLESS bằng fake (sandbox không có
   pydantic/chromadb/ollama/PyQt/server sống). Cần chạy lại trên máy thật.
3. ~~**UX Hội đồng:** gõ "y" lúc Council đang viết (chưa có gì duyệt) → lọt xuống chat thường.~~
   ✅ **ĐÃ VÁ (phiên Claude Code):** `CouncilChatBridge` thêm bộ đếm `_in_flight`
   (`mark_started`/`mark_done`/`is_in_flight`); `_start_council` đánh dấu started/done;
   `orchestrator.process_message` chặn 'Y' sớm → trả "Hội đồng đang viết code, chưa có gì
   để Sếp duyệt…". Test 9/9 PASS (`test_council_ux.py` ở root).
4. **Cloudflare** (TopCV, LinkedIn) chặn cả requests lẫn Jina → dùng RSS hoặc `web.agent` (Playwright).
5. **BẢO MẬT:** ~~App Password Gmail + token iCal THẬT từng nằm trong `.env.example`.~~
   ✅ **ĐÃ DỌN (phiên Claude Code):** token iCal + email chuyển sang `.env` (gitignored),
   `.env.example` chỉ còn placeholder; tạo `.gitignore` (`.env` + `.env.*` + `!.env.example`);
   config.py vốn default=None. **CÒN LẠI (việc Sếp):** regenerate token iCal bên Google Calendar
   (token cũ đã từng phơi) + xác nhận App Password Gmail cũ đã thu hồi (`GMAIL_APP_PASSWORD` đang trống).

### C. Việc tiếp theo (thứ tự ưu tiên cho Claude Code — môi trường chạy được THẬT)
1. `python aura_boot.py` → phải "✅ SẴN SÀNG"; rồi `python main.py` chạy thật, soi `data/logs/aura.log`.
2. ~~Cắm **cloud free (Gemini/Groq)** cho Generator + briefing.~~ ✅ XONG (Gemini, xem B.1).
3. Nghiệm thu LIVE vòng Council↔chat: `hội đồng: ...` → đợi bong bóng "🛡️ nghiệm thu" → `Y`/`không, lý do`
   → kiểm code lưu ở `data/tools_generated/` và luật vào `system_rules`.
4. ~~Vá UX mục B.3.~~ ✅ XONG (xem B.3).
5. Đổ **RSS thật** vào `FREELANCE_URLS`/`PEDAGOGY_URLS`; nghiệm thu job_scout buổi sáng.
6. Nghiệm thu từng tính năng: Health Guard (khiên đen), freeze/unfreeze, cập nhật Chân dung, briefing 3 tầng.

### D. BẤT BIẾN — đừng phá
- `ToolResult` không bao giờ raise; Vibe Diff (vô hại→làm, rủi ro→xin Y); CONTEXT §5 cấm
  `os.remove/eval/subprocess` trong code TỰ SINH (CodeGate gác); xoá → `send2trash`, không xoá cứng.
- ⛔ KHÔNG thêm AudioService vào Health Guard. Profile: JSON là nguồn sự thật. Redact trước khi lên Cloud.
- *Mẹo sửa file:* phiên Cowork hay bị "cắt cụt file" khi sửa file lớn — đã phải dùng shell heredoc.
  Claude Code sửa file thẳng trên đĩa nên không gặp lỗi này; nhưng nhớ `py_compile` sau mỗi sửa.

---

## 12. BÀN GIAO PHIÊN (Claude Code → Cowork) — 2026-07-02

> Phiên Claude Code (Opus 4.8) đã chạy môi trường THẬT. Tóm tắt để Cowork tiếp quản.
> Dùng `venv\Scripts\python.exe` (KHÔNG phải `.venv\` — rỗng). Console cần `PYTHONUTF8=1`.

### A. ĐÃ LÀM & NGHIỆM THU THẬT
- **Não cloud đa nguồn (litellm.Router, in-process — Py3.14 không chạy được proxy):**
  `brains/cloud_router.py`, `CLOUD_PROVIDER=router`, key ở `litellm/keys.env` (gitignored).
  **8 nhà / ~26 deployment**, 3 tầng: smart (GitHub GPT-4o + Mistral-large + OpenRouter code),
  fast=default (NVIDIA llama-70b + Cerebras gemma-4-31b + Mistral-small + Cohere), bulk (Gemini ×6).
  **Định tuyến thông minh** `_auto_tier`: prompt có tín hiệu code→smart; còn lại→fast. Council ép smart.
  Timeout 45s/deployment + wait_for mỗi bước Council (60s gen/30s sandbox) — chống treo vô hạn.
  ⚠️ **Groq 6-acc BỊ BAN** (multi-acc); Mistral/Cohere/Cerebras/Gemini cũng multi-acc → DÙNG NHẸ kẻo ban tiếp.
- **Council→GUI KHÉP KÍN:** đã nghiệm thu LIVE — `hội đồng: viết tool tải video` → GPT-4o/Mistral viết
  code THẬT (requests stream + kiểm RAM) → Sandbox PASS → bong bóng 🛡️ → Sếp gõ Y → lưu
  `data/tools_generated/council_task_52385_*.py`. Prompt Generator đã vá: cấm code mô phỏng, cho phép requests/urllib/open.
- **Mascot Miku** (`ui/mascot.py`, thay `interface/avatar.py` ĐÃ XOÁ): đi bộ animation (sprite MikuPet
  ở `assets/mascot/anim/`, đã xoá nền xanh), 7 loại animation (idle/walk/wave/happy/look/eat/color) tự phát,
  vỗ→vẫy, double-click→**cửa sổ chat TO**, chuột phải menu. Tối ưu: lật ảnh sẵn 2 chiều + dirty-check (~2% CPU).
  `aura_run.pyw` spawn `ui.mascot` (KHÔNG phải interface.avatar).
- **Đã sửa/dọn:** boot UTF-8 crash; assertion test cũ; UX Council gõ-Y-sớm; briefing max_tokens (thinking-model cụt);
  email digest→tier bulk; job_scout dùng Session chung; xoá `interface/avatar.py` chết + sửa launcher/boot/main;
  RSS THẬT vào `.env` (python.org + remoteok video-editor + tuyencongchuc.vn — itviec/vlance cũ đã 404).
- **Bảo mật:** dọn token iCal + Gmail App Password khỏi `.env.example`; tạo `.gitignore`.
- **Skill AURA tự viết:** `time.countdown` (đếm ngược ngày). Đang đóng gói `video.download` (xem C).

### B. LỖI/GIỚI HẠN CÒN LẠI
- **Quota free hữu hạn + multi-acc rủi ro ban.** Cân nhắc: 1 acc/nhà, thêm NHÀ khác (Z.ai/GLM, Cloudflare, NVIDIA models).
- **news_scout dùng gemma local** hay "trả về rỗng" → rớt heuristic (chưa nối pool cloud như briefing/council).
- **tuyencongchuc.vn** cho tin tuyển dụng cả nước, không lọc được theo tỉnh (VN gov ít RSS chuẩn).
- **Local gemma yếu** — mọi việc "thông minh" giờ đi pool cloud; local chỉ việc nhẹ/offline.

### C. VIỆC ĐANG DỞ (làm ngay khi vào)
1. ~~**Hoàn tất skill `video.download`**~~ ✅ XONG (phiên Cowork 02/07, xem mục E):
   compiled + test hợp đồng PASS; kèm vá routing Iron Rule. CÒN: restart AURA + chạy
   `test_video_routing.py` trên máy thật (sẽ thành 14 skills).
2. Việc Sếp: **regenerate token iCal** + xác nhận thu hồi App Password Gmail cũ
   (⚠️ `.env` hiện vẫn còn `GMAIL_APP_PASSWORD` — nếu là pass cũ đã lộ thì PHẢI thay).

### D. CÁCH RESTART AURA (đã đúc kết)
Tắt: mọi `pythonw.exe` cmdline khớp `AURA_OS_v2`. Chờ >8s. Bật: `Start-Process venv\Scripts\pythonw.exe aura_run.pyw`.
Đếm instance THẬT = PID listening trên 8765 (venv pythonw là stub-relaunch → mỗi tiến trình hiện CẶP stub+real).
Chỉ restart NÃO: kill+relaunch `main.py`; chỉ restart mặt: kill+relaunch `-m ui.mascot`.
⚠️ KHÔNG restart não khi Council đang chờ Sếp duyệt — trạng thái pending chỉ ở RAM, restart là mất (đã cắn 1 lần).

### E. BỔ SUNG (Cowork 02/07/2026 — sau test sống của Sếp)
Test sống lộ 3 điều: Council #52385 PASS ✅; lệnh `tải video "<tên>"` rơi vào local gemma
nói nhảm ("Tôi là mô hình ngôn ngữ,") vì skill tạo SAU khi boot + không có Iron Rule;
briefing alpha trượt sang xúc phạm cá nhân ("phế nhân", "biến đi"). Đã vá:
- **Routing:** `IntentLabel.VIDEO_DOWNLOAD` (schemas.py) + `_VIDEO_HINTS` ("tải video/clip/phim",
  đứng TRƯỚC manga check) + map `video.download` + bóc URL trong `_build_tool_arguments`
  (không URL → {} để hỏi lại — skill CHỈ tải link http(s) trực tiếp, không tự tìm link theo tên).
- **Persona:** Sếp chọn đổi `BRIEFING_PERSONA=gentle` (.env). Prompt alpha vẫn còn trong
  daemon.py nếu muốn quay lại — nhưng nên thêm lằn ranh cấm chửi nhân phẩm trước khi bật lại.
- **Nghiệm thu:** py_compile sạch (schemas/orchestrator/daemon/download.py); test hợp đồng
  skill PASS 3/3 (không raise). `test_video_routing.py` (root) chạy trên máy thật để chốt.
- **CÒN LẠI:** restart AURA (theo mục D) rồi chạy test; lưu ý news_scout local vẫn "trả về rỗng"
  → rớt heuristic (mục B, chưa vá).
