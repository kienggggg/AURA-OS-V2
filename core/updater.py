"""
core/updater.py
===============
Cơ chế CẬP NHẬT TỰ ĐỘNG (Auto-Update) và HOT-RESTART cho AURA OS.

Tính năng:
  1. `check_and_pull_updates()`: Tự động kéo mã nguồn mới nhất qua Git (`git pull`).
  2. `restart_aura(reason)`: Khởi động lại AURA tức thì (thay thế process hiện tại bằng sys.executable)
     mà Sếp KHÔNG cần bấm Ctrl+C hay chạy lại lệnh terminal.
  3. `watch_file_changes()`: Cảm biến nhẹ quét mtime file mã nguồn / .env. Phát hiện thay đổi ->
     tự nạp lại cấu hình hoặc tự restart.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable

from core.config import PROJECT_ROOT, settings, reload_settings

logger = logging.getLogger("aura.updater")

_MONITORED_DIRS = [
    PROJECT_ROOT / "core",
    PROJECT_ROOT / "factory",
    PROJECT_ROOT / "brains",
    PROJECT_ROOT / "interface",
    PROJECT_ROOT / "tools",
    PROJECT_ROOT / "skills",
]

_MONITORED_FILES = [
    PROJECT_ROOT / "main.py",
    PROJECT_ROOT / ".env",
    PROJECT_ROOT / "api_keys" / "keys.env",
    PROJECT_ROOT / "data" / "factory" / "prompts" / "story_chapter.txt",
]


def check_and_pull_updates() -> tuple[bool, str]:
    """Kiểm tra và kéo mã nguồn mới nhất từ Git.

    Returns:
        (updated: bool, message: str)
    """
    try:
        # 1. Quét git status/fetch
        res_fetch = subprocess.run(
            ["git", "fetch"],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=30,
        )
        if res_fetch.returncode != 0:
            return False, f"Git fetch thất bại: {res_fetch.stderr.strip()[:100]}"

        # 2. Kiểm tra xem có commit mới không
        res_log = subprocess.run(
            ["git", "log", "HEAD..@{u}", "--oneline"],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=15,
        )
        new_commits = res_log.stdout.strip()
        if not new_commits:
            return False, "AURA đã ở bản mới nhất."

        # 3. Kéo git pull
        res_pull = subprocess.run(
            ["git", "pull"],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=40,
        )
        if res_pull.returncode != 0:
            return False, f"Git pull thất bại: {res_pull.stderr.strip()[:100]}"

        msg = (
            f"✅ Đã tự động cập nhật mã nguồn mới:\n{new_commits}\n\n"
            "🔄 Đang khởi động lại AURA để áp dụng..."
        )
        logger.info(msg)
        return True, msg

    except Exception as exc:  # noqa: BLE001
        logger.warning("Cập nhật Git tự động lỗi: %s", exc)
        return False, f"Lỗi cập nhật: {exc}"


def restart_aura(reason: str = "Cập nhật mã nguồn") -> None:
    """Tái khởi động AURA bằng cách nạp lại process hiện tại (Windows/Linux OK)."""
    logger.info("🔄 Tái khởi động AURA OS (%s)...", reason)
    try:
        sys.stdout.flush()
        sys.stderr.flush()
    except Exception:  # noqa: BLE001
        pass

    python = sys.executable
    args = [python] + sys.argv
    os.execv(python, args)


class FileWatcher:
    """Quét mtime file để phát hiện code/config thay đổi."""

    def __init__(self, callback: Callable[[Path], None] | None = None) -> None:
        self.callback = callback
        self._mtimes: dict[Path, float] = {}
        self._snapshot()

    def _snapshot(self) -> None:
        for f in _MONITORED_FILES:
            if f.is_file():
                self._mtimes[f] = f.stat().st_mtime

        for d in _MONITORED_DIRS:
            if d.is_dir():
                for p in d.rglob("*.py"):
                    if p.is_file():
                        self._mtimes[p] = p.stat().st_mtime

    def check(self) -> list[Path]:
        """Trả về danh sách file có thay đổi mtime."""
        changed: list[Path] = []
        for f in _MONITORED_FILES:
            if f.is_file():
                mt = f.stat().st_mtime
                if self._mtimes.get(f) != mt:
                    self._mtimes[f] = mt
                    changed.append(f)

        for d in _MONITORED_DIRS:
            if d.is_dir():
                for p in d.rglob("*.py"):
                    if p.is_file():
                        mt = p.stat().st_mtime
                        if self._mtimes.get(p) != mt:
                            self._mtimes[p] = mt
                            changed.append(p)
        return changed
