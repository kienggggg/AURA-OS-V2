"""
factory/tools/comic_create.py
==============================
comic.create — TẠO truyện tranh mới từ ý tưởng (THÍ NGHIỆM — tool kiếm tiền #4).

Dây chuyền: LLM tầng smart viết kịch bản JSON (trang → khung → prompt ảnh tiếng
Anh + thoại tiếng Việt) → tạo ảnh từng khung qua Pollinations.ai (FREE, không
key; đã test thật 2026-07-05) fallback Gemini image (key free sẵn có trong
litellm/keys.env) → PIL dàn trang 1/2/4 khung + bóng thoại → PDF.

VÌ SAO THÍ NGHIỆM: nhất quán nhân vật giữa các khung là điểm yếu cố hữu của
image-API-không-nhớ — giảm nhẹ bằng (a) seed cố định cả job, (b) khối mô tả
nhân vật tiếng Anh LẶP NGUYÊN VĂN trong mọi prompt. Kết quả tốt bất ngờ với
manga đen trắng, nhưng KHÔNG cam kết nhân vật giống nhau 100% giữa các khung.

Từng khung ảnh cache ra đĩa NGAY (checkpoint) — Pollinations chập chờn/rate
limit thì chạy lại chỉ tạo khung còn thiếu.
"""

from __future__ import annotations

import json
import re
import textwrap
import time
import urllib.parse
import urllib.request
from pathlib import Path

from core.config import PROJECT_ROOT, settings
from factory import pdfkit
from factory import queue as job_queue
from factory.models import FormField, JobCancelled, JobRecord, ToolSpec

_PAGE_W, _PAGE_H = 1240, 1754          # ~A4 150dpi
_MARGIN, _GUTTER = 40, 24
_STYLE_SUFFIX = ", black and white manga style, clean ink lines, screentone shading, no text, no watermark"


def _slug(text: str, max_len: int = 40) -> str:
    s = re.sub(r"[^\w\-]+", "_", text, flags=re.UNICODE).strip("_")
    return s[:max_len] or "truyen_moi"


# --------------------------------------------------------------------------- #
# 1) Kịch bản: LLM smart -> JSON {characters, pages[panels[{prompt, dialogue}]]}
# --------------------------------------------------------------------------- #
def _write_script(premise: str, n_pages: int) -> dict:
    from core.llm import CloudEngine
    system = (
        "Bạn là biên kịch truyện tranh. Từ ý tưởng của user, viết kịch bản truyện "
        f"tranh NGẮN đúng {n_pages} trang, mỗi trang 2-4 khung (panel). Trả về JSON "
        "THUẦN (không markdown):\n"
        "{\"title\": \"tên truyện tiếng Việt\",\n"
        " \"characters\": [{\"name\": \"tên\", \"look\": \"mô tả NGOẠI HÌNH chi tiết "
        "bằng TIẾNG ANH (tóc, mắt, trang phục, tuổi) — dùng lặp lại y nguyên cho mọi "
        "khung có nhân vật này\"}],\n"
        " \"pages\": [{\"panels\": [{\"prompt\": \"mô tả CẢNH bằng TIẾNG ANH cho AI vẽ "
        "(hành động, góc máy, bối cảnh; nêu TÊN nhân vật xuất hiện)\", "
        "\"dialogue\": \"thoại tiếng Việt NGẮN (<=15 từ), rỗng nếu khung câm\"}]}]}\n"
        "Cốt truyện phải có mở-thắt-kết trọn vẹn trong số trang cho phép."
    )
    from factory import reflexion
    system += reflexion.lessons_prompt("comic")
    res = CloudEngine().complete(
        [{"role": "user", "content": premise}], system_prompt=system,
        temperature=0.7, max_tokens=4000, tier="smart",
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


# --------------------------------------------------------------------------- #
# 2) Ảnh: Pollinations (free, seed cố định) -> fallback Gemini image (key free)
# --------------------------------------------------------------------------- #
def _panel_prompt(panel: dict, characters: list[dict]) -> str:
    """Prompt ảnh = cảnh + mô tả nhân vật lặp nguyên văn (chốt nhất quán)."""
    prompt = str(panel.get("prompt") or "manga panel")
    named = [c for c in characters
             if str(c.get("name", "")).lower() in prompt.lower()]
    for c in (named or characters[:1]):
        prompt += f". {c.get('name')}: {c.get('look')}"
    return prompt + _STYLE_SUFFIX


def _gen_pollinations(prompt: str, seed: int, out: Path, size: int = 768) -> None:
    url = ("https://image.pollinations.ai/prompt/" + urllib.parse.quote(prompt[:1500])
           + f"?width={size}&height={size}&seed={seed}&nologo=true")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=120) as r:
        data = r.read()
    if len(data) < 5000:
        raise RuntimeError(f"Pollinations trả ảnh quá nhỏ ({len(data)}B) — nghi lỗi.")
    out.write_bytes(data)


