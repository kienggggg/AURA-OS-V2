"""
factory/tools/video_shorts.py
=============================
video.shorts — VIDEO NGẮN DỌC (9:16) tự động từ MoneyPrinterTurbo (MPT).

Nhập 1 CHỦ ĐỀ -> MPT viết kịch bản (Gemini) -> tự tải footage Pixabay -> giọng
đọc edge-tts (free) -> phụ đề -> render video dọc. AURA chỉ điều phối: gọi CLI
của MPT (chạy trong venv RIÊNG của nó ở D:\\MoneyPrinterTurbo), rồi bê thành phẩm
về data/outputs/shorts/<slug>/.

KHÁC explainer.video (ngách Anh, engine story.video tự vẽ ảnh AI): shorts dùng
FOOTAGE THẬT Pixabay + engine MPT, mặc định TIẾNG VIỆT cho thị trường VN.

Bẫy đã biết (xem memory aura-ingest-compress):
- CLI MPT có default riêng ĐÈ config.toml -> LUÔN truyền --video-source tường minh.
- footage & Pixabay 429 đã vá trong repo MPT (bản vá local).
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

from core.config import settings
from factory import queue as job_queue
from factory.models import FormField, JobCancelled, JobRecord, ToolSpec
from factory.qc import QCReport, register_checker

# MPT cài riêng ngoài AURA (venv Py3.11 của nó) — không đụng deps AURA.
_MPT_DIR = Path(getattr(settings, "mpt_dir", r"D:\MoneyPrinterTurbo"))
_MPT_PY = _MPT_DIR / "venv" / "Scripts" / "python.exe"
_DEFAULT_VOICE = "vi-VN-HoaiMyNeural-Female"

# Mốc log MPT -> phần trăm tiến độ (để dashboard đỡ đứng hình khi render lâu).
_STAGE_PCT = [
    ("generating video script", 12, "Viết kịch bản (Gemini)"),
    ("generating video terms", 20, "Rút từ khóa tìm footage"),
    ("generating audio", 30, "Lồng giọng đọc"),
    ("generating subtitle", 40, "Tạo phụ đề"),
    ("downloading videos", 50, "Tải footage Pixabay"),
    ("combining video", 70, "Ghép footage"),
    ("generating video", 82, "Chèn phụ đề + nhạc"),
    ("encoding", 90, "Xuất video"),
]


def _slug(text: str, max_len: int = 50) -> str:
    s = re.sub(r"[^\w\-]+", "_", text, flags=re.UNICODE).strip("_")
    return s[:max_len] or "short"


def _run_mpt(topic: str, language: str, voice: str, aspect: str,
             progress, job_id: str) -> dict:
    """Gọi CLI MPT, đẩy tiến độ theo log, trả JSON kết quả (task_id, videos...)."""
    if not _MPT_PY.exists():
        raise RuntimeError(f"Không thấy MoneyPrinterTurbo tại {_MPT_PY}. "
                           "Cài lại hoặc set settings.mpt_dir.")
    cmd = [
        str(_MPT_PY), "cli.py",
        "--video-subject", topic,
        "--video-language", language,
        "--video-aspect", aspect,
        "--video-source", "pixabay",     # tường minh: CLI mặc định pexels, đè config
        "--video-count", "1",
        "--voice-name", voice,
    ]
    # PHỤ ĐỀ CHÁY VÀO HÌNH — tường minh, không phó mặc config MPT.
    # Xem lại video cũ bằng skill 'watch' (29/07): KHÔNG khung nào có chữ, dù
    # subtitle.srt vẫn nằm cạnh file mp4. Người lướt TikTok tắt tiếng thì mù hoàn toàn.
    if getattr(settings, "shorts_subtitle_enabled", True):
        cmd += [
            "--subtitle-enabled",
            # Font PHẢI có dấu tiếng Việt. Mặc định MPT là MicrosoftYaHeiBold.ttc
            # (tiếng Trung) -> dùng nó là mất dấu.
            "--font-name", str(getattr(settings, "shorts_subtitle_font",
                                       "BeVietnamPro-Bold.ttf")),
            "--font-size", str(int(getattr(settings, "shorts_subtitle_size", 72))),
            # 'center' vì TikTok che ĐÁY (tên+caption) và CẠNH PHẢI (nút tim/chia sẻ).
            "--subtitle-position", str(getattr(settings, "shorts_subtitle_position",
                                               "center")),
            "--text-fore-color", "#FFFFFF",
            # Nền mờ sau chữ: cảnh quay sáng (nền trắng) mà chữ trắng thì mất hút.
            "--subtitle-background-enabled",
            "--rounded-subtitle-background",
        ]
    else:
        cmd.append("--no-subtitle-enabled")
    env = {"PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8",
           "SYSTEMROOT": r"C:\Windows", "PATH": r"C:\Windows\System32"}
    proc = subprocess.Popen(
        cmd, cwd=str(_MPT_DIR), env=env, text=True, encoding="utf-8", errors="replace",
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=1,
    )
    result_json: dict = {}
    last_pct = 10
    buf: list[str] = []
    assert proc.stdout is not None
    for line in proc.stdout:
        buf.append(line)
        low = line.lower()
        for key, pct, step in _STAGE_PCT:
            if key in low and pct > last_pct:
                last_pct = pct
                progress(pct, step)
                break
        # dòng kết quả cuối là JSON {"task_id": ...}
        s = line.strip()
        if s.startswith('{"task_id"'):
            try:
                result_json = json.loads(s)
            except json.JSONDecodeError:
                pass
        if job_queue.is_cancelled(job_id):
            proc.terminate()
            raise JobCancelled()
    proc.wait()
    if proc.returncode != 0 or not result_json:
        tail = "".join(buf[-15:])[-800:]
        raise RuntimeError(f"MPT lỗi (mã {proc.returncode}). Log cuối:\n{tail}")
    return result_json


def run(job: JobRecord, progress) -> None:
    params = job.params
    topic = str(params.get("topic") or "").strip()
    if not topic:
        raise ValueError("Chưa nhập chủ đề video ngắn (topic).")
    language = str(params.get("language") or "vi").strip() or "vi"
    voice = str(params.get("voice") or _DEFAULT_VOICE)
    aspect = str(params.get("aspect") or "9:16")

    art_dir = settings.outputs_dir / "shorts" / _slug(topic)
    art_dir.mkdir(parents=True, exist_ok=True)
    job.artifacts_dir = str(art_dir)

    pkg_path = art_dir / "package_info.json"
    if pkg_path.exists() and (art_dir / f"{_slug(topic)}.mp4").exists():
        progress(100, "Đã có sẵn (checkpoint)")
        return

    progress(6, "Khởi động xưởng video ngắn (MoneyPrinterTurbo)")
    envelope = _run_mpt(topic, language, voice, aspect, progress, job.id)
    # cli.py in: {"task_id": ..., "result": {videos, script, subtitle_path, ...}}
    result = envelope.get("result") or {}
    result["task_id"] = envelope.get("task_id")

    # Bê thành phẩm về kho AURA (MPT lưu trong storage/tasks/<uuid>/).
    videos = result.get("videos") or []
    if not videos or not Path(videos[0]).exists():
        raise RuntimeError("MPT báo xong nhưng không thấy file video.")
    progress(94, "Chép video về kho AURA")
    out_mp4 = art_dir / f"{_slug(topic)}.mp4"
    shutil.copy2(videos[0], out_mp4)

    script = str(result.get("script") or "")
    (art_dir / "script.txt").write_text(script, encoding="utf-8")
    sub = result.get("subtitle_path")
    if sub and Path(sub).exists():
        shutil.copy2(sub, art_dir / "subtitle.srt")

    pkg = {
        "title": topic, "topic": topic, "lang": language, "voice": voice,
        "aspect": aspect, "duration_s": result.get("audio_duration"),
        "terms": result.get("terms") or [], "output": str(out_mp4),
        "script": script, "mpt_task_id": result.get("task_id"),
    }
    pkg_path.write_text(json.dumps(pkg, ensure_ascii=False, indent=2), encoding="utf-8")
    progress(100, f"Xong video ngắn '{topic}' -> {out_mp4.name}")


def qc_shorts(job: JobRecord) -> QCReport:
    """Đạt khi có package_info.json + file mp4 đủ lớn (render thành công)."""
    checks: list[dict] = []
    art = Path(job.artifacts_dir) if job.artifacts_dir else None
    pkg_ok = bool(art and (art / "package_info.json").is_file())
    checks.append({"name": "package_info.json", "ok": pkg_ok})

    mp4 = None
    if art and art.is_dir():
        mp4s = list(art.glob("*.mp4"))
        mp4 = mp4s[0] if mp4s else None
    mp4_ok = bool(mp4 and mp4.stat().st_size > 200_000)   # >200KB = có nội dung thật
    checks.append({"name": "video mp4 render đủ lớn", "ok": mp4_ok})

    return QCReport(passed=pkg_ok and mp4_ok, checks=checks)


register_checker("shorts", qc_shorts)


SPEC = ToolSpec(
    name="video.shorts",
    label_vi="Video ngắn dọc (footage thật, MoneyPrinterTurbo)",
    description="Nhập 1 chủ đề — AURA viết kịch bản, tự tải footage Pixabay, lồng "
                "giọng đọc + phụ đề, render video dọc 9:16 (TikTok/Shorts/Reels). "
                "Footage thật (không phải ảnh AI), mặc định tiếng Việt. Điều phối "
                "MoneyPrinterTurbo.",
    product_line="shorts",
    form_fields=(
        FormField(key="topic", label="Chủ đề video ngắn",
                  placeholder="5 thói quen buổi sáng giúp làm việc hiệu quả"),
        FormField(key="language", label="Ngôn ngữ", type="select",
                  default="vi", required=False, choices=("vi", "en", "zh")),
        FormField(key="voice", label="Giọng đọc (edge-tts)", type="select",
                  default=_DEFAULT_VOICE, required=False,
                  choices=("vi-VN-HoaiMyNeural-Female", "vi-VN-NamMinhNeural-Male",
                           "en-US-JennyNeural-Female", "en-US-GuyNeural-Male")),
        FormField(key="aspect", label="Tỉ lệ khung", type="select",
                  default="9:16", required=False, choices=("9:16", "16:9", "1:1")),
    ),
    handler=run,
    experimental=True,
)

__all__ = ["SPEC", "run", "qc_shorts"]
