"""
skills/knowledge-base/scripts/ingest.py
=======================================
Knowledge Ingest — "AURA tự đến thư viện đọc sách rồi nhớ" (LỚP LOGIC, Level 4).

Nuốt tài liệu (URL / file txt·md·pdf / văn bản thô) -> cắt mảnh -> lưu vào kho tri
thức ChromaDB (collection 'knowledge', tag 'knowledge'). Đây là cách AURA "biết nhiều"
hơn mà KHÔNG cần train lại trọng số — sau này Orchestrator tự tra (RAG).

Tuân thủ CONTEXT.md: bọc try/except, trả ToolResult, validate nguồn, read-only web,
không secret. chromadb/pypdf nạp TRỄ -> thiếu thì báo nhẹ, không sập.
"""

from __future__ import annotations

import sys
from pathlib import Path

# skills/knowledge-base/scripts/ingest.py -> parents[3] = gốc dự án.
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import logging
import re
from urllib.parse import urlparse

from core.schemas import ToolResult

logger = logging.getLogger("aura.skills.knowledge_ingest")

_DEFAULT_CHUNK = 800
_DEFAULT_MAX_CHUNKS = 60
# Thư mục hệ thống nhạy cảm — không đọc file bên trong (least privilege).
_BLOCKED_PREFIXES = ("/etc", "/usr", "/bin", "/sbin", "/boot", "/sys", "/proc",
                     "c:\\windows", "c:\\program files")


# ---------------------------------------------------------------------------
# Lấy nội dung từ nguồn
# ---------------------------------------------------------------------------
def _read_url(url: str) -> str:
    """Cào text qua web.scrape (lazy cross-skill, đúng chuẩn registry)."""
    import json
    from tools.registry import call_skill
    res = call_skill("web.scrape", {"url": url, "max_chars": 40000})
    if not getattr(res, "ok", False):
        raise RuntimeError(f"web.scrape lỗi: {getattr(res, 'error', '?')}")
    return json.loads(res.output).get("text", "")


def _read_file(path: Path) -> str:
    low = str(path).lower()
    if any(low.startswith(pref) for pref in _BLOCKED_PREFIXES):
        raise ValueError(f"CHẶN: file trong thư mục hệ thống: {path}")
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader
        except ModuleNotFoundError as exc:
            raise ModuleNotFoundError("Thiếu 'pypdf'. Cài: pip install pypdf") from exc
        reader = PdfReader(str(path))
        return "\n".join((pg.extract_text() or "") for pg in reader.pages)
    # txt / md / mọi text khác
    return path.read_text(encoding="utf-8", errors="replace")


def _resolve(source: str, text: str, title: str) -> tuple[str, str]:
    """Trả (nội_dung, nhãn_nguồn). Ưu tiên text > URL > file > văn bản thô."""
    if text and text.strip():
        return text, (title or "text")
    src = (source or "").strip()
    if not src:
        raise ValueError("Thiếu nguồn: cần 'source' (URL/file/văn bản) hoặc 'text'.")
    if re.match(r"^https?://", src):
        return _read_url(src), (title or src)
    p = Path(src).expanduser()
    if p.is_file():
        return _read_file(p), (title or str(p))
    # Không phải URL/file -> coi như văn bản thô cần nhớ.
    return src, (title or "text")


def _chunk(text: str, size: int, max_chunks: int) -> list[str]:
    """Cắt theo đoạn, gộp tới ~size ký tự/mảnh. Giữ nhẹ: trần max_chunks."""
    clean = re.sub(r"\n{3,}", "\n\n", (text or "").strip())
    paras = [p.strip() for p in clean.split("\n") if p.strip()]
    chunks: list[str] = []
    buf = ""
    for para in paras:
        if len(buf) + len(para) + 1 <= size:
            buf = f"{buf}\n{para}".strip()
        else:
            if buf:
                chunks.append(buf)
            buf = para[:size]
        if len(chunks) >= max_chunks:
            break
    if buf and len(chunks) < max_chunks:
        chunks.append(buf)
    return chunks


# ---------------------------------------------------------------------------
# Tool công khai cho Registry
# ---------------------------------------------------------------------------
def tool_knowledge_ingest(
    source: str = "",
    text: str = "",
    title: str = "",
    chunk_size: int = _DEFAULT_CHUNK,
    max_chunks: int = _DEFAULT_MAX_CHUNKS,
    memory=None,
) -> ToolResult:
    """
    Tool 'knowledge.ingest': nuốt tài liệu vào kho tri thức (tag knowledge). Luôn trả ToolResult.
    """
    try:
        content, label = _resolve(source, text, title)
    except ModuleNotFoundError as exc:
        return ToolResult.failure("knowledge.ingest", str(exc))
    except Exception as exc:  # noqa: BLE001
        return ToolResult.failure("knowledge.ingest", f"Không đọc được nguồn: {exc}")

    if not content or not content.strip():
        return ToolResult.failure("knowledge.ingest", f"Nguồn rỗng/không có text: {label}")

    chunks = _chunk(content, max(200, chunk_size), max(1, max_chunks))
    if not chunks:
        return ToolResult.failure("knowledge.ingest", "Không cắt được mảnh nào để nhớ.")

    # Lưu vào ChromaDB collection 'knowledge'.
    try:
        from core.memory import CollectionName, MemoryStore
        from core.schemas import MemoryRecord
    except Exception as exc:  # noqa: BLE001
        return ToolResult.failure("knowledge.ingest", f"Thiếu memory/schema: {exc}")

    mem = memory
    if mem is None:
        try:
            mem = MemoryStore()
        except Exception as exc:  # noqa: BLE001 — thiếu chromadb
            return ToolResult.failure(
                "knowledge.ingest", f"Không mở được kho tri thức (cài chromadb?): {exc}"
            )

    saved = 0
    for i, ch in enumerate(chunks):
        try:
            rec = MemoryRecord(role="system", text=ch,
                               tags=["knowledge", f"source:{label}", f"part:{i+1}"])
            mem.add_memory(rec, CollectionName.KNOWLEDGE)
            saved += 1
        except Exception as exc:  # noqa: BLE001 — lưu 1 mảnh lỗi không chặn cả mẻ
            logger.warning("Lưu mảnh tri thức lỗi: %s", exc)

    if saved == 0:
        return ToolResult.failure("knowledge.ingest", "Không lưu được mảnh nào vào kho.")
    return ToolResult.success(
        "knowledge.ingest",
        output=f"📚 Đã đọc & nhớ {saved} mảnh tri thức từ: {label} (kho 'knowledge').",
    )


# ---------------------------------------------------------------------------
# CLI độc lập (Level 4)
# ---------------------------------------------------------------------------
def _main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="AURA skill knowledge.ingest — tự đọc sách rồi nhớ.")
    ap.add_argument("--source", default="", help="URL / đường dẫn file / văn bản thô.")
    ap.add_argument("--text", default="", help="Văn bản dán thẳng.")
    ap.add_argument("--title", default="", help="Nhãn nguồn.")
    ap.add_argument("--chunk-size", type=int, default=_DEFAULT_CHUNK)
    ap.add_argument("--max-chunks", type=int, default=_DEFAULT_MAX_CHUNKS)
    args = ap.parse_args(argv)

    result = tool_knowledge_ingest(
        source=args.source, text=args.text, title=args.title,
        chunk_size=args.chunk_size, max_chunks=args.max_chunks,
    )
    print(result.output if result.ok else f"[LỖI] {result.error}")
    return 0 if result.ok else 1


__all__ = ["tool_knowledge_ingest"]


if __name__ == "__main__":
    raise SystemExit(_main())
