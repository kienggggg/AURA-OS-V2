"""Tay lái của AURA — điều khiển xe THẬT, nên test canh chuyện an toàn là chính.

Ba điều phải giữ:
 1. KHÔNG cướp câu chat thường ("đi ngủ đi" tuyệt đối không được làm xe chạy).
 2. Trần thời gian: gõ 60 giây cũng chỉ chạy tối đa MAX_RUN_S.
 3. Chạy xong LUÔN gửi STOP — kể cả khi giữa chừng có lỗi.
"""

from __future__ import annotations

import pytest

from core import rover


# ---------------------- 1. Không cướp câu chat thường ------------------- #
@pytest.mark.parametrize("q", [
    "đi ngủ đi",
    "lùi lại chút cho tôi xem",
    "tiến độ dự án tới đâu rồi",
    "trái tim tôi",
    "hôm nay trời đẹp",
    "dừng săn job lại",          # là lệnh công nhân, KHÔNG phải lệnh xe
])
def test_does_not_hijack_normal_chat(q):
    assert rover.is_rover_command(q) is False, f"cướp nhầm câu: {q!r}"


@pytest.mark.parametrize("q", [
    "xe tiến 2 giây",
    "cho robot lùi",
    "xe dừng lại",
    "robot xoay trái đi",
    "phía trước xe có gì",
])
def test_recognises_real_rover_commands(q):
    assert rover.is_rover_command(q) is True


# --------------------------- 2. Trần thời gian -------------------------- #
def test_duration_is_capped():
    _, secs, _ = rover._parse("xe tiến 60 giây")
    assert secs == rover.MAX_RUN_S, "không chặn trần -> xe chạy mất kiểm soát"


def test_duration_has_floor():
    _, secs, _ = rover._parse("xe tiến 0.01 giây")
    assert secs >= 0.2


def test_default_duration_when_unspecified():
    _, secs, _ = rover._parse("xe tiến")
    assert secs == rover.DEFAULT_RUN_S


@pytest.mark.parametrize("q,expect", [
    ("xe tiến 2 giây", "F"),
    ("xe lùi 1 giây", "B"),
    ("robot xoay trái", "L"),
    ("robot xoay phải", "R"),
    ("xe dừng", "S"),
    ("khoảng cách phía trước xe", "?"),
])
def test_parses_to_right_command(q, expect):
    cmd, _, _ = rover._parse(q)
    # Lệnh chạy giờ kèm tốc độ ("B:95"); lệnh dừng/đo vẫn trần.
    assert cmd.split(":")[0] == expect


@pytest.mark.parametrize("q,speed", [
    ("xe tiến chậm", rover.SPEED_SLOW),
    ("xe tiến từ từ", rover.SPEED_SLOW),
    ("xe tiến nhanh", rover.SPEED_FAST),
    ("xe tiến", rover.SPEED_NORMAL),
])
def test_speed_words(q, speed):
    cmd, _, _ = rover._parse(q)
    assert cmd.endswith(f":{speed}")


def test_default_speed_is_slow_enough_for_indoors():
    """Đo thật 06/08: tốc 255 -> 1,13m trong 3 giây, quá nhanh trong nhà."""
    assert rover.SPEED_NORMAL <= 120
    assert rover.SPEED_SLOW < rover.SPEED_NORMAL < rover.SPEED_FAST


# ------------------------ 3. Luôn dừng, luôn an toàn -------------------- #
def test_stop_is_always_sent_even_on_error():
    """Đọc code: khối gửi lệnh phải nằm trong try/finally có gửi STOP."""
    import inspect
    src = inspect.getsource(rover._drive)
    assert "finally:" in src
    idx = src.index("finally:")
    assert 'b"S"' in src[idx:], "không gửi STOP trong finally -> xe có thể chạy tiếp khi lỗi"


def test_heartbeat_faster_than_firmware_timeout():
    """Nhịp tín hiệu sống phải NHANH HƠN ngưỡng 1,1s của firmware."""
    assert rover._HEARTBEAT_S < 1.1 / 2


def test_no_autonomous_mode_wired():
    """AURA KHÔNG được tự bật chế độ xe tự chạy (AUTO:1)."""
    import inspect
    src = inspect.getsource(rover)
    assert "AUTO:1" not in src, "đã nối chế độ tự hành -> nguy hiểm, chưa được phép"


def test_missing_car_is_reported_not_crash(monkeypatch):
    async def no_device(*a, **k):
        return None
    import bleak
    monkeypatch.setattr(bleak.BleakScanner, "find_device_by_name", no_device)
    out = rover.handle_rover_command("xe tiến 1 giây")
    assert out.startswith("⚠️") and "xe" in out.lower()
