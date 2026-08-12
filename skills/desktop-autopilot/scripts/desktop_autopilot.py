"""AURA skill entrypoint for the local Desktop Autopilot."""

from __future__ import annotations

import json
from typing import Any

from core.config import settings
from core.desktop_autopilot import get_runtime_autopilot
from core.schemas import ToolResult


def _actions(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, str):
        value = json.loads(value)
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise TypeError("actions phải là list object.")
    return value


def desktop_autopilot(
    action: str = "status",
    *,
    query: str = "",
    paths: list[str] | None = None,
    include_ocr: bool = False,
    title: str = "",
    scope: str = "local_ui",
    actions: Any = None,
    expected_window_keywords: list[str] | None = None,
) -> ToolResult:
    """Inspect context, queue a safe desktop task, or run the next queued task."""
    autopilot = get_runtime_autopilot()
    action = str(action or "status").strip().lower()
    try:
        if action == "status":
            payload = autopilot.status()
        elif action == "observe":
            if include_ocr and not getattr(settings, "desktop_autopilot_ocr_enabled", True):
                return ToolResult.failure("desktop.autopilot", "OCR local đang tắt trong cấu hình.")
            payload = autopilot.observe(include_ocr=bool(include_ocr))
        elif action == "context":
            payload = autopilot.build_local_context(query, paths=paths)
        elif action == "queue":
            payload = autopilot.enqueue_task(
                title=title,
                actions=_actions(actions),
                scope=scope,
                expected_window_keywords=expected_window_keywords,
            )
        elif action == "run_next":
            payload = autopilot.run_next()
        else:
            return ToolResult.failure(
                "desktop.autopilot",
                "action chỉ nhận status, observe, context, queue hoặc run_next.",
            )
    except Exception as exc:  # noqa: BLE001
        return ToolResult.failure("desktop.autopilot", str(exc))
    return ToolResult.success(
        "desktop.autopilot",
        output=json.dumps(payload, ensure_ascii=False, indent=2),
    )


__all__ = ["desktop_autopilot"]
