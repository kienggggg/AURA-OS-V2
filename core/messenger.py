"""
core/messenger.py
=================
Kênh NHẮN TIN của AURA qua Telegram — để Sếp điều khiển AURA và nhận báo cáo
từ ĐIỆN THOẠI, không phải ngồi ở terminal gõ "ngủ đông"/"y" cả ngày.

Thiết kế (giữ nhẹ, không thêm phụ thuộc nặng):
- Dùng thẳng Telegram Bot API qua `requests` chạy trong `asyncio.to_thread`
  (long-poll getUpdates timeout=30). KHÔNG cài python-telegram-bot.
- Chạy như MỘT nhịp background của daemon (giống các *_heartbeat khác).
- 🔒 AN NINH: bot CHỈ nghe lệnh từ đúng `telegram_owner_id`. Bot này điều khiển
  được máy Sếp (ngủ đông, đọc báo cáo, gọi cloud) nên người lạ bắt được bot
  TUYỆT ĐỐI không được ra lệnh. Mọi update từ chat id khác bị bỏ + ghi log.

Bật: đặt trong .env:
    TELEGRAM_ENABLED=true
    TELEGRAM_BOT_TOKEN=123456:ABC...      (tạo bot qua @BotFather)
    TELEGRAM_OWNER_ID=987654321           (nhắn @userinfobot để lấy id)
"""

from __future__ import annotations

import asyncio
import json
import logging
import unicodedata
from pathlib import Path
from typing import TYPE_CHECKING, Any

import requests

from core.config import settings, PROJECT_ROOT
from core.redact import redact

if TYPE_CHECKING:
    from core.daemon import AuraDaemon

logger = logging.getLogger(__name__)

_API = "https://api.telegram.org/bot{token}/{method}"
_TG_MAX = 4000  # trần 4096, chừa lề an toàn khi cắt tin dài
_FEEDBACK = PROJECT_ROOT / "data" / "feedback"

_HELP = (
    "🤖 AURA — trợ lý của Sếp. Lệnh:\n"
    "/viet [số] — bảo AURA viết tiếp chương (mặc định 1)\n"
    "/taotruyen [nền] — tạo BỘ TRUYỆN mới (chép văn án + mở form)\n"
    "/dangrk [chương] — đăng chương lên Rookies (nền tốt nhất)\n"
    "/dangwp [chương] — chuẩn bị đăng Wattpad\n"
    "/ngu — cho AURA ngủ đông (nhường CPU/RAM)\n"
    "/thuc — đánh thức AURA\n"
    "/manhinh — đọc cửa sổ và chữ đang hiện trên laptop\n"
    "/tin — tin việc có đường ứng tuyển mới nhất\n"
    "/tien — xem báo có đang chờ đối soát\n"
    "/thu1 — xem AURA còn cần 1% thao tác nào từ Chủ\n"
    "/thu1san — xác nhận đã nối Payhip + kênh nhận tiền; cho AURA tự đăng sản phẩm\n"
    "/thu1tat — dừng đăng sản phẩm mới ngay\n"
    "/trend — brief trend nóng mới nhất (trend radar)\n"
    "/crew — tình hình tổ công nhân\n"
    "/renvan — rèn cho AURA VIẾT HAY HƠN (chấm điểm, chỉ giữ bản thắng)\n"
    "/apdungvan — duyệt áp bản viết mới\n"
    "/caudao — xem tool nào bị NGẮT vì hỏng liên tiếp\n"
    "/mocaudao — đóng lại cầu dao sau khi đã sửa\n"
    "/hoc — chạy một ĐÊM TỰ RÈN kỹ năng (SkillOpt)\n"
    "/apdung — duyệt áp bản kỹ năng AURA vừa học\n"
    "/capnhat — tự động kéo mã nguồn mới nhất (git pull) & khởi động lại\n"
    "/trangthai — AURA đang chạy gì, ngủ hay thức\n"
    "/help — bảng lệnh này\n\n"
    "💡 Nhắn thẳng câu hỏi → AURA trả lời. Khi AURA xin phép, "
    "nhắn *duyệt* (hoặc *y*) để gật, *huỷ* để bỏ — y như gõ ở máy."
)



def _normalize_intent(text: str) -> str:
    folded = unicodedata.normalize("NFKD", str(text or "").casefold()).replace("đ", "d")
    return " ".join(
        "".join(ch for ch in folded if not unicodedata.combining(ch)).split()
    )


