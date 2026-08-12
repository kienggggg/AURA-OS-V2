"""
evolution/loader.py
==================
ToolLoader — cổng phê duyệt (Human-in-the-loop) + nạp nóng tool vào registry.

Chỉ chạy SAU KHI code đã qua validator (không có BLOCK) và sandbox (smoke OK).
Loader làm hai việc:
  1. Trình bày code + báo cáo cho người, hỏi Y/N (ApprovalGate).
  2. Nếu được gật: ghi code ra data/tools_generated/, importlib nạp module, tìm
     hàm tool_* và đăng ký vào ToolRegistry ĐANG CHẠY (không cần restart).

importlib là cơ chế lõi — test được offline.
"""

from __future__ import annotations

import importlib.util
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from core.config import settings

if TYPE_CHECKING:
    from tools.registry import ToolRegistry

logger = logging.getLogger("aura.evolution.loader")

# Hàm hỏi phê duyệt: nhận (tiêu đề, nội dung) -> True/False.
ApproveFn = Callable[[str, str], bool]


def cli_approval(title: str, body: str) -> bool:
    """ApprovalGate mặc định: in code + báo cáo ra terminal, đọc Y/N từ người."""
    print("\n" + "=" * 60)
    print(f"  CẦN PHÊ DUYỆT: {title}")
    print("=" * 60)
    print(body)
    print("=" * 60)
    try:
        answer = input("  Phê duyệt nạp tool này? [y/N]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False
    return answer in {"y", "yes", "có", "co"}


@dataclass
class LoadResult:
    """Kết quả nạp tool."""

    ok: bool
    tool_name: str
    registered_as: str | None
    message: str


class ToolLoader:
    """Phê duyệt + nạp nóng tool tự sinh."""

    def __init__(self, approve_fn: ApproveFn | None = None) -> None:
        self.approve_fn = approve_fn or cli_approval
        self.output_dir = settings.generated_tools_dir

    # ------------------------------------------------------------------ #
    @staticmethod
    def _safe_module_name(tool_name: str) -> str:
        """Chuẩn hoá tên file/module an toàn (chỉ chữ số gạch dưới)."""
        base = re.sub(r"[^0-9a-zA-Z_]", "_", tool_name).strip("_")
        return base or "generated_tool"

    # ------------------------------------------------------------------ #
    def request_approval(self, tool_name: str, code: str, report_text: str) -> bool:
        """Hỏi người duyệt, trình bày đầy đủ code + báo cáo validator/sandbox."""
        body = (
            f"[BÁO CÁO KIỂM TRA]\n{report_text}\n\n"
            f"[MÃ NGUỒN TOOL — đọc kỹ trước khi gật]\n{code}"
        )
        return self.approve_fn(f"tool '{tool_name}'", body)

    # ------------------------------------------------------------------ #
    def load_into_registry(
        self,
        tool_name: str,
        code: str,
        registry: "ToolRegistry",
        description: str = "",
    ) -> LoadResult:
        """
        Ghi code đã duyệt ra đĩa, nạp nóng và đăng ký vào registry.

        KHÔNG tự hỏi phê duyệt ở đây — gọi request_approval() trước; hàm này chỉ
        chạy khi đã có cái gật. Tách bạch để engine kiểm soát luồng.
        """
        module_name = self._safe_module_name(tool_name)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        module_path = self.output_dir / f"{module_name}.py"

        try:
            module_path.write_text(code, encoding="utf-8")
        except OSError as exc:
            return LoadResult(False, tool_name, None, f"Ghi file thất bại: {exc}")

        # Nạp nóng module từ đường dẫn (không qua sys.path, tránh ô nhiễm namespace).
        try:
            spec = importlib.util.spec_from_file_location(
                f"aura_generated.{module_name}", str(module_path)
            )
            if spec is None or spec.loader is None:
                return LoadResult(False, tool_name, None, "Không tạo được module spec.")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Nạp module tự sinh thất bại.")
            return LoadResult(False, tool_name, None, f"Lỗi import: {exc}")

        # Tìm entrypoint tool_* trong module.
        tool_fn = None
        registered_name = None
        for attr in dir(module):
            if attr.startswith("tool_") and callable(getattr(module, attr)):
                tool_fn = getattr(module, attr)
                registered_name = attr
                break

        if tool_fn is None:
            return LoadResult(False, tool_name, None, "Không thấy hàm tool_* để đăng ký.")

        # Đăng ký vào registry đang chạy — AURA "mọc thêm tay" ngay lập tức.
        registry.register(registered_name, tool_fn, description or f"Tool tự sinh: {tool_name}")
        logger.info("Đã nạp nóng tool '%s' vào registry.", registered_name)
        return LoadResult(
            True, tool_name, registered_name,
            f"Đã đăng ký '{registered_name}' vào registry (file: {module_path}).",
        )


__all__ = ["ToolLoader", "LoadResult", "cli_approval", "ApproveFn"]
