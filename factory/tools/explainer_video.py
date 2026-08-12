"""
factory/tools/explainer_video.py
=================================
explainer.video — VIDEO FACELESS TIẾNG ANH cho THỊ TRƯỜNG MỸ (CPM cao gấp ~10
lần VN). Mô hình từ 2 video "kiếm tiền YouTube bằng AI" (2026-07-12): ngách hẹp
kiểu "giải thích" (Kinh Thánh/lịch sử/bí ẩn/khoa học), kịch bản Anh + ảnh cảnh
AI + giọng đọc Anh + thumbnail -> đăng kênh Mỹ.

TÁI DÙNG TRỌN engine story.video (TTS, cắt đoạn, số cảnh theo thời lượng, render
Ken Burns + nhạc, thumbnail chữ tít, QC). Chỉ khác: nguồn là CHỦ ĐỀ (không phải
chương truyện), kịch bản + giọng + phụ đề TIẾNG ANH.

⚠️ Kịch bản BẮT nói SỰ THẬT, không bịa (chính sách YouTube — 2 video đều nhấn).
"""

from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from pathlib import Path

from core.config import settings
from factory import queue as job_queue
from factory.qc import register_checker
from factory.models import FormField, JobCancelled, JobRecord, ToolSpec
# Tái dùng engine story.video (đừng viết lại):
from factory.tools.story_video import (
    _make_thumbnail, _mp3_duration, _render, _scene_count, _segments, _tts_all,
    qc_story_video,
)

_VOICE = "en-US-ChristopherNeural"          # giọng nam kể chuyện Mỹ
_IMG_STYLE = (", cinematic documentary still, photorealistic, dramatic lighting, "
              "epic atmosphere, highly detailed, no text, no watermark")


def _slug(text: str, max_len: int = 50) -> str:
    s = re.sub(r"[^\w\-]+", "_", text, flags=re.UNICODE).strip("_")
    return s[:max_len] or "video"


def _write_script(topic: str, niche: str, words: int) -> tuple[str, str]:
    """LLM viết kịch bản narration TIẾNG ANH — hook mạnh, cấu trúc giữ chân, SỰ THẬT."""
    from core.llm import CloudEngine
    from factory import reflexion
    system = (
        f"You are a scriptwriter for a faceless YouTube channel in the niche: "
        f"'{niche or 'educational explainer'}', targeting a US/English audience. "
        f"Write an engaging narration script of about {words} words about the topic "
        "below. RULES: (1) a strong hook in the first 2 sentences; (2) clear, "
        "retention-friendly structure with smooth transitions; (3) warm, confident "
        "documentary-narrator tone; (4) STRICTLY FACTUAL — do NOT invent facts, "
        "quotes, or statistics (YouTube penalizes misinformation); (5) end with a "
        "short call to like and subscribe. Return PURE JSON: "
        "{\"title\": \"a clickable English title, <=90 chars\", "
        "\"script\": \"the full narration as plain prose, NO scene labels or headings\"}"
    )
    system += reflexion.lessons_prompt("explainer")
    res = CloudEngine().complete(
        [{"role": "user", "content": f"Topic: {topic}"}], system_prompt=system,
        temperature=0.7, max_tokens=max(3000, words * 3), tier="smart",
    )
    if not res.get("ok"):
        raise RuntimeError(f"Viết kịch bản lỗi: {res.get('error')}")
    m = re.search(r"\{.*\}", str(res["text"]), re.DOTALL)
    if not m:
        raise RuntimeError("Kịch bản trả về không có JSON.")
    d = json.loads(m.group(0))
    title = str(d.get("title") or topic)[:95]
    script = str(d.get("script") or "").strip()
    if len(script) < 200:
        raise RuntimeError("Kịch bản quá ngắn.")
    return title, script


def _scene_prompts(title: str, body: str, n: int) -> list[str]:
    from core.llm import CloudEngine
    try:
        res = CloudEngine().complete(
            [{"role": "user", "content": f"{title}\n\n{body[:4500]}"}],
            system_prompt=(
                f"From this narration, extract EXACTLY {n} vivid VISUAL scenes (in "
                "order, beginning to end). Write each as an English image-generation "
                "prompt: describe the setting, subject, action, mood for an AI to "
                "paint a cinematic still. Return PURE JSON: {\"scenes\": [\"...\"]}."),
            temperature=0.6, max_tokens=2500, tier="fast",
        )
        m = re.search(r"\{.*\}", str(res.get("text", "")), re.DOTALL)
        if m:
            sc = json.loads(m.group(0)).get("scenes") or []
            if sc:
                return [str(s) for s in sc][:n]
    except Exception:  # noqa: BLE001
        pass
    return [f"{title}, cinematic documentary scene"] * n


def _gen_image(prompt: str, seed: int, out: Path) -> None:
    """Pollinations (retry) -> FALLBACK Gemini image. Pollinations hay 530 quá tải/
    rate-limit -> không có fallback thì cả video mất trắng ảnh."""
    if out.exists():
        return
    import time
    full = (prompt + _IMG_STYLE)[:1500]
    url = ("https://image.pollinations.ai/prompt/" + urllib.parse.quote(full)
           + f"?width=1280&height=720&seed={seed}&nologo=true")
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=120) as r:
                data = r.read()
            if len(data) >= 5000:
                out.write_bytes(data)
                return
        except Exception:  # noqa: BLE001 — thử lại / fallback
            pass
        time.sleep(4 * (attempt + 1))
    # Pollinations nghẽn -> Gemini image (xoay 6 key free, tái dùng của comic_create).
    from factory.tools.comic_create import _gen_gemini
    _gen_gemini(full, out)


