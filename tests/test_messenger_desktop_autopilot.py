"""Telegram AND the desktop mascot bubble must call the real local screen
observer instead of letting the LLM guess. Both routes share one reader:
core.desktop_autopilot.describe_current_screen (via the runtime singleton)."""

from __future__ import annotations

import asyncio

import pytest

from core.desktop_autopilot import set_runtime_autopilot
from core.messenger import TelegramMessenger, _is_screen_observation_request


class FakeAutopilot:
    def __init__(self, observation: dict, *, enabled: bool = True) -> None:
        self.observation = observation
        self.enabled = enabled
        self.calls: list[bool] = []

    def status(self) -> dict:
        return {"owner_enabled": self.enabled}

    def observe(self, *, include_ocr: bool = False) -> dict:
        self.calls.append(include_ocr)
        return self.observation


class FakeDaemon:
    def __init__(self, autopilot: FakeAutopilot) -> None:
        self.desktop_autopilot = autopilot


@pytest.fixture(autouse=True)
def _reset_runtime_autopilot():
    """Không để bản giả rò rỉ sang test khác."""
    yield
    set_runtime_autopilot(None)


def _messenger(autopilot: FakeAutopilot) -> TelegramMessenger:
    # Nguồn chân lý duy nhất: cả Telegram lẫn mascot đọc qua runtime singleton.
    set_runtime_autopilot(autopilot)
    return TelegramMessenger(FakeDaemon(autopilot), "dummy-token", "1")


def test_natural_vietnamese_screen_question_is_detected():
    assert _is_screen_observation_request(
        "Aura, trên màn hình laptop đang có những gì"
    )
    assert _is_screen_observation_request("Bạn nhìn màn hình máy tính giúp tôi")
    assert not _is_screen_observation_request("Tắt màn hình laptop đi")
    assert not _is_screen_observation_request("Hôm nay có job gì?")


def test_natural_question_calls_real_ocr_and_never_falls_back_to_chat():
    autopilot = FakeAutopilot(
        {
            "window_category": "allowed",
            "window_title": "AURA — Xưởng Kiếm Tiền",
            "screen_size": [1920, 1080],
            "ocr_performed": True,
            "ocr_text": "Hộp hành động 1% Hai việc đang chờ",
        }
    )
    messenger = _messenger(autopilot)

    async def no_guess(_text: str) -> str:
        raise AssertionError("screen question must not reach the generic AI")

    messenger._ask_aura = no_guess
    reply = asyncio.run(
        messenger._handle("Aura, trên màn hình laptop đang có những gì")
    )

    # 'mắt sạch' thử vision trước (thất bại vì fake không có _driver) -> lùi OCR.
    assert True in autopilot.calls  # OCR thật đã chạy ở nhánh lùi
    assert "MÀN HÌNH LAPTOP HIỆN TẠI" in reply
    assert "Hộp hành động 1%" in reply


def test_explicit_screen_command_uses_same_route():
    autopilot = FakeAutopilot(
        {
            "window_category": "allowed",
            "window_title": "Facebook - Chrome",
            "screen_size": [1920, 1080],
            "ocr_performed": True,
            "ocr_text": "Trang chủ Facebook",
        }
    )
    reply = asyncio.run(_messenger(autopilot)._handle("/manhinh"))
    assert True in autopilot.calls
    assert "Trang chủ Facebook" in reply


def test_sensitive_window_is_not_ocr_reported():
    autopilot = FakeAutopilot(
        {
            "window_category": "blocked",
            "window_title": "[SENSITIVE_WINDOW]",
            "screen_size": [1920, 1080],
            "ocr_performed": False,
            "ocr_text": "",
        }
    )
    reply = asyncio.run(_messenger(autopilot)._handle("/manhinh"))
    assert "nhạy cảm" in reply and "không chụp" in reply
    assert "MÀN HÌNH LAPTOP HIỆN TẠI" not in reply


