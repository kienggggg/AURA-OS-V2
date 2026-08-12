"""
agents/coder_agent.py
====================
CoderAgent — "Khuôn mặt Thông thái": sinh code cho tool còn thiếu.

KHÁC HẲN agent_coder.py CŨ (đã loại bỏ):
  - Cũ: hard-code API key, shell=True (command injection), tự ghi file vào đường
    dẫn tuỳ ý từ comment '# FILE:', tự append vào tools.py. Cực kỳ nguy hiểm.
  - Mới: CHỈ sinh ra một "ứng viên" (GeneratedTool) gồm tên + code + mô tả.
    KHÔNG ghi file, KHÔNG chạy, KHÔNG cài gì. Mọi tác dụng phụ do EvolutionEngine
    điều phối qua validator/sandbox/approval/loader.

Dùng Bộ não cloud (System 2) qua BrainRouter để sinh code chất lượng cao, nhồi
"văn mẫu" (golden template) là cấu trúc tool manga để model bắt chước.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

from core.brain_router import BrainRouter
from core.schemas import Intent, IntentLabel, RouteTier
from brains.base import ChatMessage

logger = logging.getLogger("aura.agents.coder")

# "Văn mẫu": cấu trúc chuẩn mà mọi tool tự sinh phải noi theo.
_GOLDEN_TEMPLATE = '''\
from core.schemas import ToolResult

def tool_example(param1: str, param2: int = 0) -> ToolResult:
    """Mô tả ngắn tool làm gì."""
    try:
        # ... logic thực thi ...
        result_text = f"Đã xử lý {param1} với {param2}"
        return ToolResult.success("example", output=result_text)
    except Exception as exc:
        return ToolResult.failure("example", str(exc))
'''

_SYSTEM_PROMPT = f"""Bạn là Senior Python Engineer của hệ thống AURA.
Nhiệm vụ: viết MỘT tool Python hoàn chỉnh theo đúng khuôn mẫu chuẩn dưới đây.

KHUÔN MẪU CHUẨN (bắt buộc noi theo):
```python
{_GOLDEN_TEMPLATE}
```

QUY TẮC TUYỆT ĐỐI:
1. Chỉ xuất DUY NHẤT một khối ```python chứa code. Không giải thích ngoài khối.
2. Hàm entrypoint phải đặt tên bắt đầu bằng `tool_` và TRẢ VỀ `ToolResult`
   (import từ core.schemas). Bọc toàn bộ trong try/except, lỗi -> ToolResult.failure.
3. CẤM: os.system, subprocess, eval, exec, __import__, ctypes, socket, shutil.rmtree,
   truy cập dunder (__globals__, __subclasses__...), đường dẫn '..' hay thư mục hệ thống.
4. Nếu cần thư viện ngoài, khai báo ở đầu file bằng comment:
   `# AURA-DEPS: tên_gói_1, tên_gói_2`
5. Viết code thật, đầy đủ logic. CẤM `pass`, `TODO`, hay pseudocode.
"""


# --- Hiến pháp bảo mật (CONTEXT.md) — nhắc nhở Agent ở MỌI lần sinh code ---
# Gốc dự án = thư mục cha của agents/. CONTEXT.md nằm ở gốc.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_CONTEXT_PATH = _PROJECT_ROOT / "CONTEXT.md"


def _load_context() -> str:
    """Đọc CONTEXT.md (Hiến pháp). Lỗi/thiếu file -> trả rỗng, KHÔNG làm sập."""
    try:
        return _CONTEXT_PATH.read_text(encoding="utf-8").strip()
    except Exception as exc:  # noqa: BLE001 — thiếu hiến pháp không được chặn sinh code
        logger.warning("Không đọc được CONTEXT.md (bỏ qua): %s", exc)
        return ""


def build_system_prompt() -> str:
    """
    Dựng system prompt cho CoderAgent: NHỒI Hiến pháp CONTEXT.md lên ĐẦU, rồi tới
    khuôn mẫu/quy tắc sinh code. Đọc lại file mỗi lần gọi để luôn dùng bản mới nhất.
    """
    context = _load_context()
    if not context:
        return _SYSTEM_PROMPT
    return (
        "==== HIẾN PHÁP BẢO MẬT AURA (CONTEXT.md) — TUÂN THỦ TUYỆT ĐỐI ====\n"
        f"{context}\n"
        "==== HẾT HIẾN PHÁP ====\n\n"
        f"{_SYSTEM_PROMPT}"
    )


@dataclass
class GeneratedTool:
    """Ứng viên tool do CoderAgent sinh ra (CHƯA được duyệt/nạp)."""

    name: str
    code: str
    declared_deps: list[str]
    raw_response: str


class CoderAgent:
    """Sinh code tool mới từ một đặc tả bằng lời."""

    def __init__(self, router: BrainRouter) -> None:
        self.router = router

    def generate_tool(self, spec: str, tool_name_hint: str = "") -> GeneratedTool | None:
        """
        Sinh một tool từ đặc tả `spec`. Trả GeneratedTool, hoặc None nếu không bóc
        được code. KHÔNG ghi/chạy gì cả.
        """
        # Ép intent CLOUD (coding) để dùng System 2 cho chất lượng code cao.
        intent = Intent(
            label=IntentLabel.CODING,
            tier=RouteTier.CLOUD,
            confidence=1.0,
            reason="coder-agent forced cloud",
            raw_text=spec,
        )
        messages: list[ChatMessage] = [
            {"role": "user", "content": f"Viết tool cho yêu cầu sau:\n{spec}"}
        ]

        # Nhồi Hiến pháp CONTEXT.md vào prompt ở MỖI lần sinh code (đọc bản mới nhất).
        result = self.router.run(messages, intent, system_prompt=build_system_prompt())
        if not result.ok:
            logger.error("CoderAgent: bộ não lỗi: %s", result.error)
            return None

        code = self._extract_code_block(result.output)
        if not code:
            logger.error("CoderAgent: không bóc được khối code từ phản hồi.")
            return None

        deps = self._extract_deps(code)
        name = tool_name_hint or self._guess_tool_name(code) or "generated_tool"
        return GeneratedTool(
            name=name, code=code, declared_deps=deps, raw_response=result.output
        )

    # ------------------------------------------------------------------ #
    @staticmethod
    def _extract_code_block(text: str) -> str | None:
        """Bóc nội dung trong khối ```python ... ```; fallback ``` ... ```."""
        m = re.search(r"```python\s*\n(.*?)```", text, re.DOTALL)
        if not m:
            m = re.search(r"```\s*\n(.*?)```", text, re.DOTALL)
        return m.group(1).strip() if m else None

    @staticmethod
    def _extract_deps(code: str) -> list[str]:
        """Đọc dòng '# AURA-DEPS: a, b' để biết tool cần cài gì."""
        m = re.search(r"#\s*AURA-DEPS:\s*(.+)", code)
        if not m:
            return []
        return [d.strip() for d in m.group(1).split(",") if d.strip()]

    @staticmethod
    def _guess_tool_name(code: str) -> str | None:
        """Lấy tên hàm tool_* đầu tiên làm tên tool."""
        m = re.search(r"def\s+(tool_[0-9a-zA-Z_]+)\s*\(", code)
        return m.group(1) if m else None


__all__ = ["CoderAgent", "GeneratedTool", "build_system_prompt"]
