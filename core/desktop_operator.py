"""
core/desktop_operator.py
========================
NẤC 1 — VÒNG LẶP THAO TÁC "như người thật" (Computer Use, bản an toàn).

Đây là mảnh còn thiếu: *nhìn màn → nghĩ bước kế → làm → nhìn lại → lặp*. Khác với
desktop_autopilot (chạy danh sách bước CỨNG soạn sẵn), cái này để bộ não NHÌN màn
hình mỗi bước rồi tự quyết cú tiếp theo, có phản hồi.

AN TOÀN LÀ MẶC ĐỊNH:
- `live=False` (DRY-RUN) là mặc định: nhìn màn thật + lập kế hoạch thật, nhưng
  KHÔNG chạm chuột/phím. Chạy thử = xem AURA ĐỊNH làm gì, không rủi ro.
- Mỗi action đều qua `autopilot.run_single_action` -> validate đầy đủ: chặn cửa sổ
  ngân hàng/OTP, chặn external_submit (KHÔNG tự đăng/gửi/mua), chặn gõ chuỗi bí mật.
- Cửa sổ nhạy cảm -> dừng NGAY, không chụp, không gửi ảnh lên cloud.
- Trần số bước (mặc định 8). PyAutoGUI FAILSAFE: rê chuột vào góc = ngắt vật lý.
- Chỉ cho các action ÍT RỦI RO; tuyệt nhiên không có "đăng/gửi/nộp/mua/xóa".

CHẠY THỬ (an toàn, không chạm chuột):
    python -m core.desktop_operator --goal "mở trình duyệt tìm 'hatsune miku'"
THẬT (Sếp phải NGỒI CANH — chỉ khi đã tin):
    python -m core.desktop_operator --goal "..." --live
"""

from __future__ import annotations

import argparse
import io
import json
import logging
import sys
import time
from typing import Any, Protocol

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

logger = logging.getLogger("aura.desktop_operator")

# Các action ÍT RỦI RO nấc 1 cho phép. "done" là tín hiệu planner báo xong.
# KHÔNG có action đăng/gửi/mua — external_submit vẫn bị autopilot khoá riêng.
_ALLOWED_KINDS = frozenset({
    "observe", "click_text", "click", "type_text", "press", "hotkey",
    "scroll", "wait", "done",
})

_PLANNER_SYSTEM = (
    "Bạn là bộ điều khiển máy tính của AURA. Mỗi lượt bạn được ĐƯA ẢNH màn hình "
    "hiện tại + mục tiêu của Chủ. Trả về ĐÚNG MỘT bước kế tiếp dạng JSON:\n"
    '{"thought": "lý do ngắn", "expect": "màn hình sẽ đổi thế nào sau bước này", '
    '"done": false, "action": {"kind": "...", ...}}\n'
    "Các kind hợp lệ: click_text{target}, click{x,y,label}, type_text{text}, "
    "press{key}, hotkey{keys:[...]}, scroll{amount}, wait{seconds}, observe{}.\n"
    "QUAN TRỌNG — TỰ KIỂM: nếu phần gợi ý báo bước trước CHƯA đạt kỳ vọng, ĐỪNG "
    "lặp lại y hệt hành động cũ; thử cách khác (vd click chỗ khác, cuộn, chờ). "
    "Nếu đã đạt mục tiêu, trả {\"done\": true, \"action\": {\"kind\":\"done\"}}.\n"
    "TUYỆT ĐỐI KHÔNG bấm Đăng/Gửi/Nộp/Mua/Xóa hay nhập mật khẩu/OTP. "
    "Ưu tiên click_text (bám chữ thấy trên màn) hơn click tọa độ. "
    "Nếu app (Chrome/CapCut/Facebook...) có giao diện tiếng Anh thì cứ bám chữ "
    "tiếng Anh — máy đọc chữ Anh chính xác hơn tiếng Việt có dấu. Chỉ trả JSON."
)

_REFLEXION_LINE = "desktop_operator"
_MAX_REPEAT = 2  # lặp lại cùng một hành động quá số này -> coi như kẹt, dừng


def _action_sig(action: dict[str, Any]) -> str:
    a = action or {}
    key = a.get("target") or a.get("text") or a.get("key") or a.get("keys") or ""
    return f"{a.get('kind','')}|{key}"


def _load_lessons() -> str:
    try:
        from factory.reflexion import lessons_prompt
        return lessons_prompt(_REFLEXION_LINE)
    except Exception:  # noqa: BLE001 — không có reflexion vẫn chạy
        return ""


