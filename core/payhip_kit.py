"""
core/payhip_kit.py
==================
BỘ ĐỒ NGHỀ ĐĂNG PAYHIP — soạn sẵn mọi thứ để Sếp chỉ việc DÁN và BẤM.

Vì sao phải làm tay?
--------------------
Payhip dựng tường chống bot (Cloudflare "Performing security verification").
Trình duyệt do Playwright mở bị gắn cờ và kẹt ở màn xác minh. AURA KHÔNG lách
tường đó — lách là đường ngắn nhất tới khoá tài khoản bán hàng của Sếp.
Gumroad cũng cụt: API tạo sản phẩm chưa tồn tại (mới là feature request).

=> Bước đăng bán buộc phải có tay người. Nhưng đó là việc LÀM MỘT LẦN cho mỗi
   cuốn, không phải nghi thức hằng ngày. Việc của AURA là làm cho một lần đó
   ngắn nhất có thể: gom file + soạn sẵn từng ô chữ để Sếp chỉ Ctrl+V.

Chạy:  python -m core.payhip_kit
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from core.config import PROJECT_ROOT

COLORING_DIR = PROJECT_ROOT / "data" / "outputs" / "coloringbook"
OUT_DEFAULT = PROJECT_ROOT / "VIEC_CUA_SEP" / "02_PAYHIP_BAN_SACH"

# Giá gợi ý theo tệp người mua. Sách người lớn bán được giá hơn sách trẻ em.
PRICE_BY_AUDIENCE = {"adults": 4.99, "kids": 2.99}


def _slug(text: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "_", text).strip("_")
    return s[:48] or "sach"


def _to_letter(src: Path, dst: Path) -> str:
    """Ép PDF về đúng khổ US Letter 8.5x11 in.

    Sách AURA đẻ ra đang là 13.28x17.19 in — KHÔNG phải khổ giấy nào cả (ảnh
    được đặt theo pixel, coi như 72dpi). Tỷ lệ thì trùng khít Letter (0.7725 vs
    0.7727) nên co về Letter không méo hình. Không sửa thì máy in ở nhà để chế
    độ 'actual size' sẽ CẮT MẤT MÉP tranh -> khách bực, đòi hoàn tiền.
    """
    try:
        from pypdf import PdfReader, PdfWriter
    except ImportError:
        shutil.copy2(src, dst)
        return "PDF in được"
    try:
        reader, writer = PdfReader(str(src)), PdfWriter()
        for page in reader.pages:
            page.scale_to(width=612, height=792)  # 8.5 x 11 in @ 72pt
            writer.add_page(page)
        with dst.open("wb") as fh:
            writer.write(fh)
        return "US Letter (8.5 x 11 in)"
    except Exception as exc:  # noqa: BLE001
        print(f"   ⚠️ Không ép được khổ Letter ({exc}) — dùng file gốc.")
        shutil.copy2(src, dst)
        return _page_size_note(src)


def _page_size_note(pdf: Path) -> str:
    """Đọc KÍCH THƯỚC THẬT của trang PDF — không phán bừa 'US Letter'."""
    try:
        from pypdf import PdfReader
    except ImportError:
        return "PDF in được"
    try:
        box = PdfReader(str(pdf)).pages[0].mediabox
        w, h = float(box.width) / 72.0, float(box.height) / 72.0
        # 8.5x11 = US Letter, 8.27x11.69 = A4 (sai số in ấn ~0.15 inch)
        if abs(w - 8.5) < 0.15 and abs(h - 11) < 0.15:
            return "US Letter (8.5 x 11 in)"
        if abs(w - 8.27) < 0.15 and abs(h - 11.69) < 0.15:
            return "A4 (8.27 x 11.69 in)"
        return f"{w:.2f} x {h:.2f} in"
    except Exception:  # noqa: BLE001
        return "PDF in được"


def _tags(info: dict) -> list[str]:
    theme = (info.get("theme") or "").lower()
    words = [w for w in re.split(r"[^a-z]+", theme) if len(w) > 3]
    base = ["coloring book", "printable", "instant download", "digital download",
            "coloring pages", "pdf download", "line art"]
    base.append("kids coloring book" if info.get("audience") == "kids"
                else "adult coloring book")
    out: list[str] = []
    for t in words + base:
        if t and t not in out:
            out.append(t)
    return out[:13]


def _description(info: dict, plan: dict, size: str) -> str:
    title = info.get("title", "Coloring Book")
    subtitle = info.get("subtitle", "")
    theme = (info.get("theme") or title).lower()
    kids = info.get("audience") == "kids"
    n = info.get("pages_in") or len(plan.get("pages", []) or []) or 12

    labels = [p.get("label", "").strip() for p in (plan.get("pages") or [])]
    labels = [l for l in labels if l]
    bullets = "\n".join(f"- {l}" for l in labels[:8])
    if len(labels) > 8:
        bullets += f"\n- ...and {len(labels) - 8} more designs"

    if kids:
        opening = (
            f"A cheerful coloring book all about {theme}. {n} big, friendly pictures "
            "with thick, clean outlines that little hands can actually stay inside — "
            "no fiddly details, no frustration. Perfect for quiet afternoons, rainy "
            "days, travel bags and classroom corners."
        )
        supplies = "Great with crayons, chunky markers or colored pencils."
    else:
        opening = (
            f"Take a slow hour for yourself with {theme}. {n} original line-art pages "
            "drawn with clean, confident outlines — detailed enough to lose yourself "
            "in, open enough that your pens never fight the paper."
        )
        supplies = "Works beautifully with colored pencils, markers, gel pens and watercolor pencils."

    return f"""{subtitle}

