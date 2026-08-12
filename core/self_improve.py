"""
core/self_improve.py
====================
Cầu Reflection → Evolution: AURA tự PHÁT HIỆN mình thiếu kỹ năng (từ log thất bại),
tự ĐỀ XUẤT viết tool mới, rồi (sau khi Sếp DUYỆT) giao cho EvolutionEngine tự viết —
khép kín vòng "biết đau → biết mình thiếu gì → tự bù đắp".

Nguyên tắc an toàn (khác với 'ưu tiên lệnh vô hại'):
  Tự viết & nạp CODE MỚI là việc CÓ rủi ro -> LUÔN cần Sếp duyệt (HITL), và còn phải
  qua chuỗi cổng sẵn có của EvolutionEngine: CodeGate (AST/an ninh) -> Sandbox ephemeral
  -> remediation tự sửa -> người đọc code -> hot-load. Đây KHÔNG phải auto-run vô hại.

Thuần stdlib cho phần phát hiện/đề xuất (test offline). EvolutionEngine nạp TRỄ.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger("aura.self_improve")

# Các "dấu vết" trong log cho thấy AURA thiếu một năng lực/kỹ năng.
_GAP_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"Skill '([^']+)' chưa được khám phá", "missing_skill"),
    (r"Tool '([^']+)' chưa được đăng ký", "missing_tool"),
    (r"Công cụ '([^']+)' chưa được lắp", "missing_tool"),
    (r"không có đàn anh nào cho kỹ năng '([^']+)'", "missing_senior"),
    (r"web\.scrape.*cần web_agent|cần web_agent", "needs_browser"),
)


@dataclass
class SkillProposal:
    """Một đề xuất 'AURA nên có kỹ năng X'."""

    name: str
    kind: str
    count: int
    spec: str
    evidence: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Phát hiện khoảng trống năng lực từ log
# ---------------------------------------------------------------------------
def detect_capability_gaps(log_text: str) -> dict[str, dict]:
    """
    Quét log, gom các dấu hiệu 'thiếu kỹ năng' theo tên. Trả {name: {kind, count, evidence}}.
    """
    gaps: dict[str, dict] = {}
    for line in (log_text or "").splitlines():
        for pattern, kind in _GAP_PATTERNS:
            m = re.search(pattern, line)
            if not m:
                continue
            name = (m.group(1) if m.groups() else kind).strip()
            rec = gaps.setdefault(name, {"kind": kind, "count": 0, "evidence": []})
            rec["count"] += 1
            if len(rec["evidence"]) < 3:
                rec["evidence"].append(line.strip()[:200])
            break
    return gaps


def _build_spec(name: str, kind: str) -> str:
    """Dựng đặc tả ngắn cho CoderAgent từ tên kỹ năng còn thiếu."""
    base = (
        f"Viết một tool AURA tên gợi ý '{name}'. "
        "Tuân thủ CONTEXT.md: hàm entrypoint bắt đầu bằng 'tool_', TRẢ VỀ ToolResult "
        "(import từ core.schemas), bọc toàn bộ trong try/except, KHÔNG dùng os.system/"
        "subprocess/eval/exec, validate input. "
    )
    hint = {
        "missing_skill": "Skill này từng được gọi nhưng chưa tồn tại — hãy hiện thực hoá đúng tên.",
        "missing_tool": "Tool này được dispatch nhưng chưa đăng ký — hãy viết bản hoàn chỉnh.",
        "missing_senior": f"Cần một năng lực '{name}' mà chưa có 'đàn anh' xử lý.",
        "needs_browser": "Cần render JS/vượt anti-bot — cân nhắc dùng web.agent thay vì cào tĩnh.",
    }.get(kind, "")
    return base + hint


def propose(log_text: str, min_occurrences: int = 2) -> list[SkillProposal]:
    """
    Biến các khoảng trống lặp lại (>= min_occurrences) thành đề xuất viết kỹ năng.
    Ngưỡng giúp tránh đề xuất bừa từ một lỗi ngẫu nhiên (chỉ học từ lỗi LẶP LẠI).
    """
    gaps = detect_capability_gaps(log_text)
    proposals: list[SkillProposal] = []
    for name, rec in sorted(gaps.items(), key=lambda kv: kv[1]["count"], reverse=True):
        if rec["count"] < min_occurrences:
            continue
        proposals.append(SkillProposal(
            name=name, kind=rec["kind"], count=rec["count"],
            spec=_build_spec(name, rec["kind"]), evidence=rec["evidence"],
        ))
    return proposals


# ---------------------------------------------------------------------------
# Cổng phê duyệt đề xuất (mặc định: bắn UI + CHẶN — chờ Sếp)
# ---------------------------------------------------------------------------
def _default_proposal_gate(proposal: "SkillProposal", event_queue=None) -> bool:
    """
    Mặc định: thông báo đề xuất ra UI rồi CHẶN (không tự ý viết code khi chưa có Sếp).
    Phiên bản tương tác sẽ thay bằng cổng chờ Sếp bấm 'duyệt'.
    """
    msg = (f"🧠 AURA tự nhận thấy THIẾU kỹ năng '{proposal.name}' "
           f"(gặp {proposal.count} lần). Sếp cho phép em tự viết tool này không? "
           f"(sẽ qua kiểm AST + sandbox + Sếp đọc code trước khi nạp)")
    if event_queue is not None:
        try:
            event_queue.put_nowait({"type": "proactive", "text": msg,
                                    "proposal": proposal.name})
        except Exception as exc:  # noqa: BLE001
            logger.warning("Không bắn được đề xuất self-improve: %s", exc)
    logger.info("SELF-IMPROVE đề xuất '%s' — mặc định CHẶN chờ Sếp.", proposal.name)
    return False


# ---------------------------------------------------------------------------
# Khép vòng: phát hiện -> đề xuất -> (Sếp duyệt) -> EvolutionEngine tự viết
# ---------------------------------------------------------------------------
def run_self_improvement(
    log_text: str | None = None,
    *,
    registry=None,
    router=None,
    engine=None,
    approve_fn=None,
    event_queue=None,
    min_occurrences: int = 2,
    max_new: int = 1,
    dry_run: bool = False,
) -> dict:
    """
    Khép kín vòng tự hoàn thiện. Trả dict JSON-ready (KHÔNG ném exception).

    - approve_fn(proposal) -> bool: cổng duyệt; mặc định bắn UI + CHẶN (chờ Sếp).
    - engine: EvolutionEngine (tiêm để test); mặc định tự dựng từ router + registry.
    - dry_run: chỉ đề xuất, KHÔNG gọi evolve (an toàn để xem trước).
    """
    try:
        if log_text is None:
            try:
                from core.reflection import _read_recent_logs, _DEFAULT_LOG_PATH
                log_text = _read_recent_logs(_DEFAULT_LOG_PATH, hours=24, max_lines=800)
            except Exception as exc:  # noqa: BLE001
                logger.info("Không đọc được log (%s).", exc)
                log_text = ""

        proposals = propose(log_text or "", min_occurrences=min_occurrences)
        report: dict = {"ok": True, "proposals": [p.name for p in proposals],
                        "attempted": [], "results": [], "dry_run": dry_run}
        if not proposals:
            report["ok"] = False
            report["reason"] = "Chưa phát hiện khoảng trống năng lực lặp lại."
            return report

        gate = approve_fn or (lambda pr: _default_proposal_gate(pr, event_queue))

        for proposal in proposals[: max(0, max_new)]:
            try:
                approved = bool(gate(proposal))
            except Exception as exc:  # noqa: BLE001 — cổng duyệt nổ -> coi như CHẶN
                logger.warning("approve_fn lỗi (CHẶN): %s", exc)
                approved = False
            if not approved:
                report["results"].append({"name": proposal.name, "status": "chờ Sếp duyệt"})
                continue
            report["attempted"].append(proposal.name)
            if dry_run:
                report["results"].append({"name": proposal.name, "status": "dry_run (không viết)"})
                continue

            eng = engine or _build_engine(router, registry)
            if eng is None:
                report["results"].append({"name": proposal.name,
                                          "status": "thiếu EvolutionEngine/router/registry"})
                continue
            try:
                log = eng.evolve(proposal.spec, tool_name_hint=proposal.name)
                report["results"].append({
                    "name": proposal.name,
                    "status": "thành công" if getattr(log, "success", False) else "thất bại",
                    "registered_as": getattr(log, "tool_registered", None),
                    "aborted_reason": getattr(log, "aborted_reason", None),
                })
            except Exception as exc:  # noqa: BLE001 — evolve nổ không được làm sập
                logger.exception("EvolutionEngine.evolve lỗi.")
                report["results"].append({"name": proposal.name, "status": f"lỗi: {exc}"})
        return report
    except Exception as exc:  # noqa: BLE001 — vành đai cuối
        logger.exception("run_self_improvement lỗi.")
        return {"ok": False, "reason": f"Lỗi self-improve: {exc}", "proposals": [], "results": []}


def _build_engine(router, registry):
    """Dựng EvolutionEngine nếu đủ router + registry (nạp TRỄ). None nếu không đủ."""
    if router is None or registry is None:
        return None
    try:
        from evolution.engine import EvolutionEngine
        return EvolutionEngine(router=router, registry=registry)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Không dựng được EvolutionEngine: %s", exc)
        return None


__all__ = [
    "detect_capability_gaps",
    "propose",
    "run_self_improvement",
    "SkillProposal",
]
