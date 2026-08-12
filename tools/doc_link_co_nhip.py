# -*- coding: utf-8 -*-
"""Đọc link TikTok/Facebook qua `opencli web read` — CÓ NHỊP, vì TikTok chặn tốc độ.

11/08/2026: link đầu đọc ngon trong 23 giây, hai link tiếp theo trả về đúng hai
chữ "Please wait..." (80 byte). Đó là cửa chặn bot của TikTok, không phải lỗi
công cụ. Nên phải đi chậm, và phải BIẾT mình bị chặn thay vì ghi một tệp rỗng
rồi tưởng đã đọc xong.

    venv\\Scripts\\python.exe tools\\doc_link_co_nhip.py [số link tối đa]
"""
from __future__ import annotations

import io
import json
import random
import re
import subprocess
import sys
import time
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

GOC = Path(__file__).resolve().parent.parent
SO = GOC / "data" / "tech_evidence" / "video_sources.json"
KET_QUA = GOC / "data" / "tech_evidence" / "doc_qua_trinh_duyet.json"
BAI_RA = GOC / "web-articles"

# Dấu hiệu bị chặn, không phải nội dung.
CHAN = ("please wait", "captcha", "verify to continue", "unusual traffic")

# Dấu hiệu đây là KHUNG GIAO DIỆN chứ không phải video.
#
# 11/08/2026: ba link trả về 2-4 KB và bộ dò của tôi gắn nhãn ĐỌC_ĐƯỢC. Mở ra
# xem thì toàn "Tất cả hoạt động / Thích / Bình luận / Lượt nhắc đến" — trang
# thông báo của TikTok, vì link rút gọn hết hạn nên nó đá về đó. Đếm thanh điều
# hướng thành nội dung là đúng kiểu sai tôi đã mắc mấy lần hôm nay.
KHUNG_GIAO_DIEN = (
    "tất cả hoạt động", "lượt nhắc đến", "tiktokstudio/upload",
    "tải lên", "đăng nhập để", "log in to",
)
NGHI_GIAY = (35, 55)          # giãn ngẫu nhiên để không thành nhịp máy


def _noi_dung_that(url: str) -> tuple[str, Path | None]:
    """Tìm tệp `opencli` vừa ghi cho ĐÚNG url này.

    KHÔNG dò theo "tệp mới xuất hiện". `opencli` đặt tên tệp theo TIÊU ĐỀ
    trang, nên mọi trang TikTok hỏng đều rơi vào cùng vài cái tên
    (`TikTok.md`, `untitled.md`, `(5).md`) và đè lên nhau. Hệ quả đo được
    ngày 11/08: link 19 bị chặn ba lượt, lượt nào cũng ghi đúng vào
    `untitled/untitled.md`, mà vì tệp đó có sẵn từ trước nên tôi kết luận
    "không sinh tệp" — sai cả ba lượt.

    Mỗi tệp đều mở đầu bằng `> 原文链接: <url>`. Đối chiếu dòng đó là cách
    duy nhất biết chắc tệp này thuộc về link đang hỏi.
    """
    if not BAI_RA.exists():
        return "", None
    khop = [p for p in BAI_RA.rglob("*.md")
            if url in p.read_text(encoding="utf-8", errors="replace")[:400]]
    if not khop:
        return "", None
    tep = max(khop, key=lambda p: p.stat().st_mtime)
    return tep.read_text(encoding="utf-8", errors="replace"), tep


def doc_mot(url: str) -> dict:
    bat_dau = time.monotonic()
    try:
        subprocess.run(
            ["opencli", "web", "read", "--url", url],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=180, shell=True,
        )
    except subprocess.TimeoutExpired:
        return {"url": url, "trang_thai": "QUÁ_GIỜ", "giay": 180}
    giay = round(time.monotonic() - bat_dau, 1)

    chu, tep = _noi_dung_that(url)
    if tep is None:
        return {"url": url, "trang_thai": "KHÔNG_GHI_TỆP", "giay": giay}
    than = re.sub(r"^#.*$|^> .*$|^-+$", "", chu, flags=re.M).strip()
    # Xét "bị chặn" TRƯỚC "rỗng": "Please wait..." chỉ 14 ký tự, xét theo độ
    # dài trước thì nó thành RỖNG và mất hẳn thông tin mình đang bị chặn.
    if any(d in than.lower()[:400] for d in CHAN):
        return {"url": url, "trang_thai": "BỊ_CHẶN", "giay": giay}
    if not than or len(than) < 120:
        return {"url": url, "trang_thai": "RỖNG", "giay": giay, "ky_tu": len(than)}
    dau = sum(1 for d in KHUNG_GIAO_DIEN if d in than.lower())
    if dau >= 2:
        return {"url": url, "trang_thai": "CHỈ_KHUNG_GIAO_DIỆN", "giay": giay,
                "ky_tu": len(than)}
    return {
        "url": url, "trang_thai": "ĐỌC_ĐƯỢC", "giay": giay,
        "ky_tu": len(than),
        "tep": str(tep.relative_to(GOC)) if tep else None,
        "trich": " ".join(than.split())[:260],
    }


def main() -> int:
    han = int(sys.argv[1]) if len(sys.argv) > 1 else 999
    nguon = json.loads(SO.read_text(encoding="utf-8"))["sources"]
    can_doc = [m for m in nguon if not m.get("title")]

    xong = {}
    if KET_QUA.is_file():
        xong = {m["url"]: m for m in json.loads(KET_QUA.read_text(encoding="utf-8"))
                if m["trang_thai"] == "ĐỌC_ĐƯỢC"}
    con_lai = [m for m in can_doc if (m.get("resolved_url") or m["url"]) not in xong]

    print(f"  {len(can_doc)} link chưa đọc · {len(xong)} đã xong trước đó · "
          f"làm {min(han, len(con_lai))} link lần này\n")

    ket = list(xong.values())
    for i, m in enumerate(con_lai[:han], start=1):
        url = m.get("resolved_url") or m["url"]
        ra = doc_mot(url)
        ra["platform"] = m["platform"]
        ket.append(ra)
        dau = {"ĐỌC_ĐƯỢC": "✓", "BỊ_CHẶN": "⊘", "RỖNG": "·", "QUÁ_GIỜ": "✕",
               "CHỈ_KHUNG_GIAO_DIỆN": "▢", "KHÔNG_GHI_TỆP": "✕"}
        print(f"  {dau.get(ra['trang_thai'], '?')} [{i:>2}/{min(han, len(con_lai))}] "
              f"{ra['giay']:>5.1f}s  {ra['trang_thai']:<20} {url}", flush=True)
        if ra["trang_thai"] == "ĐỌC_ĐƯỢC":
            print(f"       {ra['trich'][:150]}")
        KET_QUA.write_text(json.dumps(ket, ensure_ascii=False, indent=2),
                           encoding="utf-8")
        if i < min(han, len(con_lai)):
            time.sleep(random.uniform(*NGHI_GIAY))

    doc_duoc = sum(1 for m in ket if m["trang_thai"] == "ĐỌC_ĐƯỢC")
    print(f"\n  ĐỌC ĐƯỢC {doc_duoc}/{len(ket)}  ->  {KET_QUA.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
