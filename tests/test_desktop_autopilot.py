"""Safety and integration tests for AURA's local Desktop Autopilot."""

from __future__ import annotations

import asyncio
import inspect
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from aiohttp.test_utils import TestClient, TestServer

from core.daemon import AuraDaemon
from core.desktop_autopilot import (
    DesktopAutopilot,
    DesktopSafetyPolicy,
    LocalTesseractOCR,
    set_runtime_autopilot,
)
from interface.dashboard import build_dashboard_app
from tools.registry import SkillRegistry


@pytest.fixture(autouse=True)
def _bat_autopilot_cho_test(monkeypatch):
    """Test phải TỰ đặt cờ, không đọc cấu hình sống của máy.

    10/08/2026: Sếp tắt bớt 24 tác vụ nền, trong đó có `desktop_autopilot`.
    Bốn test ở tệp này lập tức đỏ — không phải vì mã hỏng mà vì chúng đọc thẳng
    `.env` của người dùng.  Một phép thử phụ thuộc vào cấu hình sống thì đo cả
    tâm trạng người chỉnh máy, không đo mã.
    """
    from core.config import settings

    monkeypatch.setattr(settings, "desktop_autopilot_enabled", True, raising=False)


class FakeDriver:
    def __init__(self, title: str = "AURA — Xưởng Kiếm Tiền") -> None:
        self.title = title
        self.calls: list[tuple] = []
        self.screenshot_calls = 0

    def active_window_title(self) -> str:
        return self.title

    def screen_size(self) -> tuple[int, int]:
        return 1920, 1080

    def screenshot(self):
        self.screenshot_calls += 1
        return object()

    def click(self, x: int, y: int) -> None:
        self.calls.append(("click", x, y))

    def type_text(self, text: str) -> None:
        self.calls.append(("type_text", text))

    def press(self, key: str) -> None:
        self.calls.append(("press", key))

    def hotkey(self, *keys: str) -> None:
        self.calls.append(("hotkey", *keys))

    def scroll(self, amount: int) -> None:
        self.calls.append(("scroll", amount))


class FakeOCR:
    def __init__(self, text: str = "Hộp 1%") -> None:
        self.text = text
        self.calls = 0

    def read(self, _image) -> list[dict]:
        self.calls += 1
        return [
            {
                "text": self.text,
                "confidence": 0.99,
                "box": [[100, 100], [220, 100], [220, 150], [100, 150]],
            }
        ]


class FakeMemory:
    def _records(self):
        return [
            SimpleNamespace(
                role="user",
                text="Khóa cũ sk-abcdefgh12345678 và sở thích làm việc tự động.",
            )
        ]

    recall_context = lambda self, _query, k=3: self._records()
    recall_preferences = lambda self, _query, k=3: self._records()
    recall_rules = lambda self, _query, k=3: []
    recall_knowledge = lambda self, _query, k=3: []
    recall_profile = lambda self, _query, k=3: []


def _autopilot(
    tmp_path: Path,
    *,
    driver: FakeDriver | None = None,
    ocr: FakeOCR | None = None,
    memory=None,
) -> DesktopAutopilot:
    return DesktopAutopilot(
        driver=driver or FakeDriver(),
        ocr=ocr or FakeOCR(),
        memory=memory,
        state_path=tmp_path / "state.json",
        tasks_path=tmp_path / "tasks.json",
        audit_path=tmp_path / "audit.jsonl",
        project_root=tmp_path,
        policy=DesktopSafetyPolicy(
            allowed_windows=("aura", "codex", "chrome"),
            blocked_terms=("mb bank", "mbbank", "password", "otp", "captcha", "payment"),
        ),
    )


def test_owner_enables_once_and_status_persists(tmp_path):
    autopilot = _autopilot(tmp_path)
    with pytest.raises(PermissionError):
        autopilot.set_control("enable", confirmed_by_owner=False)

    enabled = autopilot.set_control("enable", confirmed_by_owner=True)
    restarted = _autopilot(tmp_path)

    assert enabled["runtime_enabled"] is True
    assert restarted.status()["owner_enabled"] is True
    assert restarted.status()["approved_scopes"] == ["local_ui", "research", "drafting"]
    assert restarted.status()["screenshot_retention"] is False
    assert restarted.status()["capability_version"] == "desktop-autopilot-telegram-v2"


