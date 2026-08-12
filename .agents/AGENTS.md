# Bộ Quy Tắc Hoạt Động (AGENTS.md) dành cho AI Assistant

**CẢNH BÁO QUAN TRỌNG DÀNH CHO CÁC AGENT ĐI SAU**: Dự án này là `AURA_OS_v2` - một hệ thống tự động sinh truyện (Agentic Storytelling). Để tránh "dọn rác" của nhau và tiết kiệm token, MỌI AGENT làm việc trong workspace này BẮT BUỘC phải tuân thủ các quy tắc sau:

## 1. KHÔNG LÀM THAY VIỆC CỦA AURA (Tuyệt đối không viết truyện bằng tay)
- Mục tiêu của dự án là xây dựng hệ thống để AURA **tự động** viết truyện. 
- Khi người dùng phàn nàn "Truyện dở quá", **AGENT KHÔNG ĐƯỢC TỰ TẠO RA FILE TEXT TRUYỆN MỚI**.
- Thay vào đó, Agent phải sửa mã nguồn của AURA (ví dụ: `factory/tools/story_factory.py` hoặc `factory/reflexion.py`) để cải thiện AI Prompting.

## 2. Nâng cấp chất lượng viết bằng "Few-Shot Learning", không dùng lý thuyết suông
- Nếu AURA viết văn sáo rỗng, sai tâm lý (ví dụ Isekai mà cư xử như trẻ con), hoặc nhịp độ (pacing) quá dồn dập: **CẤM** nhồi thêm các lệnh lý thuyết (như "Hãy sắc sảo lên", "Cấm dùng từ X") vào prompt một cách máy móc.
- **BẮT BUỘC** sử dụng Few-Shot Learning: Cập nhật biến `_FEW_SHOT_EXAMPLES` trong file `factory/tools/story_factory.py`. Cung cấp cặp ví dụ trực quan `[❌ Viết Dở] vs [✅ Viết Hay]` để AURA bắt chước.

## 3. Kiến Trúc Môi Trường & Dependency (Bẫy chết người)
- **Hệ Điều Hành & Python**: Hệ thống chạy trên Windows, Python 3.14. Các thư viện yêu cầu compile Rust (ví dụ: `orjson`, module proxy của `litellm`) SẼ BỊ LỖI BUILD.
- **Không dùng thư viện litellm**: Tránh cố chấp `pip install litellm`. Hệ thống đã cấu hình dùng trực tiếp Gemini hoặc các API tương thích OpenAI thông qua `brains/cloud_openai_compat.py`.
- **Tránh xung đột Namespace**: Thư mục chứa API Key được đổi tên thành `api_keys/` (file `api_keys/keys.env`). TUYỆT ĐỐI KHÔNG tạo lại thư mục tên `litellm` trong thư mục gốc dự án.

## 4. Quy trình Bàn Giao (Handover)
- **Đọc trước khi làm**: Khi bắt đầu phiên mới, BẮT BUỘC phải đọc file `walkthrough.md` trong thư mục Artifacts của não bộ, và dùng lệnh `git log -n 3` để hiểu agent trước vừa làm gì.
- **Lưu dấu vết trước khi nghỉ**: Khi kết thúc phiên làm việc tạo ra thay đổi lớn, BẮT BUỘC phải thực hiện `git commit` rõ ràng.

---
*Nếu vi phạm các quy tắc này, bạn sẽ phá hỏng công sức của agent đi trước và làm hệ thống phình to vô ích.*
