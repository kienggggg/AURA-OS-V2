"""
tools/upscale_mascot.py
=======================
HD hoá sprite mascot MỘT LẦN: assets/mascot/anim/*.png (pixel art 96x104)
-> assets/mascot/anim_hd/*.png (384x416) bằng thuật toán hq4x — thiết kế riêng
cho pixel art (giữ nét viền, mượt khối màu; khác lanczos/bicubic làm nhoè).

Chạy lại an toàn: file HD nào đã có và mới hơn file gốc thì bỏ qua.
    venv\\Scripts\\python.exe tools\\upscale_mascot.py
"""

from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC = _PROJECT_ROOT / "assets" / "mascot" / "anim"
DST = _PROJECT_ROOT / "assets" / "mascot" / "anim_hd"


def main() -> int:
    # Shim: hqx 1.0 import PIL.PyAccess (Pillow >=11 đã gỡ) chỉ để chú thích kiểu;
    # Image.load() thật vẫn còn -> nhét module giả là hqx chạy bình thường.
    import types
    if "PIL.PyAccess" not in sys.modules:
        import PIL
        shim = types.ModuleType("PIL.PyAccess")
        shim.PyAccess = object
        sys.modules["PIL.PyAccess"] = shim
        PIL.PyAccess = shim
    import hqx
    from PIL import Image

    if not SRC.is_dir():
        print(f"Không thấy thư mục nguồn {SRC}")
        return 1
    DST.mkdir(parents=True, exist_ok=True)
    done = skipped = 0
    for f in sorted(SRC.glob("*.png")):
        out = DST / f.name
        if out.is_file() and out.stat().st_mtime >= f.stat().st_mtime:
            skipped += 1
            continue
        img = Image.open(f).convert("RGBA")
        # hqx nhân 4 cả kênh alpha: tách alpha upscale nearest để viền không viền đen.
        rgb = img.convert("RGB")
        big = hqx.hq4x(rgb)
        alpha = img.getchannel("A").resize(
            (img.width * 4, img.height * 4), Image.NEAREST
        )
        big = big.convert("RGBA")
        big.putalpha(alpha)
        big.save(out)
        done += 1
        print(f"  {f.name}: {img.width}x{img.height} -> {big.width}x{big.height}")
    print(f"Xong: {done} upscale, {skipped} bỏ qua (đã có). Đích: {DST}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
