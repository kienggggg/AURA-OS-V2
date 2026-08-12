"""
factory/worker.py
==================
Vòng worker của xưởng — dò hàng đợi (factory.queue), chạy ĐÚNG 1 job nặng/lúc
(máy 12GB RAM không chịu được song song), tôn trọng cờ đóng băng `aura_frozen`
và cửa nhường RAM `_await_ram_headroom` sẵn có của daemon. Đăng ký làm 1 task
trong `AuraDaemon.start()` giống hệt mẫu `_crew_heartbeat`.

Job "running" mồ côi lúc AURA khởi động lại (crash/tắt máy giữa chừng) được
đưa lại hàng đợi NGAY LẦN ĐẦU heartbeat chạy — handler nào đọc `job.progress`
lúc vào (như echo.sleep) sẽ tự tiếp tục thay vì làm lại từ đầu.
"""

from __future__ import annotations

import asyncio
import logging
import time

from core.config import settings
from factory import qc as factory_qc
from factory import queue as job_queue
from factory.models import JobCancelled, JobRecord
from factory.tools import get_tool

logger = logging.getLogger("aura.factory.worker")

_resumed_once = False


def _make_progress(job: JobRecord, event_queue, loop: asyncio.AbstractEventLoop):
    def _progress(pct: int, step: str) -> None:
        job.progress = max(0, min(100, pct))
        job.step = step
        job_queue.update(job)
        # progress() chạy trong thread của to_thread -> đẩy về event loop bằng
        # call_soon_threadsafe (giống mẫu _on_generation trong main.py).
        if event_queue is not None:
            ev = {"type": "factory_progress", "job_id": job.id, "tool": job.tool,
                  "pct": job.progress, "step": job.step}
            try:
                loop.call_soon_threadsafe(event_queue.put_nowait, ev)
            except Exception:  # noqa: BLE001 — loop đóng/đầy không được làm sập job
                pass
    return _progress


def _resume_orphans() -> None:
    orphans = job_queue.orphaned_running()
    for job in orphans:
        logger.warning(
            "Job '%s' (%s) mồ côi sau khởi động lại -> requeue, tiếp tục từ %d%%.",
            job.id, job.tool, job.progress,
        )
        job.state = "queued"
        job.step = f"Tiếp tục sau khởi động lại (đã {job.progress}%)"
        job_queue.update(job)


async def _run_one(job: JobRecord, event_queue, loop: asyncio.AbstractEventLoop) -> None:
    tool = get_tool(job.tool)
    if tool is None or tool.handler is None:
        job.state = "failed"
        job.error = f"Không tìm thấy tool '{job.tool}' trong TOOL_REGISTRY."
        job_queue.update(job)
        return

    job.state = "running"
    job.started_at = job.started_at or time.time()
    job_queue.update(job)
    progress = _make_progress(job, event_queue, loop)

    try:
        await asyncio.to_thread(tool.handler, job, progress)
    except JobCancelled:
        logger.info("Job '%s' (%s) đã bị Hủy giữa chừng theo yêu cầu.", job.id, job.tool)
        job.state = "cancelled"
        job.step = "Đã hủy giữa chừng"
        job.finished_at = time.time()
        job_queue.update(job)
        return
    except Exception as exc:  # noqa: BLE001 — lỗi 1 job không được giết cả worker
        logger.exception("Job '%s' (%s) lỗi.", job.id, job.tool)
        job.state = "failed"
        job.error = str(exc)
        job.finished_at = time.time()
        job_queue.update(job)
        # CẦU DAO: hỏng liên tiếp nhiều lần thì NGẮT tool, khỏi đốt máy vô ích
        # (bài học token YouTube chết mà autopilot vẫn đẩy job — 25 job hỏng).
        try:
            from factory import breaker
            if breaker.note_failure(job.tool, str(exc)):
                await _emit_breaker(event_queue, loop, job.tool, str(exc))
        except Exception:  # noqa: BLE001 — cầu dao hỏng không được giết worker
            pass
        return

    # User có thể đã bấm Hủy đúng lúc handler vừa xong — tôn trọng quyết định đó.
    latest = await asyncio.to_thread(job_queue.get, job.id)
    if latest is not None and latest.state == "cancelled":
        return

    try:
        report = factory_qc.run(tool.product_line, job)
        job.qc_path = report.path
        job.state = "done" if report.passed else "needs_review"
        # REFLEXION: trượt QC -> đúc bài học để lần sau né (không sập nếu lỗi).
        if not report.passed:
            from factory import reflexion
            await asyncio.to_thread(reflexion.note_outcome, tool.product_line,
                                    tool.name, report.checks, job.error or "")
    except Exception as exc:  # noqa: BLE001 — QC lỗi không được giấu kết quả job đã chạy xong
        logger.warning("QC job '%s' lỗi (đánh dấu needs_review): %s", job.id, exc)
        job.state = "needs_review"
        job.error = job.error or f"QC lỗi: {exc}"
    job.progress = 100
    job.finished_at = time.time()
    job_queue.update(job)
    # Chạy được -> đóng cầu dao cho tool này.
    try:
        from factory import breaker
        breaker.note_success(job.tool)
    except Exception:  # noqa: BLE001
        pass


