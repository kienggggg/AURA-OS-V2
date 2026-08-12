"""
xuat_viec_dang_tay.py
=====================
Gom MỌI thứ Sếp cần ĐĂNG TAY ra một thư mục trên Desktop (dễ tìm, không phải lục
trong D:\\AURA_OS_v2). Gồm:
  - Bộ dán sẵn Payhip (VIEC_CUA_SEP) — mỗi sách 1 thư mục: PDF + bìa + bản dán.
  - Checklist toàn bộ việc đăng tay từ Manual Publish Desk (YouTube, Payhip...).

Chạy:  python xuat_viec_dang_tay.py
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PROJECT = Path(__file__).resolve().parent
SRC_VIEC = PROJECT / "VIEC_CUA_SEP"


def _desktop() -> Path:
    """Lấy ĐÚNG Desktop đang hoạt động (tôn trọng chuyển hướng OneDrive)."""
    try:
        import ctypes
        from ctypes import windll, wintypes  # type: ignore
        buf = ctypes.create_unicode_buffer(wintypes.MAX_PATH)
        # CSIDL_DESKTOPDIRECTORY = 0x10; SHGFP_TYPE_CURRENT = 0
        if windll.shell32.SHGetFolderPathW(0, 0x10, 0, 0, buf) == 0 and buf.value:
            return Path(buf.value)
    except Exception:  # noqa: BLE001
        pass
    one = Path.home() / "OneDrive" / "Desktop"
    return one if one.is_dir() else Path.home() / "Desktop"


def _build_checklist() -> str:
    try:
        from core.manual_publish_desk import list_items
        items = list_items()
    except Exception as exc:  # noqa: BLE001
        return f"# Việc đăng tay\n\n⚠️ Chưa đọc được Manual Publish Desk: {exc}\n"

    from collections import defaultdict
    groups: dict[str, list[dict]] = defaultdict(list)
    for it in items:
        groups[str(it.get("platform") or it.get("kind") or "Khác")].append(it)

    lines = [
        "# ✋ DANH SÁCH VIỆC ĐĂNG TAY",
        "",
        f"AURA gom được **{len(items)} việc** cần Sếp tự đăng. Nhóm theo nền tảng:",
        "",
    ]
    for plat, its in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        lines.append(f"## {plat} — {len(its)} việc\n")
        if its:
            lines.append(f"> Việc cần làm: {its[0].get('action') or '(xem từng mục)'}\n")
        for i, it in enumerate(its, 1):
            title = str(it.get("title") or it.get("name") or it.get("id") or "?")[:80]
            lines.append(f"{i:>2}. [ ] {title}")
        lines.append("")
    lines.append("---")
    lines.append("*Payhip: mở thư mục `PAYHIP_BAN_SACH/` — mỗi sách có sẵn PDF + bìa "
                 "+ bản chữ để Ctrl+V.*")
    lines.append("*YouTube: mở Studio, đổi video từ Riêng tư → Công khai (đúng danh "
                 "sách trên).*")
    return "\n".join(lines)


def main() -> int:
    if not SRC_VIEC.is_dir():
        print(f"❌ Không thấy {SRC_VIEC}. Chạy `python -m core.payhip_kit` trước.")
        return 1

    dest = _desktop() / "AURA_VIEC_DANG_TAY"
    if dest.exists():
        shutil.rmtree(dest, ignore_errors=True)
    dest.mkdir(parents=True, exist_ok=True)

    # 1) Bộ Payhip + mọi tài liệu hướng dẫn trong VIEC_CUA_SEP.
    n_files = 0
    for item in SRC_VIEC.iterdir():
        target = dest / ("PAYHIP_BAN_SACH" if item.name == "02_PAYHIP_BAN_SACH" else item.name)
        if item.is_dir():
            shutil.copytree(item, target, dirs_exist_ok=True)
            n_files += sum(1 for _ in target.rglob("*") if _.is_file())
        else:
            shutil.copy2(item, target)
            n_files += 1

    # 2) Checklist tổng từ Manual Publish Desk.
    (dest / "DANH_SACH_DANG_TAY.md").write_text(_build_checklist(), encoding="utf-8")

    # 3) README trên cùng.
    (dest / "_DOC_TRUOC.md").write_text(
        "# Việc đăng tay của Sếp\n\n"
        "Thư mục này AURA tự gom ra Desktop cho dễ tìm.\n\n"
        "- **DANH_SACH_DANG_TAY.md** — checklist mọi việc cần đăng tay (tick dần).\n"
        "- **PAYHIP_BAN_SACH/** — 15 sách tô màu, mỗi cuốn 1 thư mục: file PDF, ảnh "
        "bìa, và bản chữ soạn sẵn để dán vào Payhip.\n"
        "- **00_DOC_CAI_NAY_TRUOC.md** và các file 01–05 — hướng dẫn từng đầu việc "
        "(đăng nhập, nhận tiền, bảo mật).\n\n"
        "Nguồn gốc trong máy: D:\\AURA_OS_v2\\VIEC_CUA_SEP (bản này là bản sao ra Desktop).\n",
        encoding="utf-8",
    )

    print(f"✅ Đã xuất ra: {dest}")
    print(f"   {n_files} file. Mở '_DOC_TRUOC.md' để bắt đầu.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
