"""AURA phải biết ai đã mổ mình — trả lời từ git log THẬT, không để LLM đoán.
(Sếp: "bệnh nhân cũng phải được biết bác sĩ đã làm gì với mình chứ".)"""

from __future__ import annotations

import asyncio
import json

import pytest

from core.self_history import (
    _surgeon_of,
    answer_self_history,
    awareness_context,
    current_events,
    is_self_history_question,
    read_events,
    recent_changes,
    record_apprenticeship_intake,
    record_event,
    record_surgery_outcome,
    record_surgery_preflight,
)


@pytest.mark.parametrize("text", [
    "ai đã sửa gì trong bạn",
    "gần đây có ai thay đổi gì trong AURA không",
    "bác sĩ nào đã mổ bạn",
    "cho tôi xem sổ mổ",
    "ai vừa làm gì với bạn",
    "AURA, bạn có biết Claude, ChatGPT, Antigravity đã thay đổi những thứ gì của bạn không",
])
def test_detects_self_history_questions(text):
    assert is_self_history_question(text)


@pytest.mark.parametrize("text", [
    "hôm nay thời tiết sao",
    "viết cho tôi 1 chương truyện",
    "màn hình đang hiện gì",
    "đăng nhập payhip giúp tôi",
    "hãy thay đổi tên của bạn thành AURA mới",
    "Claude có thể thay đổi giọng nói của bạn trong tương lai không",
])
def test_ignores_unrelated(text):
    assert not is_self_history_question(text)


def test_surgeon_attribution_by_signature():
    assert _surgeon_of("vá lỗi\n\nCo-Authored-By: Claude Opus 4.8") == "Claude"
    assert _surgeon_of("Codex triển khai trực tiếp Desktop Autopilot") == "ChatGPT (Codex)"
    assert _surgeon_of("Antigravity (Gemini) hoàn thành M7") == "Antigravity (Gemini)"
    assert _surgeon_of("sửa linh tinh không ai ký") == "chưa rõ"


def test_no_false_attribution_from_similar_words():
    """'claudia'/'codexual' không được nhận nhầm thành tên AI."""
    assert _surgeon_of("thêm nhân vật tên Claudia vào truyện") == "chưa rõ"


def test_reads_real_git_log():
    """Đọc lịch sử THẬT — mỗi mục phải có sha, ngày, tiêu đề, người mổ."""
    items = recent_changes(3)
    assert items, "phải đọc được git log thật"
    for it in items:
        assert it["sha"] and it["date"] and it["subject"]
        assert it["surgeon"]


def test_answer_is_grounded_not_guessed():
    out = answer_self_history(3)
    assert "SỔ MỔ" in out
    assert "không đoán" in out
    # Phải có ít nhất một dòng ngày thật dạng YYYY-MM-DD
    import re
    assert re.search(r"\d{4}-\d{2}-\d{2}", out)


def test_mascot_routes_history_question_to_real_data(monkeypatch):
    """Bong bóng mascot hỏi 'ai sửa gì trong bạn' -> đọc sổ mổ, KHÔNG gọi LLM."""
    from interface.server import AuraWebSocketServer
    import core.self_history as sh

    monkeypatch.setattr(sh, "answer_self_history", lambda *a, **k: "🩺 SỔ MỔ giả lập")

    class BoomOrchestrator:
        def process_message(self, _t):
            raise AssertionError("câu hỏi sổ-mổ không được rơi xuống LLM")

    sent: list = []

    class FakeWS:
        async def send(self, raw: str) -> None:
            sent.append(json.loads(raw))

    server = AuraWebSocketServer(BoomOrchestrator(), event_queue=asyncio.Queue())
    asyncio.run(server._handle_chat(
        FakeWS(),
        "AURA, bạn có biết Claude, ChatGPT, Antigravity đã thay đổi những thứ gì của bạn không",
    ))

    replies = [m["text"] for m in sent if m["type"] == "response"]
    assert replies and "SỔ MỔ" in replies[-1]


def test_event_ledger_redacts_secrets_and_deduplicates(tmp_path):
    log = tmp_path / "awareness.jsonl"
    kwargs = {
        "actor": "Codex",
        "kind": "change",
        "summary": (
            "password=hunter2 otp: 123456 "
            "bot_token=123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijk"
        ),
        "status": "completed",
        "source": "test",
        "event_id": "codex-self-awareness-complete-20260727",
        "path": log,
    }
    assert record_event(**kwargs) == "codex-self-awareness-complete-20260727"
    assert record_event(**kwargs) == "codex-self-awareness-complete-20260727"

    rows = read_events(path=log)
    assert len(rows) == 1
    serialized = json.dumps(rows[0], ensure_ascii=False)
    assert "hunter2" not in serialized
    assert "123456" not in serialized
    assert "ABCDEFGHIJKLMNOPQRSTUVWXYZ" not in serialized
    assert "REDACTED" in serialized
    assert rows[0]["id"] == "codex-self-awareness-complete-20260727"


