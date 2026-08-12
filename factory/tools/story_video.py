"""
factory/tools/story_video.py
=============================
story.video — biến MỘT CHƯƠNG truyện (story.factory viết) thành VIDEO KỂ CHUYỆN
cho YouTube (kênh nội dung GỐC, an toàn bản quyền).

Dây chuyền (ghép đồ free sẵn có, không ôm framework ngoài):
  1. Đọc chương .md (bỏ dòng donate) → cắt đoạn kể.
  2. edge-tts đọc từng đoạn (giọng vi neural) + LẤY MỐC THỜI GIAN từng câu
     (SubMaker) → nối audio + sinh .srt khớp giọng.
  3. LLM (fast) rút ~N cảnh → prompt ảnh tiếng Anh → Pollinations vẽ minh hoạ
     (free, cache từng ảnh).
  4. ffmpeg (mượn binary video_dub): slideshow ảnh khớp thời lượng giọng + khắc
     phụ đề + nhạc-nền-không (chỉ giọng) → mp4 sẵn đăng.

Checkpoint: audio/ảnh cache ra đĩa — chạy lại chỉ làm phần thiếu.
"""

from __future__ import annotations

import asyncio
import json
import re
import subprocess
import sys
import textwrap
import urllib.parse
import urllib.request
from pathlib import Path

from core.config import settings
from factory import queue as job_queue
from factory.models import FormField, JobCancelled, JobRecord, ToolSpec
from factory.qc import QCReport, register_checker
from factory.tools.video_batch import _ffmpeg_exe, _probe   # tái dùng ffmpeg của video_dub

# NHƯỜNG MÁY CHO SẾP: ffmpeg dựng video vốn ngốn CPU/RAM, máy 12GB đụng 92% là
# gõ gì cũng đơ (đo thật 2026-07-23: ffmpeg 1.16GB + 103s CPU -> laptop lag).
# Hạ ĐỘ ƯU TIÊN xuống dưới-bình-thường: video vẫn dựng, chỉ chậm hơn chút, nhưng
# Sếp dùng máy vẫn mượt. Đây là cách đúng thay vì dừng job giữa chừng.
_LOW_PRIO: int = getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0) if sys.platform == "win32" else 0
_NOWIN: dict = (
    {"creationflags": subprocess.CREATE_NO_WINDOW | _LOW_PRIO}
    if sys.platform == "win32" else {}
)
# Trần luồng ffmpeg — để dành lõi CPU cho Sếp (0 = tự quyết, dễ ăn hết lõi).
_FF_THREADS = ["-threads", "2"]
_VOICE = "vi-VN-NamMinhNeural"
_IMG_STYLE = ", cinematic digital painting, wuxia xianxia fantasy, dramatic lighting, no text"


def _slug(text: str, max_len: int = 40) -> str:
    s = re.sub(r"[^\w\-]+", "_", text, flags=re.UNICODE).strip("_")
    return s[:max_len] or "chuong"


def _read_chapter(md_path: Path) -> tuple[str, str]:
    """Trả (tựa chương, nội dung kể) — bỏ tiêu đề '#' và khối donate."""
    raw = md_path.read_text(encoding="utf-8")
    # cắt khối donate (bắt đầu bằng đường kẻ ─────)
    raw = raw.split("─────")[0].strip()
    lines = raw.split("\n", 1)
    title = lines[0].lstrip("# ").strip()
    body = lines[1].strip() if len(lines) > 1 else ""
    return title, body


def _segments(body: str, max_chars: int = 350) -> list[str]:
    """Cắt đoạn kể vừa phải cho TTS (gộp câu ngắn, tách đoạn dài)."""
    out: list[str] = []
    for para in re.split(r"\n{2,}", body):
        para = re.sub(r"\s+", " ", para).strip()
        if not para:
            continue
        while len(para) > max_chars:
            cut = para.rfind(". ", 0, max_chars)
            if cut < 80:
                cut = max_chars
            out.append(para[:cut + 1].strip())
            para = para[cut + 1:].strip()
        if para:
            out.append(para)
    return out


