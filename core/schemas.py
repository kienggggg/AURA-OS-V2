"""
core/schemas.py
===============
Hợp đồng dữ liệu (data contracts) cho toàn bộ AURA 2.0.

Triết lý: Mọi thành phần (Daemon, Router, các Agent, Tool, Memory) giao tiếp
với nhau bằng các đối tượng pydantic có cấu trúc nghiêm ngặt — KHÔNG bằng
text tự do hay regex tag surgery như kiến trúc cũ. Nếu một thành phần trả về
JSON sai cấu trúc, pydantic sẽ raise ValidationError ngay tại biên, thay vì để
lỗi âm thầm lan vào sâu trong hệ thống.

Đây là module nền: nó KHÔNG được phép import bất kỳ module nội bộ nào khác của
AURA (tránh phụ thuộc vòng). Chỉ chuẩn thư viện + pydantic.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ---------------------------------------------------------------------------
# Tiện ích chung
# ---------------------------------------------------------------------------
def _utcnow() -> datetime:
    """Trả về thời điểm hiện tại theo UTC, luôn có tzinfo (tránh naive datetime)."""
    return datetime.now(timezone.utc)


def _new_id() -> str:
    """Sinh một ID ngắn, duy nhất, dùng để truy vết message/task qua các tầng."""
    return uuid.uuid4().hex[:12]


class _StrictModel(BaseModel):
    """
    Lớp cơ sở cho mọi schema trong AURA.

    - `extra="forbid"`: cấm field lạ → bắt sớm lỗi typo hoặc output LLM bịa thêm khoá.
    - `validate_assignment=True`: gán lại thuộc tính cũng được validate.
    - `use_enum_values=False`: giữ nguyên Enum để so sánh an toàn theo type.
    """

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        use_enum_values=False,
    )


# ---------------------------------------------------------------------------
# 1. Phân loại Intent  (đầu ra của System 1 — Local brain)
# ---------------------------------------------------------------------------
class IntentLabel(str, Enum):
    """Nhãn ý định người dùng. Router dựa vào đây để phân luồng System 1 / System 2."""

    CHITCHAT = "chitchat"            # tán gẫu, trả lời ngay bằng local brain
    SYSTEM_CONTROL = "system_control"  # điều khiển OS: mở app, dọn đĩa, tắt tiến trình
    WEB_SCRAPE = "web_scrape"        # cào web / tìm tài liệu
    JOB_SCOUT = "job_scout"          # săn việc làm / tuyển dụng
    KNOWLEDGE_INGEST = "knowledge_ingest"  # tự đọc tài liệu & ghi nhớ (RAG)
    MANGA_DOWNLOAD = "manga_download"  # tải chapter truyện
    MANGA_TRANSLATE = "manga_translate"  # dịch chapter đã tải
    VIDEO_DOWNLOAD = "video_download"  # tải video/file từ URL trực tiếp (skill AURA tự viết)
    CODING = "coding"                # viết/sửa code → đẩy lên System 2
    HEAVY_REASONING = "heavy_reasoning"  # phân tích sâu → System 2
    MEMORY_QUERY = "memory_query"    # hỏi về ký ức đã lưu
    SYSTEM_TERMINAL = "system_terminal"  # chạy lệnh terminal/shell
    UNKNOWN = "unknown"              # không phân loại được → hỏi lại người dùng


class RouteTier(str, Enum):
    """Cấp xử lý: phản xạ cục bộ (System 1) hay suy luận sâu trên cloud (System 2)."""

    LOCAL = "local"    # Ollama (Gemma/Phi-3)
    CLOUD = "cloud"    # Claude qua API


class Intent(_StrictModel):
    """Kết quả phân loại ý định cho một câu input của người dùng."""

    label: IntentLabel = Field(..., description="Nhãn ý định đã phân loại.")
    tier: RouteTier = Field(..., description="Cấp xử lý được chọn cho intent này.")
    confidence: float = Field(
        ..., ge=0.0, le=1.0, description="Độ tự tin của bộ phân loại, 0..1."
    )
    reason: str = Field(
        default="", description="Giải thích ngắn vì sao chọn nhãn/cấp này (để debug)."
    )
    raw_text: str = Field(..., description="Câu input gốc của người dùng.")


# ---------------------------------------------------------------------------
# 2. Tham số Manga  (thay cho việc bóc tham số bằng regex text tự do)
# ---------------------------------------------------------------------------
class MangaTarget(_StrictModel):
    """
    Tham số chuẩn hoá cho tác vụ tải/dịch manga.

    Sửa lỗi gốc của hệ cũ: số chương được lưu dạng `float` (10.5, 25.5 hợp lệ),
    KHÔNG ép `int()` để khỏi chết với chương lẻ.
    """

    title: str = Field(..., min_length=1, description="Tên truyện.")
    chapter: float = Field(
        ..., gt=0, description="Số chương (cho phép số lẻ như 10.5)."
    )

    @field_validator("title")
    @classmethod
    def _strip_title(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Tên truyện không được rỗng.")
        return cleaned

    @property
    def chapter_label(self) -> str:
        """
        Chuỗi tên chương dùng đặt tên thư mục: 'chapter_010' hoặc 'chapter_010_5'.
        Giữ phần thập phân khi có (10.5 → '010_5'), bỏ '.0' thừa khi là số nguyên.
        """
        if self.chapter.is_integer():
            return f"chapter_{int(self.chapter):03d}"
        whole, frac = str(self.chapter).split(".")
        return f"chapter_{int(whole):03d}_{frac}"


# ---------------------------------------------------------------------------
# 3. Task & Plan  (đầu ra khâu lập kế hoạch của Orchestrator)
# ---------------------------------------------------------------------------
class TaskStatus(str, Enum):
    """Vòng đời của một Task trong state machine của orchestrator."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    NEEDS_APPROVAL = "needs_approval"  # chờ người duyệt (vd: tool tự sinh)


