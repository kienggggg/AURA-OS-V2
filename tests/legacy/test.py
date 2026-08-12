import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.triad_council import convene_sync

print("Đang triệu tập Hội đồng 3 Nhân cách...")
ket_qua = convene_sync([
    {
        "task_id": 101,
        "instruction": """
        Viết một script Python hoàn chỉnh để dọn dẹp thư mục (CHỈ dùng os, shutil).
        Yêu cầu:
        1. Nhận đường dẫn thư mục đầu vào.
        2. Tự tạo các thư mục con: 'Video_CapCut' (.mp4, .mov), 'Tai_Lieu' (.pdf, .docx, .xlsx), 'Rac' (.tmp, .crdownload).
        3. Quét thư mục gốc và DI CHUYỂN (shutil.move) mỗi file vào đúng thư mục con.
           Các file rác (.tmp, .crdownload) cũng CHỈ chuyển vào 'Rac' — KHÔNG xoá cứng,
           để Sếp tự kiểm rồi xoá sau (an toàn, đảo ngược được).
        4. Bọc try-except an toàn, bỏ qua thư mục con đã tạo.
        5. Có docstring rõ ràng.
        """
    }
])
print("\nKết quả từ Hội đồng:")
print(ket_qua)