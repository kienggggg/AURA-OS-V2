"""
skills/video-download/scripts/download.py
Tool do AURA tự sinh (Triad Council task #52385, Sếp duyệt) — tải video/file từ URL.
Gia cố sau duyệt: timeout tường minh + đường dẫn neo gốc dự án + validate scheme.
Hợp đồng: tool_download_video(**params) -> ToolResult.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Cho phép `from core...` chạy dù file được nạp qua importlib (chèn project root).
_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import os

import requests

from core.schemas import ToolResult

_DOWNLOADS_DIR = _ROOT / "data" / "downloads"


def tool_download_video(**params) -> ToolResult:
    try:
        url = params.get("url")
        if not url:
            return ToolResult.failure("video.download", "URL không được để trống")
        if not isinstance(url, str) or not url.lower().startswith(("http://", "https://")):
            return ToolResult.failure("video.download", "URL phải bắt đầu bằng http:// hoặc https://")

        # Đường dẫn: neo vào gốc dự án (không phụ thuộc CWD) — vá lỗ Council bỏ lọt.
        out = params.get("output_path")
        if out:
            output_path = Path(out)
            if not output_path.is_absolute():
                output_path = _ROOT / output_path
        else:
            name = Path(url.split("?")[0]).name or "video.mp4"
            output_path = _DOWNLOADS_DIR / name

        # Kiểm RAM khả dụng trước khi tải (ý tưởng gốc của Council — giữ nguyên).
        try:
            import psutil
            if psutil.virtual_memory().available < 500 * 1024 * 1024:
                return ToolResult.failure(
                    "video.download", "RAM không đủ để tải video, cần ít nhất 500MB RAM trống")
        except ImportError:
            pass  # thiếu psutil -> bỏ kiểm, vẫn tải

        output_path.parent.mkdir(parents=True, exist_ok=True)

        # timeout TƯỜNG MINH (connect 10s, read 60s) — vá lỗ Council bỏ lọt: không có
        # nó, server không phản hồi làm tool đơ VÔ HẠN (đúng họ lỗi từng treo Council).
        response = requests.get(url, stream=True, timeout=(10, 60))
        response.raise_for_status()
        total = 0
        with open(output_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    total += len(chunk)

        return ToolResult.success(
            "video.download", f"Đã tải {total:,} bytes về: {output_path}")
    except requests.Timeout:
        return ToolResult.failure("video.download", "Server không phản hồi kịp (timeout).")
    except Exception as exc:  # noqa: BLE001 — hợp đồng: không bao giờ raise
        return ToolResult.failure("video.download", str(exc))
