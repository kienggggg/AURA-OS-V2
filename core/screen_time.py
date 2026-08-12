"""
core/screen_time.py
===================
QUẢN LÝ GIỜ MÀN HÌNH — đo tổng thời gian màn hình SÁNG mỗi ngày trên laptop và
điện thoại, quá hạn thì CƯỠNG CHẾ TẮT MÁY.

Sếp 30/07/2026: *"làm cho AURA cái tính năng quản lý thời gian sử dụng điện thoại,
laptop đi, phải cưỡng chế tắt máy mới được"*.

KHÁC GÌ HEALTH GUARD? Health Guard đo **giờ ngồi LIÊN TỤC** (50 phút thì khoá màn 5
phút) — nghỉ xong là đồng hồ về 0, ngồi cả ngày vẫn được. Module này đo **TỔNG giờ
màn hình sáng CẢ NGÀY**, cộng dồn qua mọi phiên, và mức phạt nặng hơn: tắt máy.
Hai thứ bổ sung nhau, không thay thế.

AN TOÀN — tắt máy là hành động PHÁ HUỶ (mất việc chưa lưu):
- Mặc định **TẮT**. Sếp phải chủ động bật (`SCREEN_TIME_ENFORCE=true`).
- Cảnh báo trước nhiều mốc, rồi đếm ngược dài đủ để lưu việc.
- Đang render video/việc nặng thì **HOÃN**, không cắt ngang.
- Sếp luôn huỷ được bằng `shutdown /a` — có ghi lại, nhưng không khoá cứng. Máy là
  của Sếp; AURA nhắc chứ không giam.
"""

from __future__ import annotations

import ctypes
import json
import logging
import os
import subprocess
import time
from ctypes import wintypes
from datetime import date, datetime
from pathlib import Path
from typing import Any

from core.config import PROJECT_ROOT, settings

logger = logging.getLogger("aura.screen_time")


def _run(cmd: list[str], timeout: float = 15.0, **kw):
    """Chạy lệnh ngoài mà KHÔNG bật cửa sổ console.

    Nhịp này gọi tasklist + adb mỗi 60 giây. Trên Windows, gọi từ pythonw (không
    có console) thì MỖI lần sinh một cửa sổ đen chớp lên giữa màn hình Sếp.
    AURA đã gặp đúng bệnh này ở `_phone_break_loop` và chữa bằng CREATE_NO_WINDOW
    (xem daemon._adb_run) — dùng lại đúng cách đó, đừng để tái phát.
    """
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                          creationflags=flags, **kw)

_LEDGER = PROJECT_ROOT / "data" / "ledger" / "screen_time.json"
# Không chạm chuột/phím quá ngần này thì coi như đã rời máy (màn có sáng cũng không tính).
_IDLE_CUTOFF_S = 300.0
# Tiến trình nặng — đang chạy thì HOÃN tắt máy, không cắt ngang việc của Sếp.
_HEAVY = ("ffmpeg", "ffprobe", "python", "pythonw", "node", "cargo", "msbuild")


# --------------------------------------------------------------------------- #
# ĐO: màn hình có đang sáng-và-được-dùng không?
# --------------------------------------------------------------------------- #
def _windows_locked() -> bool:
    """True khi đang ở màn hình khoá (LogonUI.exe chạy)."""
    try:
        out = _run(["tasklist", "/FI", "IMAGENAME eq LogonUI.exe", "/NH"], 10).stdout
        return "LogonUI" in out
    except Exception:  # noqa: BLE001 — đo hỏng thì coi như KHÔNG khoá (đếm tiếp,
        return False   # thà đếm thừa còn hơn bỏ sót giờ hại mắt)


def _idle_seconds() -> float:
    """Bao lâu rồi Sếp không chạm chuột/bàn phím."""
    class _LASTINPUTINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]
    try:
        info = _LASTINPUTINFO()
        info.cbSize = ctypes.sizeof(_LASTINPUTINFO)
        if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
            return 0.0
        return max(0.0, (ctypes.windll.kernel32.GetTickCount() - info.dwTime) / 1000.0)
    except Exception:  # noqa: BLE001
        return 0.0