async def _emit_breaker(event_queue, loop, tool: str, err: str) -> None:
    """Báo Sếp MỘT LẦN khi cầu dao vừa ngắt (đi qua event_queue -> Telegram)."""
    msg = (f"🔌 AURA đã NGẮT '{tool}' vì hỏng liên tiếp 5 lần.\n"
           f"Lỗi: {err[:160]}\n"
           "Em thôi chạy tool này để khỏi đốt máy vô ích. Sếp sửa xong thì "
           "nhắn 'mocaudao' để em chạy lại.")
    try:
        await event_queue.put({"type": "proactive", "text": msg})
    except Exception:  # noqa: BLE001
        logger.warning("Không báo được cầu dao ngắt: %s", tool)


async def factory_heartbeat(daemon) -> None:
    """Đăng ký trong AuraDaemon.start() (xem core/daemon.py)."""
    global _resumed_once
    if not _resumed_once:
        await asyncio.to_thread(_resume_orphans)
        _resumed_once = True

    loop = asyncio.get_running_loop()
    while daemon._running:
        if daemon.aura_frozen:          # CẤP 1: ngủ đông -> không NHẬN job mới
            await asyncio.sleep(settings.factory_poll_s)
            continue
        # Mã mới đang chờ restart: hoàn tất job hiện tại trong _run_one, nhưng không
        # giành job kế tiếp trước cảm biến file watcher. Nếu không, hàng đợi dài có
        # thể làm bản cập nhật bị đói vô hạn dù từng job đều kết thúc bình thường.
        if getattr(daemon, "_pending_restart", None):
            await asyncio.sleep(settings.factory_poll_s)
            continue
        await daemon._await_ram_headroom("factory_worker")
        if not daemon._running:
            break
        try:
            prefer = ("freelance.apply",) if bool(
                getattr(settings, "work_for_hire_mode_enabled", False)
            ) else ()
            job = await asyncio.to_thread(job_queue.next_queued, prefer)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Dò hàng đợi xưởng lỗi (bỏ qua chu kỳ): %s", exc)
            job = None
        # CẦU DAO: tool đang bị ngắt -> HUỶ job thay vì chạy rồi hỏng tiếp.
        # Không huỷ thì `next_queued` cứ trả lại đúng job đó, worker kẹt vòng lặp.
        if job is not None:
            try:
                from factory import breaker
                tripped, why = breaker.is_open(job.tool)
                if tripped:
                    logger.info("Bỏ qua job '%s' — cầu dao đang ngắt: %s", job.tool, why)
                    await asyncio.to_thread(job_queue.cancel, job.id)
                    await asyncio.sleep(0.2)
                    continue
            except Exception:  # noqa: BLE001
                pass
        if job is None:
            await asyncio.sleep(settings.factory_poll_s)
            continue
        await _run_one(job, daemon.event_queue, loop)


__all__ = ["factory_heartbeat"]
