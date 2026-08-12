# -*- coding: utf-8 -*-
"""Rà kho công nghệ: thứ nào đã KHẢO SÁT mà chưa bao giờ ĐỘNG TỚI.

Vì sao có tệp này: 10/08/2026 Sếp nói thẳng — "cách bạn làm việc thế này thì
khả năng nhiều thứ trong kho công nghệ đã bị bỏ sót lắm".  Đúng.  Cách tôi làm
cả ngày là phản ứng theo link Sếp thả xuống; kho thì nằm im.  Bằng chứng có
sẵn: Hermes Agent được quyết chạy thử 22/07, giao Antigravity, **19 ngày không
ai truy lại**; sáu khe khoá Groq cắm vào router cả tháng vẫn rỗng.

Cách rà: lấy tên công nghệ trong các tệp hồ sơ, rồi hỏi một câu duy nhất —
**cái tên đó có xuất hiện ở đâu ngoài chính hồ sơ không?**  Trong mã, trong
lịch sử commit, trong tệp cấu hình.  Không có nghĩa là đã khảo sát rồi bỏ đó.

Chạy:  venv\\Scripts\\python.exe tools\\ra_kho_cong_nghe.py
"""
from __future__ import annotations

import io
import re
import subprocess
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

GOC = Path(__file__).resolve().parent.parent

# Hồ sơ khảo sát — nơi công nghệ được GHI, không phải nơi nó được DÙNG.
HO_SO = (
    "AI_TECH_RESEARCH.md",
    "AURA_COMMAND.md",
    "AURA_STATE.md",
    "docs/AURA_TECH_SCOUT_2026-07-30.md",
)

# Tên công nghệ hay đi kèm các dạng này trong ghi chép.
_TEN = re.compile(
    r"`([A-Za-z][\w.\-]{2,30}(?:/[\w.\-]{2,40})?)`"      # `tên` trong nháy ngược
    r"|\*\*([A-Z][\w.\-]{2,30})\*\*"                       # **Tên** in đậm
    r"|github\.com/([\w.\-]+/[\w.\-]+)"                    # đường dẫn github
)

# Chữ thường gặp nhưng không phải công nghệ.
BO_QUA = {
    "true", "false", "none", "null", "todo", "done", "aura", "sep", "claude",
    "codex", "antigravity", "python", "json", "http", "https", "readme",
    "windows", "linux", "macos", "utf", "api", "cli", "gui", "ram", "cpu",
    "gpu", "ssd", "url", "pdf", "png", "jpg", "mp4", "csv", "html", "css",
}


def _ten_trong(text: str) -> set[str]:
    ra: set[str] = set()
    for khop in _TEN.finditer(text):
        ten = next(g for g in khop.groups() if g)
        goc = ten.split("/")[-1].strip(".-_")
        if len(goc) < 3 or goc.lower() in BO_QUA or goc.isdigit():
            continue
        ra.add(goc)
    return ra


def _co_ngoai_ho_so(ten: str) -> tuple[bool, str]:
    """Cái tên này có sống ở đâu ngoài hồ sơ khảo sát không?"""
    # 1) trong mã / cấu hình đang theo dõi
    tim = subprocess.run(
        ["git", "-C", str(GOC), "grep", "-il", "--", ten,
         "--", "*.py", "*.json", "*.toml", "*.txt", "*.bat", "*.yaml", "*.yml"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    trong_ma = [d for d in tim.stdout.splitlines() if d.strip()]
    if trong_ma:
        return True, f"mã: {trong_ma[0]}"

    # 2) trong lời commit
    log = subprocess.run(
        ["git", "-C", str(GOC), "log", "--oneline", "-i", f"--grep={ten}"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if log.stdout.strip():
        return True, "commit: " + log.stdout.splitlines()[0][:52]

    return False, ""


def main() -> int:
    ten_theo_ho_so: dict[str, set[str]] = {}
    for ho_so in HO_SO:
        duong = GOC / ho_so
        if duong.is_file():
            ten_theo_ho_so[ho_so] = _ten_trong(
                duong.read_text(encoding="utf-8", errors="replace")
            )

    tat_ca = sorted(set().union(*ten_theo_ho_so.values()))
    print(f"  Quét {len(ten_theo_ho_so)} hồ sơ, thấy {len(tat_ca)} cái tên.\n")

    bo_quen: list[str] = []
    da_dung = 0
    for ten in tat_ca:
        co, o_dau = _co_ngoai_ho_so(ten)
        if co:
            da_dung += 1
        else:
            bo_quen.append(ten)

    print(f"  ĐÃ ĐỘNG TỚI      : {da_dung:>3}")
    print(f"  CHỈ NẰM TRONG HỒ SƠ: {len(bo_quen):>3}"
          f"   ({len(bo_quen) / max(1, len(tat_ca)):.0%})\n")
    print("  Những cái tên chưa từng ra khỏi trang giấy:\n")
    for i in range(0, len(bo_quen), 4):
        print("    " + "  ".join(f"{t:<24}" for t in bo_quen[i:i + 4]).rstrip())

    print("\n  Danh sách này KHÔNG phải việc phải làm — phần lớn đáng nằm yên.")
    print("  Nó chỉ trả lời một câu: cái gì đã ghi mà chưa ai đụng lại.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
