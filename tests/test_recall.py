"""Trí nhớ biết chọn — HyDE + Self-RAG (đợt sàng 06/08/2026).

Ba điều phải giữ:
 1. Câu vô nghĩa (chào/lệnh) thì KHÔNG lục trí nhớ — đỡ tốn token.
 2. Ký ức lạc đề bị loại — nhưng KHÔNG BAO GIỜ lọc sạch trơn thành mù.
 3. HyDE hỏng thì lùi về câu gốc, tuyệt đối không làm hỏng việc tìm kiếm.
"""

from __future__ import annotations

import pytest

from core import recall


# --------------------------- cổng [Retrieve] --------------------------- #
@pytest.mark.parametrize("q", ["hi", "ok", "oke", "cảm ơn", "y", "vâng", "xong", "thanks"])
def test_skip_recall_for_smalltalk(q):
    assert recall.should_retrieve(q) is False


@pytest.mark.parametrize("q", ["tạm ngừng săn job", "bật lại săn job", "mở notepad", "tắt máy"])
def test_skip_recall_for_commands(q):
    assert recall.should_retrieve(q) is False


@pytest.mark.parametrize("q", [
    "mật khẩu wifi là gì",
    "xe robot nối dây thế nào",
    "hôm trước mình bàn gì về TEKY",
])
def test_do_recall_for_real_questions(q):
    assert recall.should_retrieve(q) is True


def test_empty_query_skips():
    assert recall.should_retrieve("") is False
    assert recall.should_retrieve("   ") is False


# ---------------------------- cổng [IsREL] ----------------------------- #
def test_filter_drops_far_memories():
    pairs = [("gần", 0.3), ("vừa", 0.9), ("xa", 1.5), ("rất xa", 1.9)]
    assert recall.filter_relevant(pairs, 1.2) == ["gần", "vừa"]


def test_filter_keeps_all_when_threshold_wide():
    pairs = [("a", 0.3), ("b", 1.9)]
    assert len(recall.filter_relevant(pairs, 2.0)) == 2


def test_filter_never_crashes_on_none_distance():
    assert recall.filter_relevant([("a", None)], 0.1) == ["a"]


# ------------------------------- HyDE ---------------------------------- #
def test_hyde_without_llm_returns_original():
    assert recall.hyde_expand("wifi tên gì", None) == "wifi tên gì"


def test_hyde_falls_back_when_llm_raises():
    def boom(_p, _s):
        raise RuntimeError("LLM chết")
    assert recall.hyde_expand("wifi tên gì", boom) == "wifi tên gì"


def test_hyde_falls_back_when_llm_returns_empty():
    assert recall.hyde_expand("wifi tên gì", lambda p, s: "   ") == "wifi tên gì"


def test_hyde_keeps_original_words():
    """Phải GIỮ câu gốc — kẻo mất từ khoá riêng (tên người, tên file)."""
    out = recall.hyde_expand("TEKY phỏng vấn", lambda p, s: "Một buổi tuyển giáo viên.")
    assert "TEKY" in out and "Một buổi tuyển giáo viên." in out


# --------------------------- smart_recall ------------------------------ #
class _FakeStore:
    def __init__(self, scored):
        self._scored = scored
        self.plain_called = False

    def search_scored(self, query, collection=None, k=None):
        return self._scored

    def search_memory(self, query, collection=None, k=None):
        self.plain_called = True
        return [r for r, _ in self._scored]


def test_smart_recall_filters(monkeypatch):
    store = _FakeStore([("gần", 0.2), ("lạc đề", 1.8)])
    out = recall.smart_recall(store, "câu hỏi thật dài để qua cổng", max_distance=1.0)
    assert out == ["gần"]


def test_smart_recall_never_returns_empty_when_something_exists():
    """Lọc gắt tới đâu cũng phải giữ mẩu gần nhất — thà thừa còn hơn mù."""
    store = _FakeStore([("xa", 1.7), ("xa hơn", 1.9)])
    out = recall.smart_recall(store, "câu hỏi thật dài để qua cổng", max_distance=0.1)
    assert out == ["xa"]


def test_smart_recall_skips_on_smalltalk():
    store = _FakeStore([("gì đó", 0.1)])
    assert recall.smart_recall(store, "ok") == []


def test_smart_recall_falls_back_when_no_search_scored():
    class Old:
        def search_memory(self, query, collection=None, k=None):
            return ["cũ"]
    out = recall.smart_recall(Old(), "câu hỏi thật dài để qua cổng")
    assert out == ["cũ"]


# ------------------- cổng GHI: đừng nhớ rác xã giao -------------------- #
@pytest.mark.parametrize("junk", [
    "xin chào", "ok", "vâng ạ", "dạ", "cảm ơn", "y",
    "Vâng, sếp cần em hỗ trợ gì ạ?",
])
def test_do_not_remember_smalltalk(junk):
    assert recall.should_remember(junk) is False


@pytest.mark.parametrize("real", [
    # KHÔNG dùng bí mật thật làm dữ liệu test.  Dòng này từng chứa mật khẩu
    # wifi thật của Sếp và đã đi vào commit f06d111 (06/08/2026) — test là mã
    # nguồn, mà mã nguồn thì được commit, được sao chép, được AI khác đọc.
    "mật khẩu wifi nhà mình là MatKhauGia@Test123 nhé",
    "hôm nay phỏng vấn TEKY bị từ chối, hẹn nộp lại CV tháng 9",
    "robot dùng chân D13 cho STBY của TB6612",
])
def test_do_remember_real_content(real):
    assert recall.should_remember(real) is True


def test_remember_gate_is_stricter_than_recall_gate():
    """Ghi phải KHÓ hơn đọc: câu đáng đọc chưa chắc đáng lưu vĩnh viễn."""
    q = "wifi?"
    assert recall.should_retrieve(q) is True
    assert recall.should_remember(q) is False
