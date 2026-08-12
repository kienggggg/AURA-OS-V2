"""ADB hand-off for installing and pairing the AURA MB Bridge APK.

Nothing here runs on daemon startup. Installation happens only from the explicit
``--install`` command after the owner connects and authorizes their Android phone.
The network path stays local: ``adb reverse`` maps the phone's 127.0.0.1:8766 to
AURA's localhost dashboard port.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

from core.android_mb_pairing import pairing
from core.config import PROJECT_ROOT, settings

PACKAGE = "vn.aura.mbbridge"
ACTIVITY = f"{PACKAGE}/.MainActivity"
DEFAULT_APK = PROJECT_ROOT / "android" / "aura-mb-bridge" / "app" / "build" / "outputs" / "apk" / "debug" / "app-debug.apk"


def _run(adb_path: str, args: list[str], timeout: float = 30.0) -> subprocess.CompletedProcess[str]:
    kwargs: dict = {"capture_output": True, "text": True, "timeout": timeout}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    return subprocess.run([adb_path, *args], **kwargs)


def connected_devices(adb_path: str = "adb", runner: Callable[..., subprocess.CompletedProcess[str]] = _run) -> list[str]:
    """Return only devices already authorized for ADB; do not prompt or change phone state."""
    try:
        result = runner(adb_path, ["devices"], timeout=15.0)
    except (OSError, subprocess.SubprocessError):
        return []
    if result.returncode != 0:
        return []
    devices = []
    for line in result.stdout.splitlines()[1:]:
        fields = line.split()
        if len(fields) >= 2 and fields[1] == "device":
            devices.append(fields[0])
    return devices


def _endpoint_or_default(endpoint: str, config: dict[str, str]) -> str:
    selected = endpoint.strip() or config["endpoint"]
    parsed = urlparse(selected)
    if parsed.scheme != "http" or not parsed.hostname or not parsed.path:
        raise ValueError("Endpoint AURA MB Bridge phải là URL HTTP đầy đủ.")
    return selected


def _select_device(adb_path: str, serial: str, runner: Callable[..., subprocess.CompletedProcess[str]]) -> str:
    devices = connected_devices(adb_path, runner)
    selected = serial.strip()
    if selected:
        if selected not in devices:
            raise RuntimeError("Điện thoại chưa được ADB cấp quyền hoặc không đúng serial.")
        return selected
    if len(devices) == 1:
        return devices[0]
    if not devices:
        raise RuntimeError("Chưa thấy Android đã cấp quyền ADB. Cắm cáp, bật USB debugging và bấm Allow.")
    raise RuntimeError("Có nhiều điện thoại ADB. Chọn serial cụ thể để tránh cài nhầm máy.")


def configure_phone(
    *,
    endpoint: str = "",
    adb_path: str = "adb",
    serial: str = "",
    runner: Callable[..., subprocess.CompletedProcess[str]] = _run,
) -> str:
    """Pass a USB or Wi-Fi relay endpoint to an already installed bridge."""
    selected = _select_device(adb_path, serial, runner)
    config = pairing()
    target_endpoint = _endpoint_or_default(endpoint, config)
    launch = runner(
        adb_path,
        ["-s", selected, "shell", "am", "start", "-n", ACTIVITY,
         "--es", "aura_endpoint", target_endpoint, "--es", "aura_token", config["token"]],
        timeout=25.0,
    )
    if launch.returncode != 0:
        raise RuntimeError(f"Không cấu hình được AURA MB Bridge: {launch.stderr.strip() or launch.stdout.strip()}")
    return "Đã cấu hình AURA MB Bridge. Bật Notification access nếu Android chưa cấp quyền."


def pair_and_install(
    *,
    apk: Path = DEFAULT_APK,
    adb_path: str = "adb",
    serial: str = "",
    endpoint: str = "",
    runner: Callable[..., subprocess.CompletedProcess[str]] = _run,
) -> str:
    """Install the locally-built APK and pass it its local-only pairing config."""
    if not apk.is_file():
        raise FileNotFoundError(f"Chưa thấy APK AURA MB Bridge: {apk}")
    selected = _select_device(adb_path, serial, runner)

    prefix = ["-s", selected]
    reverse = runner(adb_path, [*prefix, "reverse", f"tcp:{settings.dashboard_port}", f"tcp:{settings.dashboard_port}"], timeout=20.0)
    if reverse.returncode != 0:
        raise RuntimeError(f"Không tạo được cầu nối cục bộ ADB: {reverse.stderr.strip()}")
    install = runner(adb_path, [*prefix, "install", "-r", str(apk)], timeout=90.0)
    if install.returncode != 0:
        raise RuntimeError(f"Không cài được AURA MB Bridge: {install.stderr.strip() or install.stdout.strip()}")

    configure_phone(endpoint=endpoint, adb_path=adb_path, serial=selected, runner=runner)
    return (
        "Đã cài và ghép AURA MB Bridge. Trên điện thoại, bật quyền 'Notification access' cho "
        "AURA MB Bridge; sau đó báo có MBBank sẽ đi vào Telegram của bạn."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Cài/cấu hình cầu Android MBBank cho AURA")
    parser.add_argument("--install", action="store_true", help="Cài APK + tạo adb reverse + truyền pairing token")
    parser.add_argument("--configure", action="store_true", help="Chỉ truyền endpoint mới cho APK đã cài")
    parser.add_argument("--apk", type=Path, default=DEFAULT_APK, help="Đường dẫn app-debug.apk")
    parser.add_argument("--adb", default=getattr(settings, "adb_path", "adb"), help="Đường dẫn adb.exe")
    parser.add_argument("--serial", default="", help="Serial ADB khi có nhiều điện thoại")
    parser.add_argument("--endpoint", default="", help="Endpoint USB hoặc Wi-Fi nội bộ của AURA")
    args = parser.parse_args()
    if args.install:
        print(pair_and_install(apk=args.apk, adb_path=args.adb, serial=args.serial, endpoint=args.endpoint))
    elif args.configure:
        print(configure_phone(endpoint=args.endpoint, adb_path=args.adb, serial=args.serial))
    else:
        devices = connected_devices(args.adb)
        print("Android ADB sẵn sàng: " + ", ".join(devices) if devices else "Chưa có Android ADB được cấp quyền.")


if __name__ == "__main__":
    main()