def _gemini_keys() -> list[str]:
    """TẤT CẢ key Gemini free từ litellm/keys.env (GEMINI_KEY_*) — để xoay khi 429."""
    keys_env = PROJECT_ROOT / "litellm" / "keys.env"
    if not keys_env.exists():
        return []
    out: list[str] = []
    for line in keys_env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("GEMINI_KEY") and "=" in line:
            v = line.split("=", 1)[1].strip()
            if v and v not in out:
                out.append(v)
    return out


def _gen_gemini(prompt: str, out: Path) -> None:
    """Sinh ảnh qua Gemini image — XOAY hết pool key (1 key 429 không được chặn cả
    fallback; bài học cùng họ với dub.py _api_pool)."""
    import base64
    keys = _gemini_keys()
    if not keys:
        raise RuntimeError("Không có GEMINI_KEY trong litellm/keys.env để fallback.")
    body = json.dumps({
        "contents": [{"parts": [{"text": f"Generate an image: {prompt}"}]}],
        "generationConfig": {"responseModalities": ["IMAGE"]},
    }).encode("utf-8")
    last: Exception | None = None
    for key in keys:
        req = urllib.request.Request(
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"gemini-2.5-flash-image:generateContent?key={key}",
            data=body, headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                resp = json.loads(r.read())
            for part in resp["candidates"][0]["content"]["parts"]:
                if "inlineData" in part:
                    out.write_bytes(base64.b64decode(part["inlineData"]["data"]))
                    return
            raise RuntimeError("Gemini không trả ảnh nào.")
        except Exception as exc:  # noqa: BLE001 — xoay key kế
            last = exc
    raise RuntimeError(f"Gemini image thất bại đủ {len(keys)} key: {last}")


def _gen_panel(prompt: str, seed: int, out: Path) -> str:
    """Tạo 1 khung, retry + fallback. Trả tên nguồn đã dùng."""
    primary = settings.image_api_primary
    order = ["pollinations", "gemini"] if primary == "pollinations" else ["gemini", "pollinations"]
    last: Exception | None = None
    for source in order:
        for attempt in range(3):
            try:
                if source == "pollinations":
                    _gen_pollinations(prompt, seed, out)
                else:
                    _gen_gemini(prompt, out)
                return source
            except Exception as exc:  # noqa: BLE001 — thử tiếp nguồn/lượt sau
                last = exc
                time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"Tạo ảnh thất bại cả 2 nguồn: {last}")


# --------------------------------------------------------------------------- #
# 3) Dàn trang + bóng thoại
# --------------------------------------------------------------------------- #
def _panel_boxes(n: int) -> list[tuple[float, float, float, float]]:
    """Toạ độ (x0,y0,x1,y1) tỉ lệ [0..1] cho n khung trên 1 trang."""
    if n <= 1:
        return [(0, 0, 1, 1)]
    if n == 2:
        return [(0, 0, 1, 0.5), (0, 0.5, 1, 1)]
    if n == 3:
        return [(0, 0, 1, 0.42), (0, 0.42, 0.5, 1), (0.5, 0.42, 1, 1)]
    return [(0, 0, 0.5, 0.5), (0.5, 0, 1, 0.5), (0, 0.5, 0.5, 1), (0.5, 0.5, 1, 1)]


