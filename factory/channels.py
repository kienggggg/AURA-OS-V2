"""
factory/channels.py
====================
SỔ KÊNH — mỗi kênh là một "thương hiệu" riêng: một NGÁCH, trên một NỀN TẢNG, chỉ
ăn một LOẠI nội dung, giọng điệu riêng, token đăng riêng.

Đây là mảnh khớp cả xưởng lại: các tool SẢN XUẤT (video.factory, comic.create,
story.factory...) làm ra sản phẩm; sổ kênh quyết định sản phẩm nào chảy về kênh
nào. AURA quản nhiều kênh song song, mỗi kênh tự nuôi bằng đúng loại nội dung.

Ví dụ user (2026-07-06): kênh hài, kênh khoa học, kênh "phim từ truyện" — 3 ngách
khác nhau, mỗi kênh một dòng nội dung riêng.

Dữ liệu ở data/channels.json (user sửa được tay hoặc qua dashboard). Không chứa
bí mật — token thật nằm ở data/youtube/<yt_channel>/token.json (đã gitignore).
"""

from __future__ import annotations

import json
from pathlib import Path

from core.config import PROJECT_ROOT

_PATH = PROJECT_ROOT / "data" / "channels.json"

# Loại nội dung một kênh có thể nhận (khớp product_line của tool sản xuất).
CONTENT_TYPES = ("video", "comic", "novel", "content")
PLATFORMS = ("wattpad", "webtoon", "youtube", "tiktok", "facebook", "shop_pdf", "khac")

# Mẫu khởi tạo — chốt 2026-07-06: 1 GMAIL, 1 bút danh Wattpad đăng NHIỀU BỘ khác
# thể loại (tu tiên gốc, đồng nhân... mỗi bộ 1 "series" riêng trong story.factory).
# Truyện tranh để GIAI ĐOẠN 2 (ảnh AI nhạy cảm với cộng đồng họa sĩ + Webtoon siết).
# Donate = QR VietQR (MB Bank) AURA tự chèn cuối mỗi chương.
# Thương hiệu chốt 2026-07-09: bút danh "Dạ Vân", tên kênh nhồi TỪ KHOÁ để dễ tìm.
_SEED = [
    {
        "key": "wattpad-truyen",
        "name": "Truyện Tu Tiên Đồng Nhân - Dạ Vân",
        "platform": "wattpad",
        "gmail": "chung",
        "niche": "Mọi bộ truyện chữ tự sáng tác — tu tiên gốc, đồng nhân... (mỗi bộ 1 series)",
        "content_types": ["novel"],
        "style": "Giọng kể cuốn hút theo từng bộ; giữ nhất quán bằng bible + trí nhớ chương.",
        "yt_channel": "wattpad-truyen",
        "enabled": True,
    },
    {
        "key": "youtube-kechuyen",
        "name": "Kể Chuyện Tu Tiên Mỗi Đêm",
        "platform": "youtube",
        "gmail": "chung",
        "niche": "Video kể chuyện tu tiên/đồng nhân (chuyển thể từ truyện chữ Dạ Vân)",
        "content_types": ["video"],
        "style": "Giọng đọc truyền cảm, ảnh minh hoạ điện ảnh, cuốn theo từng chương.",
        "yt_channel": "youtube-kechuyen",
        "enabled": True,
    },
    {
        "key": "truyen-tranh",
        "name": "Truyện Tranh (giai đoạn 2)",
        "platform": "webtoon",
        "gmail": "chung",
        "niche": "Chuyển thể truyện chữ đã chạy ổn thành truyện tranh — LÀM SAU",
        "content_types": ["comic"],
        "style": "Phân cảnh rõ, thoại ngắn, khung dọc kiểu webtoon.",
        "yt_channel": "truyen-tranh",
        "enabled": False,
    },
]


def _load_raw() -> list[dict]:
    if _PATH.exists():
        try:
            data = json.loads(_PATH.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return data
        except (json.JSONDecodeError, OSError):
            pass
    return []


def ensure_seeded() -> None:
    """Lần đầu chưa có file -> ghi mẫu 3 kênh để user sửa."""
    if not _PATH.exists():
        _PATH.parent.mkdir(parents=True, exist_ok=True)
        _PATH.write_text(json.dumps(_SEED, ensure_ascii=False, indent=2), encoding="utf-8")


def all_channels(only_enabled: bool = False) -> list[dict]:
    ensure_seeded()
    chans = _load_raw()
    return [c for c in chans if c.get("enabled", True)] if only_enabled else chans


def get(key: str) -> dict | None:
    for c in all_channels():
        if c.get("key") == key:
            return c
    return None


def for_content(content_type: str, platform: str | None = None) -> list[dict]:
    """Các kênh (đang bật) nhận loại nội dung này — để tool sản xuất biết đăng đâu."""
    out = []
    for c in all_channels(only_enabled=True):
        if content_type in (c.get("content_types") or []):
            if platform is None or c.get("platform") == platform:
                out.append(c)
    return out


def upsert(channel: dict) -> dict:
    """Thêm/sửa 1 kênh theo 'key'. Trả bản ghi đã lưu."""
    key = str(channel.get("key") or "").strip()
    if not key:
        raise ValueError("Kênh phải có 'key'.")
    chans = _load_raw() or _SEED.copy()
    for i, c in enumerate(chans):
        if c.get("key") == key:
            chans[i] = {**c, **channel}
            break
    else:
        chans.append(channel)
    _PATH.parent.mkdir(parents=True, exist_ok=True)
    _PATH.write_text(json.dumps(chans, ensure_ascii=False, indent=2), encoding="utf-8")
    return get(key) or channel


__all__ = ["all_channels", "get", "for_content", "upsert", "ensure_seeded",
           "CONTENT_TYPES", "PLATFORMS"]
