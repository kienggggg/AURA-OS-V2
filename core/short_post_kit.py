"""
core/short_post_kit.py
======================
Soạn BỘ ĐĂNG cho video short (TikTok / Reels / Shorts): copy video + sinh caption
giật + hashtag ra một thư mục trên Desktop để Sếp đăng tay.

Vì sao đăng tay? TikTok/Meta phát hiện + khoá tài khoản bot đăng UI. AURA sản
xuất video, Sếp bấm đăng — đó là cái "1%". Xem [[aura-payhip-wall]] cùng logic.

Chạy:
    python -m core.short_post_kit                 # gói mọi short trong kho
    python -m core.short_post_kit --only 3_meo    # chỉ short khớp từ khóa
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from core.config import settings

SHORTS_DIR = settings.outputs_dir / "shorts"

# Hashtag: trộn NGÁCH (tìm đúng người) + RỘNG (discovery). Đừng nhồi quá nhiều.
_BASE_TAGS = ["#meocongnghe", "#thuthuatdienthoai", "#congnghe", "#meovathay",
              "#thuthuat", "#fyp", "#xuhuong", "#LearnOnTikTok"]


def _desktop() -> Path:
    try:
        import ctypes
        from ctypes import windll, wintypes  # type: ignore
        buf = ctypes.create_unicode_buffer(wintypes.MAX_PATH)
        if windll.shell32.SHGetFolderPathW(0, 0x10, 0, 0, buf) == 0 and buf.value:
            return Path(buf.value)
    except Exception:  # noqa: BLE001
        pass
    one = Path.home() / "OneDrive" / "Desktop"
    return one if one.is_dir() else Path.home() / "Desktop"


def _clean_caption(raw: str) -> str:
    """Bóc CHỈ caption khỏi câu trả lời hay lắm lời của Gemini (bỏ lời dẫn,
    'Lựa chọn 1/2', markdown, ngoặc kép bao ngoài)."""
    import re
    text = (raw or "").strip()
    # Bỏ các dòng lời dẫn / tiêu đề lựa chọn.
    lines, skip_pat = [], re.compile(
        r"^(dưới đây|đây là|bạn có thể|gợi ý|lựa chọn|option|caption)\b|^\*\*",
        re.IGNORECASE)
    for ln in text.splitlines():
        s = ln.strip().strip("`")
        if not s or skip_pat.search(s):
            continue
        s = re.sub(r"^\*+|\*+$", "", s).strip().strip('"').strip()
        # Nếu Gemini trả nhiều phương án, dừng ở phương án đầu tiên hoàn chỉnh.
        if lines and skip_pat.search(ln.strip()):
            break
        lines.append(s)
        if len("\n".join(lines)) > 400:
            break
    return "\n".join(lines[:5]).strip()


def _gemini_caption(title: str, script: str) -> str | None:
    """Nhờ Gemini viết caption TikTok giật (hook + giá trị + CTA). None nếu lỗi."""
    try:
        from brains.cloud_gemini import GeminiBackend
        out = GeminiBackend().chat(
            [{"role": "user", "content":
              f"Video ngắn tựa '{title}'. Nội dung: {script[:500]}\n\n"
              "Viết ĐÚNG MỘT caption TikTok tiếng Việt (2-3 dòng): dòng đầu là HOOK "
              "giật giữ người xem 2 giây đầu, kết bằng lời kêu gọi nhẹ (lưu lại/theo "
              "dõi). TUYỆT ĐỐI KHÔNG lời dẫn, KHÔNG 'Lựa chọn 1/2', KHÔNG markdown, "
              "KHÔNG hashtag, KHÔNG bịa số liệu. Chỉ in caption thuần."}],
            temperature=0.6, max_tokens=1200,
        )
        cap = _clean_caption(out)
        # Cụt (Gemini 2.5 thinking) hoặc quá ngắn -> coi như hỏng, dùng mẫu.
        return cap if len(cap) >= 25 else None
    except Exception:  # noqa: BLE001 — offline/không key -> dùng mẫu
        return None


def _template_caption(title: str, script: str) -> str:
    return (f"📱 {title}?\n"
            "3 mẹo nhỏ mà máy nào cũng dùng được — lưu lại kẻo quên nhé!\n"
            "Theo dõi để xem thêm mẹo công nghệ mỗi ngày 👇")


def build_kit(short_dir: Path, dest_root: Path) -> Path | None:
    mp4 = next(iter(short_dir.glob("*.mp4")), None)
    if mp4 is None:
        return None
    try:
        pkg = json.loads((short_dir / "package_info.json").read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        pkg = {}
    title = str(pkg.get("title") or short_dir.name.replace("_", " ")).strip()
    try:
        script = (short_dir / "script.txt").read_text(encoding="utf-8")
    except Exception:  # noqa: BLE001
        script = ""

    caption = _gemini_caption(title, script) or _template_caption(title, script)
    terms = [f"#{t}" for t in (pkg.get("terms") or []) if str(t).isalnum()]
    tags = []
    for t in terms + _BASE_TAGS:
        if t.lower() not in [x.lower() for x in tags]:
            tags.append(t)
    tags = tags[:12]

    dest = dest_root / short_dir.name
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copy2(mp4, dest / "VIDEO.mp4")
    sub = short_dir / "subtitle.srt"
    if sub.is_file():
        shutil.copy2(sub, dest / "phu_de.srt")

    (dest / "DANG_TIKTOK.md").write_text(f"""# Đăng: {title}

