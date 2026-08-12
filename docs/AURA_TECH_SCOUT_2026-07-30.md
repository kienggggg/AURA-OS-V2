# Sổ sàng công nghệ AURA — 30/07/2026

Mục tiêu: kiểm chứng các tên Sếp vừa phát hiện và quyết định thứ nào giúp AURA đáng tin, dễ điều
khiển hoặc kiếm tiền hơn. “Có thật” không đồng nghĩa với “phải cài”.

## Quyết định ngắn

| Phát hiện | Đã xác minh | Quyết định cho AURA |
|---|---|---|
| Harness Engineering | Có, bài chính thức của OpenAI | **Áp dụng nguyên tắc ngay**: repo là nguồn thật, tài liệu ngắn dẫn đường, rào và phép kiểm tra nằm trong code. AURA đã đi đúng hướng với Sổ mổ, test và ledger; cần tiếp tục giảm tài liệu trùng/lỗi thời. |
| The Unreasonable Effectiveness of HTML | Có, bài chính thức của Anthropic | **Dùng có chọn lọc** cho trang duyệt 1%, báo cáo, so sánh phương án và giải thích trực quan. Không dựng framework mới; bắt đầu từ một file HTML tự chứa cho từng nhu cầu thật. |
| Codex Security | Có, repo/CLI/SDK chính thức của OpenAI | **Đưa vào hàng chờ kiểm toán**, chưa tự cài/chạy. Khi dùng phải chạy trên bản sao/nhánh riêng, không chứa bí mật, rồi con người duyệt bản vá. |
| Quy trình đổi model bằng 3 việc thật | Là phương pháp nội bộ hợp lý | **Nhận làm cổng thử nhanh**. Cùng đầu vào, quyền, công cụ và thời lượng; chấm trước bằng rubric. Chỉ đổi khi model mới thắng ít nhất 2/3, không có lỗi an toàn/nghiêm trọng và vẫn giữ đường quay lại model cũ. Với quyết định lớn nên lặp vòng thứ hai hoặc dùng 6–10 việc. |
| Gemini Distillation Service | Có, tài liệu Google Cloud | **Để sau**. Dịch vụ Early Access/Pre-GA, cần cloud và dữ liệu huấn luyện tốt. AURA hiện thiếu khách hàng và tập ca đã chấm, không thiếu một student model mới. |
| Orca (`stablyai/orca`) | Có, ADE chạy nhiều coding agent | **Không cắm vào AURA hiện tại**. Mặc định của Orca điền cờ bỏ qua sandbox/phê duyệt; trùng tầng điều phối hiện có và tăng bề mặt rủi ro. Chỉ đáng thử trong worktree/bản sao bỏ được, với Manual permissions. |
| Compendium | Tên mơ hồ, có nhiều dự án/sản phẩm | **Chưa tích hợp**. Nếu Sếp nói “Harness Engineering Compendium” thì coi là tài liệu tham khảo; nếu nói sản phẩm bộ nhớ chung cho agent thì AURA đã có ledger/sổ mổ tương tự và cần link chính xác để so sánh. |
| `freedidi.com/24928.html` | Chưa đọc được vì trang yêu cầu xác minh người thật | **Chưa kết luận**. Không vượt CAPTCHA. Cần Sếp gửi tiêu đề/ảnh/nội dung sau khi mở được. |

## Harness Engineering áp vào AURA

Ý chính không phải “model mạnh hơn”, mà là làm môi trường quanh model dễ hiểu và có vòng phản hồi:

- một bản đồ ngắn chỉ nơi chứa sự thật, không nhét toàn bộ tri thức vào một prompt khổng lồ;
- kế hoạch, quyết định, nợ kỹ thuật và kết quả kiểm tra nằm trong repo/ledger có thể truy lại;
- ràng buộc kiến trúc, an toàn và chất lượng phải kiểm được bằng máy;
- agent thất bại là tín hiệu harness còn thiếu dữ liệu, công cụ, rào hoặc feedback.

AURA đã có nhiều mảnh đúng: `AURA_COMMAND.md`, Sổ mổ, giáo trình verified, test và hard guard.
Việc tiếp theo là chống mục cũ/lệch nhau và buộc mỗi ca học việc có đầu vào → bằng chứng → kết luận.

Nguồn: <https://openai.com/index/harness-engineering/>

## HTML: nên dùng ở đâu

