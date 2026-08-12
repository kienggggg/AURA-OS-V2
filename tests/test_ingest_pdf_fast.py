"""Đường NHANH đọc PDF (pdf-inspector) — không được làm gãy markitdown cũ.

Đo thật 06/08/2026 trên PDF 25 trang: 76ms vs 980ms của pdfplumber (~12,8 lần),
và ra Markdown CÓ CẤU TRÚC (78 tiêu đề, 12 bảng) thay vì chữ phẳng.

Điều phải giữ: PDF scan / thiếu thư viện / lỗi -> LÙI VỀ markitdown, không nổ.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core import ingest


def test_scanned_pdf_falls_back(monkeypatch, tmp_path):
    """PDF scan (exit 3) -> đường nhanh trả rỗng để caller dùng markitdown."""
    class P:
        returncode = 3
        stdout = b""
    monkeypatch.setattr(ingest.subprocess, "run", lambda *a, **k: P())
    monkeypatch.setattr(ingest, "_PY311", Path(__file__))   # giả vờ có venv
    assert ingest._pdf_fast(tmp_path / "x.pdf") == ""


def test_fast_path_error_falls_back(monkeypatch, tmp_path):
    """pdf-inspector nổ -> trả rỗng, KHÔNG ném lỗi ra ngoài."""
    def boom(*a, **k):
        raise OSError("hỏng")
    monkeypatch.setattr(ingest.subprocess, "run", boom)
    monkeypatch.setattr(ingest, "_PY311", Path(__file__))
    assert ingest._pdf_fast(tmp_path / "x.pdf") == ""


def test_no_venv_means_no_fast_path(monkeypatch, tmp_path):
    monkeypatch.setattr(ingest, "_PY311", tmp_path / "khong_co.exe")
    assert ingest._pdf_fast(tmp_path / "x.pdf") == ""


def test_non_pdf_skips_fast_path(monkeypatch, tmp_path):
    """File .txt KHÔNG được đi đường PDF."""
    called = []
    monkeypatch.setattr(ingest, "_pdf_fast", lambda *a, **k: called.append(1) or "")
    monkeypatch.setattr(ingest, "_PY311", tmp_path / "khong_co.exe")
    f = tmp_path / "a.txt"
    f.write_text("chào Sếp", encoding="utf-8")
    ingest.to_markdown(f)
    assert called == [], "file không phải PDF mà vẫn gọi đường nhanh"


def test_missing_file_still_raises(tmp_path):
    with pytest.raises(ingest.IngestError):
        ingest.to_markdown(tmp_path / "khong_ton_tai.pdf")


def test_worker_bails_out_on_scanned_pdf():
    """Worker phải thoát mã 3 khi PDF không phải chữ thật."""
    assert 'pdf_type' in ingest._PDF_FAST_WORKER
    assert "sys.exit(3)" in ingest._PDF_FAST_WORKER


@pytest.mark.skipif(
    not (Path(r"C:\Users\baloa\Downloads\Trải nghiệm Python.pdf").exists()),
    reason="không có PDF thật để nghiệm thu",
)
def test_real_pdf_returns_structured_markdown():
    """Nghiệm thu THẬT: phải ra Markdown có tiêu đề, không phải chữ phẳng."""
    md = ingest.to_markdown(r"C:\Users\baloa\Downloads\Trải nghiệm Python.pdf")
    assert len(md) > 1000
    assert md.count("##") > 10, "không có tiêu đề -> đường nhanh không chạy?"
