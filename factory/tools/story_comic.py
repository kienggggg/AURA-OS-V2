"""
factory/tools/story_comic.py
=============================
story.comic — CHUYỂN THỂ một chương truyện chữ (story.factory viết) thành
TRUYỆN TRANH (giai đoạn 2 của xưởng truyện — kênh Webtoon/Facebook).

Tái dùng máy móc của comic.create (_gen_panel/_compose_page — Pollinations free
+ fallback Gemini, dàn trang + bóng thoại), thêm 2 thứ comic.create không có:

1. NHẤT QUÁN XUYÊN CHƯƠNG: hồ sơ ngoại hình nhân vật (tiếng Anh, LLM dựng 1 lần
   từ bible) + seed CỐ ĐỊNH THEO BỘ lưu bền ở story_comic/<bộ>/comic_style.json —
   mọi chương, mọi job đều vẽ cùng bộ mặt. (comic.create seed theo job id.)
2. XUẤT WEBTOON: ngoài PDF còn strip_NN.png (trang resize ngang 800px — đúng
   khổ Webtoon/Facebook, mỗi trang 1 ảnh, đăng theo thứ tự).

Checkpoint từng khung ảnh + script như comic.create — chạy lại chỉ vẽ phần thiếu.
QC dùng chung bộ 'comic' (đủ trang + chữ không tràn + PDF mở được).
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

from core.config import settings
from factory import pdfkit
from factory import queue as job_queue
from factory.models import FormField, JobCancelled, JobRecord, ToolSpec
from factory.tools.comic_create import _compose_page, _gen_panel

# Màu manhua/webtoon (Pollinations vốn trả ảnh màu đẹp — tận dụng luôn thay vì
# ép đen trắng như comic.create).
_STYLE = (", vibrant colored manhua webtoon art style, clean lineart, "
          "dramatic lighting, detailed background, no text, no watermark")
_STRIP_W = 800          # khổ ngang chuẩn Webtoon


def _slug(text: str, max_len: int = 40) -> str:
    s = re.sub(r"[^\w\-]+", "_", text, flags=re.UNICODE).strip("_")
    return s[:max_len] or "chuong"


def _read_chapter(md_path: Path) -> tuple[str, str]:
    raw = md_path.read_text(encoding="utf-8").split("─────")[0].strip()
    lines = raw.split("\n", 1)
    title = lines[0].lstrip("#* ").rstrip("* ").strip()
    return title, (lines[1].strip() if len(lines) > 1 else "")


# --------------------------------------------------------------------------- #
# 1) Hồ sơ phong cách BỀN THEO BỘ: nhân vật (look tiếng Anh) + seed cố định.
# --------------------------------------------------------------------------- #
def _load_or_build_style(series_dir: Path, bible_path: Path, series: str) -> dict:
    style_path = series_dir / "comic_style.json"
    if style_path.exists():
        return json.loads(style_path.read_text(encoding="utf-8"))

    from core.llm import CloudEngine
    bible_txt = bible_path.read_text(encoding="utf-8") if bible_path.exists() else "{}"
    system = (
        "Bạn là hoạ sĩ thiết kế nhân vật truyện tranh. Từ bible truyện dưới đây, "
        "chọn tối đa 5 nhân vật QUAN TRỌNG nhất và tả NGOẠI HÌNH mỗi người bằng "
        "TIẾNG ANH thật chi tiết, cụ thể (tuổi, tóc, mắt, trang phục, khí chất, "
        "màu sắc đặc trưng) — mô tả này sẽ LẶP NGUYÊN VĂN trong mọi khung vẽ để "
        "giữ nhân vật nhất quán. Trả JSON THUẦN: "
        "{\"characters\": [{\"name\": \"tên tiếng Việt\", \"look\": \"english "
        "appearance description\"}]}"
    )
    res = CloudEngine().complete(
        [{"role": "user", "content": bible_txt[:6000]}], system_prompt=system,
        temperature=0.4, max_tokens=1500, tier="smart",
    )
    chars: list[dict] = []
    if res.get("ok"):
        m = re.search(r"\{.*\}", str(res["text"]), re.DOTALL)
        if m:
            try:
                chars = list(json.loads(m.group(0)).get("characters") or [])
            except ValueError:
                chars = []
    style = {"characters": chars, "seed": abs(hash(series)) % 100000}
    series_dir.mkdir(parents=True, exist_ok=True)
    style_path.write_text(json.dumps(style, ensure_ascii=False, indent=2),
                          encoding="utf-8")
    return style


# --------------------------------------------------------------------------- #
# 2) Kịch bản chương -> JSON pages/panels (prompt EN + thoại VI).
# --------------------------------------------------------------------------- #
def _write_script(title: str, body: str, characters: list[dict],
                  n_pages: int) -> dict:
    from core.llm import CloudEngine
    names = ", ".join(str(c.get("name") or "") for c in characters) or "(tự đặt)"
    system = (
        "Bạn là biên kịch chuyển thể truyện chữ thành truyện tranh. Từ CHƯƠNG "
        f"truyện dưới đây, viết kịch bản đúng {n_pages} trang, mỗi trang 2-4 khung "
        "(panel), bám SÁT diễn biến chương (không bịa thêm cốt mới). Nhân vật có "
        f"sẵn: {names} — dùng ĐÚNG tên này trong prompt. Trả JSON THUẦN:\n"
        "{\"pages\": [{\"panels\": [{\"prompt\": \"mô tả CẢNH bằng TIẾNG ANH "
        "(hành động, góc máy, bối cảnh; NÊU TÊN nhân vật xuất hiện)\", "
        "\"dialogue\": \"thoại/tường thuật tiếng Việt NGẮN <=15 từ, rỗng nếu "
        "khung câm\"}]}]}\n"
        "Trang cuối phải dừng ở điểm NÉO (cliffhanger) đúng như chương gốc."
    )
    from factory import reflexion
    system += reflexion.lessons_prompt("comic")
    res = CloudEngine().complete(
        [{"role": "user", "content": f"CHƯƠNG: {title}\n\n{body[:6000]}"}],
        system_prompt=system, temperature=0.6, max_tokens=4000, tier="smart",
    )
    if not res.get("ok"):
        raise RuntimeError(f"Viết kịch bản lỗi: {res.get('error')}")
    m = re.search(r"\{.*\}", str(res["text"]), re.DOTALL)
    if not m:
        raise RuntimeError("Kịch bản trả về không có JSON.")
    script = json.loads(m.group(0))
    if not script.get("pages"):
        raise RuntimeError("Kịch bản không có trang nào.")
    return script


def _panel_prompt(panel: dict, characters: list[dict]) -> str:
    """Cảnh + mô tả nhân vật LẶP NGUYÊN VĂN (chốt nhất quán) + style màu webtoon."""
    prompt = str(panel.get("prompt") or "comic panel")
    named = [c for c in characters
             if str(c.get("name", "")).lower() in prompt.lower()]
    for c in (named or characters[:1]):
        prompt += f". {c.get('name')}: {c.get('look')}"
    return prompt + _STYLE


# --------------------------------------------------------------------------- #
# 3) Xuất Webtoon: trang -> strip 800px ngang (mỗi trang 1 ảnh, đăng lần lượt).
# --------------------------------------------------------------------------- #
def _export_strips(page_files: list[Path], out_dir: Path) -> list[Path]:
    from PIL import Image
    strips: list[Path] = []
    for i, pf in enumerate(page_files, 1):
        im = Image.open(pf).convert("RGB")
        w, h = im.size
        im = im.resize((_STRIP_W, int(h * _STRIP_W / w)))
        sp = out_dir / f"strip_{i:02d}.png"
        im.save(str(sp))
        strips.append(sp)
    return strips


def _write_guide(series_dir: Path, series_title: str) -> None:
    """HƯỚNG_DẪN_ĐĂNG_TRANH.md của bộ — liệt kê chương đã có tranh, tick dần."""
    rows = []
    for d in sorted(series_dir.glob("ch_*")):
        pkg = d / "package_info.json"
        if not pkg.is_file():
            continue
        info = json.loads(pkg.read_text(encoding="utf-8"))
        rows.append(f"- [ ] **{info.get('title', d.name)}** — dải webtoon: "
                    f"`{d}\\strip_01.png ...` | PDF: `{d}`")
    (series_dir / "HƯỚNG_DẪN_ĐĂNG_TRANH.md").write_text(
        f"# 📤 ĐĂNG TRUYỆN TRANH: {series_title}\n\n"
        "## Webtoon (webtoons.com/vi) / Facebook page\n"
        "1. Tạo series 1 lần (tên + mô tả lấy từ publish_kit của truyện chữ).\n"
        "2. Mỗi chương: upload các file `strip_NN.png` THEO THỨ TỰ.\n"
        "3. ⚠️ Khai rõ 'AI-assisted art' nếu nền tảng hỏi — tránh bị report.\n\n"
        "## Chương đã dựng (tick khi đăng xong):\n" + "\n".join(rows) + "\n",
        encoding="utf-8")


# --------------------------------------------------------------------------- #
# Handler
# --------------------------------------------------------------------------- #
def run(job: JobRecord, progress) -> None:
    params = job.params
    series = str(params.get("series") or "").strip()
    if not series:
        raise ValueError("Cần 'series' (tên thư mục bộ trong data/outputs/story/).")
    chap = int(params.get("chapter") or 1)
    n_pages = max(2, min(10, int(params.get("pages") or 5)))

    story_dir = settings.outputs_dir / "story" / _slug(series)
    md = story_dir / "chapters" / f"ch_{chap:04d}.md"
    if not md.exists():
        raise ValueError(f"Chưa thấy chương: {md}")

    series_dir = settings.outputs_dir / "story_comic" / _slug(series)
    art_dir = series_dir / f"ch_{chap:04d}"
    panels_dir = art_dir / "panels"
    panels_dir.mkdir(parents=True, exist_ok=True)
    job.artifacts_dir = str(art_dir)

    title, body = _read_chapter(md)
    if not body:
        raise ValueError("Chương rỗng.")

    # 1) Hồ sơ nhân vật + seed BỀN THEO BỘ (mọi chương chung một bộ mặt).
    progress(3, "Hồ sơ nhân vật của bộ (dựng 1 lần, dùng mọi chương)")
    style = _load_or_build_style(series_dir, story_dir / "bible.json", series)
    characters = list(style.get("characters") or [])
    seed = int(style.get("seed") or 7)

    # 2) Kịch bản chương (checkpoint).
    script_path = art_dir / "script.json"
    if script_path.exists():
        script = json.loads(script_path.read_text(encoding="utf-8"))
        progress(10, "Dùng kịch bản đã có (checkpoint)")
    else:
        progress(6, f"Chuyển thể chương {chap} thành kịch bản tranh")
        script = _write_script(title, body, characters, n_pages)
        script_path.write_text(json.dumps(script, ensure_ascii=False, indent=2),
                               encoding="utf-8")
    pages = list(script.get("pages") or [])[:n_pages]
    total_panels = sum(len(p.get("panels") or []) for p in pages) or 1

    # 3) Vẽ từng khung (checkpoint từng file, seed bộ + số khung để cảnh khác nhau).
    done = 0
    for pi, pg in enumerate(pages):
        for ki, panel in enumerate(pg.get("panels") or []):
            f = panels_dir / f"p{pi + 1:02d}_k{ki + 1}.jpg"
            if not f.exists():
                if job_queue.is_cancelled(job.id):
                    raise JobCancelled()
                progress(12 + int(66 * done / total_panels),
                         f"Vẽ khung {done + 1}/{total_panels} (trang {pi + 1})")
                src = _gen_panel(_panel_prompt(panel, characters), seed + done, f)
                time.sleep(6.0 if src == "pollinations" else 1.0)
            done += 1

    # 4) Dàn trang + bóng thoại (tái dùng comic.create).
    progress(82, "Dàn trang + bóng thoại")
    page_files: list[Path] = []
    overflow = 0
    for pi, pg in enumerate(pages):
        panels = pg.get("panels") or []
        pfiles = [panels_dir / f"p{pi + 1:02d}_k{ki + 1}.jpg"
                  for ki in range(len(panels))]
        dias = [str(p.get("dialogue") or "") for p in panels]
        out_page = art_dir / f"page_{pi + 1:02d}.png"
        overflow += _compose_page(pfiles, dias, out_page)
        page_files.append(out_page)

    # 5) PDF + dải webtoon + package_info (khớp bộ QC 'comic').
    progress(92, "Đóng PDF + xuất dải webtoon 800px")
    pdf_path = art_dir / f"{_slug(title)}.pdf"
    pdfkit.images_to_pdf(page_files, pdf_path)
    _export_strips(page_files, art_dir)
    (art_dir / "package_info.json").write_text(json.dumps({
        "title": title, "series": series, "chapter": chap,
        "pages_in": len(pages), "pages_out": len(page_files),
        "overflow_bubbles": overflow,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_guide(series_dir, series)
    progress(100, f"Xong tranh chương {chap}: {len(page_files)} trang "
                  f"+ {len(page_files)} strip webtoon")


SPEC = ToolSpec(
    name="story.comic",
    label_vi="Truyện → Truyện tranh (Webtoon)",
    description="Chuyển thể 1 chương truyện (story.factory viết) thành truyện "
                 "tranh màu: kịch bản bám chương + nhân vật NHẤT QUÁN XUYÊN "
                 "CHƯƠNG (hồ sơ ngoại hình + seed bền theo bộ) + dàn trang bóng "
                 "thoại + PDF + dải webtoon 800px sẵn đăng. Ảnh AI free "
                 "(Pollinations, fallback Gemini).",
    product_line="comic",
    form_fields=(
        FormField(key="series", label="Tên bộ (thư mục trong data/outputs/story/)",
                  placeholder="Ma_Đạo_Độc_Tôn"),
        FormField(key="chapter", label="Chương số mấy", type="number", default=1),
        FormField(key="pages", label="Số trang tranh (2-10)", type="number",
                  default=5, required=False),
    ),
    handler=run,
    experimental=True,
)

__all__ = ["SPEC", "run"]
