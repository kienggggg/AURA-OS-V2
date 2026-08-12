"""
core/manual_publish_query.py
============================
Trả lời câu "những thứ cần đăng tay ở đâu / đường dẫn Wattpad, TikTok, Payhip..."
bằng DỮ LIỆU THẬT (thư mục Desktop AURA đã xuất + Manual Publish Desk), KHÔNG để
LLM đoán bừa. Sửa đúng lỗi Sếp gặp: mascot nghe 'Wattpad' -> bịa 'WhatsApp'.

Cùng nguyên tắc "không biết thì nói, đừng đoán" như mắt màn hình
(xem [[aura-wattpad-hand]]).
"""

from __future__ import annotations

import unicodedata
from pathlib import Path


def _norm(text: str) -> str:
    folded = unicodedata.normalize("NFKD", str(text or "").casefold()).replace("đ", "d")
    return " ".join("".join(c for c in folded if not unicodedata.combining(c)).split())


def is_manual_publish_question(text: str) -> bool:
    """True khi Sếp hỏi 'cần đăng tay gì / file/đường dẫn ở đâu'. Không bắt 'đăng
    nhập'/'đăng ký'."""
    n = _norm(text)
    if "dang nhap" in n or "dang ky" in n:
        return False
    platforms = ("wattpad", "tiktok", "payhip", "reels", "short", "youtube")
    intent = ("dang tay", "can dang", "thu can dang", "gi can dang", "viec dang",
              "duong dan", "o dau", "thanh pham", "dang o dau", "dang truyen",
              "dang video", "dang sach", "dang bai", "file")
    has_platform = any(p in n for p in platforms)
    has_intent = any(t in n for t in intent)
    # Cần có ý ĐĂNG/đường dẫn; platform một mình chưa đủ (tránh bắt nhầm chat thường).
    return has_intent and ("dang" in n or "duong dan" in n or "o dau" in n or has_platform)


def _desktop() -> Path:
    try:
        import ctypes
        from ctypes import windll, wintypes  # type: ignore
        buf = ctypes.create_unicode_buffer(wintypes.MAX_PATH)
        if windll.shell32.SHGetFolderPathW(0, 0x10, 0, 0, buf) == 0 and buf.value:
            return Path(buf.value)
    except Exception:  # noqa: BLE001
        pass
    one = Path.home() / "OneDrive" / "Desktop"
    return one if one.is_dir() else Path.home() / "Desktop"


def _count_dirs(p: Path) -> int:
    return sum(1 for d in p.iterdir() if d.is_dir()) if p.is_dir() else 0


def answer_manual_publish() -> str:
    """Bản kê THẬT các thứ cần đăng tay + đường dẫn Desktop. Chỉ liệt kê thứ CÓ
    THẬT trên đĩa; không có thì nói chưa xuất, không bịa."""
    desk = _desktop()
    viec = desk / "AURA_VIEC_DANG_TAY"
    lines = ["📋 VIỆC ĐĂNG TAY (AURA kê từ file thật, không đoán):", ""]
    found = False

    truyen = viec / "TRUYEN_DANG_TAY"
    if truyen.is_dir():
        n = _count_dirs(truyen)
        lines += [f"📚 TRUYỆN (Wattpad) — {n} bộ",
                  f"   {truyen}", "   → mở _DANH_SACH_TRUYEN.md", ""]
        found = True

    payhip = viec / "PAYHIP_BAN_SACH"
    if payhip.is_dir():
        lines += [f"🎨 SÁCH TÔ MÀU (Payhip) — {_count_dirs(payhip)} cuốn",
                  f"   {payhip}", ""]
        found = True

    video = desk / "AURA_VIDEO_TIKTOK"
    if video.is_dir():
        lines += [f"🎬 VIDEO SHORT (TikTok/Reels) — {_count_dirs(video)} cái",
                  f"   {video}", ""]
        found = True

    # YouTube: đọc từ Manual Publish Desk (số thật).
    try:
        from core.manual_publish_desk import list_items
        yt = [i for i in list_items() if str(i.get("platform")) == "YouTube"]
        if yt:
            lines += [f"📺 YOUTUBE — {len(yt)} video chờ bật Công khai",
                      "   (Studio: đổi Riêng tư → Công khai; xem DANH_SACH_DANG_TAY.md)", ""]
            found = True
    except Exception:  # noqa: BLE001
        pass

    if not found:
        return ("Chưa thấy thư mục việc-đăng-tay nào trên Desktop. Bảo tôi chạy "
                "'xuất việc đăng tay' để gom lại nhé — tôi không đoán bừa đường dẫn.")

    lines.append("Mở đúng thư mục trên Desktop là thấy, không cần hỏi lại.")
    return "\n".join(lines)


__all__ = ["is_manual_publish_question", "answer_manual_publish"]