def _is_screen_observation_request(text: str) -> bool:
    """Nhận câu yêu cầu quan sát màn hình. Uỷ quyền cho bộ nhận diện DÙNG CHUNG ở
    core.desktop_autopilot để Telegram và bong bóng mascot hành xử y hệt nhau.
    (Giữ tên/vị trí này vì test đang import từ đây.)"""
    from core.desktop_autopilot import is_screen_observation_request

    return is_screen_observation_request(text)


class TelegramMessenger:
    """Bot Telegram một-chủ (single-owner) gắn vào AuraDaemon."""

    def __init__(self, daemon: "AuraDaemon", token: str, owner_id: str) -> None:
        self._daemon = daemon
        self._token = token
        self._owner = str(owner_id).strip()
        self._offset = 0            # update_id đã xử lý (getUpdates offset)
        self._engines = None        # cặp (local, cloud) dựng lười cho chat tự do

    # ------------------------------------------------------------------ #
    # Gọi Telegram API (đồng bộ, bọc trong to_thread ở phía async)
    # ------------------------------------------------------------------ #
    def _call(self, method: str, **params: Any) -> dict[str, Any] | None:
        url = _API.format(token=self._token, method=method)
        try:
            resp = requests.post(url, data=params, timeout=40)
            data = resp.json()
            if not data.get("ok"):
                logger.warning("Telegram %s trả lỗi: %s", method, data.get("description"))
                return None
            return data
        except requests.RequestException as exc:
            logger.warning("Telegram %s lỗi mạng: %s", method, redact(str(exc)))
            return None
        except ValueError as exc:  # JSON hỏng
            logger.warning("Telegram %s trả không phải JSON: %s", method, redact(str(exc)))
            return None

    # ------------------------------------------------------------------ #
    # Gửi tin cho Sếp (dùng cả cho hook _emit đẩy báo cáo chủ động)
    # ------------------------------------------------------------------ #
    async def send(self, text: str) -> None:
        """Gửi 1 tin cho Sếp; tự cắt nếu quá dài. Không bao giờ ném ra ngoài."""
        if not text:
            return
        try:
            for chunk in _split(text, _TG_MAX):
                await asyncio.to_thread(
                    self._call, "sendMessage", chat_id=self._owner, text=chunk,
                    disable_web_page_preview="true",
                )
        except Exception as exc:  # noqa: BLE001 — kênh phụ, không được giết daemon
            logger.warning("Gửi Telegram lỗi: %s", redact(str(exc)))

    # ------------------------------------------------------------------ #
    # Vòng lắng nghe (long-poll) — chạy như 1 nhịp daemon
    # ------------------------------------------------------------------ #
    async def poll_loop(self) -> None:
        logger.info("Kênh Telegram BẬT — chỉ nghe owner id=%s.", self._owner)
        await self.send("🌅 AURA đã lên sóng Telegram. Gõ /help để xem lệnh.")
        while getattr(self._daemon, "_running", False):
            try:
                data = await asyncio.to_thread(
                    self._call, "getUpdates", offset=self._offset, timeout=30
                )
                if not data:
                    await asyncio.sleep(3)   # lỗi mạng -> nghỉ ngắn rồi thử lại
                    continue
                for upd in data.get("result", []):
                    self._offset = upd["update_id"] + 1
                    await self._dispatch(upd)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 — vành đai: không sập daemon
                logger.warning("Vòng Telegram lỗi: %s", redact(str(exc)))
                await asyncio.sleep(3)

    # ------------------------------------------------------------------ #
    async def _dispatch(self, upd: dict[str, Any]) -> None:
        msg = upd.get("message") or upd.get("edited_message")
        if not msg:
            return
        chat_id = str(msg.get("chat", {}).get("id", ""))
        text = (msg.get("text") or "").strip()
        # 🔒 KHOÁ AN NINH: chỉ owner được ra lệnh.
        if chat_id != self._owner:
            logger.warning("Bỏ tin Telegram từ NGƯỜI LẠ id=%s: %r", chat_id, text[:80])
            return
        if not text:
            return
        try:
            reply = await self._handle(text)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Xử lý lệnh Telegram lỗi: %s", redact(str(exc)))
            reply = f"⚠️ Có lỗi khi xử lý: {exc}"
        if reply:
            await self.send(reply)

    # ------------------------------------------------------------------ #
    async def _handle(self, text: str) -> str:
        """Mọi câu Telegram và kết quả đều được báo cho hồ sơ tự nhận thức."""
        request_id = ""
        try:
            from core.self_history import record_event

            request_id = await asyncio.to_thread(
                record_event,
                actor="Sếp",
                kind="user_request",
                summary=text,
                status="received",
                source="telegram",
                tags=["conversation", "owner_instruction", "telegram"],
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Ghi yêu cầu Telegram vào hồ sơ lỗi (bỏ qua): %s", exc)
        try:
            reply = await self._handle_impl(text)
        except Exception as exc:
            try:
                from core.self_history import record_event

                await asyncio.to_thread(
                    record_event,
                    actor="AURA",
                    kind="request_result",
                    summary=f"Telegram xử lý lỗi: {type(exc).__name__}: {redact(str(exc))}",
                    status="failed",
                    source="telegram",
                    request_id=request_id,
                    tags=["conversation", "runtime_error", "telegram"],
                )
            except Exception:  # noqa: BLE001
                pass
            raise
        try:
            from core.self_history import record_event

            await asyncio.to_thread(
                record_event,
                actor="AURA",
                kind="request_result",
                summary=reply,
                status="completed",
                source="telegram",
                request_id=request_id,
                tags=["conversation", "response", "telegram"],
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Ghi kết quả Telegram vào hồ sơ lỗi (bỏ qua): %s", exc)
        return reply

    async def _handle_impl(self, text: str) -> str:
        cmd = text.lower().split()[0].lstrip("/")
        if cmd in ("help", "start"):
            return _HELP
        if cmd in ("ngu", "ngudong", "sleep"):
            self._daemon.freeze_aura()
            return "💤 AURA đã ngủ đông — các nhịp ngầm tạm dừng, nhường CPU/RAM cho Sếp."
        if cmd in ("thuc", "wake"):
            self._daemon.unfreeze_aura()
            return "🌅 AURA đã thức — các nhịp ngầm hoạt động trở lại."
        if cmd in ("manhinh", "screen", "xemmanhinh"):
            return await self._describe_screen()
        if cmd in ("tin", "job", "viec"):
            return _fmt_jobs()
        if cmd in ("trend", "radar"):
            return _fmt_trend()
        if cmd in ("crew", "to", "cong nhan"):
            return _fmt_crew()
        if cmd in ("trangthai", "status", "tt"):
            return self._fmt_status()
        if cmd in ("tien", "dongtien", "cashflow"):
            return await asyncio.to_thread(self._cashflow_status)
        if cmd in ("growth", "operator", "vuaviec", "lead"):
            return await asyncio.to_thread(self._growth_status)
        if cmd in ("thu1", "1phantram", "onepercent"):
            return await asyncio.to_thread(self._one_percent_status)
        if cmd in ("thu1san", "thu1bat", "onepercentready"):
            return await asyncio.to_thread(self._activate_one_percent)
        if cmd in ("thu1tat", "onepercentstop"):
            return await asyncio.to_thread(self._disable_one_percent)
        if cmd in ("viet", "write"):
            parts = text.split()
            n = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 1
            return await asyncio.to_thread(self._enqueue_write, max(1, min(n, 5)))
        if cmd in ("caudao", "breaker"):
            from factory import breaker
            return breaker.status()
        if cmd in ("mocaudao", "resetbreaker"):
            from factory import breaker
            return breaker.reset()
        if cmd in ("renvan", "renprompt"):
            from factory.prompt_evolve import evolve
            return await asyncio.to_thread(evolve)
        if cmd in ("apdungvan", "adoptvan"):
            from factory.prompt_evolve import adopt
            return await asyncio.to_thread(adopt)
        if cmd in ("hoc", "tienhoa", "skillopt"):
            from core.skillopt_hand import run_night
            return await asyncio.to_thread(run_night)
        if cmd in ("apdung", "adopt"):
            from core.skillopt_hand import adopt
            return await asyncio.to_thread(adopt)
        if cmd in ("capnhat", "update", "pull"):
            from core.updater import check_and_pull_updates
            updated, msg = await asyncio.to_thread(check_and_pull_updates)
            if updated:
                asyncio.create_task(self._delayed_restart())
                return f"{msg}\n⏳ Đang khởi động lại AURA trong giây lát..."
            return msg
        if cmd in ("taotruyen", "newstory"):

            parts = text.split()[1:]
            plat = parts[0].lower() if parts else "rookies"
            return await asyncio.to_thread(self._assist_new_story, plat)
        if cmd in ("dangwp", "dangrk", "dang"):
            parts = text.split()[1:]
            plat = {"dangwp": "wattpad", "dangrk": "rookies"}.get(cmd)
            if plat is None:                       # /dang <nền> [chương]
                plat = parts[0].lower() if parts else "wattpad"
                parts = parts[1:]
            ch = int(parts[0]) if parts and parts[0].isdigit() else None
            return await asyncio.to_thread(self._assist_publish, plat, ch)
        # Câu hỏi quan sát màn hình phải đi thẳng vào "mắt" cục bộ. Không cho
        # cloud/orchestrator đoán từ dữ liệu khác khi chưa hề chụp/OCR màn hình.
        if _is_screen_observation_request(text):
            return await self._describe_screen()
        # "Cần đăng tay gì / file ở đâu" -> trả từ kho THẬT, không để LLM đoán bừa.
        from core.manual_publish_query import (
            answer_manual_publish, is_manual_publish_question,
        )
        if is_manual_publish_question(text):
            return await asyncio.to_thread(answer_manual_publish)
        from core.self_tuition import (
            answer_self_tuition, is_self_tuition_question,
        )
        if is_self_tuition_question(text):
            return await asyncio.to_thread(answer_self_tuition, text)
        # "Ai đã sửa gì trong bạn" -> đọc git log thật + sổ mổ, không để LLM đoán.
        from core.self_history import (
            answer_self_history, is_self_history_question,
        )
        if is_self_history_question(text):
            return await asyncio.to_thread(answer_self_history, text)
        # Không phải lệnh -> nối thẳng vào bộ não hội thoại của AURA
        # (xử lý được cả "duyệt"/"y"/"huỷ"/"ngủ đông" + chat), y như bong bóng mascot.
        return await self._ask_aura(text)

    # ------------------------------------------------------------------ #
    async def _ask_aura(self, text: str) -> str:
        """Nối vào bộ não hội thoại chung của AURA (orchestrator.process_message):
        xử lý duyệt 'y'/'huỷ', 'ngủ đông', cập nhật hồ sơ VÀ chat — đúng thứ Sếp
        gõ ở bong bóng mascot. Không có orchestrator thì rơi về cloud brain trực tiếp."""
        orch = getattr(self._daemon, "orchestrator", None)
        if orch is not None and hasattr(orch, "process_message"):
            try:
                reply = await asyncio.to_thread(orch.process_message, text, audit=False)
                if reply:
                    return str(reply)
            except Exception as exc:  # noqa: BLE001 — hỏng thì thử cloud thẳng
                logger.warning("orchestrator.process_message lỗi: %s", redact(str(exc)))
        return await self._chat_cloud(text)

    async def _describe_screen(self) -> str:
        """Đọc desktop cục bộ và báo trung thực. Dùng chung 'mắt sạch' với bong
        bóng mascot: Gemini vision đọc thẳng ảnh, tự lùi về OCR local khi offline."""
        from core.desktop_operator import describe_screen_smart

        return await asyncio.to_thread(describe_screen_smart)

    async def _chat_cloud(self, text: str) -> str:
        """Dự phòng: hỏi thẳng cloud brain (khi chưa có orchestrator)."""
        engines = self._get_engines()
        cloud = engines[1] if engines else None
        if cloud is None:
            return "⚠️ Chưa cấu hình cloud brain nên AURA chưa chat tự do được."
        persona = getattr(settings, "briefing_persona", "alpha")
        sys = (
            "Bạn là AURA — trợ lý AI riêng của Sếp, trả lời bằng "
            "tiếng Việt, ngắn gọn, thực dụng. "
            + ("Giọng đanh đá, thẳng thắn nhưng có tâm." if persona == "alpha"
               else "Giọng hiền, thân tình.")
        )
        result = await asyncio.to_thread(
            cloud.complete,
            [{"role": "user", "content": text}],
            system_prompt=sys,
            max_tokens=700,
        )
        if result.get("ok"):
            return result.get("text", "").strip() or "(AURA không có gì để nói)"
        return f"⚠️ Cloud brain lỗi: {result.get('error', 'không rõ')}"

    def _get_engines(self):
        if self._engines is None:
            try:
                from core.llm import build_engines
                self._engines = build_engines()
            except Exception as exc:  # noqa: BLE001
                logger.warning("Dựng engine cho Telegram chat lỗi: %s", redact(str(exc)))
                self._engines = (None, None)
        return self._engines

    async def _delayed_restart(self) -> None:
        await asyncio.sleep(2)
        from core.updater import restart_aura
        restart_aura("Lệnh /capnhat từ Telegram")


    # ------------------------------------------------------------------ #

    def _fmt_status(self) -> str:
        frozen = getattr(self._daemon, "aura_frozen", False)
        tasks = getattr(self._daemon, "_tasks", [])
        names = ", ".join(t.get_name() for t in tasks) or "(không)"
        ram = None
        try:
            ram = self._daemon._ram_percent()
        except Exception:  # noqa: BLE001
            pass
        ram_s = f"{ram*100:.0f}%" if isinstance(ram, float) else "?"
        state = "💤 ĐANG NGỦ ĐÔNG" if frozen else "🟢 ĐANG THỨC"
        return f"{state}\nRAM hệ thống: {ram_s}\nNhịp đang chạy: {names}"

    @staticmethod
    def _cashflow_status() -> str:
        from core.cashflow import summary

        data = summary()
        fmt = lambda values: " · ".join(
            f"{float(amount):,.0f} {currency}" for currency, amount in values.items()
        ) or "0"
        return (
            "💰 DÒNG TIỀN AURA\n"
            f"Chờ đối soát: {data.get('pending_count', 0)} · {fmt(data.get('pending_by_currency', {}))}\n"
            f"Đã ghi sổ: {data.get('confirmed_count', 0)} · {fmt(data.get('confirmed_by_currency', {}))}\n\n"
            "Báo có mới sẽ tự gửi vào Telegram; AURA chỉ cộng doanh thu sau khi bạn xác nhận ở desktop."
        )

    @staticmethod
    def _growth_status() -> str:
        try:
            from core.revenue_pipeline import get_pipeline_summary
            from core.lead_collector import get_current_verified_leads
            from core.manual_publish_desk import get_unified_action_box_items
            from core.market_test import get_or_create_experiment_cohort

            experiment_id = str(
                get_or_create_experiment_cohort().get("experiment_id") or ""
            ).strip()
            leads, batch_id = get_current_verified_leads(
                expected_experiment_id=experiment_id
            )
            if batch_id == "STALE" or not leads:
                leads_str = "0 lead live (Cần chạy cào mới)"
            else:
                leads_str = f"{len(leads)} lead live [Batch: {batch_id}]"

            p_summary = get_pipeline_summary(experiment_id)
            rev_map = p_summary.get("verified_revenue_by_currency", {})
            rev_str = " · ".join(f"{amt:,.0f} {curr}" for curr, amt in rev_map.items()) or "0 VNĐ"

            unified_actions = get_unified_action_box_items(
                experiment_id=experiment_id
            )

            lines = [
                "🚀 AURA GROWTH OPERATOR (ACTION BOX 1%)",
                f"🧪 Experiment: {experiment_id}",
                f"📌 Lead live hiện tại (M7): {leads_str}",
                f"💼 Pipeline: {p_summary.get('qualified', 0)} qualified · "
                f"{p_summary.get('ever_pitched', 0)} ever pitched · "
                f"{p_summary.get('ever_replied', 0)} ever replied · "
                f"{p_summary.get('ever_pilot_paid', 0)} ever pilot paid",
                f"💰 Doanh thu xác minh cashflow: {rev_str}",
                "",
                f"⚡ HỘP HÀNH ĐỘNG 1% ĐANG CHỜ SẾP DUYỆT ({len(unified_actions)} mục):",
            ]

            if not unified_actions:
                lines.append("📭 Chưa có hành động đăng/duyệt nào đang chờ.")
            else:
                for idx, act in enumerate(unified_actions[:5], 1):
                    lines.append(
                        f"{idx}. [{act.get('platform')}] {act.get('title')}\n"
                        f"   👉 Thao tác: {act.get('action')}\n"
                        f"   🔗 Link: {act.get('publish_url')}"
                    )
                lines.append("\nAURA vận hành 99%. Sếp bấm link trên để thực thi 1%!")
            return "\n".join(lines)
        except Exception as exc:  # noqa: BLE001
            return f"⚠️ Growth status lỗi: {exc}"

    # ------------------------------------------------------------------ #
    @staticmethod
    def _one_percent_status() -> str:
        from core.one_percent_operator import OnePercentRevenueOperator

        data = OnePercentRevenueOperator().status()
        session = data.get("payhip_session") or {}
        session_s = "đã xác minh" if session.get("ok") else "chưa xác minh"
        enabled = "BẬT" if data.get("autonomy_enabled") else "CHƯA BẬT"
        return (
            "🤖 1% CHỦ / 99% AURA\n"
            f"Tự vận hành: {enabled}\n"
            f"Phiên Payhip: {session_s}\n"
            f"Kho PDF: {data.get('remaining_products', 0)} chưa đăng / "
            f"{data.get('inventory_total', 0)} tổng\n"
            f"Nhịp đăng: tối đa {data.get('daily_publish_cap', 1)} sản phẩm/ngày, "
            f"${float(data.get('price_usd', 0)):.2f}/sản phẩm\n\n"
            f"Việc của Chủ: {data.get('one_percent_task', '')}"
        )

    @staticmethod
    def _activate_one_percent() -> str:
        """Một lệnh Telegram có chủ ý: xác nhận payout + cho phép công khai ngay."""
        from core.one_percent_operator import OnePercentRevenueOperator

        operator = OnePercentRevenueOperator()
        operator.activate_after_owner_setup()
        report = operator.run_once()
        return (
            "✅ Đã bật chế độ 1% Chủ / 99% AURA. Lệnh này đồng nghĩa bạn xác nhận "
            "Payhip và kênh nhận tiền đã hoàn tất; AURA được phép công khai sản phẩm nguyên gốc "
            "theo nhịp an toàn.\n\n"
            + str(report.get("message") or "AURA sẽ tự kiểm tra ở nhịp kế tiếp.")
        )

    @staticmethod
    def _disable_one_percent() -> str:
        from core.one_percent_operator import OnePercentRevenueOperator

        OnePercentRevenueOperator().disable_autonomy()
        return "⏸️ Đã dừng AURA đăng sản phẩm mới. Các sản phẩm đã công khai không bị thay đổi."

    # ------------------------------------------------------------------ #
    def _enqueue_write(self, n: int) -> str:
        """Đẩy job story.factory viết tiếp BỘ MỚI NHẤT (giống nhịp autopilot)."""
        try:
            series_list = self._daemon._autopilot_series()
        except Exception as exc:  # noqa: BLE001
            return f"⚠️ Không lấy được danh sách bộ truyện: {exc}"
        if not series_list:
            return "📭 Chưa có bộ truyện nào có bible để viết tiếp."
        series = series_list[0]
        try:
            from factory import queue as _fq
            from factory.models import JobRecord
            busy = any(
                j.tool == "story.factory" and j.state in ("queued", "running")
                and str(j.params.get("series") or "") == series
                for j in _fq.list_jobs(limit=100)
            )
            if busy:
                return f"⏳ Bộ '{series}' đang có job viết chạy — chờ xong đã nhé."
            _fq.enqueue(JobRecord(tool="story.factory", params={
                "series": series,
                "world": "(bộ đang chạy — tiếp bible sẵn có)",
                "chapters": n,
                "words": int(getattr(settings, "story_autopilot_words", 1800)),
            }))
            return (f"✍️ Đã giao AURA viết thêm {n} chương cho bộ '{series}'. "
                    "Xưởng chạy 1 job nặng/lúc; xong sẽ nằm ở data/outputs/story/.")
        except Exception as exc:  # noqa: BLE001
            return f"⚠️ Đẩy job viết lỗi: {exc}"

    # ------------------------------------------------------------------ #
    def _assist_publish(self, platform: str, chapter: int | None) -> str:
        """Chuẩn bị đăng lên `platform`: chép chương + mở trang viết trên máy."""
        try:
            series_list = self._daemon._autopilot_series()
        except Exception as exc:  # noqa: BLE001
            return f"⚠️ Không lấy được bộ truyện: {exc}"
        if not series_list:
            return "📭 Chưa có bộ truyện nào để đăng."
        try:
            from core.publish_hand import assist
            return assist(platform, series_list[0], chapter)
        except FileNotFoundError as exc:
            return f"⚠️ {exc}"
        except Exception as exc:  # noqa: BLE001
            return f"⚠️ Chuẩn bị đăng {platform} lỗi: {exc}"

    # ------------------------------------------------------------------ #
    def _assist_new_story(self, platform: str) -> str:
        """Chuẩn bị TẠO TRUYỆN MỚI trên nền: chép văn án + mở trang tạo truyện."""
        try:
            series_list = self._daemon._autopilot_series()
        except Exception as exc:  # noqa: BLE001
            return f"⚠️ Không lấy được bộ truyện: {exc}"
        if not series_list:
            return "📭 Chưa có bộ truyện nào."
        try:
            from core.publish_hand import assist_new_story
            return assist_new_story(platform, series_list[0])
        except Exception as exc:  # noqa: BLE001
            return f"⚠️ Chuẩn bị tạo truyện {platform} lỗi: {exc}"


# ---------------------------------------------------------------------------
# Tiện ích đọc + tóm báo cáo (module-level, không cần state)
# ---------------------------------------------------------------------------
def _load(name: str) -> dict[str, Any] | None:
    p = _FEEDBACK / name
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Đọc %s lỗi: %s", name, exc)
        return None


def _fmt_jobs() -> str:
    d = _load("job_scout_last.json")
    if not d or not d.get("items"):
        return "📭 Chưa có tin việc có thể ứng tuyển."
    try:
        from skills.scouts.job_scout import _is_real_listing

        items = [it for it in d["items"] if _is_real_listing(it)][:8]
    except Exception:  # noqa: BLE001 — fail closed nếu bộ lọc không nạp được
        items = [it for it in d["items"] if it.get("actionable") is True][:8]
    if not items:
        return "📭 Chưa có tin việc có thể ứng tuyển; các bài báo tuyển dụng đã bị loại."
    lines = ["💼 TIN VIỆC CÓ THỂ ỨNG TUYỂN mới nhất:"]
    for i, it in enumerate(items, 1):
        title = (it.get("title") or "?").strip()
        score = it.get("score")
        tag = f" [{score:.2f}]" if isinstance(score, (int, float)) else ""
        lines.append(f"{i}. {title}{tag}\n{it.get('url', '')}")
    return "\n".join(lines)


def _fmt_trend() -> str:
    d = _load("trend_radar_last.json")
    if not d or not d.get("top"):
        return "📭 Chưa có brief trend nào."
    top = d["top"][:6]
    head = "📡 TREND NÓNG (hợp góc của Sếp):"
    if d.get("weak"):
        head += " ⚠️ tín hiệu yếu"
    lines = [head]
    for i, t in enumerate(top, 1):
        title = (t.get("title") or "?").strip()
        fit = t.get("fit")
        tag = f" (hợp {fit:.2f})" if isinstance(fit, (int, float)) else ""
        lines.append(f"{i}. {title}{tag}")
    return "\n".join(lines)


def _fmt_crew() -> str:
    import time
    d = _load("crew_state.json")
    last = (d or {}).get("last", {})
    if not last:
        return "📭 Tổ công nhân chưa chạy lượt nào."
    now = time.time()
    names = {"job": "Việc làm", "news": "Tin tức", "janitor": "Dọn rác", "radar": "Trend"}
    lines = ["👷 TỔ CÔNG NHÂN — lần chạy gần nhất:"]
    for key, label in names.items():
        ts = last.get(key)
        if not ts:
            lines.append(f"• {label}: chưa chạy")
            continue
        hrs = (now - ts) / 3600
        lines.append(f"• {label}: {hrs:.1f} giờ trước")
    return "\n".join(lines)


def _split(text: str, size: int) -> list[str]:
    """Cắt tin dài theo ranh giới dòng, mỗi mảnh <= size."""
    if len(text) <= size:
        return [text]
    out, cur = [], ""
    for line in text.split("\n"):
        if len(cur) + len(line) + 1 > size:
            if cur:
                out.append(cur)
            cur = line[:size] if len(line) > size else line
        else:
            cur = f"{cur}\n{line}" if cur else line
    if cur:
        out.append(cur)
    return out


__all__ = ["TelegramMessenger"]
