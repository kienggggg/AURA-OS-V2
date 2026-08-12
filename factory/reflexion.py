"""
factory/reflexion.py
=====================
REFLEXION cho xưởng — AURA tự đúc kết lỗi thành BÀI HỌC và cất lại, để lần sau
KHÔNG lặp lại. (Ý từ Reflexion/Reflexion-memory trong đợt tech-scout 2026-07-11.)

Khác trí nhớ chat (core/memory.py remember_rule) — xưởng chạy tách daemon nên
dùng sổ RIÊNG data/factory/lessons.jsonl (append, không dep chromadb). Mỗi bài
học gắn với product_line của tool.

Vòng: worker gọi note_outcome() khi job needs_review -> LLM (fast, rẻ) đúc 1 bài
học từ QC fail -> lưu (dedup). Tool sinh nội dung gọi lessons_for() nhồi vào
system prompt. Lỗi gì trong reflexion cũng KHÔNG được làm sập job.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from core.config import settings

logger = logging.getLogger("aura.factory.reflexion")

_PATH = settings.factory_dir / "lessons.jsonl"
_MAX_PER_LINE = 6          # số bài học tối đa nhồi vào prompt / dùng để dedup


def _load() -> list[dict]:
    if not _PATH.exists():
        return []
    out: list[dict] = []
    for line in _PATH.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def lessons_for(product_line: str, k: int = _MAX_PER_LINE) -> list[str]:
    """Các bài học GẦN NHẤT của product_line (mới -> cũ). Rỗng nếu chưa có."""
    seen = [r for r in _load() if r.get("line") == product_line]
    return [str(r.get("lesson")) for r in reversed(seen)][:k]


def lessons_prompt(product_line: str) -> str:
    """Khối text nhồi vào system prompt (rỗng nếu chưa có bài học nào)."""
    ls = lessons_for(product_line)
    if not ls:
        return ""
    body = "\n".join(f"- {x}" for x in ls)
    return ("\n\nBÀI HỌC TỪ NHỮNG LẦN TRƯỚC (BẮT BUỘC tránh lặp lại các lỗi này):\n"
            + body)


def _distill(product_line: str, tool: str, report_checks: list[dict],
             error: str) -> str | None:
    """LLM đúc 1 bài học NGẮN, hành động được từ các mục QC trượt. None nếu bỏ."""
    fails = [f"{c.get('name')}: {c.get('note')}" for c in report_checks
             if not c.get("ok")]
    signal = "; ".join(fails) or (error or "").strip()
    if not signal:
        return None
    try:
        from core.llm import CloudEngine
        res = CloudEngine().complete(
            [{"role": "user", "content":
              f"Tool '{tool}' vừa trượt kiểm định. Lỗi: {signal}\n\n"
              "Viết ĐÚNG 1 câu bài học tiếng Việt NGẮN, hành động được, dạng lời "
              "dặn cho lần sau (vd 'giữ thoại <12 từ để không tràn bóng'). CHỈ 1 "
              "câu, không giải thích."}],
            system_prompt="Bạn đúc kết lỗi thành bài học ngắn gọn, cụ thể.",
            temperature=0.3, max_tokens=120, tier="fast",
        )
        if res.get("ok"):
            lesson = str(res["text"]).strip().strip('"').split("\n")[0]
            return lesson[:200] or None
    except Exception as exc:  # noqa: BLE001 — reflexion hỏng không giết job
        logger.warning("Reflexion distill lỗi: %s", exc)
    return None


def _signature(product_line: str, report_checks: list[dict], error: str) -> str:
    """Chữ ký LOẠI lỗi = tên các mục QC trượt (sorted) — để dedup theo loại lỗi,
    không theo câu chữ bài học (LLM diễn đạt mỗi lần một khác)."""
    fails = sorted(str(c.get("name")) for c in report_checks if not c.get("ok"))
    return f"{product_line}|" + (";".join(fails) or (error or "").strip()[:60])


def note_outcome(product_line: str, tool: str, report_checks: list[dict],
                 error: str = "") -> None:
    """Gọi khi job needs_review: đúc + lưu bài học. Dedup theo CHỮ KÝ LỖI (cùng
    loại lỗi thì không học lại — và né gọi LLM thừa)."""
    try:
        sig = _signature(product_line, report_checks, error)
        if any(r.get("sig") == sig for r in _load() if r.get("line") == product_line):
            return          # đã học loại lỗi này rồi
        lesson = _distill(product_line, tool, report_checks, error)
        if not lesson:
            return
        _PATH.parent.mkdir(parents=True, exist_ok=True)
        with _PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": time.time(), "line": product_line,
                                "tool": tool, "sig": sig, "lesson": lesson},
                               ensure_ascii=False) + "\n")
        logger.info("Reflexion [%s] học được: %s", product_line, lesson)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Reflexion note_outcome lỗi (bỏ qua): %s", exc)


__all__ = ["lessons_for", "lessons_prompt", "note_outcome"]