def _record_failure(status: str, goal: str, detail: str) -> None:
    """Ghi bài học khi thao tác hỏng/kẹt -> lần sau tránh (Reflexion)."""
    try:
        from factory.reflexion import note_outcome
        note_outcome(
            _REFLEXION_LINE, "desktop_operator",
            [{"name": status, "ok": False, "note": f"{goal[:60]}: {detail}"[:180]}],
            error=str(detail)[:180],
        )
    except Exception:  # noqa: BLE001
        pass


class Planner(Protocol):
    def next_step(
        self, goal: str, observation: dict[str, Any],
        screenshot_png: bytes | None, history: list[dict[str, Any]],
    ) -> dict[str, Any]: ...


class GeminiVisionPlanner:
    """Bộ não CÓ MẮT: gửi ảnh màn hình + mục tiêu cho Gemini, nhận bước kế tiếp."""

    def __init__(self, model: str | None = None) -> None:
        from brains.cloud_gemini import GeminiBackend
        self._backend = GeminiBackend(model=model)

    def next_step(self, goal, observation, screenshot_png, history):
        hist = "\n".join(
            f"- bước {i+1}: {h.get('thought','')} -> {h.get('action',{})}"
            for i, h in enumerate(history[-6:])
        ) or "(chưa có)"
        prompt = (
            f"MỤC TIÊU: {goal}\n\n"
            f"Cửa sổ: {observation.get('window_title')}\n"
            f"{observation.get('hint') or ''}\n\n"
            f"Các bước đã làm:\n{hist}\n\n"
            "Nhìn ẢNH màn hình hiện tại và trả JSON bước kế tiếp (chỉ JSON)."
        )
        images = [screenshot_png] if screenshot_png else None
        raw = self._backend.chat(
            [{"role": "user", "content": prompt}],
            system_prompt=_PLANNER_SYSTEM,
            temperature=0.2, max_tokens=600, images=images,
        )
        return _parse_step(raw)


def _parse_step(raw: str) -> dict[str, Any]:
    """Bóc JSON từ câu trả lời (kể cả khi bọc trong ```)."""
    text = (raw or "").strip()
    if "```" in text:
        text = text.split("```")[1] if text.count("```") >= 2 else text
        text = text.removeprefix("json").strip()
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        text = text[start:end + 1]
    try:
        data = json.loads(text)
    except Exception:  # noqa: BLE001
        return {"thought": "không đọc được kế hoạch", "done": True,
                "action": {"kind": "done"}, "parse_error": raw[:200]}
    action = data.get("action") or {}
    if data.get("done"):
        action = {"kind": "done"}
    return {"thought": str(data.get("thought") or ""),
            "expect": str(data.get("expect") or ""),
            "done": bool(data.get("done")), "action": action}


def describe_screen_smart() -> str:
    """Mô tả màn hình SẠCH bằng Gemini vision (đọc thẳng ẢNH -> hết méo dấu tiếng
    Việt). Lùi về OCR local khi offline/không key. Tôn trọng đúng rào an toàn:
    cửa sổ nhạy cảm/lạ thì KHÔNG chụp, KHÔNG gửi cloud."""
    from core.desktop_autopilot import get_runtime_autopilot, describe_current_screen

    try:
        ap = get_runtime_autopilot()
        if not ap.status().get("owner_enabled"):
            return ("👁️ Mắt màn hình chưa được Chủ bật. Mở tab 'Tự thao tác' trên "
                    "dashboard và bấm 'Bật tự thao tác' một lần.")
        obs = ap.observe(include_ocr=False)
        category = str(obs.get("window_category") or "unknown")
        title = str(obs.get("window_title") or "không xác định")
        if category == "blocked":
            return ("🔒 Cửa sổ hiện tại thuộc vùng nhạy cảm (ngân hàng/OTP/thanh "
                    "toán). AURA không chụp, không gửi lên đâu cả.")
        if category != "allowed":
            return (f"⚠️ AURA thấy cửa sổ '{title}' nhưng chưa nằm trong danh sách "
                    "được phép, nên không đọc nội dung.")
        img = ap._driver().screenshot()
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        from brains.cloud_gemini import GeminiBackend
        desc = GeminiBackend().chat(
            [{"role": "user", "content":
                "Đây là ảnh màn hình laptop. Mô tả NGẮN GỌN bằng tiếng Việt: đang "
                "mở ứng dụng/trang gì, nội dung chính là gì. 2-4 câu, không bịa."}],
            images=[buf.getvalue()], temperature=0.2, max_tokens=400,
        )
        desc = (desc or "").strip()
        if desc:
            return f"👁️ Cửa sổ: {title}\n{desc}"
    except Exception as exc:  # noqa: BLE001 — vision hỏng thì lùi về OCR local
        logger.warning("Gemini vision đọc màn lỗi, lùi về OCR local: %s", exc)
    return describe_current_screen()