# --------------------------------------------------------------------------- #
# TTS từng đoạn + TỰ DỰNG phụ đề từ thời lượng (edge-tts 7.x KHÔNG nhả
# WordBoundary cho giọng Việt -> SubMaker rỗng; ta đo thời lượng từng đoạn rồi
# chia phụ đề theo tỉ lệ ký tự — chắc ăn, không phụ thuộc WordBoundary).
# --------------------------------------------------------------------------- #
def _fmt_ts(t: float) -> str:
    h, m = int(t // 3600), int((t % 3600) // 60)
    s = t % 60
    return f"{h:02d}:{m:02d}:{int(s):02d},{int((s - int(s)) * 1000):03d}"


def _sub_pieces(seg: str, max_len: int = 90) -> list[str]:
    """Cắt 1 đoạn thành các mẩu phụ đề ngắn (theo câu, rồi theo độ dài)."""
    out: list[str] = []
    for sent in re.split(r"(?<=[.!?…])\s+", seg):
        sent = sent.strip()
        while len(sent) > max_len:
            cut = sent.rfind(" ", 0, max_len)
            if cut < 40:
                cut = max_len
            out.append(sent[:cut].strip())
            sent = sent[cut:].strip()
        if sent:
            out.append(sent)
    return out or [seg]


async def _tts_all(segments: list[str], voice: str, out_mp3: Path, out_srt: Path,
                   progress, base: int, span: int) -> float:
    import edge_tts

    seg_dir = out_mp3.parent / "_seg"
    seg_dir.mkdir(exist_ok=True)
    durations: list[float] = []
    with out_mp3.open("wb") as af:
        for i, seg in enumerate(segments):
            data = b""
            for attempt in range(3):        # edge-tts thi thoảng NoAudioReceived
                try:
                    comm = edge_tts.Communicate(seg, voice)
                    buf = b""
                    async for chunk in comm.stream():
                        if chunk["type"] == "audio":
                            buf += chunk["data"]
                    if buf:
                        data = buf
                        break
                except Exception:  # noqa: BLE001
                    await asyncio.sleep(1.5 * (attempt + 1))
            seg_file = seg_dir / f"s{i:03d}.mp3"
            seg_file.write_bytes(data)
            af.write(data)
            durations.append(_mp3_duration(seg_file))
            progress(base + int(span * (i + 1) / len(segments)),
                     f"Lồng giọng đoạn {i + 1}/{len(segments)}")

    # Dựng SRT: mỗi đoạn chia thành mẩu ngắn, thời lượng chia theo tỉ lệ ký tự.
    lines: list[str] = []
    t = 0.0
    idx = 1
    for seg, dur in zip(segments, durations):
        pieces = _sub_pieces(seg)
        total = sum(len(p) for p in pieces) or 1
        for p in pieces:
            d = dur * len(p) / total
            lines += [str(idx), f"{_fmt_ts(t)} --> {_fmt_ts(t + d)}",
                      textwrap.fill(p, 46), ""]
            t += d
            idx += 1
    out_srt.write_text("\n".join(lines), encoding="utf-8")
    return sum(durations)


def _mp3_duration(path: Path) -> float:
    r = subprocess.run([str(_ffmpeg_exe()), "-hide_banner", "-i", str(path)],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=60, **_NOWIN)
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)", r.stderr or "")
    if m:
        return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    return 0.0


# --------------------------------------------------------------------------- #
# Ảnh minh hoạ: LLM rút cảnh -> Pollinations
# --------------------------------------------------------------------------- #
def _scene_prompts(title: str, body: str, n: int) -> list[str]:
    from core.llm import CloudEngine
    try:
        res = CloudEngine().complete(
            [{"role": "user", "content": f"{title}\n\n{body[:4000]}"}],
            system_prompt=(
                f"Từ chương truyện tu tiên sau, rút ĐÚNG {n} CẢNH hình ảnh tiêu biểu "
                "(mở đầu → cao trào → kết). Mỗi cảnh viết 1 PROMPT ẢNH bằng TIẾNG ANH "
                "mô tả bối cảnh/nhân vật/hành động cho AI vẽ. Trả JSON THUẦN: "
                "{\"scenes\": [\"prompt1\", ...]}. Không giải thích."),
            temperature=0.6, max_tokens=2000, tier="fast",
        )
        m = re.search(r"\{.*\}", str(res.get("text", "")), re.DOTALL)
        if m:
            sc = json.loads(m.group(0)).get("scenes") or []
            if sc:
                return [str(s) for s in sc][:n]
    except Exception:  # noqa: BLE001
        pass
    return [f"{title}, wuxia cultivation scene"] * n   # fallback