{opening}

WHAT'S INSIDE
- {n} unique coloring pages, one design per page
- A matching cover page
{bullets}

THE DETAILS
- Instant digital download - printable PDF, {size}
- Print it as many times as you like, at home or at a print shop
- {supplies}
- Digital file only - nothing will be shipped

Artwork in this book was created with the assistance of AI tools.

For personal use only. Please do not redistribute, share or resell the files.
"""


def build_kits(out_dir: Path = OUT_DEFAULT) -> list[Path]:
    if not COLORING_DIR.is_dir():
        print(f"❌ Không thấy thư mục sách: {COLORING_DIR}")
        return []

    out_dir.mkdir(parents=True, exist_ok=True)
    made: list[Path] = []
    idx = 0

    for folder in sorted(COLORING_DIR.iterdir()):
        info_file = folder / "package_info.json"
        if not folder.is_dir() or not info_file.is_file():
            continue
        pdfs = sorted(folder.glob("*.pdf"))
        if not pdfs:
            continue

        info = json.loads(info_file.read_text(encoding="utf-8"))
        try:
            plan = json.loads((folder / "plan.json").read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            plan = {}

        # Chỉ đóng gói sách ĐÃ QUA KIỂM ĐỊNH — không đẩy hàng lỗi cho Sếp đăng.
        try:
            qc = json.loads((folder / "qc_report.json").read_text(encoding="utf-8"))
            if qc.get("passed") is False:
                print(f"⏭️  Bỏ qua (QC trượt): {info.get('title')}")
                continue
        except Exception:  # noqa: BLE001
            pass

        idx += 1
        pdf = pdfs[0]
        title = info.get("title", pdf.stem)
        dest = out_dir / f"{idx:02d}_{_slug(title)}"
        dest.mkdir(parents=True, exist_ok=True)

        size = _to_letter(pdf, dest / "FILE_TAI_LEN.pdf")
        cover = folder / "page_00_cover.png"
        if cover.is_file():
            shutil.copy2(cover, dest / "ANH_BIA.png")

        price = PRICE_BY_AUDIENCE.get(info.get("audience", ""), 3.99)
        tags = _tags(info)

        (dest / "DAN_VAO_PAYHIP.md").write_text(f"""# Cuốn {idx:02d} — {title}

> Mở trang thêm sản phẩm Payhip, chọn **Digital Product**, rồi dán từng ô dưới đây.
> Ba file cần dùng nằm ngay trong thư mục này.

---

## Ô 1 — Product name

```
{title}
```

## Ô 2 — Price (USD)

```
{price}
```

*(Giá gợi ý cho sách {"trẻ em" if info.get("audience") == "kids" else "người lớn"}. Sếp muốn đổi thì cứ đổi.)*

## Ô 3 — Description

```
{_description(info, plan, size)}
```

## Ô 4 — File sản phẩm (nút Upload)

`FILE_TAI_LEN.pdf` — nằm trong thư mục này

## Ô 5 — Ảnh bìa / Product image

`ANH_BIA.png` — nằm trong thư mục này

## Ô 6 — Tags / keywords (nếu Payhip hỏi)

```
{", ".join(tags)}
```

---

### ⚠️ Hai điều tuyệt đối tránh

1. **Không** viết các chữ `PLR`, `MRR`, `resale rights`, `resell` vào mô tả.
   Payhip **cấm** bán quyền-bán-lại — dính là khoá tài khoản.
   (Nguồn: help.payhip.com/article/205)
2. **Không** nhét mã QR ngân hàng vào mô tả. Lách cổng thanh toán của Payhip
   cũng là khoá tài khoản. Tiền phải chảy qua PayPal/Stripe của Payhip.

### Về dòng khai báo AI

Tôi có để sẵn một dòng *"created with the assistance of AI tools"* trong mô tả.
Payhip **không bắt buộc** khai. Tôi để vào vì nói thật với người mua là đường
dài an toàn hơn — nhưng đây là hàng của Sếp, Sếp thấy không cần thì xoá dòng đó.
""", encoding="utf-8")

        made.append(dest)
        print(f"✅ {idx:02d}. {title}  (${price})")

    return made


def main() -> None:
    ap = argparse.ArgumentParser(description="Soạn bộ đăng Payhip cho Sếp dán tay")
    ap.add_argument("--out", type=str, default=str(OUT_DEFAULT))
    args = ap.parse_args()

    made = build_kits(Path(args.out))
    print(f"\n📦 Đã soạn {len(made)} bộ đăng vào: {args.out}")


if __name__ == "__main__":
    main()