def test_unknown_window_and_disabled_owner_are_honest():
    unknown = FakeAutopilot(
        {
            "window_category": "unknown",
            "window_title": "Ứng dụng lạ",
            "screen_size": [1920, 1080],
            "ocr_performed": False,
            "ocr_text": "",
        }
    )
    assert "chưa nằm trong danh sách" in asyncio.run(
        _messenger(unknown)._handle("/manhinh")
    )

    disabled = FakeAutopilot({}, enabled=False)
    reply = asyncio.run(_messenger(disabled)._handle("/manhinh"))
    assert "chưa được Chủ bật" in reply
    assert disabled.calls == []


def test_mascot_bubble_screen_question_uses_real_eyes_not_llm():
    """Bong bóng mascot (server WebSocket) hỏi 'màn hình đang hiện gì' phải đi vào
    OCR thật, KHÔNG rớt xuống orchestrator/LLM để đoán (bug đã gặp)."""
    from interface.server import AuraWebSocketServer

    autopilot = FakeAutopilot(
        {
            "window_category": "allowed",
            "window_title": "Brave",
            "screen_size": [1920, 1080],
            "ocr_performed": True,
            "ocr_text": "Trang dang mo trong Brave",
        }
    )
    set_runtime_autopilot(autopilot)

    class BoomOrchestrator:
        """LLM phải KHÔNG bao giờ được gọi cho câu hỏi màn hình."""
        def process_message(self, _text: str) -> str:
            raise AssertionError("câu hỏi màn hình không được rơi xuống LLM")

    sent: list[tuple[str, str]] = []

    class FakeWS:
        async def send(self, raw: str) -> None:
            import json
            msg = json.loads(raw)
            sent.append((msg["type"], msg["text"]))

    server = AuraWebSocketServer(BoomOrchestrator(), event_queue=asyncio.Queue())
    asyncio.run(server._handle_chat(FakeWS(), "AURA màn hình đang hiển thị gì vậy"))

    responses = [text for kind, text in sent if kind == "response"]
    assert responses, "phải có một câu trả lời"
    assert "Trang dang mo trong Brave" in responses[-1]
    assert True in autopilot.calls  # 'mắt sạch' lùi về OCR thật (fake không chụp được)


def test_mascot_operator_command_runs_dryrun_not_llm():
    """'thao tác: ...' từ bong bóng mascot phải vào vòng lặp thao tác (DRY-RUN),
    KHÔNG rơi xuống LLM."""
    import json
    from interface.server import AuraWebSocketServer
    import core.desktop_operator as dop

    executed: list = []

    class FakeOpAutopilot:
        def status(self):
            return {"owner_enabled": True, "paused": False, "emergency_stop": False}
        def observe(self, *, include_ocr=False):
            return {"window_title": "Notepad", "window_category": "allowed",
                    "ocr_text": "trống", "screen_size": [800, 600]}
        def _driver(self):
            raise RuntimeError("test: không chụp")
        def run_single_action(self, action, *, scope="local_ui"):
            executed.append(action)

    class ScriptedPlanner:
        def next_step(self, goal, obs, png, history):
            return {"thought": "gõ", "done": len(history) >= 1,
                    "action": {"kind": "type_text", "text": "xin chào"}}

    # Tiêm operator có autopilot+planner giả để test không chạm máy thật.
    orig = dop.DesktopOperator
    dop.DesktopOperator = lambda: orig(FakeOpAutopilot(), ScriptedPlanner())

    class BoomOrchestrator:
        def process_message(self, _t):
            raise AssertionError("lệnh thao tác không được rơi xuống LLM")

    sent: list = []

    class FakeWS:
        async def send(self, raw: str) -> None:
            sent.append(json.loads(raw))

    try:
        server = AuraWebSocketServer(BoomOrchestrator(), event_queue=asyncio.Queue())
        asyncio.run(server._handle_chat(FakeWS(), "thao tác: gõ xin chào vào Notepad"))
    finally:
        dop.DesktopOperator = orig

    responses = [m["text"] for m in sent if m["type"] == "response"]
    assert responses, "phải có báo cáo kế hoạch"
    assert "DRY-RUN" in responses[-1]
    assert executed == []  # DRY-RUN: không chạm chuột
