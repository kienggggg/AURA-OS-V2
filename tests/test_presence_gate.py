"""CANH GÁC: AURA không bao giờ được che/tắt màn hình khi Sếp đang họp.

Sinh sau sự cố 05/08/2026: Health Guard phủ khiên đen GIỮA BUỔI PHỎNG VẤN TEKY
lúc Sếp đang share màn hình Google Meet -> nhà tuyển dụng phê "chưa kiểm soát
được công cụ của mình". Test này để chuyện đó KHÔNG lặp lại.
"""

from __future__ import annotations

import pytest

from core import presence as pr
from core import screen_time as st


@pytest.fixture(autouse=True)
def _as_windows(monkeypatch):
    monkeypatch.setattr(pr.os, "name", "nt")
    # Mặc định: rảnh hoàn toàn.
    monkeypatch.setattr(pr, "_device_in_use", lambda: None)
    monkeypatch.setattr(pr, "_visible_titles", lambda: ["notepad", "claude"])
    monkeypatch.setattr(pr, "_foreground_is_fullscreen", lambda: False)


def test_idle_can_interrupt():
    assert pr.busy_reason() is None
    assert pr.can_interrupt() is True


def test_webcam_in_use_blocks(monkeypatch):
    """Đang bật webcam = đang họp video -> CẤM."""
    monkeypatch.setattr(pr, "_device_in_use", lambda: "webcam")
    assert pr.can_interrupt() is False
    assert "webcam" in pr.busy_reason()


def test_mic_in_use_blocks(monkeypatch):
    monkeypatch.setattr(pr, "_device_in_use", lambda: "micro")
    assert pr.can_interrupt() is False


@pytest.mark.parametrize("title", [
    "meet.google.com - google chrome",
    "zoom meeting",
    "microsoft teams",
    "webex meeting center",
])
def test_meeting_window_blocks(monkeypatch, title):
    monkeypatch.setattr(pr, "_visible_titles", lambda: ["notepad", title])
    assert pr.can_interrupt() is False, f"cửa sổ họp '{title}' phải chặn được"


def test_presenting_slides_blocks(monkeypatch):
    monkeypatch.setattr(
        pr, "_visible_titles",
        lambda: ["powerpoint slide show - teky_slide_pro.pptx"])
    assert pr.can_interrupt() is False


def test_fullscreen_app_blocks(monkeypatch):
    monkeypatch.setattr(pr, "_foreground_is_fullscreen", lambda: True)
    assert pr.can_interrupt() is False


def test_read_error_is_treated_as_busy(monkeypatch):
    """FAIL-SAFE: đọc lỗi -> coi như ĐANG BẬN (thà lỡ ca nghỉ còn hơn phá họp)."""
    def boom():
        raise OSError("registry hỏng")
    monkeypatch.setattr(pr, "_device_in_use", boom)
    assert pr.can_interrupt() is False


def test_normal_titles_do_not_false_positive(monkeypatch):
    """Không được chặn nhầm: 'zoom ảnh', 'thu nhỏ/zoom in' KHÔNG phải cuộc họp."""
    monkeypatch.setattr(
        pr, "_visible_titles",
        lambda: ["zoom in - paint", "photo zoom tool", "teams of engineers.docx"])
    assert pr.can_interrupt() is True


# --------------------------------------------------------------------------- #
# Chốt cứng phía hành động: TẮT MÁY
# --------------------------------------------------------------------------- #
def test_shutdown_blocked_while_in_meeting(monkeypatch):
    called = []
    monkeypatch.setattr(st, "_heavy_running", lambda: False)
    monkeypatch.setattr(st, "_run", lambda *a, **k: called.append(a))
    monkeypatch.setattr("core.presence.busy_reason",
                        lambda: "đang dùng webcam (nhiều khả năng đang họp/gọi video)")
    ok, msg = st.force_shutdown(300)
    assert ok is False
    assert called == [], "ĐANG HỌP mà vẫn hẹn tắt máy là LỖI NGHIÊM TRỌNG"
    assert "HOÃN" in msg
