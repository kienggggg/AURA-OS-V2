# -*- coding: utf-8 -*-
"""Sổ soát link: link số mấy đã xem, ra kết luận gì, đưa vào sổ bằng chứng chưa.

Vì sao có tệp này: Sếp đã chép tay 38 link TikTok qua ba đợt, và khi hỏi lại
"đã soát được bao nhiêu" thì tôi phải DỰNG LẠI TỪ HỘI THOẠI — không đếm được.
Công Sếp bỏ ra rơi vào chỗ không ai đếm. Đó là lỗi quy trình, không phải lỗi
trí nhớ, nên phải sửa bằng một chỗ ghi chứ không phải bằng cố nhớ kỹ hơn.

Sổ này KHÁC `data/tech_evidence/registry.json`:
    registry   = công nghệ đã ĐO, có lệnh chạy và băm hiện vật
    sổ này     = link đã XEM, và xem xong nghĩ gì

Một link có thể đã soát mà không đẻ ra công nghệ nào — đó vẫn là kết quả, và
vẫn phải ghi, không thì lần sau có người mở lại đúng link đó.

    python tools/so_soat_link.py xem
    python tools/so_soat_link.py dot 1
    python tools/so_soat_link.py ghi 42 --tom-tat "..." --ket-luan khong-dung
                                 [--cong-nghe openmontage] [--ghi-chu "..."]

Số thứ tự GIỮ NGUYÊN từ đợt đầu (đã kiểm: vị trí 19 ra ZS4FGG6Xb, khớp cách
Sếp gọi). Đổi số là ba AI nói chuyện lệch nhau.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

GOC = Path(__file__).resolve().parent.parent
NGUON = GOC / "data" / "tech_evidence" / "video_sources.json"
SO = GOC / "data" / "tech_evidence" / "so_soat_link.json"

KET_LUAN = {
    "dung-duoc": "đáng dùng — nên đo hoặc đã đo",
    "can-do": "chưa kết luận được, phải chạy thử mới biết",
    "khong-dung": "không hợp máy này / không phải công nghệ",
    "trung": "trùng thứ đã có trong sổ bằng chứng",
    "khong-doc-duoc": "không xem được nội dung",
}


def _bay_gio() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _danh_sach() -> list[dict]:
    """Đánh số ổn định: tiktok trước, facebook sau, theo thứ tự trong sổ nguồn."""
    nguon = json.loads(NGUON.read_text(encoding="utf-8"))["sources"]
    chua = [m for m in nguon if not m.get("title")]
    thu_tu = ([m for m in chua if m["platform"] == "tiktok"]
              + [m for m in chua if m["platform"] == "facebook"])
    return [{"so": i, "platform": m["platform"],
             "url": m.get("resolved_url") or m["url"]}
            for i, m in enumerate(thu_tu, start=1)]


def _nap() -> dict:
    if SO.is_file():
        return json.loads(SO.read_text(encoding="utf-8"))
    ds = _danh_sach()
    return {
        "danh_so_khop_voi": "cách Sếp gọi từ đợt 1 (link 19 = ZS4FGG6Xb)",
        "tong": len(ds),
        "muc": {
            str(m["so"]): {
                **m,
                # 1-38: Sếp ĐÃ chép tay qua ba đợt, nhưng lúc đó chưa có sổ nên
                # không ghi được từng link ra kết luận gì. Ghi đúng sự thật:
                # đã soát, chi tiết KHÔNG có. Không bịa lại cho đẹp sổ.
                "trang_thai": "đã soát" if m["so"] <= 38 else "chưa soát",
                "tom_tat": ("Sếp chép tay trước khi có sổ này — chi tiết không "
                            "ghi lại được" if m["so"] <= 38 else ""),
                "ket_luan": "", "cong_nghe": [], "ghi_chu": "", "soat_luc": "",
            } for m in ds
        },
    }


def _luu(so: dict) -> None:
    SO.write_text(json.dumps(so, ensure_ascii=False, indent=2), encoding="utf-8")


def xem(so: dict) -> int:
    muc = so["muc"]
    dem: dict[str, int] = {}
    for m in muc.values():
        dem[m["trang_thai"]] = dem.get(m["trang_thai"], 0) + 1
    print(f"  {so['tong']} link cần mắt người\n")
    for tt, n in sorted(dem.items(), key=lambda x: -x[1]):
        print(f"    {tt:<12} {n:>3}")

    co_kl = [m for m in muc.values() if m["ket_luan"]]
    print(f"\n  có kết luận ghi lại: {len(co_kl)}")
    dem_kl: dict[str, int] = {}
    for m in co_kl:
        dem_kl[m["ket_luan"]] = dem_kl.get(m["ket_luan"], 0) + 1
    for kl, n in sorted(dem_kl.items(), key=lambda x: -x[1]):
        print(f"    {kl:<16} {n:>3}   {KET_LUAN.get(kl, '')}")

    chua = sorted(int(k) for k, m in muc.items() if m["trang_thai"] == "chưa soát")
    if chua:
        print(f"\n  chưa soát: link {chua[0]}–{chua[-1]}  ({len(chua)} link)")
    return 0


def dot(so: dict, n: int, moi_dot: int = 18) -> int:
    """In một đợt để Sếp bấm lần lượt."""
    chua = sorted((int(k) for k, m in so["muc"].items()
                   if m["trang_thai"] == "chưa soát"))
    if not chua:
        print("  không còn link nào chưa soát")
        return 0
    dau = (n - 1) * moi_dot
    lo = chua[dau:dau + moi_dot]
    if not lo:
        print(f"  đợt {n} rỗng — chỉ còn {len(chua)} link chưa soát")
        return 1
    tong_dot = (len(chua) + moi_dot - 1) // moi_dot
    print(f"  ĐỢT {n}/{tong_dot} — {len(lo)} link (còn {len(chua)} chưa soát)\n")
    for i in lo:
        print(f"{i}. {so['muc'][str(i)]['url']}")
    return 0


def ghi(so: dict, args) -> int:
    khoa = str(args.so)
    if khoa not in so["muc"]:
        print(f"  không có link số {args.so}")
        return 1
    if args.ket_luan not in KET_LUAN:
        print(f"  kết luận phải là một trong: {', '.join(KET_LUAN)}")
        return 1
    m = so["muc"][khoa]
    m.update({
        "trang_thai": "đã soát",
        "tom_tat": args.tom_tat,
        "ket_luan": args.ket_luan,
        "cong_nghe": args.cong_nghe or [],
        "ghi_chu": args.ghi_chu or "",
        "soat_luc": _bay_gio(),
    })
    print(f"  link {args.so}  [{args.ket_luan}]  {args.tom_tat[:70]}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="lenh", required=True)
    sub.add_parser("xem")
    d = sub.add_parser("dot")
    d.add_argument("n", type=int)
    d.add_argument("--moi-dot", type=int, default=18)
    g = sub.add_parser("ghi")
    g.add_argument("so", type=int)
    g.add_argument("--tom-tat", required=True)
    g.add_argument("--ket-luan", required=True)
    g.add_argument("--cong-nghe", nargs="*")
    g.add_argument("--ghi-chu")
    args = p.parse_args()

    so = _nap()
    if args.lenh == "xem":
        ma = xem(so)
    elif args.lenh == "dot":
        ma = dot(so, args.n, args.moi_dot)
    else:
        ma = ghi(so, args)
    _luu(so)
    return ma


if __name__ == "__main__":
    raise SystemExit(main())
