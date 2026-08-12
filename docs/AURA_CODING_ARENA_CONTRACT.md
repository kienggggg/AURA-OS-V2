# AURA Coding Arena — hợp đồng đo lường vòng 1

## Miền được phép đo

Chỉ đo việc sửa lỗi Python trong `AURA_OS_v2` khi đã có một test đỏ tái hiện được.
Patch bị giới hạn file, không mạng, không sửa test. Một lượt chỉ đạt khi test đỏ
thành xanh và regression thật vẫn xanh. Đây là chuẩn promotion; pilot chỉ kiểm
runner nên bắt buộc ghi `regression_pass: null` và không được tự nhận là đạt.

## Ranh giới tin cậy

- Coder chỉ được tạo patch trong workspace bỏ được.
- Hidden tests, đồng hồ, bộ đếm ký tự, HMAC signer và luật promotion thuộc evaluator.
- Coder không được ghi điểm, sửa test, sửa schema, đọc hidden tests hoặc đổi router.
- `recall`, cloud fallback và model ngoài allowlist phải tắt trong arena.
- `.env`, kho bí mật, audit log và mã nguồn thật nằm ngoài vùng ghi.
- Mọi batch được đăng ký trước bằng record `pre_registration` có HMAC; manifest
  được tính lại từ task records trước khi mở kết quả.
- Khóa HMAC chỉ ký bằng chứng máy và được truyền trực tiếp cho evaluator từ vùng ngoài workspace của coder;
  validator không tự đọc `.env` và không có khóa mặc định.
- Approval của Sếp tuyệt đối không dùng chung khóa với evaluator. Nó là tin nhắn
  Telegram trả lời đúng yêu cầu `vibe_diff`, được một verifier độc lập kiểm lại
  `message_id`, `reply_to`, `from_user_id` và tài khoản thật của Sếp.

## Cách chấm

Hai đối thủ nhận cùng snapshot, nhiệm vụ, quyền, ngân sách và giới hạn thời gian.
Kết quả ghi bốn ô paired counts. Batch 30 đầu là baseline, không dùng để tuyên bố
thắng. Tuyên bố thắng cần hai batch kín cùng hướng và exact McNemar một phía
`p < 0.05` trên các đề lệch. Không đủ đề lệch thì kết quả là `INCONCLUSIVE`; không
đổi ngưỡng sau khi xem kết quả.

Hai đối thủ phải nhận prompt giống nhau tới từng byte; evaluator ghi cùng
`prompt_sha` vào hai episode. Arena tắt recall, history và tools. Prompt không
được chứa slug, category, lý do cài lỗi, đường dẫn repo, hidden test hay đáp án.

### Luật đặt tên theo nguồn (schema v2)

Mọi trường phải mang tên theo **nguồn thật**, không theo điều ta mong muốn nó
chứng minh:

- Dữ liệu adapter/thí sinh cung cấp phải có `reported` hoặc `declared`, ví dụ
  `tokens_reported_by_participant`, `declared_history_free`.
- Chỉ dữ liệu evaluator tự đếm mới có `measured_by_evaluator`, ví dụ
  `prompt_chars_measured_by_evaluator` và `reply_chars_measured_by_evaluator`.
- Các cờ `declared_*` chỉ là lời khai để kiểm hợp đồng adapter, không phải bằng
  chứng rằng history/tools/recall đã bị cách ly. Promotion cần adapter và router
  do evaluator sở hữu để cưỡng chế thật.
- `requested_max_output_tokens` là giới hạn output được **yêu cầu** từ adapter;
  generic runner không được gọi nó là token đã đo. `budget_prompt_chars` và
  `budget_reply_chars` mới là hard cap evaluator tự đếm theo số Unicode code
  point của đúng chuỗi nhận được, trước parse và không normalize. Ký tự không
  được đánh tráo thành token.
- `red_test_pass` chỉ nói test đỏ công khai đã xanh. `regression_pass` chỉ được
  là `true/false` sau khi một regression suite thật đã chạy; pilot hiện ghi
  `null`, vì vậy không thể vượt cổng promotion.

## Hai chế độ không được đánh tráo

- `pilot`: model gọi text-only, evaluator dùng subprocess cục bộ sau AST gate.
  Vì đây không phải sandbox cấp hệ điều hành, mọi result phải mang safety flag
  `pilot_no_os_sandbox`, `participant_isolation_unverified` và
  `regression_not_run`; do đó không thể làm repro hay promotion evidence.
- `promotion`: chỉ được chạy khi có backend OS/container đã review, trusted pack
  chưa từng vào repo, không mạng, giới hạn tài nguyên và coder không đọc được
  hidden/đáp án. Thiếu backend thì fail-closed, không tự hạ xuống pilot.

Pack pilot 10 đề ngày 08/08/2026 đã lộ đáp án trong lịch sử thảo luận và chỉ được
dùng để kiểm runner. Nó vĩnh viễn không được dùng đo baseline hoặc tuyên bố thắng.

## Chuỗi bằng chứng

`pre_registration → task → episode → result → lesson → approval → promotion` phải
nối bằng ID, hash, HMAC của evaluator và bằng chứng Telegram của Sếp theo schema máy đọc được. JSON Schema chỉ kiểm hình
dạng; `core/coding_arena_evidence.py` tính lại manifest, HMAC, p-value và quan hệ
giữa các record. Lesson có evidence trùng held-out bị từ chối. Promotion cần hai
lần tái lập mới của chính AURA, rollback ref và approval Telegram sau `vibe_diff`.

Ledger JSONL bọc mỗi evidence record đã ký trong một envelope có số thứ tự,
`prev_sha` và HMAC riêng. Một head sidecar đã ký neo số record và hash cuối để
phát hiện sửa/xóa/chèn giữa sổ và việc cắt đuôi thông thường. Xác minh ledger phải
chạy trước khi append tiếp. Hash-chain + head cục bộ vẫn không chứng minh được
việc cả ledger lẫn head cùng bị rollback về một snapshot cũ hợp lệ; promotion
thật cần neo head cuối ở vùng evaluator độc lập/append-only.
Evaluator là writer duy nhất; khóa trong tiến trình không được quảng cáo như khóa
đa tiến trình. Promotion backend sau này phải dùng OS lock hoặc trusted writer
service để ngăn hai tiến trình tạo hai nhánh ledger.

## Quyền duyệt duy nhất

Chạy trận, ghi episode, tạo lesson ứng viên và kiểm held-out không cần hỏi từng
lệnh. Chỉ thời điểm một patch do AURA tự sinh được đưa vào mã nguồn thật mới cần
Sếp duyệt qua nút/trả lời Telegram cho `vibe_diff`. Validator chỉ nhận promotion
khi callback độc lập xác minh tin nhắn ấy thực sự đến từ tài khoản của Sếp; AURA
không được tự tạo approval bằng khóa HMAC của evaluator.
