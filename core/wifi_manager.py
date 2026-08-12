"""Quản lý wifi / mạng cho AURA — đọc thông tin kết nối THẬT trên máy Sếp.

Trả lời "mật khẩu wifi hiện tại là gì", "đang nối wifi nào", "liệt kê wifi đã lưu"
bằng lệnh `netsh` của Windows — đọc dữ liệu ĐÃ LƯU trên chính máy này (Sếp quên
mật khẩu), KHÔNG phải dò/hack mạng người khác.

Mọi lệnh ngoài đi qua _run() với CREATE_NO_WINDOW để KHÔNG nháy cửa sổ console
(bài học từ core/screen_time.py).
"""

from __future__ import annotations

import os
import re
import subprocess


def _run(args, timeout: int = 8) -> str:
    """Chạy 1 lệnh ngoài, ẩn cửa sổ console, trả stdout ('' nếu lỗi)."""
    kw = {}
    if os.name == "nt":
        kw["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        proc = subprocess.run(
            args, capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="ignore", **kw,
        )
        return proc.stdout or ""
    except Exception:  # noqa: BLE001 — hỏng thì coi như không đọc được
        return ""


def _field(text: str, *keys: str) -> str:
    """Giá trị sau dấu ':' của dòng có NHÃN khớp CHÍNH XÁC 1 trong keys.

    Khớp chính xác (không phải substring) để 'SSID' không dính nhầm 'AP BSSID'.
    """
    wanted = {k.lower() for k in keys}
    for line in text.splitlines():
        left, sep, right = line.partition(":")
        if sep and left.strip().lower() in wanted:
            return right.strip()
    return ""


def current_wifi() -> dict | None:
    """{ssid, signal, state} của wifi đang nối, hoặc None nếu không nối/không phải Windows."""
    if os.name != "nt":
        return None
    out = _run(["netsh", "wlan", "show", "interfaces"])
    ssid = _field(out, "ssid")
    if not ssid:
        return None
    return {
        "ssid": ssid,
        "signal": _field(out, "signal"),
        "state": _field(out, "state"),
    }


def list_profiles() -> list[str]:
    """Danh sách tên các wifi ĐÃ LƯU trên máy."""
    if os.name != "nt":
        return []
    out = _run(["netsh", "wlan", "show", "profiles"])
    names: list[str] = []
    for line in out.splitlines():
        left, sep, right = line.partition(":")
        if sep and "profile" in left.strip().lower():
            name = right.strip()
            if name and name not in names:
                names.append(name)
    return names


def saved_password(ssid: str) -> str | None:
    """Mật khẩu đã lưu của 1 wifi (None nếu không đọc được — có thể cần quyền admin)."""
    if os.name != "nt" or not ssid:
        return None
    out = _run(["netsh", "wlan", "show", "profile", "name=" + ssid, "key=clear"])
    return _field(out, "key content", "nội dung khóa", "nội dung khoá") or None


# --------------------------------------------------------------------------- #
# Lớp hỏi–đáp: chặn câu hỏi wifi trước khi rơi xuống LLM (LLM không biết, sẽ bịa).
# --------------------------------------------------------------------------- #
_PASS_WORDS = ("mật khẩu", "mat khau", "password", "pass", "key", "khóa", "khoá")
_LIST_WORDS = ("liệt kê", "liet ke", "danh sách", "danh sach", "các wifi",
               "cac wifi", "đã lưu", "da luu", "những wifi", "wifi nào đã")


def is_wifi_question(text: str) -> bool:
    """Câu hỏi có dính tới wifi/mạng đã lưu trên máy?"""
    t = (text or "").lower()
    if re.search(r"wi[\s-]?fi|wlan", t):
        return True
    if "mạng" in t and any(k in t for k in ("mật khẩu", "mat khau", "kết nối",
                                            "ket noi", "đang nối", "pass")):
        return True
    return False


def answer_wifi(text: str = "") -> str:
    """Trả lời câu hỏi wifi bằng dữ liệu THẬT trên máy (đọc, không bịa)."""
    if os.name != "nt":
        return "AURA chỉ đọc được wifi trên Windows thôi Sếp ạ."

    t = (text or "").lower()
    cur = current_wifi()

    if any(k in t for k in _LIST_WORDS):
        profs = list_profiles()
        if not profs:
            return "Máy chưa lưu wifi nào."
        return "Wifi đã lưu trên máy:\n" + "\n".join("• " + p for p in profs)

    if any(k in t for k in _PASS_WORDS):
        target = next((p for p in list_profiles() if p.lower() in t), None)
        if target is None:
            target = cur["ssid"] if cur else None
        if not target:
            profs = ", ".join(list_profiles()) or "(chưa lưu wifi nào)"
            return ("Máy đang không nối wifi. Wifi đã lưu: " + profs
                    + ". Sếp hỏi 'mật khẩu wifi <tên>' nhé.")
        pw = saved_password(target)
        if pw:
            return f"Mật khẩu wifi '{target}' là: {pw}"
        return (f"Không đọc được mật khẩu '{target}' — có thể cần chạy AURA bằng quyền "
                f"Administrator. Lệnh tay để Sếp tự lấy:\n"
                f'netsh wlan show profile name="{target}" key=clear')

    if cur:
        return (f"Đang nối wifi '{cur['ssid']}' "
                f"(tín hiệu {cur['signal'] or '?'}, {cur['state'] or '?'}).")
    return "Máy đang không nối wifi nào."