class DesktopOperator:
    def __init__(self, autopilot=None, planner: Planner | None = None) -> None:
        if autopilot is None:
            from core.desktop_autopilot import get_runtime_autopilot
            autopilot = get_runtime_autopilot()
        self.autopilot = autopilot
        self._planner = planner  # None -> nạp Gemini khi cần (khỏi tốn lúc test)

    def _planner_or_default(self) -> Planner:
        if self._planner is None:
            self._planner = GeminiVisionPlanner()
        return self._planner

    def _screenshot_png(self) -> bytes | None:
        try:
            img = self.autopilot._driver().screenshot()
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            return buf.getvalue()
        except Exception as exc:  # noqa: BLE001 — không có ảnh vẫn chạy được (text-only)
            logger.warning("Chụp màn cho planner lỗi: %s", exc)
            return None

    def run_goal(self, goal: str, *, max_steps: int = 8, live: bool = False) -> dict[str, Any]:
        """Chạy vòng lặp tới khi xong / hết bước / gặp rào an toàn.

        live=False (mặc định) = DRY-RUN: lập kế hoạch thật nhưng KHÔNG chạm chuột.
        """
        if not str(goal or "").strip():
            raise ValueError("Thiếu mục tiêu.")
        status = self.autopilot.status()
        if not status.get("owner_enabled"):
            return {"status": "not_enabled", "steps": [],
                    "message": "Chủ chưa bật tự thao tác trên dashboard."}

        planner = self._planner_or_default()
        history: list[dict[str, Any]] = []
        final = "max_steps"
        lessons = _load_lessons()      # bài học lần trước -> tránh lặp lỗi
        last_sig: str | None = None
        repeats = 0

        for step in range(1, max_steps + 1):
            # include_ocr=False: bộ não Gemini NHÌN THẲNG ẢNH màn hình, không cần
            # OCR cục bộ (EasyOCR nặng/có thể chưa cài). OCR chỉ cần khi THỰC THI
            # click_text ở chế độ live -> lúc đó autopilot tự lo, hỏng thì dừng sạch.
            try:
                obs = self.autopilot.observe(include_ocr=False)
            except Exception as exc:  # noqa: BLE001 — nhìn lỗi thì dừng, không đoán
                final = "observe_error"
                history.append({"step": step, "error": str(exc), "executed": False})
                break
            category = str(obs.get("window_category") or "unknown")
            if category == "blocked":
                final = "blocked_sensitive_window"
                history.append({"step": step, "thought": "cửa sổ nhạy cảm",
                                "action": {"kind": "abort"}, "executed": False})
                break
            if category != "allowed":
                # MÙ thì KHÔNG lập kế hoạch bừa. Cửa sổ 'unknown' = không đọc được
                # (không trong danh sách cho phép) -> dừng thật thà thay vì bịa 'done'.
                final = "cannot_see_window"
                history.append({
                    "step": step,
                    "thought": f"cửa sổ '{obs.get('window_title')}' không trong danh "
                               "sách được phép, AURA không đọc được -> dừng",
                    "action": {"kind": "abort"}, "executed": False})
                break

            # GỢI Ý KIỂM (verify-after-act): nhắc planner đối chiếu bước trước có
            # đạt kỳ vọng chưa, kèm bài học cũ. Đây là lõi nấc 3.
            hint_parts: list[str] = []
            if lessons:
                hint_parts.append(lessons)
            prev = next((h for h in reversed(history) if h.get("executed")), None)
            if prev and prev.get("expect"):
                hint_parts.append(
                    f"GỢI Ý KIỂM: bước trước đã làm {prev.get('action')} để đạt: "
                    f"'{prev.get('expect')}'. Nhìn màn hình HIỆN TẠI xem đã đạt chưa; "
                    "CHƯA thì thử cách khác, ĐỪNG lặp lại y hệt.")
            obs["hint"] = "\n".join(hint_parts)

            png = self._screenshot_png()
            try:
                plan = planner.next_step(goal, obs, png, history)
            except Exception as exc:  # noqa: BLE001
                final = "planner_error"
                history.append({"step": step, "error": str(exc), "executed": False})
                break

            action = plan.get("action") or {}
            kind = str(action.get("kind") or "")
            entry = {"step": step, "thought": plan.get("thought", ""),
                     "expect": plan.get("expect", ""),
                     "action": action, "window": obs.get("window_title"),
                     "executed": False, "live": live}

            if plan.get("done") or kind == "done":
                final = "done"
                history.append({**entry, "action": {"kind": "done"}})
                break
            if kind not in _ALLOWED_KINDS:
                final = "rejected_action"
                entry["rejected"] = f"kind '{kind}' không được phép ở nấc 1"
                history.append(entry)
                break

            # CHỐNG KẸT (nghiên cứu: agent gãy vì lặp mù bước hỏng). Lặp lại cùng
            # một hành động quá _MAX_REPEAT lần -> dừng thay vì đâm đầu tiếp.
            sig = _action_sig(action)
            repeats = repeats + 1 if sig == last_sig else 0
            last_sig = sig
            if repeats >= _MAX_REPEAT and kind not in ("observe", "wait"):
                final = "stuck"
                entry["stuck"] = (f"lặp lại '{sig}' {repeats + 1} lần mà màn hình "
                                  "không tiến triển -> dừng")
                history.append(entry)
                break

            if live:
                try:
                    self.autopilot.run_single_action(action, scope="local_ui")
                    entry["executed"] = True
                except Exception as exc:  # noqa: BLE001 — rào an toàn chặn -> dừng sạch
                    final = "safety_stop"
                    entry["safety_stop"] = str(exc)
                    history.append(entry)
                    break
                time.sleep(0.6)  # cho UI kịp phản hồi trước khi nhìn lại
            history.append(entry)

        # HỌC TỪ THẤT BẠI (Reflexion): kết thúc xấu -> ghi 1 bài học cho lần sau.
        if final in ("stuck", "safety_stop", "planner_error", "observe_error",
                     "rejected_action"):
            last = history[-1] if history else {}
            detail = (last.get("stuck") or last.get("safety_stop")
                      or last.get("rejected") or last.get("error") or final)
            _record_failure(final, goal, str(detail))

        return {"status": final, "goal": goal, "live": live,
                "steps": history, "step_count": len(history)}


