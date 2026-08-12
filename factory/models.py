"""
factory/models.py
==================
Kiểu dữ liệu dùng chung cho xưởng: ToolSpec (mô tả 1 tool kiếm tiền, đủ để
dashboard TỰ RENDER form không cần code HTML riêng cho từng tool) và JobRecord
(1 lượt chạy của tool, lưu trong sqlite qua factory.queue).
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Literal

# Trạng thái vòng đời của một job trong hàng đợi.
JobState = Literal["queued", "running", "done", "needs_review", "failed", "cancelled"]

# Loại field trên form launcher — dashboard map trực tiếp sang <input>/<select>.
FieldType = Literal["text", "textarea", "file", "number", "select", "checkbox"]


class JobCancelled(Exception):
    """Handler ném ra khi phát hiện user đã bấm Hủy (queue.is_cancelled) — worker
    bắt riêng để giữ state 'cancelled' thay vì 'failed'."""


@dataclass(frozen=True)
class FormField:
    """Một ô nhập trên form launcher của dashboard."""

    key: str
    label: str
    type: FieldType = "text"
    default: Any = ""
    required: bool = True
    choices: tuple[str, ...] = ()  # dùng khi type="select"
    placeholder: str = ""
    help_text: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key, "label": self.label, "type": self.type,
            "default": self.default, "required": self.required,
            "choices": list(self.choices), "placeholder": self.placeholder,
            "help_text": self.help_text,
        }


@dataclass(frozen=True)
class ToolSpec:
    """
    Mô tả tĩnh một tool kiếm tiền — KHÔNG chứa logic chạy, chỉ metadata + tay
    cầm tới handler. Đăng ký trong factory/tools/__init__.py: TOOL_REGISTRY.
    """

    name: str                      # vd "video.factory" — id ổn định, dùng làm khoá
    label_vi: str                  # tên hiển thị tiếng Việt trên dashboard
    description: str
    product_line: str              # "video" | "novel" | "comic" | "cv" | "excel" | "content"
    form_fields: tuple[FormField, ...]
    handler: Callable[..., "JobRecord"] | None = None  # gán ở factory/tools/*
    experimental: bool = False      # true = hiện badge "THÍ NGHIỆM" trên dashboard
    enabled: bool = True            # false = hiện mờ "sắp có" (đợt 2)

    def to_dict(self) -> dict[str, Any]:
        """JSON-safe cho GET /api/tools — bỏ `handler` (không serialize được)."""
        return {
            "name": self.name, "label_vi": self.label_vi, "description": self.description,
            "product_line": self.product_line,
            "form_fields": [f.to_dict() for f in self.form_fields],
            "experimental": self.experimental, "enabled": self.enabled,
        }


@dataclass
class JobRecord:
    """Một lượt chạy cụ thể của một ToolSpec — lưu bền trong sqlite."""

    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    tool: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    state: JobState = "queued"
    progress: int = 0               # 0..100
    step: str = "Đang chờ trong hàng đợi"
    artifacts_dir: str = ""
    qc_path: str = ""
    error: str = ""
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    finished_at: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "tool": self.tool,
            "params": self.params,
            "state": self.state,
            "progress": self.progress,
            "step": self.step,
            "artifacts_dir": self.artifacts_dir,
            "qc_path": self.qc_path,
            "error": self.error,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "JobRecord":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


__all__ = ["FormField", "ToolSpec", "JobRecord", "JobState", "FieldType", "JobCancelled"]