> File **VIDEO.mp4** nằm trong thư mục này (9:16, ~{pkg.get('duration_s','?')}s).
> Mở app TikTok / Instagram Reels / YouTube Shorts trên điện thoại, chọn video,
> rồi dán phần dưới.

---

## Caption (dán vào ô mô tả)

```
{caption}

{' '.join(tags)}
```

## Đăng ở đâu

- [ ] TikTok
- [ ] Instagram Reels
- [ ] YouTube Shorts
- [ ] Facebook Reels

*Đăng cùng lúc cả 3-4 nơi để đo chỗ nào có view nhất.*

---

### ⚠️ Nhớ

- **Đăng TAY**, đừng dùng bot — TikTok/Meta khoá tài khoản bot đăng.
- Đăng đều đặn (mỗi ngày 1 cái) thì thuật toán mới hiểu kênh và đẩy.
- Video AI: có nền nào bắt gắn nhãn thì gắn (TikTok có mục 'AI-generated').
- 2 giây đầu là sống còn — nếu caption/hook chưa đủ giật, cứ sửa thoải mái.
""", encoding="utf-8")
    return dest


def main() -> int:
    ap = argparse.ArgumentParser(description="Soạn bộ đăng video short ra Desktop")
    ap.add_argument("--only", type=str, default=None,
                    help="Chỉ gói short có tên khớp từ khóa này")
    ap.add_argument("--out", type=str, default=None)
    args = ap.parse_args()

    if not SHORTS_DIR.is_dir():
        print(f"❌ Không thấy kho short: {SHORTS_DIR}")
        return 1
    dest_root = Path(args.out) if args.out else _desktop() / "AURA_VIDEO_TIKTOK"

    dirs = [d for d in sorted(SHORTS_DIR.iterdir())
            if d.is_dir() and next(iter(d.glob("*.mp4")), None)]
    if args.only:
        dirs = [d for d in dirs if args.only.lower() in d.name.lower()]
    if not dirs:
        print("❌ Không có short nào khớp.")
        return 1

    made = 0
    for d in dirs:
        out = build_kit(d, dest_root)
        if out:
            print(f"✅ {out.name}")
            made += 1
    print(f"\n📦 Đã soạn {made} bộ đăng vào: {dest_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