def test_bank_window_never_runs_ocr_or_side_effects(tmp_path):
    driver = FakeDriver("MB Bank - Chrome")
    ocr = FakeOCR()
    autopilot = _autopilot(tmp_path, driver=driver, ocr=ocr)

    observation = autopilot.observe(include_ocr=True)
    ok, reason = autopilot.policy.validate_action(
        {"kind": "click", "x": 10, "y": 20, "label": "xem số dư"},
        title=driver.title,
        approved_scopes={"local_ui"},
        task_scope="local_ui",
    )

    assert observation["window_title"] == "[SENSITIVE_WINDOW]"
    assert observation["window_category"] == "blocked"
    assert observation["ocr_performed"] is False
    assert driver.screenshot_calls == 0
    assert ocr.calls == 0
    assert ok is False
    assert "không được tự thao tác" in reason


@pytest.mark.parametrize("title", ["", "Ứng dụng lạ"])
def test_unknown_window_fails_closed(title, tmp_path):
    autopilot = _autopilot(tmp_path, driver=FakeDriver(title))
    ok, _reason = autopilot.policy.validate_action(
        {"kind": "scroll", "amount": -100},
        title=title,
        approved_scopes={"research"},
        task_scope="research",
    )
    assert ok is False


def test_real_codex_desktop_title_is_allowlisted():
    policy = DesktopSafetyPolicy(
        allowed_windows=("aura", "codex", "chatgpt"),
        blocked_terms=("mbbank", "otp"),
    )
    assert policy.classify_window("ChatGPT") == "allowed"


def test_lightweight_tesseract_groups_words_into_clickable_lines():
    tsv = (
        "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\t"
        "width\theight\tconf\ttext\n"
        "5\t1\t1\t1\t1\t1\t100\t20\t40\t20\t95\tBat\n"
        "5\t1\t1\t1\t1\t2\t145\t20\t30\t20\t90\ttu\n"
        "5\t1\t1\t1\t1\t3\t180\t20\t70\t20\t92\tthao tac\n"
    )
    boxes = LocalTesseractOCR._parse_tsv(tsv)
    assert boxes == [
        {
            "text": "Bat tu thao tac",
            "confidence": pytest.approx((0.95 + 0.90 + 0.92) / 3),
            "box": [[100, 20], [250, 20], [250, 40], [100, 40]],
        }
    ]


def test_local_task_runs_without_per_action_approval(tmp_path):
    driver = FakeDriver()
    autopilot = _autopilot(tmp_path, driver=driver, ocr=FakeOCR())
    autopilot.set_control("enable", confirmed_by_owner=True)
    queued = autopilot.enqueue_task(
        title="Mở Hộp 1% và nhập bản nháp",
        scope="local_ui",
        expected_window_keywords=["AURA"],
        actions=[
            {"kind": "click_text", "target": "Hộp 1%"},
            {"kind": "type_text", "text": "bản nháp cục bộ"},
            {"kind": "press", "key": "enter"},
            {"kind": "scroll", "amount": -200},
        ],
    )
    result = autopilot.run_next()

    assert queued["action_count"] == 4
    assert result["status"] == "completed"
    assert driver.calls == [
        ("click", 160, 125),
        ("type_text", "bản nháp cục bộ"),
        ("press", "enter"),
        ("scroll", -200),
    ]
    audit = (tmp_path / "audit.jsonl").read_text(encoding="utf-8")
    assert "bản nháp cục bộ" not in audit


def test_public_submit_and_secret_like_text_are_blocked(tmp_path):
    autopilot = _autopilot(tmp_path)
    with pytest.raises(PermissionError):
        autopilot.enqueue_task(
            title="Gửi bài",
            scope="external_submit",
            actions=[{"kind": "click_text", "target": "Đăng bài"}],
        )
    with pytest.raises(PermissionError):
        autopilot.enqueue_task(
            title="Điền mã",
            scope="local_ui",
            actions=[{"kind": "type_text", "text": "123456"}],
        )

    ok, reason = autopilot.policy.validate_action(
        {"kind": "click_text", "target": "Đăng bài"},
        title="Facebook - Chrome",
        approved_scopes={"local_ui"},
        task_scope="local_ui",
    )
    assert ok is False
    assert "gửi/đăng/xóa" in reason


