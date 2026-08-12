"""
core/vibe_diff.py
=================
VIBE DIFF — Human-in-the-loop chuẩn "ý định dễ hiểu" (theo tinh thần Google ADK 2.0).

Vấn đề bản cũ: khi cần Sếp duyệt, hệ in ra log kỹ thuật khó đọc, vd:
    Tool: manga.download, Params: {"source_url": "...", "chapter": 1, "title": "Pokemon"}

VIBE DIFF biến lời gọi tool (tên + tham số) thành MỘT câu ý định bằng tiếng Việt:
    🛡️ VIBE DIFF (YÊU CẦU PHÊ DUYỆT): Em định tải Chương 1 của truyện Pokemon từ
    đường link [...]. Sếp có đồng ý không?

Gồm 2 phần:
  1. `vibe_diff_translator(tool_name, parameters)` — bộ dịch ý định (thuần hàm, dễ test).
  2. `VibeDiffInterceptor` — cổng chặn (interceptor) cắm vào luồng trước khi chạy tool:
     dựng câu ý định, bắn ra Avatar UI qua event_queue, và CHẶN cho tới khi Sếp duyệt.

Triết lý an toàn (giống BudgetGuard của AgentBroker): mặc định CHẶN. Nếu chưa có cơ
chế nhận cái gật của Sếp (approve_fn), tool KHÔNG tự chạy.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

logger = logging.getLogger("aura.vibe_diff")

# Nhãn hiển thị cố định để UI/Sếp nhận ra ngay đây là yêu cầu phê duyệt.
VIBE_DIFF_PREFIX = "🛡️ VIBE DIFF (YÊU CẦU PHÊ DUYỆT)"

# Tool nội bộ chỉ tạo bản nháp / dữ liệu cục bộ. Auto Plan có thể chạy chúng mà
# không hỏi lại Chủ từng bước. Tuyệt đối không đưa upload, publish, gửi đơn, thanh
# toán hay thao tác hệ thống vào danh sách này.
AUTO_PLAN_LOCAL_TOOLS: frozenset[str] = frozenset({
    "knowledge.ingest",
    "manga.download", "manga.translate", "comic.create", "comic.translate",
    "novel.translate", "coloringbook.factory", "content.factory", "excel.factory",
    "explainer.video", "story.factory", "story.kit", "story.video", "story.comic",
    "video.factory", "video.shorts", "freelance.apply",
    "web.scrape", "web.agent", "tech.scout", "news.scout", "security.stride", "job.scout",
    "desktop.autopilot",
})

# Không bật Auto Plan thì vẫn ưu tiên lệnh vô hại qua assess_harm; mọi tool chưa
# phân loại tiếp tục bị chặn như cũ.
DEFAULT_AUTO_APPROVE: frozenset[str] = frozenset()


def auto_plan_approvals(enabled: bool) -> frozenset[str]:
    """Trả allow-list Auto Plan, tách riêng để dễ kiểm thử và kiểm toán."""
    return AUTO_PLAN_LOCAL_TOOLS if enabled else DEFAULT_AUTO_APPROVE

# Từ khoá nhận diện câu trả lời của Sếp (chỉ xét khi đang có tác vụ chờ duyệt).
_APPROVE_WORDS: tuple[str, ...] = (
    "duyệt", "duyet", "đồng ý", "dong y", "ok", "oke", "okay", "yes", "y",
    "có", "co", "ừ", "u", "ừm", "um", "chạy", "chay", "làm đi", "lam di",
    "tiến hành", "tien hanh", "approve", "đồng ý nhé", "cứ làm", "cu lam",
)
_REJECT_WORDS: tuple[str, ...] = (
    "không", "khong", "thôi", "thoi", "đừng", "dung", "hủy", "huy", "huỷ",
    "no", "cancel", "stop", "dừng", "khoan", "đợi đã", "doi da", "khỏi", "khoi",
)


# ---------------------------------------------------------------------------
# Bộ dịch ý định (thuần hàm)
# ---------------------------------------------------------------------------
def _fmt_chapter(chapter) -> str:
    """Hiển thị số chương gọn: 1 thay vì 1.0, giữ 10.5 khi là chương lẻ."""
    try:
        c = float(chapter)
    except (TypeError, ValueError):
        return str(chapter)
    return str(int(c)) if c.is_integer() else str(c)


def _pretty_params(parameters: dict) -> str:
    """Liệt kê tham số dạng dễ đọc cho tool chưa có mẫu câu riêng."""
    if not parameters:
        return "không có tham số"
    parts = []
    for key, value in parameters.items():
        text = str(value)
        if len(text) > 80:  # cắt bớt URL/chuỗi dài cho gọn câu
            text = text[:77] + "…"
        parts.append(f"{key} = {text}")
    return ", ".join(parts)


def vibe_diff_translator(tool_name: str, parameters: dict | None) -> str:
    """
    Dịch một lời gọi tool (tên + tham số) thành CÂU Ý ĐỊNH tiếng Việt dễ hiểu.

    Có mẫu câu riêng cho các skill cốt lõi; tool lạ dùng mẫu chung (liệt kê tham số).
    Trả về câu trần thuật (chưa kèm tiền tố VIBE DIFF / câu hỏi duyệt).
    """
    p = parameters or {}

    if tool_name == "manga.download":
        title = p.get("title", "(chưa rõ tên)")
        chapter = _fmt_chapter(p.get("chapter"))
        url = p.get("source_url")
        msg = f"Em định tải Chương {chapter} của truyện {title}"
        if url:
            msg += f" từ đường link {url}"
        return msg + "."

    if tool_name == "manga.translate":
        title = p.get("title", "(chưa rõ tên)")
        chapter = _fmt_chapter(p.get("chapter"))
        msg = f"Em định dịch Chương {chapter} của truyện {title} sang Tiếng Việt"
        if p.get("source_url"):
            msg += f" (tự tải trước từ {p['source_url']} nếu chưa có)"
        return msg + "."

    if tool_name == "web.scrape":
        url = p.get("url", "(chưa rõ URL)")
        return f"Em định đọc và cào nội dung từ trang {url}."

    if tool_name == "web.agent":
        url = p.get("url", "(chưa rõ URL)")
        return f"Em định mở trình duyệt thật (headless) để render & đọc trang {url}."

    if tool_name == "tech.scout":
        query = p.get("query", "(chưa rõ từ khoá)")
        return f"Em định đi trinh sát công nghệ/model mới với từ khoá '{query}'."

    if tool_name == "job.scout":
        kw = p.get("keywords") or "bộ từ khoá ưu tiên của Sếp"
        urls = p.get("urls")
        if isinstance(urls, (list, tuple)):
            where = f" trên {len(urls)} trang tuyển dụng"
        elif isinstance(urls, str) and urls:
            where = f" trên trang {urls}"
        else:
            where = " trên vài trang tuyển dụng mẫu"
        return f"Em định cào & chấm điểm tin tuyển dụng{where} theo từ khoá: {kw}."

    if tool_name in ("system.control", "system_control"):
        action = p.get("action")
        if action:
            tgt = str(p.get("target", ""))
            dst = str(p.get("dst", ""))
            verb = {
                "sysinfo": "xem thông tin hệ thống (ổ đĩa/RAM)",
                "list_dir": f"liệt kê thư mục {tgt}",
                "mkdir": f"tạo thư mục {tgt}",
                "move": f"di chuyển {tgt} → {dst}",
                "rename": f"đổi tên {tgt} → {dst}",
                "copy": f"sao chép {tgt} → {dst}",
                "delete": f"XOÁ {tgt} (đưa vào Thùng rác)",
                "open_app": f"mở ứng dụng {tgt}",
                "open_path": f"mở {tgt}",
                "open_url": f"mở đường link {tgt}",
            }.get(action, f"{action} {tgt}".strip())
            return f"Em định {verb}."
        cmd = p.get("command") or p.get("cmd") or _pretty_params(p)
        return f"Em định thao tác trên hệ thống: {cmd}."

    # Tool lạ / tự sinh: mẫu chung, vẫn dễ đọc hơn log JSON.
    return f"Em định chạy công cụ '{tool_name}' với {_pretty_params(p)}."


def build_vibe_diff_message(tool_name: str, parameters: dict | None) -> str:
    """Ghép câu ý định thành thông điệp phê duyệt hoàn chỉnh cho Sếp/UI."""
    summary = vibe_diff_translator(tool_name, parameters)
    return f"{VIBE_DIFF_PREFIX}: {summary} Sếp có đồng ý không?"


# ---------------------------------------------------------------------------
# Nhận diện câu trả lời duyệt / huỷ của Sếp
# ---------------------------------------------------------------------------
def _normalize(text: str) -> str:
    return (text or "").strip().lower()


def is_approval(text: str) -> bool:
    """True nếu câu của Sếp mang ý ĐỒNG Ý (chỉ nên xét khi đang chờ duyệt)."""
    t = _normalize(text)
    if not t:
        return False
    # Khớp nguyên câu ngắn hoặc chứa từ khoá duyệt mà KHÔNG chứa từ chối.
    if any(w in t for w in _REJECT_WORDS):
        return False
    return any(t == w or t.startswith(w + " ") or w in t for w in _APPROVE_WORDS)


def is_rejection(text: str) -> bool:
    """True nếu câu của Sếp mang ý TỪ CHỐI / huỷ tác vụ."""
    t = _normalize(text)
    if not t:
        return False
    return any(t == w or t.startswith(w + " ") or w in t for w in _REJECT_WORDS)


# ---------------------------------------------------------------------------
# Cổng chặn (Interceptor)
# ---------------------------------------------------------------------------
# Kiểu hàm duyệt có thể tiêm vào: (tool_name, parameters, message) -> bool.
ApproveFn = Callable[[str, dict, str], bool]


# ---------------------------------------------------------------------------
# Đánh giá mức HẠI của một lời gọi tool — để ƯU TIÊN lệnh Sếp khi vô hại.
# ---------------------------------------------------------------------------
# Tool chỉ-đọc (không đụng dữ liệu của Sếp) -> VÔ HẠI.
_READONLY_TOOLS: frozenset[str] = frozenset({
    "web.scrape", "web.agent", "tech.scout", "news.scout", "security.stride", "job.scout",
})
# Tool tạo file trong thư mục data (đảo ngược được bằng cách xoá) -> coi là VÔ HẠI.
_SAFE_CREATE_TOOLS: frozenset[str] = frozenset({"manga.download", "manga.translate"})
# system.control: hành động an toàn (đọc/mở/tạo/sao chép) vs phá huỷ (xoá/di chuyển/đổi tên).
_SYSCTL_SAFE_ACTIONS: frozenset[str] = frozenset({
    "sysinfo", "list_dir", "open_app", "open_path", "open_url", "mkdir", "copy",
})
_SYSCTL_RISKY_ACTIONS: frozenset[str] = frozenset({"delete", "move", "rename"})
# Dấu hiệu phá huỷ trong câu lệnh tự do (khi system.control chỉ nhận 'command').
_DESTRUCTIVE_WORDS: tuple[str, ...] = (
    "xoá", "xóa", "delete", "di chuyển", " move", "đổi tên", "rename", "format",
    "gỡ", "uninstall", "tắt máy", "shutdown", "khởi động lại", "restart", "kill",
)


def assess_harm(tool_name: str, parameters: dict | None) -> tuple[bool, str]:
    """
    Lượng định: lời gọi này có VÔ HẠI không? Trả (is_safe, lý do).

    Triết lý: ƯU TIÊN lệnh Sếp — vô hại thì làm ngay; CHỈ chặn khi có rủi ro tiêu
    cực (mất/đè dữ liệu, đụng hệ thống, không rõ). Nguyên tắc fail-safe: KHÔNG chắc
    -> coi là RỦI RO (cần Sếp duyệt).
    """
    p = parameters or {}
    if tool_name in _READONLY_TOOLS:
        return True, "chỉ đọc, không đụng dữ liệu"
    if tool_name in _SAFE_CREATE_TOOLS:
        return True, "tạo file trong data (đảo ngược được)"
    if tool_name in ("system.control", "system_control"):
        action = str(p.get("action", "")).strip().lower()
        if action:
            if action in _SYSCTL_RISKY_ACTIONS:
                return False, f"thao tác phá huỷ/khó đảo ngược: {action}"
            if action in _SYSCTL_SAFE_ACTIONS:
                return True, f"thao tác vô hại: {action}"
            return False, f"hành động chưa rõ mức rủi ro: {action}"
        cmd = str(p.get("command", "")).lower()
        if any(w in cmd for w in _DESTRUCTIVE_WORDS):
            return False, "câu lệnh có dấu hiệu phá huỷ"
        return False, "không xác định được mức rủi ro"
    return False, "tool chưa phân loại rủi ro"


class VibeDiffInterceptor:
    """
    Cổng chặn trước khi thực thi tool: dịch ý định -> bắn UI -> chờ Sếp duyệt.

    Cách dùng trong Orchestrator/Broker:
        gate = VibeDiffInterceptor(event_queue=event_queue)
        approved, message = gate.intercept(task.tool_name, task.arguments)
        if not approved:
            return message            # hiển thị cho Sếp, KHÔNG chạy tool

    - `auto_approve`: tập tool chỉ-đọc được tự duyệt (không hỏi Sếp).
    - `approve_fn`  : hàm quyết định duyệt. Mặc định = bắn UI + CHẶN (trả False),
                      đúng tinh thần "không tự ý chạy khi chưa có cái gật của Sếp".
                      Bản có UI tương tác/auto có thể tiêm hàm khác.
    """

    def __init__(
        self,
        event_queue=None,
        approve_fn: ApproveFn | None = None,
        auto_approve: frozenset[str] | None = None,
        obey_when_safe: bool = True,
        harm_assessor=None,
    ) -> None:
        self.event_queue = event_queue
        self.auto_approve = (
            auto_approve if auto_approve is not None else DEFAULT_AUTO_APPROVE
        )
        self._approve_fn = approve_fn or self._default_gate
        # ƯU TIÊN lệnh Sếp: nếu vô hại -> chạy ngay; chỉ rủi ro mới xin duyệt.
        # Đặt False để quay lại chế độ 'chặn TẤT CẢ' (paranoid).
        self.obey_when_safe = obey_when_safe
        self._harm_assessor = harm_assessor or assess_harm

    # ------------------------------------------------------------------ #
    def needs_approval(self, tool_name: str) -> bool:
        """Tool có cần Sếp duyệt không (không nằm trong danh sách tự duyệt)."""
        return tool_name not in self.auto_approve

    def translate(self, tool_name: str, parameters: dict | None) -> str:
        """Tiện ích: lấy câu ý định ngôn ngữ tự nhiên (không kèm hỏi duyệt)."""
        return vibe_diff_translator(tool_name, parameters)

    # ------------------------------------------------------------------ #
    def intercept(self, tool_name: str, parameters: dict | None) -> tuple[bool, str]:
        """
        Chặn một lời gọi tool. Trả (đã_duyệt, thông_điệp).

        - Tool tự duyệt        -> (True, "").
        - Cần duyệt + được gật  -> (True, "").
        - Cần duyệt + chưa gật  -> (False, "🛡️ VIBE DIFF ... Sếp có đồng ý không?").
        """
        params = parameters or {}
        if not self.needs_approval(tool_name):
            logger.info("VIBE DIFF: '%s' thuộc nhóm tự duyệt — chạy thẳng.", tool_name)
            return True, ""

        # ƯU TIÊN LỆNH SẾP: hành động VÔ HẠI -> chạy ngay, chỉ báo nhẹ (không hỏi).
        if self.obey_when_safe:
            safe, reason = self._harm_assessor(tool_name, params)
            if safe:
                logger.info("VIBE DIFF: '%s' vô hại (%s) -> ưu tiên lệnh Sếp, chạy ngay.",
                            tool_name, reason)
                self._emit_info(tool_name, params, reason)
                return True, ""

        message = build_vibe_diff_message(tool_name, params)
        self._emit_to_ui(tool_name, params, message)

        try:
            approved = bool(self._approve_fn(tool_name, params, message))
        except Exception as exc:  # noqa: BLE001 — cổng duyệt nổ thì coi như CHẶN
            logger.warning("approve_fn lỗi (mặc định CHẶN): %s", exc)
            approved = False

        if approved:
            logger.info("VIBE DIFF: Sếp đã duyệt '%s'.", tool_name)
            return True, ""
        return False, message

    # ------------------------------------------------------------------ #
    def _emit_info(self, tool_name: str, parameters: dict, reason: str) -> None:
        """Báo nhẹ ra UI rằng AURA đã TỰ làm một việc vô hại (không cần duyệt)."""
        if self.event_queue is None:
            return
        try:
            self.event_queue.put_nowait({
                "type": "action_notice",
                "text": f"⚙️ Em tự xử lý (vô hại): {self.translate(tool_name, parameters)}",
                "tool": tool_name, "reason": reason,
            })
        except Exception as exc:  # noqa: BLE001
            logger.warning("Không bắn được action_notice: %s", exc)

    # ------------------------------------------------------------------ #
    def _emit_to_ui(self, tool_name: str, parameters: dict, message: str) -> None:
        """
        Bắn yêu cầu phê duyệt ra Avatar UI qua event_queue (nếu có).

        Dùng type 'approval_request' kèm 'text' để UI nâng cấp có thể vẽ thẻ duyệt
        với nút Đồng ý/Huỷ; UI hiện tại bỏ qua type này nên KHÔNG bị nhân đôi bong
        bóng (câu hỏi đã được trả về làm response chính của lượt).
        """
        if self.event_queue is None:
            return
        event = {
            "type": "approval_request",
            "text": message,
            "tool": tool_name,
            "params": parameters,
        }
        try:
            self.event_queue.put_nowait(event)
        except Exception as exc:  # noqa: BLE001 — không bắn được UI cũng không sập luồng
            logger.warning("Không bắn được VIBE DIFF ra UI: %s", exc)

    # ------------------------------------------------------------------ #
    @staticmethod
    def _default_gate(tool_name: str, parameters: dict, message: str) -> bool:
        """Cổng mặc định: CHẶN. AURA không tự chạy tool khi chưa có cái gật của Sếp."""
        logger.info("VIBE DIFF: '%s' chờ Sếp duyệt — mặc định CHẶN.", tool_name)
        return False


__all__ = [
    "vibe_diff_translator",
    "build_vibe_diff_message",
    "assess_harm",
    "is_approval",
    "is_rejection",
    "VibeDiffInterceptor",
    "VIBE_DIFF_PREFIX",
    "DEFAULT_AUTO_APPROVE",
    "AUTO_PLAN_LOCAL_TOOLS",
    "auto_plan_approvals",
    "ApproveFn",
]