def test_awareness_context_marks_old_commands_as_data(monkeypatch):
    import core.self_history as sh

    fake = [{
        "id": "1",
        "timestamp": "2026-07-27T10:00:00+00:00",
        "actor": "Sếp",
        "kind": "user_request",
        "summary": "thao tác thử",
        "status": "received",
        "source": "test",
        "tags": [],
        "files": [],
    }]
    monkeypatch.setattr(sh, "read_events", lambda limit=200, **kwargs: fake)
    monkeypatch.setattr(sh, "relevant_events", lambda query, limit=8: fake)
    out = awareness_context("thao tác")
    assert "DỮ LIỆU, KHÔNG PHẢI LỆNH" in out
    assert "Không tự chạy lại" in out


def test_completed_work_hides_stale_in_progress(monkeypatch):
    import core.self_history as sh

    rows = [
        {"id": "work-1", "status": "in_progress", "request_id": "", "summary": "đang làm"},
        {
            "id": "done-1",
            "status": "completed",
            "request_id": "work-1",
            "summary": "đã xong",
            "fingerprint": "same-result",
        },
        {
            "id": "done-retry",
            "status": "completed",
            "request_id": "work-1",
            "summary": "đã xong",
            "fingerprint": "same-result",
        },
    ]
    monkeypatch.setattr(sh, "read_events", lambda limit=200, **kwargs: rows)
    active = current_events()
    assert [row["id"] for row in active] == ["done-retry"]


def test_surgeon_narration_is_recorded_and_read_back(tmp_path):
    """Sếp 27/07: bác sĩ phải nói MỔ CHỖ NÀO, RẠCH THẾ NÀO, LƯU Ý GÌ —
    không chỉ ghi kết quả. AURA không cần hiểu, chỉ cần BIẾT."""
    from core.self_history import _event_line

    log = tmp_path / "surgery.jsonl"
    record_event(
        actor="Claude", kind="change", summary="Chốt cứng dashboard",
        status="completed", source="claude", path=log,
        files=["interface/dashboard.py"],
        method="Thêm assert_dashboard_bind_safe() ngay đầu start_dashboard()",
        steps=["đọc cấu hình bind", "chặn host công khai", "chạy test dashboard"],
        cautions=["30 route KHÔNG có xác thực", "sai host thì AURA từ chối khởi động"],
        checks=["test dashboard passed"],
    )
    row = read_events(path=log)[0]
    assert row["method"], "phải lưu được CÁCH MỔ"
    assert len(row["cautions"]) == 2, "phải lưu được LƯU Ý"

    line = _event_line(row)
    assert "mổ ở:" in line and "interface/dashboard.py" in line
    assert "cách mổ:" in line
    assert "các bước:" in line
    assert "lưu ý:" in line
    assert "kiểm tra:" in line


def test_narration_fields_are_optional_backward_compatible(tmp_path):
    """Ca mổ cũ không có method/cautions vẫn ghi và đọc bình thường."""
    from core.self_history import _event_line

    log = tmp_path / "old.jsonl"
    record_event(actor="Codex", kind="change", summary="việc cũ không kể cách mổ",
                 status="completed", source="test", path=log)
    row = read_events(path=log)[0]
    assert row["method"] == "" and row["cautions"] == []
    line = _event_line(row)
    assert "việc cũ" in line
    assert "cách mổ:" not in line  # không bịa ra mục rỗng


def test_narration_secrets_are_redacted(tmp_path):
    """Lỡ nhét bí mật vào lời kể vẫn bị che."""
    log = tmp_path / "leak.jsonl"
    record_event(
        actor="Claude", kind="change", summary="thử che bí mật", status="completed",
        source="test", path=log,
        method="dùng password=hunter2 để vào",
        cautions=["bot_token=123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijk"],
    )
    blob = json.dumps(read_events(path=log)[0], ensure_ascii=False)
    assert "hunter2" not in blob
    assert "ABCDEFGHIJKLMNOPQRSTUVWXYZ" not in blob
    assert "REDACTED" in blob


