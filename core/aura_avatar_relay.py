"""Token-protected, conversation-only LAN/USB bridge for AURA Avatar.

The bridge exposes no orchestrator tools or approvals. Valid text is forwarded
to AURA's localhost WebSocket as ``avatar_chat`` and only a text reply is
returned to the phone.
"""

from __future__ import annotations

import argparse
import asyncio
import ipaddress
import json
import logging
import re
import socket
import time
from collections.abc import Awaitable, Callable
from typing import Any

from aiohttp import web

from core.aura_avatar_pairing import token_matches
from core.config import settings

logger = logging.getLogger("aura.avatar.relay")

_CHAT_ROUTE = "/v1/avatar/chat"
_HEALTH_ROUTE = "/v1/avatar/health"
_MAX_BODY_BYTES = 8 * 1024
_DEVICE_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{8,80}$")

AvatarResponder = Callable[[str], Awaitable[str]]


class AvatarInputError(ValueError):
    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


def _local_ipv4() -> str:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        probe.connect(("192.0.2.1", 80))
        candidate = probe.getsockname()[0]
    address = ipaddress.ip_address(candidate)
    if address.is_loopback or address.is_unspecified:
        raise RuntimeError("Không xác định được IP Wi-Fi nội bộ cho AURA Avatar.")
    return str(address)


def resolve_host(host: str = "") -> str:
    configured = (host or settings.aura_avatar_lan_host or "auto").strip()
    return _local_ipv4() if configured.lower() in {"", "auto", "0.0.0.0"} else configured


def validate_payload(body: Any, supplied_token: str) -> tuple[str, str, str]:
    if not token_matches(supplied_token):
        raise AvatarInputError("AURA Avatar chưa được xác thực.", status=403)
    if not isinstance(body, dict):
        raise AvatarInputError("Dữ liệu AURA Avatar không hợp lệ.")

    device_id = str(body.get("device_id") or "").strip()
    request_id = str(body.get("request_id") or "").strip()
    text = str(body.get("text") or "").strip()
    if not _DEVICE_ID.fullmatch(device_id):
        raise AvatarInputError("Mã thiết bị không hợp lệ.")
    if not _REQUEST_ID.fullmatch(request_id):
        raise AvatarInputError("Mã yêu cầu không hợp lệ.")
    if not text:
        raise AvatarInputError("Câu nói đang rỗng.")
    if len(text) > 500:
        raise AvatarInputError("Câu nói dài quá 500 ký tự.", status=413)
    return device_id, request_id, text


async def ask_local_aura(text: str) -> str:
    """Ask localhost AURA through the safe ``avatar_chat`` message type."""
    try:
        import websockets
    except ModuleNotFoundError as exc:
        raise RuntimeError("Thiếu thư viện websockets cho AURA Avatar.") from exc

    uri = f"ws://127.0.0.1:{settings.ws_port}"
    async with websockets.connect(
        uri, open_timeout=5, close_timeout=2, max_size=64 * 1024
    ) as websocket:
        await websocket.send(json.dumps({"type": "avatar_chat", "text": text}))
        while True:
            raw = await asyncio.wait_for(websocket.recv(), timeout=120)
            data = json.loads(raw)
            msg_type = data.get("type")
            if msg_type == "response":
                return str(data.get("text") or "")[:1200]
            if msg_type == "error":
                raise RuntimeError(str(data.get("text") or "AURA không trả lời được."))


