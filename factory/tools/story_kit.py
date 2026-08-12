"""
factory/tools/story_kit.py
===========================
story.kit — dựng "BỘ ĐỒ NGHỀ XUẤT BẢN" cho một bộ truyện để đăng Wattpad cho
nhanh (giai đoạn đăng tay): văn án hút người đọc + ảnh bìa đúng chuẩn + tags.

Nhìn các bước đăng Wattpad, thứ tốn công/khó nhất là VĂN ÁN và ẢNH BÌA. story.kit
lo sẵn cả hai (LLM viết văn án theo bible; Pollinations vẽ bìa + PIL in tựa +
bút danh), để lúc đăng chỉ việc up ảnh + dán văn án + dán chương.

Xuất ra data/outputs/story/<bộ>/publish_kit/: van_an.md, cover.png (512×800
chuẩn Wattpad), tags.txt.
"""

from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from io import BytesIO
from pathlib import Path

from core.config import settings
from factory import pdfkit
from factory.models import FormField, JobRecord, ToolSpec

_COVER_W, _COVER_H = 512, 800   # chuẩn ảnh bìa Wattpad
_STYLE = ", cinematic key visual, xianxia wuxia fantasy, dramatic lighting, highly detailed, no text"


def _slug(text: str, max_len: int = 40) -> str:
    s = re.sub(r"[^\w\-]+", "_", text, flags=re.UNICODE).strip("_")
    return s[:max_len] or "bo_truyen"


def _gen_meta(bible: dict, sample: str) -> dict:
    """LLM viết văn án + gợi ý thể loại/tags cho Wattpad."""
    from core.llm import CloudEngine
    main = bible.get("main", {})
    imm_goal = main.get("immediate_goal") or main.get("goal") or ""
    cheat_desc = main.get("cheat_manifestation") or main.get("cheat") or ""
    ctx = (f"Tên: {bible.get('title')}\nLogline: {bible.get('logline')}\n"
           f"Thế giới: {bible.get('world')}\nNhân vật chính: {main.get('name')} — "
           f"Mục tiêu trước mắt: {imm_goal}; Lợi thế: {cheat_desc}\nMở đầu:\n{sample[:2500]}")
    res = CloudEngine().complete(
        [{"role": "user", "content": ctx}],
        system_prompt=(
            "Bạn là biên tập viên Wattpad. Trả JSON THUẦN (không markdown):\n"
            "{\"van_an\": \"VĂN ÁN tiếng Việt ~150-220 từ: mở bằng câu hook giật, nêu "
            "nhân vật + xung đột + điều đặt cược sinh tử, KẾT bằng câu gợi tò mò. Giọng cuốn "
            "hút, không spoil bí mật hay cái kết\",\n"
            " \"genre\": \"1 thể loại Wattpad hợp nhất (Fantasy/Adventure/Action...)\",\n"
            " \"tags\": [\"8-12 tag tiếng Việt + Anh không dấu # để dễ tìm, vd tutien, "
            "dongnhan, xuyenkhong, fantasy...\"]}"),
        temperature=0.7, max_tokens=1500, tier="fast",
    )
    m = re.search(r"\{.*\}", str(res.get("text", "")), re.DOTALL)
    if not m:
        raise RuntimeError("Không tạo được văn án (LLM trả sai định dạng).")
    return json.loads(m.group(0))