def _norm_cmd(text: str) -> str:
    import unicodedata
    folded = unicodedata.normalize("NFKD", str(text or "").casefold()).replace("đ", "d")
    return " ".join("".join(c for c in folded if not unicodedata.combining(c)).split())


def parse_operator_command(text: str) -> dict[str, Any] | None:
    """Bóc lệnh thao tác từ câu chat. Cú pháp RÕ RÀNG để không kích nhầm:
        'thao tác: <việc>'       -> DRY-RUN (chỉ lập kế hoạch, không chạm chuột)
        'thao tác thật: <việc>'  -> LIVE (chạm chuột thật)
    Trả None nếu không phải lệnh thao tác."""
    raw = str(text or "").strip()
    head, sep, goal = raw.partition(":")
    if not sep:
        return None
    norm = _norm_cmd(head)
    if not (norm.startswith("thao tac") or norm.startswith("thaotac")
            or norm.startswith("dieu khien")):
        return None
    goal = goal.strip()
    if not goal:
        return None
    return {"goal": goal, "live": "that" in norm}


def format_report(report: dict[str, Any]) -> str:
    lines = [
        f"🎯 Mục tiêu: {report.get('goal')}",
        f"Chế độ: {'THẬT (có chạm chuột)' if report.get('live') else 'DRY-RUN (không chạm chuột)'}",
        f"Kết thúc: {report.get('status')}  ({report.get('step_count')} bước)",
        "",
    ]
    for h in report.get("steps", []):
        stopped = h.get("safety_stop") or h.get("rejected") or h.get("stuck")
        mark = "✅" if h.get("executed") else ("🛑" if stopped else "○")
        act = h.get("action", {})
        lines.append(f"{mark} B{h.get('step')}: {h.get('thought','')[:70]}")
        lines.append(f"     → {act}")
        for k in ("rejected", "safety_stop", "stuck", "error"):
            if h.get(k):
                lines.append(f"     ⚠️ {h[k]}")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="AURA nấc 1 — vòng lặp thao tác an toàn")
    ap.add_argument("--goal", required=True, help="Mục tiêu bằng tiếng Việt")
    ap.add_argument("--live", action="store_true",
                    help="THẬT sự chạm chuột/phím (mặc định: DRY-RUN không chạm)")
    ap.add_argument("--max-steps", type=int, default=8)
    args = ap.parse_args()

    if args.live:
        print("⚠️  CHẾ ĐỘ THẬT: AURA sẽ chạm chuột/phím. Rê chuột vào GÓC màn hình để ngắt.")
    report = DesktopOperator().run_goal(
        args.goal, max_steps=args.max_steps, live=args.live)
    print(format_report(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
