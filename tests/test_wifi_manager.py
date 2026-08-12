"""Wifi manager — đọc dữ liệu wifi ĐÃ LƯU trên máy Sếp, không được bịa, không nháy console."""

from __future__ import annotations

import pytest

from core import wifi_manager as wm

IFACE = """
    Name                   : Wi-Fi
    State                  : connected
    SSID                   : Kien
    AP BSSID               : cc:2d:21:28:91:60
    Signal                 : 100%
"""

PROFILES = """
Profiles on interface Wi-Fi:
Group policy profiles (read only)
User profiles
    All User Profile     : Galaxy S23 Ultra
    All User Profile     : Kien
    All User Profile     : POCO X3 Pro
"""

KEY_CLEAR = """
    SSID name           : "Kien"
    Security settings
        Authentication      : WPA2-Personal
        Key Content         : matkhau123
"""


@pytest.fixture(autouse=True)
def _as_windows(monkeypatch):
    monkeypatch.setattr(wm.os, "name", "nt")


def test_field_exact_match_not_substring():
    """SSID phải lấy đúng, KHÔNG dính nhầm 'AP BSSID'."""
    assert wm._field(IFACE, "ssid") == "Kien"
    assert wm._field(IFACE, "signal") == "100%"
    assert wm._field(IFACE, "state") == "connected"


def test_run_hides_console_window(monkeypatch):
    """_run phải truyền CREATE_NO_WINDOW trên Windows (chống nháy cửa sổ)."""
    seen = {}

    def fake_run(args, **kw):
        seen.update(kw)
        class R:
            stdout = ""
        return R()

    monkeypatch.setattr(wm.subprocess, "run", fake_run)
    wm._run(["netsh"])
    assert seen.get("creationflags") is not None, "thiếu creationflags -> console sẽ nháy"


def test_current_wifi_parses(monkeypatch):
    monkeypatch.setattr(wm, "_run", lambda *a, **k: IFACE)
    cur = wm.current_wifi()
    assert cur == {"ssid": "Kien", "signal": "100%", "state": "connected"}


def test_current_wifi_none_when_blank(monkeypatch):
    monkeypatch.setattr(wm, "_run", lambda *a, **k: "    State : disconnected\n")
    assert wm.current_wifi() is None


def test_list_profiles(monkeypatch):
    monkeypatch.setattr(wm, "_run", lambda *a, **k: PROFILES)
    assert wm.list_profiles() == ["Galaxy S23 Ultra", "Kien", "POCO X3 Pro"]


def test_saved_password_reads_key_content(monkeypatch):
    monkeypatch.setattr(wm, "_run", lambda *a, **k: KEY_CLEAR)
    assert wm.saved_password("Kien") == "matkhau123"


def test_is_wifi_question():
    assert wm.is_wifi_question("mật khẩu wifi hiện tại là gì")
    assert wm.is_wifi_question("đang kết nối wi-fi nào")
    assert wm.is_wifi_question("liệt kê wifi đã lưu")
    assert not wm.is_wifi_question("hôm nay trời đẹp không")
    assert not wm.is_wifi_question("viết cho tôi một bài thơ")


def test_answer_password_uses_current_ssid(monkeypatch):
    monkeypatch.setattr(wm, "current_wifi", lambda: {"ssid": "Kien", "signal": "100%", "state": "connected"})
    monkeypatch.setattr(wm, "list_profiles", lambda: ["Kien"])
    monkeypatch.setattr(wm, "saved_password", lambda ssid: "matkhau123" if ssid == "Kien" else None)
    ans = wm.answer_wifi("mật khẩu wifi hiện tại là gì")
    assert "Kien" in ans and "matkhau123" in ans


def test_answer_password_specific_ssid(monkeypatch):
    monkeypatch.setattr(wm, "current_wifi", lambda: None)
    monkeypatch.setattr(wm, "list_profiles", lambda: ["Kien", "POCO X3 Pro"])
    monkeypatch.setattr(wm, "saved_password", lambda ssid: "pocopass" if ssid == "POCO X3 Pro" else None)
    ans = wm.answer_wifi("cho tôi mật khẩu wifi poco x3 pro")
    assert "pocopass" in ans


def test_answer_list(monkeypatch):
    monkeypatch.setattr(wm, "list_profiles", lambda: ["Kien", "POCO X3 Pro"])
    ans = wm.answer_wifi("liệt kê các wifi đã lưu")
    assert "Kien" in ans and "POCO X3 Pro" in ans


def test_answer_current_status(monkeypatch):
    monkeypatch.setattr(wm, "current_wifi", lambda: {"ssid": "Kien", "signal": "80%", "state": "connected"})
    ans = wm.answer_wifi("đang nối wifi nào")
    assert "Kien" in ans and "80%" in ans


def test_password_not_readable_gives_manual_hint(monkeypatch):
    monkeypatch.setattr(wm, "current_wifi", lambda: {"ssid": "Kien", "signal": "100%", "state": "connected"})
    monkeypatch.setattr(wm, "list_profiles", lambda: ["Kien"])
    monkeypatch.setattr(wm, "saved_password", lambda ssid: None)
    ans = wm.answer_wifi("mật khẩu wifi")
    assert "Administrator" in ans and "key=clear" in ans
