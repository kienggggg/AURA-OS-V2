"""
dung_lo_short_congnghe.py
=========================
Dựng MỘT LÔ short 'mẹo công nghệ' rồi tự đóng gói bộ đăng ra Desktop.

CHẠY TỐI NAY khi máy rảnh: đóng Antigravity IDE + Brave trước (máy 12GB, render
1080x1920 ngốn RAM — thiếu RAM là MPT chết mã 143). Rồi bấm nút
'DUNG_VIDEO_TOI_NAY.bat' trên Desktop (hoặc chạy file này).

An toàn: cái nào render lỗi thì BỎ QUA, làm tiếp cái sau; đã dựng rồi thì bỏ qua
(checkpoint). Cuối cùng đóng gói MỌI short thành công thành bộ đăng.
"""

from __future__ import annotations

import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from factory.models import JobRecord
import factory.tools.video_shorts as vs
from core import short_post_kit

TOPICS = [
    "3 mẹo tăng tốc điện thoại Android bị chậm",
    "5 phím tắt bàn phím Windows cực hữu ích",
    "Cách giải phóng bộ nhớ điện thoại khi báo đầy",
    "3 cách bảo vệ tài khoản Google an toàn hơn",
    "Mẹo kéo dài tuổi thọ pin điện thoại",
    "3 tính năng ẩn của Google Chrome nên dùng",
    "Cách làm wifi nhà mạnh và ổn định hơn",
    "3 mẹo dọn máy tính Windows chạy nhanh hơn",
]


def _progress(pct, step):
    print(f"    [{pct:>3}%] {step}", flush=True)


def main() -> int:
    print("=" * 60)
    print("DỰNG LÔ SHORT MẸO CÔNG NGHỆ")
    print(f"{len(TOPICS)} video. Nếu MPT chết mã 143 -> máy thiếu RAM, đóng bớt app.")
    print("=" * 60)
    ok, fail = 0, 0
    for i, topic in enumerate(TOPICS, 1):
        print(f"\n=== [{i}/{len(TOPICS)}] {topic} ===", flush=True)
        try:
            job = JobRecord(tool="shorts",
                            params={"topic": topic, "language": "vi", "aspect": "9:16"})
            t0 = time.time()
            vs.run(job, _progress)
            print(f"  ✅ XONG ({time.time()-t0:.0f}s)", flush=True)
            ok += 1
        except Exception as e:
            print(f"  ❌ LỖI (bỏ qua, làm tiếp): {e}", flush=True)
            traceback.print_exc()
            fail += 1

    print(f"\n=== RENDER: {ok} xong, {fail} lỗi ===")
    print("\nĐóng gói bộ đăng ra Desktop...")
    try:
        from core.config import settings
        dest = short_post_kit._desktop() / "AURA_VIDEO_TIKTOK"
        made = 0
        for d in sorted((settings.outputs_dir / "shorts").iterdir()):
            if d.is_dir() and next(iter(d.glob("*.mp4")), None):
                if short_post_kit.build_kit(d, dest):
                    made += 1
        print(f"📦 Đã soạn {made} bộ đăng vào: {dest}")
    except Exception as e:
        print(f"⚠️ Đóng gói lỗi: {e}")
    print("\nXong. Mở thư mục AURA_VIDEO_TIKTOK trên Desktop để đăng tay.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
