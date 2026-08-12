"""
factory/tools/video_batch.py
=============================
video.factory — DÂY CHUYỀN dịch + lồng tiếng video hàng loạt (tool kiếm tiền #1).

Mỗi dòng input = 1 URL (bilibili/youtube/...) hoặc 1 đường dẫn file local.
Từng video đi qua 3 khâu: TẢI (yt-dlp, thư viện trong venv chính) → LỒNG TIẾNG
(subprocess video_dub/dub.py qua .venv riêng của nó — pipeline đã ship thật ở
github.com/kienggggg/auto-video-dub) → QC (ffmpeg probe). Thành phẩm về
data/outputs/video/<job_id>/.

Chống nhiễu bilibili: query string kiểu ?spm_id_from=...&trackid=web_related_...
là mã theo dõi "video liên quan" — GIỮ NGUYÊN có thể làm yt-dlp lạc video. Ta
CẮT SẠCH query, chỉ giữ path /video/BVxxxx/, và ghi lại title đã tải vào
checkpoint để đối chiếu. HTTP 412 của bilibili được né bằng header trình duyệt
(UA + Referer) — đã test thật 2026-07-05.

Checkpoint <artifacts>/checkpoint.json: {url: {title, source, output, duration}}
— AURA sập giữa chừng thì video đã xong không phải làm lại.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from core.config import settings
from factory import queue as job_queue
from factory.models import FormField, JobCancelled, JobRecord, ToolSpec
from factory.qc import QCReport, register_checker

_CACHE_DIR = settings.factory_dir / "cache" / "video"

# Header trình duyệt — bilibili trả 412 Precondition Failed cho client "trần".
_HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Referer": "https://www.bilibili.com/",
}

_NOWIN: dict = (
    {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}
)


def _clean_url(raw: str) -> str:
    """Cắt query/fragment theo dõi (spm_id_from/trackid...) khỏi URL bilibili —
    giữ nguyên URL các trang khác (query của youtube ?v= là BẮT BUỘC)."""
    raw = raw.strip()
    parts = urlsplit(raw)
    if "bilibili.com" in parts.netloc:
        return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
    return raw


def _slug(text: str, max_len: int = 40) -> str:
    s = re.sub(r"[^\w\-]+", "_", text, flags=re.UNICODE).strip("_")
    return s[:max_len] or "video"


def _load_checkpoint(art_dir: Path) -> dict:
    p = art_dir / "checkpoint.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 — checkpoint hỏng thì làm lại từ đầu
            return {}
    return {}


def _save_checkpoint(art_dir: Path, data: dict) -> None:
    (art_dir / "checkpoint.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _cookie_opts(prefer_browser: bool = True) -> dict:
    """Cookie cho yt-dlp: ƯU TIÊN mượn tươi từ trình duyệt Chromium (CocCoc —
    không dính App-Bound như Chrome, phiên luôn mới, khỏi xuất tay), rơi về
    file cookies.txt khi không đọc được (trình duyệt đang khoá DB...)."""
    if prefer_browser and settings.ytdlp_cookies_browser:
        return {"cookiesfrombrowser": ("chrome", settings.ytdlp_cookies_browser, None, None)}
    if settings.ytdlp_cookies:
        return {"cookiefile": str(settings.ytdlp_cookies)}
    return {}


def _expand_channel(url: str, limit: int) -> list[str]:
    """'Lang thang': link KÊNH/danh sách (space.bilibili.com/<uid>/video, playlist...)
    -> danh sách URL video mới nhất (flat, không tải). Lỗi -> ném lên cho job báo rõ."""
    import yt_dlp

    opts = {
        "quiet": True, "no_warnings": True,
        "extract_flat": True, "playlistend": max(1, min(30, limit)),
        "http_headers": _HTTP_HEADERS, **_cookie_opts(),
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    out: list[str] = []
    for e in info.get("entries") or []:
        u = e.get("url") or ""
        if not u and e.get("id"):
            u = f"https://www.bilibili.com/video/{e['id']}/"
        if u:
            out.append(u)
    return out


def _download(url: str, item_label: str, progress, base_pct: int, span: int) -> tuple[Path, str, float]:
    """Tải 1 video qua yt-dlp (thư viện). Trả (file, title, duration_s)."""
    import yt_dlp

    _CACHE_DIR.mkdir(parents=True, exist_ok=True)

    def _hook(d: dict) -> None:
        if d.get("status") == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            got = d.get("downloaded_bytes") or 0
            if total:
                frac = got / total
                progress(base_pct + int(frac * span), f"{item_label}: tải {frac * 100:.0f}%")

    base_opts = {
        "quiet": True,
        "no_warnings": True,
        "format": settings.ytdlp_format,
        "outtmpl": str(_CACHE_DIR / "%(id)s.%(ext)s"),
        "http_headers": _HTTP_HEADERS,
        "progress_hooks": [_hook],
        "noplaylist": True,
        # merge yêu cầu ffmpeg — mượn binary trong .venv của video_dub. imageio_ffmpeg
        # đặt tên file kiểu 'ffmpeg-win-x86_64-v7.1.exe' (KHÔNG PHẢI 'ffmpeg.exe'), nên
        # phải trỏ ĐÚNG FILE — trỏ vào thư mục cha thì yt-dlp không tìm thấy binary.
        "ffmpeg_location": str(_ffmpeg_exe()),
    }

    info = None
    last_exc: Exception | None = None
    for prefer_browser in (True, False):        # cookie trình duyệt -> file -> chịu
        opts = {**base_opts, **_cookie_opts(prefer_browser)}
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
            break
        except Exception as exc:  # noqa: BLE001 — thử nguồn cookie kế
            last_exc = exc
            if not prefer_browser:
                raise
    if info is None:
        raise RuntimeError(f"Tải thất bại: {last_exc}")
    path = Path(ydl.prepare_filename(info))
    # Sau merge dash (video+audio) đuôi có thể đổi (vd .mp4) — dò file thật.
    if not path.exists():
        candidates = sorted(_CACHE_DIR.glob(f"{info['id']}.*"),
                            key=lambda p: p.stat().st_size, reverse=True)
        if not candidates:
            raise FileNotFoundError(f"yt-dlp báo xong nhưng không thấy file cho {url}")
        path = candidates[0]
    return path, str(info.get("title") or info.get("id")), float(info.get("duration") or 0)


def _ffmpeg_exe() -> Path:
    """ffmpeg trong .venv của video_dub (imageio-ffmpeg ship sẵn binary)."""
    binaries = settings.videodub_python.parent.parent / "Lib" / "site-packages" \
        / "imageio_ffmpeg" / "binaries"
    for exe in sorted(binaries.glob("ffmpeg-*.exe")):
        return exe
    raise FileNotFoundError(f"Không thấy ffmpeg trong {binaries} — kiểm video_dub/.venv.")


# Map mốc log của dub.py -> % trong khâu lồng tiếng ([1/4] bóc lời ... HOÀN TẤT).
_STAGE_RE = re.compile(r"\[(\d)/4\]")


def _dub(src: Path, out: Path, params: dict, job_id: str,
         item_label: str, progress, base_pct: int, span: int,
         glossary_path: Path | None = None,
         context_file: Path | None = None) -> None:
    """Chạy dub.py qua venv riêng, map log stage -> progress; Hủy = kill subprocess."""
    cmd = [
        str(settings.videodub_python), str(settings.videodub_script),
        "--input", str(src), "--output", str(out),
        "--target", str(params.get("target") or "vi"),
        "--model", str(params.get("model") or settings.videodub_whisper_model),
        "--bg-mode", str(params.get("bg_mode") or "music"),
    ]
    if params.get("voice"):
        cmd += ["--voice", str(params["voice"])]
    if not params.get("burn_sub", True):
        cmd += ["--no-burn-sub"]
    if glossary_path is not None:
        cmd += ["--glossary", str(glossary_path)]
    if context_file is not None and context_file.is_file():
        cmd += ["--context-file", str(context_file)]

    # dub.py in log tiếng Việt; stdout là PIPE thì Python con mặc định cp1252
    # trên Windows -> UnicodeEncodeError. PYTHONUTF8=1 ép UTF-8 toàn cục cho con.
    import os
    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
    proc = subprocess.Popen(
        cmd, cwd=str(settings.videodub_script.parent), env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace", **_NOWIN,
    )
    tail: list[str] = []
    assert proc.stdout is not None
    for line in proc.stdout:
        line = line.strip()
        if not line:
            continue
        tail.append(line)
        if len(tail) > 30:
            tail.pop(0)
        m = _STAGE_RE.search(line)
        if m:
            k = int(m.group(1))
            progress(base_pct + int(span * (0.1 + 0.7 * k / 4)),
                     f"{item_label}: {line[:90]}")
        elif "HOÀN TẤT" in line or "XONG" in line:
            progress(base_pct + int(span * 0.95), f"{item_label}: dựng xong, đang QC")
        # Ranh giới rẻ nhất để tôn trọng nút Hủy khi đang lồng tiếng.
        if job_queue.is_cancelled(job_id):
            proc.kill()
            raise JobCancelled()
    code = proc.wait()
    if code != 0:
        raise RuntimeError(
            f"dub.py exit {code}. Log cuối: " + " | ".join(tail[-5:])
        )


def run(job: JobRecord, progress) -> None:
    lines = [l for l in str(job.params.get("urls", "")).splitlines() if l.strip()]
    if not lines:
        raise ValueError("Chưa nhập URL/đường dẫn video nào.")

    # LANG THANG: dòng nào là link KÊNH (space.bilibili.com) thì bung thành các
    # tập mới nhất (channel_limit tập, mặc định 5) rồi xử lý như thường.
    limit = int(job.params.get("channel_limit") or 5)
    expanded: list[str] = []
    for l in lines:
        if "space.bilibili.com" in l:
            progress(1, f"Đi dạo kênh, gom {limit} video mới nhất...")
            eps = _expand_channel(_clean_url(l), limit)
            if not eps:
                raise ValueError(f"Kênh không thấy video nào: {l[:60]}")
            expanded.extend(eps)
        else:
            expanded.append(l)
    lines = expanded

    # PHÂN LOẠI THƯ MỤC THEO BỘ (user yêu cầu 2026-07-06): nhập "series" thì mọi
    # tập về CHUNG outputs/video/<tên bộ>/ (dễ tìm, dễ đăng), checkpoint chung theo
    # URL -> tập đã dịch ở job trước tự được bỏ qua ở job sau. Bỏ trống -> gom vào
    # outputs/video/khac/ thay vì thư mục mã job vô nghĩa.
    series = str(job.params.get("series") or "").strip()
    art_dir = settings.outputs_dir / "video" / (_slug(series) if series else "khac")
    art_dir.mkdir(parents=True, exist_ok=True)
    job.artifacts_dir = str(art_dir)
    ckpt = _load_checkpoint(art_dir)

    # Glossary KHOÁ TÊN theo BỘ: mọi tập cùng bộ (kể cả job khác, ngày khác) dùng
    # chung 1 sổ tên -> tên nhân vật KHÔNG lệch giữa các tập.
    if series:
        glossary_path = settings.outputs_dir / "video" / "_glossary" / f"{_slug(series)}.json"
    else:
        glossary_path = art_dir / "glossary.json"

    n = len(lines)
    for i, raw in enumerate(lines):
        url = _clean_url(raw)
        item_label = f"Video {i + 1}/{n}"
        base = int(i * 100 / n)
        span = int(100 / n)

        entry = ckpt.get(url) or {}
        if entry.get("output") and Path(entry["output"]).exists():
            progress(base + span, f"{item_label}: đã xong từ trước (checkpoint)")
            continue
        if job_queue.is_cancelled(job.id):
            raise JobCancelled()

        # 1) Nguồn: file local dùng thẳng; URL thì tải (0-25% của item).
        if Path(url).exists():
            src, title = Path(url), Path(url).stem
            try:
                dur, _ = _probe(src)   # QC cần duration nguồn để so với đầu ra
            except Exception:  # noqa: BLE001 — probe lỗi thì QC bỏ qua so duration
                dur = 0.0
            entry.update({"source": str(src), "title": title, "duration": dur})
            ckpt[url] = entry
            _save_checkpoint(art_dir, ckpt)
            progress(base + int(span * 0.25), f"{item_label}: dùng file local")
        elif entry.get("source") and Path(entry["source"]).exists():
            src, title, dur = Path(entry["source"]), entry.get("title", ""), \
                float(entry.get("duration") or 0)
            progress(base + int(span * 0.25), f"{item_label}: đã tải từ trước")
        else:
            progress(base, f"{item_label}: bắt đầu tải")
            src, title, dur = _download(url, item_label, progress, base, int(span * 0.25))
            entry.update({"source": str(src), "title": title, "duration": dur})
            ckpt[url] = entry
            _save_checkpoint(art_dir, ckpt)

        if job_queue.is_cancelled(job.id):
            raise JobCancelled()

        # 2) Lồng tiếng (25-95% của item) — kèm TRÍ NHỚ CỐT TRUYỆN của bộ (nếu có).
        out = art_dir / f"{_slug(title)}_{job.params.get('target', 'vi')}.mp4"
        story_file = (glossary_path.with_suffix(".story.txt")
                      if series and glossary_path is not None else None)
        _dub(src, out, job.params, job.id, item_label, progress,
             base + int(span * 0.25), int(span * 0.70),
             glossary_path=glossary_path, context_file=story_file)

        entry["output"] = str(out)
        entry["finished_ts"] = time.time()
        ckpt[url] = entry
        _save_checkpoint(art_dir, ckpt)

        # 3) Cập nhật trí nhớ cốt truyện từ phụ đề tập vừa xong (chỉ khi theo BỘ).
        if story_file is not None:
            progress(base + span - 1, f"{item_label}: cập nhật trí nhớ cốt truyện")
            _update_story(story_file, out.with_suffix(".srt"), title)
        progress(base + span, f"{item_label}: xong -> {out.name}")


def _srt_text(srt_path: Path, max_chars: int = 6000) -> str:
    """Bóc phần lời thoại từ .srt (bỏ số thứ tự + timestamp)."""
    if not srt_path.exists():
        return ""
    lines = []
    for line in srt_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.isdigit() or "-->" in line:
            continue
        lines.append(line)
    return "\n".join(lines)[:max_chars]


def _update_story(story_file: Path, srt_path: Path, episode_title: str) -> None:
    """TRÍ NHỚ CỐT TRUYỆN của bộ: LLM (tier fast) gộp tóm tắt cũ + phụ đề tập vừa
    dịch thành tóm tắt mới ≤200 từ — tập sau dịch với đầy đủ diễn biến, quan hệ
    nhân vật, cách xưng hô. Lỗi gì cũng nuốt (thiếu trí nhớ vẫn dịch được)."""
    try:
        dialogue = _srt_text(srt_path)
        if len(dialogue) < 100:
            return
        prev = story_file.read_text(encoding="utf-8").strip() if story_file.exists() else ""
        from core.llm import CloudEngine
        res = CloudEngine().complete(
            [{"role": "user", "content":
              (f"TÓM TẮT HIỆN TẠI của bộ truyện:\n{prev or '(chưa có)'}\n\n"
               f"PHỤ ĐỀ TẬP MỚI ({episode_title}):\n{dialogue}")}],
            system_prompt=(
                "Cập nhật TÓM TẮT CỐT TRUYỆN cho bộ phim dài tập: gộp tóm tắt hiện tại "
                "với diễn biến tập mới thành MỘT tóm tắt ≤200 từ tiếng Việt, ưu tiên "
                "(1) quan hệ + cách xưng hô giữa các nhân vật, (2) mưu tính/bí mật đang "
                "mở, (3) diễn biến mới nhất. Chỉ trả về tóm tắt, không giải thích."),
            temperature=0.3, max_tokens=800, tier="fast",
        )
        if res.get("ok") and str(res.get("text", "")).strip():
            story_file.parent.mkdir(parents=True, exist_ok=True)
            story_file.write_text(str(res["text"]).strip(), encoding="utf-8")
    except Exception:  # noqa: BLE001 — trí nhớ hỏng không được chặn dây chuyền
        pass


# ------------------------------------------------------------------------- #
# QC video: probe bằng chính ffmpeg của video_dub (parse stderr `-i`).
# ------------------------------------------------------------------------- #
_DUR_RE = re.compile(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)")


def _probe(path: Path) -> tuple[float, bool]:
    """(duration_s, has_audio) — ffmpeg -i in ra stderr, exit code luôn 1 (no output)."""
    r = subprocess.run(
        [str(_ffmpeg_exe()), "-hide_banner", "-i", str(path)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=60, **_NOWIN,
    )
    info = r.stderr or ""
    m = _DUR_RE.search(info)
    dur = 0.0
    if m:
        dur = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    return dur, "Audio:" in info


def qc_video(job: JobRecord) -> QCReport:
    checks: list[dict] = []
    ckpt = _load_checkpoint(Path(job.artifacts_dir)) if job.artifacts_dir else {}
    if not ckpt:
        return QCReport(passed=False, checks=[
            {"name": "checkpoint", "ok": False, "note": "Không có checkpoint — chưa video nào xong."},
        ])
    all_ok = True
    for url, entry in ckpt.items():
        out = Path(entry.get("output") or "")
        label = entry.get("title") or url
        if not out.exists() or out.stat().st_size < 1_000_000:
            checks.append({"name": f"file: {label}", "ok": False,
                           "note": "Thiếu file đầu ra hoặc < 1MB."})
            all_ok = False
            continue
        try:
            dur, has_audio = _probe(out)
        except Exception as exc:  # noqa: BLE001 — probe lỗi ghi nhận, không sập QC
            checks.append({"name": f"probe: {label}", "ok": False, "note": str(exc)})
            all_ok = False
            continue
        src_dur = float(entry.get("duration") or 0)
        # dub.py CỐ Ý kéo giãn video khi câu dịch dài (tối đa ~1.8x/đoạn) — cho
        # phép dài hơn nguồn tới 60%, nhưng không được NGẮN hơn quá 5%.
        dur_ok = (src_dur == 0) or (0.95 * src_dur <= dur <= 1.6 * src_dur)
        checks.append({
            "name": f"video: {label}", "ok": dur_ok and has_audio,
            "note": f"duration {dur:.0f}s (nguồn {src_dur:.0f}s), audio={'có' if has_audio else 'KHÔNG'}",
        })
        if not (dur_ok and has_audio):
            all_ok = False
    return QCReport(passed=all_ok, checks=checks)


register_checker("video", qc_video)


SPEC = ToolSpec(
    name="video.factory",
    label_vi="Dịch + lồng tiếng video (hàng loạt)",
    description="Dán danh sách link video nước ngoài (bilibili/youtube...) hoặc đường "
                 "dẫn file — AURA tự tải, dịch, lồng tiếng thuyết minh, khắc phụ đề, "
                 "QC rồi xuất mp4 sẵn đăng. Mỗi dòng 1 video.",
    product_line="video",
    form_fields=(
        FormField(key="urls",
                  label="Danh sách video (mỗi dòng 1 URL video / đường dẫn file / LINK KÊNH)",
                  type="textarea",
                  placeholder="https://www.bilibili.com/video/BV.../\nhttps://space.bilibili.com/<uid>/video  ← dán link kênh là tự gom các tập mới",
                  help_text="Link kênh (space.bilibili.com) sẽ được bung thành các video mới nhất."),
        FormField(key="channel_limit", label="Số tập mới nhất lấy từ mỗi link kênh",
                  type="number", default=5, required=False),
        FormField(key="series", label="Tên bộ (khoá tên nhân vật nhất quán mọi tập)",
                  required=False, placeholder="vd: Lý Cẩu Tu Tiên",
                  help_text="Cùng một tên bộ ở các lần chạy khác nhau sẽ dùng chung sổ "
                            "tên riêng — tên nhân vật không lệch giữa các tập."),
        FormField(key="target", label="Ngôn ngữ đích", type="select",
                  default="vi", choices=("vi", "en"), required=False),
        FormField(key="model", label="Cỡ model nghe (medium = nghe tên chuẩn hơn, chậm hơn)",
                  type="select", default="small",
                  choices=("tiny", "base", "small", "medium"), required=False),
        FormField(key="bg_mode", label="Âm nền", type="select", default="music",
                  choices=("music", "full", "none"), required=False,
                  help_text="music = tách bỏ giọng gốc giữ nhạc (chậm hơn); full = giữ nguyên tiếng gốc nhỏ; none = chỉ giọng thuyết minh"),
        FormField(key="burn_sub", label="Khắc phụ đề vào hình", type="checkbox",
                  default=True, required=False),
    ),
    handler=run,
)

__all__ = ["SPEC", "run", "qc_video"]
