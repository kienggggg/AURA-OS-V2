# -*- coding: utf-8 -*-
"""CỬA CŨ — phép đo đã dời sang `tools/probes/moi_truong.py`.

Ngày 11/08/2026 gộp hai bộ phép đo về `tools/probes/`. Tệp này KHÔNG bị xoá,
và đây là lý do:

    data/tech_evidence/registry.json ghi "tools/local_tech_probes.py" ở 22 chỗ.

Đó là trường `command` trong các bằng chứng Codex đã thu — cùng các hiện vật
băm từ chính lệnh ấy. Sổ bằng chứng sống được là nhờ chỗ KHÔNG ĐƯỢC VIẾT LẠI:
một bản ghi nói "lệnh này, ngày này, băm ra thế này". Sửa 22 bản ghi lịch sử
cho khớp cấu trúc thư mục mới là đúng thứ sổ sinh ra để ngăn.

Nên tên cũ ở lại làm cửa chuyển tiếp. Lệnh cũ vẫn chạy, vẫn ra đúng JSON đó.

    python tools/local_tech_probes.py ffmpeg-installed     (cách cũ, còn chạy)
    python tools/local_tech_probes.py missing crawl4ai     (cách cũ, còn chạy)
    python tools/probes/moi_truong.py missing-crawl4ai     (cách mới)

Việc mới thì khai vào sổ bằng đường mới. Đường cũ chỉ để những gì đã ghi còn
chạy lại được.
"""
from __future__ import annotations

import sys
from pathlib import Path

THAT = Path(__file__).resolve().parent / "probes"
sys.path.insert(0, str(THAT))

from moi_truong import LENH, MISSING_TECH  # noqa: E402
from chung import chay  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    doi = list(sys.argv[1:] if argv is None else argv)
    # Cách gọi cũ tách đôi: `missing crawl4ai`. Cách mới gộp: `missing-crawl4ai`.
    if len(doi) == 2 and doi[0] == "missing" and doi[1] in MISSING_TECH:
        doi = [f"missing-{doi[1]}"]
    sys.argv = [sys.argv[0], *doi]
    return chay(LENH)


if __name__ == "__main__":
    raise SystemExit(main())
