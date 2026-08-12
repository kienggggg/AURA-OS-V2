"""
core/growth_operator.py
========================
BỘ ĐÓNG GÓI TÀI SẢN DEMO THỰC THẾ AURA GROWTH OPERATOR (§10 - CODEX REVIEW VÒNG 3)
===================================================================================
- Render 3 MP4 video 9:16 thật (540x960 30fps) dùng OpenCV (cv2.VideoCapture mở & đọc được frame thật).
- Viết 7 bài caption hoàn chỉnh (demo_7_captions.md).
- Landing page HTML local thu lead thật (index.html) kèm bộ ghi nhận submissions.jsonl.
- Sinh file manifest.json chứa sha256, kích thước và trạng thái giải mã OpenCV.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from core.config import settings, PROJECT_ROOT

logger = logging.getLogger("aura.growth_operator")
_PACKAGE_DIR = PROJECT_ROOT / "data" / "outputs" / "growth_operator"
_DEMO_DIR = _PACKAGE_DIR / "demo_kit"


def _file_sha256(path: Path) -> str:
    """Tính checksum SHA256 cho 1 file."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def render_real_mp4_video(target_path: Path, title_text: str = "AURA Python Automation Demo") -> Path:
    """Render 1 video MP4 9:16 (540x960, 30fps, 60 frames) thật sự mở và giải mã được qua OpenCV/ffmpeg."""
    target_path.parent.mkdir(parents=True, exist_ok=True)

    # 540x960 vertical 9:16 ratio
    width, height = 540, 960
    fps = 30
    duration_sec = 2
    total_frames = fps * duration_sec

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(str(target_path), fourcc, fps, (width, height))

    if not out.isOpened():
        raise RuntimeError(f"Không thể khởi tạo OpenCV VideoWriter cho file: {target_path}")

    # Render frames gradient xanh đậm & text overlay
    for frame_idx in range(total_frames):
        # Background gradient
        img = np.zeros((height, width, 3), dtype=np.uint8)
        color_val = int(30 + 100 * (frame_idx / total_frames))
        img[:, :] = (color_val, 40, 15)  # BGR gradient

        # Draw header box
        cv2.rectangle(img, (20, 40), (width - 20, 140), (255, 140, 0), -1)
        cv2.putText(img, "AURA DEMO VIDEO 9:16", (30, 95), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2)

        # Draw title text
        cv2.putText(img, title_text[:25], (30, 250), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (200, 255, 200), 2)
        cv2.putText(img, f"Frame {frame_idx + 1}/{total_frames}", (30, 320), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (180, 180, 180), 1)

        # Draw footer badge
        cv2.rectangle(img, (30, height - 100), (width - 30, height - 40), (0, 128, 255), -1)
        cv2.putText(img, "Python Growth Operator", (50, height - 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

        out.write(img)

    out.release()

    # Kiểm tra giải mã lại bằng OpenCV
    cap = cv2.VideoCapture(str(target_path))
    if not cap.isOpened():
        raise RuntimeError(f"Video vừa render không thể mở bằng OpenCV VideoCapture: {target_path}")

    ret, frame = cap.read()
    cap.release()
    if not ret or frame is None:
        raise RuntimeError(f"Video vừa render không đọc được frame từ OpenCV VideoCapture: {target_path}")

    logger.info("Đã render thành công MP4 9:16 giải mã được: %s (Kích thước: %d KB)", target_path.name, target_path.stat().st_size // 1024)
    return target_path


def create_local_landing_page_html(target_path: Path) -> Path:
    """Tạo trang Landing Page HTML chạy local phục vụ thu lead thử nghiệm."""
    target_path.parent.mkdir(parents=True, exist_ok=True)
    html_content = """<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>[DEMO] AURA Python Automation & Growth Services</title>
    <style>
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #0f172a; color: #f8fafc; margin: 0; padding: 20px; }
        .container { max-width: 600px; margin: 0 auto; background: #1e293b; padding: 30px; border-radius: 12px; box-shadow: 0 10px 25px rgba(0,0,0,0.5); }
        h1 { color: #38bdf8; font-size: 24px; text-align: center; }
        p { color: #94a3b8; font-size: 14px; line-height: 1.6; }
        .form-group { margin-bottom: 15px; }
        label { display: block; margin-bottom: 5px; color: #cbd5e1; font-size: 14px; }
        input, select { width: 100%; padding: 10px; border-radius: 6px; border: 1px solid #475569; background: #0f172a; color: #fff; box-sizing: border-box; }
        button { width: 100%; padding: 12px; background: #0284c7; color: white; border: none; border-radius: 6px; font-weight: bold; cursor: pointer; font-size: 16px; margin-top: 10px; }
        button:hover { background: #0369a1; }
        .badge { display: inline-block; background: #ef4444; color: white; padding: 3px 8px; border-radius: 4px; font-size: 12px; font-weight: bold; margin-bottom: 10px; }
    </style>
</head>
<body>
    <div class="container">
        <span class="badge">DEMO INTERACTION ONLY</span>
        <h1>🚀 Gói Vận Hành Tự Động Hóa Python</h1>
        <p>Tự động cào dữ liệu, xuất file Excel & vận hành nội dung đa kênh theo tháng.</p>

        <form action="/api/demo_submit" method="POST">
            <div class="form-group">
                <label for="name">Họ & Tên:</label>
                <input type="text" id="name" name="name" placeholder="Nguyễn Văn A" required>
            </div>
            <div class="form-group">
                <label for="phone">Số điện thoại / Zalo:</label>
                <input type="text" id="phone" name="phone" placeholder="0912345678" required>
            </div>
            <div class="form-group">
                <label for="niche">Nhu cầu tự động hóa:</label>
                <select id="niche" name="niche">
                    <option value="crawl">Cào dữ liệu sản phẩm Shopee/Lazada</option>
                    <option value="content">Tự động dựng video & xuất bản mạng xã hội</option>
                    <option value="bot">Cầu nối báo có cục bộ sang Telegram</option>
                </select>
            </div>
            <button type="submit">Đăng Ký Tư Vấn Thử Nghệ (Gói 7 Ngày)</button>
        </form>
    </div>
</body>
</html>
"""
    target_path.write_text(html_content, encoding="utf-8")
    return target_path


def record_demo_submission(data: dict[str, Any], submissions_file: Path | None = None) -> dict[str, Any]:
    """Ghi nhận dữ liệu đăng ký thử nghiệm từ form Landing Page."""
    p = submissions_file or (_DEMO_DIR / "submissions.jsonl")
    p.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": int(time.time()),
        "name": str(data.get("name") or "").strip(),
        "phone": str(data.get("phone") or "").strip(),
        "niche": str(data.get("niche") or "crawl").strip(),
        "is_demo": True,
    }
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def handle_demo_submit_request(payload: dict[str, Any], submissions_file: Path | None = None) -> dict[str, Any]:
    """Route handler xử lý HTTP POST /api/demo_submit cho form landing page."""
    name = str(payload.get("name") or "").strip()
    phone = str(payload.get("phone") or "").strip()

    if len(name) < 2 or len(name) > 100:
        return {"success": False, "error": "Họ tên phải có từ 2 đến 100 ký tự."}
    normalized_phone = re.sub(r"[\s().-]", "", phone)
    if not re.fullmatch(r"\+?\d{8,15}", normalized_phone):
        return {"success": False, "error": "Số điện thoại phải có từ 8 đến 15 chữ số."}
    payload = dict(payload)
    payload["name"] = name
    payload["phone"] = normalized_phone

    entry = record_demo_submission(payload, submissions_file=submissions_file)
    return {
        "success": True,
        "message": "Đã ghi nhận đăng ký tư vấn thử nghiệm thành công!",
        "entry": entry,
    }


def create_demo_7_captions(target_path: Path) -> Path:
    """Tạo đủ 7 bài caption hoàn chỉnh phục vụ tự động hóa nội dung."""
    content = """# ✍️ 7 BÀI CAPTION DEMO NỘI BỘ (PYTHON AUTOMATION)

---

## 📌 Bài 1: Tự động cào dữ liệu giá Shopee/Lazada bằng Python
Bạn mệt mỏi vì phải nhấp tay copy giá đối thủ từng trang?
AURA có thể thiết kế script Python thu thập dữ liệu công khai và xuất Excel theo phạm vi đã thống nhất.
👉 Gửi một URL mẫu để AURA đánh giá tính khả thi và chuẩn bị bản demo cục bộ!
#PythonAutomation #WebScraping #ExcelData

---

## 📌 Bài 2: Tự động dựng video ngắn 9:16 hàng loạt
[DEMO] AURA đang thử quy trình tạo video dọc bằng OpenCV từ tư liệu do khách cung cấp.
Số lượng, thời gian dựng và chất lượng đầu ra chỉ được chốt sau khi xem tư liệu thực tế.
👉 Đăng ký trao đổi phạm vi gói thử 7 ngày; chưa có cam kết kết quả khi chưa khảo sát!
#ContentAutomation #Shorts #Reels

---

## 📌 Bài 3: Cầu nối báo có cục bộ qua Telegram
Sếp không cần mở app ngân hàng mỗi lần cần xem báo có!
AURA có cầu nối Android cục bộ để chuyển thông báo báo có sang Telegram; hệ thống không đăng nhập ngân hàng và không tự xác nhận doanh thu.
👉 Liên hệ để xem bản demo quy trình đối soát có bước xác nhận của chủ tài khoản!
#TelegramBot #Automation #Finance

---

## 📌 Bài 4: Tự động hóa đăng bài đa kênh Facebook & TikTok
Viết bài 1 lần - Xuất bản 5 nền tảng!
Script Python hỗ trợ đưa bài viết vào Bàn đăng tay (Manual Publish Desk) an toàn, không lo bị khóa tài khoản.
👉 Trải nghiệm ngay quy trình làm việc 99% tự động!
#SocialMediaAutomation #Marketing

---

## 📌 Bài 5: Tự động quét Lead ứng tuyển công khai trên Upwork & TopCV
Không bỏ lỡ bất kỳ cơ hội dự án ngon nào!
Bộ lọc Python RSS chỉ giữ các tin công khai có URL và dấu hiệu phù hợp, sau đó đưa vào hộp duyệt cục bộ.
👉 Xem bản demo và tự kiểm tra nguồn trước khi liên hệ!
#FreelanceLead #Upwork #Automation

---

## 📌 Bài 6: Tự động chuyển đổi tài liệu PDF thành Ebook đẹp mắt
AURA có thể dựng thử checklist hoặc ebook bằng Python từ nội dung và quyền sử dụng do khách cung cấp.
Phạm vi, bản quyền và thời gian giao được xác nhận trước khi bắt đầu.
👉 Inbox để xem bộ mẫu demo do AURA tự tạo!
#DigitalProducts #Payhip #PdfAutomation

---

## 📌 Bài 7: Tổng kết gói thử nghiệm 7 ngày AURA Growth Operator
Gói demo tham khảo 7 ngày, giá chỉ được chốt sau khi thống nhất phạm vi:
- 3 Video MP4 9:16 chuẩn sắc nét
- 7 Caption phong phú đa kênh
- Trang Landing Page chạy trên dashboard AURA khi máy chủ cục bộ đang bật
👉 Nhấp link để gửi đăng ký demo; đây chưa phải cam kết doanh thu!
#AURAOS #GrowthOperator #PythonServices
"""
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(content, encoding="utf-8")
    return target_path


def execute_m8_package() -> dict[str, Any]:
    """Thực thi đóng gói trọn bộ M8 AURA Growth Operator (Render 3 MP4 thật + 7 Captions + Form + Manifest)."""
    _DEMO_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Render 3 Video MP4 9:16 thật
    v1 = render_real_mp4_video(_DEMO_DIR / "demo_video_1.mp4", "Demo 1: Python Scraper")
    v2 = render_real_mp4_video(_DEMO_DIR / "demo_video_2.mp4", "Demo 2: Video Render")
    v3 = render_real_mp4_video(_DEMO_DIR / "demo_video_3.mp4", "Demo 3: Telegram Bot")

    # 2. Captions & HTML
    captions_file = create_demo_7_captions(_DEMO_DIR / "demo_7_captions.md")
    html_file = create_local_landing_page_html(_DEMO_DIR / "index.html")

    artifacts = [v1, v2, v3, captions_file, html_file]

    manifest_data = {
        "package_name": "AURA Growth Operator - Python Automation",
        "active_niche": "python_automation",
        "created_at": int(time.time()),
        "status": "LOCAL_DEMO_READY_NOT_CLIENT_DELIVERY",
        "video_count": 3,
        "caption_count": 7,
        "artifacts": []
    }

    for art in artifacts:
        if not art.is_file():
            continue

        decodable = None
        if art.suffix == ".mp4":
            cap = cv2.VideoCapture(str(art))
            decodable = cap.isOpened()
            cap.release()

        manifest_data["artifacts"].append({
            "filename": art.name,
            "path": str(art),
            "size_bytes": art.stat().st_size,
            "sha256": _file_sha256(art),
            "type": "video" if art.suffix == ".mp4" else ("html" if art.suffix == ".html" else "data"),
            "video_decodable": decodable,
        })

    manifest_path = _DEMO_DIR / "manifest.json"
    manifest_path.write_text(json.dumps(manifest_data, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "success": True,
        "manifest": str(manifest_path),
        "video_count": 3,
        "caption_count": 7,
    }
