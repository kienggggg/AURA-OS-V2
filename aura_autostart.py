"""
aura_autostart.py — Biến AURA thành "thường trú": tự khởi động cùng Windows, chạy
NỀN ẨN (không cửa sổ terminal), như một phần của hệ thống.

    python aura_autostart.py --install     # đăng ký tự khởi động khi đăng nhập
    python aura_autostart.py --status      # xem đã đăng ký chưa
    python aura_autostart.py --uninstall   # gỡ tự khởi động
    python aura_autostart.py --install --startup-folder   # ép dùng Startup folder

KIẾN TRÚC (cố ý):
  AURA chạy TRONG phiên đăng nhập của Sếp (Task Scheduler ONLOGON), KHÔNG phải Windows
  Service dưới SYSTEM — vì AURA cần màn hình (Avatar), Ollama, và quyền của Sếp.
  Dùng `pythonw.exe` -> KHÔNG hiện console. Trễ 30s sau đăng nhập cho máy ổn định.

  Nếu Task Scheduler đòi quyền Admin ("Access is denied"), --install TỰ rớt sang
  Startup folder (không cần Admin) — vẫn tự chạy ẩn khi đăng nhập.

Chỉ dùng stdlib; subprocess gọi `schtasks` bằng list args, KHÔNG shell=True.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MAIN = ROOT / "main.py"
LAUNCHER = ROOT / "aura_run.pyw"   # bật CẢ não + AURA-chan, chạy nền ẩn
TASK_NAME = "AURA_OS"


def _target() -> Path:
    """Thứ sẽ tự khởi động: ưu tiên launcher (não+mặt), fallback main.py (chỉ não)."""
    return LAUNCHER if LAUNCHER.is_file() else MAIN


def _pythonw() -> str:
    """Tìm pythonw.exe (chạy không cửa sổ). Fallback python hiện tại nếu không có."""
    exe = Path(sys.executable)
    cand = exe.with_name("pythonw.exe")
    return str(cand if cand.exists() else exe)


# ---------------------------------------------------------------------------
# Windows — Startup folder (KHÔNG cần Admin)
# ---------------------------------------------------------------------------
def _startup_dir() -> Path:
    return Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def _win_install_startup_folder() -> int:
    pw = _pythonw()
    bat = _startup_dir() / "AURA_OS.bat"
    content = f'@echo off\r\nstart "" /B "{pw}" "{_target()}"\r\n'  # /B = nền; pythonw = ẩn
    try:
        bat.parent.mkdir(parents=True, exist_ok=True)
        bat.write_text(content, encoding="utf-8")
    except OSError as exc:
        print("⛔ Không ghi được Startup .bat:", exc)
        return 1
    print(f"✅ Đã đặt launcher vào Startup folder (không cần Admin):\n  {bat}")
    print("   AURA sẽ tự chạy ẩn khi Sếp đăng nhập. Thử ngay: nháy đúp file .bat đó.")
    print("   Gỡ: python aura_autostart.py --uninstall  (hoặc xoá file .bat).")
    return 0


# ---------------------------------------------------------------------------
# Windows — Task Scheduler (mặc định, bền hơn; có thể đòi Admin)
# ---------------------------------------------------------------------------
def _win_install_task() -> int:
    pw = _pythonw()
    tr = f'"{pw}" "{_target()}"'  # pythonw aura_run.pyw — bật cả não + AURA-chan, ẩn
    cmd = [
        "schtasks", "/Create", "/TN", TASK_NAME,
        "/TR", tr,
        "/SC", "ONLOGON",
        "/DELAY", "0000:30",   # chờ 30s sau đăng nhập (Ollama kịp lên)
        "/RL", "LIMITED",      # quyền người dùng thường
        "/F",                  # ghi đè nếu đã có
    ]
    print(f"Đăng ký Task Scheduler '{TASK_NAME}':\n  {tr}")
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode == 0:
        print("✅ Đã đăng ký. AURA sẽ TỰ THỨC mỗi lần Sếp đăng nhập Windows (chạy nền ẩn).")
        print("   Thử ngay không cần đăng xuất:  schtasks /Run /TN", TASK_NAME)
        return 0

    err = (r.stderr or r.stdout).strip()
    print("⛔ Task Scheduler từ chối:", err)
    if "denied" in err.lower() or "access" in err.lower():
        print("→ Chuyển sang cách KHÔNG cần Admin (Startup folder)…\n")
        return _win_install_startup_folder()
    print("   (Có thể mở PowerShell bằng 'Run as administrator' rồi chạy lại,")
    print("    hoặc: python aura_autostart.py --install --startup-folder)")
    return 1


def _win_uninstall() -> int:
    removed = False
    r = subprocess.run(["schtasks", "/Delete", "/TN", TASK_NAME, "/F"],
                       capture_output=True, text=True)
    if r.returncode == 0:
        print(f"✅ Đã gỡ Task Scheduler '{TASK_NAME}'.")
        removed = True
    bat = _startup_dir() / "AURA_OS.bat"
    if bat.is_file():
        try:
            bat.unlink()
            print(f"✅ Đã xoá Startup launcher: {bat}")
            removed = True
        except OSError as exc:
            print("⛔ Không xoá được Startup .bat:", exc)
    if not removed:
        print("[--] Không thấy đăng ký tự khởi động nào để gỡ.")
    return 0


def _win_status() -> int:
    r = subprocess.run(["schtasks", "/Query", "/TN", TASK_NAME],
                       capture_output=True, text=True)
    found = False
    if r.returncode == 0:
        print(f"✅ Task Scheduler '{TASK_NAME}' ĐÃ đăng ký:\n{r.stdout.strip()}")
        found = True
    bat = _startup_dir() / "AURA_OS.bat"
    if bat.is_file():
        print(f"✅ Startup folder launcher có sẵn: {bat}")
        found = True
    if not found:
        print("[--] CHƯA đăng ký tự khởi động. Chạy: python aura_autostart.py --install")
    return 0


# ---------------------------------------------------------------------------
# Non-Windows — mẫu systemd --user
# ---------------------------------------------------------------------------
def _posix_hint() -> int:
    unit = f"""# ~/.config/systemd/user/aura.service
[Unit]
Description=AURA OS personal assistant
After=network-online.target

[Service]
ExecStart={sys.executable} {MAIN}
WorkingDirectory={ROOT}
Restart=on-failure

[Install]
WantedBy=default.target
"""
    print("Máy này không phải Windows. Trên Linux, dùng systemd --user:\n")
    print(unit)
    print("Kích hoạt:\n  systemctl --user daemon-reload\n"
          "  systemctl --user enable --now aura.service\n"
          "  loginctl enable-linger $USER")
    return 0


# ---------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="AURA auto-start — biến AURA thành thường trú.")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--install", action="store_true", help="Đăng ký tự khởi động khi đăng nhập.")
    g.add_argument("--uninstall", action="store_true", help="Gỡ tự khởi động.")
    g.add_argument("--status", action="store_true", help="Xem trạng thái.")
    ap.add_argument("--startup-folder", action="store_true",
                    help="(Windows) Ép dùng Startup folder (không cần Admin).")
    args = ap.parse_args(argv)

    if not MAIN.is_file():
        print(f"⛔ Không thấy main.py tại {MAIN}")
        return 1

    if os.name != "nt":
        return _posix_hint()

    if args.status:
        return _win_status()
    if args.uninstall:
        return _win_uninstall()
    if args.startup_folder:
        return _win_install_startup_folder()
    return _win_install_task()


if __name__ == "__main__":
    raise SystemExit(main())
