# Kiểm 23 nguồn — 11/08/2026

Sếp gửi nội dung 23 link (Sếp tự chép, vì TikTok chặn `yt-dlp`) và yêu cầu kiểm
kỹ. Hồ sơ này chốt lại **cái gì đã kiểm, kiểm bằng gì, và kết ra sao** — để
không ai phải đào lại.

Luật áp dụng: lời trong video chỉ là **đầu mối**. Chỉ ghi "đã kiểm chứng" khi
có lệnh chạy thật và kết quả lưu trên máy.

---

## 1. Số sao GitHub — 22/22 ĐÚNG

Tôi mở phép kiểm với giả định số sao bị thổi phồng. **Sai.**

| video khoe | thật (11/08) | lệch |
|---|---|---|
| ECC 235,2K | 239.296 | +1,7% |
| OpenClaw 385K | 385.839 | +0,2% |
| Hermes 224K | 228.582 | +2,0% |
| anthropics/skills 160K | 167.638 | +4,8% |
| hallmark 17,4K | 23.587 | +35% (repo lớn thêm) |
| ui-ux-pro-max 101K | 115.404 | +14% |
| KeyGraph 42K | 46.610 | +11% |

Lệch đều theo hướng **repo lớn thêm sau khi quay video**. Mấy kênh này đọc số
từ GitHub chứ không bịa.

### Chỗ TÔI sai

Tôi kết luận **"KeyGraph không tồn tại"** vì `api.github.com/search?q=keygraph`
trả về `keygraph/project` (13 sao) và không có gì khác. Sếp tìm ra ngay:
**`KeygraphHQ/shannon`** — 46.610 sao, AGPL-3.0, 275 commit, cập nhật 19 giờ
trước. Tên tổ chức lệch tên repo nên search xếp hạng kém.

**Luật rút ra:** tra không thấy thì nói *"tôi không tìm thấy"*, không được nói
*"không tồn tại"*.

---

## 2. OpenClaw — ĐO THẬT, và KHÔNG dùng được trên máy này

Cài `npm install -g openclaw` (83,4 MB gói, 309 phụ thuộc, 4 phút). Cắm vào
đúng bộ não local AURA đang chạy (`ollama/qwen3.5:4b`, `baseUrl`
`http://127.0.0.1:11434`, không dùng đuôi `/v1` theo cảnh báo trong tài liệu).

Ba lượt chạy thật:

| hỏi | đáp | giây |
|---|---|---|
| Thủ đô Việt Nam là gì? | lan man về Phùng Nguyên/Đông Sơn, **bịa ra "Mai Văn Phap"** | 101 |
| Thủ đô Việt Nam là gì? | trả lời về **thứ mấy trong tuần**, dịch sai "Thứ Hai = Tuesday" | 113 |
| 2 cộng 2 bằng mấy? | **rỗng** | 96 |

Đối chiếu cùng model, cùng máy:

```
AURA v3         "Hà Nội."                        3,4 s
OpenClaw        lan man + bịa tên              101   s
Hermes Agent    nhả lại lời dặn của chính nó   698   s
```

### Ba con số cần biết trước khi ai đó thử lại

- ~~**Ngữ cảnh tối thiểu 16K.**~~ **SAI — Codex kiểm chứng độc lập 11/08 và
  bác.** Tôi đọc thấy dòng *"context window of at least 16K"* trong
  `docs/providers/ollama.md` rồi gọi đó là yêu cầu cứng. Sự thật: runtime
  **chặn dưới 4K, cảnh báo dưới 8K**; 16K chỉ là ngưỡng onboarding tự đề xuất
  model. Bài học: một câu trong tài liệu **không phải** một ràng buộc trong mã.
- **Tốc độ KHÔNG đổi theo ngữ cảnh** (vẫn đúng): 3,7 tok/s ở 4K so với
  4,2 tok/s ở 32K, nhưng RAM nhảy từ 0,8 lên 4,2 GB. Cái đắt là RAM.
