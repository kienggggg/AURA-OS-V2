"""
factory/queue.py
================
Hàng đợi job BỀN qua sqlite3 (thư viện chuẩn — không thêm dependency).

Vì sao sqlite chứ không phải JSONL (như applications.jsonl): job MUTATE nhiều
lần/phút (progress %, step, state) — sqlite cho UPDATE nguyên tử, JSONL append-only
sẽ phải đọc-ghi lại cả file mỗi lần cập nhật. Sổ thu nhập/ứng tuyển (không mutate,
chỉ append) vẫn dùng JSONL như thiết kế cũ.

API đồng bộ (gọi qua asyncio.to_thread từ factory/worker.py) — giữ code ngắn,
sqlite3 tự khoá file đủ an toàn cho 1 tiến trình duy nhất (AURA).
"""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path

from core.config import settings
from factory.models import JobRecord

_DB_PATH = settings.factory_dir / "jobs.db"
_lock = threading.Lock()  # sqlite3 connection không thread-safe khi dùng qua to_thread


def _connect() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH))
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY,
            tool TEXT NOT NULL,
            data TEXT NOT NULL,
            state TEXT NOT NULL,
            created_at REAL NOT NULL
        )
        """
    )
    conn.commit()
    return conn


def enqueue(job: JobRecord) -> JobRecord:
    """Đưa 1 job mới vào hàng đợi (state='queued')."""
    with _lock, _connect() as conn:
        conn.execute(
            "INSERT INTO jobs (id, tool, data, state, created_at) VALUES (?, ?, ?, ?, ?)",
            (job.id, job.tool, json.dumps(job.to_dict(), ensure_ascii=False),
             job.state, job.created_at),
        )
    return job


def update(job: JobRecord) -> None:
    """Ghi đè toàn bộ bản ghi (dùng sau mỗi lần progress()/đổi state)."""
    with _lock, _connect() as conn:
        conn.execute(
            "UPDATE jobs SET data = ?, state = ? WHERE id = ?",
            (json.dumps(job.to_dict(), ensure_ascii=False), job.state, job.id),
        )


def get(job_id: str) -> JobRecord | None:
    with _lock, _connect() as conn:
        row = conn.execute("SELECT data FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if row is None:
        return None
    return JobRecord.from_dict(json.loads(row[0]))


def list_jobs(state: str | None = None, limit: int = 100) -> list[JobRecord]:
    with _lock, _connect() as conn:
        if state:
            rows = conn.execute(
                "SELECT data FROM jobs WHERE state = ? ORDER BY created_at DESC LIMIT ?",
                (state, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT data FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
    return [JobRecord.from_dict(json.loads(r[0])) for r in rows]


def next_queued(prefer_tools: tuple[str, ...] = ()) -> JobRecord | None:
    """Job cũ nhất còn chờ, ưu tiên một nhóm tool khi cần tập trung dòng tiền.

    Ưu tiên chỉ đổi thứ tự chạy; không xoá, không tự huỷ những job khác.
    """
    with _lock, _connect() as conn:
        row = None
        for tool in prefer_tools:
            row = conn.execute(
                "SELECT data FROM jobs WHERE state = 'queued' AND tool = ? "
                "ORDER BY created_at ASC LIMIT 1",
                (tool,),
            ).fetchone()
            if row is not None:
                break
        if row is None:
            row = conn.execute(
                "SELECT data FROM jobs WHERE state = 'queued' ORDER BY created_at ASC LIMIT 1"
            ).fetchone()
    if row is None:
        return None
    return JobRecord.from_dict(json.loads(row[0]))


def orphaned_running() -> list[JobRecord]:
    """Job còn 'running' lúc AURA khởi động lại (crash giữa chừng) — cần requeue."""
    return list_jobs(state="running", limit=1000)


def is_cancelled(job_id: str) -> bool:
    """Handler đang chạy gọi hàm này ở RANH GIỚI các bước nặng để biết user đã bấm
    Hủy chưa (nút Hủy chỉ đổi state trong DB — không kill được thread giữa chừng)."""
    job = get(job_id)
    return job is not None and job.state == "cancelled"


def cancel(job_id: str) -> bool:
    job = get(job_id)
    if job is None or job.state not in ("queued", "running"):
        return False
    job.state = "cancelled"
    job.step = "Đã hủy theo yêu cầu"
    update(job)
    return True


def purge_failed(tool: str | None = None) -> int:
    """Dọn dẹp các job bị hỏng cũ trong hàng đợi."""
    with _lock, _connect() as conn:
        if tool:
            cursor = conn.execute("DELETE FROM jobs WHERE state = 'failed' AND tool = ?", (tool,))
        else:
            cursor = conn.execute("DELETE FROM jobs WHERE state = 'failed'")
        count = cursor.rowcount
        conn.commit()
    return count


__all__ = ["enqueue", "update", "get", "list_jobs", "next_queued", "orphaned_running",
           "cancel", "is_cancelled", "purge_failed"]