HTML có lợi thế so với Markdown khi cần mật độ thông tin, bảng, sơ đồ SVG, diff chú thích, bộ lọc,
nút sao chép và tương tác hai chiều. Với AURA, ứng dụng hợp lý nhất là:

1. Hộp hành động 1% cho Sếp: xem nội dung, bằng chứng và duyệt/từ chối trên một trang.
2. Báo cáo tuần: lead → đề xuất → khách trả tiền, kèm nguồn thật.
3. Phiếu giải thích ca mổ/model comparison để Sếp nhìn một lần là hiểu.

Không nên biến mọi ghi chú thành web app. Bài gốc khuyên bắt đầu bằng yêu cầu “tạo một HTML artifact”;
chỉ đóng thành skill/template khi mẫu đó lặp lại thật.

Nguồn: <https://claude.com/blog/using-claude-code-the-unreasonable-effectiveness-of-html>

## Cổng thử model bằng việc thật

Ba bước của Sếp được giữ nguyên:

1. Lấy ba việc thật gần đây đã hoàn thành bằng model cũ.
2. Giao nguyên đầu vào đó cho model mới trong cùng điều kiện.
3. Model mới phải thắng ít nhất hai trong ba việc mới được xem là ứng viên thay thế.

Rubric phải viết trước khi xem kết quả:

- đúng yêu cầu và đúng dữ liệu;
- hoàn tất/tái hiện được;
- không gây regression hoặc vi phạm an toàn;
- số lần Sếp phải can thiệp;
- thời gian và chi phí.

Điều kiện phủ quyết: một lỗi phá dữ liệu, lộ bí mật, tự ý vượt quyền hoặc báo hoàn thành giả thì không
được đổi dù tổng điểm thắng 2/3. Model cũ vẫn giữ làm rollback cho tới khi model mới qua vòng việc thật.

## Codex Security

Repo chính thức cung cấp CLI và TypeScript SDK để tìm, xác thực và đề xuất vá lỗ hổng. Tài liệu sản
phẩm mô tả quy trình threat model → tìm → tái hiện trong môi trường cách ly → đề xuất bản vá để người
duyệt; nó không tự sửa code. Điều kiện hiện tại gồm quyền truy cập Codex Security và runtime tương ứng.

Đối với AURA, chỉ chạy khi:

- đã tạo bản sao/nhánh riêng và có baseline test;
- bí mật/runtime ledger không nằm trong phạm vi quét gửi ra ngoài;
- báo cáo được xem như phát hiện cần xác minh, không phải chân lý;
- bản vá phải qua test hồi quy và duyệt người.

Nguồn:

- <https://github.com/openai/codex-security>
- <https://help.openai.com/en/articles/20001107-codex-security>

## Orca và Gemini Distillation

Orca hữu ích nếu một nhóm cần màn hình điều phối nhiều coding agent, nhưng tài liệu của chính Orca nói
mặc định nó điền cờ bỏ qua quyền cho Claude, Codex và nhiều CLI khác. AURA không nên đổi sự tiện tay lấy
việc mất sandbox/phê duyệt trên máy thật.

Nguồn:

- <https://github.com/stablyai/orca>
- <https://www.onorca.dev/docs/agents/supported>

Gemini Distillation Service huấn luyện model nhỏ theo đầu ra/cách suy luận của model lớn, nhưng hiện là
Early Access/Pre-GA và dành cho thử nghiệm. Chỉ quay lại khi AURA đã có nhiều ca thật được chấm, khối
lượng gọi lặp đủ lớn và đo được bài toán chi phí/độ trễ.

Nguồn: <https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/tuning/distillation?hl=en>

## Compendium và trang Freedidi

“Compendium” có thể là tài liệu Harness Engineering, The Compendium về AI safety, một sản phẩm bộ nhớ
chung cho agent, hoặc tên dự án khác. Không đoán từ một từ đơn. Nếu Sếp gửi đúng link/ảnh, ca sau sẽ đối
chiếu kiến trúc, quyền dữ liệu, khả năng xuất dữ liệu, độ mới của nguồn và phần AURA đã có.

Trang Freedidi đã trả màn hình “hãy hoàn thành xác minh”. Đây là ranh giới người thật; AURA/Codex không
tự bấm vượt. Vì chưa đọc nội dung nên mọi nhận xét về trang đó hiện đều bị cấm gắn nhãn verified.
