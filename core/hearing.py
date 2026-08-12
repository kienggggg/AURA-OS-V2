"""TAI CỦA AURA — nghe file tiếng nói, chép thành chữ, chạy HOÀN TOÀN TRÊN MÁY.

Sinh ra sau 05/08/2026: Sếp gửi file ghi âm tập phỏng vấn, Claude **không nghe
được** vì skill `watch` đòi khoá Whisper API. Giờ AURA tự nghe, không cần mạng,
không cần khoá, không lộ tiếng nói của Sếp lên cloud.

Dùng Moonshine (moonshine-ai) — có **model RIÊNG cho tiếng Việt**, không phải model
đa ngữ chung. Model ~130MB, tải một lần rồi nằm cache.

Cài ở `.venv311` (giống markitdown trong core/ingest.py) vì venv chính 3.14 chưa
có wheel. Mọi lệnh ngoài đi qua _run() với CREATE_NO_WINDOW để KHÔNG nháy console.

Độ chính xác đo thật trên giọng Sếp (39s): câu thường nghe tốt, **tên riêng hay
sai** (một địa danh hai âm tiết ra thành một cụm khác hẳn; "TEKY"→"Taki"). Đủ để
nắm ý / đếm từ đệm / đo nhịp
nói; KHÔNG đủ để chép biên bản từng chữ. Đừng hứa quá với Sếp.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
_PY311 = PROJECT_ROOT / ".venv311" / "Scripts" / "python.exe"
_FFMPEG = Path.home() / ".local" / "bin" / "ffmpeg.exe"

# Định dạng âm thanh Moonshine cần: WAV PCM 16-bit, 1 kênh, 16kHz.
_RATE = 16000

_WORKER = r'''
import json, sys
# Ép stdout sang UTF-8 TRƯỚC khi in. Python 3.11 trên Windows mặc định lấy
# stdout theo bảng mã hệ thống (cp1252) khi bị bắt qua pipe; `json.dumps(...,
# ensure_ascii=False)` nhả thẳng chữ Việt nên gặp "ồ" (U+1ED3) là gãy:
#   UnicodeEncodeError: 'charmap' codec can't encode character 'ồ'
# Đo được 12/08/2026: Moonshine nghe xong 28,1 giây rồi chết ĐÚNG lúc in kết
# quả — công cụ dựng riêng cho tiếng Việt hỏng đúng vì tiếng Việt. Bên cha đã
# đọc bằng encoding="utf-8" rồi, thiếu mỗi đầu này.
sys.stdout.reconfigure(encoding="utf-8")
import moonshine_voice as mv
from moonshine_voice.transcriber import Transcriber
wav, lang = sys.argv[1], sys.argv[2]
model_path, arch = mv.get_model_for_language(lang)
samples, rate = mv.load_wav_file(wav)
tr = Transcriber(model_path, arch)
try:
    result = tr.transcribe_without_streaming(samples)
finally:
    tr.close()
lines = []
for ln in getattr(result, "lines", None) or []:
    lines.append({"t": round(float(getattr(ln, "start_time", 0.0)), 2),
                  "text": str(getattr(ln, "text", "")).strip()})
# Transcript không phải lúc nào cũng có .text -> tự ghép từ các dòng.
full = str(getattr(result, "text", "") or "").strip()
if not full:
    full = " ".join(l["text"] for l in lines if l["text"]).strip()
out = {"ok": True, "seconds": round(len(samples) / rate, 1),
       "text": full, "lines": lines}
sys.stdout.write(json.dumps(out, ensure_ascii=False))
'''


def _run(args: list[str], timeout: int) -> subprocess.CompletedProcess:
    """Chạy lệnh ngoài, ẩn cửa sổ console (bài học từ screen_time/wifi_manager)."""
    kw = {}
    if os.name == "nt":
        kw["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return subprocess.run(
        args, capture_output=True, text=True, timeout=timeout,
        encoding="utf-8", errors="replace", **kw,
    )


def available() -> bool:
    """Có đủ đồ để nghe không (venv311 + moonshine + ffmpeg)?"""
    if not _PY311.exists():
        return False
    try:
        p = _run([str(_PY311), "-c", "import moonshine_voice"], 60)
        return p.returncode == 0
    except Exception:  # noqa: BLE001
        return False


def _to_wav(src: Path, dst: Path) -> bool:
    """Đổi mọi định dạng (m4a/aac/mp3/mp4...) sang WAV 16kHz mono."""
    ff = str(_FFMPEG) if _FFMPEG.exists() else "ffmpeg"
    try:
        p = _run([ff, "-nostdin", "-y", "-i", str(src), "-vn",
                  "-ac", "1", "-ar", str(_RATE), "-c:a", "pcm_s16le",
                  str(dst), "-loglevel", "error"], 600)
        return p.returncode == 0 and dst.exists() and dst.stat().st_size > 0
    except Exception as exc:  # noqa: BLE001
        logger.warning("Đổi audio sang WAV lỗi: %s", exc)
        return False


def transcribe(path: str | Path, lang: str = "vi", timeout: int = 900) -> dict:
    """Nghe 1 file audio/video -> {ok, text, lines[{t, text}], seconds}.

    Lỗi thì trả {"ok": False, "error": "..."} — KHÔNG bịa nội dung, KHÔNG ném lỗi
    làm sập nhịp gọi.
    """
    src = Path(path)
    if not src.exists():
        return {"ok": False, "error": f"không thấy file: {src}"}
    if not _PY311.exists():
        return {"ok": False, "error": "chưa có .venv311 — cài moonshine-voice vào đó trước"}

    tmp = Path(tempfile.gettempdir()) / f"aura_hear_{os.getpid()}.wav"
    try:
        if not _to_wav(src, tmp):
            return {"ok": False, "error": "không đổi được sang WAV (thiếu ffmpeg?)"}
        try:
            p = _run([str(_PY311), "-c", _WORKER, str(tmp), lang], timeout)
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": f"nghe quá {timeout}s — file quá dài?"}
        if p.returncode != 0:
            return {"ok": False, "error": (p.stderr or "").strip()[-400:] or "lỗi không rõ"}
        try:
            return json.loads((p.stdout or "").strip())
        except ValueError:
            return {"ok": False, "error": "kết quả không đọc được"}
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


def transcribe_text(path: str | Path, lang: str = "vi") -> str:
    """Bản gọn: chỉ trả chữ. Nghe không được thì nói THẲNG là không nghe được."""
    r = transcribe(path, lang)
    if not r.get("ok"):
        return f"⚠️ Không nghe được file này: {r.get('error', '?')}"
    return r.get("text") or "(không bắt được tiếng nói nào trong file)"
