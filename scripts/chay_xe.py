# -*- coding: utf-8 -*-
"""Chạy xe rover bằng một cú bấm — Sếp tự chủ động thời điểm.

Sinh 06/08/2026 sau khi cách "hẹn giờ" thất bại 2 lần: Claude không thể canh
đúng lúc Sếp sẵn sàng quay video (lần thì xe chạy sớm, lần thì chạy muộn).
Giao quyền bấm cho Sếp là xong.

    python scripts/chay_xe.py lui 4      # lùi 4 giây
    python scripts/chay_xe.py tien 3     # tiến 3 giây
    python scripts/chay_xe.py dung
"""
import sys, io, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.rover import handle_rover_command

huong = (sys.argv[1] if len(sys.argv) > 1 else "lui").lower()
giay = sys.argv[2] if len(sys.argv) > 2 else "3"

print("=" * 46)
print(f"  XE SE {huong.upper()} {giay} GIAY")
print("=" * 46)
print()
print(handle_rover_command(f"xe {huong} {giay} giay"))
print()
input("Bam Enter de dong...")
