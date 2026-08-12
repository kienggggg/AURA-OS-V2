"""Nấc 1 — vòng lặp thao tác phải AN TOÀN: dry-run không chạm chuột, dừng đúng
khi xong / hết bước / cửa sổ nhạy cảm / action bị cấm."""

from __future__ import annotations

from core.desktop_operator import (
    DesktopOperator, _parse_step, parse_operator_command,
)


class FakeAutopilot:
    """Giả lập autopilot: đếm số lần THẬT SỰ chạm chuột (run_single_action)."""
    def __init__(self, category="allowed", enabled=True):
        self.category = category
        self.enabled = enabled
        self.executed: list[dict] = []

    def status(self):
        return {"owner_enabled": self.enabled, "paused": False, "emergency_stop": False}

    def observe(self, *, include_ocr=False):
        return {"window_title": "Brave", "window_category": self.category,
                "ocr_text": "Thanh tìm kiếm", "screen_size": [1920, 1080],
                "ocr_performed": include_ocr}

    def _driver(self):
        raise RuntimeError("không chụp trong test")  # buộc png=None, vẫn chạy

    def run_single_action(self, action, *, scope="local_ui"):
        self.executed.append(action)


class ScriptedPlanner:
    """Trả lần lượt các bước đã soạn."""
    def __init__(self, steps): self.steps = list(steps); self.i = 0
    def next_step(self, goal, observation, screenshot_png, history):
        step = self.steps[min(self.i, len(self.steps) - 1)]
        self.i += 1
        return step


def _click(target):
    return {"thought": "click", "done": False,
            "action": {"kind": "click_text", "target": target}}


def test_dryrun_never_touches_mouse():
    ap = FakeAutopilot()
    planner = ScriptedPlanner([_click("Tìm kiếm"), _click("Ô nhập"),
                               {"done": True, "action": {"kind": "done"}}])
    report = DesktopOperator(ap, planner).run_goal("tìm miku", live=False)
    assert report["status"] == "done"
    assert ap.executed == []  # DRY-RUN: tuyệt đối không chạm chuột


def test_live_executes_until_done():
    ap = FakeAutopilot()
    planner = ScriptedPlanner([_click("Tìm kiếm"),
                               {"done": True, "action": {"kind": "done"}}])
    report = DesktopOperator(ap, planner).run_goal("tìm miku", live=True)
    assert report["status"] == "done"
    assert len(ap.executed) == 1  # đúng 1 action thật trước khi 'done'


def test_max_steps_capped():
    ap = FakeAutopilot()

    class VaryingPlanner:
        """Mỗi bước một action KHÁC nhau -> không kích 'stuck', chạm trần max_steps."""
        def __init__(self): self.i = 0
        def next_step(self, goal, obs, png, history):
            self.i += 1
            return _click(f"nút số {self.i}")  # không bao giờ 'done'

    report = DesktopOperator(ap, VaryingPlanner()).run_goal(
        "vòng vô tận", live=True, max_steps=3)
    assert report["status"] == "max_steps"
    assert len(ap.executed) == 3  # dừng đúng trần


def test_sensitive_window_aborts_before_any_action():
    ap = FakeAutopilot(category="blocked")
    planner = ScriptedPlanner([_click("Đăng nhập ngân hàng")])
    report = DesktopOperator(ap, planner).run_goal("x", live=True)
    assert report["status"] == "blocked_sensitive_window"
    assert ap.executed == []  # cửa sổ nhạy cảm -> không làm gì


def test_unknown_window_stops_honestly_not_blind_plan():
    """Cửa sổ 'unknown' (không đọc được) -> dừng thật thà, KHÔNG lập kế hoạch mù."""
    ap = FakeAutopilot(category="unknown")
    planner = ScriptedPlanner([_click("gì đó")])
    report = DesktopOperator(ap, planner).run_goal("làm gì đó", live=True)
    assert report["status"] == "cannot_see_window"
    assert ap.executed == []


def test_stuck_detection_stops_repeating_same_action(monkeypatch):
    """Nấc 3: lặp lại cùng một hành động mà không tiến triển -> DỪNG 'stuck',
    không đâm đầu tiếp (phát hiện số 1 của nghiên cứu)."""
    import core.desktop_operator as dop
    monkeypatch.setattr(dop, "_record_failure", lambda *a, **k: None)

    ap = FakeAutopilot()
    planner = ScriptedPlanner([_click("nút không bao giờ đổi")])  # trả mãi 1 action
    report = DesktopOperator(ap, planner).run_goal("mãi không xong", live=True, max_steps=10)
    assert report["status"] == "stuck"
    # _MAX_REPEAT=2 -> làm tối đa 2 lần rồi dừng ở lần thứ 3, KHÔNG chạy hết 10 bước
    assert len(ap.executed) <= 2


def test_failure_records_reflexion_lesson(monkeypatch):
    """Nấc 3: kết thúc xấu -> ghi bài học qua Reflexion để lần sau tránh."""
    import core.desktop_operator as dop
    recorded = {}
    def fake_note(line, tool, checks, error=""):
        recorded["line"] = line; recorded["checks"] = checks
    monkeypatch.setattr("factory.reflexion.note_outcome", fake_note)

    ap = FakeAutopilot()
    planner = ScriptedPlanner([_click("kẹt")])
    DesktopOperator(ap, planner).run_goal("việc kẹt", live=True, max_steps=8)
    assert recorded.get("line") == "desktop_operator"
    assert recorded["checks"][0]["ok"] is False


