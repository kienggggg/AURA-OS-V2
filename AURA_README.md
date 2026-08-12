# AURA OS v2 — Bản đồ hệ thống

> Trợ lý AI cá nhân, chạy **local trên CPU** (Ollama/gemma4), điều khiển "căn nhà" (laptop)
> và **tự hoàn thiện** mỗi ngày. Tài liệu này là bản đồ để cầm lái — đọc 5 phút là nắm toàn cục.

---

## 1. AURA là gì (một câu)

Một **agent có kỷ luật**: nghe lệnh Sếp → phân loại ý định → chọn kỹ năng → **xin duyệt nếu rủi ro** →
chạy → **ghi điểm & rút kinh nghiệm** → mai giỏi hơn hôm nay.

## 2. Vòng đời một câu lệnh

```
Sếp nói
  → Orchestrator: INTENT (Iron-Rule ép nhãn, nếu không thì LLM phân loại)
  → PLAN (chọn tool + bóc tham số)
  → recall core_lesson liên quan (tự điều chỉnh trước khi làm)
  → VIBE DIFF: vô hại → chạy ngay (ưu tiên lệnh Sếp) | rủi ro → hỏi "Sếp duyệt?"
  → ACT (dispatch skill) → OBSERVE → ghi METRICS (thành/bại + thời gian)
  → RESPOND
```

## 3. Chín kỹ năng (skills/) — Progressive Disclosure

Registry tự quét `skills/`, chỉ nạp `name + description` vào prompt (Level 1), code nạp TRỄ khi gọi (Level 4).

| Skill | Việc | Ghi chú |
|---|---|---|
| `web.scrape` | Cào text/ảnh trang tĩnh | requests + BeautifulSoup, headers giả trình duyệt |
| `web.agent` | Trình duyệt thật headed + stealth | vượt JS/Cloudflare; cần playwright + playwright-stealth |
| `manga.download` | Tải chapter truyện | lazy-load, đặt tên trang |
| `manga.translate` | Dịch chapter sang Việt | easyocr + deep-translator; tự gọi manga.download nếu thiếu |
| `tech.scout` | Trinh sát model/tool mới | GitHub/HF API, chấm điểm, lưu ChromaDB |
| `security.stride` | Threat-model STRIDE | soi rủi ro TRƯỚC khi code |
| `job.scout` | Săn việc + Match Score | từ khoá Sếp; tự fallback web.agent khi 403 |
| `news.scout` | "Nhịp tim" đọc tin | RSS → LLM chấm điểm → auto-whitelist nguồn tốt |
| `system.control` | **Tay chân điều khiển laptop** | mở app/file, dọn file (xoá→Thùng rác), sysinfo; path-safety |

Thêm kỹ năng = thêm thư mục `skills/<tên>/` (SKILL.md + scripts/) → registry tự nhận.

## 4. Lõi (core/) — bộ khung & kỷ luật

| Module | Vai trò |
|---|---|
| `orchestrator.py` | State machine INTENT→PLAN→ACT→OBSERVE; iron-rule hard-routing; recall core_lesson; ghi metrics |
| `vibe_diff.py` | Human-in-the-loop: dịch ý định ra tiếng Việt + **assess_harm** (vô hại→chạy, rủi ro→hỏi) |
| `registry.py` (tools/) | Quét skills, lazy-load, `call_skill()` cho gọi chéo skill |
| `llm.py` | `LocalCPUEngine` (Ollama/gemma4, CPU) + `CloudEngine` (Claude) |
| `memory.py` | ChromaDB: conversation / user_preferences / system_rules |
| `reflection.py` | `analyze_daily_logs()` → đúc bài học (`core_lesson`) từ log 24h |
| `self_improve.py` | Cầu Reflection→Evolution: thấy thiếu kỹ năng → đề xuất (Sếp duyệt) → EvolutionEngine viết |
| `metrics.py` | Thước đo tự đánh giá: success/fail/thời gian, scorecard + trend "khá lên/tệ đi" |
| `daemon.py` | Nhịp tim ngầm: sensor Downloads · news 3×/ngày · **growth 1×/ngày** |
| `agent_broker.py` | Định tuyến Local/Cloud + BudgetGuard + redact secret |
| `config.py` | Cấu hình tập trung (đọc `.env`) |

`evolution/` (engine, gate, sandbox, validator, loader): tự sinh tool an toàn — CodeGate (AST) → Sandbox ephemeral → vòng tự sửa → Sếp đọc code → hot-load.

## 5. Ba lá chắn an toàn (luôn bật)

1. **CONTEXT.md** — Hiến pháp, nhồi vào mọi lần CoderAgent sinh code.
2. **VIBE DIFF** — không tự ý làm việc rủi ro; vô hại thì ưu tiên lệnh Sếp.
3. **Sandbox + Gate** — code tự sinh phải qua kiểm AST + chạy thử cô lập + Sếp duyệt.

## 6. Vòng tự-phát-triển (đã khép kín)

```
chạy kỹ năng → metrics ghi điểm
     ↓ mỗi đêm (daemon growth heartbeat)
reflection: log 24h → core_lesson
self_improve: thiếu kỹ năng → đề xuất (Sếp duyệt) → EvolutionEngine tự viết
metrics.trend: "mai giỏi hơn hôm nay?" → báo ra UI
     ↑
orchestrator: recall core_lesson TRƯỚC khi làm → tự điều chỉnh
```

## 7. Chạy thế nào

```bash
# 1) Môi trường
python -m venv venv && venv\Scripts\activate        # Windows
pip install -r requirements.txt                     # hoặc cài lẻ bên dưới
# Lõi: requests beautifulsoup4 pydantic pydantic-settings chromadb websockets PyQt6
# Local LLM: cài Ollama + `ollama pull gemma4:e4b`
# Tuỳ chọn: playwright playwright-stealth (+ playwright install chromium), send2trash, psutil

# 2) Cấu hình
copy .env.example .env        # điền key thật vào .env (KHÔNG vào .env.example)

# 3) Chạy
python main.py                # server + daemon (LocalCPUEngine + 9 skills)
python -m interface.avatar    # Pet UI (cửa sổ 2)

# Kiểm thử nhanh kiến trúc skill (không cần model):
python smoke_test_skills.py
```

## 8. AURA đang ở đâu so với tầm nhìn

So với "trợ lý điều khiển smart house + tự lớn như người": **~65-70%**.
- ✅ Bộ khung, an toàn, 9 kỹ năng, định tuyến, trí nhớ, tự phản tỉnh, tự đo, tay chân OS cơ bản.
- ⏳ Còn lại: điều khiển chuột/bàn phím/cửa sổ sâu (`computer_use.py`), định tuyến Local↔Cloud thông minh hơn, và **trần phần cứng** (gemma4 trên 12GB RAM giới hạn suy luận sâu — dùng CloudEngine cho bước nặng hoặc nâng RAM/GPU).

## 9. Mẹo để Sếp KHÔNG "lười suy nghĩ"

- AURA luôn **hỏi trước khi làm việc rủi ro** — đó là lúc Sếp ra quyết định thật.
- Đọc **nhịp tim trưởng thành** (🌱) mỗi ngày: nó nói AURA học gì, đề xuất gì, đang khá lên hay tệ đi → Sếp duyệt hay bác.
- Mọi quyết định kiến trúc vẫn là của Sếp; AURA chỉ thực thi + đề xuất.

---
*Cập nhật tự động bởi AURA. 41 file mã đã kiểm cú pháp sạch, registry khám phá đủ 9 skills.*
