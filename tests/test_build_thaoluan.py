from __future__ import annotations

import importlib.util
import json
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "build_thaoluan.py"
SPEC = importlib.util.spec_from_file_location("build_thaoluan", MODULE_PATH)
assert SPEC and SPEC.loader
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


def _redirect(monkeypatch, tmp_path: Path) -> Path:
    source = tmp_path / "thaoluan"
    monkeypatch.setattr(builder, "ROOT", tmp_path)
    monkeypatch.setattr(builder, "SRC", source)
    monkeypatch.setattr(builder, "OUT", tmp_path / "thaoluan.html")
    monkeypatch.setattr(builder, "MANIFEST", source / "manifest.json")
    monkeypatch.setattr(builder, "STATE", source / "state.json")
    source.mkdir()
    return source


def test_builds_two_speaker_room_and_selects_next(monkeypatch, tmp_path):
    source = _redirect(monkeypatch, tmp_path)
    (source / "001-codex.html").write_text("<p>Mở đầu</p>", encoding="utf-8")
    (source / "002-claude.html").write_text("<p>Phản biện</p>", encoding="utf-8")

    assert builder.build() == 0
    state = json.loads((source / "state.json").read_text(encoding="utf-8"))
    assert state["order"] == ["codex", "claude"]
    assert state["completed_turns"] == 2
    assert state["next_speaker"] == "codex"
    page = (tmp_path / "thaoluan.html").read_text(encoding="utf-8")
    assert "Mở đầu" in page and "Phản biện" in page
    assert "Antigravity" not in page


def test_rejects_a_gap_in_the_numbering(monkeypatch, tmp_path):
    source = _redirect(monkeypatch, tmp_path)
    (source / "001-codex.html").write_text("<p>Mở đầu</p>", encoding="utf-8")
    (source / "003-claude.html").write_text("<p>Nhảy cóc</p>", encoding="utf-8")
    assert builder.build() == 2
    assert not (tmp_path / "thaoluan.html").exists()


def test_allows_one_speaker_to_cover_for_the_other(monkeypatch, tmp_path):
    """Xen lượt là nhịp mặc định, không phải luật cứng.

    08/08/2026 Codex hết hạn mức chạy công cụ tới 15/08 nên Claude viết tiếp
    lượt 017.  Hai bảo đảm thật sự quan trọng — đánh số liên tục và lời cũ bất
    biến — vẫn được các test khác giữ.
    """
    source = _redirect(monkeypatch, tmp_path)
    (source / "001-codex.html").write_text("<p>Mở đầu</p>", encoding="utf-8")
    (source / "002-claude.html").write_text("<p>Phản biện</p>", encoding="utf-8")
    (source / "003-claude.html").write_text("<p>Viết thay khi Codex nghỉ</p>", encoding="utf-8")

    assert builder.build() == 0
    page = (tmp_path / "thaoluan.html").read_text(encoding="utf-8")
    assert "Viết thay khi Codex nghỉ" in page
    # Người viết mỗi lượt vẫn hiện trên thẻ: hai lượt liền của Claude phải đọc ra được.
    assert page.count("Claude · Lượt") == 2


def test_rejects_editing_a_committed_turn(monkeypatch, tmp_path):
    source = _redirect(monkeypatch, tmp_path)
    first = source / "001-codex.html"
    first.write_text("<p>Bản gốc</p>", encoding="utf-8")
    assert builder.build() == 0

    first.write_text("<p>Đã bị sửa</p>", encoding="utf-8")
    assert builder.build() == 2
    page = (tmp_path / "thaoluan.html").read_text(encoding="utf-8")
    assert "Bản gốc" in page
    assert "Đã bị sửa" not in page


def test_rejects_deleting_a_committed_turn(monkeypatch, tmp_path):
    source = _redirect(monkeypatch, tmp_path)
    first = source / "001-codex.html"
    first.write_text("<p>Bản gốc</p>", encoding="utf-8")
    assert builder.build() == 0
    first.unlink()
    assert builder.build() == 2
