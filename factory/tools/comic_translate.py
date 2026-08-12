"""
factory/tools/comic_translate.py
=================================
comic.translate — dịch truyện tranh v2 (tool kiếm tiền #3).

Nâng cấp so với pipeline v1 (skills/manga-translate — vẫn giữ nguyên để chạy
độc lập qua chat):
1. OCR GỘP THEO BÓNG THOẠI: easyocr paragraph=True thay vì từng dòng rời.
2. TÔ TRẮNG ĐÚNG LÒNG BÓNG: cv2 dò vùng trắng liên thông quanh chữ và tô lại
   (hết cảnh vẽ hộp trắng đè lên tranh); chữ nằm trên nền vẽ (không có bóng)
   thì fallback hộp bo góc bán trong suốt.
3. DỊCH BẰNG LLM CÓ NGỮ CẢNH: cả trang 1 call (tầng bulk) + glossary bền theo
   BỘ truyện (nhất quán tên nhân vật xuyên chương) — thay Google dịch thô từng
   cụm. Cloud hỏng -> fallback deep-translator (không đứng dây chuyền).
4. TYPESET: nhị phân cỡ chữ cho vừa bóng, căn giữa, cờ "chữ tràn" cho QC.
5. Cả CHAPTER -> PDF (Pillow) sẵn bán; checkpoint từng trang.

Input: thư mục ảnh chapter (vd data/downloads/<title>/<chapter>/ từ
manga.download) hoặc bất kỳ thư mục ảnh nào.
"""

from __future__ import annotations

import json
import re
import textwrap
import time
from pathlib import Path

from core.config import settings
from factory import pdfkit
from factory import queue as job_queue
from factory.models import FormField, JobCancelled, JobRecord, ToolSpec
from factory.qc import QCReport, register_checker

_IMAGE_EXTS = frozenset({".jpg", ".jpeg", ".png", ".webp"})
_OCR_LANGS = {"zh": ["ch_sim", "en"], "ja": ["ja", "en"], "ko": ["ko", "en"], "en": ["en"]}

# easyocr Reader nặng (~vài trăm MB RAM) — cache theo bộ ngôn ngữ, dùng lại giữa
# các job trong cùng tiến trình daemon.
_READERS: dict[tuple[str, ...], object] = {}


def _get_reader(langs: list[str]):
    key = tuple(langs)
    if key not in _READERS:
        import easyocr
        _READERS[key] = easyocr.Reader(langs, gpu=False, verbose=False)
    return _READERS[key]


def _slug(text: str, max_len: int = 40) -> str:
    s = re.sub(r"[^\w\-]+", "_", text, flags=re.UNICODE).strip("_")
    return s[:max_len] or "truyen_tranh"


# --------------------------------------------------------------------------- #
# OCR: đọc cả trang, gộp theo bóng thoại, sắp theo thứ tự đọc trên-xuống
# --------------------------------------------------------------------------- #
def _ocr_page(img_path: Path, langs: list[str], min_conf: float = 0.3) -> list[dict]:
    reader = _get_reader(langs)
    # paragraph=True: easyocr tự gộp dòng gần nhau thành CỤM (bóng thoại).
    results = reader.readtext(str(img_path), paragraph=True)
    out = []
    for item in results:
        box, text = item[0], item[1]
        text = str(text).strip()
        if len(text) < 2:
            continue
        xs = [int(p[0]) for p in box]
        ys = [int(p[1]) for p in box]
        out.append({"bbox": (min(xs), min(ys), max(xs), max(ys)), "text": text})
    # Thứ tự đọc: trên xuống dưới, trái sang phải (chuẩn manhua/webtoon).
    out.sort(key=lambda d: (d["bbox"][1], d["bbox"][0]))
    return out


