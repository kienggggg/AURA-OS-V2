"""
core/publish_hand.py
====================
TAY ĐĂNG TRUYỆN ĐA NỀN (bản TRỢ GIÚP) — một cửa cho mọi nền tảng.

Luồng chung: kiểm LUẬT NỀN (factory/platform_rules) -> đọc chương -> áp ràng
buộc của nền (khai báo AI, bỏ QR donate...) -> chép vào clipboard -> mở đúng
trang viết ở TRÌNH DUYỆT THẬT -> trả hướng dẫn ngắn cho Sếp dán + đăng.

Vì sao KHÔNG tự động hoàn toàn: Wattpad chặn bot bằng bẫy `debugger`; và tự
động đăng ồ ạt dễ bị khoá tài khoản. Trợ giúp = AURA lo 90%, Sếp bấm 2 nút.

Dùng:
    venv/Scripts/python.exe -m core.publish_hand --platform rookies --series "Tên_Bộ"
    venv/Scripts/python.exe -m core.publish_hand --platform wattpad --series "Tên_Bộ" --chapter 7
"""

from __future__ import annotations

import argparse
import logging
import sys
import webbrowser

from core.config import settings
from core.wattpad_hand import (
    parse_chapter, latest_chapter, _find_chapter, copy_to_clipboard,
)
from factory.platform_rules import can_post, disclosure_for, allows_donate_qr, get as get_rule

logger = logging.getLogger(__name__)

# Trang đích của từng nền: 'chapter' = nơi thêm chương cho truyện đã có,
# 'new' = nơi tạo truyện mới (None nếu nền không có trang riêng).
TARGETS: dict[str, dict[str, str | None]] = {
    "wattpad": {
        "chapter": "https://www.wattpad.com/myworks/",
        "new": "https://www.wattpad.com/myworks/",
    },
    "rookies": {
        "chapter": "https://rookies.vn/studio",
        "new": "https://rookies.vn/author/tao-truyen",
    },
}


