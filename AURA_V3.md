# AURA v3 — một con chatbot, có hàng rào

> Bắt đầu 10/08/2026. v2 **không bị xoá**: toàn bộ nằm nguyên tại chỗ làm kho
> phụ tùng, tắt cờ, chờ ngày có thứ chứng minh được mình chạy thì mang sang.
> Mốc `v2-truoc-khi-don` giữ trạng thái đầy đủ trước hôm nay.

## Vì sao có v3

Đếm ngày 10/08/2026, không phải cảm giác:

| | |
|---|---|
| File `.py` trong git | 339 |
| Tổng dòng | 47.566 |
| Module trong `core/` | 74 |
| Cờ bật/tắt tính năng | 33 — **29 đang TẮT** |
| `core/config.py` | **1.029 dòng**, xương sống chat dùng đúng **1** hằng số |

Bệnh không phải "code dở". Bệnh là: **thứ gì cũng được xây rồi cắm vào, không
thứ nào phải chứng minh mình chạy, và không thứ nào bị gỡ ra.** Viết lại cho
sạch mà giữ nguyên luật thì một tháng nữa lại đúng bảng số trên.

Bằng chứng bắt được ngay ngày đầu: trang "AURA nhớ gì về tôi" xây từ 09/08 —
có `memory.html`, có `core/user_memory.py`, có test riêng, test xanh — mà
`GET /memory` trả **404** suốt, vì cửa trước độc lập không nối route. Mã sống,
test xanh, sản phẩm chết.

## v3 là gì

Đúng 13 file, đi từ một cửa vào duy nhất `aura_chat.py`:

```
aura_chat.py
core/  chat_contract.py  chat_runtime.py  chat_service.py
       local_first_gateway.py  paths.py  redact.py
       secret_guard.py  user_memory.py  web_search.py
interface/  chat_adapters.py  chat_api.py  chat_app.py
            web/chat.html  web/memory.html
```

Chạy: `venv\Scripts\python.exe aura_chat.py` → <http://127.0.0.1:8799>

## Bốn luật

**1. Local là trò, cloud là thầy.** `LocalFirstGateway` hỏi Ollama trước; chỉ
mượn cloud khi trò gục, trả rỗng, hoặc trả yếu. Cloud chết không làm AURA chết.
Đây là nguyên tắc gốc mà Chat v1 từng lật ngược *mà không ai nói ra*.

**2. Không nói dối, kể cả khi im lặng dễ hơn.** Tra mạng thì fail-closed: không
đủ nguồn thì nói "chưa tra được", không bao giờ lấy trí nhớ model thay nguồn.
Hết hạn mức thì nói hết hạn mức, không gọi là "lỗi ở bộ não".

**3. Cấu hình đi theo thứ cần nó.** Không có kho cờ chung. Cần cờ mới thì đặt
cạnh mã dùng nó. `core/paths.py` giữ đúng một hằng số, và không được phình.

**4. Vào v3 phải qua cửa.** Muốn mang một mảnh v2 sang thì **đo nó chạy trước**,
rồi sửa danh sách `V3` trong `tests/test_v3_ranh_gioi.py`. Không kéo lén qua
đường `import` — hàng rào đi từ cửa vào và lần theo import thật, kể cả import
giấu trong hàm.

## Hàng rào

`tests/test_v3_ranh_gioi.py` — hỏng ngay khi v3 với tay sang kho phụ tùng, khi
có tên chết trong danh sách, hoặc khi v3 vượt 20 file.

`tests/test_chat_app.py::test_chat_only_route_set_is_exact` — bộ đường của cửa
trước phải đếm được bằng tay.

## Số đo (10/08/2026, i5 · 11,7 GB RAM · không GPU)

```
   8,0s  local  | 2 cộng 2 bằng mấy?          -> 4
   4,0s  local  | Thủ đô Việt Nam là gì?      -> Hà Nội
  15,8s  local  | Chào AURA, bạn là ai?       -> tự giới thiệu, có nhắc luật bí mật
  10,2s  local  | Viết hàm đảo ngược chuỗi    -> def reverse_string(s): return s[::-1]
  74,5s  MẠNG   | Giá Bitcoin hôm nay?        -> 4 nguồn thật, có đánh số [1][2][3]
```

