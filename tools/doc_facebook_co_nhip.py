# -*- coding: utf-8 -*-
"""Đọc 36 link Facebook còn lại qua `opencli`, có nhịp, dọn ngay sau mỗi lượt.

Ba điều học được trước khi viết tệp này, mỗi điều đều trả giá:

1. TikTok chặn sau ~15 lượt trong một giờ, và `opencli web read` chạy bằng
   chính phiên Chrome đang đăng nhập của Sếp. Nên phải đi chậm và phải DỪNG
   khi gặp tường, không gõ tiếp.

2. `opencli` đặt tên tệp theo TIÊU ĐỀ TRANG. Trang hỏng đều rơi vào cùng vài
   cái tên (`Facebook.md`, `untitled.md`) và đè lên nhau. Dò theo "tệp mới
   xuất hiện" là sai — phải đối chiếu dòng `原文链接` bên trong tệp.

3. Tệp .md kèm theo phần lớn là BẢNG TIN của Sếp: tên bạn bè ở khay Tin,
   quảng cáo, bài của người khác trong nhóm. Dọn ngay sau mỗi lượt, đừng để
   dồn 36 lượt rồi mới dọn.

Chỗ có chữ thật là MÔ TẢ ẢNH do Facebook tự sinh ("Có thể là hình ảnh về văn
bản cho biết '<nguyên văn slide>'") — bài dạng nhiều slide đọc được thành chữ
mà không cần nhìn ảnh.

    venv\\Scripts\\python.exe tools\\doc_facebook_co_nhip.py [số link tối đa]
"""
from __future__ import annotations

import json
import random
import subprocess
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

GOC = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(GOC / "tools"))
from cat_bang_tin_facebook import cat  # noqa: E402

DANH_SACH = GOC / "docs" / "link_con_lai.json"
KET_QUA = GOC / "data" / "tech_evidence" / "doc_facebook.json"
BAI_RA = GOC / "web-articles"

CHAN = ("please wait", "captcha", "unusual traffic", "temporarily blocked",
        "you're temporarily blocked")
NGHI_GIAY = (40, 60)
# Tiêu đề vô nghĩa = trang không mở được, chỉ ra khung Facebook.
TEN_RONG = {"facebook", "untitled", "trang chủ", "log in to facebook"}


def _tep_cua(url: str) -> Path | None:
    if not BAI_RA.is_dir():
        return None
    khop = [p for p in BAI_RA.rglob("*.md")
            if url in p.read_text(encoding="utf-8", errors="replace")[:400]]
    return max(khop, key=lambda p: p.stat().st_mtime) if khop else None


def doc_mot(url: str) -> dict:
    t0 = time.monotonic()
    try:
        x = subprocess.run(["opencli", "web", "read", "--url", url],
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=180, shell=True)
    except subprocess.TimeoutExpired:
        return {"url": url, "trang_thai": "QUÁ_GIỜ", "giay": 180.0}
    giay = round(time.monotonic() - t0, 1)
    ra_lenh = ((x.stdout or "") + (x.stderr or "")).lower()
    if "browser_connect" in ra_lenh:
        return {"url": url, "trang_thai": "CHƯA_NỐI_CHROME", "giay": giay}

    tep = _tep_cua(url)
    if tep is None:
        return {"url": url, "trang_thai": "KHÔNG_GHI_TỆP", "giay": giay}

    chu = tep.read_text(encoding="utf-8", errors="replace")
    if any(d in chu.lower()[:2000] for d in CHAN):
        return {"url": url, "trang_thai": "BỊ_CHẶN", "giay": giay}

    # Dọn NGAY: bảng tin không được nằm lại trên đĩa dù chỉ một lượt.
    sach, bo, mo_ta = cat(chu)
    tep.write_text(sach, encoding="utf-8")

    ten = tep.stem.replace("_", " ").strip()
    anh = len(list((tep.parent / "images").glob("*"))) if (tep.parent / "images").is_dir() else 0
    if ten.lower() in TEN_RONG and mo_ta == 0:
        return {"url": url, "trang_thai": "CHỈ_KHUNG_GIAO_DIỆN", "giay": giay,
                "anh": anh}
    return {
        "url": url, "trang_thai": "ĐỌC_ĐƯỢC", "giay": giay,
        "tieu_de": ten, "mo_ta_anh": mo_ta, "anh": anh,
        "ky_tu_sach": len(sach), "da_bo_dong": bo,
        "tep": str(tep.relative_to(GOC)),
    }


def main() -> int:
    han = int(sys.argv[1]) if len(sys.argv) > 1 else 999
    can = json.loads(DANH_SACH.read_text(encoding="utf-8"))["links"]

    xong: dict[str, dict] = {}
    if KET_QUA.is_file():
        xong = {m["url"]: m for m in json.loads(KET_QUA.read_text(encoding="utf-8"))
                if m["trang_thai"] == "ĐỌC_ĐƯỢC"}
    con_lai = [m for m in can if m["url"] not in xong][:han]

    print(f"  {len(can)} link · {len(xong)} đã xong trước đó · "
          f"làm {len(con_lai)} lần này\n")

    ket = list(xong.values())
    dau = {"ĐỌC_ĐƯỢC": "✓", "BỊ_CHẶN": "⊘", "CHỈ_KHUNG_GIAO_DIỆN": "▢",
           "QUÁ_GIỜ": "✕", "KHÔNG_GHI_TỆP": "✕", "CHƯA_NỐI_CHROME": "✕"}
    for i, m in enumerate(con_lai, start=1):
        ra = doc_mot(m["url"])
        ra["so"] = m["so"]
        ket.append(ra)
        print(f"  {dau.get(ra['trang_thai'], '?')} [{i:>2}/{len(con_lai)}] "
              f"link {m['so']:<3} {ra['giay']:>5.1f}s  {ra['trang_thai']:<20}"
              f"{ra.get('tieu_de', '')[:60]}", flush=True)
        KET_QUA.write_text(json.dumps(ket, ensure_ascii=False, indent=2),
                           encoding="utf-8")

        # Tường thì DỪNG. Gõ tiếp chỉ làm tường dày thêm, và đó là tài khoản
        # thật của Sếp đang bị đem ra đánh cược.
        if ra["trang_thai"] in ("BỊ_CHẶN", "CHƯA_NỐI_CHROME"):
            print(f"\n  DỪNG ở link {m['so']} — {ra['trang_thai']}.", flush=True)
            break
        if i < len(con_lai):
            time.sleep(random.uniform(*NGHI_GIAY))

    n = sum(1 for m in ket if m["trang_thai"] == "ĐỌC_ĐƯỢC")
    print(f"\n  ĐỌC ĐƯỢC {n}/{len(ket)}  ->  {KET_QUA.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
