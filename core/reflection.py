"""
core/reflection.py
==================
Self-Reflection — cơ chế "biết đau, biết nhớ, biết sửa sai" của AURA.

Mỗi ngày (hoặc khi gọi tay), AURA đọc lại LOG 24h qua (lỗi/cảnh báo/tương tác),
nhờ LocalCPUEngine (gemma4, CPU-only) đúc kết thành "Bài học rút kinh nghiệm"
(Lessons Learned), rồi LƯU vào ChromaDB (collection system_rules) với tag
`core_lesson`. Hôm sau, Orchestrator truy vấn các core_lesson liên quan TRƯỚC khi
thực thi kỹ năng để tự điều chỉnh hành vi.

Tuân thủ CONTEXT.md: bọc try/except (§2), không secret (§1), không phụ thuộc nặng
bắt buộc (LLM/Chroma nạp TRỄ, thiếu thì degrade chứ không sập). Engine & MemoryStore
tiêm được (dependency injection) để test offline.

Mặc định log file: data/logs/aura.log. Gọi `configure_file_logging()` lúc khởi động
(vd trong main.py) để bắt log ra file cho reflection đọc.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from core.config import PROJECT_ROOT

logger = logging.getLogger("aura.reflection")

CORE_LESSON_TAG = "core_lesson"
_LOG_DIR = PROJECT_ROOT / "data" / "logs"
_DEFAULT_LOG_PATH = _LOG_DIR / "aura.log"
_MAX_LOG_LINES = 800            # trần dòng đọc -> nhẹ CPU, không nuốt log khổng lồ
_MAX_LESSONS = 5
# Dòng "đáng học": lỗi/cảnh báo + tương tác người dùng.
_SIGNAL_RE = re.compile(r"\b(ERROR|WARNING|CRITICAL|user|Sếp|VIBE DIFF|fail|lỗi)\b", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Bật ghi log ra file (gọi 1 lần lúc khởi động nếu muốn reflection có dữ liệu)
# ---------------------------------------------------------------------------
def configure_file_logging(path: str | Path | None = None, level: int = logging.INFO) -> Path:
    """
    Gắn FileHandler vào root logger để log hệ thống được ghi ra file (cho reflection đọc).
    An toàn gọi nhiều lần (không gắn trùng). Trả về đường dẫn file log.
    """
    log_path = Path(path) if path else _DEFAULT_LOG_PATH
    log_path.parent.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    abs_path = str(log_path.resolve())
    for h in root.handlers:  # tránh gắn trùng FileHandler cùng đường dẫn
        if isinstance(h, logging.FileHandler) and getattr(h, "baseFilename", "") == abs_path:
            return log_path
    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"  # CÓ ngày -> lọc 24h được
    ))
    handler.setLevel(level)
    root.addHandler(handler)
    logger.info("Đã bật ghi log ra file: %s", abs_path)
    return log_path


# ---------------------------------------------------------------------------
# Đọc log gần đây
# ---------------------------------------------------------------------------
def _read_recent_logs(log_path: Path, hours: int, max_lines: int) -> str:
    """
    Đọc các dòng log đáng chú ý trong `hours` giờ qua. Best-effort lọc theo thời gian
    (asctime mặc định có ngày); dòng không parse được thì vẫn giữ nếu mang tín hiệu.
    """
    if not log_path.is_file():
        return ""
    try:
        lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        logger.warning("Đọc log lỗi: %s", exc)
        return ""

    lines = lines[-max_lines:]  # chỉ phần đuôi -> nhẹ
    cutoff = datetime.now() - timedelta(hours=hours)
    kept: list[str] = []
    for ln in lines:
        if not _SIGNAL_RE.search(ln):
            continue  # chỉ giữ dòng đáng học (lỗi/cảnh báo/tương tác)
        ts = _parse_ts(ln)
        if ts is not None and ts < cutoff:
            continue  # quá 24h -> bỏ
        kept.append(ln)
    return "\n".join(kept)


def _parse_ts(line: str):
    """Bóc timestamp đầu dòng (định dạng asctime mặc định). None nếu không parse được."""
    m = re.match(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", line)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Đúc kết bài học (LLM batched, fallback heuristic)
# ---------------------------------------------------------------------------
def _summarize_lessons(log_text: str, engine=None) -> list[str]:
    """
    Gọi LocalCPUEngine (gemma4) tóm tắt log -> tối đa _MAX_LESSONS bài học ngắn gọn.
    LLM offline/lỗi -> fallback heuristic (tổng hợp lỗi/cảnh báo hay gặp).
    """
    eng = engine
    if eng is None:
        try:
            from core.llm import LocalCPUEngine
            eng = LocalCPUEngine()
        except Exception as exc:  # noqa: BLE001
            logger.info("Không nạp được LocalCPUEngine (%s) -> heuristic.", exc)
            eng = None

    if eng is not None:
        system = (
            "Bạn là bộ phản tỉnh của AURA. Dưới đây là log 24h (lỗi, cảnh báo, tương tác). "
            f"Rút ra TỐI ĐA {_MAX_LESSONS} BÀI HỌC ngắn gọn, mỗi bài 1 câu, actionable, "
            "giúp mai làm tốt hơn (tránh lặp lỗi, chỉnh hành vi). Trả về MỘT mảng JSON "
            'các chuỗi, không giải thích. Ví dụ: ["Luôn timeout 300s khi nạp model lớn"].'
        )
        try:
            res = eng.complete(
                [{"role": "user", "content": log_text[:6000]}],
                system_prompt=system, temperature=0.2, max_tokens=400,
            )
            if res.get("ok"):
                import json
                m = re.search(r"\[.*\]", res["text"], re.DOTALL)
                arr = json.loads(m.group(0)) if m else json.loads(res["text"])
                lessons = [str(x).strip() for x in arr if str(x).strip()]
                if lessons:
                    return lessons[:_MAX_LESSONS]
        except Exception as exc:  # noqa: BLE001 — LLM hỏng -> heuristic
            logger.info("LLM đúc bài học hỏng (%s) -> heuristic.", exc)

    return _heuristic_lessons(log_text)


def _heuristic_lessons(log_text: str) -> list[str]:
    """Fallback: gom các thông điệp lỗi/cảnh báo lặp nhiều thành bài học thô."""
    counter: dict[str, int] = {}
    for ln in log_text.splitlines():
        m = re.search(r"\[(ERROR|WARNING|CRITICAL)\]\s+[^:]+:\s*(.+)", ln)
        if not m:
            continue
        msg = re.sub(r"\d+", "N", m.group(2)).strip()[:120]  # gộp biến thể số
        key = f"{m.group(1)}: {msg}"
        counter[key] = counter.get(key, 0) + 1
    top = sorted(counter.items(), key=lambda kv: kv[1], reverse=True)[:_MAX_LESSONS]
    return [f"Hay gặp ({n} lần) — cần xử lý: {k}" for k, n in top]


# ---------------------------------------------------------------------------
# Lưu bài học vào ChromaDB (tag core_lesson)
# ---------------------------------------------------------------------------
def _persist_lessons(lessons: list[str], memory=None) -> int:
    """Lưu mỗi bài học thành 1 MemoryRecord (tag core_lesson) vào system_rules."""
    if not lessons:
        return 0
    mem = memory
    if mem is None:
        try:
            from core.memory import MemoryStore
            mem = MemoryStore()
        except Exception as exc:  # noqa: BLE001 — thiếu chromadb -> không lưu, không sập
            logger.warning("Không mở được MemoryStore (%s) -> bỏ lưu.", exc)
            return 0
    try:
        from core.memory import CollectionName
        from core.schemas import MemoryRecord
    except Exception as exc:  # noqa: BLE001
        logger.warning("Thiếu schema/memory (%s) -> bỏ lưu.", exc)
        return 0

    stamp = datetime.now(timezone.utc).date().isoformat()
    saved = 0
    for lesson in lessons:
        try:
            rec = MemoryRecord(role="feedback", text=lesson,
                               tags=[CORE_LESSON_TAG, f"date:{stamp}"])
            mem.add_memory(rec, CollectionName.SYSTEM_RULES)
            saved += 1
        except Exception as exc:  # noqa: BLE001 — lưu 1 bài lỗi không chặn cả mẻ
            logger.warning("Lưu core_lesson lỗi: %s", exc)
    return saved


# ---------------------------------------------------------------------------
# API chính
# ---------------------------------------------------------------------------
def analyze_daily_logs(
    log_path: str | Path | None = None,
    hours: int = 24,
    *,
    raw_text: str | None = None,
    engine=None,
    memory=None,
    persist: bool = True,
    max_lines: int = _MAX_LOG_LINES,
) -> dict:
    """
    Đọc log 24h -> đúc 'Bài học rút kinh nghiệm' (LocalCPUEngine) -> lưu ChromaDB
    với tag core_lesson. Trả dict JSON-ready, KHÔNG ném exception.

    Args:
        log_path: file log (mặc định data/logs/aura.log).
        hours: cửa sổ thời gian (mặc định 24).
        raw_text: nạp thẳng nội dung log (test/đặc biệt), bỏ qua đọc file.
        engine/memory: tiêm để test; mặc định tự dựng LocalCPUEngine/MemoryStore.
        persist: có lưu vào ChromaDB không.

    Returns:
        {ok, source, analyzed_chars, lessons, saved, tag}
    """
    try:
        if raw_text is not None:
            text, source = raw_text, "raw_text"
        else:
            path = Path(log_path) if log_path else _DEFAULT_LOG_PATH
            text = _read_recent_logs(path, hours, max_lines)
            source = str(path)

        if not text.strip():
            return {"ok": False, "source": source, "reason": "Không có log đáng học trong 24h.",
                    "lessons": [], "saved": 0, "tag": CORE_LESSON_TAG}

        lessons = _summarize_lessons(text, engine=engine)
        saved = _persist_lessons(lessons, memory=memory) if persist else 0
        return {
            "ok": True, "source": source, "analyzed_chars": len(text),
            "lessons": lessons, "saved": saved, "tag": CORE_LESSON_TAG,
        }
    except Exception as exc:  # noqa: BLE001 — vành đai cuối: phản tỉnh hỏng không được sập
        logger.exception("analyze_daily_logs lỗi.")
        return {"ok": False, "reason": f"Lỗi phản tỉnh: {exc}", "lessons": [], "saved": 0,
                "tag": CORE_LESSON_TAG}


def recall_core_lessons(query: str, k: int = 3, memory=None) -> list[str]:
    """
    Truy vấn các bài học cốt lõi liên quan tới `query` (lọc theo tag core_lesson).
    Dùng cho Orchestrator để tự điều chỉnh hành vi trước khi thực thi kỹ năng.
    """
    mem = memory
    if mem is None:
        try:
            from core.memory import MemoryStore
            mem = MemoryStore()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Recall core_lesson: không mở được MemoryStore: %s", exc)
            return []
    try:
        from core.memory import CollectionName
        recs = mem.search_memory(query, CollectionName.SYSTEM_RULES, k=k)
        return [r.text for r in recs if CORE_LESSON_TAG in (getattr(r, "tags", None) or [])]
    except Exception as exc:  # noqa: BLE001 — recall lỗi không được làm sập luồng
        logger.warning("Recall core_lesson lỗi: %s", exc)
        return []


__all__ = [
    "analyze_daily_logs",
    "recall_core_lessons",
    "configure_file_logging",
    "CORE_LESSON_TAG",
]
