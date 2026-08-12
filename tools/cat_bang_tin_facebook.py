# -*- coding: utf-8 -*-
"""Giữ lại ĐÚNG bài cần đọc trong tệp Facebook `opencli` chép về.

11/08/2026: đọc một link Facebook, `opencli` lấy đúng tiêu đề bài và tải 26
ảnh — nhưng tệp .md 29 KB kèm theo thì phần lớn KHÔNG phải bài đó:

    · khay Tin, kèm tên bạn bè của Sếp
    · lời chào "… ơi, bạn đang nghĩ gì thế?"
    · quảng cáo outlier.ai / shopify / meta.ai, link đầy mã theo dõi
    · bài của NGƯỜI KHÁC trong các nhóm, kèm tên và link hồ sơ của họ
    · một mẩu tin tai nạn chết người

Repo này không bao giờ đẩy lên GitHub nên chưa rò ra ngoài. Nhưng dữ liệu
riêng của người khác không có việc gì phải nằm trong thư mục làm việc.

GIỮ THEO DANH SÁCH TRẮNG, không cắt theo danh sách đen. Với dữ liệu của người
khác thì giữ-cái-mình-biết an toàn hơn cắt-cái-mình-đoán: bản đầu tôi viết
kiểu danh sách đen, cắt được 12% và để lại nguyên tên ba người lạ.

Thứ được giữ:
    · dòng tiêu đề `#` và dòng `原文链接`
    · mọi ảnh của bài
    · MÔ TẢ ẢNH của Facebook — đây mới là chỗ có chữ. Facebook tự sinh
      "Có thể là hình ảnh về văn bản cho biết '<nguyên văn slide>'", nên bài
      dạng nhiều slide đọc được thành chữ mà không cần nhìn ảnh.

    venv\\Scripts\\python.exe tools\\cat_bang_tin_facebook.py [--that]

Không có `--that` thì chỉ xem trước, không ghi gì.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

# `reconfigure` chứ KHÔNG bọc TextIOWrapper mới: tệp này được import từ
# `doc_facebook_co_nhip.py`, và tệp kia cũng bọc stdout. Hai lớp bọc chồng
# nhau thì lớp đầu bị thu gom rác và ĐÓNG LUÔN buffer bên dưới — cả chương
# trình chết ở lệnh print đầu tiên ("I/O operation on closed file").
sys.stdout.reconfigure(encoding="utf-8")

GOC = Path(__file__).resolve().parent.parent
BAI_RA = GOC / "web-articles"

TIEU_DE = re.compile(r"^#\s|^>\s*原文链接")
ANH = re.compile(r"^!\[[^\]]*\]\([^)]*\)\s*$")
# Mô tả ảnh do Facebook sinh — chỗ chứa chữ thật của bài nhiều slide.
MO_TA_ANH = re.compile(
    r"(?:Có\s*thể\s*là\s*hình\s*ảnh|Không\s*có\s*mô\s*tả\s*ảnh"
    r"|May\s*be\s*an\s*image)", re.IGNORECASE)


def cat(chu: str) -> tuple[str, int, int]:
    giu: list[str] = []
    mo_ta = 0
    for dong in chu.splitlines():
        if TIEU_DE.match(dong) or ANH.match(dong.strip()):
            giu.append(dong)
        elif MO_TA_ANH.search(dong):
            giu.append(dong.strip())
            mo_ta += 1
    gon: list[str] = []
    for dong in giu:
        if not dong.strip() and gon and not gon[-1].strip():
            continue
        gon.append(dong)
    return "\n".join(gon).rstrip() + "\n", len(chu.splitlines()) - len(giu), mo_ta


def main() -> int:
    that = "--that" in sys.argv
    if not BAI_RA.is_dir():
        print("  chưa có web-articles/")
        return 0

    truoc = sau = 0
    for tep in sorted(BAI_RA.rglob("*.md")):
        chu = tep.read_text(encoding="utf-8", errors="replace")
        if "facebook.com" not in chu.lower():
            continue
        moi, bo, mo_ta = cat(chu)
        truoc += len(chu)
        sau += len(moi)
        print(f"  {tep.parent.name[:60]}")
        print(f"     {len(chu):>7} -> {len(moi):>6} ký tự · bỏ {bo} dòng · "
              f"{mo_ta} mô tả ảnh giữ lại")
        if that:
            tep.write_text(moi, encoding="utf-8")

    if truoc:
        print(f"\n  tổng {truoc} -> {sau} ký tự "
              f"({100 - sau * 100 // max(truoc, 1)}% bị cắt)")
    print("  ĐÃ GHI" if that else "  xem trước — thêm --that để ghi thật")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
