"""Chốt cứng: dashboard (~30 route KHÔNG xác thực, gồm route điều khiển chuột/bàn
phím) không được phép bind ra ngoài loopback nếu Sếp chưa CỐ Ý bật cờ."""

from __future__ import annotations

import pytest

from interface.dashboard import _is_loopback_host, assert_dashboard_bind_safe


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "LOCALHOST",
                                  "127.0.0.53", "::1", "[::1]", ""])
def test_loopback_hosts_are_allowed(host):
    assert _is_loopback_host(host) is True
    assert_dashboard_bind_safe(host, allow_lan=False)  # không được nổ


@pytest.mark.parametrize("host", ["0.0.0.0", "::", "192.168.50.102", "10.0.0.5",
                                  "8.8.8.8", "aura.local"])
def test_non_loopback_blocked_without_flag(host):
    """Đây là kịch bản chính: đổi một dòng config -> phải NỔ, không mở âm thầm."""
    assert _is_loopback_host(host) is False
    with pytest.raises(RuntimeError) as err:
        assert_dashboard_bind_safe(host, allow_lan=False)
    assert "CHẶN" in str(err.value)


@pytest.mark.parametrize("host", ["0.0.0.0", "192.168.50.102"])
def test_non_loopback_allowed_when_owner_opts_in(host):
    """Bật cờ tường minh thì cho qua (nhưng có cảnh báo to trong log)."""
    assert_dashboard_bind_safe(host, allow_lan=True)


def test_wildcard_is_not_treated_as_loopback():
    """0.0.0.0 nghe trên MỌI card mạng — tuyệt đối không được coi là an toàn."""
    assert _is_loopback_host("0.0.0.0") is False
    assert _is_loopback_host("::") is False


def test_start_dashboard_actually_calls_the_guard():
    """Chốt phải nằm TRONG đường khởi động thật, không chỉ là hàm rời."""
    import inspect
    from interface import dashboard
    src = inspect.getsource(dashboard.start_dashboard)
    assert "assert_dashboard_bind_safe" in src
