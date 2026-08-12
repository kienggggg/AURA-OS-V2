"""
factory/tools/coloringbook.py
==============================
coloringbook.factory — TẠO SÁCH TÔ MÀU (coloring book) PDF để bán thụ động
(Payhip/Gumroad/Etsy). Mô hình "AI Coloring Book Hustle": ý tưởng LLM + ảnh
NÉT ĐEN TRẮNG (line art) + đóng PDF — AURA đã có sẵn cả 3 mảnh, ghép lại.

Dây chuyền (100% free, không GPU):
  1. LLM (smart) từ CHỦ ĐỀ -> tên sách + N mô tả tranh line-art (tiếng Anh).
  2. Pollinations vẽ line art đen trắng (fallback Gemini) — style ép "coloring
     page, bold outlines, no shading, white background".
  3. PIL dàn mỗi tranh vào 1 trang khổ Letter dọc (viền + tiêu đề nhỏ) + trang bìa.
  4. pdfkit.images_to_pdf -> PDF sẵn bán.

Khác truyện tranh: KHÔNG thoại, KHÔNG tô bóng — chỉ nét sạch để người mua tự tô.
Checkpoint từng ảnh (chạy lại chỉ vẽ phần thiếu). QC: product_line 'coloringbook'.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

from core.config import settings
from factory import pdfkit
from factory import queue as job_queue
from factory.qc import QCReport, register_checker
from factory.models import FormField, JobCancelled, JobRecord, ToolSpec
from factory.tools.comic_create import _gen_panel

_PAGE_W, _PAGE_H = 1275, 1650          # 8.5x11 inch @ 150dpi (khổ Letter dọc)
_MARGIN = 70


def _slug(text: str, max_len: int = 40) -> str:
    s = re.sub(r"[^\w\-]+", "_", text, flags=re.UNICODE).strip("_")
    return s[:max_len] or "coloring_book"


def _style(audience: str) -> str:
    detail = ("simple thick bold outlines, large areas, minimal detail, cute"
              if audience == "kids"
              else "intricate detailed line art, fine patterns, elegant")
    return (f", black and white line art coloring book page, {detail}, clean "
            "crisp outlines, NO shading, NO grayscale, NO color, pure solid "
            "white background, centered subject, printable")


# --------------------------------------------------------------------------- #
# 1) Kịch bản: LLM -> {title, subtitle, pages[{subject, label}]}
# --------------------------------------------------------------------------- #
def _plan(theme: str, n_pages: int, audience: str) -> dict:
    from core.llm import CloudEngine
    who = "trẻ em" if audience == "kids" else "người lớn"
    system = (
        f"Bạn là người thiết kế sách tô màu cho {who}. Từ CHỦ ĐỀ của user, tạo ý "
        f"tưởng cho một cuốn coloring book đúng {n_pages} trang tô màu. Trả JSON "
        "THUẦN:\n"
        "{\"title\": \"tên sách tiếng Anh hấp dẫn, dễ tìm trên Etsy\",\n"
        " \"subtitle\": \"phụ đề ngắn tiếng Anh (đối tượng + số trang)\",\n"
        " \"pages\": [{\"subject\": \"mô tả 1 hình để vẽ line art, TIẾNG ANH, cụ "
        "thể 1 chủ thể rõ ràng, hợp tô màu\", \"label\": \"nhãn ngắn dưới tranh\"}]}\n"
        f"Mỗi trang MỘT chủ thể KHÁC nhau, đa dạng trong chủ đề. Đúng {n_pages} trang."
    )
    from factory import reflexion
    system += reflexion.lessons_prompt("coloringbook")
    res = CloudEngine().complete(
        [{"role": "user", "content": theme}], system_prompt=system,
        temperature=0.8, max_tokens=3000, tier="smart",
    )
    if not res.get("ok"):
        raise RuntimeError(f"Lên ý tưởng lỗi: {res.get('error')}")
    m = re.search(r"\{.*\}", str(res["text"]), re.DOTALL)
    if not m:
        raise RuntimeError("Ý tưởng trả về không có JSON.")
    plan = json.loads(m.group(0))
    if not plan.get("pages"):
        raise RuntimeError("Ý tưởng không có trang nào.")
    return plan


# --------------------------------------------------------------------------- #
# 2) Dàn trang: line art fit vào khổ Letter + viền + nhãn
# --------------------------------------------------------------------------- #
def _compose_page(img_path: Path, label: str, out: Path) -> None:
    from PIL import Image, ImageDraw, ImageFont

    page = Image.new("RGB", (_PAGE_W, _PAGE_H), "white")
    draw = ImageDraw.Draw(page)
    inner_w = _PAGE_W - 2 * _MARGIN
    inner_h = _PAGE_H - 2 * _MARGIN - 60          # chừa đáy cho nhãn

    im = Image.open(img_path).convert("RGB")
    iw, ih = im.size
    scale = min(inner_w / iw, inner_h / ih)
    nw, nh = int(iw * scale), int(ih * scale)
    im = im.resize((nw, nh))
    ox = (_PAGE_W - nw) // 2
    oy = _MARGIN + (inner_h - nh) // 2
    page.paste(im, (ox, oy))
    draw.rectangle([ox - 6, oy - 6, ox + nw + 6, oy + nh + 6], outline="black", width=3)

    label = (label or "").strip()
    if label:
        font = ImageFont.truetype(str(pdfkit.pick_font()[0]), 34)
        bb = draw.textbbox((0, 0), label, font=font)
        tw = bb[2] - bb[0]
        draw.text(((_PAGE_W - tw) / 2, _PAGE_H - _MARGIN - 10), label,
                  font=font, fill="black")
    out.parent.mkdir(parents=True, exist_ok=True)
    page.save(str(out))


def _compose_cover(title: str, subtitle: str, hero: Path | None, out: Path) -> None:
    from PIL import Image, ImageDraw, ImageFont

    page = Image.new("RGB", (_PAGE_W, _PAGE_H), "white")
    draw = ImageDraw.Draw(page)
    reg, bold = pdfkit.pick_font()
    ft = ImageFont.truetype(str(bold), 78)
    fs = ImageFont.truetype(str(reg), 40)

    def _center(text: str, font, y: int) -> None:
        import textwrap as _tw
        for line in _tw.wrap(text, width=22):
            bb = draw.textbbox((0, 0), line, font=font)
            draw.text(((_PAGE_W - (bb[2] - bb[0])) / 2, y), line, font=font, fill="black")
            y += (bb[3] - bb[1]) + 18

    _center(title, ft, 150)
    if hero and hero.exists():
        im = Image.open(hero).convert("RGB")
        s = min(700 / im.size[0], 700 / im.size[1])
        im = im.resize((int(im.size[0] * s), int(im.size[1] * s)))
        page.paste(im, ((_PAGE_W - im.size[0]) // 2, 560))
    if subtitle:
        _center(subtitle, fs, 1380)
    out.parent.mkdir(parents=True, exist_ok=True)
    page.save(str(out))


# --------------------------------------------------------------------------- #
# Handler
# --------------------------------------------------------------------------- #
def run(job: JobRecord, progress) -> None:
    params = job.params
    theme = str(params.get("theme") or "").strip()
    if not theme:
        raise ValueError("Chưa nhập chủ đề sách tô màu.")
    n_pages = max(3, min(30, int(params.get("pages") or 12)))
    audience = "kids" if str(params.get("audience") or "kids") == "kids" else "adults"

    art_dir = settings.outputs_dir / "coloringbook" / job.id
    line_dir = art_dir / "line"
    line_dir.mkdir(parents=True, exist_ok=True)
    job.artifacts_dir = str(art_dir)
    seed = abs(hash(job.id)) % 100000

    # 1) Kịch bản (checkpoint).
    plan_path = art_dir / "plan.json"
    if plan_path.exists():
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        progress(8, "Dùng ý tưởng đã có (checkpoint)")
    else:
        progress(4, "Lên ý tưởng sách (tầng smart)")
        plan = _plan(theme, n_pages, audience)
        plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2),
                             encoding="utf-8")
    title = str(plan.get("title") or "Coloring Book")
    subtitle = str(plan.get("subtitle") or "")
    pages = list(plan.get("pages") or [])[:n_pages]
    style = _style(audience)

    # 2) Vẽ line art từng trang (checkpoint từng file).
    line_files: list[Path] = []
    for i, pg in enumerate(pages):
        f = line_dir / f"page_{i + 1:02d}.jpg"
        if not f.exists():
            if job_queue.is_cancelled(job.id):
                raise JobCancelled()
            progress(10 + int(60 * i / len(pages)),
                     f"Vẽ nét trang {i + 1}/{len(pages)}")
            subj = str(pg.get("subject") or "a cute object")
            src = _gen_panel(subj + style, seed + i, f)
            time.sleep(6.0 if src == "pollinations" else 1.0)
        line_files.append(f)

    # 3) Dàn trang + bìa.
    progress(78, "Dàn trang + bìa")
    page_files: list[Path] = []
    cover = art_dir / "page_00_cover.png"
    _compose_cover(title, subtitle, line_files[0] if line_files else None, cover)
    page_files.append(cover)
    for i, (pg, lf) in enumerate(zip(pages, line_files)):
        out_page = art_dir / f"page_{i + 1:02d}.png"
        _compose_page(lf, str(pg.get("label") or ""), out_page)
        page_files.append(out_page)

    # 4) PDF.
    progress(94, "Đóng PDF")
    pdf_path = art_dir / f"{_slug(title)}.pdf"
    pdfkit.images_to_pdf(page_files, pdf_path)
    (art_dir / "package_info.json").write_text(json.dumps({
        "title": title, "subtitle": subtitle, "theme": theme,
        "audience": audience, "pages_in": len(pages),
        "pages_out": len(page_files),          # gồm cả bìa
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    progress(100, f"Xong '{title}' — {len(pages)} trang tô + bìa -> {pdf_path.name}")


def qc_coloringbook(job: JobRecord) -> QCReport:
    art = Path(job.artifacts_dir or "")
    pkg = art / "package_info.json"
    if not pkg.is_file():
        return QCReport(passed=False, checks=[
            {"name": "package", "ok": False, "note": "Chưa xong (thiếu package_info)."}])
    info = json.loads(pkg.read_text(encoding="utf-8"))
    checks: list[dict] = []
    ok = True
    pin, pout = int(info.get("pages_in") or 0), int(info.get("pages_out") or 0)
    full = pin >= 3 and pout >= pin + 1          # +1 = trang bìa
    checks.append({"name": "đủ trang", "ok": full, "note": f"{pout} trang (gồm bìa), {pin} tranh tô"})
    ok &= full
    pdfs = list(art.glob("*.pdf"))
    if pdfs:
        try:
            from pypdf import PdfReader
            n = len(PdfReader(str(pdfs[0])).pages)
            checks.append({"name": "pdf mở được", "ok": n == pout, "note": f"{n} trang PDF"})
            ok &= (n == pout)
        except Exception as exc:  # noqa: BLE001
            checks.append({"name": "pdf mở được", "ok": False, "note": str(exc)})
            ok = False
    else:
        checks.append({"name": "pdf mở được", "ok": False, "note": "thiếu PDF"})
        ok = False
    return QCReport(passed=bool(ok), checks=checks)


register_checker("coloringbook", qc_coloringbook)


SPEC = ToolSpec(
    name="coloringbook.factory",
    label_vi="Sách tô màu (bán Payhip/Etsy)",
    description="Nhập chủ đề — AURA lên ý tưởng, vẽ tranh NÉT đen trắng bằng AI free "
                 "(Pollinations, fallback Gemini), đóng thành sách tô màu PDF có bìa, "
                 "sẵn bán trên Payhip/Gumroad/Etsy. Sản phẩm digital thụ động, nội "
                 "dung gốc, không dính bản quyền.",
    product_line="coloringbook",
    form_fields=(
        FormField(key="theme", label="Chủ đề (vd: cute animals, mandala, dinosaurs)",
                  placeholder="cute forest animals"),
        FormField(key="pages", label="Số trang tô (3-30)", type="number",
                  default=12, required=False),
        FormField(key="audience", label="Đối tượng", type="select", default="kids",
                  choices=("kids", "adults"), required=False),
    ),
    handler=run,
    experimental=True,
)

__all__ = ["SPEC", "run"]
