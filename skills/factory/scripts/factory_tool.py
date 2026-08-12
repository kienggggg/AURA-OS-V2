"""
skills/factory/scripts/factory_tool.py
=======================================
Cổng chat vào Xưởng Kiếm Tiền — đọc/ghi CÙNG hàng đợi sqlite mà dashboard web
và factory/worker.py (chạy trong daemon) dùng. Xem SKILL.md.
"""

from __future__ import annotations

from core.schemas import ToolResult
from factory import queue as job_queue
from factory.models import JobRecord
from factory.tools import get_tool


def tool_factory(
    action: str,
    tool: str | None = None,
    params: dict | None = None,
    job_id: str | None = None,
) -> ToolResult:
    action = (action or "").strip().lower()

    if action == "enqueue":
        if not tool:
            return ToolResult.failure("factory.control", "Thiếu tham số 'tool'.")
        spec = get_tool(tool)
        if spec is None:
            return ToolResult.failure(
                "factory.control", f"Không có tool '{tool}' trong xưởng."
            )
        if not spec.enabled:
            return ToolResult.failure(
                "factory.control", f"Tool '{tool}' chưa mở (đợt sau)."
            )
        job = JobRecord(tool=tool, params=params or {})
        job_queue.enqueue(job)
        return ToolResult.success(
            "factory.control",
            output=f"Đã xếp hàng job {job.id} ({spec.label_vi}). Xem tiến độ: "
                    f"action='status', job_id='{job.id}'.",
        )

    if action == "status":
        if not job_id:
            return ToolResult.failure("factory.control", "Thiếu tham số 'job_id'.")
        job = job_queue.get(job_id)
        if job is None:
            return ToolResult.failure("factory.control", f"Không thấy job '{job_id}'.")
        return ToolResult.success(
            "factory.control",
            output=f"Job {job.id} ({job.tool}): {job.state} — {job.progress}% — {job.step}"
                    + (f" — LỖI: {job.error}" if job.error else ""),
        )

    if action == "list":
        jobs = job_queue.list_jobs(limit=10)
        if not jobs:
            return ToolResult.success("factory.control", output="Hàng đợi trống.")
        lines = [f"- {j.id} [{j.tool}] {j.state} {j.progress}% — {j.step}" for j in jobs]
        return ToolResult.success("factory.control", output="\n".join(lines))

    if action == "cancel":
        if not job_id:
            return ToolResult.failure("factory.control", "Thiếu tham số 'job_id'.")
        ok = job_queue.cancel(job_id)
        msg = f"Đã hủy job {job_id}." if ok else f"Không hủy được job {job_id} (đã xong/không tồn tại)."
        return ToolResult.success("factory.control", output=msg) if ok else \
            ToolResult.failure("factory.control", msg)

    return ToolResult.failure(
        "factory.control", f"action lạ: {action!r} — chỉ nhận enqueue/status/list/cancel."
    )
