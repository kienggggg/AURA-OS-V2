"""Sổ báo có cho AURA: nhận tín hiệu tiền vào, phát loa và đối soát trước khi ghi doanh thu.

Một tin nhắn/thông báo ngân hàng không phải bằng chứng kế toán tuyệt đối. Vì vậy AURA
ghi nó là ``observed`` trước, phát báo có nhưng không cộng vào sổ doanh thu; chỉ khi
chủ xác nhận hoặc một tích hợp chính thức được thêm sau này mới chuyển thành ``confirmed``.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import requests

from core.config import settings

logger = logging.getLogger(__name__)

_PATH = settings.ledger_dir / "cashflow.jsonl"
_LOCK = threading.RLock()
_STATUSES = frozenset({"observed", "confirmed", "ignored"})


def _ledger_path(path: Path | None = None) -> Path:
    return path or _PATH


def _read(path: Path | None = None) -> dict[str, dict[str, Any]]:
    ledger = _ledger_path(path)
    if not ledger.is_file():
        return {}
    rows: dict[str, dict[str, Any]] = {}
    try:
        lines = ledger.read_text(encoding="utf-8").splitlines()
    except OSError:
        return rows
    for line in lines:
        try:
            row = json.loads(line)
            event = row["event"]
            event_id = str(event["id"])
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            continue
        rows[event_id] = event
    return rows


def get_confirmed_cashflow(event_id: str, path: Path | None = None) -> dict[str, Any] | None:
    """Trả về dict sự kiện cashflow NẾU sự kiện tồn tại và status == 'confirmed'."""
    with _LOCK:
        rows = _read(path)
        event = rows.get(str(event_id))
        if event and str(event.get("status") or "") == "confirmed":
            return event
        return None


def _append(event: dict[str, Any], action: str, path: Path | None = None) -> dict[str, Any]:
    ledger = _ledger_path(path)
    ledger.parent.mkdir(parents=True, exist_ok=True)
    with ledger.open("a", encoding="utf-8") as file:
        file.write(json.dumps({"ts": int(time.time()), "action": action, "event": event}, ensure_ascii=False) + "\n")
    return event


def _normal(value: str, limit: int = 300) -> str:
    return " ".join(str(value or "").strip().split())[:limit]


def _spoken_amount(amount: float, currency: str) -> str:
    if currency.upper() == "VND":
        return f"AURA báo có {amount:,.0f} đồng. Mời kiểm tra dòng tiền trên máy."
    return f"AURA báo có {amount:,.2f} {currency.upper()}. Mời kiểm tra dòng tiền trên máy."


def announce_incoming(amount: float, currency: str) -> None:
    """Phát chuông + đọc số tiền qua loa Windows, không làm lộ người gửi/thông tin tài khoản."""
    if not settings.cashflow_voice_alert_enabled or not sys.platform.startswith("win"):
        return
    message = _spoken_amount(amount, currency)
    try:
        import winsound

        winsound.MessageBeep(winsound.MB_ICONASTERISK)
    except Exception:  # noqa: BLE001 — loa không làm hỏng việc ghi sổ
        pass
    try:
        # Script cố định; tiền được truyền như một argument, không được ghép vào câu lệnh PowerShell.
        script = (
            "Add-Type -AssemblyName System.Speech; "
            "$speaker = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            "$speaker.Speak($args[0])"
        )
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        subprocess.Popen(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-Command", script, message],
            creationflags=flags,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Không phát được loa báo có: %s", exc)


def notify_telegram_incoming(event: dict[str, Any]) -> None:
    """Gửi báo có gọn qua Telegram của chính Chủ; không gửi mã tham chiếu/số tài khoản."""
    if not getattr(settings, "cashflow_telegram_alert_enabled", True):
        return
    if not getattr(settings, "telegram_enabled", False):
        return
    token = settings.telegram_bot_token
    owner = str(getattr(settings, "telegram_owner_id", "") or "").strip()
    if not token or not owner:
        return
    amount = float(event.get("amount") or 0)
    currency = str(event.get("currency") or "VND").upper()
    amount_text = f"{amount:,.0f}" if currency == "VND" else f"{amount:,.2f}"
    raw_source = str(event.get("source") or "ngân hàng")
    source = "MB Bank" if raw_source.casefold() in {"mbbank", "mb_bank", "mbbank_push"} else raw_source.replace("_", " ").title()
    description = _normal(str(event.get("description") or "Báo có mới"), 180)
    message = (
        f"💰 {source} báo có\n+{amount_text} {currency}\n"
        f"Nội dung: {description}\n\n"
        "AURA đã đưa vào Dòng tiền, đang chờ đối soát — chưa cộng vào doanh thu."
    )
    try:
        requests.post(
            f"https://api.telegram.org/bot{token.get_secret_value()}/sendMessage",
            data={"chat_id": owner, "text": message, "disable_web_page_preview": "true"},
            timeout=20,
        )
    except requests.RequestException as exc:
        logger.warning("Không gửi được Telegram báo có: %s", exc)


def list_events(limit: int = 200, path: Path | None = None) -> list[dict[str, Any]]:
    events = list(_read(path).values())
    events.sort(key=lambda item: int(item.get("updated_at") or item.get("received_at") or 0), reverse=True)
    return events[:max(1, limit)]


def capture_incoming(
    *,
    amount: float | int | str,
    currency: str = "VND",
    source: str = "bank_notification",
    reference: str = "",
    description: str = "",
    received_at: int | float | str | None = None,
    path: Path | None = None,
    announcer: Callable[[float, str], None] | None = None,
    notifier: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Ghi nhận một báo có mới và phát loa một lần; không tự cộng doanh thu."""
    try:
        parsed_amount = float(amount)
    except (TypeError, ValueError) as exc:
        raise ValueError("Số tiền báo có phải là một số hợp lệ.") from exc
    if parsed_amount <= 0:
        raise ValueError("Số tiền báo có phải lớn hơn 0.")
    try:
        observed_at = int(float(received_at)) if received_at is not None else int(time.time())
    except (TypeError, ValueError):
        observed_at = int(time.time())
    clean_source = _normal(source, 80).casefold() or "bank_notification"
    clean_reference = _normal(reference, 160)
    clean_currency = _normal(currency, 8).upper() or "VND"
    clean_description = _normal(description, 300)

    with _LOCK:
        for old in _read(path).values():
            if clean_reference and old.get("source") == clean_source and old.get("reference") == clean_reference:
                return old
        now = int(time.time())
        event = {
            "id": uuid.uuid4().hex[:12],
            "kind": "incoming",
            "status": "observed",
            "amount": parsed_amount,
            "currency": clean_currency,
            "source": clean_source,
            "reference": clean_reference,
            "description": clean_description,
            "received_at": observed_at,
            "created_at": now,
            "updated_at": now,
            "income_recorded": False,
        }
        _append(event, "incoming_observed", path)

    try:
        (announcer or announce_incoming)(parsed_amount, clean_currency)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Bộ báo có lỗi sau khi đã ghi event: %s", exc)
    try:
        (notifier or notify_telegram_incoming)(event)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Bộ báo Telegram lỗi sau khi đã ghi event: %s", exc)
    return event


