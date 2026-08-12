"""Quản lý giờ màn hình — TẮT MÁY là hành động phá huỷ, phải có đủ chốt an toàn.
(Sếp 30/07: "phải cưỡng chế tắt máy mới được" — nhưng không được làm mất việc.)"""

from __future__ import annotations

import json

import pytest

from core import screen_time as st


@pytest.fixture(autouse=True)
def _isolate_ledger(tmp_path, monkeypatch):
    """Test KHÔNG được đụng sổ giờ màn hình thật của Sếp."""
    monkeypatch.setattr(st, "_LEDGER", tmp_path / "screen_time.json")


def _cfg(monkeypatch, **kw):
    for key, val in kw.items():
        monkeypatch.setattr(st.settings, key, val, raising=False)


def test_no_bare_subprocess_calls_that_flash_console():
    """CANH GÁC: mọi lệnh ngoài phải đi qua _run() để KHÔNG bật cửa sổ console.

    Sếp báo 30/07: laptop cứ chớp lên một đống cửa sổ terminal rồi tắt. Nguyên nhân
    là module này gọi tasklist + adb mỗi 60 giây bằng subprocess.run trần — trên
    Windows mỗi lần là một cửa sổ đen nháy giữa màn hình. AURA đã chữa đúng bệnh
    này ở daemon._adb_run từ trước mà vẫn bị lặp lại.
    """
    import inspect
    from core import screen_time

    src = inspect.getsource(screen_time)
    # Chỉ ĐÚNG MỘT chỗ được phép gọi subprocess.run — chính là trong _run().
    assert src.count("subprocess.run") == 1, (
        "Có lệnh gọi subprocess.run ngoài _run() -> sẽ làm nháy cửa sổ console"
    )
    assert "CREATE_NO_WINDOW" in src


def test_run_helper_hides_console_window(monkeypatch):
    """_run phải truyền CREATE_NO_WINDOW trên Windows."""
    seen = {}

    def fake_run(cmd, **kw):
        seen.update(kw)
        class R:
            stdout = ""
        return R()

    monkeypatch.setattr(st.subprocess, "run", fake_run)
    monkeypatch.setattr(st.os, "name", "nt")
    st._run(["tasklist"], 5)
    assert seen.get("creationflags"), "thiếu creationflags -> console sẽ nháy"


def test_tick_only_counts_active_devices(monkeypatch):
    """Màn tắt / rời máy thì KHÔNG cộng giờ."""
    monkeypatch.setattr(st, "laptop_screen_active", lambda: True)
    monkeypatch.setattr(st, "phone_screen_active", lambda: False)
    day = st.tick(60)
    assert day["laptop_s"] == 60 and day["phone_s"] == 0


def test_phone_unplugged_is_not_an_error(monkeypatch):
    """Rút cáp điện thoại là chuyện thường — trả None, không được nổ."""
    monkeypatch.setattr(st, "laptop_screen_active", lambda: True)
    monkeypatch.setattr(st, "phone_screen_active", lambda: None)
    day = st.tick(60)
    assert day["phone_s"] == 0


def test_warns_early_before_hitting_limit(monkeypatch):
    """Phải cảnh báo ở 80% để Sếp còn kịp thu xếp, không dí đến phút chót."""
    _cfg(monkeypatch, screen_time_enabled=True, screen_time_enforce=False,
         screen_time_daily_limit_min=100)
    st._save({**st.load_today(), "laptop_s": 81 * 60})
    note = st.check_and_enforce()
    assert note and "80%" in note


def test_no_shutdown_when_enforce_is_off(monkeypatch):
    """Mặc định KHÔNG cưỡng chế — quá hạn chỉ nhắc, tuyệt đối không tắt máy."""
    called = []
    monkeypatch.setattr(st, "force_shutdown", lambda *a, **k: called.append(a) or (True, "x"))
    _cfg(monkeypatch, screen_time_enabled=True, screen_time_enforce=False,
         screen_time_daily_limit_min=10)
    st._save({**st.load_today(), "laptop_s": 999 * 60})
    note = st.check_and_enforce()
    assert called == [], "enforce=False mà vẫn gọi tắt máy là LỖI NGHIÊM TRỌNG"
    assert note and "QUÁ HẠN" in note


def test_shutdown_only_when_owner_opted_in(monkeypatch):
    """Bật enforce thì mới hẹn tắt máy."""
    called = []
    monkeypatch.setattr(st, "force_shutdown",
                        lambda delay, reason="": called.append(delay) or (True, "đã hẹn"))
    _cfg(monkeypatch, screen_time_enabled=True, screen_time_enforce=True,
         screen_time_daily_limit_min=10, screen_time_shutdown_delay_min=5)
    st._save({**st.load_today(), "laptop_s": 999 * 60, "warned": ["80", "95"]})
    note = st.check_and_enforce()
    assert called == [300], "phải hẹn đúng 5 phút = 300 giây"
    assert note == "đã hẹn"


def test_heavy_work_blocks_shutdown(monkeypatch):
    """ĐANG RENDER thì KHÔNG được cắt ngang — hoãn tắt máy."""
    monkeypatch.setattr(st, "_heavy_running", lambda: True)
    ok, msg = st.force_shutdown(300)
    assert ok is False
    assert "HOÃN" in msg


def test_shutdown_delay_never_below_one_minute(monkeypatch):
    """Đếm ngược phải đủ dài để lưu việc — không cho tắt tức thì."""
    seen = {}
    monkeypatch.setattr(st, "_heavy_running", lambda: False)
    def fake_run(cmd, **kw):
        seen["cmd"] = cmd
        class R: pass
        return R()
    monkeypatch.setattr(st.subprocess, "run", fake_run)
    st.force_shutdown(1)   # xin tắt sau 1 giây
    assert "/t" in seen["cmd"]
    assert int(seen["cmd"][seen["cmd"].index("/t") + 1]) >= 60


def test_new_day_resets_counter(monkeypatch):
    """Sang ngày mới thì đồng hồ về 0."""
    st._save({"date": "2000-01-01", "laptop_s": 9999, "phone_s": 9999,
              "warned": ["80"], "shutdown_at": 0, "aborted": 0})
    day = st.load_today()
    assert day["laptop_s"] == 0 and day["warned"] == []


def test_status_line_reads_real_ledger(monkeypatch):
    monkeypatch.setattr(st, "phone_screen_active", lambda: None)
    _cfg(monkeypatch, screen_time_daily_limit_min=480)
    st._save({**st.load_today(), "laptop_s": 3600, "phone_s": 1800})
    line = st.status_line()
    assert "1h00p" in line and "0h30p" in line
    assert "chưa nối" in line   # nói thật khi không đọc được điện thoại
