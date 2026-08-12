"""
core/orchestrator.py
====================
AURA_Orchestrator — Agent Loop dạng State Machine tường minh.

Thay thế hoàn toàn lối "PASS 1 -> PASS 2.7 -> PASS 2.8" chắp vá của hệ cũ bằng
một vòng đời rõ ràng, debug được:

    INTENT  ->  PLAN  ->  ACT  ->  OBSERVE  ->  (RESPOND | re-PLAN nếu cần sửa)

Mỗi bước chuyển trạng thái đều được ghi vào `trace` để soi khi có lỗi — đây
chính là thứ hệ cũ thiếu (không lần ra được luồng chạy).

Kết nối sẵn trong __init__:
  - MemoryStore : recall ngữ cảnh + lưu buffer hội thoại (collection "conversation").
  - BrainRouter : ra quyết định Local/Cloud và thực thi (có fallback).
  - ToolRegistry: (tùy chọn) dispatch các tác vụ tool. Chưa lắp ở phase này thì
                  Orchestrator báo cáo trung thực thay vì giả vờ thành công.

`process_message(text)` là API dùng chung cho cả Terminal lẫn WebSocket/VTuber.
"""

from __future__ import annotations

import concurrent.futures
import hashlib
import logging
import re
import unicodedata
from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol, runtime_checkable

from brains.base import ChatMessage
from brains.cloud_claude import ClaudeBackend
from brains.local_ollama import OllamaBackend
from core.brain_router import BrainRouter
from core.config import PROJECT_ROOT, settings
from core.memory import MemoryStore
from core.self_diagnose import SelfDiagnose
from core.self_history import (
    answer_self_history,
    awareness_context,
    is_self_history_question,
    record_event,
)
from core.self_tuition import (
    answer_self_tuition,
    is_self_tuition_question,
    tuition_context,
)
from core.vibe_diff import (
    VIBE_DIFF_PREFIX,
    VibeDiffInterceptor,
    auto_plan_approvals,
    is_approval,
    is_rejection,
)
from core.schemas import (
    Intent,
    IntentLabel,
    MangaTarget,
    Plan,
    RouteTier,
    Task,
    TaskStatus,
    ToolResult,
)

logger = logging.getLogger("aura.orchestrator")

# Những nhãn được phục vụ trực tiếp bởi bộ não (không cần tool ngoài).
_BRAIN_LABELS: frozenset[IntentLabel] = frozenset(
    {
        IntentLabel.CHITCHAT,
        IntentLabel.CODING,
        IntentLabel.HEAVY_REASONING,
        IntentLabel.MEMORY_QUERY,
        IntentLabel.UNKNOWN,
    }
)

# Ánh xạ nhãn tool -> tên tool trong registry.
_TOOL_FOR_LABEL: dict[IntentLabel, str] = {
    IntentLabel.MANGA_DOWNLOAD: "manga.download",
    IntentLabel.MANGA_TRANSLATE: "manga.translate",
    IntentLabel.WEB_SCRAPE: "web.scrape",
    IntentLabel.JOB_SCOUT: "job.scout",
    IntentLabel.KNOWLEDGE_INGEST: "knowledge.ingest",
    IntentLabel.SYSTEM_CONTROL: "system.control",
    IntentLabel.SYSTEM_TERMINAL: "system.terminal",
    IntentLabel.VIDEO_DOWNLOAD: "video.download",
}

# Nhãn brain KHÓ -> bật tầng tư duy (deliberation).
_DELIBERATE_LABELS: frozenset = frozenset({IntentLabel.HEAVY_REASONING, IntentLabel.CODING})

# Giới hạn buffer hội thoại ngắn hạn giữ trong RAM (số message, ~ nửa số lượt).
_HISTORY_MAX_MESSAGES = 20
# Số vòng re-plan tối đa để tránh lặp vô hạn khi tác vụ cứ lỗi.
_MAX_REPLAN_ITERATIONS = 2


# ---------------------------------------------------------------------------
# Trạng thái state machine
# ---------------------------------------------------------------------------
class AgentState(str, Enum):
    """Các trạng thái trong một vòng xử lý của agent."""

    INTENT = "intent"
    PLAN = "plan"
    ACT = "act"
    OBSERVE = "observe"
    RESPOND = "respond"
    DONE = "done"
    FAILED = "failed"


@dataclass
class TurnTrace:
    """Nhật ký một lượt xử lý — để debug và (sau này) hiển thị lên dashboard."""

    user_text: str
    intent: Intent | None = None
    states: list[str] = field(default_factory=list)
    response: str = ""
    succeeded: bool = False

    def mark(self, state: AgentState, note: str = "") -> None:
        entry = state.value if not note else f"{state.value}: {note}"
        self.states.append(entry)
        logger.debug("[trace] %s", entry)


# ---------------------------------------------------------------------------
# Giao diện ToolRegistry (lắp đầy ở phase tools)
# ---------------------------------------------------------------------------
@runtime_checkable
class ToolRegistryProtocol(Protocol):
    """Hợp đồng tối thiểu mà một ToolRegistry phải đáp ứng để Orchestrator gọi."""

    def has(self, tool_name: str) -> bool: ...

    def dispatch(self, task: Task) -> ToolResult: ...


# ---------------------------------------------------------------------------
# Trích xuất tham số manga (tái dùng bản vá float cho số chương lẻ)
# ---------------------------------------------------------------------------
_CHAPTER_RE = re.compile(
    r"(?:chương|chapter|chap|ch)\s*[:#]?\s*(\d+(?:[.,]\d+)?)", re.IGNORECASE
)


def extract_manga_target(text: str) -> MangaTarget | None:
    """
    Bóc tên truyện + số chương từ câu lệnh tự do.

    Số chương parse dạng float (10.5 hợp lệ) — KHÔNG int() như bug cũ.
    Trả None nếu không thấy số chương (để Orchestrator hỏi lại thay vì đoán bừa).
    """
    match = _CHAPTER_RE.search(text)
    if not match:
        return None
    chapter = float(match.group(1).replace(",", "."))

    # Tên truyện: cắt bỏ phần "chương N" và các động từ lệnh phổ biến ở đầu.
    title_part = text[: match.start()]
    title_part = re.sub(
        r"\b(tải|download|dịch|dich|truyện|truyen|manga|giúp|giup|cho tôi|cho toi)\b",
        " ",
        title_part,
        flags=re.IGNORECASE,
    )
    title = " ".join(title_part.split()).strip(" -:") or "unknown"
    try:
        return MangaTarget(title=title, chapter=chapter)
    except ValueError as exc:  # title rỗng sau khi strip, hoặc chapter <= 0
        logger.warning("Không dựng được MangaTarget: %s", exc)
        return None


# ---------------------------------------------------------------------------
# QUY LUẬT THÉP (Iron Rule) — ép nhãn theo từ khoá, bỏ qua quyết định của LLM
# ---------------------------------------------------------------------------
# Model local hay chọn nhầm web.scrape khi Sếp bảo "tải truyện". Với các câu
# chứa từ khoá manga, ta CHẶN trước ở khâu phân loại và ÉP đúng tool manga.*,
# không để LLM tự quyết.
_JOB_HINTS: tuple[str, ...] = (
    "công việc", "cong viec", "việc làm", "viec lam", "tuyển dụng", "tuyen dung",
    "tìm việc", "tim viec", "job", "cv", "recruit", "hiring", "vacancy",
)
_KNOWLEDGE_HINTS: tuple[str, ...] = (
    "học tài liệu", "hoc tai lieu", "ghi nhớ tài liệu", "đọc và nhớ", "doc va nho",
    "nạp kiến thức", "nap kien thuc", "học từ", "hoc tu", "nhớ tài liệu", "đọc sách",
)
# Điều khiển hệ thống — chỉ cụm RÕ RÀNG (tránh nuốt "mở truyện"/"xoá chương").
_SYSCTL_HINTS: tuple[str, ...] = (
    "mở ứng dụng", "mo ung dung", "mở app", "mở notepad", "mở chrome", "mở edge",
    "mở thư mục", "mở file", "mở đường link", "liệt kê thư mục", "tạo thư mục",
    "xoá file", "xóa file", "đổi tên file", "di chuyển file", "sao chép file",
    "dọn ổ", "dọn rác", "dung lượng ổ", "thông tin hệ thống", "còn bao nhiêu ram",
)
_MANGA_HINTS: tuple[str, ...] = (
    "tải truyện", "tai truyen", "truyện tranh", "truyen tranh",
    "tải manga", "tai manga", "cào truyện", "download manga", "download truyện",
    "tải chap", "tai chap", "tải chapter", "download chap", "cào chap",
)
# Tải video/file từ URL trực tiếp -> ép skill video.download (AURA tự viết, task #52385).
# Cụm phải chứa "video/clip" để không nuốt "tải truyện" (manga) hay "tải tài liệu" (knowledge).
_VIDEO_HINTS: tuple[str, ...] = (
    "tải video", "tai video", "download video", "tải clip", "tai clip",
    "tải phim", "tai phim", "download clip",
)
# Nếu câu còn ý 'dịch' -> ép manga.translate thay vì manga.download (khỏi sai ý).
_TRANSLATE_HINTS: tuple[str, ...] = (
    "dịch", "dich", "translate", "việt hoá", "viet hoa", "việt hóa",
)