def _scene_count(dur: float, params: dict) -> int:
    """Số cảnh THEO THỜI LƯỢNG giọng — video dài -> nhiều cảnh, đổi ảnh chặt hơn
    (như quy trình 'nhiều cảnh khớp thoại'). params['scenes'] có thì ưu tiên."""
    if params.get("scenes"):
        return max(3, min(80, int(params["scenes"])))
    per = float(getattr(settings, "story_video_seconds_per_scene", 16.0))
    cap = int(getattr(settings, "story_video_max_scenes", 30))
    return max(5, min(cap, round(dur / max(per, 5.0))))


def _make_thumbnail(series_title: str, chap_title: str, img: Path, out: Path) -> None:
    """Thumbnail 1280x720: ảnh cảnh mạnh + dải tối + TIÊU ĐỀ chữ to giật (tên bộ +
    tựa chương). Bìa video quyết định click -> đáng đầu tư (bài học từ video kiếm tiền)."""
    from PIL import Image, ImageDraw, ImageFont
    from factory import pdfkit

    W, H = 1280, 720
    base = Image.open(img).convert("RGB")
    iw, ih = base.size
    scale = max(W / iw, H / ih)
    base = base.resize((int(iw * scale), int(ih * scale)))
    base = base.crop(((base.size[0] - W) // 2, (base.size[1] - H) // 2,
                      (base.size[0] + W) // 2, (base.size[1] + H) // 2))
    draw = ImageDraw.Draw(base, "RGBA")
    # dải tối đáy để chữ nổi
    band = Image.new("RGBA", (W, 300), (0, 0, 0, 0))
    bd = ImageDraw.Draw(band)
    for y in range(300):
        bd.line([(0, y), (W, y)], fill=(0, 0, 0, int(200 * y / 300)))
    base.paste(Image.alpha_composite(
        base.crop((0, H - 300, W, H)).convert("RGBA"), band).convert("RGB"),
        (0, H - 300))

    reg, bold = pdfkit.pick_font()
    import textwrap as _tw

    def _outlined(text: str, font, y: int, wrap: int, fill="white") -> int:
        for line in _tw.wrap(text, width=wrap):
            bb = draw.textbbox((0, 0), line, font=font)
            x = (W - (bb[2] - bb[0])) // 2
            for dx in (-3, 3):
                for dy in (-3, 3):
                    draw.text((x + dx, y + dy), line, font=font, fill="black")
            draw.text((x, y), line, font=font, fill=fill)
            y += (bb[3] - bb[1]) + 14
        return y

    if series_title:
        _outlined(series_title.upper(), ImageFont.truetype(str(bold), 44), 36, 26,
                  fill="#FFD54A")
    # Tiêu đề: cỡ chữ + độ rộng wrap TỰ CO theo độ dài để không tràn đáy khung.
    n = len(chap_title)
    tsize, twrap = (72, 18) if n <= 32 else (56, 24) if n <= 60 else (44, 30)
    lines = len(_tw.wrap(chap_title, width=twrap))
    y0 = max(H - 40 - lines * (tsize + 14), 330)
    _outlined(chap_title, ImageFont.truetype(str(bold), tsize), y0, twrap)
    out.parent.mkdir(parents=True, exist_ok=True)
    base.save(str(out))


def _series_title(story_dir: Path) -> str:
    b = story_dir / "bible.json"
    if b.is_file():
        try:
            return str(json.loads(b.read_text(encoding="utf-8")).get("title") or "").strip()
        except (ValueError, OSError):
            pass
    return ""


def _gen_image(prompt: str, seed: int, out: Path) -> None:
    """Pollinations (retry) -> FALLBACK Gemini image (Pollinations hay 530/rate-limit)."""
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
        except Exception:  # noqa: BLE001
            pass
        time.sleep(4 * (attempt + 1))
    from factory.tools.comic_create import _gen_gemini
    _gen_gemini(full, out)


# --------------------------------------------------------------------------- #
# Ghép video (ffmpeg). Hai đường: MOTION (Ken Burns + xfade + nhạc nền) và
# SIMPLE (slideshow tĩnh, dự phòng). run() gọi _render — tự thử motion rồi lùi
# về simple nếu lỗi, để autopilot không bao giờ gãy.
# --------------------------------------------------------------------------- #
_SUB_STYLE = ("force_style='FontName=Arial,FontSize=18,PrimaryColour=&H00FFFFFF,"
              "OutlineColour=&H00000000,Outline=2,Shadow=1,MarginV=40'")


def _pick_music() -> Path | None:
    """Chọn 1 track nhạc nền không bản quyền trong story_video_music_dir (nếu có).
    Trống thì trả None (video chỉ có giọng — không lỗi)."""
    d = getattr(settings, "story_video_music_dir", None)
    if not d:
        return None
    d = Path(d)
    if not d.is_dir():
        return None
    tracks = sorted(p for p in d.iterdir()
                    if p.suffix.lower() in (".mp3", ".m4a", ".aac", ".ogg", ".wav"))
    return tracks[0] if tracks else None


def _render_simple(images: list[Path], audio: Path, srt: Path, dur: float,
                   out: Path) -> None:
    """Slideshow tĩnh (bản gốc) — dự phòng khi motion lỗi. Chạy trong art_dir,
    tham chiếu file bằng tên để né escape ':' '\\' của subtitles trên Windows."""
    work = out.parent
    per = max(2.0, dur / max(1, len(images)))
    lines = []
    for img in images:
        lines.append(f"file '{img.name if img.parent == work else img.as_posix()}'")
        lines.append(f"duration {per:.3f}")
    last = images[-1]
    lines.append(f"file '{last.name if last.parent == work else last.as_posix()}'")
    (work / "slides.txt").write_text("\n".join(lines), encoding="utf-8")

    vf = ("scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720,"
          f"subtitles={srt.name}:{_SUB_STYLE}")
    cmd = [str(_ffmpeg_exe()), "-y", "-f", "concat", "-safe", "0", "-i", "slides.txt",
           "-i", audio.name, "-vf", vf, "-c:v", "libx264", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-shortest", *_FF_THREADS, out.name]
    subprocess.run(cmd, check=True, capture_output=True, timeout=1200,
                   cwd=str(work), **_NOWIN)


def _render_motion(images: list[Path], audio: Path, srt: Path, dur: float,
                   out: Path) -> None:
    """Ken Burns (pan/zoom chậm mỗi ảnh) + chuyển cảnh xfade + nhạc nền nhẹ dưới
    giọng. Toàn ffmpeg (không GPU). Ảnh phóng lên 2K trước để zoompan hết giật."""
    work = out.parent
    fps = 30
    xf = 0.7                       # thời lượng chuyển cảnh (giây)
    n = len(images)
    # Độ dài mỗi cảnh sao cho tổng (đã trừ phần chồng xfade) ≈ thời lượng giọng.
    per = max((dur + (n - 1) * xf) / max(1, n), xf + 1.3)
    frames = max(int(round(per * fps)), fps)
    lf = frames / fps              # độ dài cảnh thực tế (giây), để tính offset xfade
    music = _pick_music()
    trans = ["fade", "dissolve", "fadeblack", "slideleft", "slideright", "smoothup"]

    parts: list[str] = []
    for i in range(n):
        # Phóng ảnh lên 2560x1440 rồi zoompan xuống 720p -> zoom mượt, không giật.
        parts.append(
            f"[{i}:v]scale=2560:1440:force_original_aspect_ratio=increase,"
            f"crop=2560:1440,zoompan=z='min(zoom+0.0009,1.15)':d={frames}:"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1280x720:fps={fps},"
            f"setsar=1[v{i}]"
        )
    if n == 1:
        last = "v0"
    else:
        prev = "v0"
        for k in range(1, n):
            off = k * (lf - xf)                      # offset dồn cho chuỗi xfade
            t = trans[(k - 1) % len(trans)]
            lbl = f"x{k}"
            parts.append(f"[{prev}][v{k}]xfade=transition={t}:duration={xf}:"
                         f"offset={off:.3f}[{lbl}]")
            prev = lbl
        last = prev
    parts.append(f"[{last}]subtitles={srt.name}:{_SUB_STYLE}[vout]")

    narr = n                                          # chỉ số input giọng
    if music:
        parts.append(f"[{n + 1}:a]volume=0.14,afade=t=in:st=0:d=2[bg];"
                     f"[{narr}:a][bg]amix=inputs=2:duration=first:"
                     f"dropout_transition=0[aout]")
        amap = "[aout]"
    else:
        amap = f"{narr}:a"

    cmd = [str(_ffmpeg_exe()), "-y"]
    for img in images:
        cmd += ["-i", img.name if img.parent == work else str(img)]
    cmd += ["-i", audio.name]
    if music:
        cmd += ["-stream_loop", "-1", "-i", str(music)]
    cmd += ["-filter_complex", ";".join(parts), "-map", "[vout]", "-map", amap,
            "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-r", str(fps), "-shortest", *_FF_THREADS, out.name]
    subprocess.run(cmd, check=True, capture_output=True, timeout=1800,
                   cwd=str(work), **_NOWIN)


def _render(images: list[Path], audio: Path, srt: Path, dur: float, out: Path) -> None:
    """Dựng video: ưu tiên MOTION (Ken Burns + xfade + nhạc), lỗi thì lùi SIMPLE."""
    if getattr(settings, "story_video_motion", True) and images:
        try:
            _render_motion(images, audio, srt, dur, out)
            return
        except Exception:  # noqa: BLE001 — motion hỏng KHÔNG được làm gãy job
            import logging
            logging.getLogger(__name__).warning(
                "story.video: render motion lỗi, lùi về slideshow tĩnh.", exc_info=True)
    _render_simple(images, audio, srt, dur, out)


# --------------------------------------------------------------------------- #
# Handler
# --------------------------------------------------------------------------- #
def run(job: JobRecord, progress) -> None:
    params = job.params
    series = str(params.get("series") or "").strip()
    if not series:
        raise ValueError("Cần 'series' (tên thư mục bộ trong data/outputs/story/).")
    chap = int(params.get("chapter") or 1)
    voice = str(params.get("voice") or _VOICE)

    story_dir = settings.outputs_dir / "story" / _slug(series)
    md = story_dir / "chapters" / f"ch_{chap:04d}.md"
    if not md.exists():
        raise ValueError(f"Chưa thấy chương: {md}")

    art_dir = settings.outputs_dir / "story_video" / _slug(series) / f"ch_{chap:04d}"
    (art_dir / "img").mkdir(parents=True, exist_ok=True)
    job.artifacts_dir = str(art_dir)

    title, body = _read_chapter(md)
    segments = _segments(body)
    if not segments:
        raise ValueError("Chương rỗng, không có gì để kể.")

    # 1) TTS + phụ đề khớp giọng.
    progress(5, f"Lồng giọng chương {chap} ({len(segments)} đoạn)")
    audio = art_dir / "narration.mp3"
    srt = art_dir / "narration.srt"
    # cần cả audio LẪN srt (không rỗng) — thiếu 1 trong 2 thì lồng lại.
    if not audio.exists() or not srt.exists() or srt.stat().st_size == 0:
        asyncio.run(_tts_all(segments, voice, audio, srt, progress, 5, 45))
    dur = _mp3_duration(audio)
    if job_queue.is_cancelled(job.id):
        raise JobCancelled()

    # 2) Ảnh minh hoạ — SỐ CẢNH theo thời lượng (nhiều cảnh, đổi ảnh chặt theo thoại).
    n_scenes = _scene_count(dur, params)
    progress(55, f"Rút {n_scenes} cảnh + vẽ ảnh")
    prompts = _scene_prompts(title, body, n_scenes)
    images: list[Path] = []
    seed = abs(hash(f"{series}-{chap}")) % 100000
    for i, p in enumerate(prompts):
        if job_queue.is_cancelled(job.id):
            raise JobCancelled()
        f = art_dir / "img" / f"scene_{i + 1:02d}.jpg"
        try:
            _gen_image(p, seed + i, f)
        except Exception:  # noqa: BLE001 — 1 ảnh lỗi: dùng ảnh trước cho đỡ trống
            if images:
                f = images[-1]
            else:
                continue
        images.append(f)
        progress(55 + int(30 * (i + 1) / len(prompts)), f"Vẽ cảnh {i + 1}/{len(prompts)}")
        import time as _tm
        _tm.sleep(2.5)          # né rate-limit Pollinations khi dựng liên tục
    if not images:
        raise RuntimeError("Không vẽ được ảnh nào cho video.")

    # 3) Thumbnail có chữ tít (bìa video hút click) — lấy cảnh giữa (thường mạnh).
    try:
        hero = images[min(len(images) // 3, len(images) - 1)]
        _make_thumbnail(_series_title(story_dir), title, hero,
                        art_dir / "thumbnail.png")
    except Exception:  # noqa: BLE001 — thumbnail lỗi không được làm gãy job
        pass

    # 4) Ghép video.
    progress(88, "Ghép video (giọng + ảnh + phụ đề)")
    out = art_dir / f"{_slug(title)}_ch{chap:04d}.mp4"
    _render(images, audio, srt, dur, out)
    (art_dir / "package_info.json").write_text(json.dumps({
        "title": title, "chapter": chap, "duration_s": dur,
        "scenes": len(images), "output": str(out),
        "thumbnail": str(art_dir / "thumbnail.png"),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    progress(100, f"Xong video kể chuyện chương {chap} ({len(images)} cảnh) -> {out.name}")


# --------------------------------------------------------------------------- #
# QC riêng cho video kể chuyện. TRƯỚC ĐÂY dùng chung qc_video của dây chuyền
# LỒNG TIẾNG (đòi checkpoint per-item mà story.video không có) -> mọi video
# kể chuyện bị trượt oan, kẹt needs_review vĩnh viễn. Bộ này kiểm đúng thứ
# story.video tạo ra: package_info + mp4 + audio + khớp thời lượng giọng.
# --------------------------------------------------------------------------- #
def qc_story_video(job: JobRecord) -> QCReport:
    art = Path(job.artifacts_dir or "")
    pkg = art / "package_info.json"
    if not pkg.is_file():
        return QCReport(passed=False, checks=[
            {"name": "package", "ok": False,
             "note": "Chưa có package_info.json — video chưa dựng xong."},
        ])
    checks: list[dict] = []
    all_ok = True
    try:
        info = json.loads(pkg.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        return QCReport(passed=False, checks=[
            {"name": "package", "ok": False, "note": f"package_info hỏng: {exc}"},
        ])

    out = Path(str(info.get("output") or ""))
    if not out.is_file() or out.stat().st_size < 1_000_000:
        checks.append({"name": "file", "ok": False,
                       "note": "Thiếu file mp4 hoặc < 1MB."})
        all_ok = False
    else:
        checks.append({"name": "file", "ok": True,
                       "note": f"{out.name} ({out.stat().st_size / 1e6:.1f}MB)"})
        try:
            dur, has_audio = _probe(out)
            want = float(info.get("duration_s") or 0)
            # -shortest cắt theo giọng; cho xê dịch 5s hoặc 5% (video dài).
            dur_ok = (want == 0) or (abs(dur - want) <= max(5.0, want * 0.05))
            checks.append({
                "name": "video", "ok": dur_ok and has_audio,
                "note": f"duration {dur:.0f}s (giọng {want:.0f}s), "
                        f"audio={'có' if has_audio else 'KHÔNG'}",
            })
            if not (dur_ok and has_audio):
                all_ok = False
        except Exception as exc:  # noqa: BLE001 — probe lỗi ghi nhận, không sập QC
            checks.append({"name": "probe", "ok": False, "note": str(exc)})
            all_ok = False

    srt = art / "narration.srt"
    srt_ok = srt.is_file() and srt.stat().st_size > 0
    checks.append({"name": "subtitle", "ok": srt_ok,
                   "note": "narration.srt " + ("OK" if srt_ok else "THIẾU/rỗng")})
    if not srt_ok:
        all_ok = False
    return QCReport(passed=all_ok, checks=checks)


register_checker("story_video", qc_story_video)


SPEC = ToolSpec(
    name="story.video",
    label_vi="Truyện → Video kể chuyện (YouTube)",
    description="Biến 1 chương truyện (story.factory viết) thành video kể chuyện: "
                 "giọng đọc AI + ảnh minh hoạ AI + phụ đề khớp giọng, xuất mp4 sẵn "
                 "đăng YouTube. Nội dung gốc = an toàn bản quyền.",
    product_line="story_video",
    form_fields=(
        FormField(key="series", label="Tên bộ (thư mục trong data/outputs/story/)",
                  placeholder="Đấu_La_Đồng_Nhân"),
        FormField(key="chapter", label="Chương số mấy", type="number", default=1),
        FormField(key="voice", label="Giọng đọc", type="select", default=_VOICE,
                  choices=("vi-VN-NamMinhNeural", "vi-VN-HoaiMyNeural"), required=False),
        FormField(key="scenes", label="Số cảnh (ảnh minh hoạ)", type="number",
                  default=8, required=False),
    ),
    handler=run,
    experimental=True,
)

__all__ = ["SPEC", "run"]