def _make_cover(bible: dict, pen: str, out: Path) -> Path:
    """Bìa 512×800: ảnh Pollinations dọc + dải mờ + tựa truyện + bút danh."""
    from PIL import Image, ImageDraw

    main = bible.get("main", {})
    prompt = (f"portrait poster of {main.get('look', 'a young cultivator')}, "
              f"{bible.get('world', 'xianxia world')}" + _STYLE)
    url = ("https://image.pollinations.ai/prompt/" + urllib.parse.quote(prompt[:1200])
           + f"?width={_COVER_W}&height={_COVER_H}&seed={abs(hash(pen)) % 99999}&nologo=true")
    # Pollinations hay 530/quá tải — retry vài lần, rớt thì FALLBACK Gemini image
    # (tái dùng _gen_gemini của comic_create, key free sẵn có).
    import time
    data = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=120) as r:
                data = r.read()
            if len(data) > 5000:
                break
        except Exception:  # noqa: BLE001
            time.sleep(4 * (attempt + 1))
    if not data or len(data) < 5000:
        try:
            from factory.tools.comic_create import _gen_gemini
            tmp = out.parent / "_cover_raw.png"
            _gen_gemini(prompt + f" Vertical portrait orientation, {_COVER_W}x{_COVER_H}.", tmp)
            data = tmp.read_bytes()
        except Exception:  # noqa: BLE001 — Gemini cũng nghẽn -> fallback cuối bên dưới
            data = None
    if not data or len(data) < 5000:
        # FALLBACK CUỐI (0 API): mượn ảnh cảnh đã vẽ cho video của CHÍNH bộ này
        # (data/outputs/story_video/<bộ>/*/img/) — đã test làm bìa rất ổn.
        series_slug = out.parent.parent.name
        scenes = sorted((settings.outputs_dir / "story_video" / series_slug)
                        .glob("*/img/*.jpg"))
        if not scenes:
            raise RuntimeError("Cả Pollinations lẫn Gemini đều nghẽn và chưa có ảnh "
                               "cảnh nào của bộ này — thử lại sau.")
        data = scenes[0].read_bytes()
    img = Image.open(BytesIO(data)).convert("RGB")
    # phủ khít 512×800 (crop giữa)
    iw, ih = img.size
    scale = max(_COVER_W / iw, _COVER_H / ih)
    img = img.resize((int(iw * scale), int(ih * scale)))
    iw, ih = img.size
    img = img.crop(((iw - _COVER_W) // 2, (ih - _COVER_H) // 2,
                    (iw + _COVER_W) // 2, (ih + _COVER_H) // 2))

    draw = ImageDraw.Draw(img, "RGBA")
    from PIL import ImageFont
    font_path = str(pdfkit.pick_font()[1])   # bold
    # dải tối phía dưới cho chữ nổi
    draw.rectangle([0, _COVER_H - 220, _COVER_W, _COVER_H], fill=(0, 0, 0, 150))

    title = str(bible.get("title") or "")
    # nhị phân cỡ chữ tựa cho vừa bề ngang (căn giữa THỦ CÔNG — multiline_text
    # không nhận anchor='mm' ở nhiều bản Pillow).
    import textwrap
    size = 46
    f = ImageFont.truetype(font_path, size)
    wrapped = title
    while size >= 24:
        f = ImageFont.truetype(font_path, size)
        wrapped = textwrap.fill(title, width=max(8, int(_COVER_W * 1.7 / size)))
        bb = draw.multiline_textbbox((0, 0), wrapped, font=f, align="center")
        if bb[2] - bb[0] <= _COVER_W - 40:
            break
        size -= 2
    bb = draw.multiline_textbbox((0, 0), wrapped, font=f, align="center")
    tw, th = bb[2] - bb[0], bb[3] - bb[1]
    draw.multiline_text(((_COVER_W - tw) // 2, _COVER_H - 175), wrapped, font=f,
                        fill="white", align="center", stroke_width=2, stroke_fill="black")
    if pen:
        pf = ImageFont.truetype(font_path, 24)
        pt = f"— {pen} —"
        pb = draw.textbbox((0, 0), pt, font=pf)
        draw.text(((_COVER_W - (pb[2] - pb[0])) // 2, _COVER_H - 52), pt, font=pf,
                  fill=(255, 230, 150), stroke_width=1, stroke_fill="black")
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(out), quality=90)
    return out


def run(job: JobRecord, progress) -> None:
    series = str(job.params.get("series") or "").strip()
    if not series:
        raise ValueError("Cần 'series' (tên thư mục bộ trong data/outputs/story/).")
    story_dir = settings.outputs_dir / "story" / _slug(series)
    bible_path = story_dir / "bible.json"
    if not bible_path.exists():
        raise ValueError(f"Chưa có bible cho bộ này: {bible_path}")
    bible = json.loads(bible_path.read_text(encoding="utf-8"))

    kit_dir = story_dir / "publish_kit"
    kit_dir.mkdir(parents=True, exist_ok=True)
    job.artifacts_dir = str(kit_dir)

    chaps = sorted((story_dir / "chapters").glob("ch_*.md"))
    sample = chaps[0].read_text(encoding="utf-8")[:3000] if chaps else ""

    progress(15, "Viết văn án + gợi ý tags")
    meta = _gen_meta(bible, sample)
    pen = str(getattr(settings, "author_pen_name", "") or "")
    tags = meta.get("tags") or []

    (kit_dir / "van_an.md").write_text(
        f"# {bible.get('title')}\n\n*Tác giả: {pen}*\n\n"
        f"**Thể loại:** {meta.get('genre', '')}\n\n"
        f"{meta.get('van_an', '')}\n", encoding="utf-8")
    (kit_dir / "tags.txt").write_text(
        " ".join(f"#{str(t).lstrip('#')}" for t in tags), encoding="utf-8")

    progress(45, "Vẽ ảnh bìa 512×800")
    cover_ok = True
    try:
        cover = _make_cover(bible, pen, kit_dir / "cover.png")
    except Exception as exc:  # noqa: BLE001 — bìa lỗi (Pollinations sập) không nên
        cover, cover_ok = None, False  # vứt cả kit; văn án+tags đã lưu, chạy lại vẽ bìa
        progress(90, f"Văn án+tags xong; BÌA lỗi (chạy lại sau): {exc}")

    (kit_dir / "kit_info.json").write_text(json.dumps({
        "title": bible.get("title"), "pen_name": pen, "genre": meta.get("genre"),
        "tags": tags, "cover": str(cover) if cover else None, "cover_ok": cover_ok,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    if cover_ok:
        progress(100, f"Xong bộ kit đăng Wattpad -> {kit_dir}")
    else:
        progress(100, "Xong văn án+tags; chạy lại story.kit để vẽ bìa khi Pollinations ổn")


SPEC = ToolSpec(
    name="story.kit",
    label_vi="Bộ đồ nghề đăng truyện (văn án + bìa + tags)",
    description="Dựng sẵn văn án hút người đọc + ảnh bìa 512×800 chuẩn Wattpad + tags "
                 "cho một bộ truyện — để lúc đăng tay chỉ việc up ảnh, dán văn án, dán "
                 "chương. Chạy 1 lần/bộ (hoặc lại khi muốn đổi bìa/văn án).",
    product_line="novel",
    form_fields=(
        FormField(key="series", label="Tên bộ (thư mục trong data/outputs/story/)",
                  placeholder="Đấu_La_Đồng_Nhân"),
    ),
    handler=run,
)

__all__ = ["SPEC", "run"]
