"""The factory must yield between jobs when a safe code restart is pending."""

from __future__ import annotations

import asyncio

from factory import worker


def test_pending_restart_prevents_factory_from_claiming_next_job(monkeypatch):
    class FakeDaemon:
        _running = True
        aura_frozen = False
        _pending_restart = "code changed"
        event_queue = None

        async def _await_ram_headroom(self, _name):
            raise AssertionError("RAM gate must not run while restart is pending")

    daemon = FakeDaemon()
    monkeypatch.setattr(worker, "_resumed_once", True)

    async def stop_after_yield(_seconds):
        daemon._running = False

    monkeypatch.setattr(worker.asyncio, "sleep", stop_after_yield)
    monkeypatch.setattr(
        worker.job_queue,
        "next_queued",
        lambda *_args: (_ for _ in ()).throw(
            AssertionError("factory claimed a new job before pending restart")
        ),
    )

    asyncio.run(worker.factory_heartbeat(daemon))
