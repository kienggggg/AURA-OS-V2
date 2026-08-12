"""
xuat_truyen_dang_tay.py
=======================
Gom các bộ TRUYỆN thành phẩm cần ĐĂNG TAY (Wattpad) ra Desktop, kèm hướng dẫn.

Rookies thì AURA đã tự đăng. Đây là bản để đăng THÊM sang Wattpad (khán giả rộng
hơn, cho donate QR — Rookies cấm QR nên bản Rookies không có). Mỗi bộ 1 thư mục:
EPUB + PDF + ảnh bìa + HƯỚNG_DẪN_ĐĂNG.md (form Wattpad điền sẵn).

Chạy:  python xuat_truyen_dang_tay.py
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PROJECT = Path(__file__).resolve().parent
ROOTS = [PROJECT / "data" / "outputs" / "story", PROJECT / "data" / "outputs" / "novel"]
GUIDE_NAME = "HƯỚNG_DẪN_ĐĂNG.md"


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


def _title_of(d: Path) -> str:
    try:
        pk = json.loads((d / "package_info.json").read_text(encoding="utf-8"))
        return str(pk.get("title") or pk.get("series") or d.name)
    except Exception:  # noqa: BLE001
        return d.name


def _ready_stories() -> list[Path]:
    out: list[Path] = []
    for root in ROOTS:
        if not root.is_dir():
            continue
        for d in sorted(root.iterdir()):
            if not d.is_dir() or "test" in d.name.lower():
                continue
            if next(iter(d.glob("*.epub")), None) and (d / GUIDE_NAME).is_file():
                out.append(d)
    return out


def build_story_kit(d: Path, dest_root: Path) -> tuple[str, Path] | None:
    epub = next(iter(d.glob("*.epub")), None)
    if not epub:
        return None
    title = _title_of(d)
    dest = dest_root / d.name
    dest.mkdir(parents=True, exist_ok=True)

    shutil.copy2(epub, dest / f"{d.name}.epub")
    pdf = next(iter(d.glob("*.pdf")), None)
    if pdf:
        shutil.copy2(pdf, dest / f"{d.name}.pdf")

    # Bìa: publish_kit/cover.png -> ANH_BIA.png ngay cạnh hướng dẫn.
    cover = d / "publish_kit" / "cover.png"
    has_cover = cover.is_file()
    if has_cover:
        shutil.copy2(cover, dest / "ANH_BIA.png")
    qr = d / "donate_qr.png"
    if qr.is_file():
        shutil.copy2(qr, dest / "QR_DONATE.png")

    # Hướng dẫn: sửa đường dẫn bìa tuyệt đối -> ./ANH_BIA.png cho khớp bản sao.
    guide = (d / GUIDE_NAME).read_text(encoding="utf-8")
    if has_cover:
        guide = guide.replace(str(cover), "ANH_BIA.png (trong thư mục này)")
    (dest / GUIDE_NAME).write_text(guide, encoding="utf-8")
    return title, dest


def main() -> int:
    stories = _ready_stories()
    if not stories:
        print("❌ Chưa có bộ truyện nào đủ (epub + hướng dẫn).")
        return 1

    dest_root = _desktop() / "AURA_VIEC_DANG_TAY" / "TRUYEN_DANG_TAY"
    dest_root.mkdir(parents=True, exist_ok=True)

    index = ["# 📚 TRUYỆN CẦN ĐĂNG TAY (Wattpad)", "",
             "Rookies AURA đã tự đăng. Đây là bản đăng THÊM sang **Wattpad** để có "
             "thêm người đọc (và được để QR donate — Rookies cấm).", "",
             "Mỗi thư mục có: EPUB, PDF, ảnh bìa, và **HƯỚNG_DẪN_ĐĂNG.md** (điền form "
             "Wattpad theo đó). Wattpad chặn bot nên phải đăng tay — dán từng chương.", ""]
    made = 0
    for d in stories:
        res = build_story_kit(d, dest_root)
        if not res:
            continue
        title, dest = res
        made += 1
        index.append(f"{made}. [ ] **{title}** — mở `{dest.name}/HƯỚNG_DẪN_ĐĂNG.md`")
        print(f"✅ {title}")

    index += ["", "---",
              "⚠️ Wattpad ToS: truyện AI phải khai báo (câu khai đã có sẵn trong "
              "mô tả mỗi bộ). Đồng nhân/fanfic để chế độ phù hợp, không thương mại hoá."]
    (dest_root / "_DANH_SACH_TRUYEN.md").write_text("\n".join(index), encoding="utf-8")

    print(f"\n📦 Đã gom {made} bộ truyện vào: {dest_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
