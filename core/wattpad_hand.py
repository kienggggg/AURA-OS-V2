"""
core/wattpad_hand.py
====================
"TAY" đăng Wattpad của AURA — bản TRỢ GIÚP (assisted), KHÔNG tự-động-lén.

Vì sao không automation: Wattpad CHỦ ĐỘNG chặn trình duyệt tự động (bẫy
`debugger`, thả phiên login, chặn IP). Đánh nhau với lớp chống-bot đó vừa GIÒN
vừa RỦI RO KHOÁ TÀI KHOẢN (vi phạm ToS). Nên AURA làm 90% (chuẩn bị sẵn nội
dung) rồi để Sếp bấm nút đăng — an toàn, ổn định.

Luồng:
- Đọc chương `ch_NNNN.md` -> chép NGUYÊN THÂN BÀI vào clipboard.
- Mở Wattpad (trang myworks) ở TRÌNH DUYỆT THẬT của Sếp (đã đăng nhập sẵn).
- In/nhắn: tiêu đề chương + nhắc dán (Ctrl+V) + đăng.

Sếp chỉ việc: vào truyện -> Chương mới -> dán -> đăng (~20 giây).

Dùng:
    venv/Scripts/python.exe -m core.wattpad_hand --series "Tên_Bộ" --chapter 8
Hoặc gọi qua Telegram lệnh /dangwp (xem core/messenger.py).
"""

from __future__ import annotations

import argparse
import logging
import re
import subprocess
import sys
import tempfile
import webbrowser
from pathlib import Path

from core.config import settings

logger = logging.getLogger(__name__)

WATTPAD_MYWORKS = "https://www.wattpad.com/myworks/"


# --------------------------------------------------------------------------- #
# Đọc + làm sạch chương .md -> (tiêu đề, thân bài dạng text)
# --------------------------------------------------------------------------- #
def parse_chapter(path: Path) -> tuple[str, list[str]]:
    """Tách ch_NNNN.md -> (tiêu đề, [đoạn văn]). Bỏ '#' tiêu đề, gỡ nhẹ markdown."""
    raw = path.read_text(encoding="utf-8")
    lines = raw.splitlines()
    title = ""
    body_start = 0
    for i, ln in enumerate(lines):
        if ln.strip().startswith("#"):
            title = ln.lstrip("#").strip()
            body_start = i + 1
            break
    body = "\n".join(lines[body_start:]).strip()
    body = re.sub(r"\*{1,3}(.+?)\*{1,3}", r"\1", body, flags=re.S)
    body = body.replace("*", "")
    paras = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]
    return title or path.stem, paras


def _find_chapter(series: str, chapter: int) -> Path:
    p = settings.outputs_dir / "story" / series / "chapters" / f"ch_{chapter:04d}.md"
    if not p.is_file():
        raise FileNotFoundError(f"Không thấy chương: {p}")
    return p


def latest_chapter(series: str) -> int:
    """Số chương lớn nhất đã viết của bộ (0 nếu chưa có chương nào)."""
    d = settings.outputs_dir / "story" / series / "chapters"
    if not d.is_dir():
        return 0
    nums = [int(m.group(1)) for f in d.glob("ch_*.md")
            if (m := re.match(r"ch_(\d+)\.md$", f.name))]
    return max(nums) if nums else 0


# --------------------------------------------------------------------------- #
# Clipboard (Windows, Unicode-safe qua PowerShell Set-Clipboard)
# --------------------------------------------------------------------------- #
def copy_to_clipboard(text: str) -> bool:
    """Chép text vào clipboard. Trả True nếu thành công."""
    # Ưu tiên pyperclip nếu có (đa nền tảng).
    try:
        import pyperclip  # type: ignore
        pyperclip.copy(text)
        return True
    except Exception:  # noqa: BLE001
        pass
    # Windows: ghi file tạm UTF-8 rồi Set-Clipboard (giữ nguyên tiếng Việt).
    try:
        with tempfile.NamedTemporaryFile(
            "w", suffix=".txt", delete=False, encoding="utf-8"
        ) as f:
            f.write(text)
            tmp = f.name
        subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             f"Set-Clipboard -Value (Get-Content -Raw -Encoding UTF8 '{tmp}')"],
            check=True, capture_output=True, timeout=20,
        )
        Path(tmp).unlink(missing_ok=True)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("Chép clipboard lỗi: %s", exc)
        return False


# --------------------------------------------------------------------------- #
def assist_post(series: str, chapter: int, open_browser: bool = True) -> str:
    """Chuẩn bị đăng: chép chương vào clipboard + mở Wattpad. Trả tin nhắn cho Sếp."""
    # LUẬT NỀN TẢNG trước tiên — không đăng nếu nền cấm nội dung AI.
    from factory.platform_rules import can_post, disclosure_for
    allowed, why = can_post("wattpad")
    if not allowed:
        return f"⛔ KHÔNG đăng được: {why}"

    ch_path = _find_chapter(series, chapter)
    title, paras = parse_chapter(ch_path)
    body = "\n\n".join(paras)
    # Wattpad ToS 5.3: PHẢI khai báo AI ở mô tả truyện + ghi chú tác giả chương đầu.
    disclosure = disclosure_for("wattpad")
    if disclosure and chapter <= 1:
        body = f"{body}\n\n———\n{disclosure}"
    ok = copy_to_clipboard(body)

    cover = settings.outputs_dir / "story" / series / "publish_kit" / "cover.png"
    if open_browser:
        try:
            webbrowser.open(WATTPAD_MYWORKS)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Mở trình duyệt lỗi: %s", exc)

    lines = [
        f"📤 SẴN SÀNG ĐĂNG — {title}",
        "",
        ("✅ Đã chép NGUYÊN chương vào clipboard." if ok
         else "⚠️ Chép clipboard KHÔNG được — mở file chương copy tay:"),
    ]
    if not ok:
        lines.append(f"   {ch_path}")
    lines += [
        f"📊 {len(paras)} đoạn, ~{len(body)} ký tự.",
        "",
        "Trên Wattpad (đã mở ở trình duyệt): vào truyện → 'Phần mới' →",
        f"  • Tiêu đề: {title}",
        "  • Nội dung: bấm vào ô soạn thảo, Ctrl+V (dán), rồi Đăng.",
    ]
    if cover.is_file():
        lines.append("🖼️ (Bìa/văn án/tags — nếu là truyện MỚI — xem publish_kit/ + HƯỚNG_DẪN_ĐĂNG.md)")
    if disclosure:
        lines += [
            "",
            "⚖️ BẮT BUỘC theo ToS Wattpad (mục 5.3) — nếu không sẽ bị gỡ truyện/khoá acc:",
            f"   Dán câu này vào Ô MÔ TẢ TRUYỆN: “{disclosure}”",
        ]
        if chapter <= 1:
            lines.append("   (Đã tự chèn sẵn câu này ở cuối chương 1 trong clipboard.)")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Tay đăng Wattpad (trợ giúp) của AURA")
    ap.add_argument("--series", required=True, help="Tên thư mục bộ truyện")
    ap.add_argument("--chapter", type=int, required=True, help="Số chương (vd 8)")
    ap.add_argument("--no-open", action="store_true", help="Không tự mở trình duyệt")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO)
    print(assist_post(args.series, args.chapter, open_browser=not args.no_open))
    return 0


if __name__ == "__main__":
    sys.exit(main())