def _compose_page(panel_files: list[Path], dialogues: list[str], out: Path) -> int:
    """Ghép khung vào trang + vẽ bóng thoại đáy khung. Trả số thoại bị tràn."""
    from PIL import Image, ImageDraw, ImageFont

    page = Image.new("RGB", (_PAGE_W, _PAGE_H), "white")
    draw = ImageDraw.Draw(page)
    font_path = str(pdfkit.pick_font()[0])
    boxes = _panel_boxes(len(panel_files))
    inner_w = _PAGE_W - 2 * _MARGIN
    inner_h = _PAGE_H - 2 * _MARGIN
    overflow = 0

    for pf, dia, (fx0, fy0, fx1, fy1) in zip(panel_files, dialogues, boxes):
        x0 = _MARGIN + int(fx0 * inner_w) + (_GUTTER // 2 if fx0 > 0 else 0)
        y0 = _MARGIN + int(fy0 * inner_h) + (_GUTTER // 2 if fy0 > 0 else 0)
        x1 = _MARGIN + int(fx1 * inner_w) - (_GUTTER // 2 if fx1 < 1 else 0)
        y1 = _MARGIN + int(fy1 * inner_h) - (_GUTTER // 2 if fy1 < 1 else 0)
        w, h = x1 - x0, y1 - y0

        im = Image.open(pf).convert("RGB")
        # crop giữa cho khớp tỉ lệ khung rồi resize (không méo hình)
        ratio = w / h
        iw, ih = im.size
        if iw / ih > ratio:
            nw = int(ih * ratio)
            im = im.crop(((iw - nw) // 2, 0, (iw + nw) // 2, ih))
        else:
            nh = int(iw / ratio)
            im = im.crop((0, (ih - nh) // 2, iw, (ih + nh) // 2))
        page.paste(im.resize((w, h)), (x0, y0))
        draw.rectangle([x0, y0, x1, y1], outline="black", width=4)

        dia = (dia or "").strip()
        if dia:
            fsize = max(18, min(30, h // 16))
            font = ImageFont.truetype(font_path, fsize)
            avg = font.getlength("nhâg") / 4
            wrapped = textwrap.fill(dia, width=max(6, int((w * 0.82) / avg)))
            bb = draw.multiline_textbbox((0, 0), wrapped, font=font, align="center")
            tw, th = bb[2] - bb[0], bb[3] - bb[1]
            if th > h * 0.4:
                overflow += 1
            pad = 14
            bx0 = x0 + (w - tw) / 2 - pad
            by1 = y1 - 16
            by0 = by1 - th - 2 * pad
            draw.rounded_rectangle([bx0, by0, bx0 + tw + 2 * pad, by1], radius=16,
                                   fill="white", outline="black", width=3)
            draw.multiline_text((bx0 + pad, by0 + pad), wrapped, font=font,
                                fill="black", align="center")
    out.parent.mkdir(parents=True, exist_ok=True)
    page.save(str(out))
    return overflow


# --------------------------------------------------------------------------- #
# Handler
# --------------------------------------------------------------------------- #
def run(job: JobRecord, progress) -> None:
    premise = str(job.params.get("premise") or "").strip()
    if not premise:
        raise ValueError("Chưa nhập ý tưởng truyện.")
    n_pages = max(1, min(12, int(job.params.get("pages") or 4)))
    seed = abs(hash(job.id)) % 100000

    art_dir = settings.outputs_dir / "comic_new" / job.id
    art_dir.mkdir(parents=True, exist_ok=True)
    job.artifacts_dir = str(art_dir)
    panels_dir = art_dir / "panels"
    panels_dir.mkdir(exist_ok=True)

    # 1) Kịch bản (checkpoint: script.json).
    script_path = art_dir / "script.json"
    if script_path.exists():
        script = json.loads(script_path.read_text(encoding="utf-8"))
        progress(8, "Dùng kịch bản đã có (checkpoint)")
    else:
        progress(3, "Viết kịch bản (tầng smart)")
        script = _write_script(premise, n_pages)
        script_path.write_text(json.dumps(script, ensure_ascii=False, indent=2),
                               encoding="utf-8")
    title = str(script.get("title") or "Truyện mới")
    characters = list(script.get("characters") or [])
    pages = list(script.get("pages") or [])[:n_pages]
    total_panels = sum(len(p.get("panels") or []) for p in pages) or 1

    # 2) Tạo ảnh từng khung (checkpoint từng file).
    done_panels = 0
    for pi, pg in enumerate(pages):
        for ki, panel in enumerate(pg.get("panels") or []):
            f = panels_dir / f"p{pi + 1:02d}_k{ki + 1}.jpg"
            pct = 10 + int(70 * done_panels / total_panels)
            if not f.exists():
                if job_queue.is_cancelled(job.id):
                    raise JobCancelled()
                progress(pct, f"Vẽ khung {done_panels + 1}/{total_panels} "
                              f"(trang {pi + 1})")
                src = _gen_panel(_panel_prompt(panel, characters), seed, f)
                time.sleep(6.0 if src == "pollinations" else 1.0)  # né rate limit
            done_panels += 1

    # 3) Dàn trang + 4) PDF.
    progress(84, "Dàn trang + bóng thoại")
    page_files: list[Path] = []
    total_overflow = 0
    for pi, pg in enumerate(pages):
        panels = pg.get("panels") or []
        pfiles = [panels_dir / f"p{pi + 1:02d}_k{ki + 1}.jpg" for ki in range(len(panels))]
        dias = [str(p.get("dialogue") or "") for p in panels]
        out_page = art_dir / f"page_{pi + 1:02d}.png"
        total_overflow += _compose_page(pfiles, dias, out_page)
        page_files.append(out_page)

    progress(95, "Đóng PDF")
    pdf_path = art_dir / f"{_slug(title)}.pdf"
    pdfkit.images_to_pdf(page_files, pdf_path)
    (art_dir / "package_info.json").write_text(json.dumps({
        "title": title, "chapter": "1", "pages_in": len(pages),
        "pages_out": len(page_files), "overflow_bubbles": total_overflow,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    progress(100, f"Xong '{title}' {len(page_files)} trang -> {pdf_path.name}")


SPEC = ToolSpec(
    name="comic.create",
    label_vi="Tạo truyện tranh mới từ ý tưởng",
    description="Nhập ý tưởng — AURA viết kịch bản, vẽ từng khung bằng AI ảnh free "
                 "(Pollinations, fallback Gemini), dàn trang + bóng thoại, xuất PDF. "
                 "LƯU Ý: nhân vật giữa các khung CHƯA chắc giống nhau 100% (giới hạn "
                 "của AI ảnh free) — hợp truyện ngắn phong cách manga đen trắng.",
    product_line="comic",
    form_fields=(
        FormField(key="premise", label="Ý tưởng truyện (càng chi tiết càng tốt)",
                  type="textarea",
                  placeholder="vd: chàng tu sĩ lười biếng vô tình nuốt linh đan..."),
        FormField(key="pages", label="Số trang (1-12)", type="number",
                  default=4, required=False),
    ),
    handler=run,
    experimental=True,
)

__all__ = ["SPEC", "run"]
