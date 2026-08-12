"""Bộ vận hành ``1% Chủ / 99% AURA`` cho sản phẩm số.

Mục tiêu của module là để AURA tự làm phần vận hành lặp lại: kiểm tra phiên bán,
chọn một PDF nguyên gốc chưa đăng, công khai theo nhịp giới hạn và lưu audit.
Nó không thể (và không được phép) xác minh danh tính, liên kết payout hay ghi nhận
doanh thu khi chưa có giao dịch thật. Chủ chỉ làm bước pháp lý/tài chính một lần
trên Payhip, sau đó xác nhận bằng Telegram để cho phép AURA vận hành.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from core.config import settings

logger = logging.getLogger(__name__)

_STATE_PATH = settings.ledger_dir / "one_percent_operator.json"
_PRODUCTS_PATH = settings.ledger_dir / "payhip_products.jsonl"
_STATE_LOCK = threading.RLock()

_DEFAULT_STATE: dict[str, Any] = {
    "version": 1,
    "owner_payout_confirmed": False,
    "autonomy_enabled": False,
    "activated_at": 0,
    "last_session": {},
    "last_run_at": 0,
    "last_published_at": 0,
    "last_error": "",
    "last_notice_key": "",
    "last_notice_at": 0,
    "history": [],
}


def _copy_default_state() -> dict[str, Any]:
    return {**_DEFAULT_STATE, "last_session": {}, "history": []}


def _load_state(path: Path) -> dict[str, Any]:
    state = _copy_default_state()
    if not path.is_file():
        return state
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        logger.warning("Không đọc được trạng thái One-percent operator: %s", exc)
        return state
    if isinstance(loaded, dict):
        state.update({key: value for key, value in loaded.items() if key in state})
    if not isinstance(state.get("last_session"), dict):
        state["last_session"] = {}
    if not isinstance(state.get("history"), list):
        state["history"] = []
    return state


def _save_state(state: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def _append_history(state: dict[str, Any], event: str, *, ts: int, detail: str = "") -> None:
    history = list(state.get("history") or [])
    history.append({"ts": ts, "event": event, "detail": detail})
    state["history"] = history[-50:]


def _read_product_rows(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return rows
    for line in lines:
        try:
            row = json.loads(line)
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _append_product_row(row: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(row, ensure_ascii=False) + "\n")


def _product_key(product: Path) -> str:
    return str(product.resolve()).casefold()


class OnePercentRevenueOperator:
    """Điều phối bán sản phẩm số với một cổng xác nhận duy nhất của chủ tài khoản."""

    def __init__(
        self,
        *,
        state_path: Path | None = None,
        products_path: Path | None = None,
        inventory: Callable[[], list[Path]] | None = None,
        session_checker: Callable[[], dict[str, Any]] | None = None,
        publisher: Callable[[Path, float, bool], dict[str, Any]] | None = None,
        now: Callable[[], int] | None = None,
        price_usd: float | None = None,
        daily_publish_cap: int | None = None,
    ) -> None:
        self.state_path = state_path or _STATE_PATH
        self.products_path = products_path or _PRODUCTS_PATH
        self._inventory = inventory or self._default_inventory
        self._session_checker = session_checker or self._default_session_checker
        self._publisher = publisher or self._default_publisher
        self._now = now or (lambda: int(time.time()))
        self.price_usd = float(price_usd if price_usd is not None else settings.one_percent_product_price_usd)
        self.daily_publish_cap = int(
            daily_publish_cap if daily_publish_cap is not None else settings.one_percent_daily_publish_cap
        )

    @staticmethod
    def _default_inventory() -> list[Path]:
        from core.payhip_bot import list_coloring_books

        return list_coloring_books()

    @staticmethod
    def _default_session_checker() -> dict[str, Any]:
        from core.payhip_bot import check_seller_session

        return check_seller_session()

    @staticmethod
    def _default_publisher(pdf_file: Path, price: float, publish: bool) -> dict[str, Any]:
        from core.payhip_bot import upload_product

        return upload_product(pdf_file, price=price, publish=publish)

    def activate_after_owner_setup(self) -> dict[str, Any]:
        """Ghi rõ chủ đã hoàn tất payout và cho phép AURA tự vận hành công khai.

        Hàm này không giả vờ kiểm tra payout. Nó chỉ lưu xác nhận có chủ ý của người
        sở hữu tài khoản, là điều kiện trước khi bất kỳ sản phẩm nào được công khai.
        """
        with _STATE_LOCK:
            now = self._now()
            state = _load_state(self.state_path)
            state["owner_payout_confirmed"] = True
            state["autonomy_enabled"] = True
            state["activated_at"] = now
            state["last_error"] = ""
            _append_history(state, "owner_setup_confirmed_and_autonomy_enabled", ts=now)
            _save_state(state, self.state_path)
            return self._status_from(state)

    def disable_autonomy(self) -> dict[str, Any]:
        """Dừng công khai mới ngay lập tức; không đụng các sản phẩm đã tồn tại."""
        with _STATE_LOCK:
            now = self._now()
            state = _load_state(self.state_path)
            state["autonomy_enabled"] = False
            _append_history(state, "autonomy_disabled_by_owner", ts=now)
            _save_state(state, self.state_path)
            return self._status_from(state)

    def status(self) -> dict[str, Any]:
        """Đọc trạng thái cục bộ; không mở trình duyệt hay thay đổi trạng thái bên ngoài."""
        with _STATE_LOCK:
            return self._status_from(_load_state(self.state_path))

    def _inventory_items(self) -> list[Path]:
        try:
            return [Path(item) for item in self._inventory() if Path(item).is_file()]
        except Exception as exc:  # noqa: BLE001 - trạng thái phải chịu được kho file lỗi
            logger.warning("Không đọc được kho sản phẩm One-percent: %s", exc)
            return []

    def _published_rows(self) -> list[dict[str, Any]]:
        return [
            row for row in _read_product_rows(self.products_path)
            if str(row.get("status") or "") == "published"
        ]

    def _status_from(self, state: dict[str, Any]) -> dict[str, Any]:
        inventory = self._inventory_items()
        published = self._published_rows()
        published_keys = {str(row.get("product_key") or "") for row in published}
        remaining = [product for product in inventory if _product_key(product) not in published_keys]
        session = dict(state.get("last_session") or {})
        session_known = bool(session)
        session_active = bool(session.get("ok"))

        if not state.get("owner_payout_confirmed"):
            one_percent_task = (
                "Liên kết Payhip với phương thức nhận tiền của bạn một lần; xong nhắn /thu1san."
            )
            stage = "needs_owner_setup"
        elif not state.get("autonomy_enabled"):
            one_percent_task = "AURA đang dừng đăng mới theo lệnh của bạn. Nhắn /thu1san để chạy lại."
            stage = "paused_by_owner"
        elif session_known and not session_active:
            one_percent_task = (
                "Phiên Payhip chưa vào được dashboard; chỉ cần đăng nhập lại khi AURA báo lỗi phiên."
            )
            stage = "needs_payhip_session"
        elif not remaining:
            one_percent_task = "AURA đã hết PDF nguyên gốc chưa đăng; cần bổ sung sản phẩm mới trước khi bán tiếp."
            stage = "inventory_exhausted"
        else:
            one_percent_task = "Không cần thao tác thường xuyên: AURA tự kiểm tra và đăng tối đa một sản phẩm/ngày."
            stage = "operating" if session_active else "awaiting_first_preflight"

        return {
            "stage": stage,
            "owner_payout_confirmed": bool(state.get("owner_payout_confirmed")),
            "autonomy_enabled": bool(state.get("autonomy_enabled")),
            "payhip_session": session,
            "inventory_total": len(inventory),
            "published_total": len(published),
            "remaining_products": len(remaining),
            "daily_publish_cap": self.daily_publish_cap,
            "price_usd": self.price_usd,
            "last_published_at": int(state.get("last_published_at") or 0),
            "last_error": str(state.get("last_error") or ""),
            "one_percent_task": one_percent_task,
            "history": list(state.get("history") or [])[-10:],
        }

    @staticmethod
    def _notice(state: dict[str, Any], key: str, message: str, now: int) -> bool:
        """Không lặp cùng một lời nhắc quá một lần/ngày."""
        previous_key = str(state.get("last_notice_key") or "")
        previous_at = int(state.get("last_notice_at") or 0)
        notify = key != previous_key or now - previous_at >= 24 * 3600
        if notify:
            state["last_notice_key"] = key
            state["last_notice_at"] = now
        return notify

    def _result(
        self, state: dict[str, Any], *, outcome: str, message: str, notify: bool
    ) -> dict[str, Any]:
        return {
            "outcome": outcome,
            "message": message,
            "notify": notify,
            "status": self._status_from(state),
        }

    def run_once(self) -> dict[str, Any]:
        """Thực hiện một nhịp vận hành.

        Không có xác nhận payout + bật autonomy thì hàm dừng trước *mọi* thao tác mạng.
        Khi đã bật, nó vẫn kiểm tra phiên Payhip trước, chỉ đăng PDF chưa có trong sổ
        công khai và giới hạn một ngày để không spam thị trường.
        """
        with _STATE_LOCK:
            now = self._now()
            state = _load_state(self.state_path)
            state["last_run_at"] = now

            if not state.get("owner_payout_confirmed") or not state.get("autonomy_enabled"):
                message = (
                    "💳 1% việc của Chủ: hoàn tất Payhip + kênh nhận tiền, rồi nhắn /thu1san. "
                    "AURA chưa đăng sản phẩm nào."
                )
                notify = self._notice(state, "owner_setup_required", message, now)
                _save_state(state, self.state_path)
                return self._result(state, outcome="waiting_for_owner_setup", message=message, notify=notify)

            try:
                session = dict(self._session_checker() or {})
            except Exception as exc:  # noqa: BLE001
                session = {"ok": False, "reason": "session_check_failed", "detail": str(exc)}
            state["last_session"] = session
            if not session.get("ok"):
                state["last_error"] = str(session.get("reason") or "session_check_failed")
                message = (
                    "⚠️ AURA chưa vào được Payhip dashboard nên đã dừng, không đăng gì. "
                    "Khi tiện, đăng nhập lại Payhip rồi AURA sẽ tự tiếp tục."
                )
                notify = self._notice(state, "payhip_session_unavailable", message, now)
                _append_history(state, "payhip_session_unavailable", ts=now, detail=state["last_error"])
                _save_state(state, self.state_path)
                return self._result(state, outcome="payhip_session_unavailable", message=message, notify=notify)

            inventory = self._inventory_items()
            published = self._published_rows()
            published_keys = {str(row.get("product_key") or "") for row in published}
            candidates = [product for product in inventory if _product_key(product) not in published_keys]
            if not candidates:
                message = "📦 AURA đã đăng hết PDF nguyên gốc hiện có; không có sản phẩm mới để công khai."
                notify = self._notice(state, "inventory_exhausted", message, now)
                _append_history(state, "inventory_exhausted", ts=now)
                _save_state(state, self.state_path)
                return self._result(state, outcome="inventory_exhausted", message=message, notify=notify)

            today = datetime.fromtimestamp(now).date()
            published_today = sum(
                1
                for row in published
                if int(row.get("ts") or 0) and datetime.fromtimestamp(int(row["ts"])).date() == today
            )
            if published_today >= self.daily_publish_cap:
                message = "⏳ AURA đã đạt nhịp đăng sản phẩm hôm nay; lượt tiếp theo sẽ tự chạy vào ngày mới."
                _save_state(state, self.state_path)
                return self._result(state, outcome="daily_publish_cap_reached", message=message, notify=False)

            product = candidates[0]
            try:
                result = dict(self._publisher(product, self.price_usd, True) or {})
            except Exception as exc:  # noqa: BLE001
                result = {"success": False, "reason": str(exc)}
            if not result.get("success") or result.get("status") != "published":
                reason = str(result.get("reason") or "publication_not_confirmed")
                state["last_error"] = reason
                message = (
                    "⚠️ AURA không xác nhận được việc công khai sản phẩm Payhip nên không ghi là đã đăng. "
                    f"Lý do: {reason}"
                )
                notify = self._notice(state, f"publication_failed:{reason}", message, now)
                _append_history(state, "publication_failed", ts=now, detail=reason)
                _save_state(state, self.state_path)
                return self._result(state, outcome="publication_failed", message=message, notify=notify)

            row = {
                "ts": now,
                "platform": "payhip",
                "status": "published",
                "product_key": _product_key(product),
                "file": str(product),
                "title": str(result.get("title") or product.stem),
                "price_usd": self.price_usd,
            }
            _append_product_row(row, self.products_path)
            state["last_published_at"] = now
            state["last_error"] = ""
            _append_history(state, "product_published", ts=now, detail=str(product.name))
            _save_state(state, self.state_path)
            message = (
                f"🛍️ AURA đã công khai sản phẩm Payhip: {row['title']} (${self.price_usd:.2f}). "
                "Đây là sản phẩm đã đăng, chưa phải doanh thu; tiền chỉ được ghi khi có giao dịch thật."
            )
            return self._result(state, outcome="published", message=message, notify=True)


def status() -> dict[str, Any]:
    return OnePercentRevenueOperator().status()


__all__ = ["OnePercentRevenueOperator", "status"]
