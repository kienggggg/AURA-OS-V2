# -*- coding: utf-8 -*-
"""Hợp đồng chung cho mọi phép đo trong `tools/probes/`.

Trước 11/08/2026 có HAI bộ phép đo, cùng nạp vào một sổ bằng chứng:

    tools/local_tech_probes.py   (Codex)  argparse, in JSON một dòng
    tools/probes/do_cong_nghe.py (Claude) tra argv[1], in bảng cho người đọc

Cùng đích mà khác cửa. Tệ hơn: `core/tech_evidence` BĂM STDOUT làm hiện vật,
nên hai kiểu in ra hai loại hiện vật không so được với nhau.

Chọn kiểu của Codex — một dòng JSON, khoá đã sắp — vì nó băm ổn định và máy
đọc được. Bảng cho người đọc không mất: `--nguoi-doc` dựng lại từ chính JSON
đó, nên thứ Sếp nhìn và thứ vào sổ luôn là một.

Dấu hiệu cả hai đã tự chọn cùng đường: phép đo Codex viết mới hôm nay
(`hermes_openclaw_contract.py`) dùng đúng kiểu tra `argv[1]` và nằm luôn
trong `tools/probes/`.

LUẬT CỦA MỘT PHÉP ĐO (giữ nguyên từ bản Codex):
  - không cài gì, không tải gì, không ra Internet;
  - không in đường dẫn máy, khoá, hay nội dung tài liệu riêng của Sếp;
  - thoát 0 khi phép đo ĐẠT, thoát 1 khi KHÔNG ĐẠT — sổ đọc mã thoát.
"""
from __future__ import annotations

import io
import json
import sys
from typing import Callable, Mapping

# Phép đo hay in tiếng Việt; không bọc thì PowerShell nuốt dấu.
if isinstance(sys.stdout, io.TextIOWrapper) and sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")


def emit(payload: Mapping) -> None:
    """In kết quả: MỘT dòng JSON, khoá đã sắp.

    Sắp khoá để hai lần chạy cùng kết quả băm ra cùng một chuỗi — không thì
    sổ ghi "hiện vật đã đổi" trong khi chẳng có gì đổi.
    """
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def bang(payload: Mapping, cot: tuple[str, ...] = ()) -> None:
    """Dựng bảng cho người đọc TỪ CHÍNH JSON vừa in ra.

    Không tự in bảng riêng: in riêng là mở đường cho bảng nói một đằng, sổ
    ghi một nẻo.
    """
    muc = {k: v for k, v in payload.items() if not isinstance(v, (dict, list))}
    rong = max((len(k) for k in muc), default=0)
    for khoa, gia_tri in muc.items():
        print(f"  {khoa:<{rong}}  {gia_tri}", file=sys.stderr)
    for khoa in cot:
        hang = payload.get(khoa)
        if not isinstance(hang, list) or not hang:
            continue
        print(f"\n  {khoa}:", file=sys.stderr)
        for m in hang:
            if isinstance(m, dict):
                print("    " + "  ".join(f"{k}={v}" for k, v in m.items()),
                      file=sys.stderr)


def chay(lenh: Mapping[str, Callable[[], int]]) -> int:
    """Cửa vào chung: `python <tệp> <tên phép đo>`.

    Giữ kiểu tra `argv[1]` thay vì argparse — ngắn hơn, và là kiểu cả hai
    chúng tôi đã tự chọn khi viết tệp mới.
    """
    if len(sys.argv) != 2 or sys.argv[1] not in lenh:
        print("phép đo: " + ", ".join(sorted(lenh)), file=sys.stderr)
        return 2
    try:
        return lenh[sys.argv[1]]()
    except Exception as exc:                            # noqa: BLE001
        # Phép đo gãy KHÁC phép đo không đạt. Gãy thì nói là gãy, đừng để
        # sổ ghi "không đạt" cho một thứ chưa hề được đo.
        emit({"ok": False, "do_duoc": False,
              "loi": f"{type(exc).__name__}: {exc}"})
        return 2
