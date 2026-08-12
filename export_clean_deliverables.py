"""
export_clean_deliverables.py
============================
Lọc CHỈ CÁC FILE THÀNH PHẨM HOÀN CHỈNH (.pdf, .epub, .mp4, .csv, .md)
và đưa ra Desktop của Sếp (hỗ trợ cả OneDrive Desktop nếu Windows bật).
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

desktops = [
    Path("C:/Users/baloa/Desktop"),
    Path("C:/Users/baloa/OneDrive/Desktop"),
]

outputs_dir = Path("data/outputs")

# Các định dạng thành phẩm thật (bỏ qua ảnh khung hình rác / file audio tạm)
ALLOWED_EXTS = {".pdf", ".epub", ".mp4", ".csv"}

categories = {
    "1_Sach_To_Mau_PDF": ["coloringbook"],
    "2_Truyen_Chuu_EPUB_PDF": ["story", "novel"],
    "3_Freelance_Deliverables": ["freelance"],
    "4_Video_Hoan_Chinh_MP4": ["shorts", "story_video", "video"],
}

for dt_path in desktops:
    if not dt_path.exists():
        continue

    target_root = dt_path / "THANH_PHAM_AURA"
    target_root.mkdir(parents=True, exist_ok=True)

    print(f"📦 Đang lọc thành phẩm sạch ra Desktop: {target_root}")
    total_copied = 0

    for cat_name, subdirs in categories.items():
        target_cat = target_root / cat_name
        target_cat.mkdir(parents=True, exist_ok=True)
        cat_count = 0

        for sd in subdirs:
            src_path = outputs_dir / sd
            if src_path.exists():
                for f in src_path.rglob("*"):
                    if f.is_file() and f.suffix.lower() in ALLOWED_EXTS and not f.name.startswith("."):
                        # Tránh copy đè
                        dest_file = target_cat / f.name
                        if dest_file.exists():
                            dest_file = target_cat / f"{f.stem}_{total_copied}{f.suffix}"
                        shutil.copy2(f, dest_file)
                        cat_count += 1
                        total_copied += 1

        print(f"  ✅ [{cat_name}]: {cat_count} file thành phẩm chuẩn")

    print(f"🎉 Hoàn thành chép {total_copied} file thành phẩm sạch vào {target_root}\n")

# Refresh Windows Shell Explorer
try:
    import ctypes
    ctypes.windll.shell32.SHChangeNotify(0x08000000, 0x0000, None, None)
except Exception:
    pass
