"""Narrow, token-protected LAN ingress for AURA MB Bridge.

This is deliberately separate from the dashboard: it has one POST route, accepts
only minimal MBBank notification events and never exposes AURA controls over Wi-Fi.
"""

from __future__ import annotations

import argparse
import asyncio
import ipaddress
import logging
import re
import socket
from collections.abc import Callable
from typing import Any

from aiohttp import web

from core.android_mb_pairing import token_matches
from core.config import settings

logger = logging.getLogger("aura.android_mb_lan_relay")

_ROUTE = "/v1/mbbank/incoming"
_REFERENCE = re.compile(r"^[a-f0-9]{64}$")
_MAX_BODY_BYTES = 4 * 1024


class RelayInputError(ValueError):
    """A rejected incoming phone payload with a safe HTTP status."""

    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


def _local_ipv4() -> str:
    """Find the IP chosen by the OS for the active private-network route."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        probe.connect(("192.0.2.1", 80))  # TEST-NET; UDP connect sends no packet.
        candidate = probe.getsockname()[0]
    address = ipaddress.ip_address(candidate)
    if address.is_loopback or address.is_unspecified:
        raise RuntimeError("Không xác định được IP Wi-Fi nội bộ cho cầu Android MB.")
    return str(address)


def resolve_host(host: str = "") -> str:
    configured = (host or settings.android_mb_lan_host or "auto").strip()
    return _local_ipv4() if configured.lower() in {"", "auto", "0.0.0.0"} else configured


def ingest_payload(
    body: Any,
    supplied_token: str,
    *,
    capture: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Validate one Android event before it can enter AURA's cashflow queue."""
    if not token_matches(supplied_token):
        raise RelayInputError("Cầu Android chưa được xác thực.", status=403)
    if not isinstance(body, dict):
        raise RelayInputError("Dữ liệu báo có không hợp lệ.")

    reference = str(body.get("reference") or "").strip().lower()
    if not _REFERENCE.fullmatch(reference):
        raise RelayInputError("Mã đối chiếu Android không hợp lệ.")
    if str(body.get("currency") or "VND").upper() != "VND":
        raise RelayInputError("Cầu MB Android chỉ nhận VND.")

    from core.cashflow import capture_incoming

    create = capture or capture_incoming
    try:
        return create(
            amount=body.get("amount"),
            currency="VND",
            source="mbbank_android_notification",
            reference=reference,
            description="MB Bank báo có từ Android",
            received_at=body.get("received_at"),
        )
    except (TypeError, ValueError) as exc:
        raise RelayInputError(str(exc)) from exc


async def _incoming(request: web.Request) -> web.Response:
    if request.content_length and request.content_length > _MAX_BODY_BYTES:
        return web.json_response({"error": "Gói báo có quá lớn."}, status=413)
    try:
        body = await request.json()
        event = ingest_payload(body, request.headers.get("X-AURA-Cashflow-Token", ""))
    except RelayInputError as exc:
        return web.json_response({"error": str(exc)}, status=exc.status)
    except Exception:  # noqa: BLE001 - never disclose internal details to LAN callers
        logger.exception("Cầu Android MB nhận payload lỗi.")
        return web.json_response({"error": "Không xử lý được báo có."}, status=400)
    return web.json_response({"id": event.get("id"), "status": event.get("status")}, status=201)


def build_lan_relay_app() -> web.Application:
    app = web.Application(client_max_size=_MAX_BODY_BYTES)
    app.router.add_post(_ROUTE, _incoming)
    return app


async def start_lan_relay(*, host: str = "", port: int | None = None) -> tuple[web.AppRunner, str]:
    bind_host = resolve_host(host)
    bind_port = int(port or settings.android_mb_lan_port)
    app = build_lan_relay_app()
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    try:
        await web.TCPSite(runner, bind_host, bind_port).start()
    except Exception:
        await runner.cleanup()
        raise
    endpoint = f"http://{bind_host}:{bind_port}{_ROUTE}"
    logger.info("Cầu Android MB Wi-Fi đang nghe trên %s:%d.", bind_host, bind_port)
    return runner, endpoint


async def _serve(host: str, port: int) -> None:
    runner, endpoint = await start_lan_relay(host=host, port=port)
    print(f"AURA MB LAN relay ready: {endpoint}")
    try:
        await asyncio.Event().wait()
    finally:
        await runner.cleanup()


def main() -> None:
    parser = argparse.ArgumentParser(description="AURA MB LAN relay")
    parser.add_argument("--host", default="auto")
    parser.add_argument("--port", type=int, default=settings.android_mb_lan_port)
    args = parser.parse_args()
    asyncio.run(_serve(args.host, args.port))


__all__ = [
    "RelayInputError",
    "build_lan_relay_app",
    "ingest_payload",
    "resolve_host",
    "start_lan_relay",
]


if __name__ == "__main__":
    main()