def test_emergency_stop_prevents_queued_task(tmp_path):
    autopilot = _autopilot(tmp_path)
    autopilot.set_control("enable", confirmed_by_owner=True)
    autopilot.enqueue_task(
        title="Cuộn trang",
        actions=[{"kind": "scroll", "amount": -100}],
    )
    autopilot.set_control("emergency_stop", confirmed_by_owner=True)
    assert autopilot.run_next() == {
        "status": "blocked",
        "reason": "paused_or_emergency_stop",
    }


def test_read_self_context_stays_inside_safe_project_files(tmp_path):
    (tmp_path / "core").mkdir()
    (tmp_path / "AURA_COMMAND.md").write_text("AURA command", encoding="utf-8")
    (tmp_path / "core" / "agent.py").write_text("print('safe')", encoding="utf-8")
    (tmp_path / ".env").write_text("SECRET=do-not-read", encoding="utf-8")
    outside = tmp_path.parent / "outside-aura-secret.txt"
    outside.write_text("outside", encoding="utf-8")
    autopilot = _autopilot(tmp_path)

    result = autopilot.read_self_context(
        paths=["AURA_COMMAND.md", "core/agent.py", ".env", "../outside-aura-secret.txt"]
    )
    paths = [row["path"] for row in result["files"]]

    assert paths == ["AURA_COMMAND.md", "core\\agent.py"]
    assert all("do-not-read" not in row["text"] for row in result["files"])
    assert result["source_file_count"] == 1
    outside.unlink()


def test_local_memory_is_connected_and_redacted(tmp_path):
    autopilot = _autopilot(tmp_path, memory=FakeMemory())
    result = autopilot.recall_local_memory("owner preferences")

    assert result["available"] is True
    assert result["records"]
    assert all("sk-abcdefgh12345678" not in row["text"] for row in result["records"])
    assert "[REDACTED_KEY]" in result["records"][0]["text"]


def test_skill_registry_discovers_and_calls_desktop_autopilot(tmp_path):
    autopilot = _autopilot(tmp_path)
    set_runtime_autopilot(autopilot)
    registry = SkillRegistry(Path(__file__).parents[1] / "skills")

    assert registry.has("desktop.autopilot")
    result = registry.execute_tool("desktop.autopilot", {"action": "status"})
    assert result.ok is True
    assert json.loads(result.output)["physical_kill_switch"] == "move_mouse_to_any_corner"


def test_dashboard_control_inspect_and_private_context(tmp_path):
    driver = FakeDriver()
    autopilot = _autopilot(tmp_path, driver=driver, memory=FakeMemory())
    set_runtime_autopilot(autopilot)

    async def scenario() -> None:
        client = TestClient(TestServer(build_dashboard_app()))
        await client.start_server()
        try:
            status = await client.get("/api/desktop-autopilot")
            assert status.status == 200
            denied = await client.post(
                "/api/desktop-autopilot/control",
                json={"action": "enable", "confirmed_by_owner": False},
            )
            assert denied.status == 400
            enabled = await client.post(
                "/api/desktop-autopilot/control",
                json={"action": "enable", "confirmed_by_owner": True},
            )
            assert enabled.status == 200
            assert (await enabled.json())["runtime_enabled"] is True
            inspected = await client.post(
                "/api/desktop-autopilot/inspect",
                json={"include_ocr": False},
            )
            assert inspected.status == 200
            assert (await inspected.json())["window_category"] == "allowed"
            context = await client.get("/api/desktop-autopilot/context")
            context_data = await context.json()
            assert context.status == 200
            assert context_data["memory"]["connected"] is True
            assert context_data["private_text_exposed"] is False
            assert "records" not in context_data["memory"]
        finally:
            await client.close()

    asyncio.run(scenario())


def test_daemon_registers_desktop_autopilot_heartbeat():
    start_source = inspect.getsource(AuraDaemon.start)
    heartbeat_source = inspect.getsource(AuraDaemon._desktop_autopilot_heartbeat)
    assert "_desktop_autopilot_heartbeat()" in start_source
    assert "run_next" in heartbeat_source
    assert "include_ocr=False" in heartbeat_source
