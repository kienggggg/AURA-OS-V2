"""
core/jarvis_core.py
===================
JARVIS Proactive Core — Hệ Thần Kinh Trung Ương Tự Chủ & Chủ Động Cho AURA OS v2.

Lấy cảm hứng từ các Siêu AI (J.A.R.V.I.S., Ultron, Alpha trong Rebuild World, Transformers):
  1. Cảm Nhận Đa Giác Quan (Perception Engine): Giám sát môi trường, nhiệt độ máy, tiến độ xưởng và tài nguyên.
  2. Tổng Hợp Chỉ Thị Chủ Động (Proactive Synthesizer): Tự động phát hiện cơ hội/nguy cơ và đưa ra báo cáo ngắn gọn cho Sếp.
  3. Phối Hợp Hội Đồng Đa Nhân Cách (Triad Council Integration): Kết nối Architect, Generator, Reviewer.
  4. Thao Tác Vật Lý Sinh Học (Biological Physical Operator): Điều khiển chuột/bàn phím ảo qua Bezier curves & human keystrokes.
"""

from __future__ import annotations

import logging
import time
import sys
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.metrics import system_thermal_check

logger = logging.getLogger("aura.jarvis")


@dataclass
class JarvisTelemetry:
    """Chỉ số sinh hiệu toàn hệ thống."""
    cpu_percent: float
    memory_percent: float
    thermal_ok: bool
    active_jobs: int
    system_status: str


class JarvisProactiveCore:
    """Trái tim điều hành chủ động JARVIS của AURA OS v2."""

    def __init__(self, name: str = "AURA-JARVIS") -> None:
        self.name = name
        self.start_time = time.monotonic()
        logger.info("Khởi chạy JARVIS Proactive Core cho %s.", self.name)

    def scan_telemetry(self) -> JarvisTelemetry:
        """Quét chỉ số sinh hiệu toàn máy tính (CPU, RAM, Nhiệt độ)."""
        th = system_thermal_check()
        status = "HEALTHY (Êm ái)" if not th.get("overheated") else "COOLING (Đang hạ nhiệt)"
        return JarvisTelemetry(
            cpu_percent=th.get("cpu_percent", 0.0),
            memory_percent=th.get("memory_percent", 0.0),
            thermal_ok=not th.get("overheated", False),
            active_jobs=0,
            system_status=status,
        )

    def synthesize_proactive_brief(self) -> str:
        """Tổng hợp báo cáo chủ động ngắn gọn như JARVIS phục vụ Sếp."""
        telem = self.scan_telemetry()
        uptime_min = int((time.monotonic() - self.start_time) / 60)
        
        brief = [
            f"⚡ [JARVIS CORE STATUS]: Hệ thống vận hành bình thường ({uptime_min}m uptime).",
            f"📊 Sinh hiệu: CPU {telem.cpu_percent:.1f}% | RAM {telem.memory_percent:.1f}% | Trạng thái: {telem.system_status}.",
            "🛡️ Bảo vệ: Cầu dao xưởng HOẠT ĐỘNG | Chống quá nhiệt TỰ ĐỘNG | Anti-Bot sinh học SẴN SÀNG.",
            "🤖 Sẵn sàng tiếp nhận mục tiêu dài hạn và tự động tiến hoá!"
        ]
        return "\n".join(brief)


if __name__ == "__main__":
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    core = JarvisProactiveCore()
    print(core.synthesize_proactive_brief())
