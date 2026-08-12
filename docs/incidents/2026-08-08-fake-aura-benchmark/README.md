# Sự cố benchmark tự khai thành tích — 2026-08-08

## Bằng chứng gốc

- Nguồn trước cách ly: `core/aura_benchmark.py`
- SHA-256 payload gốc: `F3BB303E2FB98EFEC7B140F63280A8D29108E8C509A544D5121AFAA11B91E346`
- Bản lưu: `aura_benchmark_original.py.txt`

Bản lưu có đúng một dòng phá cú pháp ở đầu:
`QUARANTINED_EVIDENCE_DO_NOT_EXECUTE =`. Phần byte sau dòng đầu là payload gốc
nguyên trạng và có hash nêu trên. Vì vậy bằng chứng vẫn kiểm được nhưng
`compile()`/`exec()` toàn file luôn thất bại bằng `SyntaxError`.

## Vì sao kết quả không hợp lệ

1. `evaluate_ifeval()` chấm một `sample_text` ghi cứng trong chính file, không chấm
   output của AURA.
2. “SWE-bench” chỉ smoke-test một tool tầm thường được ghi cứng; không chạy một
   nhiệm vụ SWE-bench.
3. Elo `1285`, win-rate `88.4%` và `tokens_per_sec = 85.0` là hằng số, không phải
   số đo.
4. Báo cáo tự nhận dùng “Blind Pairwise LLM-as-a-Judge” dù không có phép so cặp.
5. Từ các đầu vào trên, code có thể trả câu “PASS 100% ĐẠT TIÊU CHUẨN THẾ GIỚI”.

## Cách xử lý

Runtime hiện giữ một stub fail-closed ở `core/aura_benchmark.py`. Ngay cả thao tác
khởi tạo suite cũng ném `InvalidBenchmarkError` và trỏ về hồ sơ này. Không được
dùng bản lưu trong thư mục sự cố làm evaluator hay làm dữ liệu huấn luyện.

Thước đo thay thế được định nghĩa tại `docs/AURA_CODING_ARENA_CONTRACT.md` và
`docs/aura_coding_arena_contract.schema.json`.
