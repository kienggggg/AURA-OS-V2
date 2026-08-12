"""AURA phải trả lời 'cần đăng tay gì / file ở đâu' từ KHO THẬT, không để LLM
đoán bừa (Sếp gặp: hỏi Wattpad -> mascot bịa 'WhatsApp')."""

from __future__ import annotations

import asyncio
import json

from core.manual_publish_query import is_manual_publish_question as q


def test_detector_matches_publish_questions():
    for t in ["đưa tôi đường dẫn những thứ cần đăng wattpad",
              "truyện cần đăng ở đâu", "file video tiktok đâu",
              "có gì cần đăng tay không", "đường dẫn sách payhip"]:
        assert q(t), t


def test_detector_ignores_unrelated_and_login():
    for t in ["đăng nhập payhip giúp tôi", "đăng ký tài khoản",
              "hôm nay thời tiết sao", "viết cho tôi 1 chương truyện"]:
        assert not q(t), t


def test_answer_is_honest_when_nothing_exported(monkeypatch, tmp_path):
    import core.manual_publish_query as mpq
    monkeypatch.setattr(mpq, "_desktop", lambda: tmp_path)  # Desktop rỗng
    monkeypatch.setattr("core.manual_publish_desk.list_items", lambda: [])
    out = mpq.answer_manual_publish()
    assert "không đoán" in out.lower() or "chưa thấy" in out.lower()


def test_mascot_publish_question_uses_real_data_not_llm(monkeypatch):
    """Bong bóng mascot hỏi Wattpad -> trả từ kho thật, KHÔNG rơi xuống LLM."""
    from interface.server import AuraWebSocketServer
    import core.manual_publish_query as mpq

    monkeypatch.setattr(mpq, "answer_manual_publish",
                        lambda: "📋 4 bộ truyện ở Desktop\\...\\TRUYEN_DANG_TAY")

    class BoomOrchestrator:
        def process_message(self, _t):
            raise AssertionError("câu hỏi đăng-tay không được rơi xuống LLM")

    sent: list = []

    class FakeWS:
        async def send(self, raw: str) -> None:
            sent.append(json.loads(raw))

    server = AuraWebSocketServer(BoomOrchestrator(), event_queue=asyncio.Queue())
    asyncio.run(server._handle_chat(FakeWS(), "đưa tôi đường dẫn những thứ cần đăng wattpad"))

    responses = [m["text"] for m in sent if m["type"] == "response"]
    assert responses and "TRUYEN_DANG_TAY" in responses[-1]