# --------------------------------------------------------------------------- #
# Dịch: cả trang 1 call LLM bulk + glossary; fallback Google từng cụm
# --------------------------------------------------------------------------- #
def _translate_page(texts: list[str], target: str, glossary: dict[str, str],
                    context: str) -> list[str]:
    if not texts:
        return []
    lang = "tiếng Việt" if target == "vi" else target
    gloss = "\n".join(f"- {k} => {v}" for k, v in list(glossary.items())[:30])
    numbered = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(texts))
    system = (
        f"Bạn là dịch giả truyện tranh. Dịch các CÂU THOẠI sau sang {lang}, ngắn gọn "
        "tự nhiên như lời nói trong bóng thoại, giữ cảm xúc (?!...), xưng hô nhất quán.\n"
        + (f"GLOSSARY BẮT BUỘC:\n{gloss}\n" if gloss else "")
        + (f"Bối cảnh truyện: {context}\n" if context else "")
        + "Trả về ĐÚNG danh sách đánh số như đầu vào, mỗi dòng 'số. bản dịch', "
          "không giải thích."
    )
    try:
        from core.llm import CloudEngine
        res = CloudEngine().complete(
            [{"role": "user", "content": numbered}], system_prompt=system,
            temperature=0.3, max_tokens=4000, tier=settings.novel_llm_tier,
        )
        if res.get("ok"):
            out: list[str | None] = [None] * len(texts)
            for m in re.finditer(r"^\s*(\d+)\s*[\.\):]\s*(.+)$", str(res["text"]), re.MULTILINE):
                i = int(m.group(1)) - 1
                if 0 <= i < len(texts):
                    out[i] = m.group(2).strip()
            if sum(1 for x in out if x) >= len(texts) * 0.8:
                return [x if x else texts[i] for i, x in enumerate(out)]
    except Exception:  # noqa: BLE001 — cloud hỏng thì đi đường Google bên dưới
        pass
    # Fallback: Google dịch free từng cụm (như v1) — chậm + kém ngữ cảnh nhưng sống.
    from deep_translator import GoogleTranslator
    tr = GoogleTranslator(source="auto", target=target)
    out2 = []
    for t in texts:
        try:
            out2.append(tr.translate(t) or t)
        except Exception:  # noqa: BLE001
            out2.append(t)
    return out2


def _build_glossary(sample_texts: list[str], target: str) -> dict[str, str]:
    """Trích tên riêng 1 lần từ thoại các trang đầu (tầng smart)."""
    sample = "\n".join(sample_texts)[:4000]
    if len(sample) < 80:
        return {}
    try:
        from core.llm import CloudEngine
        res = CloudEngine().complete(
            [{"role": "user", "content": sample}],
            system_prompt=(
                "Từ các câu thoại truyện tranh sau, trích JSON THUẦN {\"tên gốc\": "
                f"\"tên dịch {'tiếng Việt (Hán-Việt nếu là truyện Trung)' if target == 'vi' else target}\"}} "
                "gồm tên NHÂN VẬT/MÔN PHÁI/CHIÊU THỨC lặp lại. Tối đa 20 mục. "
                "Không có tên nào thì trả {}."
            ),
            temperature=0.2, max_tokens=1000, tier="smart",
        )
        m = re.search(r"\{.*\}", str(res.get("text", "")), re.DOTALL)
        if m:
            return {str(k): str(v) for k, v in json.loads(m.group(0)).items()}
    except Exception:  # noqa: BLE001 — không có glossary vẫn dịch được
        pass
    return {}