class Task(_StrictModel):
    """Một đơn vị công việc khả thi: 'gọi tool X với tham số Y'."""

    id: str = Field(default_factory=_new_id)
    tool_name: str = Field(..., description="Tên tool sẽ được dispatch qua ToolRegistry.")
    arguments: dict[str, Any] = Field(
        default_factory=dict, description="Tham số truyền vào tool (đã chuẩn hoá)."
    )
    status: TaskStatus = Field(default=TaskStatus.PENDING)
    depends_on: list[str] = Field(
        default_factory=list, description="Danh sách id task phải xong trước."
    )
    created_at: datetime = Field(default_factory=_utcnow)


class Plan(_StrictModel):
    """Chuỗi Task có thứ tự mà orchestrator sinh ra để giải quyết một intent."""

    intent: Intent
    tasks: list[Task] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_utcnow)

    @property
    def is_empty(self) -> bool:
        return len(self.tasks) == 0


# ---------------------------------------------------------------------------
# 4. ToolResult  (đầu ra chuẩn của mọi tool)
# ---------------------------------------------------------------------------
class ToolResult(_StrictModel):
    """
    Kết quả trả về thống nhất cho mọi tool. Tool KHÔNG raise exception ra ngoài;
    nó bắt lỗi và gói vào đây để orchestrator quyết định retry / fallback System 2.
    """

    ok: bool = Field(..., description="True nếu tool chạy thành công.")
    tool_name: str
    output: str = Field(default="", description="Nội dung kết quả (dạng text cho LLM đọc).")
    error: str | None = Field(default=None, description="Mô tả lỗi nếu ok=False.")
    artifacts: list[str] = Field(
        default_factory=list, description="Đường dẫn file sinh ra (ảnh, PDF, CBZ...)."
    )
    elapsed_ms: int = Field(default=0, ge=0, description="Thời gian chạy (ms).")

    @classmethod
    def success(
        cls,
        tool_name: str,
        output: str = "",
        artifacts: list[str] | None = None,
        elapsed_ms: int = 0,
    ) -> "ToolResult":
        return cls(
            ok=True,
            tool_name=tool_name,
            output=output,
            artifacts=artifacts or [],
            elapsed_ms=elapsed_ms,
        )

    @classmethod
    def failure(cls, tool_name: str, error: str, elapsed_ms: int = 0) -> "ToolResult":
        return cls(ok=False, tool_name=tool_name, error=error, elapsed_ms=elapsed_ms)


