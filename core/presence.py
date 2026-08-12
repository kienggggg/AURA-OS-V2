"""MẮT CANH TRƯỚC KHI NGẮT — Sếp có đang bận việc KHÔNG ĐƯỢC PHÁ không?

Sinh ra sau sự cố 05/08/2026: Health Guard phủ "khiên đen" **giữa buổi phỏng vấn
TEKY** trong lúc Sếp đang share màn hình Google Meet. Nhà tuyển dụng phê "chưa
kiểm soát được công cụ của mình". Ép nghỉ chạy MÙ là gốc bệnh.

Từ nay, mọi thứ định che/tắt màn hình PHẢI hỏi `busy_reason()` trước.

Ba giác quan (Windows, không cần cài gì thêm, không nháy console):
1. **Webcam/mic ĐANG bật** — đọc registry CapabilityAccessManager. Đây là dấu hiệu
   mạnh nhất của "đang họp video".
2. **Cửa sổ họp đang mở** — quét tiêu đề cửa sổ tìm Meet/Zoom/Teams...
3. **Cửa sổ trước mặt đang FULL MÀN HÌNH** — đang trình chiếu slide.

FAIL-SAFE: đọc lỗi -> coi như ĐANG BẬN (thà lỡ một ca nghỉ còn hơn phá cuộc họp).
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

# Tiêu đề cửa sổ báo "đang họp". Phải ĐỦ ĐẶC TRƯNG để không dính nhầm
# (vd tránh mỗi chữ "zoom" trần vì "zoom in/zoom ảnh" cũng khớp).
_MEETING_TITLES = (
    "meet.google.com", "google meet",
    "zoom meeting", "zoom workplace", "zoom cloud meetings",
    "microsoft teams", "teams meeting",
    "webex", "skype", "google hangouts", "discord",
    "phòng họp", "cuộc họp",
)
# Đang trình chiếu slide (PowerPoint để tên cửa sổ theo dạng này).
_PRESENT_TITLES = (
    "powerpoint slide show", "slide show", "trình chiếu",
    "presentation mode", "présentation",
)

_CONSENT_ROOTS = (
    r"SOFTWARE\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\webcam",
    r"SOFTWARE\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\microphone",
)


def _device_in_use() -> str | None:
    """Webcam/mic có đang được app nào dùng không? -> tên thiết bị, hoặc None.

    Windows ghi `LastUsedTimeStop = 0` khi thiết bị ĐANG được dùng, và ghi
    timestamp thật khi đã nhả. Đọc registry, không cần quyền admin.
    """
    if os.name != "nt":
        return None
    try:
        import winreg
    except ImportError:
        return None

    for root in _CONSENT_ROOTS:
        label = "webcam" if root.endswith("webcam") else "micro"
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, root) as key:
                for app in _iter_apps(winreg, key):
                    if _app_active(winreg, app):
                        return label
        except OSError:
            continue          # không có nhánh này -> bỏ qua, chưa kết luận bận
    return None


def _iter_apps(winreg, key):
    """Sinh các khoá app (gồm cả nhánh NonPackaged của app desktop)."""
    i = 0
    while True:
        try:
            name = winreg.EnumKey(key, i)
        except OSError:
            break
        i += 1
        try:
            sub = winreg.OpenKey(key, name)
        except OSError:
            continue
        if name.lower() == "nonpackaged":
            j = 0
            while True:
                try:
                    inner = winreg.EnumKey(sub, j)
                except OSError:
                    break
                j += 1
                try:
                    yield winreg.OpenKey(sub, inner)
                except OSError:
                    continue
        else:
            yield sub


def _app_active(winreg, app_key) -> bool:
    """LastUsedTimeStop == 0 nghĩa là app ĐANG dùng thiết bị ngay lúc này."""
    try:
        stop, _ = winreg.QueryValueEx(app_key, "LastUsedTimeStop")
        start, _ = winreg.QueryValueEx(app_key, "LastUsedTimeStart")
    except OSError:
        return False
    return int(stop) == 0 and int(start) > 0


def _visible_titles() -> list[str]:
    """Tiêu đề mọi cửa sổ đang hiện (chữ thường)."""
    if os.name != "nt":
        return []
    import ctypes
    from ctypes import wintypes

    u32 = ctypes.windll.user32
    titles: list[str] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def _cb(hwnd, _lparam):
        if u32.IsWindowVisible(hwnd):
            n = u32.GetWindowTextLengthW(hwnd)
            if n:
                buf = ctypes.create_unicode_buffer(n + 1)
                u32.GetWindowTextW(hwnd, buf, n + 1)
                titles.append(buf.value.lower())
        return True

    u32.EnumWindows(_cb, 0)
    return titles


def _foreground_is_fullscreen() -> bool:
    """Cửa sổ trước mặt có phủ kín màn hình không (= đang trình chiếu)?"""
    if os.name != "nt":
        return False
    import ctypes
    from ctypes import wintypes

    u32 = ctypes.windll.user32
    hwnd = u32.GetForegroundWindow()
    if not hwnd:
        return False
    # Bỏ qua desktop/shell — chúng vốn full màn, không phải trình chiếu.
    shell = u32.GetShellWindow()
    if hwnd == shell or hwnd == u32.GetDesktopWindow():
        return False

    rect = wintypes.RECT()
    if not u32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return False
    sw = u32.GetSystemMetrics(0)   # SM_CXSCREEN
    sh = u32.GetSystemMetrics(1)   # SM_CYSCREEN
    return (rect.right - rect.left) >= sw and (rect.bottom - rect.top) >= sh


def busy_reason() -> str | None:
    """Lý do KHÔNG được che/tắt màn hình lúc này; None = rảnh, ngắt được.

    Đọc lỗi -> trả lý do "không đọc được" (fail-safe: coi như đang bận).
    """
    if os.name != "nt":
        return None
    try:
        dev = _device_in_use()
        if dev:
            return f"đang dùng {dev} (nhiều khả năng đang họp/gọi video)"

        titles = _visible_titles()
        for t in titles:
            if any(k in t for k in _MEETING_TITLES):
                return "đang mở cửa sổ họp trực tuyến"
            if any(k in t for k in _PRESENT_TITLES):
                return "đang trình chiếu slide"

        if _foreground_is_fullscreen():
            return "một ứng dụng đang chạy toàn màn hình (có thể đang trình chiếu)"
    except Exception as exc:  # noqa: BLE001 — đọc hỏng thì KHÔNG được liều
        logger.warning("Không đọc được trạng thái màn hình (%s) -> coi như đang bận", exc)
        return "không đọc được trạng thái màn hình"
    return None


def can_interrupt() -> bool:
    """True khi CHẮC CHẮN an toàn để che/tắt màn hình."""
    return busy_reason() is None
