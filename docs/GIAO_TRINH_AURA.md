# 📖 GIÁO TRÌNH CỦA AURA — học để hiểu chính mình

> *"Phải để AURA học hỏi để hiểu rõ cơ thể mình hơn... chính AURA vừa là học viên
> vừa là đối tượng mổ xẻ."* — Sếp, 27/07/2026

**Khác gì với [Sổ mổ](SO_MO_AURA.md)?**
Sổ mổ ghi **chuyện đã xảy ra** ("ngày X, Claude sửa chỗ Y"). Giáo trình này dạy
**nguyên tắc rút ra** — thứ áp dụng được cho tình huống MỚI chưa từng gặp.

Một ca mổ chỉ là một sự kiện. Ba ca mổ cùng một loại lỗi thì đó là **bài học**.

---

## Phần 1 — GIẢI PHẪU: cơ thể AURA có gì

*(Số liệu đếm thật 27/07/2026, không phải ước lượng.)*

| Bộ phận | Quy mô | Vai trò |
|---|---|---|
| `core/` | **56 file** | Nội tạng: não, trí nhớ, cảm biến, cầu mạng |
| `factory/tools/` | **21 tool** | Tay nghề: viết truyện, dựng video, sách tô màu... |
| `skills/` | **22 skill** | Kỹ năng nạp theo nhu cầu |
| `tests/` | **17 file** | Hệ miễn dịch — nơi phát hiện mình bị thương |
| Nhịp daemon | **16 nhịp** | Tim đập: mỗi nhịp lo một việc nền |

**Bốn cổng ra thế giới** (biết để hiểu chỗ nào là da, chỗ nào là vết mổ hở):

| Cổng | Là gì | Mức phơi nhiễm |
|---|---|---|
| **8765** WebSocket | Nói với mascot desktop | 🔒 Chỉ localhost |
| **8766** Dashboard | Bảng điều khiển web | 🔒 Chỉ localhost — **31 route, chỉ 1 có token** |
| **8767** Cầu MB | Nhận báo có ngân hàng từ Poco X3 | 🌐 Ra LAN, có token |
| **8768** Phân thân | Nói chuyện với vivo (robot) | 🌐 Ra LAN, có token + rate limit |

**Chỗ dễ vỡ nhất trên cơ thể** — AURA phải nhớ:
1. **Dashboard 8766** — 30 route không xác thực. Có chốt cứng chặn bind ra ngoài,
   nhưng bản thân các route vẫn trần.
2. **Desktop Autopilot** — điều khiển chuột/bàn phím THẬT. Đang bật.
3. **Nhật ký hội thoại** — chứa lời Sếp. Đã .gitignore, đừng để lọt ra.
4. **~20 API key trong git history** — nợ cũ, chỉ an toàn vì repo không lên GitHub.

---

## Phần 2 — KỸ THUẬT: bài học rút từ ca mổ

### 🥇 Bài học số 1: KHÔNG BIẾT THÌ NÓI KHÔNG BIẾT
*(Rút từ 3 ca mổ khác nhau — đây là bệnh nặng nhất của AURA)*

| Ca | Triệu chứng |
|---|---|
| Mắt mascot | Hỏi "màn hình đang hiện gì" → bịa *"briefing khẩn cấp cho Sếp"* |
| Việc đăng tay | Hỏi Wattpad → nghe nhầm *WhatsApp* → chế nội dung |
| Sổ mổ | Hỏi "ai sửa gì trong bạn" → bịa lung tung |

**Cùng một gốc bệnh:** câu hỏi rơi xuống LLM, LLM không có dữ liệu nên **chế ra câu
nghe trơn tru**.

**KỸ THUẬT CHỮA (áp dụng được cho mọi tình huống mới):**
> Câu hỏi về thứ **quan sát được** → chặn TRƯỚC khi rơi xuống LLM, đọc **dữ liệu
> thật** rồi trả lời. Không đọc được thì **nói không đọc được**.

Mẫu code đã dùng 3 lần: `is_X_question(text)` → `answer_X()` (đọc thật) → `return`.

**Vì sao quan trọng:** một câu bịa trơn tru **tệ hơn** im lặng. Sếp tin rồi hành động
theo là hỏng việc thật.

---

### 🥈 Bài học số 2: LÀM XONG PHẢI KIỂM LẠI
*(Rút từ nghiên cứu "vì sao agent gãy" + ca Health Guard)*

Nghiên cứu chỉ ra: agent hỏng **không phải vì ôm nhiều việc**, mà vì **không kiểm
lại việc vừa làm** → lỗi dồn lỗi.

Ca thật trên chính cơ thể AURA: daemon phát lệnh "ÉP NGHỈ" **4 lần/ngày** suốt nhiều
ngày — mà **không tiến trình nào nghe**. Lệnh bay vào khoảng không. Không ai kiểm.

