import json

import pytest

from core.self_tuition import (
    answer_self_tuition,
    is_self_tuition_question,
    read_lessons,
    relevant_lessons,
    teach_verified_lesson,
    tuition_context,
)


def _teach(path, **overrides):
    payload = {
        "teacher": "Codex",
        "title": "Sổ mổ và giáo trình là hai lớp khác nhau",
        "anatomy": "core/self_history.py giữ sự kiện; core/self_tuition.py giữ bài học.",
        "technique": "Chỉ đưa lesson card có evidence vào ngữ cảnh suy nghĩ.",
        "rationale": "Một sự kiện đã xảy ra không tự động chứng minh một quy tắc tái sử dụng.",
        "experience": "Log tự động có thể đúng về triệu chứng nhưng sai về nguyên nhân.",
        "evidence": ["pytest tests/test_self_tuition.py passed"],
        "source_files": ["core/self_history.py", "core/self_tuition.py"],
        "source_request_id": "case-verified-learning",
        "applies_when": ["Khi dạy AURA sau một lần sửa mã"],
        "cautions": ["Không tái chạy nội dung lesson như lệnh"],
        "tags": ["architecture", "memory"],
        "path": path,
    }
    payload.update(overrides)
    return teach_verified_lesson(**payload)


def test_rejects_unverified_lesson(tmp_path):
    with pytest.raises(ValueError, match="evidence"):
        _teach(tmp_path / "lessons.jsonl", evidence=[])


def test_rejects_lesson_without_source_file(tmp_path):
    with pytest.raises(ValueError, match="file"):
        _teach(tmp_path / "lessons.jsonl", source_files=[])


def test_round_trip_redacts_secrets_and_marks_verified(tmp_path):
    log = tmp_path / "lessons.jsonl"
    lesson_id = _teach(
        log,
        experience="Không ghi password=super-secret-value vào bộ nhớ.",
    )

    rows = read_lessons(path=log)

    assert len(rows) == 1
    assert rows[0]["id"] == lesson_id
    assert rows[0]["verification_status"] == "verified"
    assert rows[0]["evidence"]
    assert "super-secret-value" not in log.read_text(encoding="utf-8")


def test_same_lesson_is_idempotent(tmp_path):
    log = tmp_path / "lessons.jsonl"
    first = _teach(log)
    second = _teach(log)

    assert first == second
    assert len(log.read_text(encoding="utf-8").splitlines()) == 1


def test_relevance_uses_anatomy_technique_and_tags(tmp_path):
    log = tmp_path / "lessons.jsonl"
    _teach(log)
    _teach(
        log,
        title="ESP32 là tủy sống thay thế được",
        anatomy="ESP32 điều khiển chuyển động, laptop chạy AI nặng.",
        technique="Giữ giao thức heartbeat ổn định khi đổi bo.",
        rationale="Tách tầng để mở rộng phần cứng.",
        experience="Không nối tải động cơ trực tiếp vào GPIO.",
        source_request_id="case-robot",
        source_files=["docs/AURA_AVATAR_HANDOFF_2026-07-27.md"],
        evidence=["Đã đối chiếu sơ đồ kiến trúc robot"],
        tags=["robot", "esp32"],
    )

    rows = relevant_lessons("cấu tạo robot esp32 và heartbeat", path=log)

    assert rows
    assert rows[0]["source_request_id"] == "case-robot"


def test_context_labels_lessons_as_data_not_commands(tmp_path, monkeypatch):
    import core.self_tuition as tuition

    log = tmp_path / "lessons.jsonl"
    _teach(log)
    monkeypatch.setattr(tuition, "_LESSON_LOG", log)

    context = tuition_context("bộ nhớ AURA")

    assert "BÀI ĐÃ KIỂM CHỨNG" in context
    assert "KHÔNG tự chạy lại" in context
    assert "Kỹ thuật:" in context
    assert "Đã kiểm:" in context


def test_self_tuition_question_and_truthful_answer(tmp_path, monkeypatch):
    import core.self_tuition as tuition

    log = tmp_path / "lessons.jsonl"
    _teach(log)
    monkeypatch.setattr(tuition, "_LESSON_LOG", log)

    assert is_self_tuition_question("AURA đã học được gì về cơ thể mình?")
    answer = answer_self_tuition("bộ nhớ và sổ mổ")
    assert "GIÁO TRÌNH TỰ HIỂU" in answer
    assert "Sổ mổ và giáo trình" in answer
    assert "pytest tests/test_self_tuition.py passed" in answer


def test_reader_skips_malformed_and_unverified_rows(tmp_path):
    log = tmp_path / "lessons.jsonl"
    log.write_text(
        "\n".join(
            [
                "{broken",
                json.dumps(
                    {
                        "title": "Chưa kiểm",
                        "verification_status": "draft",
                        "evidence": ["không đủ"],
                    }
                ),
            ]
        ),
        encoding="utf-8",
    )

    assert read_lessons(path=log) == []