# --------------------------------------------------------------------------- #
# Tô trắng lòng bóng thoại (cv2) + typeset chữ Việt (PIL)
# --------------------------------------------------------------------------- #
def _whiten_bubble(img_bgr, bbox: tuple[int, int, int, int]) -> tuple:
    """Tô trắng vùng bóng thoại chứa bbox. Trả (ảnh, bbox_vùng_được_tô, is_bubble).

    Dò: quanh bbox (nới 40%), lấy mask điểm sáng (>=200), nở ra để lấp khe chữ,
    tìm thành phần liên thông ĐÈ LÊN bbox -> đó là lòng bóng. Không có (chữ nằm
    trên nền vẽ) -> trả bbox nới nhẹ, phía gọi sẽ vẽ hộp bo góc.
    """
    import cv2
    import numpy as np

    h, w = img_bgr.shape[:2]
    x0, y0, x1, y1 = bbox
    px, py = int((x1 - x0) * 0.4) + 8, int((y1 - y0) * 0.4) + 8
    rx0, ry0 = max(0, x0 - px), max(0, y0 - py)
    rx1, ry1 = min(w, x1 + px), min(h, y1 + py)
    region = img_bgr[ry0:ry1, rx0:rx1]
    gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
    light = (gray >= 200).astype(np.uint8)
    light = cv2.morphologyEx(light, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    n, labels, stats, _ = cv2.connectedComponentsWithStats(light, connectivity=4)

    bx0, by0, bx1, by1 = x0 - rx0, y0 - ry0, x1 - rx0, y1 - ry0  # bbox trong region
    best, best_area = 0, 0
    for i in range(1, n):
        lx, ly, lw, lh, area = stats[i]
        # thành phần phải phủ tâm bbox và to hơn hẳn bbox -> mới là lòng bóng
        cx, cy = (bx0 + bx1) // 2, (by0 + by1) // 2
        if lx <= cx <= lx + lw and ly <= cy <= ly + lh and area > best_area:
            best, best_area = i, area
    bbox_area = max(1, (bx1 - bx0) * (by1 - by0))
    # Chặn TRÊN: bóng nằm trên nền trắng (mây/trời) thì vùng liên thông "ăn lan"
    # ra cả nền -> to bất thường so với cụm chữ; khi đó coi như KHÔNG dò được
    # bóng, dùng hộp bo góc (đẹp hơn là tô trắng cả một mảng nền).
    if best and bbox_area * 0.9 <= best_area <= bbox_area * 6.0:
        mask = (labels == best)
        region[mask] = (255, 255, 255)
        ys, xs = np.nonzero(mask)
        return img_bgr, (rx0 + xs.min(), ry0 + ys.min(), rx0 + xs.max(), ry0 + ys.max()), True
    # Không dò được bóng -> nới bbox nhẹ làm hộp thoại nhân tạo.
    return img_bgr, (max(0, x0 - 4), max(0, y0 - 4), min(w, x1 + 4), min(h, y1 + 4)), False


def _fit_text(draw, text: str, box_w: int, box_h: int, font_path: str,
              max_size: int = 42) -> tuple:
    """Nhị phân cỡ chữ lớn nhất vừa (box_w, box_h). Trả (font, wrapped, w, h, overflow)."""
    from PIL import ImageFont

    lo, hi, best = 9, max_size, None
    while lo <= hi:
        mid = (lo + hi) // 2
        font = ImageFont.truetype(font_path, mid)
        avg_w = font.getlength("nhâg") / 4 or mid * 0.55
        wrapped = textwrap.fill(text, width=max(1, int(box_w / avg_w)))
        bb = draw.multiline_textbbox((0, 0), wrapped, font=font, align="center")
        tw, th = bb[2] - bb[0], bb[3] - bb[1]
        if tw <= box_w and th <= box_h:
            best = (font, wrapped, tw, th, False)
            lo = mid + 1
        else:
            hi = mid - 1
    if best:
        return best
    font = ImageFont.truetype(font_path, 9)
    wrapped = textwrap.fill(text, width=max(1, int(box_w / max(1, font.getlength("n")))))
    bb = draw.multiline_textbbox((0, 0), wrapped, font=font, align="center")
    return font, wrapped, bb[2] - bb[0], bb[3] - bb[1], True   # overflow=True


def _render_page(img_path: Path, items: list[dict], out_path: Path) -> int:
    """Tô bóng + đặt chữ Việt căn giữa. Trả số cụm bị TRÀN (cho QC)."""
    import cv2
    import numpy as np
    from PIL import Image, ImageDraw

    img = cv2.imdecode(np.fromfile(str(img_path), dtype=np.uint8), cv2.IMREAD_COLOR)
    boxes = []
    for it in items:
        img, area, is_bubble = _whiten_bubble(img, it["bbox"])
        boxes.append((area, is_bubble))

    pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(pil, "RGBA")
    font_path = str(pdfkit.pick_font()[0])
    overflow = 0
    for it, (area, is_bubble) in zip(items, boxes):
        ax0, ay0, ax1, ay1 = area
        bw, bh = max(8, ax1 - ax0 - 6), max(8, ay1 - ay0 - 6)
        if not is_bubble:
            # chữ trên nền vẽ: hộp bo góc trắng mờ để vẫn thấy tranh phía sau
            draw.rounded_rectangle(area, radius=8, fill=(255, 255, 255, 225))
        font, wrapped, tw, th, ovf = _fit_text(draw, it["vi"], bw, bh, font_path)
        overflow += int(ovf)
        cx, cy = (ax0 + ax1) / 2, (ay0 + ay1) / 2
        draw.multiline_text((cx - tw / 2, cy - th / 2), wrapped, font=font,
                            fill=(20, 20, 20, 255), align="center")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pil.save(str(out_path))
    return overflow


# --------------------------------------------------------------------------- #
# Handler
# --------------------------------------------------------------------------- #
def run(job: JobRecord, progress) -> None:
    params = job.params
    src_dir = Path(str(params.get("folder") or "").strip())
    if not src_dir.exists() or not src_dir.is_dir():
        raise ValueError(f"Không thấy thư mục ảnh: {src_dir}")
    pages = sorted(p for p in src_dir.iterdir() if p.suffix.lower() in _IMAGE_EXTS)
    if not pages:
        raise ValueError(f"Thư mục {src_dir} không có ảnh (.jpg/.png/.webp).")

    title = str(params.get("title") or src_dir.parent.name or src_dir.name)
    chapter = src_dir.name
    target = str(params.get("target") or "vi")
    langs = _OCR_LANGS.get(str(params.get("source_lang") or "zh"), _OCR_LANGS["zh"])

    series_dir = settings.outputs_dir / "comic" / _slug(title)
    out_dir = series_dir / chapter
    out_dir.mkdir(parents=True, exist_ok=True)
    job.artifacts_dir = str(out_dir)

    ckpt_path = out_dir / "checkpoint.json"
    ckpt: dict = {}
    if ckpt_path.exists():
        try:
            ckpt = json.loads(ckpt_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            ckpt = {}

    # Glossary bền theo BỘ truyện (mọi chapter dùng chung).
    gloss_path = series_dir / "glossary.json"
    glossary: dict[str, str] = {}
    if gloss_path.exists():
        glossary = json.loads(gloss_path.read_text(encoding="utf-8"))

    n = len(pages)
    progress(2, f"{n} trang — nạp model OCR ({'+'.join(langs)})")
    _get_reader(langs)   # nạp 1 lần trước cho progress không khựng ở trang 1

    total_overflow = 0
    first_texts: list[str] = []
    for i, page in enumerate(pages):
        out_page = out_dir / f"{page.stem}_vi.png"
        pct = 5 + int(85 * i / n)
        if str(page.name) in ckpt and out_page.exists():
            progress(pct, f"Trang {i + 1}/{n}: xong từ trước (checkpoint)")
            continue
        if job_queue.is_cancelled(job.id):
            raise JobCancelled()

        progress(pct, f"Trang {i + 1}/{n}: OCR")
        items = _ocr_page(page, langs)
        texts = [it["text"] for it in items]

        # Glossary dựng 1 lần từ thoại 3 trang đầu (nếu chưa có).
        if not glossary and not gloss_path.exists():
            first_texts.extend(texts)
            if i >= min(2, n - 1):
                progress(pct, "Chốt glossary tên riêng (1 lần, tầng smart)")
                glossary = _build_glossary(first_texts, target)
                gloss_path.write_text(
                    json.dumps(glossary, ensure_ascii=False, indent=2), encoding="utf-8"
                )

        progress(pct + 1, f"Trang {i + 1}/{n}: dịch {len(texts)} cụm thoại")
        vi = _translate_page(texts, target, glossary, str(params.get("context") or ""))
        for it, v in zip(items, vi):
            it["vi"] = v

        progress(pct + 2, f"Trang {i + 1}/{n}: tô bóng + đặt chữ")
        ovf = _render_page(page, items, out_page)
        total_overflow += ovf
        ckpt[str(page.name)] = {"bubbles": len(items), "overflow": ovf, "ts": time.time()}
        ckpt_path.write_text(json.dumps(ckpt, ensure_ascii=False, indent=2),
                             encoding="utf-8")

    # Đóng PDF chapter.
    progress(93, "Đóng gói PDF chapter")
    out_pages = sorted(out_dir.glob("*_vi.png"))
    pdf_path = out_dir / f"{_slug(title)}_{chapter}.pdf"
    pdfkit.images_to_pdf(out_pages, pdf_path)

    (out_dir / "package_info.json").write_text(json.dumps({
        "title": title, "chapter": chapter, "pages_in": n,
        "pages_out": len(out_pages), "overflow_bubbles": total_overflow,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    progress(100, f"Xong {len(out_pages)}/{n} trang -> {pdf_path.name}")


# --------------------------------------------------------------------------- #
# QC truyện tranh
# --------------------------------------------------------------------------- #
def qc_comic(job: JobRecord) -> QCReport:
    art = Path(job.artifacts_dir)
    checks: list[dict] = []
    ok_all = True

    info = {}
    p = art / "package_info.json"
    if p.exists():
        info = json.loads(p.read_text(encoding="utf-8"))
    pages_in, pages_out = int(info.get("pages_in") or 0), int(info.get("pages_out") or 0)
    full = pages_in > 0 and pages_out >= pages_in
    checks.append({"name": "đủ trang", "ok": full, "note": f"{pages_out}/{pages_in}"})
    ok_all &= full

    ovf = int(info.get("overflow_bubbles") or 0)
    checks.append({"name": "chữ không tràn bóng", "ok": ovf == 0,
                   "note": f"{ovf} cụm bị tràn" if ovf else "0 cụm tràn"})
    ok_all &= (ovf == 0)

    pdfs = list(art.glob("*.pdf"))
    if pdfs:
        try:
            from pypdf import PdfReader
            n_pages = len(PdfReader(str(pdfs[0])).pages)
            checks.append({"name": "pdf mở được", "ok": n_pages == pages_out,
                           "note": f"{n_pages} trang PDF"})
            ok_all &= (n_pages == pages_out)
        except Exception as exc:  # noqa: BLE001
            checks.append({"name": "pdf mở được", "ok": False, "note": str(exc)})
            ok_all = False
    else:
        checks.append({"name": "pdf mở được", "ok": False, "note": "thiếu file PDF"})
        ok_all = False

    return QCReport(passed=bool(ok_all), checks=checks)


register_checker("comic", qc_comic)


SPEC = ToolSpec(
    name="comic.translate",
    label_vi="Dịch truyện tranh → PDF",
    description="Chỉ vào thư mục ảnh một chapter (vd đã tải bằng manga.download) — "
                 "AURA OCR từng bóng thoại, dịch bằng não cloud có glossary nhất quán "
                 "cả bộ, tô trắng lòng bóng rồi đặt chữ Việt căn giữa, đóng PDF sẵn bán.",
    product_line="comic",
    form_fields=(
        FormField(key="folder", label="Thư mục ảnh chapter",
                  placeholder=r"D:\AURA_OS_v2\data\downloads\TenTruyen\Chapter_1"),
        FormField(key="title", label="Tên bộ truyện (glossary dùng chung cả bộ)",
                  required=False),
        FormField(key="source_lang", label="Ngôn ngữ gốc", type="select",
                  default="zh", choices=("zh", "ja", "ko", "en"), required=False),
        FormField(key="target", label="Ngôn ngữ đích", type="select",
                  default="vi", choices=("vi", "en"), required=False),
        FormField(key="context", label="Bối cảnh truyện (giúp dịch hay hơn, tùy chọn)",
                  required=False, placeholder="vd: truyện tu tiên hài"),
    ),
    handler=run,
)

__all__ = ["SPEC", "run", "qc_comic"]
