"""Ingest tài liệu -> Markdown sạch cho LLM đọc (tiết kiệm token).

Keo dán quanh `markitdown` (Microsoft): PDF / Word / Excel / PowerPoint / HTML
-> Markdown gọn. markitdown chỉ chạy Python 3.10-3.13 nên gọi qua venv phụ
`.venv311` bằng subprocess — venv chính 3.14 của AURA không cài được.

Dùng trong code:      from core.ingest import to_markdown
                      md = to_markdown(r"D:\\file.pdf")
Dùng ngoài terminal:  venv\\Scripts\\python.exe -m core.ingest <file> [-o ra.md]

Lưu ý: YouTube URL markitdown hay fail (YouTube chặn transcript) — video thì
dùng pipeline faster-whisper sẵn có, đừng đi đường này.
"""

from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger("aura.ingest")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
_PY311 = PROJECT_ROOT / ".venv311" / "Scripts" / "python.exe"

# Đuôi file markitdown xử lý tốt (đã test PDF tiếng Việt chuẩn 2026-07-19)
SUPPORTED = {".pdf", ".docx", ".xlsx", ".xls", ".pptx", ".html", ".htm",
             ".csv", ".json", ".xml", ".epub", ".zip", ".msg"}


class IngestError(RuntimeError):
    pass


def _native_fallback(path: Path) -> str:
    """Fallback đọc trực tiếp khi venv phụ markitdown không có sẵn."""
    suf = path.suffix.lower()
    text = path.read_text(encoding="utf-8", errors="replace").strip()
    if suf in {".txt", ".md", ".markdown"}:
        return text
    if suf in {".json", ".xml"}:
        return f"```\n{text}\n```"
    if suf == ".csv":
        lines = [line.strip().split(",") for line in text.splitlines() if line.strip()]
        if not lines:
            return ""
        md_lines = ["| " + " | ".join(lines[0]) + " |", "| " + " | ".join(["---"] * len(lines[0])) + " |"]
        for row in lines[1:]:
            md_lines.append("| " + " | ".join(row) + " |")
        return "\n".join(md_lines)
    if suf in {".html", ".htm"}:
        import re
        clean = re.sub(r"<script.*?>.*?</script>", "", text, flags=re.DOTALL | re.IGNORECASE)
        clean = re.sub(r"<style.*?>.*?</style>", "", clean, flags=re.DOTALL | re.IGNORECASE)
        clean = re.sub(r"<[^>]+>", "", clean)
        return "\n".join([line.strip() for line in clean.splitlines() if line.strip()])
    return text


_PDF_FAST_WORKER = r'''
import sys
import pdf_inspector as pi
path = sys.argv[1]
cls = pi.classify_pdf(path)
# PDF scan/ảnh thì pdf_inspector không trích được chữ -> để markitdown lo.
if getattr(cls, "pdf_type", "") != "text_based":
    sys.exit(3)
r = pi.process_pdf(path)
md = getattr(r, "markdown", None) or getattr(r, "text", "") or ""
sys.stdout.write(md)
'''


def _pdf_fast(path: Path, timeout: int = 60) -> str:
    """Đường NHANH cho PDF chữ thật — pdf-inspector (Rust, không GPU/khoá/mạng).

    Đo thật 06/08/2026 trên file 25 trang: **76ms** so với 980ms của pdfplumber
    (nhanh ~12,8 lần), và ra Markdown CÓ CẤU TRÚC (78 tiêu đề + 12 bảng) thay vì
    chữ phẳng.

    Trả "" khi không dùng được (PDF scan, chưa cài, lỗi) -> caller lùi về markitdown.
    """
    if not _PY311.exists():
        return ""
    try:
        proc = subprocess.run(
            [str(_PY311), "-c", _PDF_FAST_WORKER, str(path)],
            capture_output=True, timeout=timeout,
            env={"PYTHONUTF8": "1", "SYSTEMROOT": "C:\\Windows",
                 "PATH": "C:\\Windows\\System32"},
        )
    except Exception as exc:  # noqa: BLE001 — hỏng thì lùi về đường cũ
        logger.debug("pdf-inspector lỗi (%s) — dùng markitdown.", exc)
        return ""
    if proc.returncode != 0:
        return ""      # 3 = PDF scan, cần OCR; số khác = lỗi
    return proc.stdout.decode("utf-8", errors="replace").strip()


def to_markdown(source: str | Path, timeout: int = 120) -> str:
    """Chuyển file/URL thành Markdown. Tự động fallback nếu thiếu markitdown."""
    src = str(source)
    is_url = src.lower().startswith(("http://", "https://"))
    src_path = Path(src)
    if not is_url and not src_path.exists():
        raise IngestError(f"Không thấy file: {src}")

    # PDF chữ thật -> đường nhanh; PDF scan hoặc lỗi thì rơi xuống markitdown.
    if not is_url and src_path.suffix.lower() == ".pdf":
        fast = _pdf_fast(src_path)
        if fast:
            return fast

    if _PY311.exists():
        proc = subprocess.run(
            [str(_PY311), "-m", "markitdown", src],
            capture_output=True, timeout=timeout,
            env={"PYTHONUTF8": "1", "SYSTEMROOT": "C:\\Windows",
                 "PATH": "C:\\Windows\\System32"},
        )
        out = proc.stdout.decode("utf-8", errors="replace").strip()
        if proc.returncode == 0 and out:
            return out

    if not is_url:
        try:
            return _native_fallback(src_path)
        except Exception as exc:
            raise IngestError(f"Hỏng fallback nạp file {src}: {exc}") from exc

    raise IngestError(f"Thiếu markitdown venv {_PY311} để nạp URL.")


def ingest_to_file(source: str | Path, out_path: str | Path | None = None) -> Path:
    """Chuyển rồi ghi ra .md (mặc định cạnh file gốc / data/outputs/ingest cho URL)."""
    md = to_markdown(source)
    src = str(source)
    if out_path is None:
        if src.lower().startswith(("http://", "https://")):
            safe = "".join(c if c.isalnum() else "_" for c in src[-60:]).strip("_")
            out_path = PROJECT_ROOT / "data" / "outputs" / "ingest" / f"{safe}.md"
        else:
            out_path = Path(src).with_suffix(".md")
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(md, encoding="utf-8")
    return out_path


if __name__ == "__main__":
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        raise SystemExit(1)
    dst = None
    if "-o" in args:
        i = args.index("-o")
        dst = args[i + 1]
        args = args[:i] + args[i + 2:]
    p = ingest_to_file(args[0], dst)
    print(f"[OK] -> {p}")