def test_expect_is_carried_for_verification():
    """Nấc 3: planner trả 'expect' -> lưu vào lịch sử để bước sau tự kiểm."""
    ap = FakeAutopilot()
    planner = ScriptedPlanner([
        {"thought": "gõ", "expect": "ô soạn thảo hiện chữ", "done": False,
         "action": {"kind": "type_text", "text": "hi"}},
        {"done": True, "action": {"kind": "done"}}])
    report = DesktopOperator(ap, planner).run_goal("gõ hi", live=True)
    assert report["steps"][0]["expect"] == "ô soạn thảo hiện chữ"


def test_forbidden_action_kind_rejected():
    ap = FakeAutopilot()
    planner = ScriptedPlanner([
        {"thought": "thử đăng", "done": False, "action": {"kind": "publish"}}])
    report = DesktopOperator(ap, planner).run_goal("đăng bài", live=True)
    assert report["status"] == "rejected_action"
    assert ap.executed == []  # 'publish' không nằm trong allowlist nấc 1


def test_not_enabled_short_circuits():
    ap = FakeAutopilot(enabled=False)
    report = DesktopOperator(ap, ScriptedPlanner([_click("x")])).run_goal("x", live=True)
    assert report["status"] == "not_enabled"
    assert ap.executed == []


def test_parse_step_strips_code_fence():
    step = _parse_step('```json\n{"thought":"a","done":false,'
                       '"action":{"kind":"click_text","target":"OK"}}\n```')
    assert step["action"]["kind"] == "click_text"
    assert step["action"]["target"] == "OK"


def test_parse_step_bad_json_is_safe_done():
    step = _parse_step("xin lỗi tôi không chắc")
    assert step["done"] is True  # không đọc được -> dừng an toàn, không bịa action


class _FakeImg:
    def save(self, buf, format="PNG"):
        buf.write(b"\x89PNG\r\n\x1a\nfake")


class _SmartAutopilot:
    def __init__(self, category="allowed"):
        self.category = category
    def status(self):
        return {"owner_enabled": True}
    def observe(self, *, include_ocr=False):
        return {"window_title": "Brave", "window_category": self.category,
                "ocr_text": "chudt méo", "ocr_performed": include_ocr,
                "screen_size": [1920, 1080]}
    def _driver(self):
        class D:
            def screenshot(self): return _FakeImg()
        return D()


def test_smart_screen_uses_gemini_vision_when_online(monkeypatch):
    import core.desktop_autopilot as da
    import brains.cloud_gemini as cg
    from core.desktop_operator import describe_screen_smart

    monkeypatch.setattr(da, "get_runtime_autopilot", lambda: _SmartAutopilot())

    class FakeGemini:
        def __init__(self, *a, **k): pass
        def chat(self, msgs, *, images=None, **k):
            assert images, "phải gửi ẢNH cho vision"
            return "Đang mở trình duyệt Brave với trang tìm kiếm."
    monkeypatch.setattr(cg, "GeminiBackend", FakeGemini)

    out = describe_screen_smart()
    assert "Brave" in out and "trình duyệt Brave" in out  # đọc sạch, đúng tiếng Việt


def test_smart_screen_falls_back_to_local_ocr_when_offline(monkeypatch):
    import core.desktop_autopilot as da
    import brains.cloud_gemini as cg
    from core.desktop_operator import describe_screen_smart

    monkeypatch.setattr(da, "get_runtime_autopilot", lambda: _SmartAutopilot())

    class BoomGemini:
        def __init__(self, *a, **k): pass
        def chat(self, *a, **k): raise RuntimeError("offline")
    monkeypatch.setattr(cg, "GeminiBackend", BoomGemini)

    out = describe_screen_smart()
    assert "MÀN HÌNH LAPTOP" in out  # lùi về OCR local, vẫn trung thực


def test_smart_screen_blocks_sensitive_window(monkeypatch):
    import core.desktop_autopilot as da
    from core.desktop_operator import describe_screen_smart
    monkeypatch.setattr(da, "get_runtime_autopilot",
                        lambda: _SmartAutopilot(category="blocked"))
    out = describe_screen_smart()
    assert "nhạy cảm" in out  # KHÔNG chụp, KHÔNG gửi cloud


def test_operator_command_dryrun_by_default():
    cmd = parse_operator_command("thao tác: mở Notepad gõ xin chào")
    assert cmd == {"goal": "mở Notepad gõ xin chào", "live": False}


def test_operator_command_live_requires_explicit_that():
    cmd = parse_operator_command("thao tác thật: mở Notepad gõ xin chào")
    assert cmd["live"] is True
    assert cmd["goal"] == "mở Notepad gõ xin chào"


def test_normal_chat_is_not_operator_command():
    assert parse_operator_command("hôm nay thời tiết thế nào") is None
    assert parse_operator_command("thao tác") is None       # thiếu ':' + việc
    assert parse_operator_command("thao tác:") is None       # thiếu việc
