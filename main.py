"""
main.py
=======
Điểm khởi động AURA — siêu mỏng. Một lệnh `python main.py` đánh thức cả hệ:
  - Orchestrator (Memory + Router + Tools)
  - WebSocket server (cho Pet UI nối vào)
  - Daemon ngầm (sensor quét Downloads, đẩy tin chủ động ra UI)

Mascot Miku khởi động RIÊNG (python -m ui.mascot, hoặc .bat/shortcut),
đúng blueprint — Qt loop tách khỏi asyncio của hệ này.

Toàn bộ logic nằm trong các module core/; file này chỉ ráp và bấm nút chạy.
"""

from __future__ import annotations

import asyncio
import logging
import sys

# Console Windows mặc định cp1252 không in được box-drawing/emoji/tiếng Việt có dấu
# khi stdout bị pipe (không phải console thật, vd chạy qua tool dev) -> ép UTF-8.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except (AttributeError, ValueError):
        pass

from core.config import settings


def _setup_logging() -> None:
    logging.basicConfig(
        level=getattr(logging, settings.log_level, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    # Ghi log ra file (data/logs/aura.log) để Self-Reflection có dữ liệu mỗi đêm.
    try:
        from core.reflection import configure_file_logging
        configure_file_logging()
    except Exception as exc:  # noqa: BLE001 — thiếu file-log không được chặn khởi động
        logging.getLogger("aura").warning("Không bật file logging: %s", exc)


async def _run() -> None:
    """Dựng và chạy đồng thời Server + Daemon trên cùng một event loop."""
    # Import trễ để lỗi thiếu thư viện hiện rõ ràng, không vỡ lúc nạp module.
    from core.agent_broker import AgentBroker
    from core.daemon import AuraDaemon
    from core.orchestrator import AURA_Orchestrator
    from core.llm import LocalCPUEngine
    from brains.cloud_claude import ClaudeBackend
    from interface.server import AuraWebSocketServer
    from tools.registry import build_default_registry

    settings.ensure_dirs()

    # Hàng đợi chia sẻ: daemon (sensor) -> server (broadcast ra UI).
    event_queue: asyncio.Queue[dict] = asyncio.Queue()

    # NỐI MẠCH KHUÔN MẶT: khi gemma4:e4b bắt đầu/kết thúc generate, engine gọi listener.
    # Engine chạy ở thread riêng (asyncio.to_thread) nên phải đẩy về loop bằng
    # call_soon_threadsafe; server._broadcast_loop sẽ phát status ra mọi UI (mascot).
    from core.llm import add_generation_listener
    _loop = asyncio.get_running_loop()

    def _on_generation(active: bool) -> None:
        ev = {"type": "status", "text": "talking_start" if active else "talking_end"}
        try:
            _loop.call_soon_threadsafe(event_queue.put_nowait, ev)
        except Exception:  # noqa: BLE001 — loop đóng/đầy không được làm sập generate
            pass

    add_generation_listener(_on_generation)

    # Nhà thầu chính: LocalCPUEngine (Ollama, CPU-only) + Claude (cloud/đàn anh), gắn ngân
    # sách + cổng UI để duyệt việc trả phí. Đàn anh chuyên dụng sẽ được tech_scout
    # đăng ký thêm sau qua broker.register_senior(...).
    broker = AgentBroker(
        local=LocalCPUEngine(),  # System 1 chạy 100% CPU qua Ollama (core.llm)
        cloud=ClaudeBackend(),
        event_queue=event_queue,
    )
    # Đăng ký "Mắt thần" LocateAnything-3B làm Senior local, miễn phí.
    from core.computer_use import register_vision_senior
    register_vision_senior(broker)
    orchestrator = AURA_Orchestrator(
        router=broker, registry=build_default_registry(), event_queue=event_queue
    )
    server = AuraWebSocketServer(orchestrator, event_queue=event_queue)
    daemon = AuraDaemon(event_queue=event_queue)
    # Cấp 1 (AURA Sleep): cho orchestrator cầm daemon để lệnh chat "aura ngủ đông/
    # thức dậy" đóng/mở băng các nhịp ngầm.
    orchestrator.daemon = daemon
    # Kênh Telegram: daemon CẦM orchestrator để chat từ điện thoại (duyệt 'y'/'huỷ',
    # 'ngủ đông', hỏi-đáp) đi qua ĐÚNG bộ não hội thoại như bong bóng mascot.
    daemon.orchestrator = orchestrator
    # Bước 4 (vệ sinh bộ nhớ): daemon DÙNG CHUNG MemoryStore của orchestrator để lưu
    # bản briefing cuối — tránh mở client ChromaDB thứ 2 (khỏi tranh chấp khoá file).
    daemon.memory = orchestrator.memory
    # Mắt–tay Desktop dùng chung MemoryStore hiện hành, tránh mở ChromaDB lần hai.
    from core.desktop_autopilot import DesktopAutopilot, set_runtime_autopilot
    daemon.desktop_autopilot = DesktopAutopilot(memory=orchestrator.memory)
    set_runtime_autopilot(daemon.desktop_autopilot)

    # Hội đồng 3 nhân cách + cầu Human Gate — NGỦ ĐÔNG khi tập trung kiếm tiền
    # (COUNCIL_ENABLED=false mặc định): không construct = không tốn RAM, ít nhiễu.
    if getattr(settings, "council_enabled", False):
        from core.triad_council import TriadCouncil, CouncilChatBridge
        _council = TriadCouncil(
            generator_tier=settings.council_generator_tier, memory=orchestrator.memory
        )
        orchestrator.council = _council
        orchestrator.council_bridge = CouncilChatBridge(_council, event_queue=event_queue)
    orchestrator.loop = _loop

    # Dashboard web (Xưởng Kiếm Tiền) — kênh chính để Sếp TỰ dùng mọi tool.
    from interface.dashboard import start_dashboard
    dashboard_runner = await start_dashboard()
    lan_relay_runner = None
    lan_relay_endpoint = ""
    avatar_relay_runner = None
    avatar_relay_endpoint = ""
    if settings.android_mb_lan_enabled:
        try:
            from core.android_mb_lan_relay import start_lan_relay
            lan_relay_runner, lan_relay_endpoint = await start_lan_relay()
        except Exception as exc:  # noqa: BLE001 - optional relay must not stop AURA
            logging.getLogger("aura.main").warning("Không mở được cầu Android MB Wi-Fi: %s", exc)
    if settings.aura_avatar_lan_enabled:
        try:
            from core.aura_avatar_relay import start_avatar_relay
            avatar_relay_runner, avatar_relay_endpoint = await start_avatar_relay()
        except Exception as exc:  # noqa: BLE001 - optional relay must not stop AURA
            logging.getLogger("aura.main").warning("Không mở được cầu AURA Avatar: %s", exc)

    print("╔══════════════════════════════════════════════╗")
    print("║   🧠 AURA - Autonomous Intelligence System     ║")
    print(f"║   WebSocket: ws://{settings.ws_host}:{settings.ws_port}".ljust(49) + "║")
    print(f"║   Xưởng (dashboard): http://{settings.dashboard_host}:{settings.dashboard_port}".ljust(49) + "║")
    if lan_relay_endpoint:
        print(f"║   Cầu MB Wi-Fi: {lan_relay_endpoint}".ljust(49) + "║")
    if avatar_relay_endpoint:
        print(f"║   AURA Avatar: {avatar_relay_endpoint}".ljust(49) + "║")
    print("║   Mở giao diện: python -m ui.mascot            ║")
    print("╚══════════════════════════════════════════════╝")

    await daemon.start()
    try:
        await server.serve_forever()
    finally:
        await daemon.stop()
        if lan_relay_runner is not None:
            await lan_relay_runner.cleanup()
        if avatar_relay_runner is not None:
            await avatar_relay_runner.cleanup()
        await dashboard_runner.cleanup()


def main() -> None:
    _setup_logging()
    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        print("\n👋 AURA tắt.")


if __name__ == "__main__":
    # Chống CHẠY ĐÔI: có 2 launcher (Startup AURA_OS.bat + start_aura.bat bấm tay);
    # bản thứ hai thoát im lặng để mỗi lệnh không bị nhân đôi.
    from core.single_instance import ensure_single
    ensure_single("daemon")
    main()
