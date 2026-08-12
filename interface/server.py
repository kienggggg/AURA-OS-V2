"""
interface/server.py
==================
AuraWebSocketServer — cổng WebSocket bọc Orchestrator.

Theo blueprint: event loop của giao diện (VTuber/Pet UI) phải TÁCH HẲN khỏi
asyncio của AURA. Server này chạy phía AURA, lắng nghe lệnh từ UI, gọi
`process_message()` ở thread riêng (để không chặn event loop), rồi đẩy kết quả
ngược lại. UI chỉ là client — Qt loop của nó sống độc lập.

Giao thức tin nhắn (JSON, đơn giản):
  UI  -> server: {"type": "chat", "text": "..."}
  server -> UI : {"type": "response", "text": "..."}      (trả lời xong)
                 {"type": "status",   "text": "thinking"}  (báo đang xử lý)
                 {"type": "error",    "text": "..."}        (lỗi)

websockets import trễ để app vẫn import được khi chưa cài.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING

from core.config import settings

if TYPE_CHECKING:
    from core.orchestrator import AURA_Orchestrator

logger = logging.getLogger("aura.interface.server")

# Loại tin NGẦM được phép HOÃN khi đang trả lời User (chỉ hoãn HIỂN THỊ, không chặn daemon).
# KHÔNG hoãn: status (talking_start/end điều khiển animation), response, error,
# approval_request (chính là câu trả lời), health_break (lệnh khoá máy), pong.
_DEFERRABLE_TYPES: frozenset[str] = frozenset({
    "proactive", "news", "growth", "action_notice",
})
# Trần buffer tin hoãn — phòng tràn nếu User để câu trả lời chạy quá lâu.
_MAX_DEFERRED = 50


class AuraWebSocketServer:
    """Phục vụ một (hoặc nhiều) UI client, cầu nối tới Orchestrator."""

    def __init__(
        self,
        orchestrator: "AURA_Orchestrator",
        host: str | None = None,
        port: int | None = None,
        event_queue: "asyncio.Queue[dict] | None" = None,
    ) -> None:
        self.orchestrator = orchestrator
        self.host = host or settings.ws_host
        self.port = port or settings.ws_port
        # Hàng đợi chia sẻ với daemon: sensor bỏ tin chủ động vào, server broadcast.
        self.event_queue = event_queue
        # Tập client đang nối (để broadcast tin chủ động ra UI).
        self._clients: set = set()
        # KIỂM SOÁT ĐỒNG THỜI (Luật im lặng): đang trả lời User thì hoãn tin ngầm.
        # Đếm số phiên chat đang chạy (hỗ trợ nhiều client); >0 = đang bận.
        self._chat_active = 0
        # Hàng chờ tạm các tin ngầm bị hoãn, xả ra ngay khi trả lời xong.
        self._deferred: list[dict] = []

    # ------------------------------------------------------------------ #
    async def _handle_chat(self, websocket, text: str) -> None:
        """
        Xử lý một tin chat: báo trạng thái, chạy process_message ở thread riêng.

        Trong lúc xử lý/trả lời, đặt cờ bận (_chat_active) để _broadcast_loop HOÃN
        mọi tin ngầm. Trả lời xong (finally) -> xả hàng tin ngầm ra UI theo đúng thứ tự.
        """
        self._chat_active += 1
        request_id = ""

        async def audit_result(summary: str, status: str = "completed") -> None:
            try:
                from core.self_history import record_event

                await asyncio.to_thread(
                    record_event,
                    actor="AURA",
                    kind="request_result",
                    summary=summary,
                    status=status,
                    source="mascot_websocket",
                    request_id=request_id,
                    tags=["conversation", "response"],
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("Ghi kết quả mascot vào hồ sơ lỗi (bỏ qua): %s", exc)

        try:
            try:
                from core.self_history import record_event

                request_id = await asyncio.to_thread(
                    record_event,
                    actor="Sếp",
                    kind="user_request",
                    summary=text,
                    status="received",
                    source="mascot_websocket",
                    tags=["conversation", "owner_instruction"],
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("Ghi yêu cầu mascot vào hồ sơ lỗi (bỏ qua): %s", exc)

            await self._send(websocket, "status", "thinking")

            # MẮT THẬT trước LLM: câu 'màn hình đang hiện gì' PHẢI đi vào OCR cục bộ,
            # không để orchestrator/LLM ĐOÁN từ trí nhớ (bug đã gặp: AURA bịa 'briefing
            # cho Sếp' trong khi màn đang hiện thứ khác). Dùng chung đúng đường Telegram.
            try:
                from core.desktop_autopilot import is_screen_observation_request
                from core.desktop_operator import describe_screen_smart

                if is_screen_observation_request(text):
                    # describe_screen_smart: Gemini vision đọc thẳng ảnh (sạch dấu),
                    # tự lùi về OCR local khi offline.
                    eyes = await asyncio.to_thread(describe_screen_smart)
                    await self._send(websocket, "response", eyes)
                    await audit_result(eyes)
                    return
            except Exception as exc:  # noqa: BLE001 — mắt lỗi thì rơi xuống chat thường
                logger.warning("Đọc màn hình cho mascot lỗi (rơi xuống chat): %s", exc)

            # "CẦN ĐĂNG TAY GÌ / FILE Ở ĐÂU" -> trả từ KHO THẬT, không để LLM đoán
            # (Sếp gặp: hỏi Wattpad, AURA bịa 'WhatsApp'). AURA phải biết hàng của mình.
            try:
                from core.manual_publish_query import (
                    answer_manual_publish, is_manual_publish_question,
                )

                if is_manual_publish_question(text):
                    ans = await asyncio.to_thread(answer_manual_publish)
                    await self._send(websocket, "response", ans)
                    await audit_result(ans)
                    return
            except Exception as exc:  # noqa: BLE001 — lỗi thì rơi xuống chat thường
                logger.warning("Trả lời việc-đăng-tay lỗi: %s", exc)

            # Hỏi về chính AURA -> ledger + git thật. Mascot xử lý trực tiếp để
            # không phụ thuộc LLM; các giao diện khác còn có chốt tại Orchestrator.
            try:
                from core.self_history import (
                    answer_self_history, is_self_history_question,
                )

                if is_self_history_question(text):
                    ans = await asyncio.to_thread(answer_self_history, text)
                    await self._send(websocket, "response", ans)
                    await audit_result(ans)
                    return
            except Exception as exc:  # noqa: BLE001
                logger.warning("Trả lời hồ sơ tự nhận thức lỗi: %s", exc)

            # LỆNH THAO TÁC (nấc 2): 'thao tác: <việc>' -> vòng lặp thao tác.
            # Mặc định DRY-RUN (chỉ lập kế hoạch); 'thao tác thật:' mới chạm chuột.
            try:
                from core.desktop_operator import (
                    DesktopOperator, format_report, parse_operator_command,
                )

                cmd = parse_operator_command(text)
                if cmd is not None:
                    report = await asyncio.to_thread(
                        DesktopOperator().run_goal, cmd["goal"], live=cmd["live"]
                    )
                    formatted = format_report(report)
                    await self._send(websocket, "response", formatted)
                    await audit_result(formatted)
                    return
            except Exception as exc:  # noqa: BLE001 — lỗi thao tác thì báo, không im
                logger.warning("Lệnh thao tác mascot lỗi: %s", exc)
                await self._send(websocket, "error", f"⚠️ Thao tác lỗi: {exc}")
                await audit_result(f"Thao tác lỗi: {exc}", status="failed")
                return

            # process_message là đồng bộ (gọi LLM/tool có thể chặn). Đẩy sang thread
            # riêng qua asyncio.to_thread để KHÔNG chặn event loop của server.
            try:
                response = await asyncio.to_thread(
                    self.orchestrator.process_message, text, audit=False
                )
            except Exception as exc:  # noqa: BLE001 — không để server chết vì 1 request
                logger.exception("process_message lỗi.")
                await self._send(websocket, "error", f"Lỗi nội bộ: {exc}")
                await audit_result(f"Lỗi nội bộ: {exc}", status="failed")
                return

            await self._send(websocket, "response", response)
            await audit_result(response)
        finally:
            # Hết phiên này; nếu KHÔNG còn phiên nào -> xả tin ngầm đã hoãn.
            self._chat_active = max(0, self._chat_active - 1)
            if self._chat_active == 0:
                await self._flush_deferred()

    async def _handle_avatar_chat(self, websocket, text: str) -> None:
        """Kênh chỉ-hội-thoại cho điện thoại robot; không dùng đường tool/approval."""
        await self._send(websocket, "status", "thinking")
        try:
            response = await asyncio.to_thread(
                self.orchestrator.process_avatar_message, text
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("process_avatar_message lỗi.")
            await self._send(websocket, "error", f"Lỗi nội bộ: {exc}")
            return
        await self._send(websocket, "response", response)

    # ------------------------------------------------------------------ #
    @staticmethod
    async def _send(websocket, msg_type: str, text: str) -> None:
        """Gửi một tin JSON về UI."""
        await websocket.send(json.dumps({"type": msg_type, "text": text}))

    async def _connection(self, websocket) -> None:
        """Vòng đời một kết nối UI: đọc tin, phân loại, đáp."""
        logger.info("UI client kết nối.")
        self._clients.add(websocket)
        try:
            async for raw in websocket:
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    await self._send(websocket, "error", "Tin nhắn không phải JSON hợp lệ.")
                    continue

                msg_type = data.get("type")
                if msg_type == "chat":
                    text = (data.get("text") or "").strip()
                    if text:
                        await self._handle_chat(websocket, text)
                    else:
                        await self._send(websocket, "error", "Tin chat rỗng.")
                elif msg_type == "avatar_chat":
                    text = (data.get("text") or "").strip()
                    if text:
                        await self._handle_avatar_chat(websocket, text)
                    else:
                        await self._send(websocket, "error", "Tin AURA Avatar rỗng.")
                elif msg_type == "ping":
                    await self._send(websocket, "pong", "ok")
                else:
                    await self._send(websocket, "error", f"Loại tin lạ: {msg_type!r}")
        except Exception as exc:  # noqa: BLE001 — gồm cả ConnectionClosed
            logger.info("UI client ngắt kết nối: %s", exc)
        finally:
            self._clients.discard(websocket)

    # ------------------------------------------------------------------ #
    async def _broadcast_loop(self) -> None:
        """
        Lấy tin chủ động từ event_queue (daemon bỏ vào) và định tuyến ra UI.

        LUÔN tiêu thụ queue ngay (không chặn daemon); chỉ HOÃN việc HIỂN THỊ tin ngầm
        khi đang trả lời User (qua _route_event).
        """
        if self.event_queue is None:
            return
        while True:
            event = await self.event_queue.get()
            await self._route_event(event)

    async def _route_event(self, event: dict) -> bool:
        """
        Quyết định gửi NGAY hay HOÃN một sự kiện.

        - Đang trả lời User (_chat_active>0) và là tin ngầm hoãn-được -> cất vào hàng
          chờ, trả False. Daemon KHÔNG bị chặn (queue đã được tiêu thụ).
        - Còn lại (status/response/error/approval/health...) -> gửi ngay, trả True.
        """
        etype = event.get("type")
        if self._chat_active > 0 and etype in _DEFERRABLE_TYPES:
            self._deferred.append(event)
            if len(self._deferred) > _MAX_DEFERRED:
                # Giữ các tin mới nhất, bỏ tin cũ để tránh phình bộ nhớ.
                self._deferred = self._deferred[-_MAX_DEFERRED:]
            logger.info("Hoãn tin ngầm '%s' (đang trả lời User).", etype)
            return False
        await self._broadcast_event(event)
        return True

    async def _broadcast_event(self, event: dict) -> None:
        """Đẩy một sự kiện xuống MỌI client đang nối (bỏ client đã chết)."""
        if not self._clients:
            logger.info("Tin nhưng chưa có UI: %s", event.get("text"))
            return
        payload = json.dumps(event)
        dead = set()
        for ws in self._clients:
            try:
                await ws.send(payload)
            except Exception:  # noqa: BLE001 — client chết thì bỏ
                dead.add(ws)
        self._clients -= dead

    async def _flush_deferred(self) -> None:
        """XẢ HÀNG: gửi các tin ngầm đã hoãn ra UI (sau khi trả lời User xong)."""
        if not self._deferred:
            return
        pending = self._deferred
        self._deferred = []
        logger.info("Xả %d tin ngầm sau khi trả lời xong.", len(pending))
        for event in pending:
            await self._broadcast_event(event)

    # ------------------------------------------------------------------ #
    async def serve_forever(self) -> None:
        """Chạy server bất tận (await trong asyncio), kèm vòng broadcast."""
        try:
            import websockets
        except ModuleNotFoundError as exc:
            raise ModuleNotFoundError(
                "Thiếu 'websockets'. Cài: pip install websockets"
            ) from exc

        logger.info("AURA WebSocket server: ws://%s:%d", self.host, self.port)
        async with websockets.serve(self._connection, self.host, self.port):
            # Chạy song song vòng broadcast (nếu có event_queue).
            await asyncio.gather(
                asyncio.Future(),          # giữ server sống mãi
                self._broadcast_loop(),    # đẩy tin chủ động
            )

    def run(self) -> None:
        """Tiện ích chạy server đứng-một-mình (blocking)."""
        asyncio.run(self.serve_forever())


__all__ = ["AuraWebSocketServer"]
