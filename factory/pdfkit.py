"""
factory/pdfkit.py
==================
Đóng gói thành phẩm: PDF (fpdf2) + EPUB (ebooklib) cho truyện chữ, PDF ảnh
(Pillow) cho truyện tranh. Pure Python — cài sạch trên py3.14 Windows,
CỐ Ý tránh weasyprint (đòi GTK runtime, cực khổ trên Windows).

Font: ưu tiên settings.comic_font_path nếu tồn tại, fallback font Windows
(times/arial — đầy đủ dấu tiếng Việt, dùng local không cần redistribute).
"""

from __future__ import annotations

import logging
from pathlib import Path

from core.config import settings

logger = logging.getLogger("aura.factory.pdfkit")

# (regular, bold) — thử theo thứ tự, lấy cặp đầu tiên tồn tại.
_FONT_CANDIDATES: tuple[tuple[str, str], ...] = (
    (str(settings.comic_font_path), str(settings.comic_font_path)),
    (r"C:\Windows\Fonts\times.ttf", r"C:\Windows\Fonts\timesbd.ttf"),
    (r"C:\Windows\Fonts\arial.ttf", r"C:\Windows\Fonts\arialbd.ttf"),
)


def pick_font() -> tuple[Path, Path]:
    """(regular, bold) TTF có dấu tiếng Việt. Không thấy gì -> lỗi rõ ràng."""
    for reg, bold in _FONT_CANDIDATES:
        if Path(reg).exists():
            b = Path(bold) if Path(bold).exists() else Path(reg)
            return Path(reg), b
    raise FileNotFoundError(
        "Không tìm thấy font TTF nào (times/arial). Điền COMIC_FONT_PATH trong .env."
    )


def chapters_to_pdf(
    chapters: list[tuple[str, str]],
    out_path: Path,
    title: str,
    author: str = "",
) -> Path:
    """Danh sách (tên chương, nội dung text) -> PDF sách có trang bìa + số trang."""
    from fpdf import FPDF

    reg, bold = pick_font()
    pdf = FPDF(format="A5")
    pdf.add_font("book", "", str(reg))
    pdf.add_font("book", "B", str(bold))
    pdf.set_auto_page_break(auto=True, margin=18)

    # Trang bìa chữ (đơn giản, sạch — bìa ảnh để bản sau).
    pdf.add_page()
    pdf.set_font("book", "B", 26)
    pdf.ln(60)
    pdf.multi_cell(0, 14, title, align="C")
    if author:
        pdf.ln(8)
        pdf.set_font("book", "", 13)
        pdf.multi_cell(0, 8, author, align="C")

    for chap_title, body in chapters:
        pdf.add_page()
        pdf.set_font("book", "B", 15)
        pdf.multi_cell(0, 9, chap_title)
        pdf.ln(3)
        pdf.set_font("book", "", 11.5)
        for para in body.split("\n"):
            para = para.strip()
            if para:
                pdf.multi_cell(0, 6.4, para)
                pdf.ln(1.6)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(out_path))
    return out_path


def chapters_to_epub(
    chapters: list[tuple[str, str]],
    out_path: Path,
    title: str,
    author: str = "",
    lang: str = "vi",
) -> Path:
    """Danh sách (tên chương, nội dung) -> EPUB có mục lục."""
    from ebooklib import epub

    book = epub.EpubBook()
    book.set_identifier(f"aura-{abs(hash(title))}")
    book.set_title(title)
    book.set_language(lang)
    if author:
        book.add_author(author)

    items = []
    for i, (chap_title, body) in enumerate(chapters, 1):
        paras = "".join(
            f"<p>{p.strip()}</p>" for p in body.split("\n") if p.strip()
        )
        ch = epub.EpubHtml(title=chap_title, file_name=f"ch_{i:04d}.xhtml", lang=lang)
        ch.content = f"<h2>{chap_title}</h2>{paras}"
        book.add_item(ch)
        items.append(ch)

    book.toc = items
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav", *items]

    out_path.parent.mkdir(parents=True, exist_ok=True)
    epub.write_epub(str(out_path), book)
    return out_path


def images_to_pdf(image_paths: list[Path], out_path: Path) -> Path:
    """Ghép ảnh (trang truyện tranh) thành 1 PDF — Pillow save_all, 0 dep mới."""
    from PIL import Image

    if not image_paths:
        raise ValueError("Không có ảnh nào để đóng PDF.")
    pages = []
    for p in image_paths:
        im = Image.open(p)
        if im.mode != "RGB":
            im = im.convert("RGB")
        pages.append(im)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pages[0].save(str(out_path), save_all=True, append_images=pages[1:],
                  format="PDF", resolution=96)
    for im in pages:
        im.close()
    return out_path


__all__ = ["pick_font", "chapters_to_pdf", "chapters_to_epub", "images_to_pdf"]
