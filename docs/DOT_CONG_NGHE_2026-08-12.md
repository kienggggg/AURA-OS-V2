# Đợt công nghệ 12/08/2026 — 19 cái vào sổ, phân loại trước khi đo

Cả 19 đều ở trạng thái **DISCOVERED**: biết tên, **chưa đo gì trên máy này**.

Mỗi mục có **hai** claim để riêng: `-nguon-noi` (lời của video/README) và
`-da-tra` (tra GitHub API và đọc tệp LICENSE ngày 12/08). Tra API **không** đưa
mục nào lên trạng thái cao hơn — nó cho biết repo có thật và số sao/giấy phép ra
sao, không phải chạy được trên máy này.

## Bản đầu của trang này ghi thiếu — đây là chỗ đã sửa

Bản đầu chỉ chép lời nguồn, chưa mở cái nào ra. Tra rồi thì:

| | nguồn nói | tra ra |
|---|---|---|
| **wigolo** | 904 sao · AGPL-3.0 | **4.506 sao** (thấp 5 lần). Giấy phép: GitHub API trả `NOASSERTION`, nhưng **đọc tệp LICENSE thì đúng là AGPL-3.0** — tin trường metadata là báo sai ngược lại |
| **Claude-Code-Game-Studios** | 14k sao | **23.806** — video thấp 70% |
| **DiffusionGemma** | 25,2B tổng | **26B** (`google/diffusiongemma-26B-A4B-it`). 3,8B active và "nhanh gấp 4" thì đúng |
| **page-agent** | (không nêu repo) | **`alibaba/page-agent`, 28.592 sao, MIT**. GitHub search không ra, tra web mới thấy |
| **dots.ocr** | (không nêu repo) | `studio-dots-ai/dots.ocr`, 9.066 sao, MIT |
| **Ix** | đọc như dự án lớn | **694 sao** — dự án nhỏ, đúng như nó tự nhận là alpha |
| **Firecrawl for Codex** | (không nêu repo) | `firecrawl/firecrawl-codex-plugin`, **15 sao** |
| **Cloudflare Monetization Gateway** | — | **không phải mã nguồn mở**, là dịch vụ + bài blog. Không có repo để đo |

Lại đúng kết luận đợt 2: **số trong video không đáng tin theo cả hai chiều** —
lần này cả ba chỗ lệch đều là video ghi THẤP hơn thật.

Số sao, giấy phép, tốc độ trong claim `-nguon-noi` vẫn là **lời của nguồn**.

Việc của trang này không phải chọn cái tốt, mà là **loại sớm cái sổ đã trả lời rồi** —
đúng giá trị đã đo được của sổ: 20 công nghệ trước đó, **0 cái được cắm vào AURA**,
nhưng 3 cái bị chặn vì đã biết là xấu.

Trạng thái REJECTED/BLOCKED **không tự đặt được** — đó là quyết định của Sếp, không
phải kết quả của một lệnh (CLAUDE.md §5). Dưới đây là đề nghị, chờ Sếp gật.

---

## A. Sổ đã trả lời rồi — đề nghị loại, không cần đo

| | vì sao đã trả lời |
|---|---|
| **Unsloth Desktop** | Train model trên máy **không GPU rời**. Cùng loại với AirLLM — đã đo **60,6 giây/token** cho 70B rồi BLOCKED. Chính nguồn cũng viết "máy yếu vẫn train được nhưng sẽ chậm hơn nhiều". Nguồn đã tự trả lời. |
| **DiffusionGemma** | **26B tham số tổng** (nguồn ghi 25,2B là sai). Google nói: lượng tử hoá rồi vẫn cần **~24 GB VRAM**. Máy có **11,7 GB RAM** và **không GPU rời**. Đây là con số của chính nhà phát hành, không phải suy đoán của tôi. |

## B. Không thuộc bài toán của AURA

**authentik** (máy chủ định danh cho tổ chức — AURA một người dùng, chạy local;
thêm nữa giấy phép là `NOASSERTION`, phải đọc tệp trước khi dùng) ·
**croc** (truyền tệp giữa hai máy) ·
**Cloudflare Monetization Gateway** (không phải mã nguồn mở — dịch vụ + bài blog,
không có gì để đo) ·
**Claude of Duty**, **Claude-Code-Game-Studios** (demo game, không phải hạ tầng).

**the-elements-of-style** và **complete-shelf** — loại vì **KHÔNG CÓ GIẤY PHÉP**.
Không giấy phép nghĩa là tác giả giữ toàn quyền: đọc thì được, dùng lại là vi phạm.
Đây mới là lý do loại. Bản đầu của trang này ghi "không phải hạ tầng" — đúng nhưng
lạc chỗ, và sẽ sai nếu sau này AURA cần đúng loại nội dung đó.

## C. Đáng xem, nhưng có điều kiện — nêu điều kiện luôn

**Ix** — đúng bài toán "ba AI một repo, mỗi phiên đọc lại codebase từ đầu", claim
tiết kiệm 30–99,7% token. Nhưng: **694 sao** (bài giới thiệu đọc như dự án lớn, thật
ra nhỏ), còn **alpha**, cần **Docker + ArangoDB + Node 22** — nặng hơn cả AURA v3
(17 tệp, 3 gói). Và sau khi tách, v3 chỉ còn **4.248 dòng**, chưa đủ lớn để cần đồ thị.
*Điều kiện để đo: khi có codebase thật sự lớn phải làm việc thường xuyên.*

**page-agent** — tra ra là **`alibaba/page-agent`, 28.592 sao, MIT, TypeScript**,
không backend. Đây là cái đáng chú ý nhất đợt này về mặt chất lượng dự án, và đúng
tinh thần v3. Nhưng v3 hiện không có việc nào cần GUI agent.
*Điều kiện: khi cần AURA thao tác trên trang web.*

**browser-use** — hôm nay bài "đọc Facebook" đã giải xong bằng **trình duyệt trong app,
0 phụ thuộc thêm**, đọc được 34/36 link. browser-use kéo theo Playwright + vòng lặp LLM.
*Điều kiện: khi cách hiện tại gãy.*

**wigolo** — **AGPL-3.0**. Nếu AURA từng phát hành thì giấy phép này lây sang. Cân
nhắc giấy phép **trước** khi bỏ công đo.

**dots.ocr**, **PaddleOCR** — chồng một phần lên `docling` (8,2s) và `markitdown` (8,1s)
đã BENCHMARKED. Nhưng hai cái đó đọc **PDF có sẵn chữ**; OCR là cho **ảnh chụp / bản
scan**. Đây là khe hở thật, không phải trùng lặp. *Câu hỏi quyết định: có tài liệu nào
là ảnh scan không? Không có thì bỏ cả hai.*

**Firecrawl for Codex** (dịch vụ ngoài, cần khoá) · **GenOffice**, **PPT-MASTER**
(sinh tài liệu — chưa có nhu cầu) · **Mano-P** (nguồn không nêu số đo nào).

---

## Thứ KHÔNG vào sổ

Bốn thứ trong đợt này không phải công nghệ nên không có mục: sơ đồ **10 bước RAG**,
sơ đồ **4 loại memory**, video giải thích **MCP**, và bộ **8 prompt làm website**.
Chúng là nội dung để đọc, không phải thứ cài được và đo được.