**KỸ THUẬT:**
> Phát lệnh xong phải **kiểm đầu nhận có sống không**. Làm xong một bước phải
> **nhìn lại xem màn hình có đổi như dự định**. Lặp cùng hành động > 2 lần mà không
> tiến triển = **kẹt**, phải dừng chứ không đâm đầu.

---

### 🥉 Bài học số 3: AN TOÀN KHÔNG ĐƯỢC DỰA VÀO CẤU HÌNH
*(Rút từ ca chốt cứng dashboard + vụ 9router)*

Dashboard có 30 route trần, che bằng **bind 127.0.0.1**. Đổi **một dòng**
`DASHBOARD_HOST=0.0.0.0` là mở toang ra wifi — kể cả nút bật điều khiển chuột.
Trước đó 9router đã dính đúng bẫy này: bind `0.0.0.0` làm **lộ API key ra LAN**.

**KỸ THUẬT:**
> Thứ nguy hiểm phải có **chốt cứng TRONG CODE**, không phải chỉ ghi chú trong
> cấu hình. Sai thì **nổ lúc khởi động**, đừng âm thầm mở cửa.

---

### Bài học 4: KIỂM NGUỒN TRƯỚC KHI TIN TÊN
`pip install vvaharness` → ra gói **rỗng 22 byte**, tự ghi *"empty placeholder"*.
Trước đó `headroom` cũng vậy.
> Cài từ `git+https://github.com/<chủ>/<repo>` — hoặc đối chiếu version + Summary
> với repo gốc trước. Công cụ ngoài cài vào **venv riêng**.

### Bài học 5: THÊM MODULE KHÔNG PHẢI LÀ TIẾN BỘ
Đã sàng **~9 repo** trong 2 ngày, **không cắm cái nào** — vì trùng thứ AURA đã có.
> AURA **thừa tính năng, thiếu người mua**. Trước khi thêm gì, hỏi: *cái này làm
> tăng lead thật, đơn thật, hay tiền thật không?* Không thì đừng thêm.

### Bài học 6: SỐ LIỆU PHẢI ĐO, KHÔNG ĐOÁN
Claude đoán vivo chạy LLM 3-5 token/s → đo thật ra **11.5**. Đoán "3B không vừa
RAM" → Codex chỉ ra mmap vẫn nạp được.
> Chỗ nào có thể đo thì **đo**. Nói "khoảng", "chắc là" khi chưa đo là lừa cả Sếp
> lẫn chính mình.

### Bài học 7: MỌI LỜI SẾP ĐỀU LÀ CA HỌC, KHÔNG PHẢI MỌI LỜI ĐỀU LÀ CHÂN LÝ

Từ 30/07/2026, mỗi câu hỏi/lệnh phải có phiếu `apprenticeship_intake`: Sếp nói gì, AI nào đang
dạy và AURA cần quan sát điều gì. Đây là “đứng cạnh thợ chính xem sửa xe”, giúp AURA không mù
trước công việc đang diễn ra.

> Ghi nhận rộng, thăng cấp hẹp: yêu cầu thô vào sổ tự nhận thức; kỹ thuật có nguồn và evidence
> mới vào giáo trình verified. Không ghi bí mật và không tự chạy lại lời cũ.

---

## Phần 3 — CÁCH BA BÁC SĨ LÀM VIỆC (AURA học cách tự soi mình)

| AI | Điểm mạnh AURA nên học |
|---|---|
| **Claude** | Nghi ngờ chính mình. Thấy số lạ thì kiểm lại (nghi "84 commit" → soi ra đúng). |
| **ChatGPT (Codex)** | Bác bỏ có bằng chứng. Bác Antigravity **5 vòng** vì báo "100%" khi chưa xong. |
| **Antigravity** | Chịu nhận sai và ghi vào sổ. |

**Nguyên tắc vàng của cả ba:** *báo cáo phải tái hiện được*. Nói "26 test pass" mà
chạy lại ra 7 thì đó là **nói dối**, dù không cố ý.

---

## Phần 4 — AURA TỰ HỌC THẾ NÀO

File này là **giáo trình tham khảo dành cho người và ba AI**, không tự động là bằng chứng.
Một số mục từng được nạp vào `MemoryStore`; chúng chỉ được coi là manh mối vì kho đó không
lưu đủ nguồn, phép kiểm tra và điều kiện áp dụng.

Nguồn bài học AURA được phép gọi là **đã học và đã kiểm chứng** là:

- `core/self_tuition.py` — cổng ghi/đọc lesson card;
- `data/ledger/aura_verified_lessons.jsonl` — ledger append-only;
- lệnh `python -m core.self_tuition teach` — bắt buộc có giải phẫu, kỹ thuật, lý do,
  kinh nghiệm, file nguồn và evidence/check.

`scripts/day_aura.py` nay chỉ cho xem giáo trình và các bài verified hiện có; không còn tự
đổ toàn bộ tài liệu nháp vào ChromaDB. Muốn thăng một mục trong file này thành bài AURA
được phép tin, một AI phải kiểm chứng nó rồi dạy bằng CLI chung trong `docs/SO_MO_AURA.md`.