def _iron_rule_label(text: str) -> IntentLabel | None:
    """
    Quy luật thép: nếu câu lệnh chứa từ khoá manga -> ÉP nhãn manga.*,
    bỏ qua LLM. Trả None nếu không khớp (để classifier LLM xử lý như thường).
    """
    low = (text or "").lower()
    # Việc làm / tuyển dụng -> ép thẳng job.scout (độc lập với manga).
    if any(h in low for h in _JOB_HINTS):
        return IntentLabel.JOB_SCOUT
    # Tự đọc tài liệu & ghi nhớ -> ép KNOWLEDGE_INGEST.
    if any(h in low for h in _KNOWLEDGE_HINTS):
        return IntentLabel.KNOWLEDGE_INGEST
    # Điều khiển laptop -> ép SYSTEM_CONTROL (đi qua VIBE DIFF xin duyệt).
    if any(h in low for h in _SYSCTL_HINTS):
        return IntentLabel.SYSTEM_CONTROL
    # Suy luận sâu -> HEAVY_REASONING (kích hoạt tầng tư duy).
    if any(h in low for h in _DEEP_HINTS):
        return IntentLabel.HEAVY_REASONING
    # Tải video/clip -> ép video.download (đặt TRƯỚC manga: cụm đã chứa "video/clip"
    # nên không đụng "tải truyện"; để LLM tự quyết thì local gemma nói nhảm).
    if any(h in low for h in _VIDEO_HINTS):
        return IntentLabel.VIDEO_DOWNLOAD
    if not any(h in low for h in _MANGA_HINTS):
        if any(h in low for h in _TRANSLATE_HINTS) and any(m in low for m in ("manga", "truyện tranh", "truyen tranh")):
            return IntentLabel.MANGA_TRANSLATE
        return None
    if any(h in low for h in _TRANSLATE_HINTS):
        return IntentLabel.MANGA_TRANSLATE
    return IntentLabel.MANGA_DOWNLOAD


# Câu hỏi cần SUY LUẬN sâu -> bật tầng tư duy (deliberation). Ưu tiên thấp nhất.
_DEEP_HINTS: tuple[str, ...] = (
    "phân tích", "phan tich", "so sánh", "so sanh", "lập kế hoạch", "lap ke hoach",
    "đánh giá", "danh gia", "giải thích kỹ", "vì sao", "tại sao", "nên chọn",
    "chiến lược", "chien luoc", "ưu nhược", "uu nhuoc",
)


# ---------------------------------------------------------------------------
# ĐIỀU KHIỂN NĂNG LƯỢNG 2 CẤP — phát hiện lệnh trạng thái (chặn TRƯỚC mọi nhãn)
# ---------------------------------------------------------------------------
# Cấp 1: AURA ngủ đông / thức dậy (đóng băng nhịp ngầm của daemon).
_FREEZE_HINTS: tuple[str, ...] = (
    "aura ngủ đông", "aura ngu dong", "aura đi ngủ", "aura di ngu",
    "tạm dừng chạy ngầm", "tam dung chay ngam", "tạm dừng nền", "tam dung nen",
)
_UNFREEZE_HINTS: tuple[str, ...] = (
    "aura thức dậy", "aura thuc day", "aura làm việc tiếp", "aura lam viec tiep",
    "aura dậy đi", "aura day di",
)
# Cấp 2: laptop ngủ đông (gọi skill system.power tắt phần cứng).
_HIBERNATE_HINTS: tuple[str, ...] = (
    "laptop ngủ đông", "laptop ngu dong", "máy tính đi ngủ", "may tinh di ngu",
    "sleep máy", "sleep may", "cho máy ngủ", "cho may ngu", "cho laptop ngủ",
)


def _detect_control(text: str) -> str | None:
    """
    Phát hiện lệnh điều khiển năng lượng. Trả 'unfreeze'|'hibernate'|'freeze' hoặc None.
    Kiểm TRƯỚC Iron Rule để không bị classifier nuốt nhầm.
    """
    low = (text or "").lower()
    if any(h in low for h in _UNFREEZE_HINTS):
        return "unfreeze"
    if any(h in low for h in _HIBERNATE_HINTS):
        return "hibernate"
    if any(h in low for h in _FREEZE_HINTS):
        return "freeze"
    return None


# ---------------------------------------------------------------------------
# CẬP NHẬT CHÂN DUNG SẾP qua chat (goal/habit/weakness) — Bước 2
# ---------------------------------------------------------------------------
_PROFILE_CATS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("weakness", "ĐIỂM YẾU", ("điểm yếu", "diem yeu", "nhược điểm", "nhuoc diem", "tật xấu", "tat xau")),
    ("habit",    "THÓI QUEN", ("thói quen", "thoi quen")),
    ("goal",     "MỤC TIÊU",  ("mục tiêu", "muc tieu", "mục đích", "muc dich")),
)
_PROFILE_WRITE_VERBS: tuple[str, ...] = (
    "thêm", "them", "ghi nhớ", "ghi nho", "ghi lại", "ghi lai", "cập nhật", "cap nhat",
    "lưu", "luu", "đặt", "dat", "nhớ giúp", "nho giup", "set", "add", "record", "ghi",
)
_PROFILE_QUESTION_HINTS: tuple[str, ...] = (
    "là gì", "la gi", "là sao", "la sao", "thế nào", "the nao", "bao nhiêu", "bao nhieu",
    "có không", "co khong",
)


def _extract_profile_content(text: str, cat_words: tuple[str, ...]) -> str:
    """Bóc nội dung sau ':' hoặc ' là '; không có thì lược verb + từ khoá category."""
    t = (text or "").strip()
    low = t.lower()
    for sep in (":", " là ", " is "):
        idx = low.find(sep)
        if idx != -1:
            return t[idx + len(sep):].strip(" .\"'“”")
    out = t
    strip_words = cat_words + _PROFILE_WRITE_VERBS + (
        "của tôi", "cua toi", "cho tôi", "cho toi", "mới", "moi",
        "vào hồ sơ", "vao ho so", "giúp", "giup",
    )
    for w in strip_words:
        out = re.sub(re.escape(w), " ", out, flags=re.IGNORECASE)
    return " ".join(out.split()).strip(" .\"'“”")


def _detect_profile_update(text: str) -> dict | None:
    """
    Phát hiện ý định GHI Chân dung Sếp. Trả {category,label,text,kind} hoặc None.
    Chỉ bắt câu KHAI BÁO/GHI (bỏ câu hỏi) — phần xác nhận 'Y' do Vibe Diff lo.
    """
    low = (text or "").lower().strip()
    if not low or low.endswith("?") or any(q in low for q in _PROFILE_QUESTION_HINTS):
        return None
    for cat, label, words in _PROFILE_CATS:
        if any(w in low for w in words):
            has_verb = any(v in low for v in _PROFILE_WRITE_VERBS)
            if not (has_verb or " là " in f" {low} " or ":" in text):
                return None
            content = _extract_profile_content(text, words)
            if not content:
                return None
            kind = "bad" if (cat == "habit" and any(
                b in low for b in ("bỏ", "tật xấu", "tat xau", "xấu", "xau", "cai nghiện", "cai nghien")
            )) else "good"
            return {"category": cat, "label": label, "text": content, "kind": kind}
    return None


