"""Điều khiển công nhân bằng lời — 'ngừng săn job' phải là LỆNH, không phải xin báo cáo."""

from __future__ import annotations

import pytest

from core import worker_control as wc


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(wc, "_PATH", tmp_path / "crew_paused.json")


def test_detect_control_commands():
    assert wc.is_worker_control("tạm ngừng săn job")
    assert wc.is_worker_control("tắt job scout đi")
    assert wc.is_worker_control("bật lại săn job")
    assert wc.is_worker_control("dừng dọn rác lại")
    assert wc.is_worker_control("tạm dừng cả tổ công nhân")


def test_not_control():
    assert not wc.is_worker_control("hôm nay có tin tức gì không")   # có đối tượng, KHÔNG động từ
    assert not wc.is_worker_control("cho tôi xem tất cả tin tức")    # 'tất cả' không phải lệnh cả-tổ
    assert not wc.is_worker_control("tắt tất cả thông báo")          # động từ nhưng KHÔNG nhắm công nhân
    assert not wc.is_worker_control("mật khẩu wifi là gì")
    assert not wc.is_worker_control("sử dụng máy tính thế nào")      # 'dụng' != 'dung'


def test_pause_then_resume():
    msg = wc.handle_worker_control("tạm ngừng săn job")
    assert "TẠM NGỪNG" in msg
    assert wc.is_paused("job") and not wc.is_paused("news")
    msg2 = wc.handle_worker_control("bật lại săn job")
    assert "BẬT LẠI" in msg2
    assert not wc.is_paused("job")


def test_pause_all_crew():
    wc.handle_worker_control("tạm dừng cả tổ công nhân")
    assert all(wc.is_paused(w) for w in ("job", "news", "janitor", "radar"))


def test_both_verbs_earliest_wins():
    # 'ngừng' đứng TRƯỚC 'bật lại' -> hiểu là NGỪNG.
    wc.handle_worker_control("ngừng săn job, tí nữa bật lại")
    assert wc.is_paused("job")


def test_state_persists_to_file():
    wc.handle_worker_control("tạm ngừng dọn rác")
    assert wc.list_paused() == ["janitor"]
    # đọc lại từ file (mô phỏng khởi động lại)
    assert wc._load() == {"janitor"}