- ~~**Giấy phép mâu thuẫn.**~~ **Codex làm rõ: giấy phép thật là MIT.**
  `NOASSERTION` chỉ là GitHub không tự nhận diện được tệp LICENSE.

### Codex bổ sung điều tôi bỏ sót

Đường `infer` nhẹ của OpenClaw **vẫn trả lời đúng**; chỉ khi chạy **full agent**
mới hỏng (210,08 giây, lan man/sai với `qwen3.5:4b`). Tức lỗi nằm ở **lớp
agent**, không phải ở chỗ nối model — đúng một chuyện với Hermes.

### Kết

`REJECTED` cho vai trò bộ não. Đây là **lần thứ ba** cùng một dạng hỏng
(Hermes, OpenClaw, `qwen3:1.7b`): khung agent lớn nhồi lời dặn khổng lồ vào
ngữ cảnh, và model 4B **đánh mất chính câu hỏi**.

Vẫn còn giá trị để **đọc mã**: 68 nhà cung cấp (có `ollama`, `lmstudio`,
`vllm`, `litellm` hạng nhất) và danh sách kênh có cả **`zalo`**/`zalouser`.

---

## 3. Đã cài — công cụ cho Claude, không phải cho AURA

| skill | nguồn | giấy phép |
|---|---|---|
| `hallmark` | Nutlope/hallmark | MIT |
| `design` · `design-system` · `ui-styling` · `ui-ux-pro-max` · `brand` · `slides` · `banner-design` | nextlevelbuilder/ui-ux-pro-max-skill | MIT |

Chi phí đo được: **~3.900 ký tự frontmatter** (≈970 token) nạp mỗi phiên; phần
thân chỉ nạp khi gọi. 8,4 MB trên đĩa, đã cho vào `.gitignore`.

### Cố ý KHÔNG cài

- **`anthropics/skills`** (17 skill) — đã có sẵn `docx`, `pdf`, `pptx`,
  `skill-creator`, `canvas-design`… Cài nữa là trùng.
- **`affaan-m/ECC`** (**285 skill**) — 285 mô tả nạp mỗi phiên là đúng căn
  bệnh phình ngữ cảnh mà v3 đang chống. Nếu cần thì **nhặt từng cái**, sau khi
  đọc.

---

## 4. Chưa kiểm — đầu mối, không phải kết luận

| thứ | ghi chú |
|---|---|
| `KeygraphHQ/shannon` | 46.610 sao, AGPL-3.0. Pentest tự động — **công cụ tấn công**, chỉ dùng trên hệ thống của chính mình. Chưa chạy. |
| Phép đo CLI so với MCP (26.800 so với 114.000 token) | Số của đội Playwright, **chưa tự đo lại**. Trùng nguyên tắc v3 đang dùng: đừng đổ mọi thứ vào ngữ cảnh. |
| `MonkeyOCR` | 6.625 sao, Apache-2.0. README nói đa ngôn ngữ nhưng **không nhắc tiếng Việt** — cùng lỗ hổng với MinerU. |
| Claude Code: `/rc`, `/branch`, `/fork`, `/subtask`, `/background`, `/btw` | Chưa xác minh từng lệnh. |
| `makerspet/oomwoo` · `awesome-llm-apps` · `exercises-dataset` | Thật, nhưng không dính việc của AURA. |

---

## Nhắc lại luật

Số sao **không phải** phép đo — repo 385K sao vẫn trả lời sai ba lần liên
tiếp trên máy này. Thứ duy nhất đáng tin là **lệnh đã chạy và kết quả lưu lại**.

Và luật thứ hai, học từ chính hồ sơ này: **đọc tài liệu không phải là đo.**
Tôi viết "ngữ cảnh tối thiểu 16K" vì thấy câu đó trong `ollama.md`. Codex đọc
mã và thấy runtime chỉ chặn ở 4K. Một câu trong tài liệu là **lời hứa của người
viết tài liệu**, không phải ràng buộc của chương trình.