def run(job: JobRecord, progress) -> None:
    import asyncio
    params = job.params
    topic = str(params.get("topic") or "").strip()
    if not topic:
        raise ValueError("Chưa nhập chủ đề video (topic).")
    niche = str(params.get("niche") or getattr(settings, "explainer_niche", "")).strip()
    voice = str(params.get("voice") or getattr(settings, "explainer_voice", _VOICE))
    words = max(400, min(3000, int(params.get("words")
                                   or getattr(settings, "explainer_words", 900))))

    art_dir = settings.outputs_dir / "explainer" / _slug(topic)
    (art_dir / "img").mkdir(parents=True, exist_ok=True)
    job.artifacts_dir = str(art_dir)

    # 1) Kịch bản (checkpoint).
    sp = art_dir / "script.json"
    if sp.exists():
        d = json.loads(sp.read_text(encoding="utf-8"))
        title, script = str(d.get("title") or topic), str(d.get("script") or "")
        progress(10, "Dùng kịch bản đã có (checkpoint)")
    else:
        progress(4, "Viết kịch bản tiếng Anh (tầng smart)")
        title, script = _write_script(topic, niche, words)
        sp.write_text(json.dumps({"title": title, "script": script},
                                 ensure_ascii=False, indent=2), encoding="utf-8")

    segments = _segments(script)
    if not segments:
        raise ValueError("Kịch bản rỗng.")

    # 2) TTS Anh + phụ đề.
    progress(15, f"Lồng giọng Anh ({len(segments)} đoạn)")
    audio, srt = art_dir / "narration.mp3", art_dir / "narration.srt"
    if not audio.exists() or not srt.exists() or srt.stat().st_size == 0:
        asyncio.run(_tts_all(segments, voice, audio, srt, progress, 15, 45))
    dur = _mp3_duration(audio)
    if job_queue.is_cancelled(job.id):
        raise JobCancelled()

    # 3) Ảnh cảnh — số cảnh theo thời lượng (nhiều cảnh, đỡ tĩnh).
    n = _scene_count(dur, params)
    progress(55, f"Rút {n} cảnh + vẽ ảnh")
    prompts = _scene_prompts(title, script, n)
    images: list[Path] = []
    seed = abs(hash(topic)) % 100000
    for i, p in enumerate(prompts):
        if job_queue.is_cancelled(job.id):
            raise JobCancelled()
        f = art_dir / "img" / f"scene_{i + 1:02d}.jpg"
        try:
            _gen_image(p, seed + i, f)
        except Exception:  # noqa: BLE001 — 1 ảnh lỗi: dùng ảnh trước
            if images:
                f = images[-1]
            else:
                continue
        images.append(f)
        progress(55 + int(28 * (i + 1) / len(prompts)), f"Vẽ cảnh {i + 1}/{len(prompts)}")
        import time as _tm
        _tm.sleep(2.5)          # né rate-limit Pollinations khi dựng liên tục
    if not images:
        raise RuntimeError("Không vẽ được ảnh nào.")

    # 4) Thumbnail (tên ngách + tiêu đề) + 5) render.
    try:
        hero = images[min(len(images) // 3, len(images) - 1)]
        _make_thumbnail(niche or "EXPLAINED", title, hero, art_dir / "thumbnail.png")
    except Exception:  # noqa: BLE001
        pass
    progress(88, "Ghép video (giọng + ảnh + phụ đề)")
    out = art_dir / f"{_slug(title)}.mp4"
    _render(images, audio, srt, dur, out)
    (art_dir / "package_info.json").write_text(json.dumps({
        "title": title, "topic": topic, "niche": niche, "duration_s": dur,
        "scenes": len(images), "output": str(out),
        "thumbnail": str(art_dir / "thumbnail.png"), "lang": "en",
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    progress(100, f"Xong video Anh '{title}' ({len(images)} cảnh) -> {out.name}")


register_checker("explainer", qc_story_video)   # cùng cấu trúc: package + mp4 + srt


SPEC = ToolSpec(
    name="explainer.video",
    label_vi="Video faceless tiếng Anh (thị trường Mỹ)",
    description="Nhập chủ đề — AURA viết kịch bản TIẾNG ANH (bắt sự thật), vẽ ảnh "
                 "cảnh AI, đọc giọng Mỹ, ghép video + thumbnail cho kênh faceless "
                 "thị trường Mỹ (CPM cao). Tái dùng engine story.video (Ken Burns + "
                 "nhạc + nhiều cảnh). Nội dung gốc, an toàn bản quyền.",
    product_line="explainer",
    form_fields=(
        FormField(key="topic", label="Chủ đề video (cụ thể)",
                  placeholder="The mystery of the Nazca Lines"),
        FormField(key="niche", label="Ngách kênh (giọng/khung)", required=False,
                  placeholder="Ancient mysteries explained"),
        FormField(key="voice", label="Giọng đọc (edge-tts Anh)", type="select",
                  default=_VOICE, required=False,
                  choices=("en-US-ChristopherNeural", "en-US-GuyNeural",
                           "en-US-JennyNeural", "en-US-AriaNeural")),
        FormField(key="words", label="Độ dài kịch bản (từ)", type="number",
                  default=900, required=False),
    ),
    handler=run,
    experimental=True,
)

__all__ = ["SPEC", "run"]