class AvatarRelay:
    """Small replay cache and rate limit around one safe text responder."""

    def __init__(self, responder: AvatarResponder = ask_local_aura) -> None:
        self.responder = responder
        self._cache: dict[tuple[str, str], tuple[float, str]] = {}
        self._last_request: dict[str, float] = {}

    def _prune(self, now: float) -> None:
        expired = [key for key, (seen, _) in self._cache.items() if now - seen > 600]
        for key in expired:
            self._cache.pop(key, None)

    async def chat(self, body: Any, supplied_token: str) -> tuple[str, bool]:
        device_id, request_id, text = validate_payload(body, supplied_token)
        now = time.monotonic()
        self._prune(now)
        key = (device_id, request_id)
        cached = self._cache.get(key)
        if cached is not None:
            return cached[1], True

        previous = self._last_request.get(device_id, 0.0)
        if now - previous < 0.35:
            raise AvatarInputError("AURA Avatar đang nhận câu trước, hãy chờ một chút.", status=429)
        self._last_request[device_id] = now
        response = (await self.responder(text)).strip()[:1200]
        if not response:
            response = "AURA chưa tạo được câu trả lời."
        self._cache[key] = (now, response)
        return response, False


def build_avatar_relay_app(
    responder: AvatarResponder = ask_local_aura,
) -> web.Application:
    relay = AvatarRelay(responder)

    async def health(request: web.Request) -> web.Response:
        if not token_matches(request.headers.get("X-AURA-Avatar-Token", "")):
            return web.json_response({"error": "Chưa xác thực."}, status=403)
        return web.json_response({"status": "ok", "mode": "conversation_only"})

    async def chat(request: web.Request) -> web.Response:
        if request.content_length and request.content_length > _MAX_BODY_BYTES:
            return web.json_response({"error": "Gói AURA Avatar quá lớn."}, status=413)
        try:
            body = await request.json()
            response, replayed = await relay.chat(
                body, request.headers.get("X-AURA-Avatar-Token", "")
            )
        except AvatarInputError as exc:
            return web.json_response({"error": str(exc)}, status=exc.status)
        except Exception:  # noqa: BLE001 - do not disclose internals to LAN callers
            logger.exception("Cầu AURA Avatar xử lý câu nói lỗi.")
            return web.json_response(
                {"error": "AURA tạm thời chưa trả lời được."}, status=502
            )
        return web.json_response({"response": response, "replayed": replayed})

    app = web.Application(client_max_size=_MAX_BODY_BYTES)
    app.router.add_get(_HEALTH_ROUTE, health)
    app.router.add_post(_CHAT_ROUTE, chat)
    return app


async def start_avatar_relay(
    *, host: str = "", port: int | None = None
) -> tuple[web.AppRunner, str]:
    configured = (host or settings.aura_avatar_lan_host or "auto").strip()
    dual = configured.lower() == "dual"
    bind_hosts = ["127.0.0.1", _local_ipv4()] if dual else [resolve_host(configured)]
    bind_port = int(port or settings.aura_avatar_lan_port)
    runner = web.AppRunner(build_avatar_relay_app(), access_log=None)
    await runner.setup()
    try:
        for bind_host in dict.fromkeys(bind_hosts):
            await web.TCPSite(runner, bind_host, bind_port).start()
    except Exception:
        await runner.cleanup()
        raise
    advertised_host = bind_hosts[-1]
    endpoint = f"http://{advertised_host}:{bind_port}{_CHAT_ROUTE}"
    logger.info(
        "AURA Avatar đang nghe trên %s:%d.",
        ", ".join(bind_hosts),
        bind_port,
    )
    return runner, endpoint


async def _serve(host: str, port: int) -> None:
    runner, endpoint = await start_avatar_relay(host=host, port=port)
    print(f"AURA Avatar relay ready: {endpoint}")
    try:
        await asyncio.Event().wait()
    finally:
        await runner.cleanup()


def main() -> None:
    parser = argparse.ArgumentParser(description="AURA Avatar conversation-only relay")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=settings.aura_avatar_lan_port)
    args = parser.parse_args()
    asyncio.run(_serve(args.host, args.port))


__all__ = [
    "AvatarInputError",
    "AvatarRelay",
    "ask_local_aura",
    "build_avatar_relay_app",
    "resolve_host",
    "start_avatar_relay",
    "validate_payload",
]


if __name__ == "__main__":
    main()