# ---------------------------------------------------------------------------
# 5. AgentMessage  (giao thức "5 bộ mặt Quintessa" — message passing)
# ---------------------------------------------------------------------------
class AgentRole(str, Enum):
    """Năm khuôn mặt của Quintessa + người dùng."""

    USER = "user"
    ROUTER = "router"          # ý thức trung tâm
    SYSTEM_AGENT = "system_agent"  # thực thi cứng (OS control)
    CODER_AGENT = "coder_agent"    # tiến hóa (viết code)
    WEB_AGENT = "web_agent"        # cào tri thức
    MEMORY = "memory"

    
class AgentMessage(_StrictModel):
    """
    Phong bì chuẩn cho mọi liên lạc giữa các agent.

    Thay thế hoàn toàn cơ chế nhét tag `<translate_manga>...</translate_manga>`
    vào text rồi bóc bằng regex. Mọi thứ giờ là JSON có validate.
    """

    id: str = Field(default_factory=_new_id)
    sender: AgentRole
    receiver: AgentRole
    action: str = Field(..., description="Hành động yêu cầu, vd: 'clean_disk'.")
    parameters: dict[str, Any] = Field(default_factory=dict)
    payload: str = Field(default="", description="Nội dung text kèm theo (nếu có).")
    correlation_id: str | None = Field(
        default=None,
        description="ID để nối request↔response qua nhiều chặng (trace luồng).",
    )
    timestamp: datetime = Field(default_factory=_utcnow)

    def reply(
        self,
        action: str,
        parameters: dict[str, Any] | None = None,
        payload: str = "",
    ) -> "AgentMessage":
        """Tạo message trả lời, tự đảo sender/receiver và giữ correlation_id."""
        return AgentMessage(
            sender=self.receiver,
            receiver=self.sender,
            action=action,
            parameters=parameters or {},
            payload=payload,
            correlation_id=self.correlation_id or self.id,
        )


# ---------------------------------------------------------------------------
# 6. MemoryRecord  (đơn vị ghi vào ChromaDB)
# ---------------------------------------------------------------------------
class MemoryRecord(_StrictModel):
    """Một mẩu ký ức lưu vào ChromaDB, kèm metadata để truy vấn theo role/thời gian."""

    id: str = Field(default_factory=_new_id)
    role: Literal["user", "assistant", "system", "feedback"] = Field(
        ..., description="Nguồn của mẩu ký ức."
    )
    text: str = Field(..., min_length=1)
    timestamp: datetime = Field(default_factory=_utcnow)
    tags: list[str] = Field(default_factory=list)

    def to_chroma_metadata(self) -> dict[str, Any]:
        """
        ChromaDB metadata chỉ nhận kiểu vô hướng (str/int/float/bool).
        Hàm này ép datetime→ISO string và list[str]→chuỗi nối, để lưu an toàn.
        """
        return {
            "role": self.role,
            "timestamp": self.timestamp.isoformat(),
            "tags": ",".join(self.tags),
        }


__all__ = [
    "IntentLabel",
    "RouteTier",
    "Intent",
    "MangaTarget",
    "TaskStatus",
    "Task",
    "Plan",
    "ToolResult",
    "AgentRole",
    "AgentMessage",
    "MemoryRecord",
]