def confirm(
    event_id: str,
    *,
    confirmed_by_owner: bool,
    product_line: str = "khac",
    note: str = "",
    path: Path | None = None,
    income_recorder: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Đối soát báo có rồi mới ghi một khoản thật vào sổ thu nhập tổng."""
    if not confirmed_by_owner:
        raise ValueError("Chỉ ghi doanh thu sau khi Chủ xác nhận tiền đã về.")
    with _LOCK:
        event = _read(path).get(str(event_id))
        if event is None:
            raise KeyError("Không tìm thấy báo có.")
        if event.get("status") == "confirmed":
            return event
        if event.get("status") != "observed":
            raise ValueError("Chỉ có thể xác nhận một báo có đang chờ đối soát.")
        recorder = income_recorder
        if recorder is None:
            from factory.ledger import record as recorder
        details = _normal(note, 300)
        source_note = f"cashflow:{event['id']} · {event.get('source') or 'bank'}"
        if details:
            source_note += f" · {details}"
        recorder(
            product_line=_normal(product_line, 80) or "khac",
            item=event.get("description") or "Báo có ngân hàng",
            amount=float(event["amount"]),
            direction="in",
            note=source_note,
            currency=str(event.get("currency") or "VND"),
        )
        event["status"] = "confirmed"
        event["income_recorded"] = True
        event["updated_at"] = int(time.time())
        _append(event, "confirmed_by_owner", path)
        return event


def ignore(event_id: str, *, confirmed_by_owner: bool, path: Path | None = None) -> dict[str, Any]:
    if not confirmed_by_owner:
        raise ValueError("Chỉ Chủ mới có thể bỏ qua một báo có.")
    with _LOCK:
        event = _read(path).get(str(event_id))
        if event is None:
            raise KeyError("Không tìm thấy báo có.")
        if event.get("status") != "observed":
            raise ValueError("Báo có này không còn chờ đối soát.")
        event["status"] = "ignored"
        event["updated_at"] = int(time.time())
        _append(event, "ignored_by_owner", path)
        return event


def summary(path: Path | None = None) -> dict[str, Any]:
    pending_by_currency: dict[str, float] = {}
    confirmed_by_currency: dict[str, float] = {}
    pending = confirmed = 0
    for event in list_events(limit=10_000, path=path):
        currency = str(event.get("currency") or "VND")
        amount = float(event.get("amount") or 0)
        if event.get("status") == "observed":
            pending += 1
            pending_by_currency[currency] = pending_by_currency.get(currency, 0.0) + amount
        elif event.get("status") == "confirmed":
            confirmed += 1
            confirmed_by_currency[currency] = confirmed_by_currency.get(currency, 0.0) + amount
    return {
        "pending_count": pending,
        "confirmed_count": confirmed,
        "pending_by_currency": pending_by_currency,
        "confirmed_by_currency": confirmed_by_currency,
    }


def dashboard_data(path: Path | None = None) -> dict[str, Any]:
    return {"summary": summary(path), "events": list_events(path=path)}


__all__ = [
    "announce_incoming", "capture_incoming", "confirm", "dashboard_data", "ignore", "list_events",
    "notify_telegram_incoming", "summary",
]