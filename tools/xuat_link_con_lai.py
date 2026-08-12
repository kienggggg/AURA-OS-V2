# -*- coding: utf-8 -*-
"""Xuất danh sách link CÒN LẠI cho Sếp đọc, đánh số khớp hai đợt trước.

Số thứ tự phải giữ nguyên giữa các đợt: Sếp gọi "link 19" thì cả ba AI phải
hiểu cùng một link. Thứ tự = tiktok trước, facebook sau, theo đúng thứ tự
trong `video_sources.json`. Đã kiểm: vị trí 19 ra ZS4FGG6Xb, khớp cách Sếp gọi.

    venv\\Scripts\\python.exe tools\\xuat_link_con_lai.py [số link đã xong]
"""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

GOC = Path(__file__).resolve().parent.parent
SO = GOC / "data" / "tech_evidence" / "video_sources.json"
RA_MD = GOC / "docs" / "LINK_CON_LAI.md"
RA_JSON = GOC / "docs" / "link_con_lai.json"


def main() -> int:
    xong_den = int(sys.argv[1]) if len(sys.argv) > 1 else 38
    nguon = json.loads(SO.read_text(encoding="utf-8"))["sources"]
    chua = [m for m in nguon if not m.get("title")]
    thu_tu = ([m for m in chua if m["platform"] == "tiktok"]
              + [m for m in chua if m["platform"] == "facebook"])

    con_lai = [
        {"so": i, "platform": m["platform"],
         "url": m.get("resolved_url") or m["url"]}
        for i, m in enumerate(thu_tu, start=1) if i > xong_den
    ]

    RA_JSON.write_text(json.dumps(
        {"danh_so_khop_voi": "cach Sep goi tu dot 1 (link 19 = ZS4FGG6Xb)",
         "da_xong_den": xong_den,
         "con_lai": len(con_lai),
         "links": con_lai}, ensure_ascii=False, indent=2), encoding="utf-8")

    dong = [
        f"# Link còn lại — {len(con_lai)} cái",
        "",
        f"Đã xong 1–{xong_den}. Số thứ tự giữ nguyên từ đợt đầu.",
        "",
    ]
    nen_truoc = None
    for m in con_lai:
        if m["platform"] != nen_truoc:
            nen_truoc = m["platform"]
            dong += ["", f"## {nen_truoc}", ""]
        dong.append(f"{m['so']}. {m['url']}")
    RA_MD.write_text("\n".join(dong) + "\n", encoding="utf-8")

    print(f"  đã xong 1–{xong_den} · còn {len(con_lai)}")
    for nen in ("tiktok", "facebook"):
        n = sum(1 for m in con_lai if m["platform"] == nen)
        if n:
            print(f"    {nen:<10} {n}")
    print(f"\n  {RA_JSON.relative_to(GOC)}")
    print(f"  {RA_MD.relative_to(GOC)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
