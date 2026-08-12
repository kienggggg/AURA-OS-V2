"""Trần thời gian cho một lượt chat — AURA phải trả lời, không được im lặng.

08/08/2026: đo được một câu hỏi tự do chạy 500 giây vẫn chưa trả về (Ollama trả
rỗng -> rơi xuống cloud -> lặp kế hoạch).  Telegram vì thế không có gì để gửi và
Sếp tưởng kênh chỉ một chiều.  Các test dưới giữ cho lỗi đó không quay lại.
"""
from __future__ import annotations

import time

import pytest

from core.orchestrator import AURA_Orchestrator


class _Stub:
    """Chỉ mượn phần trần thời gian, không dựng cả orchestrator thật."""

    _impl_within_budget = AURA_Orchestrator._impl_within_budget

    def __init__(self, delay: float, budget: float) -> None:
        self._delay = delay
        self._budget = budget
        self.calls = 0

    def _process_message_impl(self, text: str) -> str:
        self.calls += 1
        time.sleep(self._delay)
        return f"xong: {text}"


@pytest.fixture(autouse=True)
def _budget(monkeypatch):
    def apply(value: float):
        from core import orchestrator as mod

        monkeypatch.setattr(mod.settings, "chat_turn_budget_s", value, raising=False)

    return apply


def test_cau_tra_loi_nhanh_di_qua_binh_thuong(_budget):
    _budget(5.0)
    stub = _Stub(delay=0.0, budget=5.0)
    assert stub._impl_within_budget("chào") == "xong: chào"


def test_qua_han_thi_tra_loi_that_tha_chu_khong_treo(_budget):
    _budget(0.5)
    stub = _Stub(delay=30.0, budget=0.5)
    started = time.monotonic()
    reply = stub._impl_within_budget("câu hỏi dài")
    elapsed = time.monotonic() - started

    assert elapsed < 5.0, f"vẫn treo {elapsed:.1f}s — trần không có tác dụng"
    assert reply, "im lặng còn tệ hơn câu trả lời xấu"
    assert "giây" in reply, reply


def test_dat_0_thi_tat_tran(_budget):
    _budget(0.0)
    stub = _Stub(delay=0.0, budget=0.0)
    assert stub._impl_within_budget("x") == "xong: x"
    assert stub.calls == 1
