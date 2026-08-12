# -*- coding: utf-8 -*-
"""Dựng ảnh chụp SẠCH của AURA v2 để đẩy công khai — một commit, không lịch sử.

Vì sao không đẩy thẳng nhánh hiện tại: lịch sử git có ~20 khoá API THẬT ở
commit 88e8c07 (Antigravity đổi thư mục làm hỏng .gitignore). Đã gỡ khỏi bản
theo dõi nhưng vẫn nằm trong lịch sử, nên `git push` là công khai chúng.

Dựng ở THƯ MỤC KHÁC, không đụng repo gốc: nhánh mồ côi làm ngay trong repo dễ
để lại trạng thái nửa vời nếu đứt giữa chừng.

    venv\\Scripts\\python.exe tools\\dung_anh_chup_cong_khai.py <thư mục đích>

LOẠI BỎ — mỗi mục là một thứ đã soi tận nơi ngày 11/08/2026:

  portfolio/            CV thật + README có email, nơi ở, Zalo
  .env.example          KHÔNG phải mẫu: CALENDAR_ICS_URL, GMAIL_USER, IMAP_HOST
                        đều là giá trị THẬT. URL lịch iCal đọc được toàn bộ
                        lịch của Sếp. Thay bằng bản mẫu thật sự.
  data/user_profile.json    owner, goals, habits, WEAKNESSES, routines
  data/ledger/          thu nhập, đơn ứng tuyển, thời gian dùng máy
  data/feedback/        hồ sơ ứng tuyển việc
  data/leads/           danh sách khách tiềm năng
  data/pitches_ready.md · data/briefing_state.json · data/channels.json
  data/downloads/       phụ đề bilibili — nội dung của người khác
  data/reference_epubs/ truyện mẫu — nội dung của người khác
  tools/soat_pii.py     BỘ SOÁT TỰ NÓ LÀ CHỖ RÒ (thêm 12/08/2026). Nó chứa mẫu
                        regex của đúng những thứ nó đi tìm — họ tên, nơi ở,
                        chứng chỉ, email, tên Page, tên tệp CV. Thay `[aạ]`
                        bằng ký tự đầu là đọc ra nguyên văn, một dòng code.
                        Tệ hơn: danh sách "tha" của chính nó đánh dấu tệp này
                        là `*`, nên bộ soát TỰ BỎ QUA MÌNH và báo "sạch".
                        Một danh sách tha che mất chỗ rò thật thì tệ hơn không
                        có danh sách nào. Bộ soát dữ liệu riêng ở lại máy riêng.

GIỮ LẠI: toàn bộ mã, test, tài liệu, và data/tech_evidence/ (sổ bằng chứng —
đây mới là thứ đáng giá nhất cho người đến sau).

KHÔNG loại: số điện thoại trong mã đều là giả (`placeholder` trong form HTML,
dữ liệu test "Nguyễn Văn A"); 27 tệp khớp "ngân hàng" đều là MÃ NỐI MB Bank,
không có số tài khoản; 3 chuỗi giống khoá đều là "sk-abc123def..." trong test.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
GOC = Path(__file__).resolve().parent.parent

BO = [
    "portfolio/",
    "data/user_profile.json",
    "data/ledger/",
    "data/feedback/",
    "data/leads/",
    "data/pitches_ready.md",
    "data/briefing_state.json",
    "data/channels.json",
    "data/downloads/",
    "data/reference_epubs/",
    "tools/soat_pii.py",
]
# Giá trị thật trong .env.example -> thay bằng mẫu.
#
# 12/08/2026 thêm ba biến cuối, sau khi soi bản ĐÃ ĐẨY LÊN GitHub. Chúng không
# phải khoá nên đợt soát đầu bỏ qua — nhưng ghép lại, bộ từ khoá săn việc và hai
# feed tuyển dụng đủ để đọc ra Sếp ở tỉnh nào, có chứng chỉ gì, đang tìm việc gì.
# Bí mật thì đổi được, còn chỗ ở và nghề nghiệp thì không.
#
# KHÔNG chép giá trị thật vào chú thích này: tệp công cụ cũng lên ảnh chụp, nên
# viết ra đây là tự dán lại đúng thứ vừa gỡ. Lần đầu tôi viết hụt chỗ này và bộ
# soát bắt được.
THAY_MAU = re.compile(
    r"^(CALENDAR_ICS_URL|GMAIL_USER|IMAP_HOST|SMTP_HOST|TELEGRAM_[A-Z_]+"
    r"|SCOUT_KEYWORDS|FREELANCE_URLS|PEDAGOGY_URLS)=(.+)$",
    re.MULTILINE)
# Tên tệp CV có HỌ TÊN Sếp và nằm trong lệnh đã ghi ở sổ bằng chứng.
TEN_CV = re.compile(r"[A-Za-zÀ-ỹ]+-[A-Za-zÀ-ỹ]+-[A-Za-zÀ-ỹ]+-TopCV\.vn-[\d.]+\.pdf")


def main() -> int:
    if len(sys.argv) < 2:
        print("  cần thư mục đích")
        return 2
    dich = Path(sys.argv[1]).resolve()
    if dich.exists() and any(dich.iterdir()):
        print(f"  {dich} không rỗng — dừng, không ghi đè")
        return 1
    dich.mkdir(parents=True, exist_ok=True)

    ra = subprocess.run(["git", "-C", str(GOC), "ls-files"], capture_output=True,
                        text=True, encoding="utf-8", errors="replace")
    tep = [d for d in ra.stdout.splitlines() if d.strip()]

    chep = bo_qua = 0
    da_bo: list[str] = []
    roi_im_lang: list[str] = []
    for ten in tep:
        # Tên tệp có ký tự ngoài ASCII bị `git ls-files` bọc nháy và escape
        # bát phân ("data/downloads/\346\235\216..."). Gỡ ra trước khi so, không
        # thì luật lọc trượt và tệp lọt vào ảnh chụp — hoặc rơi im lặng ở
        # `is_file()`, cũng tệ ngang: ảnh chụp thiếu mà không ai biết.
        that = ten
        if ten.startswith('"') and ten.endswith('"'):
            that = (ten[1:-1].encode("latin-1", "backslashreplace")
                    .decode("unicode_escape").encode("latin-1")
                    .decode("utf-8", "replace"))
        if any(that.startswith(b) for b in BO):
            bo_qua += 1
            da_bo.append(that)
            continue
        nguon = GOC / that
        if not nguon.is_file():
            roi_im_lang.append(that)
            continue
        cai = dich / that
        cai.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(nguon, cai)
        chep += 1

    # .env.example: thay giá trị thật bằng mẫu, giữ lại mọi chú thích.
    mau = dich / ".env.example"
    if mau.is_file():
        chu = mau.read_text(encoding="utf-8", errors="replace")
        chu, n = THAY_MAU.subn(r"\1=", chu)
        mau.write_text(chu, encoding="utf-8")
        print(f"  .env.example: rỗng hoá {n} giá trị thật")

    # Sổ bằng chứng ghi NGUYÊN VĂN lệnh đã chạy, trong đó có đường dẫn tệp CV —
    # mà tên tệp CV chứa họ tên Sếp. Không sửa sổ gốc (CLAUDE.md §5: sổ sống được
    # là nhờ chỗ không được viết lại), nên che ở BẢN SAO, và che bằng một dấu
    # nhìn thấy được chứ không thay bằng giá trị giả — người đọc phải biết là
    # chỗ này đã bị che, không phải lệnh vốn thế.
    che = 0
    for tep in dich.rglob("*"):
        if not tep.is_file() or tep.suffix.lower() not in (".json", ".md", ".txt"):
            continue
        chu = tep.read_text(encoding="utf-8", errors="replace")
        moi = TEN_CV.sub("<ten-tep-CV-da-che>.pdf", chu)
        if moi != chu:
            tep.write_text(moi, encoding="utf-8")
            che += 1
    print(f"  che tên tệp CV trong {che} tệp (sổ gốc giữ nguyên)")

    print(f"\n  chép {chep} · loại {bo_qua} · rơi im lặng {len(roi_im_lang)}"
          f"  (tổng {len(tep)})")
    print("\n  ĐÃ LOẠI:")
    for t in da_bo:
        print(f"    {t}")
    if roi_im_lang:
        print("\n  RƠI IM LẶNG — phải xem từng cái, không được bỏ qua:")
        for t in roi_im_lang:
            print(f"    {t}")
    print(f"\n  -> {dich}")
    return 0 if chep + bo_qua == len(tep) else 1


if __name__ == "__main__":
    raise SystemExit(main())