def _read_kit(series: str) -> tuple[dict, str]:
    """Đọc bộ đồ nghề đăng: (kit_info, văn án thuần văn xuôi)."""
    import json
    kit_dir = settings.outputs_dir / "story" / series / "publish_kit"
    info: dict = {}
    p = kit_dir / "kit_info.json"
    if p.is_file():
        try:
            info = json.loads(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            info = {}
    blurb = ""
    va = kit_dir / "van_an.md"
    if va.is_file():
        raw = va.read_text(encoding="utf-8")
        keep = []
        for ln in raw.splitlines():
            s = ln.strip()
            if not s:
                continue
            # Bỏ dòng tiêu đề/tác giả/thể loại (Rookies có ô riêng cho chúng).
            if s.startswith("#") or s.startswith("*Tác giả") or s.startswith("**Thể loại"):
                continue
            keep.append(s)
        blurb = "\n\n".join(keep)
    return info, blurb


def assist_new_story(platform: str, series: str, open_browser: bool = True) -> str:
    """TẠO TRUYỆN MỚI trên nền: chép VĂN ÁN vào clipboard + mở trang tạo truyện."""
    platform = (platform or "").strip().lower()
    allowed, why = can_post(platform)
    if not allowed:
        return f"⛔ KHÔNG tạo truyện trên {platform}: {why}"
    target = TARGETS.get(platform)
    if target is None:
        return f"⚠️ Chưa cấu hình trang đích cho nền '{platform}'."

    info, blurb = _read_kit(series)
    if not blurb:
        return (f"⚠️ Bộ '{series}' chưa có văn án (publish_kit/van_an.md). "
                "Chờ AURA dựng story.kit rồi thử lại.")

    # Wattpad ToS: khai báo AI PHẢI nằm trong MÔ TẢ truyện -> chèn thẳng vào văn án.
    disclosure = disclosure_for(platform)
    if disclosure:
        blurb = f"{blurb}\n\n{disclosure}"
    ok = copy_to_clipboard(blurb)

    url = target["new"] or target["chapter"]
    if open_browser and url:
        try:
            webbrowser.open(url)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Mở trình duyệt lỗi: %s", exc)

    rule = get_rule(platform)
    tags = info.get("tags") or []
    lines = [
        f"🆕 TẠO TRUYỆN MỚI trên {rule.name if rule else platform}",
        "",
        ("✅ Đã chép VĂN ÁN (mô tả truyện) vào clipboard."
         if ok else "⚠️ Chép clipboard lỗi — mở publish_kit/van_an.md copy tay."),
        f"🌐 Đã mở: {url}",
        "",
        "Điền vào form theo đúng các ô:",
        f"  • Tên truyện: {info.get('title', series)}",
        f"  • Bút danh/Tác giả: {info.get('pen_name', '(để trống)')}",
        f"  • Thể loại: {info.get('genre', '(tự chọn)')}",
        f"  • Mô tả/Giới thiệu: Ctrl+V (đã có sẵn trong clipboard)",
        f"  • Tags: {' '.join('#' + t for t in tags) if tags else '(không có)'}",
        f"  • Ảnh bìa: {info.get('cover', '(chưa có)')}",
    ]
    if disclosure:
        lines += ["", f"⚖️ Đã tự chèn khai báo AI vào cuối mô tả (bắt buộc theo ToS)."]
    if not allows_donate_qr(platform):
        lines += ["", f"🚫 Nền này CẤM donate ngoài hệ thống — đừng để QR ngân hàng vào mô tả."]
    lines += ["", "Tạo xong truyện rồi thì đăng từng chương bằng lệnh đăng chương."]
    return "\n".join(lines)


def assist(platform: str, series: str, chapter: int | None = None,
           new_story: bool = False, open_browser: bool = True) -> str:
    """Chuẩn bị đăng 1 chương lên `platform`. Trả tin nhắn hướng dẫn cho Sếp."""
    platform = (platform or "").strip().lower()

    # 1) LUẬT NỀN trước tiên — chặn nếu nền cấm nội dung AI / chưa rà quy định.
    allowed, why = can_post(platform)
    if not allowed:
        return f"⛔ KHÔNG đăng lên {platform}: {why}"
    rule = get_rule(platform)
    target = TARGETS.get(platform)
    if target is None:
        return f"⚠️ Chưa cấu hình trang đích cho nền '{platform}'."

    # 2) Đọc chương.
    ch = chapter or latest_chapter(series)
    if ch < 1:
        return f"📭 Bộ '{series}' chưa có chương nào."
    ch_path = _find_chapter(series, ch)
    title, paras = parse_chapter(ch_path)
    body = "\n\n".join(paras)

    # 3) Áp ràng buộc của nền.
    disclosure = disclosure_for(platform)
    if disclosure and ch <= 1:
        body = f"{body}\n\n———\n{disclosure}"

    ok = copy_to_clipboard(body)

    # 4) Mở đúng trang ở TRÌNH DUYỆT THẬT của Sếp.
    url = target["new"] if new_story else target["chapter"]
    if open_browser and url:
        try:
            webbrowser.open(url)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Mở trình duyệt lỗi: %s", exc)

    # 5) Soạn hướng dẫn.
    name = rule.name if rule else platform
    lines = [
        f"📤 SẴN SÀNG ĐĂNG lên {name} — {title}",
        "",
        ("✅ Đã chép NGUYÊN chương vào clipboard."
         if ok else f"⚠️ Chép clipboard lỗi — mở file copy tay:\n   {ch_path}"),
        f"📊 {len(paras)} đoạn, ~{len(body)} ký tự.",
        "",
        f"🌐 Đã mở: {url}",
        f"  • Tiêu đề chương: {title}",
        "  • Bấm vào ô soạn thảo → Ctrl+V (dán) → Đăng.",
    ]

    # Cảnh báo riêng theo luật từng nền.
    if disclosure:
        lines += [
            "",
            "⚖️ BẮT BUỘC (ToS) — không làm sẽ bị gỡ truyện/khoá tài khoản:",
            f"   Dán câu này vào Ô MÔ TẢ TRUYỆN: “{disclosure}”",
        ]
        if ch <= 1:
            lines.append("   (Đã tự chèn sẵn ở cuối chương 1 trong clipboard.)")
    if not allows_donate_qr(platform):
        lines += [
            "",
            f"🚫 {name} CẤM kêu gọi donate ngoài hệ thống → ĐỪNG chèn QR ngân hàng "
            "vào chương. Kiếm tiền bằng chức năng khoá chương/donate của chính nền.",
        ]
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Tay đăng truyện đa nền (trợ giúp)")
    ap.add_argument("--platform", required=True, help="wattpad | rookies")
    ap.add_argument("--series", required=True, help="Tên thư mục bộ truyện")
    ap.add_argument("--chapter", type=int, help="Số chương (bỏ trống = mới nhất)")
    ap.add_argument("--new", action="store_true",
                    help="TẠO TRUYỆN MỚI (chép văn án + mở trang tạo truyện)")
    ap.add_argument("--no-open", action="store_true", help="Không mở trình duyệt")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO)
    if args.new:
        print(assist_new_story(args.platform, args.series,
                               open_browser=not args.no_open))
    else:
        print(assist(args.platform, args.series, args.chapter,
                     open_browser=not args.no_open))
    return 0


if __name__ == "__main__":
    sys.exit(main())
