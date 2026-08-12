"""CHỐNG CHẠY ĐÔI — mỗi bộ phận của AURA chỉ được sống MỘT bản.

Sinh sau 05/08/2026: phát hiện AURA chạy **trùng 2 bản** mọi tiến trình
(2 daemon, 2 mascot, 2 health_guard) vì có HAI launcher độc lập:
  1. `AURA_OS.bat` trong Startup Windows -> `aura_run.pyw`  (tự chạy khi mở máy)
  2. `start_aura.bat`                                        (Sếp bấm tay)
Hậu quả: mỗi lệnh bị nhân đôi — 2 lần ép nghỉ, 2 mascot đi lại, 2 lần quét việc.

Chữa tận gốc ở TIẾN TRÌNH, không phải ở launcher: bật bao nhiêu lần cũng chỉ một
bản sống. Bản thứ hai **thoát im lặng** (không báo lỗi, để Sếp khỏi tưởng hỏng).

Cách làm: named mutex của Windows — hệ điều hành tự nhả khi tiến trình chết, nên
không bao giờ kẹt khoá "ma" như file lock lúc máy tắt đột ngột.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

_ERROR_ALREADY_EXISTS = 183
# GIỮ handle/file suốt đời tiến trình — mất tham chiếu là mất khoá.
_HELD: list = []


def _acquire_windows(name: str) -> bool:
    import ctypes
    from ctypes import wintypes

    k32 = ctypes.windll.kernel32
    k32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
    k32.CreateMutexW.restype = wintypes.HANDLE
    # "Local\" = trong phiên đăng nhập này (không cần quyền như "Global\").
    handle = k32.CreateMutexW(None, False, f"Local\\AURA_OS_v2_{name}")
    if not handle:
        return True                       # không tạo được khoá -> đừng chặn oan
    if k32.GetLastError() == _ERROR_ALREADY_EXISTS:
        k32.CloseHandle(handle)
        return False
    _HELD.append(handle)
    return True


def _acquire_posix(name: str) -> bool:
    import fcntl

    path = Path(os.environ.get("TMPDIR", "/tmp")) / f"aura_{name}.lock"
    try:
        fh = path.open("w")
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (OSError, BlockingIOError):
        return False
    _HELD.append(fh)
    return True


def acquire(name: str) -> bool:
    """Giành quyền chạy cho bộ phận `name`. False = đã có bản khác đang chạy."""
    try:
        if os.name == "nt":
            return _acquire_windows(name)
        return _acquire_posix(name)
    except Exception as exc:  # noqa: BLE001 — khoá hỏng KHÔNG được chặn AURA khởi động
        logger.warning("Không tạo được khoá chống chạy đôi (%s) — vẫn chạy tiếp.", exc)
        return True


def ensure_single(name: str) -> None:
    """Đã có bản đang chạy -> THOÁT IM LẶNG. Dùng ở đầu mỗi entry point."""
    if acquire(name):
        return
    logger.info("AURA '%s' đã chạy sẵn — bản này thoát để tránh chạy đôi.", name)
    sys.exit(0)