4/5 câu trò tự trả. Ba tham số quyết định tốc độ, đo được chứ không đoán:
`think=False` (339s → 24,8s), `keep_alive="5m"` (29s → 5-9s), `num_ctx=4096`.
Cỡ model **gần như không ảnh hưởng** — qwen3.5:4b 5,9 tok/s so với gemma4:e2b
5,5 tok/s.

## Không thuộc v3 (nằm trong kho, chờ đo)

Telegram · rover BLE · xưởng truyện/video · mascot · arena · crew 4 công nhân ·
desktop autopilot · SkillOpt · Wattpad/Payhip. Tất cả còn nguyên trong repo.

## Đã thử và LOẠI HẲN

**Hermes Agent** (Nous, MIT) — chạy thử 10/08/2026, **đã đóng hồ sơ**.

Đòi ngữ cảnh **64.000 token**. Trên Ollama local máy này, câu "Thủ đô Việt Nam
là gì?" mất **11 phút 38 giây** và trả về mảnh vụn system prompt của chính nó.
Cùng câu đó v3 trả **4,0 giây / "Hà Nội"**. Nó cần Python 3.11-3.13 (AURA chạy
3.14) và dài 756.101 dòng, model mặc định `claude-opus-4`.

Kiểm chứng độc lập ngày 11/08 xác nhận raw run: Hermes ghi 698 giây, đồng hồ ngoài
ghi 701,09 giây và đầu ra không trả lời câu hỏi. Nhưng hai suy luận cũ đã bị sửa:
Hermes **có** hỗ trợ Ollama local qua provider `custom`, và phép chạy này không đủ
chứng minh nó cần đúng 16 GB VRAM. Điều chắc chắn là mã đặt hard floor 64.000
token và cấu hình Hermes + model 4B không phù hợp với máy này.

Không dùng Hermes làm runtime. Nếu sau này cần sandbox, gateway hay vòng đời
skill thì chỉ học từng pattern hẹp, không clone cả khung vào front door.

**OpenClaw** — kiểm chứng độc lập 11/08/2026, **loại khỏi vai trò bộ não**.

Ba session gốc xác nhận các lỗi Claude báo: hai câu thủ đô trả lời lan man/sai và
phép tính trả `NO_REPLY`. Phép chạy mới trong profile tách biệt cho thấy đường
`infer` nhẹ còn trả đúng, nhưng full agent mất 210,08 giây và lại trả lời
lan man/sai với `qwen3.5:4b`. OpenClaw không có hard minimum 16K: runtime hiện
chặn dưới 4K, cảnh báo dưới 8K; 16K chỉ là ngưỡng onboarding tự đề xuất model.
Giấy phép thật là MIT. Chỉ đọc provider/context guard/Zalo experimental để học,
không nối OpenClaw vào front door hoặc cho nó chạy tool trên host.

## Màn hình và trí nhớ phải kể cùng một câu chuyện

Lỗi nặng nhất bắt được ngày 10/08: `persist=True` chỉ có ở **đường thành công**,
nên mọi lượt hỏng bốc hơi khỏi sổ trong khi vẫn nằm trên màn hình. Sếp hỏi "câu
thứ 2 là gì", AURA trả lời **đúng theo sổ của nó** — và sổ đó thiếu một lượt.

Giờ vào sổ: `ok`, `cannot_answer`, `web_unavailable`, `timeout`.
Không vào sổ, có lý do:

- `rejected` — cổng bí mật đã hứa "em không ghi nó vào nhật ký hội thoại". Chặn
  ngay tại chỗ ghi, không ở nơi gọi: người sau thêm một nhánh là lời hứa vỡ.
- `backend_error` — bộ não gãy trước khi AURA kịp nói với Sếp điều gì.

Lượt quá giờ cần một khoản **ân hạn riêng có trần** (`_AN_HAN_GHI_SO`) chỉ để
ghi, vì chỗ ghi sổ vốn dùng chính cái hạn giờ vừa hết.

## Máy làm việc của máy

Ba thứ AURA **không hỏi model**, vì hỏi là mời nó đoán:

| | |
|---|---|
| `core/dong_ho.py` | Giờ máy. Model từng nói 21/07 khi là 10/08 — sai 20 ngày. |
| `core/may_tinh.py` | Phép tính. Model nói "khoảng 23 ngày" khi đúng là 22, và `1247*38` ra 46396 thay vì 47.386. |
| `core/web_search.py` | Có cần tra mạng không — luật từ khoá, xem lại được, không đổi giữa hai lần chạy. |

Con số là dữ kiện của **máy**; câu chữ mới là việc của **model**.