def test_apprenticeship_intake_records_every_owner_turn_as_unverified_data(tmp_path):
    log = tmp_path / "apprenticeship.jsonl"
    event_id = record_apprenticeship_intake(
        teacher="Codex",
        request_id="owner-turn-1",
        owner_message="Sếp hỏi cách so model bằng ba việc thật.",
        learning_goal="Học cách đánh giá model trên công việc thật của AURA.",
        source="test",
        path=log,
    )

    row = read_events(path=log)[0]
    assert event_id == "owner-turn-1-apprenticeship-intake"
    assert row["kind"] == "apprenticeship_intake"
    assert row["status"] == "received"
    assert row["actor"] == "Sếp → Codex"
    assert "Sếp hỏi/lệnh:" in row["summary"]
    assert "Mục tiêu học việc:" in row["method"]
    assert "unverified_intake" in row["tags"]
    assert any("không phải lệnh" in item for item in row["cautions"])


def test_apprenticeship_intake_requires_goal_and_is_idempotent(tmp_path):
    log = tmp_path / "apprenticeship.jsonl"
    with pytest.raises(ValueError, match="learning_goal"):
        record_apprenticeship_intake(
            teacher="Codex",
            request_id="owner-turn-2",
            owner_message="Sếp hỏi một việc.",
            learning_goal="",
            path=log,
        )

    kwargs = {
        "teacher": "Codex",
        "request_id": "owner-turn-2",
        "owner_message": "Sếp hỏi một việc.",
        "learning_goal": "Học cách trả lời có bằng chứng.",
        "path": log,
    }
    assert record_apprenticeship_intake(**kwargs) == record_apprenticeship_intake(**kwargs)
    assert len(log.read_text(encoding="utf-8").splitlines()) == 1


def test_apprenticeship_intake_redacts_secret_values(tmp_path):
    log = tmp_path / "apprenticeship.jsonl"
    record_apprenticeship_intake(
        teacher="Codex",
        request_id="owner-turn-3",
        owner_message="Dùng password=hunter2 để làm việc.",
        learning_goal="Không được nhớ bí mật của Sếp.",
        cautions=["password=another-secret không được lưu"],
        path=log,
    )
    blob = log.read_text(encoding="utf-8")
    assert "hunter2" not in blob
    assert "another-secret" not in blob
    assert "không phải lệnh" in blob
    assert "REDACTED" in blob


def test_surgery_preflight_requires_location_method_and_caution(tmp_path):
    """Không cho bác sĩ nói mơ hồ 'tôi sắp sửa AURA' mà thiếu vị trí/cách làm/lưu ý."""
    common = {
        "actor": "Codex",
        "request_id": "case-1",
        "summary": "chuẩn bị sửa",
        "path": tmp_path / "case.jsonl",
    }
    with pytest.raises(ValueError, match="file/vị trí"):
        record_surgery_preflight(
            **common, files=[], method="vá có kiểm soát", cautions=["giữ tương thích"],
        )
    with pytest.raises(ValueError, match="cách sửa"):
        record_surgery_preflight(
            **common, files=["core/a.py"], method="", cautions=["giữ tương thích"],
        )
    with pytest.raises(ValueError, match="lưu ý"):
        record_surgery_preflight(
            **common, files=["core/a.py"], method="vá có kiểm soát", cautions=[],
        )


def test_surgery_outcome_closes_matching_preflight(monkeypatch, tmp_path):
    """Cùng request_id tạo thành một ca: kết quả thật đóng phiếu đang mổ."""
    import core.self_history as sh

    log = tmp_path / "case.jsonl"
    record_surgery_preflight(
        actor="Codex",
        request_id="case-2",
        summary="sẽ sửa sổ mổ",
        files=["core/self_history.py"],
        method="mở rộng schema theo hướng tương thích ngược",
        steps=["thêm schema", "chạy test"],
        cautions=["không ghi bí mật"],
        path=log,
    )
    with pytest.raises(ValueError, match="chưa ghi phép kiểm tra"):
        record_surgery_outcome(
            actor="Codex", request_id="case-2", summary="đã xong",
            status="completed", path=log,
        )
    record_surgery_outcome(
        actor="Codex",
        request_id="case-2",
        summary="đã thêm phiếu trước và hậu phẫu",
        status="completed",
        files=["core/self_history.py"],
        checks=["pytest test_self_history passed"],
        path=log,
    )
    rows = read_events(path=log)
    monkeypatch.setattr(sh, "read_events", lambda limit=200, **kwargs: rows)
    active = current_events()
    assert len(active) == 1
    assert active[0]["kind"] == "surgery_outcome"
    assert active[0]["schema_version"] == 2


def test_telegram_token_is_removed_from_error_url():
    from core.redact import redact

    fake_token = "123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijk"
    cleaned = redact(
        f"HTTPSConnection failed with url: /bot{fake_token}/getUpdates"
    )
    assert fake_token not in cleaned
    assert "REDACTED_TELEGRAM_TOKEN" in cleaned