def _profile_key(text: str) -> str:
    """ID ổn định ascii-an-toàn từ nội dung (slug + hash ngắn): cùng nội dung -> cùng key."""
    base = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii").lower()
    slug = re.sub(r"[^a-z0-9]+", "-", base).strip("-")[:24].strip("-") or "item"
    h = hashlib.md5(text.strip().lower().encode("utf-8")).hexdigest()[:6]
    return f"{slug}-{h}"


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------
class AURA_Orchestrator:
    """
    Điều phối viên trung tâm. Cầm state machine và ráp Memory + Router + Tools.

    Ví dụ:
        orch = AURA_Orchestrator()          # tự dựng Memory + Router mặc định
        print(orch.process_message("Chào AURA"))
        orch.run_agent_loop()               # chế độ REPL terminal
    """

    DEFAULT_PERSONA = (
        f"Bạn là AURA — quản gia AI cá nhân của Sếp. "
        f"Mã nguồn gốc (thư mục làm việc hiện tại) của bạn đang nằm tại '{PROJECT_ROOT}'. "
        "Trả lời thẳng vào vấn đề, tối giản, không rườm rà. "
        "Ưu tiên giải pháp ít thao tác nhất cho sếp."
    )

    def __init__(
        self,
        router: BrainRouter | None = None,
        memory: MemoryStore | None = None,
        registry: ToolRegistryProtocol | None = None,
        persona: str | None = None,
        event_queue=None,
        vibe_diff: VibeDiffInterceptor | None = None,
    ) -> None:
        """
        Khởi tạo và KẾT NỐI các thành phần lõi ngay tại đây (yêu cầu #2).

        Cho phép tiêm phụ thuộc (dependency injection) để test; nếu không truyền
        thì tự dựng mặc định: Ollama (local) + Claude (cloud) cho Router, và
        MemoryStore ChromaDB.

        event_queue: hàng đợi chia sẻ với server. SelfDiagnose dùng để bắn đề xuất
            sửa lỗi ra UI cho Sếp duyệt khi một tool thất bại.
        """
        self.memory = memory if memory is not None else MemoryStore()
        self.router = router if router is not None else BrainRouter(
            local=OllamaBackend(),
            cloud=ClaudeBackend(),
        )
        self.registry = registry
        self.persona = persona or self.DEFAULT_PERSONA
        self.event_queue = event_queue
        # Auto Plan xử lý việc nội bộ/bản nháp đã kiểm toán; việc ra ngoài hoặc có
        # rủi ro vẫn đi qua VIBE DIFF để Chủ quyết định.
        self.vibe_diff = vibe_diff or VibeDiffInterceptor(
            event_queue=event_queue,
            auto_approve=auto_plan_approvals(settings.auto_plan_enabled),
        )
        # Plan đang chờ Sếp phê duyệt (HITL xuyên lượt qua tin 'duyệt'/'huỷ').
        self._pending_plan: Plan | None = None
        # Điều khiển năng lượng 2 cấp: tham chiếu daemon nền (Cấp 1) + lệnh đang chờ
        # Sếp gõ 'Y' ('freeze'|'unfreeze'|'hibernate'). main.py gắn self.daemon sau khi dựng.
        self.daemon = None
        self._pending_control: str | None = None
        # Hội đồng 3 nhân cách (Triad Council) + cầu Human Gate qua chat (lắp ở main.py).
        self.council = None
        self.council_bridge = None
        self.loop = None
        # Chân dung Sếp (Bước 2): nạp hồ sơ để nhồi vào prompt + cập nhật qua chat (Vibe Diff).
        try:
            from core.profile import ProfileStore
            self.profile = ProfileStore()
        except Exception as exc:  # noqa: BLE001 — thiếu hồ sơ KHÔNG được làm sập orchestrator
            logger.warning("Không mở được Chân dung Sếp (bỏ qua): %s", exc)
            self.profile = None
        self._pending_profile: dict | None = None
        # Tầng tư duy: câu khó -> lập kế hoạch + tự phản biện (nhẹ CPU, chỉ tác vụ khó).
        self.deliberate_enabled = True

        # Mắt chẩn lỗi: khi tool fail ở nhánh OBSERVE, tự gói traceback/lỗi -> hỏi
        # Claude -> bắn đề xuất ra UI (event_queue) cho Sếp duyệt.
        self.diagnoser = SelfDiagnose(self.router, event_queue=event_queue)

        # Buffer hội thoại ngắn hạn trong RAM (recency); ChromaDB lo phần relevance.
        self._history: list[ChatMessage] = []
        # Hội thoại từ điện thoại robot có buffer riêng. Quan trọng: kênh này không bao giờ
        # đi qua các trạng thái pending approval/control/profile của process_message().
        self._avatar_history: list[ChatMessage] = []
        # Nạp trễ tầng cloud miễn phí dành cho Avatar. Kênh robot cần phản hồi nhanh;
        # model local 7GB của laptop chỉ là phương án cho UI chính, không phù hợp thoại realtime.
        self._avatar_cloud = None
        logger.info("AURA_Orchestrator sẵn sàng (registry=%s, diagnose=%s).",
                    "có" if registry else "chưa lắp",
                    "bật" if event_queue is not None else "chỉ-log")

    # ================================================================== #
    # API CHÍNH — dùng chung cho Terminal & WebSocket
    # ================================================================== #
    def process_message(self, text: str, *, audit: bool = True) -> str:
        """Bọc API chính để mọi câu lệnh/kết quả đều vào hồ sơ tự nhận thức."""
        cleaned = (text or "").strip()
        request_id = ""
        if cleaned and audit:
            try:
                request_id = record_event(
                    actor="Sếp",
                    kind="user_request",
                    summary=cleaned,
                    status="received",
                    source="aura_chat",
                    tags=["conversation", "owner_instruction"],
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("Ghi yêu cầu vào hồ sơ AURA lỗi (bỏ qua): %s", exc)
        try:
            response = self._impl_within_budget(cleaned)
        except Exception as exc:
            if audit:
                try:
                    record_event(
                        actor="AURA",
                        kind="request_result",
                        summary=f"Không xử lý được yêu cầu: {type(exc).__name__}: {exc}",
                        status="failed",
                        source="aura_chat",
                        request_id=request_id,
                        tags=["conversation", "runtime_error"],
                    )
                except Exception:  # noqa: BLE001
                    pass
            raise
        if audit:
            try:
                record_event(
                    actor="AURA",
                    kind="request_result",
                    summary=response,
                    status="completed",
                    source="aura_chat",
                    request_id=request_id,
                    tags=["conversation", "response"],
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("Ghi kết quả vào hồ sơ AURA lỗi (bỏ qua): %s", exc)
        return response

    def _impl_within_budget(self, text: str) -> str:
        """Trần thời gian cho CẢ LƯỢT, không phải cho từng lời gọi.

        Từng backend đều đã có hạn giờ riêng (Ollama, cloud, router), nhưng cả
        đường đi thì không: local gục -> rơi xuống cloud -> lập lại kế hoạch, cộng
        dồn thành treo vô hạn.  08/08/2026 đo được: một câu hỏi tự do chạy 500 giây
        vẫn chưa trả về, nên Telegram không có gì để gửi và Sếp tưởng AURA điếc.

        Thà trả một câu xấu còn hơn im lặng: im lặng khiến người dùng không phân
        biệt được "đang nghĩ" với "đã chết".

        Luồng bị bỏ rơi vẫn chạy nốt (Python không giết được thread), nhưng nó là
        thread nền và không giữ chân câu trả lời nữa.
        """
        budget = float(getattr(settings, "chat_turn_budget_s", 90.0) or 90.0)
        if budget <= 0:
            return self._process_message_impl(text)
        pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        future = pool.submit(self._process_message_impl, text)
        try:
            return future.result(timeout=budget)
        except concurrent.futures.TimeoutError:
            logger.warning(
                "Lượt chat quá %.0fs mà chưa xong — trả lời thật thà thay vì treo.", budget
            )
            return (
                f"⏳ AURA nghĩ quá {budget:.0f} giây mà chưa ra câu trả lời.\n"
                "Thường là bộ não local trả rỗng rồi cloud đang nghẽn hoặc hết hạn mức.\n"
                "Sếp thử lại sau ít phút, hoặc hỏi câu ngắn hơn."
            )
        finally:
            pool.shutdown(wait=False)

    def _process_message_impl(self, text: str) -> str:
        """
        Chạy trọn một vòng state machine cho một câu input và trả về câu trả lời.

        Đây là điểm vào duy nhất cho mọi giao diện. Không ai gọi thẳng router.
        """
        text = (text or "").strip()
        if not text:
            return "Sếp chưa nhập gì cả."

        # Hỏi về chính AURA phải trả từ ledger + git thật trên MỌI giao diện,
        # không chỉ WebSocket. Đặt trước các pending gate để câu hỏi không bị hiểu
        # nhầm thành phản hồi duyệt/hủy.
        if is_self_tuition_question(text):
            return answer_self_tuition(query=text)
        if is_self_history_question(text):
            return answer_self_history(query=text)
        # "Mật khẩu wifi / đang nối mạng nào" -> đọc netsh THẬT trên máy, không để
        # LLM bịa (Sếp quên mật khẩu, đây là dữ liệu đã lưu trên chính máy này).
        from core.wifi_manager import answer_wifi, is_wifi_question
        if is_wifi_question(text):
            return answer_wifi(text)
        # "Ngừng/bật săn job" là LỆNH điều khiển công nhân, KHÔNG phải xin báo cáo.
        # Chặn TRƯỚC iron-rule JOB_SCOUT (kẻo 'tạm ngừng săn job' bị hiểu thành
        # 'cho xem báo cáo job' -> trả lời một nẻo).
        from core.worker_control import handle_worker_control, is_worker_control
        if is_worker_control(text):
            return handle_worker_control(text)
        # "xe tiến 2 giây" / "robot dừng" -> điều khiển xe THẬT qua BLE.
        # Bắt buộc có từ chỉ xe (xe/robot/rover) nên không cướp câu chat thường.
        from core.rover import handle_rover_command, is_rover_command
        if is_rover_command(text):
            return handle_rover_command(text)

        # HUMAN GATE: đang chờ Sếp nghiệm thu code của Hội đồng? (Y / 'không, lý do')
        if self.council_bridge is not None and self.council_bridge.has_pending:
            handled, resp = self.council_bridge.handle_reply(text)
            if handled:
                return resp
        # Hội đồng đang VIẾT (chưa có gì duyệt) mà Sếp gõ 'Y' sớm -> nói rõ, đừng lọt xuống chat.
        elif self.council_bridge is not None and self.council_bridge.is_in_flight:
            from core.vibe_diff import is_approval
            if is_approval(text):
                return ("Hội đồng đang viết code, chưa có gì để Sếp duyệt. Em sẽ trình code "
                        "kèm lời mời nghiệm thu ('Y' / 'không, lý do') ngay khi viết xong nhé.")

        # HITL Cấp năng lượng: đang chờ Sếp gõ 'Y' cho lệnh ngủ đông?
        if self._pending_control is not None:
            decided = self._resolve_pending_control(text)
            if decided is not None:
                return decided

        # HITL Chân dung Sếp: đang chờ Sếp gõ 'Y' cho cập nhật hồ sơ?
        if self._pending_profile is not None:
            decided = self._resolve_pending_profile(text)
            if decided is not None:
                return decided

        # HITL: nếu đang có tác vụ chờ duyệt, ưu tiên xử lý câu trả lời duyệt/huỷ.
        if self._pending_plan is not None:
            decided = self._resolve_pending_approval(text)
            if decided is not None:
                return decided

        # ĐIỀU KHIỂN NĂNG LƯỢNG (Cấp 1/2): chặn TRƯỚC mọi phân loại; in dòng xác nhận
        # và chờ Sếp gõ 'Y' (Vibe Diff) trước khi thực thi.
        control = _detect_control(text)
        if control is not None:
            self._pending_control = control
            return self._control_confirm_message(control)

        # CẬP NHẬT CHÂN DUNG SẾP: bắt ý định ghi goal/habit/weakness -> xin duyệt 'Y'.
        prof_update = _detect_profile_update(text)
        if prof_update is not None:
            self._pending_profile = prof_update
            return self._profile_confirm_message(prof_update)

        # TRIỆU TẬP HỘI ĐỒNG viết tool (tiền tố rõ ràng): "hội đồng: <yêu cầu>"
        if text.lower().startswith(("hội đồng:", "hoi dong:", "triệu tập hội đồng",
                                    "trieu tap hoi dong", "viết tool:", "viet tool:")):
            return self._start_council(text)

        trace = TurnTrace(user_text=text)

        # --- STATE: INTENT ---
        trace.mark(AgentState.INTENT)
        # QUY LUẬT THÉP: từ khoá manga -> ép nhãn manga.*, KHÔNG hỏi LLM.
        forced = _iron_rule_label(text)
        if forced is not None:
            intent = Intent(
                label=forced, tier=RouteTier.LOCAL, confidence=1.0,
                reason="quy-luật-thép: ép nhãn manga theo từ khoá", raw_text=text,
            )
            trace.mark(AgentState.INTENT, f"IRON RULE -> {forced.value}")
        else:
            intent = self.router.classify(text)
            trace.mark(AgentState.INTENT, f"{intent.label.value}/{intent.tier.value}")
        trace.intent = intent

        # --- STATE: PLAN ---
        trace.mark(AgentState.PLAN)
        plan = self._plan(intent, text)

        # --- STATE: ACT + OBSERVE (có thể lặp re-plan) ---
        response = self._act_and_observe(plan, text, trace)

        # --- STATE: RESPOND + lưu buffer ---
        trace.mark(AgentState.RESPOND)
        trace.response = response
        self._remember_turn(text, response)
        trace.mark(AgentState.DONE if trace.succeeded else AgentState.FAILED)
        return response

    def process_avatar_message(self, text: str) -> str:
        """Kênh Vivo cũng ghi/đọc cùng hồ sơ, nhưng vẫn giữ rào chỉ-hội-thoại."""
        cleaned = (text or "").strip()
        request_id = ""
        if cleaned:
            try:
                request_id = record_event(
                    actor="Sếp",
                    kind="user_request",
                    summary=cleaned,
                    status="received",
                    source="aura_avatar",
                    tags=["conversation", "owner_instruction", "vivo"],
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("Ghi yêu cầu Avatar vào hồ sơ lỗi (bỏ qua): %s", exc)
        try:
            response = self._process_avatar_message_impl(cleaned)
        except Exception as exc:
            try:
                record_event(
                    actor="AURA Avatar",
                    kind="request_result",
                    summary=f"Không xử lý được yêu cầu: {type(exc).__name__}: {exc}",
                    status="failed",
                    source="aura_avatar",
                    request_id=request_id,
                    tags=["conversation", "runtime_error", "vivo"],
                )
            except Exception:  # noqa: BLE001
                pass
            raise
        try:
            record_event(
                actor="AURA Avatar",
                kind="request_result",
                summary=response,
                status="completed",
                source="aura_avatar",
                request_id=request_id,
                tags=["conversation", "response", "vivo"],
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Ghi kết quả Avatar vào hồ sơ lỗi (bỏ qua): %s", exc)
        return response

    def _process_avatar_message_impl(self, text: str) -> str:
        """
        Trả lời điện thoại AURA Avatar bằng một đường hội thoại chỉ-đọc.

        Không gọi classify/plan/tool và không đọc hoặc thay đổi bất kỳ trạng thái chờ
        duyệt nào. Nhờ vậy tiếng nói nhận sai trên điện thoại không thể vô tình duyệt
        kế hoạch, điều khiển Windows hay thực hiện giao dịch.
        """
        text = (text or "").strip()
        if not text:
            return "Tôi chưa nghe rõ. Bạn nói lại giúp tôi nhé."
        if len(text) > 500:
            return "Câu nói dài quá. Bạn nói ngắn hơn giúp tôi nhé."

        if is_self_tuition_question(text):
            # Chỉ đọc lesson ledger đã kiểm chứng; không đi qua router, tool hay trạng thái duyệt.
            return answer_self_tuition(query=text, limit=5)[:1200]
        if is_self_history_question(text):
            # Chỉ đọc ledger/git; không đi qua router, tool hoặc trạng thái duyệt.
            return answer_self_history(query=text, limit=6)[:1200]

        intent = Intent(
            label=IntentLabel.CHITCHAT,
            tier=RouteTier.LOCAL,
            confidence=1.0,
            reason="aura-avatar-conversation-only",
            raw_text=text,
        )
        system_prompt = self._build_system_prompt(intent, text) + (
            "\n\n[KÊNH AURA AVATAR — CHỈ HỘI THOẠI]\n"
            "Đây là giọng nói từ điện thoại robot. Chỉ trả lời hoặc giải thích; tuyệt đối "
            "không duyệt/hủy kế hoạch đang chờ, không chạy công cụ, không điều khiển máy, "
            "không thực hiện giao dịch và không khẳng định đã làm một hành động. "
            "Trả lời bằng tiếng Việt tự nhiên, tối đa khoảng 400 ký tự, phù hợp để đọc thành tiếng."
        )
        messages = self._avatar_history + [{"role": "user", "content": text}]
        result = None
        # Runtime thật dùng AgentBroker. Nếu AURA đang cấu hình router/openai/gemini miễn phí,
        # cho Avatar đi thẳng qua CloudEngine để không nạp model local 7GB gây đầy RAM.
        # Test hoặc orchestrator được nhúng với router khác vẫn dùng đúng router được tiêm.
        is_runtime_broker = self.router.__class__.__name__ == "AgentBroker"
        free_cloud = settings.cloud_provider in {"router", "openai", "gemini"}
        if is_runtime_broker and free_cloud:
            try:
                from core.llm import CloudEngine
                from core.redact import redact, redact_messages

                if self._avatar_cloud is None:
                    self._avatar_cloud = CloudEngine()
                safe_messages = redact_messages(messages)
                safe_prompt = redact(system_prompt)
                output = self._avatar_cloud.chat(
                    safe_messages,
                    system_prompt=safe_prompt,
                    temperature=0.45,
                    max_tokens=320,
                    tier="fast",
                )
                result = ToolResult.success("avatar:free-cloud", output)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Tầng AI miễn phí cho AURA Avatar lỗi: %s", exc)
                result = ToolResult.failure("avatar:free-cloud", str(exc))
        else:
            result = self.router.run(
                messages, intent, system_prompt=system_prompt, max_tokens=320
            )
        self._record_metric("avatar.chat", result.ok, getattr(result, "elapsed_ms", 0))
        if not result.ok:
            return "Bộ não AURA đang tạm mất kết nối. Tôi chưa thể trả lời lúc này."

        response = (result.output or "").strip()
        if not response:
            response = "Tôi đang nghe, nhưng chưa tạo được câu trả lời."
        # Giữ câu trả lời vừa đủ cho loa điện thoại và tránh payload bất thường.
        response = response[:1200]
        self._remember_avatar_turn(text, response)
        return response

    def run_agent_loop(self) -> None:
        """Chế độ REPL terminal để debug nhanh (giao diện WebSocket gọi process_message)."""
        print("=" * 52)
        print("AURA Agent Loop — gõ 'exit' để thoát")
        print("=" * 52)
        try:
            while True:
                user_text = input("\n🤔 Sếp: ").strip()
                if user_text.lower() in {"exit", "quit", "bye"}:
                    print("\n👋 AURA tạm nghỉ. Hẹn gặp lại sếp.")
                    break
                if not user_text:
                    continue
                answer = self.process_message(user_text)
                print(f"\n💡 AURA: {answer}")
        except (EOFError, KeyboardInterrupt):
            print("\n\n👋 Thoát.")

    # ================================================================== #
    # STATE: PLAN
    # ================================================================== #
    def _plan(self, intent: Intent, text: str) -> Plan:
        """
        Biến intent thành Plan.

        - Nhãn brain  -> Plan rỗng task (Act = gọi bộ não với ngữ cảnh).
        - Nhãn tool   -> Plan có Task(tool_name, arguments đã chuẩn hoá).
        """
        if intent.label in _BRAIN_LABELS:
            return Plan(intent=intent, tasks=[])

        tool_name = _TOOL_FOR_LABEL.get(intent.label)
        if tool_name is None:
            # Không nên xảy ra, nhưng phòng hờ: coi như tác vụ brain.
            return Plan(intent=intent, tasks=[])

        arguments = self._build_tool_arguments(intent.label, text)
        task = Task(tool_name=tool_name, arguments=arguments)
        return Plan(intent=intent, tasks=[task])

    def _build_tool_arguments(self, label: IntentLabel, text: str) -> dict:
        """Chuẩn hoá tham số cho từng loại tool (thay cho regex bóc tách rải rác cũ)."""
        if label in (IntentLabel.MANGA_DOWNLOAD, IntentLabel.MANGA_TRANSLATE):
            # Bóc link nguồn nếu Sếp dán vào câu lệnh -> để VIBE DIFF hiện đúng link
            # và manga.download có source_url mà cào.
            url_match = re.search(r"https?://\S+", text)
            source_url = (
                url_match.group(0).rstrip(".,;)]}\"'") if url_match else None
            )
            # Loại URL khỏi text trước khi bóc tên truyện (khỏi dính link vào title).
            text_for_title = text.replace(source_url, " ") if source_url else text
            target = extract_manga_target(text_for_title)
            if target is None:
                return {}  # thiếu số chương -> Act sẽ hỏi lại
            args = {"title": target.title, "chapter": target.chapter}
            if source_url:
                args["source_url"] = source_url
            return args
        if label == IntentLabel.KNOWLEDGE_INGEST:
            url_match = re.search(r"https?://\S+", text)
            if url_match:
                return {"source": url_match.group(0).rstrip(".,;)]}\"'")}
            # không có URL -> để skill tự hiểu source là file/văn bản thô.
            return {"source": text}
        if label == IntentLabel.JOB_SCOUT:
            # Bóc URL tuyển dụng nếu Sếp dán vào; không có -> dùng URL mẫu.
            found = re.findall(r"https?://\S+", text)
            urls = [u.rstrip(".,;)]}\"'") for u in found] or None
            return {"urls": urls}  # dict non-rỗng -> qua được cổng kiểm tham số
        if label == IntentLabel.WEB_SCRAPE:
            url_match = re.search(r"https?://\S+", text)
            return {"url": url_match.group(0)} if url_match else {"query": text}
        if label == IntentLabel.VIDEO_DOWNLOAD:
            # Skill chỉ tải URL http(s) TRỰC TIẾP. Không có URL (Sếp chỉ nói tên
            # video) -> {} để _dispatch_tasks hỏi lại, KHÔNG đoán bừa link.
            url_match = re.search(r"https?://\S+", text)
            if url_match:
                return {"url": url_match.group(0).rstrip(".,;)]}\"'")}
            return {}
        # SYSTEM_CONTROL: để nguyên câu lệnh cho tool tự diễn giải.
        if label == IntentLabel.SYSTEM_CONTROL:
            return {"command": text}
            
        if label == IntentLabel.SYSTEM_TERMINAL:
            # Dùng LLM (bộ não hiện tại) để trích xuất lệnh shell/bash, tránh sai sót của regex
            prompt = (
                "Bạn là bộ trích xuất lệnh terminal. "
                f"Hãy đọc câu sau và trích xuất đúng câu lệnh (bash/cmd/powershell) mà người dùng muốn chạy: '{text}'\n"
                "CHỈ in ra nguyên văn câu lệnh, không giải thích thêm, không bọc trong markdown tick (```)."
            )
            # Gọi LLM (có fallback) để parse. max_tokens=200 là đủ cho một lệnh.
            try:
                res = self.router.run(
                    [{"role": "user", "content": prompt}], 
                    Intent(label=IntentLabel.SYSTEM_TERMINAL, tier=RouteTier.CLOUD, confidence=1.0, raw_text=text), 
                    max_tokens=200
                )
                cmd = res.output.strip() if res.ok else ""
                if cmd.startswith("```"):
                    cmd = "\n".join(cmd.split("\n")[1:-1]).strip()
                return {"command": cmd}
            except Exception:
                # Nếu LLM lỗi mạng/API, dự phòng lấy nguyên câu (executor sẽ hên xui)
                return {"command": text}
                
        return {}

    # ================================================================== #
    # STATE: ACT + OBSERVE
    # ================================================================== #
    def _act_and_observe(self, plan: Plan, text: str, trace: TurnTrace) -> str:
        """
        Thực thi Plan rồi quan sát kết quả. Vòng lặp có giới hạn re-plan.

        - Plan rỗng task -> gọi bộ não (đã gồm fallback bên trong Router).
        - Plan có task   -> dispatch qua registry; OBSERVE quyết định
                            thành công / cần-sửa / thất bại.
        """
        if plan.is_empty:
            return self._act_with_brain(plan.intent, text, trace)

        # VIBE DIFF gate (HITL): xin Sếp duyệt TRƯỚC khi chạy bất kỳ tool nào.
        gate = self._vibe_diff_gate(plan, trace)
        if gate is not None:
            return gate

        return self._run_tool_loop(plan, text, trace)

    def _run_tool_loop(self, plan: Plan, text: str, trace: TurnTrace) -> str:
        """Vòng ACT+OBSERVE thực thi tool (đã qua cổng VIBE DIFF)."""
        # SELF-REFLECTION: trước khi thực thi kỹ năng, truy vấn bài học cốt lõi
        # liên quan để tự điều chỉnh (biết đau -> biết nhớ -> biết sửa sai).
        lessons = self._recall_core_lessons(text)
        if lessons:
            trace.mark(AgentState.ACT, f"áp {len(lessons)} bài học cốt lõi")
            for _l in lessons:
                logger.info("[core_lesson] %s", _l[:140])
        # Tác vụ tool.
        for iteration in range(1, _MAX_REPLAN_ITERATIONS + 1):
            trace.mark(AgentState.ACT, f"vòng {iteration}")
            results = self._dispatch_tasks(plan, trace)

            trace.mark(AgentState.OBSERVE)
            if all(r.ok for r in results):
                trace.succeeded = True
                return self._summarize_tool_success(results)

            # Có task lỗi -> trạng thái "cần sửa". Thử lại trong giới hạn.
            failed = [r for r in results if not r.ok]
            trace.mark(AgentState.OBSERVE, f"cần sửa ({len(failed)} lỗi)")

            # KHÉP KÍN VÒNG TỰ CHẨN: mỗi tool fail -> gói lỗi, hỏi Claude, bắn đề
            # xuất ra UI cho Sếp duyệt. Bọc try/catch: việc chẩn lỗi mà nổ cũng
            # KHÔNG được làm sập luồng chính.
            self._diagnose_failures(failed, trace)

            if iteration >= _MAX_REPLAN_ITERATIONS:
                trace.succeeded = False
                return self._summarize_tool_failure(failed)

        # Không tới được, nhưng để mypy yên tâm.
        trace.succeeded = False
        return "Có lỗi không xác định khi xử lý tác vụ."

    def _vibe_diff_gate(self, plan: Plan, trace: TurnTrace) -> str | None:
        """
        Cổng phê duyệt VIBE DIFF. Trả None nếu mọi task được duyệt (chạy tiếp);
        trả chuỗi thông báo (và lưu _pending_plan) nếu cần chờ Sếp duyệt.
        """
        pending: list[str] = []
        for task in plan.tasks:
            if not task.arguments:
                continue  # thiếu tham số -> để _dispatch_tasks báo lỗi như cũ
            approved, message = self.vibe_diff.intercept(task.tool_name, task.arguments)
            if not approved:
                task.status = TaskStatus.NEEDS_APPROVAL
                pending.append(message)
        if pending:
            self._pending_plan = plan
            trace.mark(AgentState.ACT, "vibe-diff: chờ Sếp phê duyệt")
            return "\n\n".join(pending)
        return None

    def _resolve_pending_approval(self, text: str) -> str | None:
        """
        Xử lý câu trả lời của Sếp cho tác vụ đang chờ duyệt.
        Duyệt -> chạy plan đã lưu (bỏ qua cổng). Huỷ -> bỏ plan. Mơ hồ -> None.
        """
        plan = self._pending_plan
        if plan is None:
            return None
        if is_rejection(text):
            self._pending_plan = None
            return "Dạ vâng, em huỷ tác vụ vừa rồi nhé sếp."
        if is_approval(text):
            self._pending_plan = None
            trace = TurnTrace(user_text=text)
            trace.intent = plan.intent
            trace.mark(AgentState.ACT, "vibe-diff: ĐÃ DUYỆT, thực thi")
            response = self._run_tool_loop(plan, text, trace)
            trace.mark(AgentState.DONE if trace.succeeded else AgentState.FAILED)
            self._remember_turn(text, response)
            return response
        return None

    # ================================================================== #
    # ĐIỀU KHIỂN NĂNG LƯỢNG 2 CẤP (Vibe Diff: in xác nhận + chờ Sếp gõ 'Y')
    # ================================================================== #
    def _control_confirm_message(self, action: str) -> str:
        """Dòng xác nhận in ra Chat Window; chờ Sếp gõ 'Y' mới thực thi."""
        if action == "freeze":
            what = ("Em sẽ cho AURA NGỦ ĐÔNG — tạm dừng mọi nhịp chạy ngầm (đọc tin, "
                    "tự phản tỉnh, quét file) để nhường CPU/RAM cho Sếp. Chat vẫn mở để "
                    "Sếp gọi em dậy.")
        elif action == "unfreeze":
            what = "Em sẽ ĐÁNH THỨC AURA — cho các nhịp chạy ngầm hoạt động trở lại."
        elif action == "hibernate":
            what = ("Em sẽ cho LAPTOP NGỦ (đóng băng phần cứng Windows). Mọi thứ tạm dừng "
                    "cho tới khi Sếp bật máy lại.")
        else:
            what = "Em chưa rõ lệnh."
        return f"{VIBE_DIFF_PREFIX}: {what} Gõ 'Y' để xác nhận (hoặc 'không' để huỷ)."

    def _resolve_pending_control(self, text: str) -> str | None:
        """Xử lý câu trả lời Y/huỷ cho lệnh ngủ đông đang chờ. Mơ hồ -> None (rơi xuống)."""
        action = self._pending_control
        if action is None:
            return None
        if is_rejection(text):
            self._pending_control = None
            return "Dạ vâng, em huỷ lệnh vừa rồi nhé sếp."
        if is_approval(text):
            self._pending_control = None
            return self._execute_control(action)
        return None

    def _execute_control(self, action: str) -> str:
        """Thực thi lệnh điều khiển năng lượng SAU khi Sếp đã gõ 'Y'."""
        if action == "freeze":
            if self.daemon is not None and hasattr(self.daemon, "freeze_aura"):
                self.daemon.freeze_aura()
                return ("💤 AURA đã ngủ đông: dừng mọi nhịp chạy ngầm, nhường CPU/RAM cho "
                        "Sếp. Chat vẫn mở — nói 'aura thức dậy' khi cần em làm tiếp.")
            return ("Em sẵn sàng ngủ đông nhưng phiên này chưa gắn được daemon nền "
                    "(có thể đang chạy chế độ terminal).")
        if action == "unfreeze":
            if self.daemon is not None and hasattr(self.daemon, "unfreeze_aura"):
                self.daemon.unfreeze_aura()
                return "☀️ AURA đã thức dậy: các nhịp chạy ngầm hoạt động lại bình thường."
            return "Em chưa gắn được daemon nền nên không có gì để đánh thức ở phiên này."
        if action == "hibernate":
            if self.registry is not None and self.registry.has("system.power"):
                try:
                    if hasattr(self.registry, "execute_tool"):
                        res = self.registry.execute_tool("system.power", {})
                    else:
                        res = self.registry.dispatch(Task(tool_name="system.power", arguments={}))
                except Exception as exc:  # noqa: BLE001 — gọi skill nổ không được làm sập lượt
                    return f"Không cho máy ngủ được: {exc}"
                if getattr(res, "ok", False):
                    return res.output
                return f"Không cho máy ngủ được: {getattr(res, 'error', '?')}"
            return "Chưa lắp skill 'system.power' nên em chưa cho laptop ngủ được, sếp ạ."
        return "Lệnh điều khiển không rõ."

    # ================================================================== #
    # TRIAD COUNCIL — triệu tập Hội đồng viết tool (Human Gate qua chat)
    # ================================================================== #
    def _start_council(self, text: str) -> str:
        """Khởi chạy một phiên Hội đồng trên event loop của server (không chặn lượt chat)."""
        if self.council is None or self.loop is None:
            return "Hội đồng chưa lắp ở phiên này (chỉ chạy khi khởi động qua main.py)."
        instruction = re.sub(
            r"^(hội đồng|hoi dong|triệu tập hội đồng|trieu tap hoi dong|viết tool|viet tool)"
            r"\s*[:\-]?\s*", "", text, flags=re.IGNORECASE).strip()
        if not instruction:
            return ("Sếp cho em nội dung cần Hội đồng viết, vd: "
                    "'hội đồng: viết script tính số nguyên tố thứ n'.")
        import time as _t
        task = {"task_id": int(_t.time()) % 100000, "instruction": instruction}

        def _done(fut) -> None:
            if self.council_bridge is not None:
                self.council_bridge.mark_done()
            try:
                r = fut.result()
            except Exception as exc:  # noqa: BLE001
                r = {"status": "ERR", "attempts": "?", "error_log": str(exc)}
            if self.event_queue is not None:
                try:
                    self.event_queue.put_nowait({
                        "type": "proactive",
                        "text": (f"🧠 Hội đồng task #{task['task_id']}: {r.get('status')} "
                                 f"(vòng {r.get('attempts', '?')})."),
                    })
                except Exception:  # noqa: BLE001
                    pass

        import asyncio as _a
        # Đánh dấu "đang viết" TRƯỚC khi chạy để Sếp gõ 'Y' sớm được trả lời đúng (không lọt chat).
        if self.council_bridge is not None:
            self.council_bridge.mark_started()
        try:
            fut = _a.run_coroutine_threadsafe(self.council.master_deliberate(task), self.loop)
            fut.add_done_callback(_done)
        except Exception as exc:  # noqa: BLE001 — không triệu tập được không làm sập lượt
            if self.council_bridge is not None:
                self.council_bridge.mark_done()
            return f"Không triệu tập được Hội đồng: {exc}"
        return (f"Đã triệu tập Hội đồng cho task #{task['task_id']}. Em sẽ trình code ra để "
                "Sếp nghiệm thu (gõ 'Y' hoặc 'không, lý do') khi viết xong.")

    # ================================================================== #
    # CẬP NHẬT CHÂN DUNG SẾP (Vibe Diff: in xác nhận + chờ Sếp gõ 'Y')
    # ================================================================== #
    def _profile_confirm_message(self, update: dict) -> str:
        """Dòng xác nhận in ra Chat Window; chờ Sếp gõ 'Y' mới ghi vào hồ sơ."""
        return (f"{VIBE_DIFF_PREFIX}: Em sẽ ghi vào Chân dung Sếp — "
                f"[{update['label']}] {update['text']}. "
                f"Gõ 'Y' để xác nhận (hoặc 'không' để huỷ).")

    def _resolve_pending_profile(self, text: str) -> str | None:
        """Xử lý Y/huỷ cho cập nhật hồ sơ đang chờ. Mơ hồ -> None (rơi xuống luồng thường)."""
        update = self._pending_profile
        if update is None:
            return None
        if is_rejection(text):
            self._pending_profile = None
            return "Dạ vâng, em không ghi vào hồ sơ nữa nhé sếp."
        if is_approval(text):
            self._pending_profile = None
            return self._apply_profile_update(update)
        return None

    def _apply_profile_update(self, update: dict) -> str:
        """Ghi vào user_profile.json (nguồn sự thật) rồi đồng bộ ChromaDB. SAU khi Sếp gõ 'Y'."""
        if self.profile is None:
            return "Em chưa mở được hồ sơ Chân dung Sếp ở phiên này nên chưa ghi được."
        cat = update["category"]
        content = update["text"]
        key = _profile_key(content)
        try:
            if cat == "goal":
                self.profile.add_goal(key, content)
            elif cat == "habit":
                self.profile.add_habit(key, content, kind=update.get("kind", "good"))
            else:
                self.profile.note_weakness(key, content)
            # Đồng bộ ChromaDB (tái dùng MemoryStore sẵn có); lỗi sync KHÔNG chặn việc lưu JSON.
            try:
                self.profile.sync_to_memory(memory=self.memory)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Sync profile -> ChromaDB lỗi (đã lưu JSON): %s", exc)
            return f"✅ Đã ghi vào Chân dung Sếp — [{update['label']}] {content}."
        except Exception as exc:  # noqa: BLE001 — ghi hồ sơ lỗi không được làm sập lượt
            logger.warning("Ghi profile lỗi: %s", exc)
            return f"Xin lỗi sếp, em ghi hồ sơ chưa được: {exc}"

    def _diagnose_failures(self, failed: list[ToolResult], trace: TurnTrace) -> None:
        """
        Với mỗi ToolResult thất bại: gọi SelfDiagnose để gói lỗi, hỏi Claude và bắn
        đề xuất sửa ra UI (qua event_queue) cho Sếp duyệt.

        Toàn bộ bọc try/catch: nếu bản thân việc chẩn lỗi nổ (mất mạng, thiếu key,
        queue đóng...) thì NUỐT lỗi đó — luồng chính tuyệt đối không được sập chỉ
        vì khâu chẩn đoán phụ trợ.
        """
        for result in failed:
            try:
                diag = self.diagnoser.diagnose_tool_result(
                    result, context=f"intent={trace.intent.label.value if trace.intent else '?'}"
                )
                trace.mark(
                    AgentState.OBSERVE,
                    f"diagnose {result.tool_name}: {'ok' if diag.ok else 'không hỏi được đàn anh'}",
                )
            except Exception as exc:  # noqa: BLE001 — chẩn lỗi nổ cũng không được làm sập
                logger.warning("SelfDiagnose lỗi cho '%s' (bỏ qua): %s",
                               result.tool_name, exc)

    def _act_with_brain(self, intent: Intent, text: str, trace: TurnTrace) -> str:
        """Act cho nhãn brain: dựng system prompt giàu ngữ cảnh rồi gọi Router.run()."""
        trace.mark(AgentState.ACT, "brain")
        system_prompt = self._build_system_prompt(intent, text)
        messages = self._history + [{"role": "user", "content": text}]

        # Câu KHÓ -> bật tầng tư duy (lập kế hoạch + tự phản biện). Câu thường -> 1 phát.
        if self.deliberate_enabled and intent.label in _DELIBERATE_LABELS:
            deliberated = self._deliberate_answer(intent, text, system_prompt, trace)
            if deliberated is not None:
                trace.succeeded = True
                return deliberated

        result = self.router.run(messages, intent, system_prompt=system_prompt, max_tokens=2048)
        self._record_metric("brain", result.ok, getattr(result, "elapsed_ms", 0))

        trace.mark(AgentState.OBSERVE, result.tool_name)
        if result.ok:
            trace.succeeded = True
            return result.output
        trace.succeeded = False
        return (
            "Xin lỗi sếp, cả bộ não local lẫn cloud đều không phản hồi được lúc này. "
            f"(Chi tiết: {result.error})"
        )

    def _dispatch_tasks(self, plan: Plan, trace: TurnTrace) -> list[ToolResult]:
        """Gửi từng Task tới registry. Chưa lắp registry -> báo cáo trung thực."""
        results: list[ToolResult] = []
        for task in plan.tasks:
            if not task.arguments:
                task.status = TaskStatus.FAILED
                results.append(
                    ToolResult.failure(
                        task.tool_name,
                        "Thiếu tham số (vd: chưa rõ số chương, hoặc chưa có link http(s) "
                        "trực tiếp để tải). Sếp nói rõ hơn giúp em.",
                    )
                )
                continue

            if self.registry is None or not self.registry.has(task.tool_name):
                task.status = TaskStatus.FAILED
                results.append(
                    ToolResult.failure(
                        task.tool_name,
                        f"Công cụ '{task.tool_name}' chưa được lắp ở phiên này.",
                    )
                )
                continue

            task.status = TaskStatus.RUNNING
            result = self.registry.dispatch(task)
            task.status = TaskStatus.SUCCEEDED if result.ok else TaskStatus.FAILED
            self._record_metric(task.tool_name, result.ok, getattr(result, "elapsed_ms", 0))
            results.append(result)
        return results

    def _deliberate_answer(self, intent: Intent, text: str, system_prompt: str,
                           trace: TurnTrace) -> str | None:
        """
        Tầng tư duy cho câu khó: lập kế hoạch -> nháp -> tự phản biện -> viết lại.
        Trả câu trả lời cuối, hoặc None nếu hỏng (caller fallback 1-phát).
        """
        try:
            from core.deliberate import deliberate

            def _complete(prompt: str, system: str) -> str:
                res = self.router.run(
                    [{"role": "user", "content": prompt}], intent, system_prompt=system, max_tokens=2048
                )
                self._record_metric("brain", res.ok, getattr(res, "elapsed_ms", 0))
                return res.output if res.ok else ""

            trace.mark(AgentState.ACT, "deliberate: lập kế hoạch + tự phản biện")
            out = deliberate(text, _complete, system_prompt=system_prompt, max_critiques=1)
            ans = (out or {}).get("answer", "").strip()
            if ans:
                trace.mark(AgentState.OBSERVE, f"deliberate xong ({out.get('passes',0)} vòng sửa)")
                return ans
        except Exception as exc:  # noqa: BLE001 — tư duy hỏng -> fallback 1 phát
            logger.warning("Deliberation lỗi, fallback đơn: %s", exc)
        return None

    # ================================================================== #
    # Dựng prompt giàu ngữ cảnh (yêu cầu #4: giữ ngữ cảnh)
    # ================================================================== #
    # Hỏi về công việc nhà máy (truyện/video AURA tự làm) -> nhồi trạng thái thật
    # vào system prompt để AURA KHÔNG chối "không có truyện nào".
    _FACTORY_HINTS = (
        "truyện", "chương", "viết", "video", "nhà máy", "xưởng", "công việc",
        "đăng", "wattpad", "youtube", "sáng tác", "kể chuyện", "kit", "bộ ", "đấu la",
    )

    def _factory_awareness(self, text: str) -> str:
        """Tóm tắt việc nhà máy ĐÃ/ĐANG làm (truyện/video/job) — chỉ nhồi khi câu hỏi
        có dính tới. Lỗi gì cũng -> '' (không sập lượt chat)."""
        low = text.lower()
        if not any(h in low for h in self._FACTORY_HINTS):
            return ""
        import json as _json
        from core.config import settings
        lines: list[str] = []
        try:
            story_root = settings.outputs_dir / "story"
            info = []
            if story_root.exists():
                for d in sorted(story_root.iterdir()):
                    if not (d.is_dir() and (d / "bible.json").exists()):
                        continue
                    try:
                        title = _json.loads((d / "bible.json").read_text(
                            encoding="utf-8")).get("title") or d.name
                    except Exception:  # noqa: BLE001
                        title = d.name
                    n = len(list((d / "chapters").glob("ch_*.md"))) \
                        if (d / "chapters").exists() else 0
                    kit = "đã có bộ kit đăng" if (d / "publish_kit" / "van_an.md").exists() \
                        else "chưa có kit"
                    info.append(f"'{title}' — {n} chương, {kit} "
                                f"(thư mục data/outputs/story/{d.name}/)")
            if info:
                lines.append("TRUYỆN AURA ĐÃ TỰ VIẾT: " + "; ".join(info))
        except Exception:  # noqa: BLE001
            pass
        try:
            vroot = settings.outputs_dir / "story_video"
            vids = list(vroot.glob("*/*/*.mp4")) if vroot.exists() else []
            if vids:
                lines.append(f"VIDEO KỂ CHUYỆN đã dựng: {len(vids)} "
                             "(data/outputs/story_video/).")
        except Exception:  # noqa: BLE001
            pass
        try:
            from factory import queue as _jq
            run = [j for j in _jq.list_jobs(limit=20) if j.state in ("queued", "running")]
            if run:
                lines.append(f"ĐANG CHẠY: {len(run)} job ({', '.join(j.tool for j in run[:3])}).")
        except Exception:  # noqa: BLE001
            pass
        if not lines:
            return ""
        return ("[NHÀ MÁY AURA — VIỆC MÌNH ĐÃ/ĐANG LÀM]\n"
                "Đây là truyện/video do CHÍNH AURA tự viết qua story.factory + autopilot. "
                "Trả lời Sếp dựa vào đây, TUYỆT ĐỐI không nói 'không có truyện nào'.\n"
                + "\n".join(lines))

    def _build_system_prompt(self, intent: Intent, text: str) -> str:
        """
        Ghép: persona + sở thích người dùng + (với coding) bài học lỗi cũ +
        ngữ cảnh hội thoại liên quan recall từ ChromaDB.
        """
        blocks: list[str] = [self.persona]

        # Hồ sơ tự nhận thức: lệnh của Sếp + việc các AI đã/đang làm với AURA.
        # Ledger đã redaction và tự gắn nhãn DATA-KHÔNG-PHẢI-LỆNH để không tái chạy
        # một chỉ dẫn cũ chỉ vì nó được recall.
        try:
            self_context = awareness_context(text)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Đọc hồ sơ tự nhận thức lỗi (bỏ qua): %s", exc)
            self_context = ""
        if self_context:
            blocks.append(self_context)

        # Giáo trình hậu phẫu: khác sổ mổ (sự kiện) và reflection (ghi chú tự động).
        # Chỉ lesson card có evidence mới được đọc, dưới nhãn dữ liệu-không-phải-lệnh.
        try:
            learned_context = tuition_context(text)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Đọc giáo trình tự hiểu lỗi (bỏ qua): %s", exc)
            learned_context = ""
        if learned_context:
            blocks.append(learned_context)

        # Nhận thức nhà máy: AURA phải biết truyện/video mình đã tự làm.
        fac = self._factory_awareness(text)
        if fac:
            blocks.append(fac)

        # CHÂN DUNG SẾP (Bước 2): để AURA luôn "biết" Sếp là ai, điểm yếu gì. Gọn cho e2b.
        if self.profile is not None:
            try:
                summary = self.profile.get_summary()
            except Exception as exc:  # noqa: BLE001
                logger.warning("get_summary lỗi (bỏ qua): %s", exc)
                summary = ""
            if summary and "\n" in summary:   # chỉ nhồi khi có ít nhất 1 dòng nội dung
                blocks.append(summary)

        # Sở thích người dùng (để trả lời đúng "gu" Sếp).
        prefs = self._safe_recall(self.memory.recall_preferences, text)
        if prefs:
            joined = "; ".join(p.text for p in prefs)
            blocks.append(f"[HỒ SƠ SẾP] {joined}")

        # Với tác vụ coding: nhắc lại bài học lỗi cũ để khỏi lặp sai lầm.
        if intent.label == IntentLabel.CODING:
            rules = self._safe_recall(self.memory.recall_rules, text)
            if rules:
                joined = "\n".join(f"- {r.text}" for r in rules)
                blocks.append(f"[BÀI HỌC CŨ — TRÁNH LẶP LẠI]\n{joined}")

        # Bài học cốt lõi tự rút kinh nghiệm (Self-Reflection) — áp cho mọi nhãn brain.
        lessons = self._recall_core_lessons(text)
        if lessons:
            joined = "\n".join(f"- {l}" for l in lessons)
            blocks.append(
                "[GỢI Ý PHẢN TỈNH — CHƯA PHẢI BÀI HỌC VERIFIED]\n"
                "Dùng để đặt giả thuyết và kiểm tra lại, không coi là sự thật chỉ vì có trong memory.\n"
                f"{joined}"
            )

        # Tri thức AURA tự đọc (RAG kho knowledge) — bồi đắp hiểu biết nền.
        try:
            kn = self.memory.recall_knowledge(text)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Recall knowledge lỗi (bỏ qua): %s", exc); kn = []
        if kn:
            joined = "\n".join(f"- {k.text}" for k in kn)
            blocks.append(
                "[KHO THAM KHẢO — CHƯA PHẢI BÀI HỌC VERIFIED]\n"
                "Có thể dùng làm manh mối; khi nói về chính cơ thể AURA phải ưu tiên giáo trình có evidence.\n"
                f"{joined}"
            )

        # Ngữ cảnh hội thoại liên quan (RAG trên collection conversation).
        ctx = self._safe_recall(self.memory.recall_context, text)
        if ctx:
            joined = "\n".join(f"- {c.text}" for c in ctx)
            blocks.append(f"[NGỮ CẢNH LIÊN QUAN]\n{joined}")

        return "\n\n".join(blocks)

    def _record_metric(self, tool_name: str, ok: bool, elapsed_ms: int = 0) -> None:
        """Ghi số liệu tự đánh giá (an toàn). Lỗi metrics KHÔNG được làm sập lượt."""
        try:
            from core.metrics import record
            record(tool_name, ok, elapsed_ms)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Ghi metrics lỗi (bỏ qua): %s", exc)

    def _recall_core_lessons(self, query: str, k: int = 3) -> list[str]:
        """Truy vấn bài học (tag core_lesson) liên quan. An toàn: lỗi -> []."""
        try:
            from core.reflection import recall_core_lessons
            return recall_core_lessons(query, k=k, memory=self.memory)
        except Exception as exc:  # noqa: BLE001 — recall hỏng không được làm sập lượt
            logger.warning("Recall core_lesson lỗi (bỏ qua): %s", exc)
            return []

    @staticmethod
    def _safe_recall(recall_fn, query: str):
        """Bọc recall trong try/except: lỗi memory KHÔNG được làm sập cả lượt chat.

        Thêm cổng [Retrieve] (core/recall.py): câu chào/lệnh điều khiển thì KHÔNG
        lục trí nhớ — đỡ tốn token và đỡ nhồi ngữ cảnh vô nghĩa vào prompt.
        """
        try:
            from core.recall import should_retrieve
            if not should_retrieve(query):
                return []
        except Exception:  # noqa: BLE001 — thiếu module thì cứ lục như cũ
            pass
        try:
            return recall_fn(query)
        except Exception as exc:  # noqa: BLE001 — cố tình nuốt để giữ độ bền
            logger.warning("Recall memory lỗi (bỏ qua ngữ cảnh): %s", exc)
            return []

    # ================================================================== #
    # Lưu buffer hội thoại (RAM + ChromaDB)
    # ================================================================== #
    def _remember_turn(self, user_text: str, assistant_text: str) -> None:
        """Lưu lượt hội thoại vào cả buffer RAM lẫn ChromaDB (collection conversation)."""
        # RAM buffer — cắt bớt cho gọn context (phần cứng yếu, giảm context window).
        self._history.append({"role": "user", "content": user_text})
        self._history.append({"role": "assistant", "content": assistant_text})
        if len(self._history) > _HISTORY_MAX_MESSAGES:
            self._history = self._history[-_HISTORY_MAX_MESSAGES:]

        # ChromaDB — bền vững, để recall theo relevance ở các lượt sau.
        try:
            self.memory.remember_turn("user", user_text)
            self.memory.remember_turn("assistant", assistant_text)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Lưu memory thất bại (bỏ qua): %s", exc)

    def _remember_avatar_turn(self, user_text: str, assistant_text: str) -> None:
        """Giữ ngữ cảnh riêng cho phân thân điện thoại và vẫn bồi vào trí nhớ AURA."""
        self._avatar_history.append({"role": "user", "content": user_text})
        self._avatar_history.append({"role": "assistant", "content": assistant_text})
        if len(self._avatar_history) > _HISTORY_MAX_MESSAGES:
            self._avatar_history = self._avatar_history[-_HISTORY_MAX_MESSAGES:]
        try:
            self.memory.remember_turn("user", f"[AURA Avatar] {user_text}")
            self.memory.remember_turn("assistant", f"[AURA Avatar] {assistant_text}")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Lưu memory AURA Avatar thất bại (bỏ qua): %s", exc)

    # ================================================================== #
    # Tóm tắt kết quả tool
    # ================================================================== #
    @staticmethod
    def _summarize_tool_success(results: list[ToolResult]) -> str:
        parts = [r.output for r in results if r.output]
        artifacts = [a for r in results for a in r.artifacts]
        msg = "\n".join(parts) if parts else "Xong rồi sếp."
        if artifacts:
            msg += "\n\nFile kết quả:\n" + "\n".join(f"- {a}" for a in artifacts)
        return msg

    @staticmethod
    def _summarize_tool_failure(failed: list[ToolResult]) -> str:
        lines = [f"- {r.tool_name}: {r.error}" for r in failed]
        return "Tác vụ chưa xong, sếp ạ:\n" + "\n".join(lines)


__all__ = [
    "AURA_Orchestrator",
    "AgentState",
    "TurnTrace",
    "ToolRegistryProtocol",
    "extract_manga_target",
    "_iron_rule_label",
]
