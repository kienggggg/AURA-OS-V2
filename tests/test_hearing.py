"""TAI của AURA — nghe file tiếng nói offline.

Sinh sau 05/08/2026: Sếp gửi file ghi âm tập phỏng vấn mà Claude KHÔNG nghe được
(skill watch đòi khoá Whisper API). Test này giữ hai điều: (1) nghe hỏng thì phải
NÓI THẲNG là hỏng, tuyệt đối không bịa nội dung; (2) không nháy cửa sổ console.
"""

from __future__ import annotations

import subprocess

import pytest

from core import hearing


def test_no_bare_subprocess_calls_that_flash_console():
    """CANH GÁC: mọi lệnh ngoài phải qua _run() để không bật cửa sổ đen."""
    import inspect
    src = inspect.getsource(hearing)
    assert src.count("subprocess.run") == 1, "có subprocess.run ngoài _run() -> nháy console"
    assert "CREATE_NO_WINDOW" in src


def test_run_hides_console(monkeypatch):
    seen = {}

    def fake_run(args, **kw):
        seen.update(kw)
        class R:
            returncode = 0
            stdout = ""
            stderr = ""
        return R()

    monkeypatch.setattr(hearing.subprocess, "run", fake_run)
    monkeypatch.setattr(hearing.os, "name", "nt")
    hearing._run(["x"], 5)
    assert seen.get("creationflags") is not None


def test_missing_file_says_so_not_hallucinate():
    r = hearing.transcribe("khong_ton_tai_12345.mp3")
    assert r["ok"] is False
    assert "không thấy file" in r["error"]


def test_transcribe_text_reports_failure_plainly():
    out = hearing.transcribe_text("khong_ton_tai_12345.mp3")
    assert out.startswith("⚠️"), "nghe hỏng mà không báo -> Sếp tưởng là nội dung thật"


def test_timeout_is_reported_not_swallowed(monkeypatch, tmp_path):
    src = tmp_path / "a.wav"
    src.write_bytes(b"x")
    monkeypatch.setattr(hearing, "_to_wav", lambda a, b: True)

    def boom(*a, **k):
        raise subprocess.TimeoutExpired(cmd="x", timeout=1)

    monkeypatch.setattr(hearing, "_run", boom)
    r = hearing.transcribe(src)
    assert r["ok"] is False and "quá" in r["error"]


def test_bad_wav_conversion_is_reported(monkeypatch, tmp_path):
    src = tmp_path / "a.m4a"
    src.write_bytes(b"x")
    monkeypatch.setattr(hearing, "_to_wav", lambda a, b: False)
    r = hearing.transcribe(src)
    assert r["ok"] is False and "WAV" in r["error"]


def test_worker_joins_lines_when_text_empty():
    """Transcript không phải lúc nào cũng có .text -> phải tự ghép từ các dòng."""
    assert 'full = " ".join' in hearing._WORKER


@pytest.mark.skipif(not hearing.available(), reason="chưa cài moonshine-voice ở .venv311")
def test_real_vietnamese_audio_if_available(tmp_path):
    """Nghiệm thu THẬT: dựng 1 file WAV im lặng, phải chạy trọn không nổ."""
    import wave
    wav = tmp_path / "im_lang.wav"
    with wave.open(str(wav), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
        w.writeframes(b"\x00\x00" * 16000)     # 1 giây im lặng
    r = hearing.transcribe(wav)
    assert r["ok"] is True
    assert r["seconds"] == pytest.approx(1.0, abs=0.2)
