"""
copy_deliverables_to_desktop.py
================================
Sao chép toàn bộ thành phẩm AURA làm ra ra thư mục THANH_PHAM_AURA trên Desktop của Sếp.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

desktop = Path.home() / "Desktop" / "THANH_PHAM_AURA"
desktop.mkdir(parents=True, exist_ok=True)

outputs_dir = Path("data/outputs")

categories = {
    "1_Sach_To_Mau_PDF": ["coloringbook"],
    "2_Truyen_Chuu_EPUB_PDF": ["story", "novel"],
    "3_Freelance_Deliverables": ["freelance"],
    "4_Video_Shorts": ["shorts", "story_video", "video"],
    "5_Web_Portals": ["web"],
}

print(f"📦 Đang sao chép thành phẩm vào: {desktop}\n")
copied_count = 0

for cat_name, subdirs in categories.items():
    target_cat = desktop / cat_name
    target_cat.mkdir(parents=True, exist_ok=True)
    cat_file_count = 0
    for sd in subdirs:
        src_path = outputs_dir / sd
        if src_path.exists():
            for f in src_path.rglob("*"):
                if f.is_file() and not f.name.startswith("."):
                    # Nếu trùng tên file thì đánh số thứ tự
                    dest_file = target_cat / f.name
                    if dest_file.exists():
                        dest_file = target_cat / f"{f.stem}_{copied_count}{f.suffix}"
                    shutil.copy2(f, dest_file)
                    cat_file_count += 1
                    copied_count += 1
    print(f"  ✅ [{cat_name}]: Đã chép {cat_file_count} file")

print(f"\n🎉 HOÀN THÀNH: Đã chép tổng cộng {copied_count} thành phẩm ra Desktop tại thư mục 'THANH_PHAM_AURA'!")