def laptop_screen_active() -> bool:
    """Laptop có đang 'ăn mắt' Sếp không: không khoá màn VÀ có tương tác gần đây."""
    return (not _windows_locked()) and _idle_seconds() < _IDLE_CUTOFF_S


def phone_screen_active() -> bool | None:
    """Màn điện thoại có sáng không. None = không đọc được (rút cáp — chuyện thường)."""
    adb = str(getattr(settings, "adb_path", "adb") or "adb")
    try:
        devs = _run([adb, "devices"], 15)
        if sum(1 for ln in devs.stdout.splitlines()[1:] if ln.strip().endswith("device")) == 0:
            return None
        out = _run([adb, "shell", "dumpsys", "power"], 20).stdout
        for line in out.splitlines():
            low = line.strip().lower()
            if "mwakefulness=" in low:
                return "awake" in low
            if "mscreenon=" in low:
                return "true" in low
        return None
    except Exception:  # noqa: BLE001 — điện thoại là phụ, không được làm sập nhịp
        return None


# --------------------------------------------------------------------------- #
# SỔ: cộng dồn theo NGÀY, sống qua khởi động lại
# --------------------------------------------------------------------------- #
def _today() -> str:
    return date.today().isoformat()


def load_today() -> dict[str, Any]:
    """Số liệu hôm nay. Sang ngày mới thì tự về 0 (không xoá lịch sử cũ)."""
    blank = {"date": _today(), "laptop_s": 0.0, "phone_s": 0.0,
             "warned": [], "shutdown_at": 0.0, "aborted": 0}
    try:
        data = json.loads(_LEDGER.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return blank
    if not isinstance(data, dict) or data.get("date") != _today():
        return blank
    for key, default in blank.items():
        data.setdefault(key, default)
    return data


def _save(day: dict[str, Any]) -> None:
    try:
        _LEDGER.parent.mkdir(parents=True, exist_ok=True)
        tmp = _LEDGER.with_suffix(".tmp")
        tmp.write_text(json.dumps(day, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(_LEDGER)
    except OSError as exc:
        logger.warning("Ghi sổ giờ màn hình lỗi: %s", exc)


def tick(seconds: float) -> dict[str, Any]:
    """Cộng thêm `seconds` cho thiết bị nào đang sáng. Trả số liệu hôm nay."""
    day = load_today()
    if laptop_screen_active():
        day["laptop_s"] = float(day["laptop_s"]) + seconds
    if phone_screen_active() is True:
        day["phone_s"] = float(day["phone_s"]) + seconds
    _save(day)
    return day


# --------------------------------------------------------------------------- #
# CƯỠNG CHẾ
# --------------------------------------------------------------------------- #
def _heavy_running() -> bool:
    """Có việc nặng đang chạy không (render video...). Có thì HOÃN tắt máy."""
    try:
        import psutil
    except ImportError:
        return False
    try:
        for proc in psutil.process_iter(["name", "cpu_percent"]):
            name = (proc.info.get("name") or "").lower()
            if any(h in name for h in _HEAVY) and (proc.info.get("cpu_percent") or 0) > 25:
                return True
    except Exception:  # noqa: BLE001
        pass
    return False


def _fmt(seconds: float) -> str:
    total = int(seconds)
    return f"{total // 3600}h{(total % 3600) // 60:02d}p"


def status_line() -> str:
    """Câu báo cáo cho Sếp — đọc số THẬT từ sổ, không ước lượng."""
    day = load_today()
    limit_s = float(getattr(settings, "screen_time_daily_limit_min", 480)) * 60
    total = float(day["laptop_s"]) + float(day["phone_s"])
    phone = phone_screen_active()
    phone_note = "" if phone is not None else " (điện thoại chưa nối, không đếm được)"
    left = limit_s - total
    tail = f"còn {_fmt(left)}" if left > 0 else f"ĐÃ QUÁ {_fmt(-left)}"
    return (f"⏱️ Giờ màn hình hôm nay: laptop {_fmt(day['laptop_s'])} · "
            f"điện thoại {_fmt(day['phone_s'])}{phone_note}\n"
            f"   Tổng {_fmt(total)} / hạn {_fmt(limit_s)} — {tail}")


def force_shutdown(delay_s: int = 300, reason: str = "") -> tuple[bool, str]:
    """Hẹn giờ tắt máy. Windows tự hiện cảnh báo; Sếp huỷ được bằng `shutdown /a`.

    Trả (đã hẹn được chưa, lời nhắn).
    """
    if _heavy_running():
        return False, "Đang chạy việc nặng (render/build) — HOÃN tắt máy, không cắt ngang."
    # CHỐT CỨNG: đang họp / share màn hình / trình chiếu -> KHÔNG được tắt máy.
    from core.presence import busy_reason
    _busy = busy_reason()
    if _busy:
        return False, f"Sếp {_busy} — HOÃN tắt máy, không cắt ngang."
    msg = reason or "AURA: đã quá hạn giờ màn hình hôm nay. Lưu việc lại giúp Sếp."
    try:
        _run(["shutdown", "/s", "/t", str(max(60, int(delay_s))), "/c", msg[:500]], 15, check=True)
    except Exception as exc:  # noqa: BLE001
        return False, f"Không hẹn được giờ tắt máy: {exc}"
    day = load_today()
    day["shutdown_at"] = time.time() + delay_s
    _save(day)
    logger.warning("Đã hẹn TẮT MÁY sau %ds vì quá giờ màn hình.", delay_s)
    return True, (f"⛔ Đã hẹn TẮT MÁY sau {delay_s // 60} phút. "
                  "Lưu việc ngay. Cần hoãn khẩn thì gõ: shutdown /a")


def cancel_shutdown() -> bool:
    """Huỷ lệnh tắt máy đã hẹn (Sếp đổi ý / có việc gấp)."""
    try:
        _run(["shutdown", "/a"], 15)
    except Exception:  # noqa: BLE001
        return False
    day = load_today()
    day["shutdown_at"] = 0.0
    day["aborted"] = int(day.get("aborted", 0)) + 1
    _save(day)
    return True


def check_and_enforce() -> str | None:
    """Gọi mỗi nhịp: cảnh báo theo mốc, quá hạn thì hẹn tắt máy.

    Trả lời nhắn cần đẩy cho Sếp, hoặc None nếu chưa cần nói gì.
    """
    if not bool(getattr(settings, "screen_time_enabled", False)):
        return None
    day = load_today()
    limit_s = float(getattr(settings, "screen_time_daily_limit_min", 480)) * 60
    total = float(day["laptop_s"]) + float(day["phone_s"])
    warned: list[str] = list(day.get("warned") or [])

    # Cảnh báo sớm để Sếp còn kịp thu xếp — nhưng CHỈ khi chưa quá hạn. Đã vượt rồi
    # mà còn báo "đã dùng 80%" là vô lý (test bắt được: 16h39p/0h10p vẫn báo 80%).
    if total < limit_s:
        for mark, pct in (("80", 0.8), ("95", 0.95)):
            if total >= limit_s * pct and mark not in warned:
                warned.append(mark)
                day["warned"] = warned
                _save(day)
                return (f"⚠️ Đã dùng {int(pct*100)}% hạn giờ màn hình hôm nay "
                        f"({_fmt(total)}/{_fmt(limit_s)}). Thu xếp nghỉ dần đi Sếp.")
        return None
    if not bool(getattr(settings, "screen_time_enforce", False)):
        if "over" not in warned:
            warned.append("over")
            day["warned"] = warned
            _save(day)
            return (f"⛔ ĐÃ QUÁ HẠN giờ màn hình ({_fmt(total)}/{_fmt(limit_s)}). "
                    "Cưỡng chế đang TẮT — bật SCREEN_TIME_ENFORCE=true nếu Sếp muốn "
                    "AURA tự tắt máy.")
        return None
    if float(day.get("shutdown_at") or 0) > time.time():
        return None      # đã hẹn rồi, đừng hẹn chồng
    delay = int(getattr(settings, "screen_time_shutdown_delay_min", 5)) * 60
    ok, msg = force_shutdown(delay, f"AURA: quá hạn giờ màn hình ({_fmt(total)}). Lưu việc lại.")
    return msg if ok else f"⚠️ {msg}"


__all__ = ["laptop_screen_active", "phone_screen_active", "tick", "load_today",
           "status_line", "force_shutdown", "cancel_shutdown", "check_and_enforce"]
