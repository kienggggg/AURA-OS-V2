"""
core/computer_use.py
===================
"Mắt thần" + ráp luồng Computer Use an toàn.

Gồm:
  - VisionGroundingBackend: đàn anh LOCAL `LocateAnything-3B` (qua Ollama vision)
    — nhận ảnh + mô tả vật thể, trả về toạ độ bounding box. Chạy local, 0 phí.
    Là một LLMBackend nên AgentBroker đón qua đúng cổng chuẩn (register_senior).
  - ComputerUseFlow: ráp CHỤP -> ĐỊNH VỊ -> ĐỀ XUẤT (Sếp gật) -> THỰC THI (MCP).

Van an toàn nằm ở AuraMCPClient (action side-effect qua approve_fn). Flow này
còn thêm một bước trình bày toạ độ ra UI trước khi gật, để Sếp thấy rõ sẽ click
vào đâu — model 3B có thể đoán lệch, nên người xác nhận là bắt buộc.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass

from brains.base import BrainError, ChatMessage, LLMBackend
from core.config import settings
from core.schemas import RouteTier

logger = logging.getLogger("aura.computer_use")


# ---------------------------------------------------------------------------
# Đàn anh "Mắt thần" — vision grounding chạy local
# ---------------------------------------------------------------------------
class VisionGroundingBackend(LLMBackend):
    """
    LocateAnything-3B qua Ollama (model đa phương thức chạy local).

    Chỉ làm 1 việc: nhận ảnh (base64) + mô tả vật thể -> trả toạ độ [x, y] tâm
    vùng cần click. Trả về JSON chuẩn để Flow parse, không văn vẻ.
    """

    tier = RouteTier.LOCAL  # chạy local, không tính phí

    def __init__(self, model: str = "locate-anything:3b", host: str | None = None) -> None:
        self.model = model
        self.host = (host or settings.ollama_host).rstrip("/")
        self.name = f"vision:{self.model}"

    def is_online(self) -> bool:
        import requests
        try:
            return requests.get(f"{self.host}/api/tags", timeout=3.0).status_code == 200
        except requests.RequestException:
            return False

    def chat(
        self,
        messages: list[ChatMessage],
        system_prompt: str | None = None,
        *,
        temperature: float = 0.0,
        max_tokens: int = 256,
        **kwargs,
    ) -> str:
        """
        Gọi Ollama vision. Ảnh truyền qua kwargs['images'] (list base64) theo chuẩn
        Ollama /api/chat. Trả nguyên text (Flow sẽ parse toạ độ).
        """
        import requests

        images = kwargs.get("images") or []
        payload_messages = []
        if system_prompt:
            payload_messages.append({"role": "system", "content": system_prompt})
        # Gắn ảnh vào message user cuối (chuẩn Ollama multimodal).
        for i, m in enumerate(messages):
            entry = {"role": m["role"], "content": m["content"]}
            if i == len(messages) - 1 and images:
                entry["images"] = images
            payload_messages.append(entry)

        body = {
            "model": self.model,
            "messages": payload_messages,
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        try:
            resp = requests.post(f"{self.host}/api/chat", json=body,
                                 timeout=settings.ollama_timeout_s)
            resp.raise_for_status()
            return resp.json()["message"]["content"]
        except (requests.RequestException, KeyError, ValueError) as exc:
            raise BrainError(f"Vision grounding lỗi: {exc}") from exc


# Prompt cho mắt thần — ép trả JSON toạ độ, không văn vẻ.
_GROUNDING_SYSTEM = (
    "Bạn là hệ định vị giao diện. Nhận ảnh màn hình + mô tả một vật thể. "
    "Trả về DUY NHẤT JSON: {\"found\": true/false, \"x\": <int>, \"y\": <int>}. "
    "x,y là toạ độ TÂM (pixel) của vật thể trong ảnh. Không giải thích gì thêm."
)


@dataclass
class GroundingResult:
    """Toạ độ định vị được."""

    found: bool
    x: int = 0
    y: int = 0


# ---------------------------------------------------------------------------
# Ráp luồng Computer Use an toàn
# ---------------------------------------------------------------------------
class ComputerUseFlow:
    """
    Ráp: CHỤP -> ĐỊNH VỊ (mắt thần) -> ĐỀ XUẤT ra UI -> Sếp gật -> THỰC THI (MCP).

    Flow KHÔNG tự click. Nó chuẩn bị toạ độ + mô tả, đẩy ra UI; chỉ khi
    AuraMCPClient.approve_fn trả True (Sếp gật) thì action mới chạy.
    """

    def __init__(self, vision: VisionGroundingBackend, mcp_client, event_queue=None) -> None:
        self.vision = vision
        self.mcp = mcp_client
        self.event_queue = event_queue

    # ------------------------------------------------------------------ #
    @staticmethod
    def _parse_grounding(text: str) -> GroundingResult:
        """Bóc JSON toạ độ từ phản hồi mắt thần (chịu được rác xung quanh)."""
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if not m:
            return GroundingResult(found=False)
        try:
            data = json.loads(m.group(0))
            return GroundingResult(
                found=bool(data.get("found", False)),
                x=int(data.get("x", 0)),
                y=int(data.get("y", 0)),
            )
        except (ValueError, TypeError):
            return GroundingResult(found=False)

    def _emit(self, text: str) -> None:
        if self.event_queue is not None:
            try:
                self.event_queue.put_nowait({"type": "proactive", "text": text})
            except Exception as exc:  # noqa: BLE001
                logger.warning("Không đẩy được tin computer-use ra UI: %s", exc)

    # ------------------------------------------------------------------ #
    async def click_target(self, target_desc: str) -> dict:
        """
        Toàn luồng "Click vào <target_desc>".

        Returns: dict {ok, stage, detail} — minh bạch dừng ở chặng nào.
        """
        # B1: CHỤP (read-only, tự do)
        shot = await self.mcp.screenshot()
        if not shot.ok:
            return {"ok": False, "stage": "screenshot", "detail": shot.detail}
        image_b64 = self._extract_image_b64(shot.data)
        if not image_b64:
            return {"ok": False, "stage": "screenshot", "detail": "Không lấy được ảnh base64."}

        # B2: ĐỊNH VỊ (mắt thần local)
        try:
            raw = self.vision.chat(
                [{"role": "user", "content": f"Định vị: {target_desc}"}],
                system_prompt=_GROUNDING_SYSTEM,
                images=[image_b64],
            )
        except BrainError as exc:
            return {"ok": False, "stage": "grounding", "detail": str(exc)}

        g = self._parse_grounding(raw)
        if not g.found:
            self._emit(f"Em không tìm thấy '{target_desc}' trên màn hình.")
            return {"ok": False, "stage": "grounding", "detail": "không định vị được"}

        # B3: ĐỀ XUẤT ra UI (để Sếp thấy sẽ click vào đâu) + B4: gật -> THỰC THI
        self._emit(
            f"Em định click vào '{target_desc}' tại toạ độ ({g.x},{g.y}). "
            f"Sếp xác nhận thì em thực thi."
        )
        # AuraMCPClient.click đã có cổng duyệt bên trong (approve_fn).
        result = await self.mcp.click(g.x, g.y, label=target_desc)
        if not result.ok:
            return {"ok": False, "stage": "execute", "detail": result.detail}
        return {"ok": True, "stage": "done", "detail": f"đã click ({g.x},{g.y})"}

    # ------------------------------------------------------------------ #
    @staticmethod
    def _extract_image_b64(shot_data) -> str | None:
        """
        Lấy chuỗi base64 ảnh từ kết quả screenshot của cua-driver.

        cua-driver trả ảnh trong content blocks; ta dò block kiểu image. Bọc an
        toàn vì cấu trúc có thể khác giữa các phiên bản — không tìm thấy thì None.
        """
        try:
            content = getattr(shot_data, "content", None) or []
            for block in content:
                # block có thể là ImageContent với .data (base64)
                data = getattr(block, "data", None)
                if isinstance(data, str) and len(data) > 100:
                    return data
        except Exception as exc:  # noqa: BLE001
            logger.warning("Bóc ảnh screenshot lỗi: %s", exc)
        return None


def register_vision_senior(broker, model: str = "locate-anything:3b") -> None:
    """
    Đăng ký "Mắt thần" vào AgentBroker như một Senior LOCAL, MIỄN PHÍ.

    Gọi sau khi dựng broker (vd trong main.py):
        from core.computer_use import register_vision_senior
        register_vision_senior(broker)
    """
    from core.agent_broker import SeniorSpec

    spec = SeniorSpec(
        name="LocateAnything-3B",
        backend=VisionGroundingBackend(model=model),
        skills=frozenset({"vision", "grounding", "locate"}),
        is_paid=False,        # chạy local — KHÔNG tính phí
        cost_per_call=0.0,
    )
    broker.register_senior(spec)


__all__ = [
    "VisionGroundingBackend",
    "ComputerUseFlow",
    "GroundingResult",
    "register_vision_senior",
]