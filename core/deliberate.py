"""
core/deliberate.py
==================
Tầng TƯ DUY của AURA — biến "trả lời bộc phát" thành "nghĩ rồi tự kiểm".

Với câu HỎI KHÓ (phân tích/lập kế hoạch/coding), thay vì bắn 1 câu trả lời ngay,
AURA chạy vòng:
    LẬP KẾ HOẠCH (các bước cần xét) → NHÁP (suy nghĩ từng bước) → TỰ PHẢN BIỆN
    (tìm chỗ sai/thiếu) → VIẾT LẠI (sửa theo góp ý).
Nhờ vậy CÙNG một model nhỏ (gemma4) cho ra câu trả lời chắc hơn rõ rệt — không cần
đổi trọng số, chỉ cần "scaffolding" tư duy.

NHẸ CPU: chỉ dùng cho tác vụ khó; số vòng tự-phản-biện giới hạn (mặc định 1); tự DỪNG
sớm khi bản nháp đã ổn ("OK"). LLM nạp qua một hàm `complete_fn(prompt, system)->str`
tiêm từ ngoài (Orchestrator bọc router) -> module này thuần, test offline được.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

logger = logging.getLogger("aura.deliberate")

# complete_fn: nhận (prompt, system_prompt) trả về text. Lỗi nên trả "" (không ném).
CompleteFn = Callable[[str, str], str]

_OK_MARKERS = ("ok", "không có gì", "khong co gi", "hoàn hảo", "đã ổn", "da on", "không cần sửa")


def _safe(complete_fn: CompleteFn, prompt: str, system: str) -> str:
    try:
        out = complete_fn(prompt, system)
        return out.strip() if isinstance(out, str) else ""
    except Exception as exc:  # noqa: BLE001 — một bước tư duy hỏng không được làm sập
        logger.warning("deliberate: complete_fn lỗi: %s", exc)
        return ""


def _looks_ok(critique: str) -> bool:
    c = (critique or "").strip().lower()
    if not c:
        return True
    # Phản biện ngắn + chứa dấu hiệu "ổn" -> coi như không cần sửa.
    return len(c) < 40 and any(m in c for m in _OK_MARKERS)


def deliberate(
    question: str,
    complete_fn: CompleteFn,
    *,
    system_prompt: str = "",
    max_critiques: int = 1,
    plan: bool = True,
) -> dict:
    """
    Chạy vòng tư duy cho một câu hỏi khó. Trả dict JSON-ready (KHÔNG ném exception):
        {answer, plan, drafts:[...], critiques:[...], passes:int}

    - max_critiques: số vòng tự-phản-biện (0 = chỉ nháp có kế hoạch).
    - plan: có bước lập kế hoạch trước không.
    """
    q = (question or "").strip()
    if not q:
        return {"answer": "", "plan": "", "drafts": [], "critiques": [], "passes": 0}

    sys_p = system_prompt or "Bạn là AURA — trợ lý suy luận cẩn thận, trả lời tiếng Việt."

    # 1) LẬP KẾ HOẠCH
    plan_text = ""
    if plan:
        plan_text = _safe(
            complete_fn,
            f"Câu hỏi: {q}\n\nLiệt kê 2-4 BƯỚC/khía cạnh cần cân nhắc để trả lời tốt. "
            "Gạch đầu dòng, ngắn gọn, KHÔNG trả lời vội.",
            sys_p,
        )

    # 2) NHÁP (suy nghĩ từng bước)
    draft_prompt = f"Câu hỏi: {q}\n"
    if plan_text:
        draft_prompt += f"\nCác bước cần xét:\n{plan_text}\n"
    draft_prompt += "\nSuy nghĩ từng bước, rồi đưa ra CÂU TRẢ LỜI rõ ràng, đầy đủ."
    answer = _safe(complete_fn, draft_prompt, sys_p) or q  # fallback cực đoan: vọng lại câu hỏi
    drafts = [answer]
    critiques: list[str] = []
    passes = 0

    # 3) TỰ PHẢN BIỆN → VIẾT LẠI (lặp giới hạn, dừng sớm khi ổn)
    for _ in range(max(0, max_critiques)):
        critique = _safe(
            complete_fn,
            f"Câu hỏi: {q}\n\nBản trả lời nháp:\n{answer}\n\n"
            "Đóng vai người phản biện khó tính: chỉ ra điểm SAI / THIẾU / chưa chặt chẽ. "
            "Nếu đã tốt, chỉ ghi 'OK'.",
            sys_p,
        )
        critiques.append(critique)
        if _looks_ok(critique):
            break
        revised = _safe(
            complete_fn,
            f"Câu hỏi: {q}\n\nBản nháp:\n{answer}\n\nGóp ý phản biện:\n{critique}\n\n"
            "Viết lại CÂU TRẢ LỜI hoàn chỉnh, đã khắc phục các góp ý trên.",
            sys_p,
        )
        if revised:
            answer = revised
            drafts.append(revised)
        passes += 1

    return {"answer": answer, "plan": plan_text, "drafts": drafts,
            "critiques": critiques, "passes": passes}


__all__ = ["deliberate", "CompleteFn"]
