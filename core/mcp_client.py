"""
core/mcp_client.py
=================
AuraMCPClient — AURA đóng vai MCP Client, nối tới `cua-driver` (MCP Server) để
điều khiển chuột/phím ở chế độ ngầm.

VAN AN TOÀN (luật sắt): mọi action CHẠM RA NGOÀI (click, gõ, kéo) PHẢI qua cổng
duyệt của Sếp trước khi thực thi. "Ngầm" = không giật chuột vật lý; KHÔNG đồng
nghĩa "không người duyệt". Một cú gật cho một chuỗi action, không hỏi từng pixel.

Hai nhóm thao tác:
  - READ-ONLY (chụp màn hình, liệt kê cửa sổ): chạy tự do, không cần duyệt.
  - SIDE-EFFECT (click/type/drag/scroll): BẮT BUỘC qua approve_fn.

MCP SDK import trễ — app vẫn import được khi chưa cài cua-driver.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable

logger = logging.getLogger("aura.mcp_client")

# Hàm duyệt action: nhận (mô tả hành động) -> True/False.
ApproveActionFn = Callable[[str], bool]

# Các action có tác dụng phụ — BẮT BUỘC duyệt.
_SIDE_EFFECT_ACTIONS: frozenset[str] = frozenset(
    {"click", "double_click", "right_click", "type", "key", "drag", "scroll", "move"}
)
# Các action chỉ đọc — chạy tự do.
_READ_ONLY_ACTIONS: frozenset[str] = frozenset({"screenshot", "list_windows", "get_screen_size"})


@dataclass
class ActionResult:
    """Kết quả một thao tác qua MCP."""

    ok: bool
    action: str
    detail: str = ""
    data: Any = None


class AuraMCPClient:
    """
    Client nối tới cua-driver MCP server.

    Cách dùng (đồng bộ-hoá bề mặt, async bên dưới do MCP SDK là async):
        client = AuraMCPClient(server_cmd=["cua-driver"], approve_fn=cli_approve)
        await client.connect()
        shot = await client.screenshot()                 # read-only, tự do
        await client.click(120, 340, label="nút Lưu")    # side-effect -> hỏi duyệt
        await client.close()
    """

    def __init__(
        self,
        server_cmd: list[str] | None = None,
        approve_fn: ApproveActionFn | None = None,
    ) -> None:
        """
        Args:
            server_cmd: lệnh khởi chạy cua-driver MCP server (stdio transport).
            approve_fn: cổng duyệt action side-effect; mặc định CHẶN (an toàn).
        """
        self.server_cmd = server_cmd or ["cua-driver"]
        self.approve_fn = approve_fn or self._default_deny
        self._session = None
        self._ctx = None  # giữ context manager để đóng đúng cách

    # ------------------------------------------------------------------ #
    @staticmethod
    def _default_deny(description: str) -> bool:
        """Mặc định CHẶN mọi action side-effect khi chưa cấp cổng duyệt thật."""
        logger.warning("Action side-effect bị chặn (chưa có cổng duyệt): %s", description)
        return False

    # ------------------------------------------------------------------ #
    async def connect(self) -> None:
        """Mở phiên MCP tới cua-driver qua stdio. Import SDK trễ."""
        try:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client
        except ModuleNotFoundError as exc:
            raise ModuleNotFoundError(
                "Thiếu MCP SDK. Cài: pip install mcp  (và cài cua-driver riêng)."
            ) from exc

        params = StdioServerParameters(command=self.server_cmd[0],
                                       args=self.server_cmd[1:])
        self._ctx = stdio_client(params)
        read, write = await self._ctx.__aenter__()
        self._session = ClientSession(read, write)
        await self._session.__aenter__()
        await self._session.initialize()
        logger.info("Đã nối cua-driver MCP server: %s", " ".join(self.server_cmd))

    async def close(self) -> None:
        """Đóng phiên MCP gọn gàng."""
        try:
            if self._session is not None:
                await self._session.__aexit__(None, None, None)
            if self._ctx is not None:
                await self._ctx.__aexit__(None, None, None)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Đóng MCP lỗi (bỏ qua): %s", exc)
        finally:
            self._session = None
            self._ctx = None

    # ------------------------------------------------------------------ #
    async def _call_tool(self, name: str, arguments: dict) -> ActionResult:
        """Gọi một tool của cua-driver. KHÔNG tự kiểm duyệt ở đây (caller lo)."""
        if self._session is None:
            return ActionResult(False, name, "Chưa connect() tới MCP server.")
        try:
            result = await self._session.call_tool(name, arguments)
        except Exception as exc:  # noqa: BLE001 — lỗi MCP không nên nổ ra ngoài
            logger.exception("Gọi tool MCP '%s' lỗi.", name)
            return ActionResult(False, name, f"Lỗi MCP: {exc}")
        return ActionResult(True, name, "ok", data=result)

    async def _guarded_call(self, action: str, arguments: dict, description: str) -> ActionResult:
        """
        Cổng chung: action side-effect phải qua approve_fn; read-only thì thẳng.

        Đây là chỗ luật sắt được thực thi — KHÔNG đường vòng.
        """
        if action in _SIDE_EFFECT_ACTIONS:
            if not self.approve_fn(description):
                return ActionResult(False, action,
                                    "Sếp chưa duyệt — action bị hủy.")
        return await self._call_tool(action, arguments)

    # ------------------------------------------------------------------ #
    # READ-ONLY — tự do
    # ------------------------------------------------------------------ #
    async def screenshot(self) -> ActionResult:
        """Chụp màn hình (read-only). Trả ảnh trong .data theo định dạng cua-driver."""
        return await self._call_tool("screenshot", {})

    async def list_windows(self) -> ActionResult:
        return await self._call_tool("list_windows", {})

    # ------------------------------------------------------------------ #
    # SIDE-EFFECT — qua cổng duyệt
    # ------------------------------------------------------------------ #
    async def click(self, x: int, y: int, label: str = "") -> ActionResult:
        """Click tại (x,y). Mô tả `label` hiện ra để Sếp biết click vào cái gì."""
        desc = f"CLICK tại ({x},{y})" + (f" — {label}" if label else "")
        return await self._guarded_call("click", {"x": x, "y": y}, desc)

    async def type_text(self, text: str) -> ActionResult:
        """Gõ chuỗi text (side-effect)."""
        preview = text if len(text) <= 40 else text[:40] + "…"
        return await self._guarded_call("type", {"text": text}, f"GÕ: {preview!r}")

    async def press_key(self, key: str) -> ActionResult:
        return await self._guarded_call("key", {"key": key}, f"PHÍM: {key}")

    async def scroll(self, dx: int, dy: int) -> ActionResult:
        return await self._guarded_call("scroll", {"dx": dx, "dy": dy},
                                        f"CUỘN ({dx},{dy})")


__all__ = ["AuraMCPClient", "ActionResult", "ApproveActionFn"]